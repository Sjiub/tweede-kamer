import json
import pandas as pd
import subprocess
import shutil
import os

from prompt_en_zeroshot import prompt as PROMPT_ZEROSHOT_EN
from prompt_en_fewshot import prompt as PROMPT_FEWSHOT_EN
from prompt_en_CCoT import prompt as PROMPT_CCOT_EN

# Add prompt configurations
PROMPT_CONFIGS = {
    "zeroshot": {
        "prompt": PROMPT_ZEROSHOT_EN,
        "name": "zeroshot",
        "description": "Zero-shot prompt without examples"
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
    def add_test(self, test_data):
        """Add a test case to the report without requiring truth labels."""
        
        # Add header for this test case
        self.content += "== Speech Analysis\n\n"
        
        # Add speaker and party information
        self.content += f"*Speaker:* {test_data['Speaker']}\n"
        self.content += f"*Party:* {test_data['Party']}\n\n"
        
        # Add the speech text
        speech = escape_for_typst(str(test_data['Speech']))
        self.content += f"*Speech:*\n#quote[{speech}]\n\n"
        
        # Add the analysis results
        self.content += "*Analysis:*\n```json\n"
        try:
            result = clean_result(test_data["Result"]) if isinstance(test_data["Result"], str) else test_data["Result"]
            cleaned = json.dumps(result, indent=2, ensure_ascii=False)
        except:
            cleaned = json.dumps(test_data["Result"], indent=2, ensure_ascii=False)
        self.content += cleaned + "\n```\n\n"
        
        # Add separator between test cases
        self.content += "#line(length: 100%)\n\n"

    def save(self, typst_path="report.typ", pdf_path="report.pdf"):
        with open(typst_path, "w", encoding="utf-8") as f:
            f.write(self.content)
        subprocess.run(["typst", "compile", typst_path, pdf_path], check=True)


if __name__ == "__main__":
    for prompt_type, config in PROMPT_CONFIGS.items():
        datasets = [
            (f"results/results_{prompt_type}_mistral.csv", config["prompt"], f"EN-Adhominem-{config['name']}", "mistral-small3.1")
        ]

        for csv_path, prompt_template, tag, model in datasets:
            report = TypstReport()
            try:
                df = pd.read_csv(csv_path)
                prompt_hash = get_prompt_hash(prompt_template)
                
                df["dataset_name"] = "Tweede Kamer Debate"
                df["prompt_version"] = f"{tag}-{prompt_hash}"
                df["model"] = model
                df["cleaned_output"] = df["result"].apply(clean_result)
                
                from datetime import datetime
                from zoneinfo import ZoneInfo
                now = datetime.now(ZoneInfo("Europe/Amsterdam")).strftime("%Y-%m-%d %H:%M:%S")
                
                # Calculate metrics if possible
                metrics = {}
                if 'final_label' in df.columns:
                    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
                    
                    # Extract predictions
                    predictions = []
                    for _, row in df.iterrows():
                        try:
                            result = clean_result(row['result'])
                            if isinstance(result, dict) and 'found_fallacy' in result:
                                predictions.append(1 if result['found_fallacy'] else 0)
                            else:
                                predictions.append(0)
                        except:
                            predictions.append(0)
                    
                    # Get true labels
                    true_labels = df["final_label"].tolist()
                    
                    # Calculate metrics
                    metrics['accuracy'] = accuracy_score(true_labels, predictions)
                    metrics['precision'] = precision_score(true_labels, predictions, zero_division=0)
                    metrics['recall'] = recall_score(true_labels, predictions, zero_division=0)
                    metrics['f1'] = f1_score(true_labels, predictions, zero_division=0)
                
                info = [
                    ("Model", model),
                    ("Quantisation", "Q8_0"),
                    ("Prompt Version", f'Mika-prompt_EN_{prompt_hash}'),
                    ("Dataset", df["dataset_name"].iloc[0]),
                    ("Date & Time", now),
                    ("Duration (s)", f"{duration:.2f}"),
                    ("Cost ($)", f"{cost:.2f}"),
                    ("Electricity Usage (W)", f"{energy_measured:.2f}"),
                    ("Unparsed", len_unparsed),
                    ("n tests", len(df))
                ]
                
                # Add metrics if available
                if metrics:
                    info.extend([
                        ("Accuracy", f"{metrics['accuracy']:.4f}"),
                        ("Precision", f"{metrics['precision']:.4f}"),
                        ("Recall", f"{metrics['recall']:.4f}"),
                        ("F1 Score", f"{metrics['f1']:.4f}")
                    ])
                
                report.add_general_info(info, ["confusion_matrix.png", "power_plot.png"])

                for _, test in df.iterrows():
                    report.add_test(test)

                base_name = os.path.splitext(os.path.basename(csv_path))[0]
                typst_file = f"{base_name}.typ"
                pdf_file = f"{base_name}.pdf"
                report.save(typst_file, pdf_file)
                print(f"✅ Report generated: {pdf_file}")
                
            except Exception as e:
                print(f"❌ Error generating report: {e}")
                continue