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
    def __init__(self, gguf_path, params, llama_cli_path="/app/llama-cli"):
        self.llama_cli_path = llama_cli_path
        self.gguf_path = gguf_path
        self.params = params
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
            n_gpu_layers=-1,
            threads=None,
            ctx_size=16384,
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
        power_samples.clear()
        # Start building command
        cmd = [
            llama_cli_path,
            "--model", model_path
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

        # Always include this flag
        cmd += ["-no-cnv"]

        # Render prompt with Gemma chat format
        prompt = render_prompt(messages)
        cmd += ["--prompt", prompt]
        try:
            if verbose:
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
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=timeout
                )
                output = result.stdout.strip()
            avg_power = sum(self.power_samples) / len(self.power_samples) if self.power_samples else 0
            energy = avg_power * duration

            return {
                "message": {"content": extract_model_json_block(output)},
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
        



