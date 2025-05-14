import pandas as pd
import fcntl
import langdetect

class LLM_TEST:
    """
        Method to run inference on a model.
        `repo_id` is the huggingface link to a gguf compatibale model.
        `query` A list of texts to analyse
        `prompt` The promt, it has to have the marker {text} where the query element will be inserted
        `quant` Quantisation of gguf file
        `hf_token` Api token to hugging face, for models with restriction
    """


    def __init__(self, prompt=None, df=None, parse_function=None, system_prompt=None, model=None, quant=None, ollama=False,
                 hf_token=None, dataset_nick_name=None, prompt_nick_name=None, text_key="Speech", row_range=None, row_count=None, 
                 multithreads=1, TIME_ZONE = "Europe/Amsterdam", timeout=60 * 3):

        self.prompt = prompt
        self.df = df
        self.model = model
        self.quant = quant
        self.ollama = ollama
        self.hf_token = hf_token
        self.dataset_nick_name = dataset_nick_name
        self.prompt_nick_name = prompt_nick_name
        self.text_key = text_key
        self.parse_function = parse_function
        self.system_prompt = system_prompt
        self.row_range = row_range
        self.row_count = row_count
        self.multithreads= multithreads
        self.TIME_ZONE = TIME_ZONE
        self.timeout = timeout

        

        # Detect languages
        self.prompt_language = langdetect.detect(prompt)
        self.dataset_language = langdetect.detect(df[text_key].iloc[0])

        self.df_file_name = self.generate_file_name(".","csv")
        self.df_lock_file = self.generate_file_name(".", "lock")
        self.df.to_csv(self.df_file_name, index=False)
        self.check_types()
    def __copy__(self):
        raise RuntimeError("Copies are not allowed—object bound to its original container.")

    def write_result(self, update_list):
        """
        This method makes sure the result is saved with the appropriate fail-saves
        """
        # This blocks other read's -> avoids access to the file at the same time
        with open(self.df_lock_file, "w") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                self.df = pd.read_csv(self.df_file_name)
                for update in update_list:
                    idx = update["index"]
                    result = update["result"]
                    raw = update["raw"]
                    self.df.loc[idx, ["result", "raw"]] = [result, raw]

                self.df.to_csv(self.df_file_name, index=False)
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)


    def check_types(self):
        assert isinstance(self.df, pd.DataFrame), "df must be a pandas DataFrame"
        assert isinstance(self.prompt, str) and self.prompt != "", "prompt must be a non-empty string"
        assert isinstance(self.model, str) and self.model != "", "model must be a non-empty string"
        assert isinstance(self.ollama, bool), "ollama must be a boolean"
        assert isinstance(self.dataset_language, str), "dataset_language must be a string"
        assert isinstance(self.prompt_language, str), "prompt_language must be a string"
        assert isinstance(self.dataset_nick_name, str), "dataset_nick_name must be a string"
        assert isinstance(self.prompt_nick_name, str), "prompt_nick_name must be a string"
        assert callable(self.parse_function), "parse_function must be a callable (function)"

        # Conditional check: if not using ollama, hf_token must be present
        if not self.ollama:
            assert isinstance(self.hf_token, str) and self.hf_token != "", \
                "hf_token must be a non-empty string if ollama is False"
            assert isinstance(self.quant, str) and self.quant != "", "quant must be a non-empty string"

        print("All type checks passed.")
    def get_df(self):
        return self.df
    def get_output(self):
        print("second output:", self.output)
        assert self.output != None, "Output is missing. Did the test run successfully?"
        return self.output
    def generate_file_name(self, dir_path, file_type:str):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        import os
        now=datetime.now(ZoneInfo(self.TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")
        path = f"results_{self.prompt_language}_{self.dataset_language}_{self.model}_{now}.{file_type}".replace("/","_")
        out_path = os.path.join(dir_path,path)
        return out_path
    def clean_result(self,text: str):
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
    def save_test(self, energy=None, duration=None, cost=None):
        self.energy = energy
        self.duration = duration
        self.cost = cost
        
    def save_results(self, output, accuracy, len_unclassified):
        self.df = output
        self.accuracy = accuracy
        self.len_unclassified = len_unclassified

    def plot_confusion_matrix(self, path="confusion_matrix.png"):
        from sklearn.metrics import confusion_matrix, accuracy_score
        import seaborn as sns
        import matplotlib.pyplot as plt

        y_true = self.df["truth_label"]
        y_pred = self.df["predicted"]

        # Use boolean labels for computation
        labels = [False, True]
        label_names = ["No Ad Hominem", "Ad Hominem"]

        # Compute accuracy
        accuracy = accuracy_score(y_true, y_pred)
        print(f"✅ Accuracy: {accuracy:.2%}")

        # Compute confusion matrix
        cm = confusion_matrix(y_true, y_pred, labels=labels)

        # Plot confusion matrix
        plt.figure(figsize=(6, 5))
        sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                    xticklabels=label_names,
                    yticklabels=label_names)
        plt.xlabel("Predicted Label")
        plt.ylabel("True Label")
        plt.title("Confusion Matrix")
        plt.tight_layout()
        plt.savefig(path)
        plt.close()

        return path

    def plot_power_samples(self, df, output_path="power_usage_plot.png"):
        import matplotlib.pyplot as plt
        plt.figure(figsize=(10, 4))
        plt.plot(df, label="GPU Power (W)", linewidth=1.2)
        plt.title("GPU Power Usage Over Time")
        plt.xlabel("Sample Number")
        plt.ylabel("Power Draw (Watts)")
        plt.grid(True)
        plt.legend()
        plt.tight_layout()
        plt.savefig(output_path)
        plt.close()
        return output_path
    def generate_report_labled_data(self):
        from typst_report import TypstReport, get_prompt_hash
        from datetime import datetime
        from zoneinfo import ZoneInfo
        import os

        report = TypstReport()
        confusion_matrix_path = self.plot_confusion_matrix(path=f'confusion_matrix.png')
        #plot_power_path = self.plot_power_samples(power_samples, output_path=f'power_plot.png')


        # Open csv file
        # Generate unique identifier
        prompt_hash = str(get_prompt_hash(self.prompt))
        now=datetime.now(ZoneInfo(self.TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")
        info = [
                ("Model", self.model),
                ("Quantisation", self.quant),
                ("Prompt Version", f'{self.prompt_nick_name}_{self.prompt_language}_{prompt_hash}'),
                ("Dataset", self.dataset_nick_name),
                ("Date & Time", now),
                ("Duration (s)", f"{self.duration:.2f}"),
                (r"Cost (\$)", f"{self.cost:.2f}"),
                ("Accuracy", f"{(self.accuracy * 100):.2f}%"),
                ("Unparsed ", self.len_unclassified),
                ("n tests", len(self.df)),
          #      ("Electricity Usage (W)", f"{energy_measured:.2f}")
            ]
        report.add_general_info(info,[confusion_matrix_path])# plot_power_path])

        self.df["cleaned_output"] = self.df["result"].apply(self.clean_result)
        for _, test in self.df.iterrows():
            report.add_test(test)
        path = f"results_{self.prompt_language}_{self.dataset_language}_{self.model}_{now}".replace("/","_")
        out_path = os.path.join(".", path)
        report.save(f"{out_path}.typ", f"{out_path}.pdf")
