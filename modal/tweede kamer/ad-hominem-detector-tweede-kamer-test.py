import modal
import os
import glob
import csv
import json
import pandas as pd
from pathlib import Path
from hardware import GPU_INFO
from prompt_en_zeroshot import prompt as PROMPT_ZEROSHOT_EN
from prompt_en_fewshot import prompt as PROMPT_FEWSHOT_EN
from prompt_en_CCoT import prompt as PROMPT_CCOT_EN

# Specify name of program
app = modal.App("ad-hominem-detector-tk")
GPU_CONFIG = "L4"
TIME_ZONE = "Europe/Amsterdam"

# Define prompt configurations
PROMPT_CONFIGS = {
    "zeroshot": {
        "prompt": PROMPT_ZEROSHOT_EN,
        "name": "zeroshot",
        "description": "Zero-shot prompt without examples or reasoning steps"
    },
    "fewshot": {
        "prompt": PROMPT_FEWSHOT_EN,
        "name": "fewshot",
        "description": "Few-shot prompt with examples"
    },
    "ccot": {
        "prompt": PROMPT_CCOT_EN,
        "name": "ccot",
        "description": "Chain-of-thought prompt with reasoning steps"
    }
}

# Initialize volumes
model_cache = modal.Volume.from_name("llamacpp-cache", create_if_missing=True)
cache_dir = "/root/.cache/llama.cpp"

results = modal.Volume.from_name("llamacpp-results", create_if_missing=True)
results_dir = "/root/results"

#Update relative path to CSV file
CURRENT_DIR = Path(__file__).parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
MERGED_ANNOTATIONS_PATH = str(PROJECT_ROOT / "data" / "labeled tweede kamer data" / "merged_annotations.csv")
FONTS_PATH = CURRENT_DIR / "DejaVuSans.ttf"
FONTS_BOLD_PATH = CURRENT_DIR / "DejaVuSans-Bold.ttf"
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
        "fpdf2", "ollama", "openpyxl")
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
    .add_local_file(str(MERGED_ANNOTATIONS_PATH), 
                   remote_path="/root/merged_annotations.csv")
    .add_local_file(str(FONTS_PATH), remote_path="/root/DejaVuSans.ttf")
    .add_local_file(str(FONTS_BOLD_PATH), remote_path="/root/DejaVuSans-Bold.ttf")
    .add_local_python_source("prompt_en_zeroshot")
    .add_local_python_source("prompt_en_fewshot")
    .add_local_python_source("prompt_en_CCoT")
    .add_local_python_source("hardware")
    .add_local_python_source("typst_report")
    .add_local_python_source("progress_bar")
    .add_local_python_source("key")
)


# -------------------- DOWNLOAD MODEL -------------------- #
cache_dir = "/root/.cache/llama.cpp"
@app.function(
    image=download_image, volumes={cache_dir: model_cache}, timeout=60 * 60 * 10,
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
        temperature=0.0,
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
        ],
        options={
            "temperature": 0.0  # Set temperature to 0
        }
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

def plot_power_samples(power_samples):
    import matplotlib.pyplot as plt
    import os
    
    # Create output path in results directory
    output_path = os.path.join(results_dir, "power_usage_plot.png")
    
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

def get_gpu_power():
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
    timeout=60 * 60 * 10,
    volumes={
        results_dir: results,
        cache_dir: model_cache,
        },
    gpu=GPU_CONFIG)
def run_pipeline(repo_id, query, prompt, quant="Q8_0", ollama=False, dataset_language=None, 
                prompt_language=None, dataset_nick_name=None, prompt_nick_name=None, hf_token=None, DEBUG=False):
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

