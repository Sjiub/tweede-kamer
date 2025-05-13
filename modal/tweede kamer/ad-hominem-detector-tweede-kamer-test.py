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
from prompt_nl_zeroshot import prompt as PROMPT_ZEROSHOT_NL
from prompt_nl_fewshot import prompt as PROMPT_FEWSHOT_NL
from prompt_nl_CCoT import prompt as PROMPT_CCOT_NL

# Specify name of program
app = modal.App("ad-hominem-detector-tk")
GPU_CONFIG = "L4"
TIME_ZONE = "Europe/Amsterdam"

# Define prompt configurations
PROMPT_CONFIGS = {
    # English prompts
    "zeroshot_en": {
        "prompt": PROMPT_ZEROSHOT_EN,
        "name": "zeroshot",
        "description": "Zero-shot prompt without examples or reasoning steps",
        "language": "EN"
    },
    "fewshot_en": {
        "prompt": PROMPT_FEWSHOT_EN,
        "name": "fewshot",
        "description": "Few-shot prompt with examples",
        "language": "EN"
    },
    "ccot_en": {
        "prompt": PROMPT_CCOT_EN,
        "name": "ccot",
        "description": "Chain-of-thought prompt with reasoning steps",
        "language": "EN"
    },
    # Dutch prompts
    "zeroshot_nl": {
        "prompt": PROMPT_ZEROSHOT_NL,
        "name": "zeroshot",
        "description": "Zero-shot prompt without examples or reasoning steps (Dutch)",
        "language": "NL"
    },
    "fewshot_nl": {
        "prompt": PROMPT_FEWSHOT_NL,
        "name": "fewshot",
        "description": "Few-shot prompt with examples (Dutch)",
        "language": "NL"
    },
    "ccot_nl": {
        "prompt": PROMPT_CCOT_NL,
        "name": "ccot",
        "description": "Chain-of-thought prompt with reasoning steps (Dutch)",
        "language": "NL"
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
    .add_local_python_source("prompt_nl_zeroshot")
    .add_local_python_source("prompt_nl_fewshot")
    .add_local_python_source("prompt_nl_CCoT")
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

def ollama_inference(model, msg, timeout_seconds=240):
    import ollama
    import os
    import signal
    import time
    import json
    from contextlib import contextmanager
    
    class TimeoutException(Exception):
        pass
    
    @contextmanager
    def time_limit(seconds):
        def signal_handler(signum, frame):
            raise TimeoutException("Inference timed out")
        
        signal.signal(signal.SIGALRM, signal_handler)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)
    
    try:
        partial_output = ""
        
        with time_limit(timeout_seconds):
            # Use stream=True without a custom handler
            response_stream = ollama.chat(
                model=model,
                messages=[
                    {'role': 'user', 'content': msg}
                ],
                options={
                    "temperature": 0.0
                },
                stream=True  # Enable streaming
            )
            
            # Process the stream manually
            for chunk in response_stream:
                if 'message' in chunk and 'content' in chunk['message']:
                    partial_output += chunk['message']['content']
            
            # For successful completion, return the full response
            return partial_output
            
    except TimeoutException:
        # Return the timeout info with the partial output (truncate if needed)
        max_chars = 500  # Limit to 500 characters
        truncated_output = partial_output[:max_chars]
        if len(partial_output) > max_chars:
            truncated_output += "... [truncated]"
        
        return json.dumps({
            "status": "timeout",
            "raw_result": {
                "timeout_error": f"Inference timed out after {timeout_seconds} seconds",
                "is_timeout": True,
                "partial_output": truncated_output
            }
        })
    except Exception as e:
        # Handle other exceptions
        return json.dumps({
            "status": "error",
            "raw_result": {
                "error": str(e),
                "is_error": True
            }
        })

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
    
    timeout_seconds = 240  # 4 minutes timeout per inference

    # Initialise llm
    if ollama:
        # starts the ollama 
        download_ollama_model(repo_id)
    else:
        gguf_path = download_model.remote(repo_id, quant=quant, hf_token=hf_token)
        llm = Llama(model_path=gguf_path, n_gpu_layers=-1, n_ctx=4096, verbose=DEBUG)

    inference = []
    for idx, row in enumerate(query):
        storming_progress_bar(idx, len(query), start_time, update_message=f'Row: {idx}')
        _prompt = prompt
        full_prompt = _prompt.format(text=row)
        
        if ollama:
            result = ollama_inference(repo_id, full_prompt, timeout_seconds)
        else:
            # For llama.cpp we would need a different timeout approach
            result = llama_cpp_inference(llm, gguf_path, full_prompt)

        energy = 0
        is_timeout = False
        
        try:
            parsed = clean_result(result)
            # Check if this is a timeout result
            if isinstance(parsed, dict) and parsed.get("status") == "timeout":
                is_timeout = True
                print(f"⏱️ Timeout detected for row {idx}")
        except Exception as e:
            print(f"❌ Error parsing result at row {idx}: {e}")
            print("result: ", result)
            parsed = {
                "status": "error",
                "raw_result": {
                    "parsing_error": str(e),
                    "is_error": True
                }
            }

        inference.append({
            "result": parsed if not isinstance(parsed, str) else result,
            "energy_by_token": energy,
            "index": idx,
            "is_timeout": is_timeout
        })

    # Print metrics
    duration = time.time() - start_time
    avg_power = sum(power_samples) / len(power_samples) if power_samples else 0
    energy_measured = avg_power * duration

    df = pd.DataFrame(inference)
    cost = duration * GPU_INFO[GPU_CONFIG]["price_per_sec"]
    energy_by_token = df["energy_by_token"].sum()
    print(f"\n⏱️ Duration: {duration:.2f} for {len(query)} queries. Average computation time: {duration/len(query)}")
    print(f"⚡ Estimated power (by nvidia-smi): {energy_measured:.4f} W")
    print(f"🔋 Estimated power (by tokenizer): {energy_by_token:.4f} W")
    print(f"🤑 Cost: {cost:.2f} 💰")
    
    # Count timeouts
    timeout_count = df["is_timeout"].sum() if "is_timeout" in df.columns else 0
    if timeout_count > 0:
        print(f"⚠️ {timeout_count} queries timed out")

    return inference, energy_measured, duration, cost, power_samples
    
def generate_tk_report(results_df, prompt, dataset_language, prompt_language, dataset_nick_name, prompt_nick_name, model, quant, energy_measured, duration, cost, power_samples, graph_paths, metrics=None):
    from typst_report import TypstReport, get_prompt_hash
    from datetime import datetime
    from zoneinfo import ZoneInfo
    import os
    
    report = TypstReport()
    prompt_hash = str(get_prompt_hash(prompt))
    now = datetime.now(ZoneInfo(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")
    
    # Count timeouts
    timeout_count = results_df["is_timeout"].sum() if "is_timeout" in results_df.columns else 0
    
    # Calculate total ad hominem attacks (excluding timeouts)
    non_timeout_df = results_df[results_df["is_timeout"] != 1]
    total_attacks = sum(1 for _, row in non_timeout_df.iterrows() if row.get('found_fallacy', 0) == 1)
    attack_percentage = (total_attacks / len(non_timeout_df) * 100) if len(non_timeout_df) > 0 else 0
    
    # Only calculate metrics if they weren't provided and the dataframe has the necessary columns
    if metrics is None and 'final_label' in results_df.columns:
        from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
        
        # Extract predictions from the results (excluding timeouts)
        predictions = []
        true_labels = []
        for idx, row in results_df.iterrows():
            # Skip timeout cases
            if row.get('is_timeout', 1) == 1:
                continue
                
            try:
                result = clean_result(row['result']) if isinstance(row['result'], str) else row['result']
                if isinstance(result, dict) and 'found_fallacy' in result:
                    predictions.append(1 if result['found_fallacy'] else 0)
                    true_labels.append(row["final_label"])
                else:
                    predictions.append(0)
                    true_labels.append(row["final_label"])
            except:
                predictions.append(0)
                true_labels.append(row["final_label"])
        
        # Calculate metrics
        if predictions:
            metrics = {
                'accuracy': accuracy_score(true_labels, predictions),
                'precision': precision_score(true_labels, predictions, zero_division=0),
                'recall': recall_score(true_labels, predictions, zero_division=0),
                'f1': f1_score(true_labels, predictions, zero_division=0)
            }
        else:
            metrics = {'accuracy': 0, 'precision': 0, 'recall': 0, 'f1': 0}
    
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
        ("Ad Hominem Attacks", f"{total_attacks} ({attack_percentage:.1f}%)"),
        ("GPU Type", GPU_CONFIG),
        ("n tests", len(results_df)),
        ("Timeouts", timeout_count),
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

    # Process each speech for the report with special handling for timeouts
    for _, speech in results_df.iterrows():
        result_to_display = None
        
        # Handle timeout cases
        if speech.get('is_timeout', 0) == 1:
            result_to_display = {
                "status": "timeout",
                "raw_result": {
                    "timeout_error": "Inference timed out",
                    "is_timeout": True
                }
            }
        else:
            # For non-timeout cases, try to clean the result
            try:
                result_to_display = clean_result(speech["result"]) if isinstance(speech["result"], str) else speech["result"]
            except Exception:
                result_to_display = {
                    "status": "error",
                    "raw_result": {
                        "parsing_error": "Unable to parse JSON output",
                        "raw_output": str(speech["result"])[:500] + "..." if len(str(speech["result"])) > 500 else str(speech["result"])
                    }
                }
        
        report.add_test({
            "Speech": speech["speech_text"],
            "Speaker": speech["speaker_name"],
            "Party": speech["speaker_party"],
            "Result": result_to_display
        })

    path = f"report_tk_debate_{dataset_language}_{model}_{prompt_nick_name}_{prompt_language}_{now}".replace("/","_")
    out_path = os.path.join(results_dir, path)
    report.save(f"{out_path}.typ", f"{out_path}.pdf")

def handle_timeout_row(results_df, idx):
    """Handle timeout cases by setting default values"""
    results_df.at[idx, 'is_timeout'] = 1
    
    # Extract partial output if available and truncate it
    timeout_result = results_df.at[idx, 'result']
    partial_output = ""
    max_chars = 500  # Limit to 500 characters
    
    # Handle different formats of timeout results
    if isinstance(timeout_result, dict):
        if 'raw_result' in timeout_result:
            full_output = timeout_result['raw_result'].get('partial_output', '')
            partial_output = full_output[:max_chars]
        elif 'partial_output' in timeout_result:
            full_output = timeout_result.get('partial_output', '')
            partial_output = full_output[:max_chars]
    elif isinstance(timeout_result, str):
        partial_output = timeout_result[:max_chars]
    
    if len(partial_output) > max_chars:
        partial_output += "... [truncated]"
    
    # Save partial output to a new column
    results_df.at[idx, 'partial_output'] = partial_output
    
    # Set numeric fields to -1 for timeouts
    numeric_fields = ['found_fallacy', 'count', 'average_confidence', 'highest_confidence', 
                     'lowest_confidence', 'speech_relation_confidence']
    text_fields = ['mention_names', 'mention_types', 'mention_quotes', 'mention_categories',
                   'fallacy_quote', 'fallacy_explanation', 'fallacy_local_topic', 'fallacy_target',
                   'fallacy_explicitness', 'fallacy_confidence', 'speech_relation_type',
                   'speech_relation_justification']
    
    for field in numeric_fields:
        results_df.at[idx, field] = -1
    for field in text_fields:
        results_df.at[idx, field] = "[TIMEOUT]"
        
def process_result_row(results_df, idx, cleaned_result):
    """Process a single result row and update the DataFrame"""
    results_df.at[idx, 'is_timeout'] = 0
    
    if not isinstance(cleaned_result, dict):
        return

    # Process mentions
    if mentions := cleaned_result.get('mentions', []):
        for field_base, field_df in [('name', 'mention_names'), ('type', 'mention_types'), 
                                  ('quote', 'mention_quotes'), ('mention_category', 'mention_categories')]:
            values = [mention.get(field_base, '') for mention in mentions]
            results_df.at[idx, field_df] = '|||'.join(values)

    # Process summary statistics
    if summary := cleaned_result.get('summary', {}):
        for field in ['count', 'average_confidence', 'highest_confidence', 'lowest_confidence']:
            results_df.at[idx, field] = summary.get(field, 0)

    # Process fallacies
    if fallacies := cleaned_result.get('found_fallacy', []):
        results_df.at[idx, 'found_fallacy'] = 1
        for field_base, field_df in [('quote', 'fallacy_quote'), ('explanation', 'fallacy_explanation'), 
                                   ('local_topic', 'fallacy_local_topic'), ('target', 'fallacy_target'),
                                   ('explicitness', 'fallacy_explicitness'), ('confidence', 'fallacy_confidence')]:
            values = [str(fallacy.get(field_base, '')) for fallacy in fallacies]
            results_df.at[idx, field_df] = '|||'.join(values)

    # Process speech relation
    if speech_relation := cleaned_result.get('speech_relation', {}):
        results_df.at[idx, 'speech_relation_type'] = speech_relation.get('type', '')
        results_df.at[idx, 'speech_relation_justification'] = speech_relation.get('justification', '')
        results_df.at[idx, 'speech_relation_confidence'] = speech_relation.get('confidence', 0.0)

def init_result_columns(results_df):
    """Initialize result columns with default values"""
    result_columns = {
        'found_fallacy': 0, 'count': 0, 'is_timeout': 0,
        'average_confidence': 0.0, 'highest_confidence': 0.0, 'lowest_confidence': 0.0,
        'mention_names': '', 'mention_types': '', 'mention_quotes': '', 'mention_categories': '',
        'fallacy_quote': '', 'fallacy_explanation': '', 'fallacy_local_topic': '',
        'fallacy_target': '', 'fallacy_explicitness': '', 'fallacy_confidence': '',
        'speech_relation_type': '', 'speech_relation_justification': '', 'speech_relation_confidence': 0.0,
        'partial_output': '' 
    }
    
    for col, default_val in result_columns.items():
        results_df[col] = default_val

def calculate_metrics(predictions, true_labels, timeout_count, total_samples):
    """Calculate performance metrics"""
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
    
    if not predictions:
        return {
            'accuracy': 0, 'precision': 0, 'recall': 0, 'f1': 0,
            'timeout_count': timeout_count,
            'timeout_percentage': (timeout_count / total_samples * 100) if total_samples > 0 else 0
        }

    return {
        'accuracy': accuracy_score(true_labels, predictions),
        'precision': precision_score(true_labels, predictions, zero_division=0),
        'recall': recall_score(true_labels, predictions, zero_division=0),
        'f1': f1_score(true_labels, predictions, zero_division=0),
        'timeout_count': timeout_count,
        'timeout_percentage': (timeout_count / total_samples * 100) if total_samples > 0 else 0
    }

def plot_confusion_matrix(true_labels, predictions, model_id, prompt_name):
    """Create and save confusion matrix visualization"""
    import matplotlib.pyplot as plt
    import seaborn as sns
    from sklearn.metrics import confusion_matrix
    import numpy as np
    
    plt.figure(figsize=(8, 6))
    
    if not predictions:
        cm = np.zeros((2, 2), dtype=int)
        title = f'Confusion Matrix - {model_id} (all samples timed out)'
    else:
        cm = confusion_matrix(true_labels, predictions)
        title = f'Confusion Matrix - {model_id} ({prompt_name}, excluding timeouts)'
        
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', 
               xticklabels=['No Fallacy', 'Fallacy'], 
               yticklabels=['No Fallacy', 'Fallacy'])
    plt.ylabel('True Label', fontsize=11, labelpad=10)
    plt.xlabel('Predicted Label', fontsize=11, labelpad=10)
    plt.title(title, pad=15)
    plt.tight_layout()
    
    confusion_matrix_path = os.path.join(results_dir, "confusion_matrix.png")
    plt.savefig(confusion_matrix_path)
    plt.close()
    
    return confusion_matrix_path

def save_results(results_df, file_prefix, model_name, prompt_name, strategy_suffix=""):
    """Save results to CSV"""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    
    now = datetime.now(ZoneInfo(TIME_ZONE)).strftime("%Y-%m-%d_%H-%M-%S")
    csv_path = f"{file_prefix}_{model_name}_{prompt_name}{strategy_suffix}_{now}.csv"
    csv_out_path = os.path.join(results_dir, csv_path)
    results_df.to_csv(csv_out_path, index=False, sep=';')
    print("📁 Results saved to:", csv_out_path)
    return csv_path

@app.function(
    image=download_image,
    timeout=60 * 60 * 10,
    volumes={results_dir: results, cache_dir: model_cache},
)
def run_analysis(prompt_type, sample_strategy="full", specific_indices=None, sample_size=None):
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
    from key import hf_token

    # Validate prompt type
    if prompt_type not in PROMPT_CONFIGS:
        raise ValueError(f"Unknown prompt type: {prompt_type}. Available types: {list(PROMPT_CONFIGS.keys())}")

    prompt_config = PROMPT_CONFIGS[prompt_type]
    print(f"Using {prompt_config['name']} prompt: {prompt_config['description']}")

    # Load dataset
    df = pd.read_csv("/root/merged_annotations.csv", sep=";")

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

    # Define models to test
    models = [
        ("mistral-small3.1", "Mistral"),
    ]

    for model_id, model_name in models:
        print(f"\n🔄 Processing with {model_name} ({model_id})")
        
        # Run analysis
        inference, energy_measured, duration, cost, power_samples = run_pipeline.remote(
            model_id,
            debate_df["speech_text"].tolist(),
            prompt_config['prompt'],
            ollama=True,
            dataset_language="NL", 
            prompt_language="EN", 
            dataset_nick_name=f"tk_debate_{model_name.lower()}_{prompt_type}{strategy_suffix}",
            prompt_nick_name=f"{prompt_config['name']}-prompt",
            hf_token=hf_token
        )

        # Process results
        results_df = pd.DataFrame(inference)
        
        # Add original data columns from debate_df
        for col in debate_df.columns:
            results_df[col] = debate_df[col].values

        # Initialize result columns
        init_result_columns(results_df)

        # Process results and calculate metrics
        predictions, true_labels = [], []
        timeout_count = 0

        for idx, row in results_df.iterrows():
            try:
                # Check for timeout using multiple methods
                is_timeout = False
                
                # Method 1: Check the is_timeout flag directly in the row
                if row.get('is_timeout', False):
                    is_timeout = True
                
                # Method 2: Check if result dictionary has status=timeout
                if isinstance(row['result'], dict) and row['result'].get('status') == 'timeout':
                    is_timeout = True
                
                # Method 3: Check if raw_result indicates timeout
                if isinstance(row['result'], dict) and isinstance(row['result'].get('raw_result'), dict):
                    if row['result']['raw_result'].get('is_timeout', False):
                        is_timeout = True
                
                # Handle timeout case
                if is_timeout:
                    handle_timeout_row(results_df, idx)
                    timeout_count += 1
                    continue

                # Process normal (non-timeout) case
                cleaned_result = clean_result(row['result']) if isinstance(row['result'], str) else row['result']
                process_result_row(results_df, idx, cleaned_result)
                
                # Collect prediction data (excluding timeouts)
                if isinstance(cleaned_result, dict):
                    predictions.append(1 if cleaned_result.get('found_fallacy') else 0)
                    true_labels.append(row["final_label"])

            except Exception as e:
                print(f"Error processing row {idx}: {e}")
                # Set as timeout/error as fallback
                handle_timeout_row(results_df, idx)
                timeout_count += 1


        # Calculate metrics
        metrics = calculate_metrics(predictions, true_labels, timeout_count, len(results_df))
        
        # Create confusion matrix visualization
        confusion_matrix_path = plot_confusion_matrix(
            true_labels, predictions, model_id, prompt_config["name"])

        # Save results to CSV
        csv_path = save_results(
            results_df, 
            "results_tk_debate_NL", 
            model_name, 
            prompt_config['name'],
            strategy_suffix
        )

        # Generate PDF report
        power_plot_path = plot_power_samples(power_samples)
        generate_tk_report(
            results_df,
            prompt_config['prompt'],
            "NL", "EN",
            f"tk_debate_{model_name.lower()}_{prompt_type}{strategy_suffix}",
            f"{prompt_config['name']}-prompt",
            model_id,
            "Q8_0",
            energy_measured,
            duration,
            cost,
            power_samples,
            [power_plot_path, confusion_matrix_path],
            metrics
        )

        # Print results
        print(f"\n✨ Results for {model_name}:")
        print(f"Accuracy: {metrics['accuracy']*100:.1f}%")
        print(f"Precision: {metrics['precision']*100:.1f}%")
        print(f"Recall: {metrics['recall']*100:.1f}%")
        print(f"F1 Score: {metrics['f1']*100:.1f}%")
        print(f"Timeouts: {metrics['timeout_count']} ({metrics['timeout_percentage']:.1f}%)")

@app.local_entrypoint()
def main():
    # Example usage:
    
    # Full dataset
    #run_analysis.remote(prompt_type="ccot", sample_strategy="full")
    
    # Balanced sample of 10
    #run_analysis.remote(prompt_type="ccot", sample_strategy="balanced", sample_size=10)
    
    # Specific rows
    run_analysis.remote(prompt_type="ccot", sample_strategy="specific", specific_indices=[71, 72, 73, 74, 75])
    
    # Random sample
    #run_analysis.remote(prompt_type="ccot", sample_strategy="random", sample_size=50)