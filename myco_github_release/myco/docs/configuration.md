# Configuration Reference

All Myco settings live in two places:
- **`config/models.yaml`** — the main config file (edit this)
- **`.env`** — environment variables for secrets (API keys, tokens)
- **Settings UI** — the easiest way to change most things (Settings panel in the app)

Changes to `config/models.yaml` take effect after restarting Myco. API keys set in the UI take effect immediately without restart.

---

## Environment variables (`.env`)

Copy `.env.example` to `.env` and fill in:

```bash
# Required — your admin token
MYCO_PARENT_TOKEN=your-secret-token-here

# AI model API keys — add only the ones you want to use
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=AIza...
MISTRAL_API_KEY=...
COHERE_API_KEY=...

# Local Ollama server (default is fine for most setups)
OLLAMA_HOST=http://localhost:11434

# Server binding
MYCO_HOST=127.0.0.1   # use 0.0.0.0 only behind a reverse proxy with TLS
MYCO_PORT=8000

# CORS — comma-separated list of allowed origins
MYCO_CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# Log level: DEBUG, INFO, WARNING, ERROR
MYCO_LOG_LEVEL=INFO

# Feature flags
MYCO_SELF_IMPROVE=true
```

> **Security:** Never commit `.env` to Git. It is in `.gitignore` by default.

---

## `config/models.yaml`

### Data paths

```yaml
db_path:    data/myco.db          # SQLite database (conversations, snapshots)
chroma_path: data/chroma          # ChromaDB vector store (if used)
tfidf_path: data/tfidf_memory.json # TF-IDF fallback memory
graph_path: data/graph.json       # Knowledge graph
```

---

### Resource profile

```yaml
resource_profile: standard   # minimal | standard | full
```

| Value | RAM | Description |
|---|---|---|
| `minimal` | 2 GB | TF-IDF memory only, no ChromaDB, tiny model |
| `standard` | 4 GB | ChromaDB keyword mode, small Ollama model |
| `full` | 8 GB+ | Full embeddings, larger models |

You can override individual settings even with a profile set.

---

### Memory settings

```yaml
prefer_tfidf: false       # true = always use TF-IDF regardless of ChromaDB
max_graph_nodes: 2000     # cap on knowledge graph nodes (memory limit)
max_graph_edges: 5000     # cap on knowledge graph edges
```

**When to use `prefer_tfidf: true`:**
- Machine has less than 3 GB RAM
- Running on a Raspberry Pi or similar ARM device
- You want maximum performance with minimal overhead

---

### Model configuration

```yaml
models:
  prefer_local: true     # always try Ollama first before cloud models
  timeout_s: 60          # seconds to wait for a model response

  tiers:
    tier_powerful:        # used for complex coding/research tasks
      - ollama/llama3.2:3b
      - anthropic/claude-opus-4-5
      - openai/gpt-4o

    tier_balanced:        # used for most tasks
      - ollama/llama3.2:3b
      - anthropic/claude-sonnet-4-20250514
      - openai/gpt-4o-mini

    tier_fast:            # used for quick responses
      - ollama/qwen2.5:1.5b
      - ollama/llama3.2:1b
      - anthropic/claude-haiku-4-5-20251001

    tier_local:           # last resort, fully local
      - ollama/qwen2.5:1.5b
      - ollama/llama3.2:1b
      - ollama/tinyllama

  api_keys:
    anthropic: ""         # or set ANTHROPIC_API_KEY env var
    openai: ""
    google: ""
    mistral: ""
    cohere: ""

  custom_endpoints:
    ollama: "http://localhost:11434"
    # Add custom local servers:
    # lm_studio: "http://localhost:1234/v1"
    # vllm: "http://localhost:8080/v1"
```

**Routing rules:** Myco picks the tier based on task type:

| Task type | Complexity | Tier used |
|---|---|---|
| Coding | High | `tier_powerful` |
| Research | High | `tier_powerful` |
| Analysis | Medium | `tier_balanced` |
| Creative | Medium | `tier_balanced` |
| Conversation | Medium | `tier_fast` |
| Quick recall | Low | `tier_local` |

