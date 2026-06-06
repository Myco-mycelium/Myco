<div align="center">

# 🍄 Myco

**A digital mind that never stops growing.**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-49%20passing-brightgreen.svg)](safety/tests/test_security.py)
[![Works Offline](https://img.shields.io/badge/offline-fully%20functional-orange.svg)](docs/offline-mode.md)
[![Discord](https://img.shields.io/badge/Discord-Join%20Community-7289da.svg)](https://discord.gg/NTGWzPy4yB)

Myco is a self-growing AI entity that starts with almost zero knowledge and learns from every interaction, document, and experience. Unlike a chatbot, it remembers everything, improves itself, and absorbs open-source code as new capabilities — all while running on a 2GB RAM laptop with no internet required.

[**Quick Start**](#quick-start) · [**Installation**](docs/installation.md) · [**Documentation**](docs/index.md) · [**Plugins**](docs/plugins.md) · [**Discord**](https://discord.gg/NTGWzPy4yB)

</div>

---

## What makes Myco different

| Feature | Myco | Typical AI chatbot |
|---|---|---|
| Remembers past conversations | ✅ Forever | ❌ Session only |
| Works without internet/API | ✅ Full offline mode | ❌ Requires cloud |
| Absorbs open-source code | ✅ Any Python plugin | ❌ Fixed capabilities |
| Gets smarter over time | ✅ Self-improving loop | ❌ Static |
| Runs on a 2GB RAM laptop | ✅ TF-IDF + tiny model | ❌ Usually 8GB+ |
| Visual plugins (3D, charts) | ✅ HTML panels in UI | ❌ Text only |
| Your data stays local | ✅ SQLite on your disk | ❌ Cloud servers |

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/Myco-mycelium/myco.git
cd myco

# 2. Install
pip install -r requirements.txt

# 3. Optional: start a local AI model (free, private)
ollama pull qwen2.5:1.5b   # recommended for 4GB RAM machines

# 4. Run
python -m api.main

# 5. Open  http://localhost:8000
```

On first start, your **parent token** is printed to the terminal. Save it — you'll need it to log in to the UI.

> **No Ollama? No API key? No problem.** Myco runs in offline mode with full memory, tools, and plugins. See [Offline Mode](docs/offline-mode.md).

---

## Growth stages

Myco begins as a Seedling and grows through 7 stages as you interact with it:

```
🌱 Seedling  →  🌿 Sprout  →  🌳 Sapling  →  🌸 Budding
                                   ↓
🌲 Ancient  ←  🎋 Flourishing  ←  🌻 Blooming
```

Each stage changes how Myco responds, reasons, and communicates. A Seedling barely forms sentences; an Ancient reasons deeply and teaches back.

---

## Key capabilities

### 🧠 Persistent memory
Three memory layers work together:
- **Episodic** (SQLite) — every conversation, timestamped forever
- **Semantic** (TF-IDF or ChromaDB) — fuzzy search over all knowledge
- **Knowledge graph** (NetworkX) — concepts and how they relate

### 📥 Multimodal learning
Teach Myco by dropping in files, URLs, or pasted text. Supports PDF, TXT, MD, CSV, JSON, HTML. Works offline.

### 🧩 Plugin system
Any Python code becomes a Myco capability:
```python
# This becomes a tool Myco can use in conversation
def summarize(text: str) -> str:
    """Summarize text to 3 sentences"""
    sentences = text.split('.')
    return '. '.join(sentences[:3]) + '.'
```
Plugins with `UI_WIDGET = '<div>...</div>'` get a live panel in the UI — 3D viewers, colour pickers, dashboards, anything.

### 🔁 Self-improvement
Every 6 hours, Myco analyses its own weaknesses, writes code to fix them, sandbox-tests the code, and queues it for your approval. You stay in full control.

### 🌐 Works offline
No API key? No Ollama? Myco still:
- Answers from memory
- Uses all tools
- Runs all plugins
- Learns from documents

---

## Supported AI models

| Provider | Models | Setup |
|---|---|---|
| **Ollama** (local, free) | Llama, Qwen, Mistral, Phi, Gemma… | `ollama pull <model>` |
| Anthropic | Claude Sonnet, Opus, Haiku | `ANTHROPIC_API_KEY=...` |
| OpenAI | GPT-4o, GPT-4o-mini | `OPENAI_API_KEY=...` |
| Google | Gemini 2.0 Flash, 1.5 Pro | `GOOGLE_API_KEY=...` |
| Mistral | Mistral Large, Small, Nemo | `MISTRAL_API_KEY=...` |
| Any OpenAI-compatible | vLLM, LM Studio, llama.cpp | Custom endpoint |

Switch models at any time from **Settings → AI Models** — no restart needed.

---

## Documentation

| Guide | Description |
|---|---|
| [Installation](docs/installation.md) | Windows, macOS, Linux, Docker |
| [Quick Start](docs/quick-start.md) | Be up and running in 5 minutes |
| [Configuration](docs/configuration.md) | Every setting explained |
| [Models](docs/models.md) | Adding models, routing, switching |
| [Plugins](docs/plugins.md) | Writing, installing, merging from GitHub |
| [API Reference](docs/api-reference.md) | All 41 endpoints with examples |
| [Offline Mode](docs/offline-mode.md) | Using Myco without any AI model |
| [Security](docs/security.md) | Threat model, sandbox, hardening |
| [Troubleshooting](docs/troubleshooting.md) | Common problems and fixes |
| [Contributing](docs/contributing.md) | How to contribute |

---

## Requirements

| Setup | RAM | Python | Notes |
|---|---|---|---|
| Offline only | 2 GB | 3.12+ | No model needed |
| With Ollama (tiny) | 3 GB | 3.12+ | `qwen2.5:1.5b` |
| With Ollama (good) | 6 GB | 3.12+ | `llama3.2:3b` |
| With cloud API | 1 GB | 3.12+ | API key required |

---

## License

MIT — see [LICENSE](LICENSE). Use it, fork it, ship it, sell it.

---

## Community

**Discord:** [discord.gg/NTGWzPy4yB](https://discord.gg/NTGWzPy4yB) — chat with other users, share plugins, get help, and follow development.

Myco is built by an individual learning as they go. The community is what makes it grow. Whether you are an expert or just curious, you are welcome.

---

## Contributing

See [CONTRIBUTING.md](docs/contributing.md). Issues and PRs welcome at all skill levels — no coding experience required to help.