@app.function(
    image=download_image,
    volumes={results_dir: results},
    timeout=60 * 60 * 10,
)
def detect_ad_hominem_tk(df, prompt, model, quant, ollama, dataset_language, prompt_language, dataset_nick_name, prompt_nick_name, hf_token):
    import pandas as pd
    from datetime import datetime
    from zoneinfo import ZoneInfo

    querys = df["speech_text"].to_list()
    
    inference, energy_measured, duration, cost, power_samples = run_pipeline.remote(
         model,
         querys,
         prompt,
         ollama=ollama,
         quant=quant,
         hf_token=hf_token
    )

    results_df = pd.DataFrame(inference)
    
    # Copy all original columns
    for col in df.columns:
        results_df[col] = df[col].values
    
    # Save complete results CSV
    now = datetime.now(ZoneInfo(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")
    path = f"report_tk_debate_{dataset_language}_{model}_{prompt_nick_name}_{prompt_language}_{now}".replace("/","_")
    out_path = os.path.join(results_dir, path)
    results_df.to_csv(out_path, index=False, sep=';')  # Using semicolon separator to match input format
    print("📁 Results saved to:", out_path)
    
    power_plot_path = plot_power_samples(power_samples)
    
    now = datetime.now(ZoneInfo(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")
    
    # Calculate metrics if the dataframe has the necessary columns
    metrics = None
    if 'final_label' in results_df.columns:
        from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
        
        # Extract predictions from the results
        predictions = []
        for idx, row in results_df.iterrows():
            try:
                result = clean_result(row['result'])
                if isinstance(result, dict) and 'found_fallacy' in result:
                    predictions.append(1 if result['found_fallacy'] else 0)
                else:
                    predictions.append(0)
            except:
                predictions.append(0)
                
        # Get true labels
        true_labels = results_df["final_label"].tolist()
        
        # Calculate metrics
        metrics = {
            'accuracy': accuracy_score(true_labels, predictions),
            'precision': precision_score(true_labels, predictions, zero_division=0),
            'recall': recall_score(true_labels, predictions, zero_division=0),
            'f1': f1_score(true_labels, predictions, zero_division=0)
        }
    
    # Generate report
    generate_tk_report(
        results_df,
        prompt,
        dataset_language,
        prompt_language,
        dataset_nick_name,
        prompt_nick_name,
        model,
        quant,
        energy_measured,
        duration,
        cost,
        power_samples,
        [power_plot_path],
        metrics  # Pass the metrics
    )
    
def generate_tk_report(results_df, prompt, dataset_language, prompt_language, dataset_nick_name, prompt_nick_name, model, quant, energy_measured, duration, cost, power_samples, graph_paths, metrics=None):
    from typst_report import TypstReport, get_prompt_hash
    from datetime import datetime
    from zoneinfo import ZoneInfo
    import os
    
    report = TypstReport()
    prompt_hash = str(get_prompt_hash(prompt))
    now = datetime.now(ZoneInfo(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")
    
    # Only calculate metrics if they weren't provided and the dataframe has the necessary columns
    if metrics is None and 'final_label' in results_df.columns:
        from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
        
        # Extract predictions from the results
        predictions = []
        for _, row in results_df.iterrows():
            try:
                result = clean_result(row['result'])
                if isinstance(result, dict) and 'found_fallacy' in result:
                    predictions.append(1 if result['found_fallacy'] else 0)
                else:
                    predictions.append(0)
            except:
                predictions.append(0)
                
        # Get true labels
        true_labels = results_df["final_label"].tolist()
        
        # Calculate metrics
        metrics = {
            'accuracy': accuracy_score(true_labels, predictions),
            'precision': precision_score(true_labels, predictions, zero_division=0),
            'recall': recall_score(true_labels, predictions, zero_division=0),
            'f1': f1_score(true_labels, predictions, zero_division=0)
        }
    
    info = [
        ("Model", model),
        ("Quantisation", quant),
        ("Prompt Version", f'{prompt_nick_name}_{prompt_language}_{prompt_hash}'),
        ("Dataset", "Tweede Kamer Debate"),
        ("Date & Time", now),
        ("Number of Speeches", len(results_df)),
        ("Duration (s)", f"{duration:.2f}"),
        (r"Cost (\$)", f"{cost:.2f}"),
        ("Electricity Usage (W)", f"{energy_measured:.2f}"),
        ("Unparsed", 0),  # Added unparsed count
        ("n tests", len(results_df))  # Added total tests
    ]
    
    # Add metrics if available
    if metrics:
        info.extend([
            ("Accuracy", f"{metrics['accuracy']*100:.1f}%"),
            ("Precision", f"{metrics['precision']*100:.1f}%"),
            ("Recall", f"{metrics['recall']*100:.1f}%"),
            ("F1 Score", f"{metrics['f1']*100:.1f}%")
        ])
    
    # Convert graph paths to relative paths
    relative_graph_paths = [os.path.basename(path) for path in graph_paths if path]
    report.add_general_info(info, relative_graph_paths)

    results_df["cleaned_output"] = results_df["result"].apply(clean_result)
    for _, speech in results_df.iterrows():
        report.add_test({
            "Speech": speech["speech_text"],
            "Speaker": speech["speaker_name"],
            "Party": speech["speaker_party"],
            "Result": speech["cleaned_output"]
        })

    path = f"report_tk_debate_{dataset_language}_{model}_{prompt_nick_name}_{prompt_language}_{now}".replace("/","_")
    out_path = os.path.join(results_dir, path)
    report.save(f"{out_path}.typ", f"{out_path}.pdf")

@app.function(
    image=download_image,
    timeout=60 * 60 * 10,
    volumes={results_dir: results, cache_dir: model_cache},
)
def run_tweede_kamer_analysis(test_run, prompt_type): 
    import pandas as pd  # Move imports to start of function
    from key import hf_token
    from sklearn.metrics import confusion_matrix, accuracy_score, precision_score, recall_score, f1_score
    import seaborn as sns
    import matplotlib.pyplot as plt
    from datetime import datetime  
    from zoneinfo import ZoneInfo  

    if prompt_type not in PROMPT_CONFIGS:
        raise ValueError(f"Unknown prompt type: {prompt_type}. Available types: {list(PROMPT_CONFIGS.keys())}")

    prompt_config = PROMPT_CONFIGS[prompt_type]
    print(f"Using {prompt_config['name']} prompt: {prompt_config['description']}")

    # Load merged annotations dataset
    df = pd.read_csv("/root/merged_annotations.csv", sep=";")
    
    # Configure test or full run
    if test_run:
        # Get a balanced sample with both classes
        class_0 = df[df['final_label'] == 0].head(5)
        class_1 = df[df['final_label'] == 1].head(5)
        debate_df = pd.concat([class_0, class_1])
        dataset_suffix = "_test"
        print(f"🧪 TEST RUN: Analyzing {len(debate_df)} balanced speeches (5 per class)")
    else:
        debate_df = df
        dataset_suffix = ""
        print("📊 FULL RUN: Analyzing all speeches")

    # Define models to test
    models = [
        #("deepseek-r1:8b", "DeepSeek"),
        #("gemma3:27b", "Gemma"),
        ("mistral-small3.1", "Mistral"),
    ]

    for model_id, model_name in models:
        print(f"\n🔄 Processing with {model_name} ({model_id})")
        
        # Run analysis using Dutch text
        inference, energy_measured, duration, cost, power_samples = run_pipeline.remote(
            model_id,
            debate_df["speech_text"].tolist(),
            prompt_config['prompt'],  # Use the prompt from config
            ollama=True,
            dataset_language="NL", 
            prompt_language="EN", 
            dataset_nick_name=f"tweede_kamer_debate_{model_name.lower()}_{prompt_type}{dataset_suffix}",
            prompt_nick_name=f"{prompt_config['name']}-prompt",
            hf_token=hf_token
        )

        # Process results
        results_df = pd.DataFrame(inference)
        
        # Add original data columns to results
        for col in debate_df.columns:
            results_df[col] = debate_df[col].values
            
        # Add new columns with default values
        # Fallacy detection and summary
        results_df['found_fallacy'] = 0
        results_df['count'] = 0
        results_df['average_confidence'] = 0.0
        results_df['highest_confidence'] = 0.0
        results_df['lowest_confidence'] = 0.0
        
        # Mentions-related columns (will store multiple values separated by '|||')
        results_df['mention_names'] = ''
        results_df['mention_types'] = ''
        results_df['mention_quotes'] = ''
        results_df['mention_categories'] = ''
        
        # Fallacy details
        results_df['fallacy_quote'] = ''
        results_df['fallacy_explanation'] = ''
        results_df['fallacy_local_topic'] = ''
        results_df['fallacy_target'] = ''
        results_df['fallacy_explicitness'] = ''
        results_df['fallacy_confidence'] = '' 
        
        # Speech relation
        results_df['speech_relation_type'] = ''
        results_df['speech_relation_justification'] = ''
        results_df['speech_relation_confidence'] = 0.0
        
        # Process each result and fill in the new columns
        for idx, row in results_df.iterrows():
            try:
                cleaned_result = clean_result(row['result'])
                if isinstance(cleaned_result, dict):
                    # Process mentions (handling multiple entries)
                    mentions = cleaned_result.get('mentions', [])
                    if mentions:
                        names = []
                        types = []
                        quotes = []
                        categories = []
                        
                        for mention in mentions:
                            names.append(mention.get('name', ''))
                            types.append(mention.get('type', ''))
                            quotes.append(mention.get('quote', ''))
                            categories.append(mention.get('mention_category', ''))
                        
                        # Join with delimiter
                        results_df.at[idx, 'mention_names'] = '|||'.join(names)
                        results_df.at[idx, 'mention_types'] = '|||'.join(types)
                        results_df.at[idx, 'mention_quotes'] = '|||'.join(quotes)
                        results_df.at[idx, 'mention_categories'] = '|||'.join(categories)
                    
                    # Summary statistics
                    summary = cleaned_result.get('summary', {})
                    results_df.at[idx, 'count'] = summary.get('count', 0)
                    results_df.at[idx, 'average_confidence'] = summary.get('average_confidence', 0.0)
                    results_df.at[idx, 'highest_confidence'] = summary.get('highest_confidence', 0.0)
                    results_df.at[idx, 'lowest_confidence'] = summary.get('lowest_confidence', 0.0)

                    # Found fallacy details
                    fallacies = cleaned_result.get('found_fallacy', [])
                    if fallacies:
                        results_df.at[idx, 'found_fallacy'] = 1
                        
                        # Store all fallacies using delimiters
                        quotes = []
                        explanations = []
                        topics = []
                        targets = []
                        explicitness = []
                        confidences = []
                        
                        for fallacy in fallacies:
                            quotes.append(fallacy.get('quote', ''))
                            explanations.append(fallacy.get('explanation', ''))
                            topics.append(fallacy.get('local_topic', ''))
                            targets.append(fallacy.get('target', ''))
                            explicitness.append(fallacy.get('explicitness', ''))
                            confidences.append(str(fallacy.get('confidence', 0)))
                        
                        # Join with delimiter
                        results_df.at[idx, 'fallacy_quote'] = '|||'.join(quotes)
                        results_df.at[idx, 'fallacy_explanation'] = '|||'.join(explanations)
                        results_df.at[idx, 'fallacy_local_topic'] = '|||'.join(topics)
                        results_df.at[idx, 'fallacy_target'] = '|||'.join(targets)
                        results_df.at[idx, 'fallacy_explicitness'] = '|||'.join(explicitness)
                        results_df.at[idx, 'fallacy_confidence'] = '|||'.join(confidences)

                    # Speech relation
                    speech_relation = cleaned_result.get('speech_relation', {})
                    results_df.at[idx, 'speech_relation_type'] = speech_relation.get('type', '')
                    results_df.at[idx, 'speech_relation_justification'] = speech_relation.get('justification', '')
                    results_df.at[idx, 'speech_relation_confidence'] = speech_relation.get('confidence', 0.0)
            except Exception as e:
                print(f"Error processing row {idx}: {e}")
                continue
        
        # Save results CSV
        prompt_language = "EN"
        now = datetime.now(ZoneInfo(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")
        csv_path = f"results_tk_debate_NL_{model_name}_{prompt_type}_{prompt_language}_{now}.csv".replace("/","_")
        csv_out_path = os.path.join(results_dir, csv_path)
        results_df.to_csv(csv_out_path, index=False, sep=';')
        print("📁 Results saved to:", csv_out_path)
        
        # Extract predictions
        predictions = []
        for idx, row in results_df.iterrows():
            try:
                result = clean_result(row['result'])
                if isinstance(result, dict) and 'found_fallacy' in result:
                    predictions.append(1 if result['found_fallacy'] else 0)
                else:
                    predictions.append(0)
            except:
                predictions.append(0)

        # Get true labels
        true_labels = debate_df["final_label"].tolist()

        # Calculate metrics
        accuracy = accuracy_score(true_labels, predictions)
        precision = precision_score(true_labels, predictions, zero_division=0)
        recall = recall_score(true_labels, predictions, zero_division=0)
        f1 = f1_score(true_labels, predictions, zero_division=0)
        
        # Create and save confusion matrix
        cm = confusion_matrix(true_labels, predictions)
        plt.figure(figsize=(8, 6))
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', 
               xticklabels=['No Fallacy', 'Fallacy'], 
               yticklabels=['No Fallacy', 'Fallacy'])
        plt.ylabel('True Label', fontsize=11, labelpad=10)
        plt.xlabel('Predicted Label', fontsize=11, labelpad=10)
        plt.title(f'Confusion Matrix - {model_id}', pad=15)
        plt.tight_layout()
        confusion_matrix_path = os.path.join(results_dir, "confusion_matrix.png")
        plt.savefig(confusion_matrix_path)
        plt.close()
        
        metrics = {
            'accuracy': accuracy,
            'precision': precision,
            'recall': recall,
            'f1': f1
        }

        # Generate PDF report
        power_plot_path = plot_power_samples(power_samples)
        generate_tk_report(
            results_df,
            prompt_config['prompt'],
            "NL",
            "EN",
            f"tweede_kamer_debate_{model_name.lower()}_{prompt_type}{dataset_suffix}",
            f"{prompt_config['name']}-prompt",
            model_id,
            "Q8_0",
            energy_measured,
            duration,
            cost,
            power_samples,
            [power_plot_path, confusion_matrix_path],
            metrics  # Pass the metrics to avoid recalculation
        )

        # Print results
        print(f"📝 Report generated: {csv_path}")
        print(f"\n✨ Results for {model_name}:")
        print(f"Accuracy: {accuracy*100:.1f}%")
        print(f"Precision: {precision*100:.1f}%")
        print(f"Recall: {recall*100:.1f}%")
        print(f"F1 Score: {f1*100:.1f}%")
        print("Confusion Matrix:")
        print(cm)
        
@app.local_entrypoint()
def main():
    # All configuration in one place
    config = {
        "test_mode": True,  # Set to False for full run
        "prompt_types": ["zeroshot", "fewshot", "ccot"]  # List of prompts to run
    }
    
    for prompt_type in config["prompt_types"]:
        print(f"\n📤 Submitting Tweede Kamer analysis job using {prompt_type} prompt...")
        run_tweede_kamer_analysis.remote(
            test_run=config["test_mode"],
            prompt_type=prompt_type
        )
        print(f"✅ Job submitted for {prompt_type}")
    
    print("\n🎉 All jobs submitted! You can now close your laptop.")


# Run all prompts
#"prompt_types": ["zeroshot", "fewshot", "ccot"]

# Run only two prompts
#"prompt_types": ["zeroshot", "fewshot"]

# Run single prompt
#"prompt_types": ["ccot"]