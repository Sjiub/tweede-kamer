import modal
import os
import glob
import csv
import json
from pathlib import Path
from hardware import GPU_INFO
from promt_en import prompt as PROMPT_TEMPLATE_EN
from promt_nl import prompt as PROMPT_TEMPLATE_NL

# Specify name of program
app = modal.App("ad-hominem-detector")
# Specify GPU Used
GPU_CONFIG = "L4"  # or "A10G", etc.
TIME_ZONE = "Europe/Amsterdam"

# Initialise volumes
model_cache = modal.Volume.from_name("llamacpp-cache", create_if_missing=True)
cache_dir = "/root/.cache/llama.cpp"

results = modal.Volume.from_name("llamacpp-results", create_if_missing=True)
results_dir = "/root/results"

# -------------------- IMAGE -------------------- #
# Nvidia image is being downloaded with build chain to complile llama-cpp-python
# llama.cpp would also work but the python interface has better predefined configs.
# Notably, llama.cpp had the issue of not finding the stop-token.
# It was in an infinite loop of talking with itself. The issue was ofcourse,
# that the prompt template was not automatically resolved, llama-cpp-python, however, could automatically
# resolve that.
typst_version="v0.13.1"
download_image = (
    modal.Image.from_registry(f"nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04", add_python="3.12")
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
    # Install other deps
    .pip_install("torch","pandas", "numpy", "huggingface_hub[hf_transfer]==0.26.2",
        "transformers", "sentencepiece", "scikit-learn", "seaborn", "matplotlib", 
        "fpdf2", "ollama" )
    .apt_install("curl", "systemctl")
    .run_commands([
        "curl -fsSL https://ollama.com/install.sh | sh"
    ])
    .run_commands([
    # Step 2: Download Typst binary (Linux x86_64 MUSL build)
    f"curl -L -o typst.tar.xz https://github.com/typst/typst/releases/download/{typst_version}/typst-x86_64-unknown-linux-musl.tar.xz",

    # Step 3: Extract the archive
    "tar -xf typst.tar.xz",

    # Step 4: Move the binary to your system path
    "mv typst-x86_64-unknown-linux-musl/typst /usr/local/bin/"
    ])
    .entrypoint([])
    .env({"LD_LIBRARY_PATH":"/app/:$LD_LIBRARY_PATH"},)
    .env({"HUGGINGFACE_HUB_TOKEN":"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"})
    # Add files
    #.add_local_dir(".", remote_path="/root/ad-hominem")
    .add_local_file("sample_data_english.csv", remote_path="/root/sample_data_english.csv")
    .add_local_file("sample_data_dutch.csv", remote_path="/root/sample_data_dutch.csv")
    .add_local_file("DejaVuSans.ttf", remote_path="/root/DejaVuSans.ttf")
    .add_local_file("DejaVuSans-Bold.ttf", remote_path="/root/DejaVuSans-Bold.ttf")
    .add_local_file("ollama.service", remote_path= "/etc/systemd/system/ollama.service")
    .add_local_python_source("promt_en", )
    .add_local_python_source("promt_nl", )
    .add_local_python_source("hardware")
    .add_local_python_source("typst_report")
    .add_local_python_source("progress_bar")
    .add_local_python_source("key")
    
)


# -------------------- DOWNLOAD MODEL -------------------- #
cache_dir = "/root/.cache/llama.cpp"
@app.function(
    image=download_image, volumes={cache_dir: model_cache}, timeout=60 * 10,
)
def download_model(repo_id: str, revision=None, quant: str = "Q8_0", hf_token= None):
    global gguf_path
    from huggingface_hub import snapshot_download
    import shutil

    print("📦 Downloading model from:", repo_id)
    model_path = snapshot_download(repo_id, local_dir=cache_dir, token=hf_token)


    gguf_files = glob.glob(os.path.join(model_path, "*.gguf"))
    model_cache.commit()
    print("🦙 model loaded")

    if gguf_files:
        preferred = [f for f in gguf_files if quant.lower() or quant in f]
        if not preferred:
            # Check if capital letters is the issue:
            preferred = [f for f in gguf_files if quant or quant in f]
            raise FileNotFoundError(f"No GGUF file found for quant '{quant}'")

        return preferred[0]
    else:
        raise FileNotFoundError("No GGUF file found in the downloaded model directory.")

