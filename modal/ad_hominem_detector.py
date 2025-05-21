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
        "fpdf2", "ollama", "langdetect", "pytest", "jinja2",  "beautifulsoup4", "lxml")
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
    .env({"LD_LIBRARY_PATH":"/app/:$LD_LIBRARY_PATH"},)
    # Add files
    .add_local_file("sample_data_english.csv", remote_path="/root/sample_data_english.csv")
    .add_local_file("sample_data_dutch.csv", remote_path="/root/sample_data_dutch.csv")
    .add_local_file("merged_annotations.csv", remote_path="/root/merged_annotations.csv")
    .add_local_file("ollama.service", remote_path= "/etc/systemd/system/ollama.service")
    .add_local_python_source("hardware")
    .add_local_python_source("typst_report")
    .add_local_python_source("progress_bar")
    .add_local_python_source("llm_test")
    .add_local_python_source("woke_llama")
    .add_local_python_source("prompt_en_zeroshot_without_extras")
    .add_local_python_source("prompt_nl_zeroshot_without_extras")
    .add_local_python_source("prompt_en_fewshot_without_extras")
    .add_local_python_source("prompt_nl_fewshot_without_extras")
    .add_local_python_source("prompt_en_CCoT_without_extras")
    .add_local_python_source("prompt_en_CCoT_without_extras")
    .add_local_python_source("prompt_en_fewshot")
    .add_local_python_source("prompt_en_CCoT")
    .add_local_python_source("prompt_nl_zeroshot")
    .add_local_python_source("prompt_en_zeroshot")
    .add_local_python_source("prompt_nl_fewshot")
    .add_local_python_source("prompt_nl_CCoT")
    .add_local_python_source("prompt")
)

BATCH_SIZE = 0
TIMEOUT = 0

# -------------------- DOWNLOAD MODEL -------------------- #
@app.function(
    image=download_image, volumes={ollama_dir: model_cache}, timeout=60 * 10,
)
def download_model(llm_test):
    from huggingface_hub import hf_hub_download, list_repo_files
    import os
    import shutil
    # Inputs
    repo_id = llm_test.model
    quantization = llm_test.quant

    # Step 1: Find matching GGUF file
    files = list_repo_files(repo_id)
    gguf_file = next(
        (f for f in files if f.endswith(".gguf") and quantization in f),
        None
    )
    

    if gguf_file is None:
        raise ValueError(f"No GGUF file with quantization '{quantization}' found in {repo_id}")
    print(f"GGUF file with quantization '{quantization}' found in {repo_id}")
    # Step 2: Download the model to your custom path
    model_path = hf_hub_download(
        repo_id=repo_id,
        filename=gguf_file,
    )
    
    dir_name = repo_id.split("/")[0]
    path = f"{ollama_dir}/{dir_name}/{gguf_file}"
    if not os.path.exists(path):
        # Copy/rename to desired path
        os.makedirs(f"{ollama_dir}/{dir_name}")
        shutil.copy(model_path, path)
        print("Saved as: ", path)
    return path

@app.function(
    image=download_image,
    timeout=10*60*10,
    volumes={
        results_dir: results,
        ollama_dir: model_cache
        },
    gpu=GPU_CONFIG)
def llama_cpp_inference_batch(model_path,llm, list_msg, timeout, verbose=True, temperature=0):
    from woke_llama import Woke_LLama


    woke_llama = Woke_LLama(
        llama_cli_path="/app/llama-cli",
        gguf_path=model_path
    )

    responses = []
    for messages in list_msg:
        result = woke_llama.inference(messages=messages, timeout=timeout, verbose=verbose, temperature=0)
        result["index"] = messages[-1]["index"]
        result["is_timeout"] = result["status"] == -1
        result["raw"] = result
        responses.append(result)

    return responses

@app.function(
    image=download_image,
    timeout=4*60*10,
    volumes={
        results_dir: results,
        ollama_dir: model_cache
        },
    gpu="A100-80GB")
