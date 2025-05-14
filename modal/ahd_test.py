from llm_test import LLM_TEST
import pandas as pd



# Initialise object

llm_test = LLM_TEST( 
    prompt="PROMPT_TEMPLATE_EN", 
    df=pd.DataFrame(), 
    system_prompt="You are an expert in analyzing political texts. Analyze the text below for ad-hominem attacks.",
    text_key="Speech",
    parse_function=(), 
    model="mistral-small3.1", 
    ollama=True,
    dataset_nick_name="US-Election", 
    prompt_nick_name="Prototype_prompt", 
    # howmany rows are being feed into the llm at once
    row_count=1,
    # Specify the range
    row_range=None,
    # In how many engines the program should run
    multithreads=1
    )


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

# LLM
def timeout_check():
    pass
def text_length():
    # Test extrem case for inputs
    pass
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

# Output generation




def test_confusion_matrix():
    pass
def test_report_generation():
    # Specify labled and unlabled report
    pass
