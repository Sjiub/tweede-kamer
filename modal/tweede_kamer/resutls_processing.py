from fpdf import FPDF
import json
import pandas as pd

from promt_en import prompt as PROMPT_TEMPLATE_EN
from promt_nl import prompt as PROMPT_TEMPLATE_NL

import requests

from fpdf import FPDF

class PDF(FPDF):
    def __init__(self):
        super().__init__()

        self.add_font("DejaVu", "", "DejaVuSans.ttf")
        self.add_font("DejaVu", "B", "DejaVuSans-Bold.ttf")
        self.set_font("DejaVu", size=11)

    def header(self):
        self.set_font("DejaVu", "B", 14)
        self.cell(0, 10, "Test Report", ln=True, align='C')
        self.ln(5)
    def add_general_info(self, info, graph_paths):
        self.set_font("DejaVu", "B", 12)
        self.cell(0, 10, "General Information", ln=True)
        self.set_font("DejaVu", size=11)


        for label, value in info:
            self.cell(50, 8, f"{label}:", ln=False)
            self.cell(0, 8, str(value), ln=True)

        self.ln(5)
        for path in graph_paths:
            if path != None:
                self.image(path, w=180)
                self.ln(10)


    def add_test(
        self,
        test_data,
        show_speech=True,
        show_true_label=True,
        show_predicted_label=True,
        show_raw_output=True,
        show_clean_output=True
    ):
        self.set_font("DejaVu", "B", 12)
        self.cell(0, 10, f"Test {test_data.get('id', '-')}", ln=True)
        self.set_font("DejaVu", size=11)


        self.ln(2)

        if show_speech:
            self.cell(40, 8, "Speech:", ln=False)
            self.multi_cell(0, 8, str(test_data["Speech"]))

        if show_true_label:
            self.cell(40, 8, "True Label:", ln=False)
            self.cell(0, 8, str(test_data["truth_label"]), ln=True)

        if show_predicted_label:
            self.cell(40, 8, "Predicted Label:", ln=False)
            self.cell(0, 8, str(test_data["predicted"]), ln=True)
    
        if show_clean_output:
            self.ln(2)
            self.set_font("DejaVu", "B", 11)
            self.cell(0, 8, "Cleaned Output:", ln=True)


            try:
                if isinstance(test_data["result"], str):
                    parsed = json.loads(test_data["result"])
                else:
                    parsed = test_data["result"]

                cleaned_json = json.dumps(parsed, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"JSON formatting error: {e}")
                cleaned_json = str(test_data["result"])

            self.set_font("DejaVu", size=9)
            line_height = 5
            lines = wrap_json_for_pdf(cleaned_json, width=100)
            block_height = line_height * len(lines)
            x_start = self.get_x()
            y_start = self.get_y()
            self.set_fill_color(240, 240, 240)
            self.rect(x_start, y_start, w=190, h=block_height + 2, style='F')
            self.set_xy(x_start + 2, y_start + 1)
            for line in lines:
                if self.get_y() > 270:
                    self.add_page()
                self.cell(0, line_height, line, ln=True)
            self.ln(3)

def add_colored_json(pdf, json_obj):
    import re
    pdf.set_font("DejaVu", size=9)
    json_str = json.dumps(json_obj, indent=2, ensure_ascii=False)

    for line in json_str.splitlines():
        if re.match(r'\s*".*?": ', line):
            pdf.set_text_color(0, 0, 180)  # keys in blue
        elif re.match(r'\s*".*"', line):
            pdf.set_text_color(0, 100, 0)  # strings in green
        elif re.match(r'\s*\d+', line):
            pdf.set_text_color(150, 0, 0)  # numbers in red
        else:
            pdf.set_text_color(0, 0, 0)    # default
        pdf.multi_cell(0, 5, line)
    pdf.set_text_color(0, 0, 0)  # reset
import textwrap

