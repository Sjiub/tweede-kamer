import pandas as pd


# Initialisation stage
import modal
from ad_hominem_detector import download_image

# Specify name of program
app = modal.App("ad-hominem-detector-Unit-test")
# Specify GPU Used
GPU_CONFIG = "L4"  # or "A10G", etc.
TIME_ZONE = "Europe/Amsterdam"

# Initialise volumes
model_cache = modal.Volume.from_name("ollama-models", create_if_missing=True)
ollama_dir = "/opt/ai/models"

results = modal.Volume.from_name("unittest-results", create_if_missing=True)
results_dir = "/root/results"



def find_llama_cli():
    import subprocess
    import os
    try:
        # Check if llama-cli is in PATH
        path = subprocess.check_output(['which', 'llama-cli'], stderr=subprocess.DEVNULL).decode().strip()
        if path:
            print(f"'llama-cli' found in PATH at: {path}")
            return path
    except subprocess.CalledProcessError:
        print("'llama-cli' not found in PATH. Searching the filesystem...")

    # Fallback: Search the file system for the executable
    search_root = '/'  # You can change this to '/home/youruser' to limit the scope
    for root, dirs, files in os.walk(search_root):
        if 'llama-cli' in files:
            full_path = os.path.join(root, 'llama-cli')
            print(f"'llama-cli' found at: {full_path}")
            version = subprocess.check_output([full_path, "--version"], stderr=subprocess.DEVNULL).decode().strip()
            print(f"version of llama-cli is: {version}")
            return full_path

    print("'llama-cli' not found anywhere on the system.")
    return None


# TODO verify that the test works correclty
def define_test():
    from llm_test import LLM_TEST
    from ad_hominem_detector import prep_data
    df, prompt_config, strategy_suffix, prompt_type = prep_data(prompt_type="ccot_nl", sample_strategy="balanced", sample_size=10)#48)#specific_indices=[71, 72, prep_data(prompt_type="ccot_nl", sample_strategy="random", sample_size=200)#specific_indices=[71, 72, 73, 773, 74, 75])
    def parse_function():
        pass
    llm_test =  LLM_TEST( 
        prompt=prompt_config['prompt'], 
        df=df, 
        system_prompt= "sys_prompt",
        text_key="speech_text",
        truth_lable_name="final_label",
        parse_function=parse_function, 
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
        multithreads=1,
        dir_path="/root/results",
        timeout=4*60
    )
    return llm_test


def check_types():
    assert isinstance(llm_test.df, pd.DataFrame), "df must be a pandas DataFrame"
    assert isinstance(llm_test.prompt, str) and llm_test.prompt != "", "prompt must be a non-empty string"
    assert isinstance(llm_test.model, str) and llm_test.model != "", "model must be a non-empty string"
    assert isinstance(llm_test.ollama, bool), "ollama must be a boolean"
    assert isinstance(llm_test.dataset_language, str), "dataset_language must be a string"
    assert isinstance(llm_test.prompt_language, str), "prompt_language must be a string"
    assert isinstance(llm_test.dataset_nick_name, str), "dataset_nick_name must be a string"
    assert isinstance(llm_test.prompt_nick_name, str), "prompt_nick_name must be a string"
    assert callable(llm_test.parse_function), "parse_function must be a callable (function)"

    # Conditional check: if not using ollama, hf_token must be present
    if not llm_test.ollama:
        assert isinstance(llm_test.hf_token, str) and llm_test.hf_token != "", \
            "hf_token must be a non-empty string if ollama is False"
        assert isinstance(llm_test.quant, str) and llm_test.quant != "", "quant must be a non-empty string"

    print("All type checks passed.")

# Verify that the test runtime works as expected
def check_write_block(llm_test):
    import time
    import threading
    import pandas as pd
    import fcntl
    import time
    import os
    llm_test.df_file_name = "test_file.csv"
    llm_test.df_lock_file = "test_file.lock"
    # Create the lock file if it doesn't exist
    if not os.path.exists(llm_test.df_lock_file):
        with open(llm_test.df_lock_file, "w") as f:
            f.write("")
    if not os.path.exists(llm_test.df_file_name):
        pd.DataFrame(columns=["data"]).to_csv(llm_test.df_file_name, index=False)

    def block_file(_):
        llm_test.df = pd.DataFrame(["tp 1"], columns=["data"])
        time.sleep(5)

    def write_block_file(_):
        llm_test.df.loc[len(llm_test.df)] = "tp 2"
        time.sleep(1)

    def refresh_df(_):
        df = pd.read_csv(llm_test.df_file_name)
        assert len(df) == 2, f"Error during writing to file: {df}"
        print("check write block ok")


    # Thread to run the concurrent writer
    writer_thread = threading.Thread(target=lambda: llm_test.write_df(write_block_file, None))

    # Start the blocking write
    blocking_thread = threading.Thread(target=lambda: llm_test.write_df(block_file, None))
    blocking_thread.start()

    # Wait a moment and then start the concurrent writer
    time.sleep(1)
    writer_thread.start()

    # Wait for both to finish
    blocking_thread.join()
    writer_thread.join()

    # Evaluate results
    llm_test.write_df(refresh_df, None)


def check_compute_sampling(llm_test):
    assert len(llm_test.get_df()) == 10
    # draw 5 times a batch of 2
    for i in range(5):
        indices, available_df = llm_test.get_compute_batch(2)
        # Check that indices are never none
        assert len(indices) != 0, f"In run nr: {i}, emty indices {indices}"

    # But now it has to be empty!
    val = llm_test.get_compute_batch(1)
    assert all(len(idx) == 0 for idx in val), f"Error indices should be empty but contains a value {val}"

    print("Check compute ok")
def timeout_check():
    pass
def check_text_length():
    from ad_hominem_detector import run_pipeline
    def fetch_complex_text(min_length=10000):
        import requests
        from bs4 import BeautifulSoup
        url = "https://en.wikisource.org/wiki/The_Origin_of_Species_(1872)"
        response = requests.get(url)
        soup = BeautifulSoup(response.text, "html.parser")

        # Extract paragraphs and join into a single text
        paragraphs = soup.find_all("p")
        full_text = "\n\n".join(p.get_text() for p in paragraphs)

        # Filter long enough and return
        if len(full_text) >= min_length:
            return full_text[:min_length + 1000]  # optionally clip to target + buffer
        else:
            raise ValueError("Fetched text is too short.")
    llm_test = define_test()
    llm_test.df = llm_test.df.head(1)
    llm_test.df[llm_test.text_key][0] = fetch_complex_text(10000) 
    run_pipeline(llm_test)
    assert llm_test.df["is_timeout"][0] == False, "Error long text didnt run"
    print("check long text ok")
def llm_outputs():
    # test if json format output is correct
    pass

def test_llm_finish_forcast():
    # Test if forcast of execution time is kind of reasonable
    pass

def sampling_strategy_for_computation():
    # The llm should take random index for computation.abs
    # test that every speech is only once computed
    pass

# Edge cases, Test instances that don't fit the norm and might cause a problem in the analyisis



# Check that the appropriate outputs are correctly generated


def test_confusion_matrix():
    pass
def test_report_generation():
    # Specify labled and unlabled report
    pass

@app.function(
    image=download_image,
    timeout=60 * 60,
    volumes={
        results_dir: results,
        ollama_dir: model_cache
        },
    )
def root_function():
    assert find_llama_cli() != None
    llm_test = define_test()
    check_compute_sampling(llm_test=llm_test)
    check_write_block(llm_test=llm_test)
    check_text_length()
