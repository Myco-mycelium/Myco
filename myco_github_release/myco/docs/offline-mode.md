# Offline Mode

Myco works fully without any AI model — no Ollama, no API keys, no internet. This page explains what changes in offline mode and how to get the most out of it.

---

## What changes in offline mode

When no AI model is reachable, Myco switches to its **offline brain** automatically. You will see an amber banner at the top of the UI:

> 🌱 **Offline mode** — no AI model connected. Myco still works: memory, tools, and plugins all run. [Connect a model →]

| Capability | Online | Offline |
|---|---|---|
| Generative AI responses | ✅ Full | ⚠ Memory + rules |
| Document ingestion | ✅ LLM extracts key facts | ✅ Sentence-splitting |
| Tools (calculator, converter…) | ✅ | ✅ |
| Plugins (3D viewer, charts…) | ✅ | ✅ |
| Memory search | ✅ | ✅ |
| Knowledge graph growth | ✅ | ✅ |
| XP and stage progression | ✅ | ✅ |
| Web search tool | ✅ | ✅ (still works) |
| Self-improvement loop | ✅ | ❌ Requires LLM |
| Autonomous gap research | ✅ | ❌ Requires LLM |

Offline mode is not a degraded experience — it is a different mode. The more you teach Myco (by ingesting documents and chatting), the better the offline responses become.

---

## How the offline brain works

The offline brain uses three layers in order:

### 1. Intent detection

Myco recognises common intents from your message:

| What you say | What happens |
|---|---|
| "hello", "hi", "hey" | Stage-appropriate greeting |
| "what can you do?" | Lists capabilities |
| "calculate 15 * 24" | Runs the Calculator tool |
| "convert 5 km to miles" | Runs the Unit Converter tool |
| "what time is it?" | Returns current time |
| "tell me a joke" | Returns a joke |
| "what do you know about X?" | Searches memory |
| "who are you?" | Explains Myco and current stage |
| "what stage are you?" | Shows XP, stage, memory count |
| "remember what I said about X" | Searches episodic memory |

### 2. Memory retrieval

If no intent matches, Myco searches its semantic memory (TF-IDF or ChromaDB) for the most relevant stored knowledge. The more you have taught Myco — through conversations and document ingestion — the better these answers are.

For example, if you ingested a Wikipedia article about photosynthesis and then ask "how do plants make food?", Myco retrieves the most relevant sentences and presents them.

### 3. Fallback

If memory has nothing relevant, Myco gives an honest uncertainty response and encourages you to ingest relevant material. At low memory counts (under 10 memories), it specifically tells you what to do.

---

## Offline document ingestion

When you drop a document in offline mode, Myco cannot use an LLM to extract key concepts. Instead it uses **sentence splitting**:

1. Splits the text at sentence boundaries (`.`, `!`, `?`)
2. Filters out sentences shorter than 20 characters
3. Stores each sentence as a memory with `confidence: 2`
4. Extracts entities and adds them to the knowledge graph
5. Awards XP for each sentence stored

This is less intelligent than LLM extraction — it stores more raw sentences rather than distilled concepts — but it is effective. A 1,000-word article might produce 50–80 memories that Myco can search over.

**Tip:** Ingest clean, factual text in offline mode. Well-written Wikipedia articles, how-to guides, and reference documents work well.

---

## Getting the most from offline mode

### Build up memory first

The more memories Myco has, the better its offline responses. Before going fully offline:

1. **Ingest your key documents** — anything you want Myco to know
2. **Have some conversations online** — Myco stores everything
3. **Queue research topics** — go to **Growth → Queue a learning topic** while online

### Use tools

All built-in tools work offline:
- `calculate 500 * 1.08` — math
- `convert 37 celsius to fahrenheit` — unit conversion
- `what time is it?` — current time
- `format this JSON: {"key": "value"}` — if JSON Tools plugin is installed

### Teach Myco facts directly

In the chat:
```
Remember that: The Python GIL is the Global Interpreter Lock. It prevents multiple threads from executing Python bytecodes at once.
```

Or use the Ingest tab to paste text directly — it works offline and stores everything.

### Stage matters in offline mode

The offline brain adapts to Myco's growth stage. A Seedling gives very short, simple responses. An Ancient gives longer, more nuanced answers. Growing Myco (by interacting and ingesting) improves offline responses even without a model.

---

## Enabling a model later

When you are ready to add an AI model, the transition is seamless:

1. Start Ollama: `ollama serve`
2. Pull a model: `ollama pull qwen2.5:1.5b`
3. The amber banner disappears automatically within 30 seconds
4. All memories collected in offline mode are immediately available to the LLM

No data is lost and no restart is needed.

---

## Minimum hardware for offline mode

| Component | Minimum |
|---|---|
| RAM | 512 MB |
| Disk | 200 MB (for the database + TF-IDF index) |
| CPU | Any (single-core 1 GHz works) |
| Network | None required |
| Python | 3.12+ |

Offline mode uses:
- FastAPI (~15 MB RAM)
- TF-IDF memory (~2 MB for 10,000 memories)
- Knowledge graph (~8 MB for 2,000 nodes)
- SQLite episodic store (~5 MB for 10,000 messages)

Total: **~30 MB RAM** in pure offline mode with no ChromaDB.

---

## Detecting offline mode programmatically

```bash
# Check if online or offline
curl http://localhost:8000/health
# Returns: {"status":"alive","mode":"online"} or {"mode":"offline"}

# Get detailed status (requires token)
curl http://localhost:8000/status \
  -H "Authorization: Bearer YOUR_TOKEN"
# Returns offline_message with human-readable explanation
```

```javascript
// In JavaScript
const health = await fetch('http://localhost:8000/health').then(r => r.json());
if (health.offline) {
  console.log('Running in offline mode');
}
```
