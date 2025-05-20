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
                 multithreads=1, TIME_ZONE = "Europe/Amsterdam", timeout=60 * 3, batch_size=10, dir_path=None, truth_lable_name=None):

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
        self.batch_size = batch_size
        self.dir_path = dir_path
        self.truth_lable_name = truth_lable_name

        

        # Detect languages
        self.prompt_language = langdetect.detect(prompt)
        self.dataset_language = langdetect.detect(df[text_key].iloc[0])

        self.df_file_name = self.generate_file_name(dir_path,"csv")
        self.df_lock_file = self.generate_file_name(dir_path, "lock")
        # Prepair df
        # Add missing columns
        for col in [ "duration", "energy", "raw", "is_timeout"]:
            if col not in self.df.columns:
                self.df[col] = None  # or use np.nan if you're doing numerical operations
        df["power-samples"] = pd.Series(dtype="object")
        df["result"] = pd.Series(dtype="object")
        self.df.to_csv(self.df_file_name, index=False)
        self.check_types()
    def __copy__(self):
        raise RuntimeError("Copies are not allowed—object bound to its original container.")
    
    def write_df(self, function,params):
        """
        This method makes sure the result is saved with the appropriate fail-saves
        """
        # This blocks other read's -> avoids access to the file at the same time
        with open(self.df_lock_file, "w") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                self.df = pd.read_csv(self.df_file_name)
                result = function(params)
                self.df.to_csv(self.df_file_name, index=False)
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
        return result

    def write_result(self, update_list):
        """
        This method makes sure the result is saved with the appropriate fail-saves
        """
        # This blocks other read's -> avoids access to the file at the same time
        def manipulation(tralala):
            for update in update_list:
                idx = update["index"]
                del update["index"]
                self.df["is_timeout"] = self.df["is_timeout"].astype("boolean")
                is_timeout = bool(update["is_timeout"])
                self.df.at[idx, "is_timeout"] = is_timeout
                
                if not is_timeout:
                    try:
                        update["result"] = self.extract_message(update["raw"])
                    except Exception as e:
                        print("error: ", str(e))
                        update["result"] = e

                self.df.at[idx, "raw"] = update
                self.df.at[idx, "duration"] = update["duration"]
                # Ensure 'result' column is ready for storing dicts
                if "result" not in self.df.columns:
                    self.df["result"] = pd.Series(dtype="object")
                elif self.df["result"].dtype != "object":
                    self.df["result"] = self.df["result"].astype("object")
                self.df.at[idx, "result"] = update["result"]
                self.df.at[idx, "energy"] = update["energy"]
                self.df["power-samples"] = self.df["power-samples"].astype("object")
                self.df.at[idx, "power-samples"] = update["power-samples"]

        self.write_df(manipulation, None)

    def get_compute_batch(self, batch_size=None):
        """
        This method gets a compute batch.
        It marks the elements that get computed with [raw] = "processing..." to avoid multiple compute
        """
        if batch_size is None:
            batch_size = self.batch_size
        # assert batch_size < len(self.df), "ERROR: batch size is bigger than data"

        def manipulation(batch_size):
            # Ensure the dtype is compatible with strings
            if self.df["raw"].dtype != "object":
                self.df["raw"] = self.df["raw"].astype("object")

            # Step 1: Filter out rows where 'raw' is NaN (i.e., not being processed yet)
            available_df = self.df[pd.isna(self.df["raw"])]

            # Step 2: If no rows are available, return None
            if available_df.index.empty:
                return available_df.index[:0], available_df.index[:0] 
            # Handle end case, when available df is smaller than batch size
            if len(available_df) < batch_size:
                print("in get_compute_batch: Congrats final run detected!!")
                batch_size = len(available_df)

            # Step 2: Take a random sample
            sample = available_df.sample(n=batch_size, random_state=42)

            # Step 3: Mark sampled rows as "processing..."
            self.df.loc[sample.index, "raw"] = "processing..."

            # Step 4: Return indices of the sampled rows
            return sample.index, available_df.index

        return self.write_df(manipulation, batch_size)

    def compute_forecast_report(self, start_time, GPU_INFO, GPU_CONFIG):
        import time
        import datetime
        from datetime import datetime
        from zoneinfo import ZoneInfo  

        total_rows = len(self.df)
        if total_rows == 0:
            print("No data available.")
            return

        # Identify unfinished and finished rows
        unfinished_mask = self.df["raw"].isna()
        finished_mask = ~unfinished_mask

        finished_count = finished_mask.sum()
        unfinished_count = unfinished_mask.sum()
        finished_percent = (finished_count / total_rows) * 100

        # Average duration
        avg_duration = self.df.loc[finished_mask, "duration"].mean() if finished_count > 0 else None

        # Average energy
        avg_energy = self.df.loc[finished_mask, "energy"].mean() if finished_count > 0 else None

        # Forecasts
        remaining_time = (avg_duration/self.multithreads) * unfinished_count if avg_duration else None
        estimated_total_energy = avg_energy * total_rows if avg_energy else None

        # Cost calculation: duration * price/sec * threads
        price_per_sec = GPU_INFO[GPU_CONFIG]["price_per_sec"]
        total_duration = avg_duration * len(self.df)
        estimated_cost = total_duration * price_per_sec if total_duration else None
        readable_time = datetime.fromtimestamp(start_time, tz=ZoneInfo(self.TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")
        # Output
        print("\n📊 Forecast Report")
        print(f"✅ Finished: {finished_count}/{total_rows} ({finished_percent:.2f}%)")
        print(f"⏱️ Running since: {readable_time}  Avg Duration: {avg_duration:.2f}s" if avg_duration else "⏱️ Avg Duration: N/A")
        print(f"⏳ Estimated Remaining Time: {remaining_time/60:.2f} min" if remaining_time else "⏳ Remaining Time: N/A")
        print(f"⚡ Estimated Total Energy: {estimated_total_energy:.2f} J" if estimated_total_energy else "⚡ Energy: N/A")
        print(f"💰 Estimated Cost: ${estimated_cost:.2f} " if estimated_cost else "🤑 Cost: N/A")

        return {
            "finished_percent": round(finished_percent, 2),
            "avg_duration": round(avg_duration, 2) if avg_duration else None,
            "remaining_minutes": round(remaining_time / 60, 2) if remaining_time else None,
            "estimated_total_energy": round(estimated_total_energy, 2) if estimated_total_energy else None,
            "estimated_cost": round(estimated_cost, 2) if estimated_cost else None
        }



    def check_types(self):
        assert isinstance(self.df, pd.DataFrame), "df must be a pandas DataFrame"
        assert isinstance(self.prompt, str) and self.prompt != "", "prompt must be a non-empty string"
        assert isinstance(self.model, str) and self.model != "", "model must be a non-empty string"
        assert isinstance(self.dataset_language, str), "dataset_language must be a string"
        assert isinstance(self.prompt_language, str), "prompt_language must be a string"
        assert isinstance(self.dataset_nick_name, str), "dataset_nick_name must be a string"
        assert isinstance(self.prompt_nick_name, str), "prompt_nick_name must be a string"
        assert callable(self.parse_function), "parse_function must be a callable (function)"
        assert isinstance(self.hf_token, str) and self.hf_token != "", \
            "hf_token must be a non-empty string"
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
    @staticmethod
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
        if not isinstance(text, str):
            if isinstance(text, dict):
                raise Exception("Passing already parsed json to cleaner function")
            else:
                raise Exception(f"Unexpected type of str: {type(text)}, {text}")
        # Try to extract JSON block from markdown-style ```json ... ``` block
        if re.search(r'```json\b', text, re.IGNORECASE):
            try:
                match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
                if match:
                    json_str = match.group(1).strip()
                    return json.loads(json_str)
            except Exception as e:
                print("Format ```json(...)``` not valid, attemting different decoding method")

        # Try raw JSON
        try:
            return json.loads(text)
        except Exception:
            print("Format json.loads not valid, attemting different decoding method")

        # Try using ast.literal_eval for single-quoted "JSON"
        try:
            return ast.literal_eval(text)
        except Exception as e:
            print(f"Format ast.literal_eval(...) not valid: {e}")

        raise ValueError(f"Unable to parse JSON from text: {text}")
    def extract_message(self, data):
        if isinstance(data,str):
            data = self.clean_result(data)
            if "choices" in data:
                return data["choices"][0]["message"]['content']
            elif 'message' in data: 
                return data["message"]['content']
            else:
                return data
        else:
            if "message" in data:
                return self.clean_result(data["message"]['content'])
            raise Exception("Extract_message: unexpected input:", data)
    def save_test(self, energy=None, duration=None, cost=None):
        self.energy = energy
        self.duration = duration
        self.cost = cost
        
    def save_results(self, output, accuracy, len_unclassified):
        self.df = output
        self.accuracy = accuracy
        self.len_unclassified = len_unclassified
    def compute_results(self):
        import pandas as pd
        from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

        self.known_df = self.df.dropna()
        self.known_df["predicted"] = self.known_df["result"].apply(self.parse_function)

        self.len_unclassified = len(self.known_df[self.known_df["predicted"]== "Unknown"])
        self.known_df  = self.known_df[self.known_df["predicted"] != "Unknown"]

        # Now make types consistent
        self.known_df["truth_label"] = self.known_df[self.truth_lable_name] != "No Ad Hominem"
        self.known_df["predicted"] = self.known_df["predicted"] != "No Ad Hominem"
    
        self.accuracy = accuracy_score(self.known_df["truth_label"], self.known_df["predicted"])
        self.precision_score = precision_score(self.known_df["truth_label"], self.known_df["predicted"], zero_division=0)
        self.recall_score = recall_score(self.known_df["truth_label"], self.known_df["predicted"], zero_division=0)
        self.f1_score = f1_score(self.known_df["truth_label"], self.known_df["predicted"], zero_division=0)

        print(f"Accuracy: {self.accuracy}")
        print(f"Precision: {self.precision_score}")
        print(f"Recall: {self.recall_score}")
        print(f"F1 Score: {self.f1_score}")

    def plot_confusion_matrix(self, path="confusion_matrix.png"):
        from sklearn.metrics import confusion_matrix, accuracy_score
        import seaborn as sns
        import matplotlib.pyplot as plt

        y_true = self.known_df["truth_label"]
        y_pred = self.known_df["predicted"]

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
    def generate_report_labled_data(self,start_time,GPU_INFO, GPU_CONFIG):
        from typst_report import TypstReport, get_prompt_hash
        from datetime import datetime
        from zoneinfo import ZoneInfo
        import os
        import time

        report = TypstReport(self.text_key)
        confusion_matrix_path = self.plot_confusion_matrix(path=f'confusion_matrix.png')
        #plot_power_path = self.plot_power_samples(power_samples, output_path=f'power_plot.png')

        params = self.compute_forecast_report(start_time=start_time, GPU_INFO=GPU_INFO, GPU_CONFIG=GPU_CONFIG)
        print("params: ", params)
        self.duration = time.time() - start_time
        self.cost = params["estimated_cost"]
        self.energy = params["estimated_total_energy"]

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
                ("Electricity Usage (W)", f"{self.energy:.2f}")
            ]
        report.add_general_info(info,[confusion_matrix_path])# plot_power_path])

        self.df["cleaned_output"] = self.df["result"]
        for _, test in self.known_df.iterrows():
            report.add_test(test)
        path = f"results_{self.prompt_language}_{self.dataset_language}_{self.model}_{now}".replace("/","_")
        print("dir_path: ", self.dir_path, "path: ", path)
        out_path = os.path.join(self.dir_path, path)
        report.save(f"{out_path}.typ", f"{out_path}.pdf")

    def do_runtime_stats():
        new_df = self.df.dropna(subset=["raw"])
        new_df["runtime"] = new_df["raw"].apply(self.clean_result)["runtime"]
        
    def do_inference_stats():
        # Extract relevant runtime info from any row
        runtime_info = self.df["raw"].iloc[0].get("message", {}).get("runtime", {})

        inference_stats = [
            ("Prompt tokens", runtime_info.get("prompt_tokens")),
            ("Generation tokens", runtime_info.get("generation_tokens")),
            ("Total tokens", runtime_info.get("total_tokens")),
            ("Prompt time (ms)", runtime_info.get("prompt_time_ms")),
            ("Generation time (ms)", runtime_info.get("generation_time_ms")),
            ("Total time (ms)", runtime_info.get("total_time_ms")),
            ("Tokens/sec (prompt)", round(runtime_info.get("prompt_tokens", 0) / (runtime_info.get("prompt_time_ms", 1) / 1000), 2)),
            ("Tokens/sec (generation)", round(runtime_info.get("generation_tokens", 0) / (runtime_info.get("generation_time_ms", 1) / 1000), 2)),
            ("Model GGUF Version", runtime_info.get("gguf_version")),
            ("Model File Type", runtime_info.get("file_type")),
            ("Quantization Version", runtime_info.get("quantization_version")),
            ("Layers Offloaded", f"{runtime_info.get('layers_offloaded', 0)} / {runtime_info.get('total_layers', '?')}"),
            ("Batch Size", runtime_info.get("n_batch")),
            ("Context Size", runtime_info.get("n_ctx")),
            ("UBatch Size", runtime_info.get("n_ubatch")),
            ("KV Size", runtime_info.get("kv_size")),
        ]

        return inference_stats


    def generate_tk_report(self, start_time,GPU_INFO, GPU_CONFIG):
        from typst_report import TypstReport, get_prompt_hash
        from datetime import datetime
        from zoneinfo import ZoneInfo
        import os
        import time
        
        report = TypstReport(self.text_key)
        prompt_hash = str(get_prompt_hash(self.prompt))
        now = datetime.now(ZoneInfo(self.TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")
        confusion_matrix_path = self.plot_confusion_matrix(path=f'confusion_matrix.png')
        params = self.compute_forecast_report(start_time=start_time, GPU_INFO=GPU_INFO, GPU_CONFIG=GPU_CONFIG)

        self.duration = time.time() - start_time
        self.cost = params["estimated_cost"]
        self.energy = params["estimated_total_energy"]
        self.avg_duration= params["avg_duration"]

        # Count timeouts
        timeout_count = self.df["is_timeout"].sum()
        
        # Calculate total ad hominem attacks (excluding timeouts)
        non_timeout_df = self.df[self.df["is_timeout"] != 1]
        total_attacks = sum(1 for _, row in non_timeout_df.iterrows() if row.get('found_fallacy', 0) == 1)
        attack_percentage = (total_attacks / len(non_timeout_df) * 100) if len(non_timeout_df) > 0 else 0
        
        
        info = [
            ("Model", self.model),
            ("Quantisation", self.quant),
            ("Prompt Version", f'{self.prompt_nick_name}_{self.prompt_language}_{prompt_hash}'),
            ("Dataset", "Tweede Kamer Debate"),
            ("Date & Time", now),
            ("Number of Speeches", len(self.df)),
            ("Duration (s)", f"{self.duration:.2f}"),
            ("Average duration: ", self.avg_duration),
            (r"Cost (\$)", f"{self.cost:.2f}"),
            ("Electricity Usage (J)", f"{self.energy:.2f}"),
            ("Ad Hominem Attacks", f"{total_attacks} ({attack_percentage:.1f}%)"),
            ("GPU Type", GPU_CONFIG),
            ("n tests", len(self.df)),
            ("Timeouts", timeout_count),
            ("Accuracy", f"{self.accuracy * 100:.1f}%"),
           ("Precision", f"{self.precision_score * 100:.1f}%"),
           ("Recall", f"{self.recall_score * 100:.1f}%"),
           ("F1 Score", f"{self.f1_score * 100:.1f}%")
        ]
        #Convert graph paths to relative paths
        #relative_graph_paths = [os.path.basename(path) for path in graph_paths if path]
        report.add_general_info(info, [confusion_matrix_path])

        # Process each speech for the report with special handling for timeouts
        for _, speech in self.df.iterrows():
            result_to_display = None
            
            # Handle timeout cases
            if speech["is_timeout"]:
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
                    result_to_display = self.clean_result(speech["result"]) if isinstance(speech["result"], str) else speech["result"]
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
        path = f"report_tk_debate_{self.prompt_language}_{self.dataset_language}_{self.model}_{now}".replace("/","_")
        print("dir_path: ", self.dir_path)
        print("path: ", path)
        out_path = os.path.join(self.dir_path, path)
        report.save(f"{out_path}.typ", f"{out_path}.pdf")

