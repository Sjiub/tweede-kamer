from prompt_en_zeroshot import prompt as PROMPT_ZEROSHOT_EN
from prompt_en_fewshot import prompt as PROMPT_FEWSHOT_EN
from prompt_en_CCoT import prompt as PROMPT_CCOT_EN
from prompt_nl_zeroshot import prompt as PROMPT_ZEROSHOT_NL
from prompt_en_fewshot_without_extras import prompt as PROMPT_ZEROSHOT_WITHOUT_EXTRAS_EN
from prompt_nl_zeroshot_without_extras import prompt as PROMPT_ZEROSHOT_WITHOUT_EXTRAS_NL
from prompt_nl_fewshot import prompt as PROMPT_FEWSHOT_NL
from prompt_nl_CCoT import prompt as PROMPT_CCOT_NL
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
    "zeroshot_nl_without_extra": {
        "prompt": PROMPT_ZEROSHOT_WITHOUT_EXTRAS_NL,
        "name": "zeroshot",
        "description": "Zero-shot prompt without examples or reasoning steps (Dutch)",
        "language": "NL"
    },
    "zeroshot_en_without_extra": {
        "prompt": PROMPT_ZEROSHOT_WITHOUT_EXTRAS_EN,
        "name": "zeroshot",
        "description": "Zero-shot prompt without examples or reasoning steps (Dutch)",
        "language": "EN"
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
    },
}