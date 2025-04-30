import modal

app = modal.App("ad-hominem-detector2",
    image=modal.Image.from_registry("nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04", add_python="3.12")
        .apt_install(
            "build-essential", "cmake", "git",
            "python3-dev", "python3-pip",
            "libopenblas-dev", "libomp-dev", "clang", "gcc"
        )
        .run_commands([
            "ln -s /usr/local/cuda/lib64/stubs/libcuda.so /usr/lib/x86_64-linux-gnu/libcuda.so.1",
            "export LD_LIBRARY_PATH=/usr/local/cuda/lib64/stubs:$LD_LIBRARY_PATH",
            "CMAKE_ARGS='-DGGML_CUDA=on' pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121"
        ])
        .pip_install("torch", "pandas", "numpy", "huggingface_hub[hf_transfer]==0.26.2", "transformers", "sentencepiece")
        .env({"LD_LIBRARY_PATH": "/app/:$LD_LIBRARY_PATH"})
        .add_local_file("sample_data_english.csv", remote_path="/root/sample_data_english.csv")
        .add_local_file("sample_data_dutch.csv", remote_path="/root/sample_data_dutch.csv")
        .add_local_file("promt_en.py", remote_path="/root/promt_en.py")
        .add_local_file("promt_nl.py", remote_path="/root/promt_nl.py"),
    volumes={
        "/root/.cache/llama.cpp": modal.Volume.from_name("llamacpp-cache", create_if_missing=True),
        "/root/results": modal.Volume.from_name("llamacpp-results", create_if_missing=True),
    },
)
@app.cls()
class AdHominemDetector:
    """
    A class-based wrapper for evaluating language models on Ad Hominem detection using llama.cpp
    and Modal cloud infrastructure.
    """
    GPU_CONFIG = "L4"
    GPU_INFO = {
        "T4": {"energy": 0.012, "nvidia_driver": "sm_75"},
        "L4": {"energy": 0.009, "nvidia_driver": "sm_89"},
        "A10G": {"energy": 0.020, "nvidia_driver": "sm_86"},
        "A100-40GB": {"energy": 0.035, "nvidia_driver": "sm_80"},
        "A100-80GB": {"energy": 0.040, "nvidia_driver": "sm_80"},
        "L40S": {"energy": 0.030, "nvidia_driver": "sm_89"},
        "H100": {"energy": 0.050, "nvidia_driver": "sm_90"},
    }

    def __init__(self):
        self.arch = self.GPU_INFO[self.GPU_CONFIG]["nvidia_driver"]
        self.model_cache = modal.Volume.from_name("llamacpp-cache", create_if_missing=True)
        self.results = modal.Volume.from_name("llamacpp-results", create_if_missing=True)
        self.cache_dir = "/root/.cache/llama.cpp"
        self.results_dir = "/root/results"
        self.power_samples = []

    def clean_result(text: str):
        """Attempt to parse a JSON result from raw text."""
        try:
            return json.loads(text)
        except Exception:
            try:
                json_start = text.find('json') + len('json')
                json_end = text.rfind('```')
                return json.loads(text[json_start:json_end].strip())
            except:
                return ast.literal_eval(text)

    def get_gpu_power(self):
        """Returns the current GPU power usage in watts."""
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True
        )
        try:
            return float(result.stdout.strip())
        except:
            return 0.0

    def monitor_power(self, interval=0.5):
        """Continuously monitor and record GPU power usage."""
        while True:
            power = self.get_gpu_power()
            self.power_samples.append(power)
            time.sleep(interval)

    def llama_cpp_inference(self, llm, prompt: str):
        """Run inference with Llama model on a prompt."""
        response = llm.create_chat_completion(
            messages=[{"role": "user", "content": str(prompt)}],
            response_format={"type": "json_object"},
        )
        return response["choices"][0]["message"]["content"]

    @modal.method()
    def download_model(self, repo_id: str, revision=None, quant: str = "Q8_0"):
        """Download a GGUF model from HuggingFace to the cache directory."""
        from huggingface_hub import snapshot_download
        return Llama.from_pretrained(
            repo_id=repo_id,
            filename=f"*{quant.lower()}.gguf",
            local_dir=self.cache_dir,
            verbose=False
        )

    @modal.method()
    def run_pipeline(self, repo_id, df, prompt, out_path, DEBUG=False):
        """Run the full evaluation pipeline for a given model and dataset."""
        monitor = threading.Thread(target=self.monitor_power, daemon=True)
        monitor.start()
        start_time = time.time()

        llm = self.download_model.remote(repo_id)
        #llm = Llama(model_path=gguf_path, n_gpu_layers=-1, n_ctx=4096, verbose=DEBUG)
        df = df.head(5)

        predictions = []
        correct = 0

        for idx, row in df.iterrows():
            full_prompt = prompt.format(text=row["Speech"].strip())
            result = self.llama_cpp_inference(llm, full_prompt)

            input_token_count = len(llm.tokenize(full_prompt.encode("utf-8")))
            output_token_count = len(llm.tokenize(result.encode("utf-8")))
            energy = (input_token_count + output_token_count) / 1000 * self.GPU_INFO[self.GPU_CONFIG]["energy"]

            try:
                parsed = self.clean_result(result)
                predicted_label = "Ad Hominem" if parsed["summary"]["count"] > 0 else "No Ad Hominem"
            except Exception:
                predicted_label = "Unknown"
                parsed = result

            is_correct = predicted_label == row["Label"].strip()
            correct += int(is_correct)

            predictions.append({
                "Speech": row["Speech"],
                "True Label": row["Label"],
                "Predicted Label": predicted_label,
                "Correct": is_correct,
                "Compute Energy": energy,
                "raw_output": parsed
            })

        accuracy = correct / len(df)
        output_csv = os.path.join(self.results_dir, out_path)
        pd.DataFrame(predictions).to_csv(output_csv, index=False)

        duration = time.time() - start_time
        avg_power = sum(self.power_samples) / len(self.power_samples)
        energy_measured = avg_power * duration
        total_energy = sum(p["Compute Energy"] for p in predictions)
        energy_token = total_energy / duration

        return accuracy, energy_measured, energy_token, duration

    @modal.method()
    def run_all_evaluations(self):
        """Run all evaluations using English and Dutch prompts on two models."""
        from promt_en import prompt as PROMPT_TEMPLATE_EN
        from promt_nl import prompt as PROMPT_TEMPLATE_NL

        repo_1 = "TheBloke/deepseek-llm-7B-chat-GGUF"
        repo_2 = "BramVanroy/GEITje-7B-ultra-GGUF"
        df_en = pd.read_csv("sample_data_english.csv")
        df_nl = pd.read_csv("sample_data_dutch.csv")

        self.run_pipeline.remote(repo_1, df_en, PROMPT_TEMPLATE_EN, "predictions_english_english_deepseek7b.csv")
        self.run_pipeline.remote(repo_1, df_nl, PROMPT_TEMPLATE_NL, "predictions_dutch_dutch_deepseek7b.csv")
        self.run_pipeline.remote(repo_2, df_nl, PROMPT_TEMPLATE_NL, "predictions_dutch_dutch_geitje.csv")
        self.run_pipeline.remote(repo_2, df_en, PROMPT_TEMPLATE_EN, "predictions_english_english_geitje.csv")

@app.local_entrypoint()
def main():
    detector = AdHominemDetector()
    detector.run_all_evaluations.remote()