def wrap_json_for_pdf(json_text, width=100):
    """Wrap each line of JSON so long values don't overflow the page."""
    wrapped_lines = []
    for line in json_text.splitlines():
        indent = len(line) - len(line.lstrip(" "))
        wrapped = textwrap.wrap(line, width=width)
        if wrapped:
            wrapped_lines.append(wrapped[0])
            for cont_line in wrapped[1:]:
                wrapped_lines.append(" " * indent + cont_line)
        else:
            wrapped_lines.append(line)
    return wrapped_lines


def get_prompt_hash(prompt, length=8):
    """
        Unique identifier for prompt, its to avoid methodological errors
    """
    import hashlib
    # Create a SHA-256 hash object

    hash_object = hashlib.sha256(str(prompt).encode())
    # Get the hexadecimal digest
    hex_digest = hash_object.hexdigest()
    # Truncate to the desired length
    return hex_digest[:length]
def clean_result(text: str):
    import json
    import ast
    try:
        return json.loads(text)
    except Exception as e:
        try:
            print(f"issue during llm-output cleaning: {e}")
            json_start = text.find('json') + len('json')
            json_end = text.rfind('```')
            json_str = text[json_start:json_end].strip()
            return json.loads(text)
        except:
            try:
                return ast.literal_eval(text)
            except:
                return "formating error"

# Example test data


if __name__ == "__main__":
    # Generate the PDF
    pdf = PDF()
    pdf.add_page()

    # Open csv file
    df = pd.read_csv("results/results_dutch_dutch_deepseek7b.csv")
    prompt_hash = str(get_prompt_hash(PROMPT_TEMPLATE_NL))
    print("prompt_hash: ", prompt_hash)
    df["dataset_name"] = "US_Parlament_nl"
    df["prompt_version"] = f"NL-Adhominem-{prompt_hash}"
    df["model"] = "TheBloke/deepseek-llm-7B-chat-GGUF"
    df["cleaned_output"] = df["raw_output"].apply(clean_result)

    for _, test in df.iterrows():
        pdf.add_test(test)

    pdf.output("results_dutch_dutch_deepseek7b.pdf")
    pdf = PDF()
    pdf.add_page()

    # Open csv file
    df = pd.read_csv("results/results_english_english_deepseek7b.csv")
    prompt_hash = str(get_prompt_hash(PROMPT_TEMPLATE_EN))
    print("prompt_hash: ", prompt_hash)
    df["dataset_name"] = "US_Parlament_nl"
    df["prompt_version"] = f"EN-Adhominem-{prompt_hash}"
    df["model"] = "TheBloke/deepseek-llm-7B-chat-GGUF"
    df["cleaned_output"] = df["raw_output"].apply(clean_result)

    for _, test in df.iterrows():
        pdf.add_test(test)

    pdf.output("results_english_english_deepseek7b.pdf")
    pdf = PDF()
    pdf.add_page()

    # Open csv file
    df = pd.read_csv("results/results_english_english_geitje.csv")
    prompt_hash = str(get_prompt_hash(PROMPT_TEMPLATE_EN))
    print("prompt_hash: ", prompt_hash)
    df["dataset_name"] = "US_Parlament_nl"
    df["prompt_version"] = f"EN-Adhominem-{prompt_hash}"
    df["model"] = "BramVanroy/GEITje-7B-ultra-GGUF"
    df["cleaned_output"] = df["raw_output"].apply(clean_result)

    for _, test in df.iterrows():
        pdf.add_test(test)

    pdf.output("results_english_english_geitje.pdf")
    pdf = PDF()
    pdf.add_page()

    # Open csv file
    df = pd.read_csv("results/results_dutch_dutch_geitje.csv")
    prompt_hash = str(get_prompt_hash(PROMPT_TEMPLATE_EN))
    print("prompt_hash: ", prompt_hash)
    df["dataset_name"] = "US_Parlament_nl"
    df["prompt_version"] = f"NL-Adhominem-{prompt_hash}"
    df["model"] = "BramVanroy/GEITje-7B-ultra-GGUF"
    df["cleaned_output"] = df["raw_output"].apply(clean_result)

    for _, test in df.iterrows():
        pdf.add_test(test)

    pdf.output("results_dutch_dutch_geitje.pdf")