# @app.function(
#     image=download_image, volumes={"/root/.ollama": model_cache}, timeout=60 * 10,
# )
def download_ollama_model(model: str):
    #https://modal.com/blog/how_to_run_ollama_article
    import os
    import subprocess
    import time

    subprocess.run(["systemctl", "start", "ollama"])
    # Start Ollama in the background
    #process = subprocess.Popen(["ollama", "serve"])

    # Optional: wait a moment for server to boot
    import time
    time.sleep(2)

    import ollama
    ollama.pull(model)
    

# -------------------- RUN LLAMA.CPP -------------------- #

def llama_cpp_inference(llm, gguf_path: str, prompt: str, n_predict: int = -1,DEBUG=False):
    # set layers to "off-load to", aka run on, GPU
    if GPU_CONFIG is not None:
        n_gpu_layers = 9999  # all
    else:
        n_gpu_layers = 0
    response = llm.create_chat_completion(
        messages=[
            {"role": "user", "content": str(prompt)},
        ],
        response_format={
        "type": "json_object"
        },
        #temperature=0,
    )
    return response["choices"][0]["message"]["content"]
def ollama_inference(model,msg):
    import ollama
    import os
    #os.environ['OLLAMA_MODELS'] = cache_dir

    # Run inference with a model (e.g., llama3)
    response = ollama.chat(
        model=model,
        messages=[
            {'role': 'user', 'content': msg}
        ]
    )
    return response['message']['content']

# -------------------- Helper -------------------- #
def clean_result(text: str):
    """
        Multiple ways to resolve different ways a llm might return json.
        1. normal
        2. embedded in text but marked as specified in the template
        3. normal json but with '' instead of ""
    """
    import json
    import ast
    import re
    text = str(text).strip()
     # Try to extract JSON block from markdown-style ```json ... ``` block
    if re.search(r'```json\b', text, re.IGNORECASE):
        try:
            match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
            if match:
                json_str = match.group(1).strip()
                return json.loads(json_str)
        except Exception:
            pass

    # Try raw JSON
    try:
        return json.loads(text)
    except Exception:
        pass

    # Try using ast.literal_eval for single-quoted "JSON"
    try:
        return ast.literal_eval(text)
    except Exception:
        pass

    raise ValueError("Unable to parse JSON from text.")

def get_gpu_power():
    """
        Return power usage of cuda driver
    """
    import subprocess
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True
    )
    try:
        return float(result.stdout.strip())
    except:
        return 0.0

power_samples = []
def monitor_power(interval=0.5):
    """
        Monitor average power consumtion of cuda driver
    """
    import time
    while True:
        power = get_gpu_power()
        power_samples.append(power)
        time.sleep(interval)
# -------------------- EVALUATE -------------------- #
cache_dir = "/root/.cache/llama.cpp"
@app.function(
    image=download_image,
    timeout=60 * 60,
    volumes={
        results_dir: results,
        cache_dir: model_cache,
        },
    gpu=GPU_CONFIG)
def run_pipeline(repo_id, query, prompt, quant="Q8_0", ollama=False, hf_token=None, DEBUG=False):
    """
        Method to run inference on a model.
        `repo_id` is the huggingface link to a gguf compatibale model.
        `query` A list of texts to analyse
        `prompt` The promt, it has to have the marker {text} where the query element will be inserted
        `quant` Quantisation of gguf file
        `hf_token` Api token to hugging face, for models with restriction
    """
    import pandas as pd
    import time
    import threading
    from llama_cpp import Llama
    from progress_bar import storming_progress_bar
    import subprocess

    print("🚀 Starting pipeline...")
    monitor = threading.Thread(target=monitor_power, daemon=True)
    monitor.start()
    start_time = time.time()

    # Initialise llm
    if ollama:
        # starts the ollama 
        download_ollama_model(repo_id)
        #process = subprocess.Popen(["ollama", "serve"])
    else:
        gguf_path = download_model.remote(repo_id,quant=quant, hf_token=hf_token)
        llm = Llama(model_path=gguf_path, n_gpu_layers=-1, n_ctx=4096, verbose=DEBUG)

    inference = []
    for idx, row in enumerate(query):
        storming_progress_bar(idx, len(query), start_time, update_message=f'Row: {idx}')
        _prompt = prompt
        full_prompt = _prompt.format(text=row)
        
        if ollama:
            result = ollama_inference(repo_id, full_prompt)
        else:
            result = llama_cpp_inference(llm, gguf_path, full_prompt)

        # # #Calculate tokens
        # input_tokens = llm.tokenize(full_prompt.encode("utf-8"))
        # input_token_count = len(input_tokens)

        # output_tokens = llm.tokenize(result.encode("utf-8"))
        # output_token_count = len(output_tokens)

        # energy = (input_token_count + output_token_count) / 1000 * GPU_INFO[GPU_CONFIG]["energy"]
        energy = 0
        try:
            parsed = clean_result(result)
        except Exception as e:
            print(f"❌ Error parsing result at row {idx}: {e}")
            print("result: ", result)
            parsed = result

        inference.append({
            "result": parsed,
            "energy_by_token": energy,
            "index": idx
        })

    # Print metrix
    duration = time.time() - start_time
    avg_power = sum(power_samples) / len(power_samples)
    energy_measured = avg_power * duration

    df = pd.DataFrame(inference)
    cost = duration* GPU_INFO[GPU_CONFIG]["price_per_sec"]
    energy_by_token = df["energy_by_token"].sum()
    print(f"\n⏱️ Duration: {duration:.2f} for {len(query)} querys. Average computation time: {duration/len(query)}")
    print(f"⚡ Estimated power (by nvidia-smi): {energy_measured:.4f} W")
    print(f"🔋 Estimated power ( by tokenizer): { energy_by_token:.4f} W")
    print(f"🤑 Cost: {cost:.2f} 💰")

    return inference, energy_measured, duration,cost, power_samples

