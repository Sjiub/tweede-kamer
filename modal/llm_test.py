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
                 multithreads=1, TIME_ZONE = "Europe/Amsterdam", timeout=60 * 3, batch_size=10, dir_path=None, truth_lable_name=None, max_text_length=6000, filename=None):

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
        self.max_text_length = max_text_length
        self.filename = filename

        

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
    # Function to check if a row contains an error
    @staticmethod
    def check_error(result_str):
        try:
            result_dict = ast.literal_eval(result_str) if isinstance(result_str, str) else result_str
            if isinstance(result_dict, dict) and result_dict.get('status') == 'error':
                return True
            return False
        except:
            return True  # If we can't parse it, consider it an error
    # Function to analyze a single CSV file

    def analyze_csv(self):     
        try:     
            df = self.df
            
            # Check if we have the expected columns
            required_cols = ['result', 'is_timeout', 'final_label']
            missing_cols = [col for col in required_cols if col not in df.columns]
            
            if missing_cols:
                # Try with comma delimiter if semicolon didn't work correctly
                missing_cols = [col for col in required_cols if col not in df.columns]
                
                if missing_cols:
                    print(f"Error: Missing required columns {missing_cols}")
                    return None
            
            df["result"] = df["result"].apply(self.clean_result)
            df["count"] = df["result"].apply(self.extract_predicted_label)
            # Find rows with errors or timeouts
            timeout_rows = df[df['is_timeout'] == 1]
            error_rows = df[df['result'].apply(check_error)]

        

            # Print excluded rows
            print("Rows excluded due to timeout:")
            if len(timeout_rows) > 0:
                print(timeout_rows[['index', 'file_id', 'speaker_name']].head())
                if len(timeout_rows) > 5:
                    print(f"...and {len(timeout_rows) - 5} more")
            else:
                print("None")

            print("\nRows excluded due to errors:")
            if len(error_rows) > 0:
                print(error_rows[['index', 'file_id', 'speaker_name']].head())
                if len(error_rows) > 5:
                    print(f"...and {len(error_rows) - 5} more")
            else:
                print("None")

            print("\nRows excluded due to not containing a label: ")
            if len(df) != len(df.dropna(subset=self.truth_lable_name)):
                print(f"excluded: {df - len(df.dropna(subset=self.truth_lable_name))}")
                df = df.dropna(subset=self.truth_lable_name)

            # Filter out rows where is_timeout is 1 or result contains an error
            df_filtered = df[(df['is_timeout'] != 1) & (~df['result'].apply(check_error))]

            # Print summary of excluded rows
            total_rows = len(df)
            excluded_rows = total_rows - len(df_filtered)
            print(f"\nTotal rows in dataset: {total_rows}")
            print(f"Total rows excluded: {excluded_rows} ({excluded_rows/total_rows:.2%})")
            print(f"Remaining rows for analysis: {len(df_filtered)}")

            # Extract the ground truth labels (1 for ad hominem, 0 for not ad hominem)
            y_true = df_filtered['final_label'].values

            # Extract the predicted labels (1 if LLM found ad hominem, 0 otherwise)
            y_pred = df_filtered['count'].apply(lambda x: 1 if x > 0 else 0).values

            # Calculate metrics
            self.accuracy = accuracy_score(y_true, y_pred) * 100
            self.precision = precision_score(y_true, y_pred, zero_division=0) * 100
            self.recall = recall_score(y_true, y_pred, zero_division=0) * 100
            self.f1 = f1_score(y_true, y_pred, zero_division=0) * 100


            # Print metrics
            print(f"\nAccuracy: {self.accuracy:.2f}%")
            print(f"Precision: {self.precision:.2f}%")
            print(f"Recall: {self.recall:.2f}%")
            print(f"F1 Score: {self.f1:.2f}%")

            # Generate and print confusion matrix
            cm = confusion_matrix(y_true, y_pred)
            print("\nConfusion Matrix:")
            print(f"True Negative: {cm[0][0]}")
            print(f"False Positive: {cm[0][1]}")
            print(f"False Negative: {cm[1][0]}")
            print(f"True Positive: {cm[1][1]}")
            
            # Visualize the confusion matrix
            plt.figure(figsize=(10, 7))
            sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
                        xticklabels=['No Ad Hominem', 'Ad Hominem'],
                        yticklabels=['No Ad Hominem', 'Ad Hominem'])
            plt.xlabel('Predicted')
            plt.ylabel('Actual')
            plt.title(f'Confusion Matrix for labled data')
            plt.tight_layout()
            plt.show()
            
            # Return metrics for sorting later
            return {
                'accuracy': accuracy,
                'precision': precision,
                'recall': recall,
                'f1': f1,
                'confusion_matrix': cm,
            }
        except Exception as e:
            print(f"Error processing {e}")
            self.accuracy = 0
            self.precision = 0
            self.recall = 0
            self.f1 = 0
            return None

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
    def generate_file_name(self, dir_path, file_type: str):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        import os

        now = datetime.now(ZoneInfo(self.TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")
        if self.filename == None:
            filename = f"results_{self.prompt_language}_{self.dataset_language}_{self.model}_{now}.{file_type}".replace("/", "_")
            out_path = os.path.join(dir_path, filename)
        else:
            filename = f"{self.filename}.{file_type}"
            # Ensure 'final' directory exists
            final_dir = os.path.join(dir_path, "final")
            os.makedirs(final_dir, exist_ok=True)

            out_path = os.path.join(final_dir, filename)
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

        self.known_df = self.df.dropna(subset="result")
        if len(self.known_df)==0:
            print("Error(ish) len of df is 0")
            return
        self.known_df["predicted"] = self.known_df["result"].apply(self.parse_function)

        self.len_unclassified = len(self.known_df[self.known_df["predicted"]== "Unknown"])
        self.known_df  = self.known_df[self.known_df["predicted"] != "Unknown"]

        # Now make types consistent
        self.known_df[self.truth_lable_name] = self.known_df[self.truth_lable_name] != "No Ad Hominem"
        self.known_df["predicted"] = self.known_df["predicted"] != "No Ad Hominem"
    
        self.accuracy = accuracy_score(self.known_df[self.truth_lable_name], self.known_df["predicted"])
        self.precision_score = precision_score(self.known_df[self.truth_lable_name], self.known_df["predicted"], zero_division=0)
        self.recall_score = recall_score(self.known_df[self.truth_lable_name], self.known_df["predicted"], zero_division=0)
        self.f1_score = f1_score(self.known_df[self.truth_lable_name], self.known_df["predicted"], zero_division=0)

        print(f"Accuracy: {self.accuracy}")
        print(f"Precision: {self.precision_score}")
        print(f"Recall: {self.recall_score}")
        print(f"F1 Score: {self.f1_score}")

    def plot_confusion_matrix(self, path="confusion_matrix.png"):
        from sklearn.metrics import confusion_matrix, accuracy_score
        import seaborn as sns
        import matplotlib.pyplot as plt

        y_true = self.known_df[self.truth_lable_name]
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
        #confusion_matrix_path = self.plot_confusion_matrix(path=f'confusion_matrix.png')
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
        report.add_general_info(info,[])# plot_power_path])

        # self.df["cleaned_output"] = self.df["result"]
        # for _, test in self.known_df.iterrows():
        #     report.add_test(test)
        path = f"results_{self.prompt_language}_{self.dataset_language}_{self.model}_{now}".replace("/","_")
        print("dir_path: ", self.dir_path, "path: ", path)
        out_path = os.path.join(self.dir_path, path)
        report.save(f"{out_path}.typ", f"{out_path}.pdf")


    def do_runtime_stats(self):
        from collections import Counter
        new_df = self.df.dropna(subset=["raw"])

        def extract_runtime(row):
            try:
                return row["message"]["runtime"]
            except (TypeError, KeyError):
                return {}

        # Extract all runtime dicts
        runtimes = new_df["raw"].apply(extract_runtime).tolist()
        runtimes = [rt for rt in runtimes if rt]

        if not runtimes:
            return [], [], {}

        # Aggregate prompt-dependent fields
        prompt_fields = [
            "prompt_tokens", "generation_tokens", "total_tokens",
            "prompt_time_ms", "generation_time_ms", "total_time_ms"
        ]

        prompt_aggregates = []
        for field in prompt_fields:
            values = [rt.get(field, 0) for rt in runtimes]
            mean_value = sum(values) / len(values)
            prompt_aggregates.append((field.replace("_", " ").title(), round(mean_value, 2)))

        # Add throughput calculations
        avg_prompt_tokens = sum(rt.get("prompt_tokens", 0) for rt in runtimes) / len(runtimes)
        avg_prompt_time = sum(rt.get("prompt_time_ms", 1) for rt in runtimes) / len(runtimes)
        avg_gen_tokens = sum(rt.get("generation_tokens", 0) for rt in runtimes) / len(runtimes)
        avg_gen_time = sum(rt.get("generation_time_ms", 1) for rt in runtimes) / len(runtimes)

        throughput_stats = [
            ("Tokens/sec (prompt)", round(avg_prompt_tokens / (avg_prompt_time / 1000), 2)),
            ("Tokens/sec (generation)", round(avg_gen_tokens / (avg_gen_time / 1000), 2))
        ]

        # Environment info from the first valid row (assumed constant)
        env_fields = [
            "gguf_version", "file_type", "quantization_version", "file_size_gib",
            "bits_per_weight", "layers_offloaded", "total_layers",
            "n_batch", "n_ctx", "n_ubatch", "kv_size"
        ]
        env_runtime = runtimes[0]
        environment_info = [(field.replace("_", " ").title(), env_runtime.get(field)) for field in env_fields]

        # GPU breakdown (count how many for each type)
        gpu_counter = Counter(rt.get("gpu_device", "Unknown") for rt in runtimes)
        gpu_usage_summary = dict(gpu_counter)

        return prompt_aggregates + throughput_stats, environment_info, gpu_usage_summary



    def generate_tk_report(self, start_time,GPU_INFO, GPU_CONFIG):
        from typst_report import TypstReport, get_prompt_hash
        from datetime import datetime
        from zoneinfo import ZoneInfo
        import os
        import time
        
        report = TypstReport(self.text_key)
        prompt_hash = str(get_prompt_hash(self.prompt))
        now = datetime.now(ZoneInfo(self.TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")
        self.analyze_csv()
        #confusion_matrix_path = self.plot_confusion_matrix(path=f'confusion_matrix.png')
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
           ("Precision", f"{self.precision * 100:.1f}%"),
           ("Recall", f"{self.recall * 100:.1f}%"),
           ("F1 Score", f"{self.f1 * 100:.1f}%")
        ]
         # Add runtime statistics and GPU breakdown
        prompt_stats, environment_info, gpu_usage_summary = self.do_runtime_stats()
        info += prompt_stats
        info += [("Environment - " + k, v) for k, v in environment_info]
        info.append(("GPU Config (provided)", GPU_CONFIG))
        for gpu_name, count in gpu_usage_summary.items():
            info.append((f"GPU Usage - {gpu_name}", count))
        #Convert graph paths to relative paths
        #relative_graph_paths = [os.path.basename(path) for path in graph_paths if path]
        report.add_general_info(info, [])

        path = f"Final_{self.prompt_language}_{self.dataset_language}_{self.model}_{now}".replace("/","_")
        print("dir_path: ", self.dir_path)
        print("path: ", path)
        out_path = os.path.join(self.dir_path, path)
        report.save(f"{out_path}.typ", f"{out_path}.pdf")