---

### Generation settings

```yaml
generation:
  max_tokens: 512         # max response length (lower = faster on weak hardware)
  temperature: 0.7        # 0.0 = focused, 2.0 = creative

  # Per-stage temperature — Myco gets more precise as it grows
  stage_temperatures:
    Seedling:    0.9      # more random, babbling
    Sprout:      0.85
    Sapling:     0.8
    Budding:     0.75
    Blooming:    0.7
    Flourishing: 0.65
    Ancient:     0.6      # most precise, wise
```

**`max_tokens` guide:**
- `256` — short answers, fastest, best for weak hardware
- `512` — standard (default), good balance
- `1024` — longer answers, slower
- `2048` — very detailed, requires a capable model

---

### Tools

```yaml
tools:
  - calculator       # safe math evaluation
  - current_time     # returns UTC time
  - web_search       # DuckDuckGo instant answers
  - read_file        # read files in data/ or config/ (path-traversal protected)
  - write_memory     # store key-value notes
  - read_memory      # retrieve stored notes
  - list_memory      # list all stored keys
  # - run_python     # execute sandboxed Python (disabled by default — use with caution)
```

Remove tools you don't want Myco to use. Adding `run_python` enables dynamic computation but adds a small attack surface (it runs in the security sandbox).

---

### Safety settings

```yaml
safety:
  self_improve_enabled: true    # master switch for autonomous self-improvement
  block_injections: true        # block messages that look like prompt injection
  injection_threshold: 1        # 1 = block on any match, 2 = require 2+ matches
  max_ingest_chars: 50000       # max size of ingested content
  max_chat_chars: 4000          # max length of a single chat message
```

**`injection_threshold`:**
- `1` — strictest: blocks anything that matches any injection pattern
- `2` — balanced: requires 2 matching patterns before blocking
- Set to `2` if you get false positives on normal messages

---

### Scheduler settings

```yaml
scheduler:
  heartbeat_mins: 30        # how often the growth heartbeat runs (minutes)
  consolidation_hour: 3     # UTC hour for nightly memory consolidation (0-23)
  graph_persist_mins: 15    # how often the knowledge graph saves to disk
```

**Reducing CPU usage on slow machines:**
- Increase `heartbeat_mins` to `60` or higher
- The heartbeat only does meaningful work when the growth interval has elapsed anyway

---

### Autonomous learning settings

```yaml
learner:
  enabled: true             # let Myco detect knowledge gaps and research them
  research_delay_s: 30      # seconds between research tasks (rate limiting)
  bootstrap_on_start: true  # learn core skills on first run (< 50 memories)
```

**`research_delay_s`:** On slow PCs or metered connections, increase this to `120` or more to reduce background activity.

---

## Logging (`config/logging.yaml`)

Logs go to:
- **Console** — INFO level
- **`data/myco.log`** — DEBUG level (rotates at 10 MB, keeps 5 files)
- **`data/security.log`** — WARNING level for auth/sandbox/audit events only

To increase verbosity for debugging:
```yaml
loggers:
  myco:
    level: DEBUG
```

To silence all non-error output:
```yaml
loggers:
  myco:
    level: ERROR
```

---

## Applying changes

| Change type | How to apply |
|---|---|
| `config/models.yaml` | Restart Myco |
| `.env` file | Restart Myco |
| API keys in the UI | Immediate (no restart) |
| Model switch in the UI | Immediate |
| Scheduler interval | Restart Myco |
| Safety settings | Restart Myco |

---

## Resetting to defaults

To start completely fresh:
```bash
# Delete all data (conversations, memory, graph)
rm -rf data/

# Reset config
cp config/models.yaml config/models.yaml.backup
# Edit config/models.yaml to your preferences

# Restart
python -m api.main
```

> **Warning:** This deletes all of Myco's memories and growth permanently. Take a snapshot first if you want to be able to roll back: **Settings → Memory & Storage → Take snapshot**.