def compute_results(inference, df):
    import pandas as pd
    from sklearn.metrics import accuracy_score
    inference_df = pd.DataFrame(inference)
    # assign error
    try:
        assert df.shape[0] == inference_df.shape[0], (
            f"Row mismatch: df has {df.shape[0]} rows, "
            f"inference_df has {inference_df.shape[0]} rows.\n"
            f"inference_df head:\n{inference_df.head()}"
        )
        
        df["result"] = inference_df["result"].values
        df["energy_by_token"] = inference_df["energy_by_token"].values
        df["index"] = inference_df["index"].values

    except AssertionError as e:
        print("Assertion failed:", e)
        df["result"] = inference_df["result"]
        df["energy_by_token"] = inference_df["energy_by_token"]
        df["index"] = inference_df["index"]

    

    def extract_predicted_label(result):
        json
        try:
            # If result is a string, try to load it
            if isinstance(result, str):
                result = json.loads(result)

            count = result.get("summary", {}).get("count", 0)
            print("➡️ Count value:", count)
            return "Ad Hominem" if count > 0 else "No Ad Hominem"
        except Exception as e:
            # Optional: print(e) for debugging
            return "Unknown"

    df["predicted"] = df["result"].apply(extract_predicted_label)

    len_unclassified = len(df[df["predicted"]== "Unknown"])
    df = df[df["predicted"] != "Unknown"]

    # Now make types consistent
    df["truth_label"] = df["Label"] != "No Ad Hominem"
    df["predicted"] = df["predicted"] != "No Ad Hominem"
 
    accuracy = accuracy_score(df["truth_label"], df["predicted"])
    print(f"🎯 Accuracy: {accuracy:.2%}")
    return df, accuracy, len_unclassified

def plot_confusion_matrix(df, path="confusion_matrix.png"):
    from sklearn.metrics import confusion_matrix, accuracy_score
    import seaborn as sns
    import matplotlib.pyplot as plt

    y_true = df["truth_label"]
    y_pred = df["predicted"]

    # Use boolean labels for computation
    labels = [False, True]
    label_names = ["No Ad Hominem", "Ad Hominem"]

    # Compute accuracy
    accuracy = accuracy_score(y_true, y_pred)
    print(f"✅ Accuracy: {accuracy:.2%}")

    # Compute confusion matrix
    cm = confusion_matrix(y_true, y_pred, labels=labels)

    # Plot confusion matrix
    plt.figure(figsize=(6, 5))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                xticklabels=label_names,
                yticklabels=label_names)
    plt.xlabel("Predicted Label")
    plt.ylabel("True Label")
    plt.title("Confusion Matrix")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()

    return path

def plot_power_samples(power_samples, output_path="power_usage_plot.png"):
    import matplotlib.pyplot as plt
    plt.figure(figsize=(10, 4))
    plt.plot(power_samples, label="GPU Power (W)", linewidth=1.2)
    plt.title("GPU Power Usage Over Time")
    plt.xlabel("Sample Number")
    plt.ylabel("Power Draw (Watts)")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()
    return output_path
