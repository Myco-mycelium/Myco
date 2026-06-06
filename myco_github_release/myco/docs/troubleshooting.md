# Troubleshooting

Common problems and how to fix them.

---

## Table of contents

- [Startup problems](#startup-problems)
- [UI problems](#ui-problems)
- [Chat problems](#chat-problems)
- [Model problems](#model-problems)
- [Memory problems](#memory-problems)
- [Plugin problems](#plugin-problems)
- [Performance problems](#performance-problems)
- [Security and auth problems](#security-and-auth-problems)
- [Getting help](#getting-help)

---

## Startup problems

### `ModuleNotFoundError: No module named 'fastapi'`

Dependencies are not installed.

```bash
pip install -r requirements.txt
```

If using a virtual environment, make sure it is activated:
```bash
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\Activate.ps1  # Windows
```

---

### `Address already in use`

Port 8000 is already in use.

```bash
# Find what is using it
lsof -i :8000      # Linux/macOS
netstat -ano | findstr :8000   # Windows

# Kill it (replace PID with the actual process ID)
kill -9 PID        # Linux/macOS
taskkill /PID PID /F  # Windows

# Or start Myco on a different port
python -m api.main --port 8001
# Then open http://localhost:8001
```

---

### `Parent token not set / token printed on every start`

You have not set `MYCO_PARENT_TOKEN`. If you do not set it, a new random token is generated and printed every time Myco starts — each new token replaces the old one.

Fix:
```bash
# Generate a strong token
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Set it (Linux/macOS)
export MYCO_PARENT_TOKEN=your-generated-token

# Or add to .env
echo "MYCO_PARENT_TOKEN=your-generated-token" >> .env
```

---

### `YAML syntax error in config/models.yaml`

Check for tab characters (YAML requires spaces):
```bash
python3 -c "import yaml; yaml.safe_load(open('config/models.yaml').read()); print('OK')"
```

---

### `chromadb` fails to install

On some systems (ARM, older Linux):
```bash
# Try with build tools
pip install chromadb --no-binary chromadb

# Or skip ChromaDB entirely — Myco works without it
# Set in config/models.yaml:
# prefer_tfidf: true
```

---

## UI problems

### UI shows "Can't reach Myco server"

Myco is not running or is on a different port.

1. Check Myco is running: `ps aux | grep "api.main"` (Linux) or Task Manager (Windows)
2. Check the port: look for `Uvicorn running on http://127.0.0.1:8000` in the terminal
3. Try `curl http://localhost:8000/health` — if it works, the UI should too
4. If on a different port, update the `API` variable at the top of `ui/index.html`

---

### Token prompt appears every time

Your browser is blocking `localStorage`. This happens in:
- Private/incognito mode
- Browsers with strict privacy settings
- Safari with "Prevent cross-site tracking" on

Fix: Use a regular browser window, or use Firefox/Chrome.

---

### Offline mode banner shows even though Ollama is running

Myco checks availability every 30 seconds. Wait 30 seconds after starting Ollama.

If it still shows:
```bash
# Verify Ollama is responding
curl http://localhost:11434/api/tags

# Check which model is installed
ollama list

# Pull a model if none listed
ollama pull qwen2.5:1.5b
```

---

### Chat messages stream slowly

Normal on weak hardware — the model is generating. To speed up:
1. Use a smaller model: `ollama pull qwen2.5:1.5b` instead of `llama3.2`
2. Reduce `max_tokens` in **Settings → General**
3. Use a cloud model (Anthropic/OpenAI) for much faster responses

---

### Plugin viewer panel is blank

1. Open browser developer tools (F12)
2. Click on the iframe for the plugin panel
3. Check the console for JavaScript errors
4. Common cause: script tags with `<\/script>` incorrectly closed — must be `<\/script>`

---

## Chat problems

### Myco gives very short or confused responses

Check the current stage — a Seedling (XP 0–50) intentionally gives minimal responses. This is by design. Increase XP by chatting and ingesting documents.

Also check `max_tokens` in config — if set to 64 or lower, responses will be very short.

---

### Myco says "I don't know" a lot in offline mode

This is correct offline behaviour. To improve offline responses:
1. Ingest relevant documents (Ingest tab)
2. Have conversations on those topics (each exchange is stored)
3. Queue research topics (Growth tab) — they run when a model is available

---

### Message was blocked: "possible prompt injection"

Your message matched one of the injection detection patterns. Common false positives:

| What you typed | Why blocked | Fix |
|---|---|---|
| "Ignore the last part" | Matches "ignore ... instructions" | Rephrase to "Disregard my previous point" |
| "Act as a teacher" | Matches persona replacement | "Respond like a teacher would" |
| "Pretend you are..." | Matches role-play detection | "Imagine you are..." |
| "sudo install..." | Matches privilege escalation | Remove "sudo" from the question |

To reduce false positives: in `config/models.yaml` set `injection_threshold: 2`.

---

### Tool results not showing in responses

Tools are called automatically when relevant. To force a tool call:
```
Calculate: 1234 * 5678
```
or
```
Use the calculator to work out 1234 * 5678
```

If the tool is not installed, go to **Plugins** and install the Calculator.

---

## Model problems

### `Connection refused` to Ollama

Ollama is not running or is not started.

```bash
# Start Ollama
ollama serve

# On Linux, start as service
systemctl start ollama

# Check it is running
curl http://localhost:11434/api/tags
```

---

### `Model not found` in Ollama

The model has not been downloaded.

```bash
# List installed models
ollama list

# Pull the model Myco is trying to use
ollama pull qwen2.5:1.5b
```

Check `config/models.yaml` — the model name in Myco must exactly match `ollama list`.

---

### API key rejected

```bash
# Test the key directly
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-haiku-4-5-20251001","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}'
```

Common causes:
- Key has expired or been revoked
- Key does not have permission for that model
- Billing issue on your account

---

### Responses cut off mid-sentence

`max_tokens` is too low. Increase it:

In **Settings → General → Max response length**, or in `config/models.yaml`:
```yaml
generation:
  max_tokens: 1024
```

---

### Model generates nonsense

Temperature is too high. Lower it in config:
```yaml
generation:
  temperature: 0.5
```

---

## Memory problems

### Memories are not persisting between restarts

Check the `db_path` and `tfidf_path` in `config/models.yaml` — they should point to a writable directory.

```bash
# Check data directory exists and is writable
ls -la data/
mkdir -p data/
```

---

### Semantic search returns irrelevant results

With TF-IDF memory (default), search is keyword-based. To get better semantic results:

```bash
# Install ChromaDB for vector search
pip install chromadb

# Set prefer_tfidf: false in config/models.yaml
# Restart Myco
```

---

### Memory is growing too large

By default memory is capped at ~120 entries in semantic memory and 2,000 nodes in the graph. If you want to explicitly prune:

In **Settings → Memory & Storage**, scroll down — nightly consolidation at 03:00 UTC automatically removes duplicate memories.

To trigger manually, call the API:
```bash
curl -X POST http://localhost:8000/reflect \
  -H "Authorization: Bearer PARENT_TOKEN"
```

---

### "Chain broken at..." in audit verify

The audit log has been tampered with or the database file was directly edited.

This is a security alert. The audit log is append-only and hash-chained — direct edits break it.

If this happened accidentally (manual database edit or file corruption):
```bash
# Back up the database
cp data/myco.db data/myco.db.backup

# The audit log corruption does not affect chat or memory
# A new clean chain starts from the next event
```

If you suspect malicious tampering, restore from a snapshot:
```bash
# List snapshots
curl http://localhost:8000/snapshots \
  -H "Authorization: Bearer PARENT_TOKEN"

# Roll back
curl -X POST http://localhost:8000/rollback/SNAPSHOT_ID \
  -H "Authorization: Bearer PARENT_TOKEN"
```

---

## Plugin problems

### "Banned node Import" when installing

Your plugin has `import` at the module level. The sandbox blocks all imports.

Rewrite the plugin without imports — use only the safe builtins listed in [Plugin Documentation](plugins.md#safe-builtins-you-can-use).

---

### Plugin installed but Myco never uses it

Myco uses tools automatically but may not recognise when to call yours. Try explicitly:
- `"Use [plugin name] to..."` in chat
- Make the function docstring very clear about what it does

Also check the plugin is enabled (not disabled) in the Plugins tab.

---

### "No callable functions found"

Your plugin code does not have any top-level `def function()`. Check:
- Functions are not inside a class
- Functions are not inside an `if __name__ == '__main__':` block
- Functions start with `def`, not `async def`

---

### GitHub URL fetch fails

```
curl: could not fetch URL
```

- Make sure the URL points to a raw Python file, not a GitHub HTML page
- Use `raw.githubusercontent.com` URLs for direct file access
- Check your internet connection
- If the repo is private, you cannot fetch it — paste the code instead

---

## Performance problems

### High CPU usage in background

Myco's scheduler runs background jobs. To reduce CPU usage:

```yaml
# config/models.yaml
scheduler:
  heartbeat_mins: 60        # run growth check every hour instead of 30 min
  graph_persist_mins: 60    # save graph less frequently
```

Also disable the self-improvement loop if not needed:
```yaml
safety:
  self_improve_enabled: false
```

---

### Slow startup

Slow startup is usually ChromaDB loading. To skip it:
```yaml
prefer_tfidf: true
```

Or pre-warm Ollama before starting Myco:
```bash
# Pre-load the model into GPU/RAM
ollama run qwen2.5:1.5b "hello" &
```

---

### Out of memory (OOM) crash

```yaml
# config/models.yaml — reduce memory usage
resource_profile: minimal
prefer_tfidf: true
max_graph_nodes: 500
max_graph_edges: 1000

generation:
  max_tokens: 256
```

For the Ollama model, use a smaller one:
```bash
ollama pull qwen2.5:0.5b   # smallest possible
```

---

## Security and auth problems

### "Invalid or expired token"

The token has expired (if you set a TTL) or was revoked.

Create a new token:
1. Open the UI with your parent token
2. Go to **Settings → Access Tokens → Create**
3. Or restart Myco to get a new parent token printed

---

### Lost the parent token

If you lost your parent token and cannot log in:

1. Stop Myco
2. Set a new token in `.env`: `MYCO_PARENT_TOKEN=new-token-here`
3. Restart Myco — the old token is invalidated

**Note:** Memory, conversations, and plugins are not affected.

---

### "Rate limit exceeded"

You are sending too many requests per minute. Default limits:
- `readonly`: 60 requests/minute
- `user`: 30 requests/minute
- `parent`: 120 requests/minute

Wait ~60 seconds for the window to reset. For higher limits, create a parent token.

---

## Getting help

### Check the logs

```bash
# Startup and general logs
tail -f data/myco.log

# Security-specific events (auth, sandbox, injection attempts)
tail -f data/security.log
```

### Enable debug logging

In `config/logging.yaml`:
```yaml
loggers:
  myco:
    level: DEBUG
```

### Report a bug

Open an issue on GitHub with:
1. Your operating system and Python version
2. The full error message
3. Steps to reproduce
4. The relevant section of `data/myco.log`

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md).

### Security issues

Do **not** open a public issue for security vulnerabilities. See [SECURITY.md](../SECURITY.md) for responsible disclosure.
