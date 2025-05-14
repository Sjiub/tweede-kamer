import os
import json
from llama_cpp import LLama

class Davids_LLama(LLama):
    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)
        self.gguf_path = None
        self.params_path = None
        self.template_path = None

    def load_ollama_model(self, model_dir, gguf_path, params_path, DEBUG=False):
        """
        Loads model paths from an ollama format.
        
        Args:
            model_dir (str): Path to the directory containing the model files.
        """
        self.gguf_path = os.path.join(model_dir, "model.gguf")
        self.params_path = os.path.join(model_dir, "params.json")
        #self.template_path = os.path.join(model_dir, "template.txt")

        # check if these files actually exist:
        for path, name in [
            (self.gguf_path, "gguf_path"),
            (self.params_path, "params_path"),
        ]:
            if not os.path.isfile(path):
                raise FileNotFoundError(f"Expected {name} at: {path}")

        with open(self.params_path, "r", encoding="utf-8") as f:
            self.params = json.load(f)
        # Now initialize the base LLama class
        super().__init__(
            model_path=self.gguf_path,
            params = self.params,
            verbose=DEBUG
        )

        print("Davids_LLama model loaded and initialized.")