@app.function(image=download_image,volumes={results_dir: results,},timeout=60 * 60,)
def detect_ad_hominem(df, prompt, model,quant, ollama, dataset_language, prompt_language, dataset_nick_name, prompt_nick_name,hf_token):
    import pandas as pd
    from datetime import datetime
    from zoneinfo import ZoneInfo

    querys = df["Speech"].to_list()
    inference, energy_measured, duration, cost, power_samples = run_pipeline.remote(
         model,
         querys,
         prompt,
         ollama=ollama,
         quant=quant,
         hf_token=hf_token
    )
    inference_df, accuracy, len_unparsed = compute_results(inference, df)
    confusion_matrix_path = plot_confusion_matrix(inference_df, path=f'confusion_matrix.png')
    plot_power_path = plot_power_samples(power_samples, output_path=f'power_plot.png')
    generate_pdf(
        inference_df,
        prompt,
        dataset_language,
        prompt_language,
        dataset_nick_name,
        prompt_nick_name,
        model,
        quant,
        accuracy,
        len_unparsed,
        energy_measured,
        duration,
        cost,
        power_samples,
        [confusion_matrix_path, plot_power_path])
    now=datetime.now(ZoneInfo(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")
    path = f"results_{prompt_language}_{dataset_language}_{model}_{now}.csv".replace("/","_")
    out_path = os.path.join(results_dir,path)
    pd.DataFrame(inference).to_csv(out_path, index=False)
    print("📁 Results saved to:", out_path)


def generate_pdf(inference_df, prompt, dataset_language, prompt_language, dataset_nick_name, prompt_nick_name, model, quant, accuracy,len_unparsed, energy_measured, duration, cost, power_samples,graph_paths ):
    from typst_report import TypstReport, get_prompt_hash
    from datetime import datetime
    from zoneinfo import ZoneInfo

    report = TypstReport()


    # Open csv file
    # Generate unique identifier
    prompt_hash = str(get_prompt_hash(prompt))
    now=datetime.now(ZoneInfo(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")
    info = [
            ("Model", model),
            ("Quantisation", quant),
            ("Prompt Version", f'{prompt_nick_name}_{prompt_language}_{prompt_hash}'),
            ("Dataset", dataset_nick_name),
            ("Date & Time", now),
            ("Duration (s)", f"{duration:.2f}"),
            ("Cost ($)", f"{cost:.2f}"),
            ("Accuracy", f"{accuracy:.2f}%"),
            ("Unparsed ", len_unparsed),
            ("n tests", len(inference_df)),
            ("Electricity Usage (W)", f"{energy_measured:.2f}")
        ]
    report.add_general_info(info,graph_paths)

    inference_df["cleaned_output"] = inference_df["result"].apply(clean_result)
    for _, test in inference_df.iterrows():
        report.add_test(test)
    path = f"results_{prompt_language}_{dataset_language}_{model}_{now}".replace("/","_")
    out_path = os.path.join(results_dir, path)
    report.save(f"{out_path}.typ", f"{out_path}.pdf")

@app.function(
    image=download_image,
    timeout=60 * 60 * 3,  # 3 hour
    volumes={results_dir: results, cache_dir: model_cache},
)
def run_all_evaluations():
    import pandas as pd
    from promt_en import prompt as PROMPT_TEMPLATE_EN
    from promt_nl import prompt as PROMPT_TEMPLATE_NL
    from key import hf_token


    repo_id = "TheBloke/deepseek-llm-7B-chat-GGUF"
    df = pd.read_csv("sample_data_english.csv")
    df_nl = pd.read_csv("sample_data_dutch.csv")
    # Sample indices from one of the dataframes
    sampled_indices = df.sample(n=2, random_state=42).index

    # Use the same indices to sample both dataframes
    sampled_en = df.loc[sampled_indices]
    sampled_nl = df_nl.loc[sampled_indices]

    def run_english_test(model, quant):
        detect_ad_hominem.remote(
        sampled_en, PROMPT_TEMPLATE_EN,
        model,quant,
        dataset_language="EN", prompt_language="EN", dataset_nick_name="US_election",
        prompt_nick_name="Davids-promt",hf_token=hf_token)
    def run_dutch_test(model, quant):
        detect_ad_hominem.remote(
        sampled_nl, PROMPT_TEMPLATE_NL,
        model,quant,
        dataset_language="NL", prompt_language="NL", dataset_nick_name="US_election",
        prompt_nick_name="Davids-promt",hf_token=hf_token)
    detect_ad_hominem.remote(
        sampled_en, PROMPT_TEMPLATE_EN,
        "deepseek-r1:8b", "",ollama=True,
        dataset_language="EN", prompt_language="EN", dataset_nick_name="US_election",
        prompt_nick_name="Davids-promt",hf_token=hf_token
    )

    # detect_ad_hominem.remote(
    #     sampled_df, PROMPT_TEMPLATE_EN,
    #     "google/gemma-3-27b-pt-qat-q4_0-gguf","Q4_0",
    #     dataset_language="EN", prompt_language="EN", dataset_nick_name="US_election",
    #     prompt_nick_name="Davids-promt",hf_token=hf_token)
    # run_english_test("BramVanroy/GEITje-7B-ultra-GGUF", "Q8_0")
    # run_dutch_test("BramVanroy/GEITje-7B-ultra-GGUF", "Q8_0")
    # run_english_test("XelotX/DeepSeek-R1-Distill-Llama-8B-GGUF", "Q8_0")
    # run_dutch_test("XelotX/DeepSeek-R1-Distill-Llama-8B-GGUF", "Q8_0")

    # run_dutch_test("unsloth/phi-4-GGUF", "Q8_0")
    # run_english_test("unsloth/phi-4-GGUF", "Q8_0")

    
# "unsloth/Llama-4-Scout-17B-16E-Instruct-GGUF"
# "unsloth/DeepSeek-R1-Distill-Qwen-32B-GGUF"
# https://huggingface.co/unsloth/DeepSeek-R1-Distill-Qwen-32B-GGUF -> watch out for prompt template
    # accuracy_en_depseek, energy_en_depseek, tokens_en_depseek, duration_en_depseek = run_pipeline.remote(
    #     repo_id, df, PROMPT_TEMPLATE_EN, "predictions_english_english_deepseek7b.csv"
    # )
    # accuracy_nl_deepseek, energy_nl_deepseek, tokens_nllabels_deepseek, duration_nl_deepseek = run_pipeline.remote(
    #     repo_id, df_nl, PROMPT_TEMPLATE_NL, "predictions_dutch_dutch_deepseek7b.csv"
    # )

    # repo_id = "BramVanroy/GEITje-7B-ultra-GGUF"
    # accuracy_nl_geitje, energy_nl_geitje, tokens_nl_geitje, duration_nl_geitje = run_pipeline.remote(
    #     repo_id, df_nl, PROMPT_TEMPLATE_NL, "predictions_dutch_dutch_geitje.csv"
    # )
    # accuracy_en_geitje, energy_en_geitje, tokens_en_geitje, duration_en_geitje = run_pipeline.remote(
    #     repo_id, df, PROMPT_TEMPLATE_EN, "predictions_english_english_geitje.csv"
    # )

    # print(f"EN-EN DeepSeek ➤ Accuracy: {accuracy_en_depseek:.2f}, Energy: {energy_en_depseek} J, Tokens: {tokens_en_depseek}, Duration: {duration_en_depseek:.2f}s")
    # print(f"NL-NL DeepSeek ➤ Accuracy: {accuracy_nl_deepseek:.2f}, Energy: {energy_nl_deepseek} J, Tokens: {tokens_nl_deepseek}, Duration: {duration_nl_deepseek:.2f}s")
    # print(f"EN-EN GEITje     ➤ Accuracy: {accuracy_en_geitje:.2f}, Energy: {energy_en_geitje} J, Tokens: {tokens_en_geitje}, Duration: {duration_en_geitje:.2f}s")
    # print(f"NL-NL GEITje     ➤ Accuracy: {accuracy_nl_geitje:.2f}, Energy: {energy_nl_geitje} J, Tokens: {tokens_nl_geitje}, Duration: {duration_nl_geitje:.2f}s")
    # accuracy_en_gemma3, energy_en_gemma3, tokens_en_gemma3, duration_en_gemma3 = run_pipeline.remote(
    #      "google/gemma-3-27b-pt-qat-q4_0-gguf",
    #      df,
    #      PROMPT_TEMPLATE_EN,
    #      "predictions_english_english_gemma3.csv",
    #      quant="Q4_0"
    # )
    #
    #print(f"EN-EN gemma3 ➤ Accuracy: {accuracy_en_gemma3:.2f}, Energy: {energy_en_gemma3} J, Tokens: {tokens_en_gemma3}, Duration: {duration_en_gemma3:.2f}s")


@app.local_entrypoint()
def main():
    print("📤 Submitting cloud job...")
    run_all_evaluations.remote()

    print("✅ Job submitted! You can now close your laptop.")
