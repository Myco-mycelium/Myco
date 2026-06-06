# Frequently Asked Questions

Can't find your answer here? Ask on [Discord](https://discord.gg/NTGWzPy4yB) or [open an issue](https://github.com/Myco-mycelium/myco/issues).

---

## General

### What is Myco?

Myco is a self-growing AI that runs on your computer. It starts knowing almost nothing, then learns from every conversation, every document you share, and every topic it researches. The more you use it, the smarter it gets.

Unlike a normal chatbot that forgets everything after each session, Myco remembers everything permanently. It stores knowledge in three layers: a conversation history, a searchable memory store, and a concept graph.

---

### Is this free to use?

Yes. Myco itself is MIT licensed and completely free. You can use it, modify it, and share it.

Running costs depend on how you use it:
- **With Ollama (local models):** completely free — runs on your hardware
- **With cloud APIs (Claude, GPT-4o, etc.):** you pay the API provider per token

For most personal use, Ollama is free and works great.

---

### Does it work without the internet?

Yes. In offline mode (no AI model), Myco uses its own memory to answer questions. Tools and plugins still work. Documents can still be ingested. Myco still grows.

The offline brain gets smarter the more you teach it — so even without any AI model, Myco improves over time. See [Offline Mode](offline-mode.md) for details.

---

### Is my data private?

Yes, if you use local models (Ollama). Everything stays on your machine:
- Conversations are in `data/myco.db` on your computer
- Memories are in `data/` on your computer
- Nothing is sent to any server

If you use cloud APIs (Anthropic, OpenAI, etc.), your messages go to their servers. Check their privacy policies.

---

### What hardware do I need?

| Setup | Minimum RAM | Works well with |
|---|---|---|
| Offline only | 512 MB | Any computer from 2010+ |
| With Ollama (tiny model) | 2 GB | Budget laptops, Raspberry Pi 4 |
| With Ollama (good model) | 4–6 GB | Most modern laptops |
| With cloud API | 1 GB | Any computer with internet |

---

### Does it work on Raspberry Pi?

Yes! Use offline mode or `ollama pull qwen2.5:0.5b` (the smallest model). Set `prefer_tfidf: true` in the config to skip ChromaDB. With a Pi 4 (4 GB) you can run a decent model.

---

### Can I use it on Windows?

Yes. See [Installation — Windows](installation.md#windows). Docker is also an option that avoids most Windows compatibility issues.

---

## AI Models

### What is Ollama?

Ollama is a free program that runs AI models on your own computer. No account, no internet required, no cost. Download from [ollama.com](https://ollama.com). It works on Windows, macOS, and Linux.

---

### Which model should I use?

| Your RAM | Recommended model | Quality |
|---|---|---|
| 2 GB | `tinyllama` or `qwen2.5:0.5b` | Basic but usable |
| 4 GB | `qwen2.5:1.5b` | Good |
| 6 GB | `llama3.2:3b` | Very good |
| 8 GB+ | `llama3.2` or `mistral` | Excellent |

For the best quality regardless of hardware, use Claude or GPT-4o with an API key.

---

### Can I switch models while it's running?

Yes. Go to **Settings → AI Models**, pick a new model, and click **Use this brain**. Takes effect on the next message — no restart.

---

### What if I have an API key for Claude/GPT-4o but no Ollama?

That works fine. Set the API key in **Settings → AI Models** or in `.env`. Myco will use the cloud model for all requests.

---

### What if I have neither Ollama nor an API key?

Myco runs in offline mode. It answers questions from its own memory, runs all tools and plugins, and learns from documents you share. You can connect a model later — all the memories you built up carry over instantly.

---

## Memory

### How long does Myco remember things?

Forever, unless you delete them. Everything is stored in a local SQLite database. Myco's memory persists across restarts, updates, and computer reboots.

---

### Can I delete specific memories?

Not yet through the UI — this is a planned feature. For now, you can:
- Take a snapshot **before** teaching Myco something, then roll back if needed
- Delete the entire `data/` folder to start fresh (this deletes everything)

---

### What is the knowledge graph?

The knowledge graph is a network of concepts Myco builds as it learns. When you talk about "Python" and "programming", Myco creates a connection between them. Over time this network grows and helps Myco make connections between ideas.

It is capped at 2,000 nodes by default to keep RAM usage low.

---

### Can I export my memories?

The raw data is in `data/myco.db` (SQLite) and `data/tfidf_memory.json`. You can open the SQLite file with any SQLite viewer (like [DB Browser for SQLite](https://sqlitebrowser.org/)).

A proper export feature is planned.

---

## Plugins

### What can plugins do?

- Add functions Myco can call during conversations (calculators, converters, formatters)
- Add visual panels to the UI (3D viewers, colour pickers, charts, dashboards, anything HTML/JS)
- Any Python code that passes the security sandbox

---

### Are plugins safe?

Every plugin goes through a 5-layer security sandbox before it runs:
1. AST analysis — rejects any imports, exec, eval, file access
2. Restricted builtins — only ~40 safe functions available
3. Subprocess isolation — runs in a separate OS process
4. Resource limits — 3 second timeout, 256 MB RAM, no network
5. Output screening — checks for leaked credentials or URLs

If a plugin fails any of these, it is rejected and never runs. See [Plugin Security](plugins.md#security-model).

---

### Can I install a plugin from GitHub?

Yes. In **Plugins → Add Plugin → GitHub URL**, paste:
- A direct file link: `https://github.com/user/repo/blob/main/tool.py`
- A repo URL: `https://github.com/user/repo` (Myco tries common filenames)

Myco fetches it, runs it through the sandbox, and installs if safe.

---

### My plugin was rejected — what does "Banned node Import" mean?

Your Python code has `import something` at the top level. The sandbox blocks all imports for security. Rewrite the plugin to not use any imports — use only the built-in Python functions listed in [Plugin Documentation](plugins.md#safe-builtins-you-can-use).

---

## Self-improvement

### Is it safe for Myco to modify itself?

Yes, with the built-in safeguards:
1. All generated code passes the full security sandbox
2. Code changes go into an approval queue — **you must approve them first**
3. A snapshot of Myco's brain is taken before any change
4. Any integration error triggers automatic rollback

You are always in control. Nothing changes without your explicit approval.

---

### How do I turn off self-improvement?

**Settings → General → Self-improvement → OFF**, or in config:
```yaml
safety:
  self_improve_enabled: false
```

---

### What is the approval queue?

When Myco generates a self-improvement plan (a new tool, a knowledge update), it goes into a queue. You see a notification in **Growth → Pending Approvals**. You can read exactly what the change is, see that it passed the sandbox, and then approve or reject it.

Nothing is ever applied without you clicking Approve.

---

## Troubleshooting

### The UI says "Can't reach Myco server"

Myco is not running. Open a terminal and run:
```bash
python -m api.main
```

Then refresh the page.

---

### I lost my parent token

Stop Myco, add `MYCO_PARENT_TOKEN=new-token` to your `.env` file, and restart. Your memories and conversations are safe — only the token changes.

---

### Myco is very slow

Try a smaller model. In **Settings → AI Models**, switch to `qwen2.5:1.5b` or `tinyllama`. Also reduce **Max response length** in **Settings → General** to 256 tokens.

---

### Something else is broken

Check [Troubleshooting](troubleshooting.md) for a full list of fixes. If your problem is not there, ask on [Discord](https://discord.gg/NTGWzPy4yB) or [open an issue](https://github.com/Myco-mycelium/myco/issues).
