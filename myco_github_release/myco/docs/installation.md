# Installation Guide

Myco runs on Windows, macOS, and Linux. The minimum requirement is Python 3.12 and about 2 GB of free RAM. No AI model is required to get started.

---

## Table of contents

- [Prerequisites](#prerequisites)
- [Linux](#linux)
- [macOS](#macos)
- [Windows](#windows)
- [Docker](#docker)
- [Verify the installation](#verify-the-installation)
- [Adding an AI model](#adding-an-ai-model)

---

## Prerequisites

### Python 3.12+

Check your version:
```bash
python3 --version
```

If you have an older version:
- **Linux (Ubuntu/Debian):** `sudo apt install python3.12 python3.12-pip`
- **macOS:** `brew install python@3.12`
- **Windows:** Download from [python.org](https://www.python.org/downloads/)

### Git

```bash
git --version
```

If not installed:
- **Linux:** `sudo apt install git`
- **macOS:** `brew install git` or install Xcode Command Line Tools
- **Windows:** Download from [git-scm.com](https://git-scm.com)

---

## Linux

```bash
# 1. Clone the repository
git clone https://github.com/Myco-mycelium/myco.git
cd myco

# 2. Create a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy the environment template
cp .env.example .env

# 5. Set your parent token (use a strong random string)
# Edit .env and set MYCO_PARENT_TOKEN=your-secret-token
# Or generate one:
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# 6. Start Myco
python -m api.main
```

Open **http://localhost:8000** in your browser.

### Ubuntu/Debian specific

If you get `pip: command not found`:
```bash
sudo apt install python3-pip python3-venv
```

If ChromaDB install fails on ARM (Raspberry Pi):
```bash
pip install chromadb --no-binary chromadb
```
Or use lightweight mode (TF-IDF only) by setting `prefer_tfidf: true` in `config/models.yaml`.

---

## macOS

```bash
# 1. Clone
git clone https://github.com/Myco-mycelium/myco.git
cd myco

# 2. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment
cp .env.example .env
# Edit .env — at minimum set MYCO_PARENT_TOKEN

# 5. Start
python -m api.main
```

### Apple Silicon (M1/M2/M3)

ChromaDB and most packages work natively on Apple Silicon. If you hit any issues:
```bash
# Install Rosetta 2 if needed
softwareupdate --install-rosetta

# Use the native arm64 Python
arch -arm64 pip install -r requirements.txt
```

---

## Windows

### Option A — PowerShell (recommended)

```powershell
# 1. Clone
git clone https://github.com/Myco-mycelium/myco.git
cd myco

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3. Install
pip install -r requirements.txt

# 4. Set up environment
copy .env.example .env
# Edit .env in Notepad — set MYCO_PARENT_TOKEN

# 5. Start
python -m api.main
```

> **Note:** If you see `execution policy` errors running the activate script:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### Option B — WSL 2 (Windows Subsystem for Linux)

WSL 2 gives the best compatibility. Follow the [Linux instructions](#linux) inside a WSL 2 Ubuntu terminal.

### Windows firewall

Windows may ask to allow Python through the firewall when Myco starts. Click **Allow** — this is needed for the local web UI.

### Path issues

If `python` is not found, try `py` instead:
```powershell
py -m api.main
```

---

## Docker

The Docker setup is the easiest way to run Myco in production or on a server.

### With docker-compose (recommended)

```bash
# 1. Clone
git clone https://github.com/Myco-mycelium/myco.git
cd myco

# 2. Set your token
export MYCO_PARENT_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

# 3. Pull Ollama model (optional)
docker run --rm ollama/ollama pull qwen2.5:1.5b

# 4. Start
docker-compose up -d

# View logs
docker-compose logs -f myco
```

Open **http://localhost:8000**.

### Manual Docker

```bash
# Build
docker build -t myco .

# Run (replace YOUR_TOKEN with a real token)
docker run -d \
  --name myco \
  -p 127.0.0.1:8000:8000 \
  -e MYCO_PARENT_TOKEN=YOUR_TOKEN \
  -v myco_data:/app/data \
  --read-only \
  --no-new-privileges \
  myco

# With GPU support (NVIDIA)
docker run -d \
  --name myco \
  --gpus all \
  -p 127.0.0.1:8000:8000 \
  -e MYCO_PARENT_TOKEN=YOUR_TOKEN \
  -v myco_data:/app/data \
  myco
```

### Reverse proxy (nginx)

To expose Myco publicly with HTTPS:

```nginx
server {
    listen 443 ssl;
    server_name myco.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/myco.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/myco.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
        proxy_read_timeout 300s;
        # Required for SSE (streaming chat)
        proxy_cache off;
        proxy_set_header Connection '';
        chunked_transfer_encoding on;
    }
}
```

---

## Verify the installation

After starting, check:

```bash
# Should return {"status":"alive","mode":"online" or "offline"}
curl http://localhost:8000/health
```

Open the UI at **http://localhost:8000** — you should see the Myco interface with an onboarding screen asking for your parent token.

If you see the **offline mode banner** (amber bar), Myco is running but no AI model is connected. That is fine — everything except generative AI works. See [Adding an AI model](#adding-an-ai-model).

---

## Adding an AI model

### Option A — Ollama (local, free, recommended)

```bash
# Install Ollama from https://ollama.com

# Pull a model (choose based on your RAM)
ollama pull qwen2.5:1.5b    # 4 GB RAM
ollama pull llama3.2:3b     # 6 GB RAM
ollama pull llama3.2        # 8 GB RAM

# Ollama starts automatically. Myco detects it within 30 seconds.
```

### Option B — Cloud API key

Set an environment variable before starting:
```bash
export ANTHROPIC_API_KEY=sk-ant-...   # Claude
export OPENAI_API_KEY=sk-...          # GPT-4o
export GOOGLE_API_KEY=AIza...         # Gemini
```

Or paste the key in the UI: **Settings → AI Models → Select provider → API Key**.

### Option C — Local server (vLLM, LM Studio, llama.cpp)

In Settings → AI Models → Custom, enter:
- **Endpoint:** `http://localhost:1234/v1` (LM Studio default)
- **Model name:** the model name shown in your local server

---

## Next steps

- [Quick Start Guide](quick-start.md) — be productive in 5 minutes
- [Configuration](configuration.md) — tune Myco for your hardware
- [Adding plugins](plugins.md) — give Myco new abilities
