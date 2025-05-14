import json
import pandas as pd
import subprocess
import shutil
import os

from promt_en import prompt as PROMPT_TEMPLATE_EN
from promt_nl import prompt as PROMPT_TEMPLATE_NL

def get_prompt_hash(prompt, length=8):
    import hashlib
    hash_object = hashlib.sha256(str(prompt).encode())
    return hash_object.hexdigest()[:length]

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
def escape_for_typst(text: str) -> str:
    """
    Escape special Typst characters so they display as raw text.
    """
    return (
        text.replace("\\", "\\\\")   # escape backslash first
            .replace("#", "\\#")     # Typst command indicator
            .replace("$", "\\$")     # Math mode
            .replace("{", "\\{")     # Group open
            .replace("}", "\\}")     # Group close
            .replace("[", "\\[")     # Bracket open
            .replace("]", "\\]")     # Bracket close
    )



class TypstReport:
    def __init__(self):
        if not shutil.which("typst"):
            raise EnvironmentError("Typst CLI is not installed or not in PATH.")
        # Install packages:
            
        self.content = """
            #import "@preview/codly:1.3.0": *
            #import "@preview/codly-languages:0.1.1": *
            #show: codly-init.with()

            #codly(languages: codly-languages)
            #set text(font: "DejaVu Sans Mono")
            """
        self.content += "= Test Report\n\n"

    def add_general_info(self, info, graph_paths):
        self.content += "== General Information\n\n"
        for label, value in info:
            self.content += f"*{label}:* {value}\\\n\n"
        for path in graph_paths:
            if path:
                self.content += f'#image("{path}")\n\n'

    def add_test(self, test_data, **kwargs):
        self.content += f"== Test {test_data.get('id', '-')}\n\n"

        if kwargs.get("show_speech", True):
            speech = escape_for_typst(str(test_data['Speech']))
            self.content += f"*Speech:* {speech}\n\n"

        if kwargs.get("show_true_label", True):
            self.content += f"*True Label:* {test_data['truth_label']}\n\n"

        if kwargs.get("show_predicted_label", True):
            self.content += f"*Predicted Label:* {test_data['predicted']}\n\n"
            true_label = str(test_data.get("truth_label", "")).strip().lower()
            predicted_label = str(test_data.get("predicted", "")).strip().lower()
            if predicted_label == true_label:
                result_type = "Correct"
            elif predicted_label == "true" and true_label == "false":
                result_type = "False Positive"
            elif predicted_label == "false" and true_label == "true":
                result_type = "False Negative"
            else:
                result_type = "Other"
            self.content += f"*Result:* {result_type}\n\n"

        if kwargs.get("show_clean_output", True):
            self.content += "*Cleaned Output:*\n\n```json\n"
            try:
                result = clean_result(test_data["result"]) if isinstance(test_data["result"], str) else test_data["result"]
                cleaned = json.dumps(result, indent=2, ensure_ascii=False)
            except:
                cleaned = json.dumps(test_data["result"], indent=2, ensure_ascii=False)

            self.content += cleaned + "\n```\n\n"

    def save(self, typst_path="report.typ", pdf_path="report.pdf"):
        with open(typst_path, "w", encoding="utf-8") as f:
            f.write(self.content)
        #subprocess.run(["typst", "compile", typst_path, pdf_path], check=True)

if __name__ == "__main__":
    datasets = [
        ("results/results_en_en_deepseek8b.csv", PROMPT_TEMPLATE_EN, "EN-Adhominem", "deepseek-r1:8b"),
    ]

    for csv_path, prompt_template, tag, model in datasets:
        report = TypstReport()
        df = pd.read_csv(csv_path)
        prompt_hash = get_prompt_hash(prompt_template)
        print("prompt_hash:", prompt_hash)

        df["dataset_name"] = "US_Parlament_nl"
        df["prompt_version"] = f"{tag}-{prompt_hash}"
        df["model"] = model
        df["cleaned_output"] = df["result"].apply(clean_result)
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now=datetime.now(ZoneInfo("Europe/Amsterdam")).strftime("%Y-%m-%d %H:%M:%S")
        info = [
                ("Model", "deepseek"),
                ("Quantisation", "quant"),
                ("Prompt Version", f'prompt_{prompt_hash}'),
                ("Dataset", "dataset_nick_name"),
                ("Date & Time", now),
                ("Duration (s)", f"{"duration"}"),
                ("Accuracy", f"{"accuracy"}%"),
                ("Unparsed ", "len_unparsed"),
                ("n tests", len("inference_df")),
                ("Electricity Usage (W)", f"{"energy_measured"}")
            ]
        report.add_general_info(info,["image.png"])

        for _, test in df.iterrows():
            report.add_test(test)

        base_name = os.path.splitext(os.path.basename(csv_path))[0]
        typst_file = f"{base_name}.typ"
        pdf_file = f"{base_name}.pdf"
        report.save(typst_file, pdf_file)
