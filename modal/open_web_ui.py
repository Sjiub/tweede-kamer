import modal
from fastapi.responses import HTMLResponse
from fastapi import FastAPI
from pydantic import BaseModel

app = modal.App("democracy slap's next top model")

# Initialise volumes
model_cache = modal.Volume.from_name("ollama-models", create_if_missing=True)
ollama_dir = "/opt/ai/models"
webui_data = modal.Volume.from_name("openwebui-data", create_if_missing=True)

# -------------------- IMAGE -------------------- #
# Nvidia image is being downloaded with build chain to complile llama-cpp-python
# llama.cpp would also work but the python interface has better predefined configs.
# Notably, llama.cpp had the issue of not finding the stop-token.
# It was in an infinite loop of talking with itself. The issue was ofcourse,
# that the prompt template was not automatically resolved, llama-cpp-python, however, could automatically
# resolve that.

download_image = (
    modal.Image.from_registry(f"ghcr.io/ggerganov/llama.cpp:full-cuda", add_python="3.12")
    .pip_install("fastapi[standard]")
    .add_local_python_source("woke_llama", copy=True)
    .env({"LD_LIBRARY_PATH":"/app/:$LD_LIBRARY_PATH"},)
    .entrypoint([])
)
# open_webui_image = (
#     modal.Image.from_registry("ghcr.io/open-webui/open-webui:main",)
#     .pip_install("open-webui")
# )

class GenerateRequest(BaseModel):
    prompt: str
    temperature: float = 0.7

@app.function(
    image=download_image, 
    volumes={ollama_dir:model_cache},
    gpu="L4"
    )
def inference(messages, params):
    from woke_llama import Woke_LLama
    import os
    print("TP 1")
    # Original long path
    long_model_path = f'{ollama_dir}/models--Mungert--gemma-3-27b-it-GGUF/blobs/f3b2259712093260f0f5336d879c8270f23429d1693f6ae5b756086d2c695668'
    # Shorter, safe path for llama.cpp
    short_model_path = '/app/model.gguf'

    # Create symlink if it doesn't already exist
    if not os.path.exists(short_model_path):
        os.symlink(long_model_path, short_model_path)

    woke_llama = Woke_LLama(
        llama_cli_path="/app/llama-cli",
        gguf_path=short_model_path
    )

    return woke_llama.inference(
        messages=messages, verbose=True
    )

@app.function(image=download_image)
@modal.asgi_app()
def fastapi_app():
    from fastapi import FastAPI, Request

    web_app = FastAPI()

    @web_app.post("/api/chat")
    async def generate(request: Request):
        body = await request.body()
        print("request body:", body)
        try:
            json_body = await request.json()
            print("Parsed JSON:", json_body)
        except Exception as e:
            print("Error parsing JSON:", str(e))
            return {"error": "Invalid JSON"}

        # Example: access individual fields
        model = json_body.get("model")
        messages = json_body.get("messages", [])
        print("Model:", model)
        print("Messages:", messages)

        data = inference.remote(messages, None)  # You can customize this with actual inputs
        return {
            "message": {"content": data["message"]["content"]},
            "energy": data["energy"]
        }
    @web_app.post("/api/generate")
    def generate(request: Request):
        data = inference.remote("hi", None)
        return  {"message": {"content": data["message"]["content"]}, "energy": data["energy"]}
    @web_app.get("/api/tags")
    def tag(request: Request):
        response = []
        for model in ["gemma3:27b"]:
            response.append({
                "name" : model,
                "model" : model
            })
        return {"models": response}
    @web_app.get("/api/version")
    def version(request: Request):
        return {"version": "0.5.1"}
    return web_app

