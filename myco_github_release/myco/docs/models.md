# AI Models

Myco supports every major AI provider and any OpenAI-compatible local server. This page covers adding models, switching between them, and how the router picks the right model for each task.

---

## Supported providers

| Provider | Models | How to connect |
|---|---|---|
| **Ollama** (local) | Llama 3.2, Qwen 2.5, Mistral, Phi-3, Gemma 2, TinyLlama, + any model | Install Ollama, pull a model |
| **Anthropic** | Claude Opus 4.5, Sonnet 4, Haiku 4.5 | `ANTHROPIC_API_KEY` |
| **OpenAI** | GPT-4o, GPT-4o-mini, GPT-4 Turbo, o1-mini | `OPENAI_API_KEY` |
| **Google** | Gemini 2.0 Flash, 1.5 Pro, 1.5 Flash | `GOOGLE_API_KEY` |
| **Mistral** | Mistral Large, Small, Nemo, Codestral | `MISTRAL_API_KEY` |
| **Cohere** | Command R+, Command R | `COHERE_API_KEY` |
| **LM Studio** | Any GGUF model | Custom endpoint |
| **vLLM** | Any HuggingFace model | Custom endpoint |
| **llama.cpp** | Any GGUF model | Custom endpoint |
| **Any OpenAI-compatible API** | Any model | Custom endpoint |

---

## Ollama (recommended — free, private, offline)

Ollama runs models locally. No account, no API key, no data leaves your machine.

### Install Ollama

```bash
# Linux
curl -fsSL https://ollama.com/install.sh | sh

# macOS
brew install ollama

# Windows
# Download from https://ollama.com/download
```

### Pull a model

```bash
# Recommended by RAM:
ollama pull qwen2.5:1.5b    # 2–4 GB RAM  (~1 GB download)
ollama pull llama3.2:1b     # 4 GB RAM    (~1.3 GB download)
ollama pull llama3.2:3b     # 6 GB RAM    (~2 GB download)
ollama pull llama3.2        # 8 GB RAM    (~4 GB download)
ollama pull mistral         # 8 GB RAM    (~4 GB download)

# Coding focused:
ollama pull codellama       # 8 GB RAM
ollama pull deepseek-coder  # 8 GB RAM

# Ultra-lightweight (2 GB RAM):
ollama pull tinyllama       # 637 MB
ollama pull qwen2.5:0.5b    # 397 MB
```

Myco detects Ollama automatically at `http://localhost:11434`. No configuration needed.

### Run Ollama in the background

```bash
# Linux/macOS — run as a service
ollama serve &

# Or start automatically on boot
systemctl enable ollama    # Linux systemd
```

---

## Cloud API providers

### Anthropic (Claude)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Or in the UI: **Settings → AI Models → Anthropic → paste key → Use this brain**

Available models:
- `claude-opus-4-5` — most capable, best reasoning
- `claude-sonnet-4-20250514` — best balance of speed and quality
- `claude-haiku-4-5-20251001` — fastest, cheapest

### OpenAI

```bash
export OPENAI_API_KEY=sk-...
```

Available models:
- `gpt-4o` — best quality
- `gpt-4o-mini` — fast and cheap
- `gpt-4-turbo` — large context window
- `o1-mini` — strong reasoning

### Google Gemini

```bash
export GOOGLE_API_KEY=AIza...
```

Available models:
- `gemini-2.0-flash` — fast, cheap, multimodal
- `gemini-1.5-pro` — large context, strong reasoning
- `gemini-1.5-flash` — balance of speed and quality

### Mistral

```bash
export MISTRAL_API_KEY=...
```

Available models:
- `mistral-large-latest`
- `mistral-small-latest`
- `open-mistral-nemo`
- `codestral-latest`

### Cohere

```bash
export COHERE_API_KEY=...
```

Available models:
- `command-r-plus` — best quality
- `command-r` — good balance
- `command` — fastest

---

## Local servers (advanced)

If you run your own inference server, add it as a custom endpoint.

### LM Studio

1. Start LM Studio and load a model
2. Click **Local Server** and start it (default: `http://localhost:1234`)
3. In Myco UI: **Settings → AI Models → Custom**
   - Endpoint: `http://localhost:1234/v1`
   - Model name: the model name shown in LM Studio

### vLLM

```bash
# Start vLLM
python -m vllm.entrypoints.openai.api_server \
  --model meta-llama/Llama-3.2-3B \
  --port 8080
```

