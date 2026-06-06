# Changelog

All notable changes to Myco are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [2.0.0] — Initial public release

### What is Myco?

Myco is a self-growing AI entity that starts with almost no knowledge and learns through every interaction. Unlike a chatbot, it persists everything it learns, improves itself over time, and can absorb open-source Python code as new capabilities.

### Features in this release

#### Core
- **Self-growing AI** — 7 growth stages (Seedling → Ancient), each with different behaviour and personality
- **Three memory layers** — episodic (SQLite), semantic (TF-IDF or ChromaDB), knowledge graph (NetworkX)
- **Works offline** — full functionality without any AI model using the offline brain (intent detection + memory search)
- **Autonomous learning** — detects knowledge gaps in conversation and researches them in the background

#### Models
- **Any AI model** — Ollama (local), Claude, GPT-4o, Gemini, Mistral, Cohere, or any OpenAI-compatible endpoint
- **Smart routing** — automatically picks the best model for each task type
- **Hot-swap** — switch models without restarting
- **Graceful fallback** — if any model fails, tries alternatives; if all fail, switches to offline brain

#### Plugins
- **Open-source merger** — paste Python code or a GitHub URL; Myco absorbs it as a capability
- **Tool plugins** — functions Myco calls during conversation
- **Viewer plugins** — HTML/JS panels rendered live in the UI (3D, charts, colour pickers, anything)
- **Security sandbox** — 5-layer protection: AST whitelist → restricted builtins → subprocess isolation → resource limits → output screening
- **6 example plugins** — Calculator, Word Analyser, Unit Converter, JSON Tools, Color Explorer, 3D Cube Viewer

#### UI
- **Full desktop-app UI** — sidebar navigation, mind card, status indicator
- **Offline mode banner** — clear indication when no AI model is connected, with one-click fix
- **Settings panel** — change any configuration without touching a file
- **Terminal panel** — run allowlisted system commands from the UI
- **Plugin manager** — install, preview, enable/disable, remove plugins from the UI
- **Approval queue** — review and approve Myco's self-improvement proposals

#### Security
- **Token-based auth** — three roles (parent/user/readonly), PBKDF2-hashed
- **Prompt injection detection** — 12 pattern-based rules block known attack vectors
- **Tamper-evident audit log** — SHA-256 hash chain, every security event recorded
- **Mind snapshots** — take a snapshot before risky changes; roll back any time
- **Rate limiting** — per-token sliding-window rate limits

#### Infrastructure
- **Docker support** — Dockerfile + docker-compose with security hardening
- **Background scheduler** — nightly memory consolidation, growth heartbeat, audit integrity checks
- **Persistent knowledge graph** — JSON-backed, survives restarts, bounded at 2,000 nodes
- **Tiered semantic memory** — auto-selects TF-IDF (2MB RAM) or ChromaDB based on hardware

### Minimum requirements
- Python 3.12+
- 2 GB RAM (offline mode only)
- 3 GB RAM (with Ollama `qwen2.5:1.5b`)

---

## How to update

When a new version is released:

```bash
git pull origin main
pip install -r requirements.txt
python -m api.main
```

Your data in `data/` is preserved between updates. Take a snapshot first just in case:
```
Settings → Memory & Storage → Take snapshot
```