def large_llama_cpp_inference_batch(model_path,llm, list_msg, timeout, verbose=True, temperature=0):
    from woke_llama import Woke_LLama


    woke_llama = Woke_LLama(
        llama_cli_path="/app/llama-cli",
        gguf_path=model_path
    )

    responses = []
    for messages in list_msg:
        result = woke_llama.inference(messages=messages, timeout=timeout, verbose=verbose, temperature=0, ctx_size=128000)
        result["index"] = messages[-1]["index"]
        result["is_timeout"] = result["status"] == -1
        result["raw"] = result
        responses.append(result)

    return responses

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
    start_time = time.time()

    # Initialise llm
    gguf_path = download_model.remote(llm_test)
        

    def process_batch():
        while True:
            indices, available_df = llm_test.get_compute_batch()
            if len(indices) == 0:
                print("Terminating Runner ...")
                break
            else:
                print(f"Total elements to cumpute: {len(llm_test.get_df())} already computed elements: {len(llm_test.get_df())- len(available_df)} still to compute elements: {len(available_df)}")
            query = []
            for idx in indices:
                messages = []
                # Add system prompt
                if llm_test.system_prompt != None:
                    messages.append({'role': 'system', 'content': llm_test.system_prompt})
                df = llm_test.get_df()
                
                if idx - llm_test.row_count + 1 < 0:
                    start = 0
                else:
                    start = idx - llm_test.row_count + 1
                if idx == start:
                    rows = df.iloc[[idx]]
                else:  # as DataFrame
                    rows = df.iloc[start:idx]

                messages.extend([   
                    {'index': idx, 'role': 'user', 'content': llm_test.prompt.format(text=row)} 
                    for row in rows[llm_test.text_key]
                ])

                # Handle text's that have a very large size, eg. see notebook sampling. 
                # This way we could fit a harry potter book into the model as its hosted on a different gpu.
                if rows["text_length"].max() >= llm_test.max_text_length:
                    large_llama_cpp_inference_batch.remote(gguf_path,llm_test.model, [messages], llm_test.timeout, verbose=False)
                    llm_test.write_result(results)
                else:
                    query.append(messages)

            
            results = llama_cpp_inference_batch.remote(gguf_path,llm_test.model, query, llm_test.timeout, verbose=False)
            llm_test.write_result(results)
            llm_test.compute_forecast_report(start_time, GPU_INFO, GPU_CONFIG)  
    #Inference executionc
    with ThreadPoolExecutor(max_workers=llm_test.multithreads) as executor:
        futures = [executor.submit(process_batch) for _ in range(llm_test.multithreads)]

        for future in as_completed(futures):
            try:
                future.result()  # Wait for thread to complete
            except Exception as e:
                print(f"A thread failed with error: {e}")
            
    llm_test.generate_tk_report(start_time, GPU_INFO, GPU_CONFIG )#power_samples)
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

    # Add text length
    df['text_length'] = df['speech_text'].astype(str).apply(len)

    # Sample selection based on strategy
    if sample_strategy == "full":
        debate_df = df
        strategy_suffix = ""
    
    elif sample_strategy == "balanced":
        sample_size = sample_size or 10  # Default to 10 if not specified
        half_size = int(sample_size // 2)
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
    timeout=60 * 60*6,
    volumes={
        results_dir: results,
        ollama_dir: model_cache
        },
    )
def run_all_evaluations():
    import pandas as pd
    # from key import hf_token
    from llm_test import LLM_TEST

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
    # Initialise the test
    df, prompt_config, strategy_suffix, prompt_type = prep_data(prompt_type="fewshot_en", sample_strategy="full") 

    if prompt_config["language"] == "EN":
        sys_prompt = "You are an expert in analyzing political texts. Analyze the text below for ad-hominem attacks."
    else:
        sys_prompt = "Je bent een neutrale, getrainde expert in politieke discoursanalyse en drogredendetectie. Je eerste taak is het identificeren van ad-hominem aanvallen, met behulp van expert-niveau redenering en transparantie."
    
    llm_test = LLM_TEST( 
        prompt=prompt_config['prompt'], 
        df=df, 
        system_prompt= sys_prompt,
        text_key="speech_text",
        truth_lable_name="final_label",
        parse_function=extract_predicted_label, 
        model="unsloth/gemma-3-27b-it-GGUF",
        hf_token="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",
        quant="Q4_K_M",
        dataset_nick_name=f"tweede_kamer_debate",
        
        prompt_nick_name=prompt_config['name'], 
        # howmany rows are being feed into the llm at once
        row_count=1,
        # Text that are longer will be computed on bigger gpu
        max_text_length=6000,
        # How many element should be in a batch
        batch_size=10,
        # In how many threads/container the program should run
        multithreads=10,
        dir_path="/root/results",
        filename="21_may_final",
        timeout=4*60
    )
    run_pipeline(llm_test)
    # Money before run 4981.54$ -> 4980.84 in reality. Program thought 0.36
    # Second was 4978.73

    # Big run 4972.49$ 
    # Big run 2 4951.36
    # test execution
    

@app.local_entrypoint()
def main():
    print("📤 Submitting cloud job...")
    run_all_evaluations.remote()

    print("✅ Job submitted! You can now close your laptop.")