In Myco: endpoint `http://localhost:8080/v1`, model `meta-llama/Llama-3.2-3B`.

### llama.cpp server

```bash
./server -m model.gguf --host 0.0.0.0 --port 8081
```

In Myco: endpoint `http://localhost:8081/v1`, model `llama`.

### Any OpenAI-compatible API

```yaml
# config/models.yaml
models:
  custom_endpoints:
    my_server: "http://192.168.1.100:8000/v1"
  tiers:
    tier_balanced:
      - my_server/my-model-name
```

---

## Switching models at runtime

No restart needed — switch the active model anytime.

### From the UI

**Settings → AI Models** → select provider and model → **Use this brain**

The change takes effect on the next message.

### From the API

```bash
curl -X POST http://localhost:8000/models/switch \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model": "ollama/llama3.2:3b"}'
```

### Add a new model at runtime

```bash
curl -X POST http://localhost:8000/models/add \
  -H "Authorization: Bearer YOUR_PARENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "anthropic",
    "model": "claude-opus-4-5",
    "api_key": "sk-ant-...",
    "tier": "tier_powerful"
  }'
```

---

## How routing works

Myco automatically picks the best available model for each task. You do not need to manage this manually.

### Task-to-tier mapping

| Task type | Tier used | Why |
|---|---|---|
| Complex coding | `tier_powerful` | Needs strong reasoning |
| Deep research | `tier_powerful` | Needs broad knowledge |
| Analysis | `tier_balanced` | Good quality, not too slow |
| Creative writing | `tier_balanced` | Benefits from creativity |
| Regular chat | `tier_fast` | Quick responses feel natural |
| Memory recall | `tier_local` | Simple retrieval, save costs |

### Tier fallback

If the primary model in a tier is unreachable, Myco tries the next model in that tier, then moves to the next tier down, then falls back to local models. If all models fail, it switches to the offline brain.

### Override routing

To force a specific model for all tasks, put it first in all tiers in `config/models.yaml`:

```yaml
models:
  tiers:
    tier_powerful:
      - ollama/llama3.2:3b   # always use this first
      - anthropic/claude-opus-4-5
    tier_balanced:
      - ollama/llama3.2:3b
    tier_fast:
      - ollama/llama3.2:3b
    tier_local:
      - ollama/llama3.2:3b
```

Or set `prefer_local: true` to always use Ollama regardless of tier.

---

## Model health and availability

Myco probes model availability every 30 seconds. A model that fails a request is marked unhealthy for 60 seconds before being tried again.

To check model health:

```bash
curl http://localhost:8000/status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Returns:
```json
{
  "online": true,
  "mode": "online",
  "model_status": {
    "tiers": {
      "tier_fast": [
        {"model": "ollama/qwen2.5:1.5b", "healthy": true},
        {"model": "anthropic/claude-haiku-4-5-20251001", "healthy": false}
      ]
    }
  }
}
```

---

## Performance tuning by hardware

### 2 GB RAM machine

```yaml
models:
  prefer_local: true
  tiers:
    tier_powerful:  [ollama/tinyllama]
    tier_balanced:  [ollama/tinyllama]
    tier_fast:      [ollama/qwen2.5:0.5b]
    tier_local:     [ollama/qwen2.5:0.5b]

generation:
  max_tokens: 256
  temperature: 0.7
```

### 4 GB RAM machine

```yaml
models:
  prefer_local: true
  tiers:
    tier_powerful:  [ollama/qwen2.5:1.5b]
    tier_balanced:  [ollama/qwen2.5:1.5b]
    tier_fast:      [ollama/llama3.2:1b]
    tier_local:     [ollama/llama3.2:1b]

generation:
  max_tokens: 512
```

### 8 GB RAM machine

```yaml
models:
  prefer_local: true
  tiers:
    tier_powerful:  [ollama/llama3.2, anthropic/claude-sonnet-4-20250514]
    tier_balanced:  [ollama/llama3.2:3b]
    tier_fast:      [ollama/qwen2.5:1.5b]
    tier_local:     [ollama/qwen2.5:1.5b]
```

### No local machine (cloud only)

```yaml
models:
  prefer_local: false
  tiers:
    tier_powerful:  [anthropic/claude-opus-4-5, openai/gpt-4o]
    tier_balanced:  [anthropic/claude-sonnet-4-20250514, openai/gpt-4o-mini]
    tier_fast:      [anthropic/claude-haiku-4-5-20251001]
    tier_local:     [anthropic/claude-haiku-4-5-20251001]
```
