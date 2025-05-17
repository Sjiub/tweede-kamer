import modal
import os
import glob
import csv
import json
from pathlib import Path
from hardware import GPU_INFO
from prompt import PROMPT_CONFIGS

# Specify name of program
app = modal.App("ad-hominem-detector")
# Specify GPU Used
GPU_CONFIG = "L4"  # or "A10G", etc.
TIME_ZONE = "Europe/Amsterdam"

# Initialise volumes
model_cache = modal.Volume.from_name("ollama-models", create_if_missing=True)
ollama_dir = "/opt/ai/models"

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
llamacpp = "ghcr.io/ggerganov/llama.cpp:full-cuda"
python_llamacpp = "nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04"
download_image = (
    modal.Image.from_registry(llamacpp, add_python="3.12")
    # .apt_install(
    #     "build-essential", "cmake", "git",
    #     "python3-dev", "python3-pip",
    #     "libopenblas-dev", "libomp-dev", "clang", "gcc"
    # )
    # .run_commands([
    #     "ln -s /usr/local/cuda/lib64/stubs/libcuda.so /usr/lib/x86_64-linux-gnu/libcuda.so.1",
    #     "export LD_LIBRARY_PATH=/usr/local/cuda/lib64/stubs:$LD_LIBRARY_PATH",
    #     "CMAKE_ARGS='-DGGML_CUDA=on' pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121"
    # ])
    # Install other deps
    .pip_install("torch","pandas", "numpy", "huggingface_hub[hf_transfer]==0.26.2",
        "transformers", "sentencepiece", "scikit-learn", "seaborn", "matplotlib", 
        "fpdf2", "ollama", "langdetect", "pytest", "jinja2")
    .apt_install("curl", "systemctl")
    .run_commands([
        "curl  -fsSL https://ollama.com/install.sh | sh"
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
    #.env({"OLLAMA_MODELS":ollama_dir})
    .env({"LD_LIBRARY_PATH":"/app/:$LD_LIBRARY_PATH"},)
    .env({"HUGGINGFACE_HUB_TOKEN":"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"})
    #.run_commands(f"OLLAMA_MODELS={ollama_dir} ollama serve &")
    # Add files
    #.add_local_dir(".", remote_path="/root/ad-hominem")
    .add_local_file("sample_data_english.csv", remote_path="/root/sample_data_english.csv")
    .add_local_file("sample_data_dutch.csv", remote_path="/root/sample_data_dutch.csv")
    .add_local_file("merged_annotations.csv", remote_path="/root/merged_annotations.csv")
    .add_local_file("ollama.service", remote_path= "/etc/systemd/system/ollama.service")
    .add_local_python_source("prompt_en", )
    .add_local_python_source("prompt_nl", )
    .add_local_python_source("hardware")
    .add_local_python_source("typst_report")
    .add_local_python_source("progress_bar")
    .add_local_python_source("llm_test")
    .add_local_python_source("prompt_en_zeroshot")
    .add_local_python_source("prompt_en_fewshot")
    .add_local_python_source("prompt_en_CCoT")
    .add_local_python_source("prompt_nl_zeroshot")
    .add_local_python_source("prompt_nl_fewshot")
    .add_local_python_source("prompt_nl_CCoT")
    .add_local_python_source("prompt")
)

# -------------------- DOWNLOAD MODEL -------------------- #
@app.function(
    image=download_image, volumes={ollama_dir: model_cache}, timeout=60 * 10,
)
def download_model(llm_test):
    global gguf_path
    from huggingface_hub import snapshot_download
    import shutil
    # from llm_test import LLM_TEST

        
    # from llm_test import LLM_TEST
    # from llama_cpp import Llama
    # llm = Llama.from_pretrained(
    # repo_id="Mungert/gemma-3-27b-it-GGUF",
    # filename="gemma-3-27b-it-q4_0.gguf",
    # cache_dir=ollama_dir  # <-- your custom location
    # )
    return ollama_dir + "/" + "gemma-3-27b-it-q4_0.gguf"

    print("📦 Downloading model from:", repo_id)
    model_path = snapshot_download(llm_test.model, local_dir=cache_dir, token=llm_test.hf_token)
    gguf_files = glob.glob(os.path.join(model_path, "*.gguf"))
    model_cache.commit()
    print("🦙 model loaded")

    if gguf_files:
        preferred = [f for f in gguf_files if llm_test.quant.lower() or llm_test.quant in f]
        if not preferred:
            # Check if capital letters is the issue:
            preferred = [f for f in gguf_files if llm_test.quant or llm_test.quant in f]
            raise FileNotFoundError(f"No GGUF file found for quant '{llm_test.quant}'")

        return preferred[0]
    else:
        raise FileNotFoundError("No GGUF file found in the downloaded model directory.")

@app.function(
    image=download_image,
    timeout=60 * 60,
    volumes={
        results_dir: results,
        ollama_dir: model_cache
        },
    )
def download_ollama_model(model: str):
    #https://modal.com/blog/how_to_run_ollama_article
    import os
    import subprocess
    import time

    subprocess.Popen(["ollama", "serve"], env={**os.environ, "OLLAMA_MODELS": ollama_dir})

    # Optional: wait a moment for server to boot
    #import time
    #time.sleep(2)
    print("download model: ", model)

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

@app.function(
    image=download_image,
    timeout=60 * 60,
    volumes={
        results_dir: results,
        ollama_dir: model_cache
        },
    gpu=GPU_CONFIG)
def llama_cpp_inference_batch(llm, list_msg, timeout, temperature=0):
    import ollama
    import subprocess
    import os
    import time
    import threading
    
    # from llama_cpp import Llama
    
    # llm = Llama(
    #     model_path=f'{ollama_dir}/models--Mungert--gemma-3-27b-it-GGUF/blobs/f3b2259712093260f0f5336d879c8270f23429d1693f6ae5b756086d2c695668',
    #     n_ctx=4096,
    #     n_gpu_layers=-1,
    #     )
    from jinja2 import Template
    import sys

    def render_prompt(messages, chat_template="gemma3"):
        """
        Renders a chat prompt using Gemma 3-style formatting:
        <bos><start_of_turn>user ...<end_of_turn>
        <start_of_turn>model ...<end_of_turn>
        ...
        Appends a final <start_of_turn>model\n to indicate LLM should continue.
        """
        prompt = ""

        for message in messages:
            role = message["role"]
            content = message["content"].strip()
            prompt += f"<start_of_turn>{role}\n{content}<end_of_turn>\n"

        # Add opening for model response
        prompt += "<start_of_turn>model\n"
        return prompt

#sha256-1fa8532d986d729117d6b5ac2c884824d0717c9468094554fd1d36412c740cfc', n_ctx=4096, verbose=True)
    monitor = threading.Thread(target=monitor_power, daemon=True)
    monitor.start()
    def extract_model_json_block(text):
        start_marker = "\nmodel"
        end_marker = "[end of text]"

        start_index = text.find(start_marker)
        end_index = text.find(end_marker)

        if start_index == -1 or end_index == -1:
            raise ValueError("Markers not found in text.")

        # Extract the block exactly as it appears between the markers
        block = text[start_index + len(start_marker):end_index].strip()

        return block



    # Doc: https://docs.unsloth.ai/basics/gemma-3-how-to-run-and-fine-tune
    # https://blog.steelph0enix.dev/posts/llama-cpp-guide/#llama-cli
    def run_llama_cli_chat(
        messages,
        model_path,
        llama_cli_path="/app/llama-cli",
        temperature=0,
        top_k=64,
        top_p=0.95,
        repeat_penalty=1,
        min_p=0.01,
        n_gpu_layers=-1,
        threads=None,
        ctx_size=16384,
        seed=3407,
        prio=2,
        timeout=timeout
    ):
        """
        Calls llama-cli with a Gemma-style prompt. Only includes CLI args that are set.
        Outputs logs directly to terminal.
        """
        # Start building command
        cmd = [
            llama_cli_path,
            "--model", model_path
        ]

        # Conditionally add optional arguments
        if threads is not None:
            cmd += ["--threads", str(threads)]
        if ctx_size is not None:
            cmd += ["--ctx-size", str(ctx_size)]
        if n_gpu_layers is not None:
            cmd += ["--n-gpu-layers", str(n_gpu_layers)]
        if seed is not None:
            cmd += ["--seed", str(seed)]
        if prio is not None:
            cmd += ["--prio", str(prio)]
        if temperature is not None:
            cmd += ["--temp", str(temperature)]
        if repeat_penalty is not None:
            cmd += ["--repeat-penalty", str(repeat_penalty)]
        if min_p is not None:
            cmd += ["--min-p", str(min_p)]
        if top_k is not None:
            cmd += ["--top-k", str(top_k)]
        if top_p is not None:
            cmd += ["--top-p", str(top_p)]

        # Always include this flag (optional: make it conditional too)
        cmd += ["-no-cnv"]

        # Render prompt with Gemma chat format
        prompt = render_prompt(messages)
        cmd += ["--prompt", prompt]
        try:
            # Use a temporary file or PIPE for capturing output if needed
            print("TP 0")
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=sys.stderr,
                text=True
            )

            captured_output = []

            for line in process.stdout:
                print(line, end='')          # Print to console
                captured_output.append(line) # Capture output

            process.wait()

            output = ''.join(captured_output).strip()
            return {
                "message": {"content": extract_model_json_block(output)},
                "error": "",
                "status": ""
            }

        except subprocess.TimeoutExpired:
            print("output llm: Timeout")
            return {
                "message": {"content": ""},
                "error": "LLM process timed out and was terminated.",
                "status": -1
            }

        except Exception as e:
            print("output llm: Error -> ", str(e))
            return {
                "message": {"content": ""},
                "error": str(e),
                "status": -2
            }
    responses = []
    for messages in list_msg:
        start_time = time.time()
        power_samples.clear()

        result = run_llama_cli_chat(
            messages=messages,
            model_path=f'{ollama_dir}/models--Mungert--gemma-3-27b-it-GGUF/blobs/f3b2259712093260f0f5336d879c8270f23429d1693f6ae5b756086d2c695668',
            temperature=0,
            )
        duration = time.time() - start_time
        avg_power = sum(power_samples) / len(power_samples) if power_samples else 0
        energy = avg_power * duration

        responses.append({
            "index": messages[-1]["index"],
            "raw": result,
            "duration": duration,
            "energy": energy,
            "power-samples": power_samples.copy(),
            "is_timeout": result["status"] == -1
        })

    return responses
@app.function(
    image=download_image,
    timeout=60 * 60,
    volumes={
        results_dir: results,
        ollama_dir: model_cache
        },
    gpu=GPU_CONFIG)
def ollama_inference(model, list_msg, timeout, temperature=0):
    import ollama
    import subprocess
    import os
    import time
    import threading
    from concurrent.futures import ThreadPoolExecutor, TimeoutError

    # Initialise ollama
    subprocess.Popen(["ollama", "serve"], env={**os.environ, "OLLAMA_MODELS": ollama_dir})
    time.sleep(0.5)
    monitor = threading.Thread(target=monitor_power, daemon=True)
    monitor.start()

    def call_ollama(message):
        return ollama.chat(model=model, messages=message, options={"temperature": temperature})

    responses = []

    with ThreadPoolExecutor(max_workers=1) as executor:
        for messages in list_msg:
            start_time = time.time()
            power_samples.clear()

            future = executor.submit(call_ollama, messages)
            try:
                response = future.result(timeout=timeout)
                is_timeout = False
                raw = response
            except TimeoutError:
                is_timeout = True
                raw = None
            except Exception as e:
                raw = e
                is_timeout = False

            duration = time.time() - start_time
            avg_power = sum(power_samples) / len(power_samples) if power_samples else 0
            energy = avg_power * duration

            responses.append({
                "index": messages[-1]["index"],
                "raw": raw,
                "duration": duration,
                "energy": energy,
                "power-samples": power_samples.copy(),
                "is_timeout": is_timeout
            })

    return responses
# -------------------- Helper -------------------- #


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
def run_pipeline(llm_test, DEBUG=False):
    import pandas as pd
    import time
    import threading
    #from llama_cpp import Llama
    from progress_bar import storming_progress_bar
    import subprocess
    from llm_test import LLM_TEST
    from concurrent.futures import ThreadPoolExecutor, as_completed

    print("🚀 Starting pipeline...")
    # TODO find different way in monitoring power
    start_time = time.time()

    # Initialise llm
    if llm_test.ollama:
        # starts the ollama 
        download_ollama_model.remote(llm_test.model)
        #process = subprocess.Popen(["ollama", "serve"])
    else:
        #gguf_path = download_model.remote(llm_test)
        #llm = Llama(model_path=gguf_path, n_gpu_layers=-1, n_ctx=4096, verbose=DEBUG)
        pass

    def process_batch():
        #while True:
        indices = llm_test.get_compute_batch()
        #if indices.empty:
        #    break
        query = []
        for idx in indices:
            messages = []
            # Add system prompt
            if llm_test.system_prompt != None:
                messages.append({'role': 'system', 'content': llm_test.system_prompt})
            df = llm_test.get_df()
            pos = df.index.get_loc(idx)  # Get integer position of index
            start = max(0, pos - llm_test.row_count)
            if pos == 0:
                rows = df.iloc[[0]]
            else:  # as DataFrame
                rows = df.iloc[start:pos]

            messages.extend([   
                {'index': idx, 'role': 'user', 'content': llm_test.prompt.format(text=row)} 
                for row in rows[llm_test.text_key]
            ])
            query.append(messages)
        if llm_test.ollama:
            results = ollama_inference.remote(llm_test.model, query, llm_test.timeout)
        else:
            results = llama_cpp_inference_batch.remote(llm_test.model, query, llm_test.timeout)
        llm_test.write_result(results)
        llm_test.compute_forecast_report(start_time, GPU_INFO, GPU_CONFIG)  
    process_batch()
    # #Inference execution
    # with ThreadPoolExecutor(max_workers=llm_test.multithreads) as executor:
    #     futures = [executor.submit(process_batch) for _ in range(llm_test.multithreads)]

    #     for future in as_completed(futures):
    #         try:
    #             future.result()  # Wait for thread to complete
    #         except Exception as e:
    #             print(f"A thread failed with error: {e}")
            
    llm_test.compute_results()
    llm_test.generate_tk_report(start_time, GPU_INFO, GPU_CONFIG )#power_samples)
    return llm_test

def compute_results(llm_test):
    import pandas as pd
    from sklearn.metrics import accuracy_score

    df = llm_test.get_df()

    df["predicted"] = df["result"].apply(llm_test.parse_function)

    len_unclassified = len(df[df["predicted"]== "Unknown"])
    df = df[df["predicted"] != "Unknown"]

    # Now make types consistent
    df["truth_label"] = df["Label"] != "No Ad Hominem"
    df["predicted"] = df["predicted"] != "No Ad Hominem"
 
    accuracy = accuracy_score(df["truth_label"], df["predicted"])
    print(f"🎯 Accuracy: {accuracy:.2%}")
    llm_test.save_results(output=df, accuracy=accuracy, len_unclassified=len_unclassified)
    return llm_test

def prep_data(prompt_type, sample_strategy="full", specific_indices=None, sample_size=None):
    """
    Unified function to run ad hominem analysis with different sampling strategies.
    
    Args:
        prompt_type (str): Type of prompt to use ("zeroshot", "fewshot", "ccot")
        sample_strategy (str): How to sample the data:
            - "full": Use complete dataset
            - "balanced": Equal number of positive/negative samples
            - "specific": Use specific row indices
            - "random": Random sample of specified size
        specific_indices (list): List of specific indices to analyze (for "specific" strategy)
        sample_size (int): Number of samples to use (for "balanced" or "random" strategy)
    """
    import pandas as pd
    
    # Validate prompt type
    if prompt_type not in PROMPT_CONFIGS:
        raise ValueError(f"Unknown prompt type: {prompt_type}. Available types: {list(PROMPT_CONFIGS.keys())}")

    prompt_config = PROMPT_CONFIGS[prompt_type]
    print(f"Using {prompt_config['name']} prompt: {prompt_config['description']}")

    # Load dataset
    df = pd.read_csv("merged_annotations.csv", sep=";")

    # Sample selection based on strategy
    if sample_strategy == "full":
        debate_df = df
        strategy_suffix = ""
    
    elif sample_strategy == "balanced":
        sample_size = sample_size or 10  # Default to 10 if not specified
        half_size = sample_size // 2
        class_0 = df[df['final_label'] == 0].sample(n=half_size)
        class_1 = df[df['final_label'] == 1].sample(n=half_size)
        debate_df = pd.concat([class_0, class_1])
        strategy_suffix = "_balanced"
    
    elif sample_strategy == "specific":
        if not specific_indices:
            raise ValueError("specific_indices must be provided when using 'specific' strategy")
        debate_df = df.iloc[specific_indices].reset_index(drop=True)
        strategy_suffix = "_specific"
    
    elif sample_strategy == "random":
        if not sample_size:
            raise ValueError("sample_size must be provided when using 'random' strategy")
        debate_df = df.sample(n=sample_size)
        strategy_suffix = "_random"
    
    else:
        raise ValueError(f"Unknown sample strategy: {sample_strategy}")

    print(f"🔍 Analyzing {len(debate_df)} speeches using {sample_strategy} strategy")
    return debate_df, prompt_config, strategy_suffix, prompt_type

@app.function(
    image=download_image,
    timeout=60 * 60,
    volumes={
        results_dir: results,
        ollama_dir: model_cache
        },
    )
def run_all_evaluations():
    import pandas as pd
    # from key import hf_token
    from llm_test import LLM_TEST

    # df = pd.read_csv("sample_data_english.csv")
    # df_nl = pd.read_csv("sample_data_dutch.csv")
    # # Sample indices from one of the dataframes
    # sampled_indices = df.sample(n=20, random_state=42).index

    # # Use the same indices to sample both dataframes
    # sampled_en = df.loc[sampled_indices]
    # sampled_nl = df_nl.loc[sampled_indices]
    df, prompt_config, strategy_suffix, prompt_type = prep_data(prompt_type="ccot_nl", sample_strategy="balanced", sample_size=2)#48)#specific_indices=[71, 72, prep_data(prompt_type="ccot_nl", sample_strategy="random", sample_size=200)#specific_indices=[71, 72, 73, 773, 74, 75])

    def extract_predicted_label(result):
        json
        try:
            # If result is a string, try to load it
            if isinstance(result, str):
                result = json.loads(result)

            count = result.get("summary", {}).get("count", 0)

            return "Ad Hominem" if count > 0 else "No Ad Hominem"
        except Exception as e:
            # Optional: print(e) for debugging
            return "Unknown"
    print("len of df to compute: ", len(df))
    # Initialise the test, this is for datasharing between methods and is purly cosmetic ;)     
    llm_test = LLM_TEST( 
        prompt=prompt_config['prompt'], 
        df=df, 
        system_prompt="Je bent een neutrale, getrainde expert in politieke discoursanalyse en drogredendetectie. Je eerste taak is het identificeren van ad-hominem aanvallen, met behulp van expert-niveau redenering en transparantie.",#"You are an expert in analyzing political texts. Analyze the text below for ad-hominem attacks.",
        text_key="speech_text",
        truth_lable_name="final_label",
        parse_function=extract_predicted_label, 
        model="Mungert/gemma-3-27b-it-GGUF",#"mistral-small3.1", 
        ollama=False,
        hf_token="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",
        quant="Q4_K_M",
        dataset_nick_name=f"tweede_kamer_debate",
        
        prompt_nick_name="ccot_nl", 
        # howmany rows are being feed into the llm at once
        row_count=1,
        # How many element should be in a batch
        batch_size=10,
        # In how many threads/container the program should run
        multithreads=2,
        dir_path="/root/results",
        timeout=4*60
    )
    # test execution
    run_pipeline(llm_test)

@app.local_entrypoint()
def main():
    print("📤 Submitting cloud job...")
    run_all_evaluations.remote()

    print("✅ Job submitted! You can now close your laptop.")
