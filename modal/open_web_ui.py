import modal


app = modal.App("democracy slap's next top model")

# Initialise volumes
model_cache = modal.Volume.from_name("ollama-cache", create_if_missing=True)
webui_data = modal.Volume.from_name("openwebui-data", create_if_missing=True)

# -------------------- IMAGE -------------------- #
# Nvidia image is being downloaded with build chain to complile llama-cpp-python
# llama.cpp would also work but the python interface has better predefined configs.
# Notably, llama.cpp had the issue of not finding the stop-token.
# It was in an infinite loop of talking with itself. The issue was ofcourse,
# that the prompt template was not automatically resolved, llama-cpp-python, however, could automatically
# resolve that.

download_image = (
    modal.Image.from_registry(f"nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04", add_python="3.12")
    .apt_install(
        "build-essential", "cmake", "git",
        "python3-dev", "python3-pip",
        "libopenblas-dev", "libomp-dev", "clang", "gcc", 
        "curl", "systemctl", "nodejs", "npm"
    )
    # Install other deps
    .pip_install("ollama","open-webui")
    .run_commands([
        "curl -fsSL https://ollama.com/install.sh | sh"
    ])
    .entrypoint([])
    # Add files
    .add_local_file("ollama.service", remote_path= "/etc/systemd/system/ollama.service")
)
open_webui_image = (
    modal.Image.from_registry("ghcr.io/open-webui/open-webui:main",)
    .pip_install("open-webui")
)
@app.function(
    image=download_image, 
    volumes={"/root/.ollama": model_cache}, 
    timeout=60 * 10,
)
def download_ollama_model(model: str):
    #https://modal.com/blog/how_to_run_ollama_article
    print("Enter download ollama model function")
    import os
    import subprocess
    import ollama

    subprocess.run(["systemctl", "start", "ollama"])

    import time
    time.sleep(1)

    import ollama
    ollama.pull(model)

@app.function(
    image=download_image,
    volumes={"/root/.ollama": model_cache},
    gpu="L4",
    timeout=60 * 60,
)
@modal.web_server(11434)
def ollama_server():
    import subprocess
    import os

    print("Starting Ollama server...")

    env = os.environ.copy()
    env["OLLAMA_HOST"] = "0.0.0.0"  # 👈 IMPORTANT

    subprocess.run("OLLAMA_HOST=0.0.0.0 ollama serve", shell=True)


@app.function(
    image=open_webui_image,
    volumes={"/app/backend/data/persist": webui_data}
)
@modal.asgi_app()
def open_webui():
    import subprocess
    import os
    import sys
    from open_webui.main import app as webui_app
    
    # print("Continue open webui function")
    # handle = modal.Function.from_name("democracy slap's next top model", "ollama_server")

    #web_url = handle.web_url
    
    web_url="https://post-x--democracy-slap-s-next-top-model-ollama-server-dev.modal.run"
    print("WebUI is available at:", web_url)
    env = os.environ.copy()
    env["OLLAMA_BASE_URL"] = web_url
    env["DATA_DIR"] = "/app/backend/data/persist"
    env["WEBUI_URL"] = "0.0.0.0"
    env["WEBUI_SECRET_KEY"] = "very secret"
    env["GLOBAL_LOG_LEVEL"] = "DEBUG"
    os.environ = env
    return webui_app
    subprocess.run(
        ["uvicorn", "open_webui.main:app", "--host", "0.0.0.0", "--port", "8080"],
        cwd="/app/backend",
        env=env,
        check=True
    )

@app.function()
def initialise():
    print("Initialise interface")
    model_whislist= [
        #"mistral-small3.1",
        "gemma3:1b"
    ]
    for model in model_whislist:
        download_ollama_model.remote(model).get()
