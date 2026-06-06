# Quick Start Guide

Be productive with Myco in under 5 minutes.

---

## Step 1 — Start Myco

```bash
cd myco
source .venv/bin/activate   # or .venv\Scripts\Activate.ps1 on Windows
python -m api.main
```

You will see something like:
```
════════════════════════════════════════════════════════════
  MYCO PARENT TOKEN (save this — shown only once)
  abc123xyz789...
════════════════════════════════════════════════════════════
INFO: Myco starting up...
INFO: Started server process [12345]
INFO: Uvicorn running on http://127.0.0.1:8000
```

**Save that token.** You will need it every time you open the UI.

---

## Step 2 — Open the UI

Go to **http://localhost:8000** in your browser.

You will see a welcome screen asking for your token. Paste it in and click **Let's grow →**.

---

## Step 3 — Say hello

Click on the **Chat** tab (it should already be open). Type anything:

```
Hello! What can you do?
```

If you see an **orange banner** saying "offline mode", Myco has no AI model yet. It will still reply from memory and rules. To connect a model, go to [Step 4](#step-4--optional-connect-an-ai-model).

---

## Step 4 — Optional: connect an AI model

### Quickest option — Ollama (free, private, no account needed)

```bash
# In a separate terminal:
ollama pull qwen2.5:1.5b   # ~1 GB download, works on 4 GB RAM
```

Myco detects Ollama automatically within 30 seconds. The orange banner disappears.

### Cloud option

Click **Settings → AI Models** in the sidebar, choose your provider (Anthropic, OpenAI, Google…), and paste your API key.

---

## Step 5 — Teach Myco something

Click **Ingest** in the sidebar. You can:

- **Drop a file** — PDF, TXT, Markdown, CSV, JSON
- **Paste a URL** — Myco fetches and reads the page
- **Paste text** — anything you want Myco to remember

Try pasting this:
```
Paris is the capital of France. It has a population of about 2.1 million.
The Eiffel Tower was built in 1889 for the World's Fair.
```

Myco extracts memories and stores them. Now ask in chat:
```
What do you know about Paris?
```

---

## Step 6 — Install a plugin

Click **Plugins → Examples** in the sidebar. Find **Calculator** and click **Install →**.

Now ask in chat:
```
Calculate 1234 * 5678
```

Myco will use the Calculator plugin to compute the answer. Plugins permanently expand what Myco can do.

---

## Step 7 — Watch Myco grow

Check the mind card in the sidebar — it shows:
- **Stage** — starts at Seedling, grows to Ancient
- **XP** — earned from every interaction
- **Memories** — total knowledge stored
- **Concepts** — nodes in the knowledge graph

Every conversation, document, and plugin makes Myco smarter and moves it closer to the next stage.

---

## What to explore next

| Want to… | Go to… |
|---|---|
| Use a local AI model | [Installation → Adding an AI model](installation.md#adding-an-ai-model) |
| Tune performance for your hardware | [Configuration](configuration.md) |
| Add tools and visual panels | [Plugins](plugins.md) |
| Merge a GitHub project into Myco | [Plugins → Merging from GitHub](plugins.md#merging-from-github) |
| Use Myco without any internet | [Offline Mode](offline-mode.md) |
| Access Myco from another device | [API Reference](api-reference.md) |
| Run securely in production | [Security](security.md) |
| Something broke | [Troubleshooting](troubleshooting.md) |

---

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Enter` | Send chat message |
| `Shift+Enter` | New line in chat |
| Click any hint chip | Fill the chat input |

---

## The parent token

The parent token gives full admin access. Keep it safe:
- Never share it — it can read all memory, approve self-improvements, and roll back Myco's brain
- Store it in a password manager
- If you lose it, restart Myco — a new one is generated (the old one stops working)

To create a **limited user token** (chat only, no admin), go to **Settings → Access Tokens → Create**.
