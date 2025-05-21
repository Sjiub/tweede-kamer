import os
import json
import subprocess
import sys
import jinja2
import threading
import time

class Woke_LLama():
    """
    What makes this llama woke is that it's aware over its energy consumption.
    As the warper comes with out the binarys of llama.cpp much of the original functionality is preserved.
    Additionally, on inference the option for an timeout is implemented.
    Its only working on cuda devices, but if you can be woke and use Woke_LLama!
    """
    #https://www.seedshirt.de/alpakasmall
    # https://pxhere.com/en/photo/1338909
    def __init__(self, gguf_path, llama_cli_path="/app/llama-cli"):
        self.llama_cli_path = llama_cli_path
        self.gguf_path = gguf_path
        self.power_samples = []
        self.monitor = threading.Thread(target=self.monitor_power, daemon=True)
        self.monitor.start()

    @staticmethod
    def extract_model_json_block(text):
        start_marker = "\nmodel"
        end_marker = "[end of text]"

        start_index = text.find(start_marker)
        end_index = text.find(end_marker)

        if start_index == -1 or end_index == -1:
            raise ValueError("Markers not found in text.")

        # Extract the block exactly as it appears between the markers
        block = text[start_index + len(start_marker):end_index].strip()

        return block
    @staticmethod
    def render_prompt(messages, chat_template="gemma3"):
        """
        Renders a chat prompt using Gemma 3-style formatting:
        <bos><start_of_turn>user ...<end_of_turn>
        <start_of_turn>model ...<end_of_turn>
        ...
        Appends a final <start_of_turn>model\n to indicate LLM should continue.
        """
        # TODO implement chat_template handler from gguf file
        prompt = ""

        for message in messages:
            role = message["role"]
            content = message["content"].strip()
            prompt += f"<start_of_turn>{role}\n{content}<end_of_turn>\n"

        # Add opening for model response
        prompt += "<start_of_turn>model\n"
        return prompt
    @staticmethod
    def get_gpu_power():
        """
            Return power usage of cuda driver
        """
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


    def monitor_power(self, interval=0.5):
        """
            Monitor average power consumtion of cuda driver
        """
        import time
        while True:
            power = self.get_gpu_power()
            self.power_samples.append(power)
            time.sleep(interval)

    # Doc: https://docs.unsloth.ai/basics/gemma-3-how-to-run-and-fine-tune
    # https://blog.steelph0enix.dev/posts/llama-cpp-guide/#llama-cli
    def inference(
            self,
            messages,
            temperature=0,
            top_k=64,
            top_p=0.95,
            repeat_penalty=1,
            min_p=0.01,
            n_gpu_layers=63,
            threads=None,
            ctx_size=8192,
            seed=3407,
            prio=2,
            timeout=4*60,
            verbose=True
            ):


        """
        Calls llama-cli with a Gemma-style prompt. Only includes CLI args that are set.
        Outputs logs directly to terminal.
        """
        start_time = time.time()
        self.power_samples.clear()
        # Start building command
        cmd = [
            self.llama_cli_path,
            "--model", self.gguf_path,
        ]

        # Conditionally add optional arguments
        if threads is not None:
            cmd += ["--threads", str(threads)]
        if ctx_size is not None:
            cmd += ["--ctx-size", str(ctx_size)]
        if n_gpu_layers is not None:
            cmd += ["--n-gpu-layers", str(n_gpu_layers)]
        if seed is not None:
            cmd += ["--seed", str(seed)]
        if prio is not None:
            cmd += ["--prio", str(prio)]
        if temperature is not None:
            cmd += ["--temp", str(temperature)]
        if repeat_penalty is not None:
            cmd += ["--repeat-penalty", str(repeat_penalty)]
        if min_p is not None:
            cmd += ["--min-p", str(min_p)]
        if top_k is not None:
            cmd += ["--top-k", str(top_k)]
        if top_p is not None:
            cmd += ["--top-p", str(top_p)]

        # Always include this flags
        # TODO flash attention? 
        cmd += ["-no-cnv", "--flash-attn", "--no-warmup"]

        # Render prompt with Gemma chat format
        prompt = self.render_prompt(messages)
        cmd += ["--prompt", prompt]
        try:
            if verbose:
                command_str = ' '.join(cmd)
                print("Command length:", len(command_str))
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True
                )

                captured_output = []

                for line in process.stdout:
                    print(line, end='')            # Stream to terminal
                    captured_output.append(line)   # Capture in memory

                process.wait(timeout=timeout)

                output = ''.join(captured_output).strip()

            else:
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=timeout
                )
                output = result.stdout.strip()
            duration = time.time() - start_time
            avg_power = sum(self.power_samples) / len(self.power_samples) if self.power_samples else 0
            energy = avg_power * duration

            return {
                "message": {
                    "content": self.extract_model_json_block(output), 
                    "runtime":  self.extract_llama_log_info(output)
                    },
                "error": "",
                "status": process.returncode if verbose else result.returncode,
                "time": start_time,
                "duration": duration,
                "energy": energy,
                "power-samples": self.power_samples.copy()
            }

        except subprocess.TimeoutExpired:
            if verbose:
                process.kill()
            return {
                "message": {"content": ""},
                "error": f"Timeout after {timeout} seconds",
                "status": 1,
                "time": start_time,
                "duration": time.time() - start_time,
                "energy": None,
                "power-samples": self.power_samples.copy()
            }

        except Exception as e:
            return {
                "message": {"content": ""},
                "error": str(e),
                "status": 1,
                "time": start_time,
                "duration": time.time() - start_time,
                "energy": None,
                "power-samples": self.power_samples.copy()
            }

    def perplexity():
        raise NotImplementedError()
    def check_gpu_run(log):
        # From log data check if inference was actually run on gpu
        raise NotImplementedError
    def get_model_metadata(self):
        cmd = [self.llama_cli_path,  "--model", model_path, "--info"]
        process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=sys.stderr,
                text=True
            )
        for line in process.stdout:
                print(line, end='')          # Print to console
                captured_output.append(line) # Capture output

        process.wait()

        return ''.join(captured_output).strip()
        import re
    def parse_llama_args(cmd: str) -> dict:
        args = shlex.split(cmd)
        flags = {
            "threads": "--threads",
            "ctx_size": "--ctx-size",
            "n_gpu_layers": "--n-gpu-layers",
            "seed": "--seed",
            "prio": "--prio",
            "temperature": "--temp",
            "repeat_penalty": "--repeat-penalty",
            "min_p": "--min-p",
            "top_k": "--top-k",
            "top_p": "--top-p",
        }

        config = {}
        for key, flag in flags.items():
            if flag in args:
                idx = args.index(flag)
                try:
                    val = args[idx + 1]
                    config[key] = float(val) if '.' in val else int(val)
                except (IndexError, ValueError):
                    continue

        # Detect always-included flags
        config["flash_attention"] = "--flash-attn" in args
        config["no_cnv"] = "-no-cnv" in args

        return config
    @staticmethod
    def extract_llama_log_info(log: str, cmd: str = None) -> dict:
        import re
        info = {}
        if cmd:
            info["runtime"] = parse_llama_args(cmd)

        # --- GPU Usage ---
        if "using device CUDA" in log:
            info["gpu_used"] = True
            device_match = re.search(r'using device CUDA\d+ \((.*?)\)', log)
            if device_match:
                info["gpu_device"] = device_match.group(1)
        else:
            info["gpu_used"] = False

        # --- Token Performance Metrics ---
        prompt = re.search(r'prompt eval time =\s+([\d.]+) ms / +(\d+) tokens', log)
        eval_ = re.search(r'eval time =\s+([\d.]+) ms / +(\d+) runs', log)
        total = re.search(r'total time =\s+([\d.]+) ms / +(\d+) tokens', log)

        if prompt and eval_ and total:
            prompt_time = float(prompt.group(1))
            prompt_tokens = int(prompt.group(2))
            eval_time = float(eval_.group(1))
            eval_runs = int(eval_.group(2))
            total_time = float(total.group(1))
            total_tokens = int(total.group(2))

            info.update({
                "prompt_tokens": prompt_tokens,
                "generation_tokens": total_tokens - prompt_tokens,
                "total_tokens": total_tokens,
                "prompt_time_ms": prompt_time,
                "generation_time_ms": eval_time,
                "total_time_ms": total_time
            })

        # --- GGUF File Info ---
        if m := re.search(r"file format = GGUF V(\d+)", log):
            info["gguf_version"] = int(m.group(1))

        if m := re.search(r"file type\s+= (\w+)", log):
            info["file_type"] = m.group(1)

        if m := re.search(r"file size\s+= ([\d.]+) GiB \(([\d.]+) BPW\)", log):
            info["file_size_gib"] = float(m.group(1))
            info["bits_per_weight"] = float(m.group(2))

        # --- Quantization Metadata ---
        quant_patterns = {
            "quantization_version": r"general\.quantization_version u32\s+= (\d+)",
            "file_type_code": r"general\.file_type u32\s+= (\d+)",
            "imatrix_file": r"quantize\.imatrix\.file str\s+= (.+)",
            "imatrix_dataset": r"quantize\.imatrix\.dataset str\s+= (.+)",
            "entries_count": r"quantize\.imatrix\.entries_count i32\s+= (\d+)",
            "chunks_count": r"quantize\.imatrix\.chunks_count i32\s+= (\d+)"
        }

        for key, pattern in quant_patterns.items():
            match = re.search(pattern, log)
            if match:
                val = match.group(1)
                info[key] = int(val) if val.isdigit() else val

        # --- Tensor Types ---
        tensor_patterns = {
            "f32_tensors": r"type\s+f32: +(\d+) tensors",
            "q4_0_tensors": r"type\s+q4_0: +(\d+) tensors"
        }

        for key, pattern in tensor_patterns.items():
            match = re.search(pattern, log)
            if match:
                info[key] = int(match.group(1))

        # --- Offloading and Buffer Sizes ---
        if m := re.search(r'offloaded (\d+)/(\d+) layers to GPU', log):
            info["layers_offloaded"] = int(m.group(1))
            info["total_layers"] = int(m.group(2))

        if m := re.search(r'CPU_Mapped model buffer size = ([\d.]+) MiB', log):
            info["cpu_model_buffer_size_mib"] = float(m.group(1))

        if m := re.search(r'CPU\s+output buffer size =\s+([\d.]+) MiB', log):
            info["cpu_output_buffer_size_mib"] = float(m.group(1))

        # --- llama_context settings ---
        context_patterns = {
            "n_seq_max": r'n_seq_max\s+= (\d+)',
            "n_ctx": r'n_ctx\s+= (\d+)',
            "n_ctx_per_seq": r'n_ctx_per_seq\s+= (\d+)',
            "n_batch": r'n_batch\s+= (\d+)',
            "n_ubatch": r'n_ubatch\s+= (\d+)',
            "causal_attn": r'causal_attn\s+= (\d+)',
            "flash_attn": r'flash_attn\s+= (\d+)',
            "freq_base": r'freq_base\s+= ([\d.]+)',
            "freq_scale": r'freq_scale\s+= ([\d.]+)'
        }

        for key, pattern in context_patterns.items():
            match = re.search(pattern, log)
            if match:
                info[key] = float(match.group(1)) if '.' in match.group(1) else int(match.group(1))

        # --- KV Cache Info ---
        if m := re.search(
            r"kv_size = (\d+), type_k = '([^']+)', type_v = '([^']+)', n_layer = (\d+), can_shift = (\d+), padding = (\d+)",
            log
        ):
            info["kv_size"] = int(m.group(1))
            info["kv_type_k"] = m.group(2)
            info["kv_type_v"] = m.group(3)
            info["kv_n_layer"] = int(m.group(4))
            info["kv_can_shift"] = bool(int(m.group(5)))
            info["kv_padding"] = int(m.group(6))

        return info

        



