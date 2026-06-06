# API Reference

Myco exposes a REST API at `http://localhost:8000`. All endpoints except `/health` require a Bearer token.

---

## Authentication

```bash
# Add to every request
-H "Authorization: Bearer YOUR_TOKEN"
```

Three token roles:

| Role | What it can do |
|---|---|
| `readonly` | Read memory, health, sessions, graph |
| `user` | Chat, ingest, switch models, everything readonly can do |
| `parent` | Full admin — approve changes, rollback, manage tokens, everything |

Get your parent token from the startup output. Create user/readonly tokens in **Settings → Access Tokens**.

---

## System

### `GET /health`
No auth required. Returns current status.

```bash
curl http://localhost:8000/health
```
```json
{
  "status": "alive",
  "stage": "Sprout",
  "xp": 42,
  "model": "qwen2.5:1.5b",
  "offline": false,
  "mode": "online"
}
```

---

### `GET /status`
Requires: `readonly`

Full system status including model health.

```bash
curl http://localhost:8000/status \
  -H "Authorization: Bearer TOKEN"
```
```json
{
  "online": true,
  "mode": "online",
  "offline_message": "",
  "memory_backend": "TFIDFMemory",
  "memory_count": 247,
  "graph_nodes": 89,
  "stage": "Sprout",
  "xp": 42,
  "tools": ["calculator", "current_time", "web_search"],
  "plugins": 3,
  "python": "3.12.3"
}
```

---

### `GET /mind`
Requires: `readonly`

Full mind state.

```bash
curl http://localhost:8000/mind \
  -H "Authorization: Bearer TOKEN"
```
```json
{
  "stage": "Sprout",
  "xp": 42,
  "current_model": "ollama/qwen2.5:1.5b",
  "total_interactions": 15,
  "personality_traits": {"curious": true},
  "memory_count": 247,
  "graph_stats": {"nodes": 89, "edges": 134},
  "tools": ["calculator", "current_time"]
}
```

---

## Chat

### `POST /chat`
Requires: `user`  
Response: `text/event-stream` (SSE)

Send a message and receive a streamed response.

```bash
curl -N -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "What do you know about Python?"}'
```

SSE events:
```
data: {"token": "Python"}
data: {"token": " is"}
data: {"token": " a high-level..."}
data: {"done": true, "stage": "Sprout", "xp": 45}
```

**Request body:**
```json
{
  "message": "Your message here",
  "session_id": "optional-session-id",
  "media": [
    {"type": "image", "data": "data:image/jpeg;base64,..."}
  ]
}
```

**JavaScript example:**
```javascript
const response = await fetch('http://localhost:8000/chat', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer TOKEN',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ message: 'Hello Myco!' })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  const text = decoder.decode(value);
  for (const line of text.split('\n')) {
    if (line.startsWith('data: ')) {
      const data = JSON.parse(line.slice(6));
      if (data.token) process.stdout.write(data.token);
    }
  }
}
```

---

## Memory

### `POST /ingest`
Requires: `user`

Teach Myco from content.

```bash
curl -X POST http://localhost:8000/ingest \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "The speed of light is 299,792,458 metres per second.",
    "source_type": "text",
    "source_label": "physics facts"
  }'
```

**`source_type` values:** `text`, `document`, `image`, `video`, `url`

**Response:**
```json
{
  "reaction": "Oh! I learned about light speed!",
  "memories": [
    {"type": "fact", "content": "Speed of light is 299,792,458 m/s", "confidence": 3}
  ],
  "summary": "A physics fact about the speed of light.",
  "xp": 55,
  "stage": "Sprout"
}
```

---

### `GET /memory`
Requires: `readonly`

Search semantic memory.

```bash
# Search by query
curl "http://localhost:8000/memory?q=speed+of+light&limit=5" \
  -H "Authorization: Bearer TOKEN"

# Get recent memories
curl "http://localhost:8000/memory?limit=20" \
  -H "Authorization: Bearer TOKEN"
```

**Response:**
```json
{
  "results": [
    {
      "content": "Speed of light is 299,792,458 m/s",
      "metadata": {
        "type": "fact",
        "source": "text",
        "label": "physics facts",
        "confidence": "3"
      },
      "score": 0.847
    }
  ],
  "total": 247
}
```

---

### `GET /episodes`
Requires: `readonly`

Get recent conversation history.

```bash
curl "http://localhost:8000/episodes?n=10" \
  -H "Authorization: Bearer TOKEN"
```

---

### `GET /sessions`
Requires: `readonly`

List conversation sessions.

```bash
curl http://localhost:8000/sessions \
  -H "Authorization: Bearer TOKEN"
```

---

### `GET /graph`
Requires: `readonly`

Knowledge graph statistics and most-connected concepts.

```bash
curl http://localhost:8000/graph \
  -H "Authorization: Bearer TOKEN"
```
```json
{
  "stats": {"nodes": 89, "edges": 134},
  "most_connected": [
    ["Python", 12],
    ["AI", 9],
    ["Myco", 8]
  ]
}
```

---

## Models

### `GET /models`
Requires: `readonly`

List all configured model tiers.

```bash
curl http://localhost:8000/models \
  -H "Authorization: Bearer TOKEN"
```

---

### `POST /models/add`
Requires: `parent`

Register a new model at runtime (no restart).

```bash
curl -X POST http://localhost:8000/models/add \
  -H "Authorization: Bearer PARENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "anthropic",
    "model": "claude-opus-4-5",
    "api_key": "sk-ant-...",
    "tier": "tier_powerful"
  }'
```

**Request body:**
- `provider`: `anthropic` | `openai` | `google` | `mistral` | `cohere` | `ollama` | `custom`
- `model`: model name string
- `api_key`: optional API key (can be set via env var instead)
- `endpoint`: optional custom server URL
- `tier`: `tier_powerful` | `tier_balanced` | `tier_fast` | `tier_local`

---

### `POST /models/switch`
Requires: `user`

Switch the active model immediately.

```bash
curl -X POST http://localhost:8000/models/switch \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model": "ollama/llama3.2:3b"}'
```

---

## Self-improvement

### `POST /reflect`
Requires: `parent`

Manually trigger the self-improvement and reflection cycle.

```bash
curl -X POST http://localhost:8000/reflect \
  -H "Authorization: Bearer PARENT_TOKEN"
```

---

### `GET /self-improve/pending`
Requires: `parent`

View changes waiting for your approval.

```bash
curl http://localhost:8000/self-improve/pending \
  -H "Authorization: Bearer PARENT_TOKEN"
```
```json
{
  "pending": [
    {
      "plan_id": "abc12345",
      "action_type": "new_tool",
      "description": "Create a palindrome checker function",
      "sandbox_verdict": "accepted",
      "created_at": 1717200000.0
    }
  ]
}
```

---

### `POST /self-improve/approve/{plan_id}`
Requires: `parent`

Approve a pending change. It will be integrated into Myco.

```bash
curl -X POST http://localhost:8000/self-improve/approve/abc12345 \
  -H "Authorization: Bearer PARENT_TOKEN"
```

---

### `POST /self-improve/reject/{plan_id}`
Requires: `parent`

Reject a pending change.

```bash
curl -X POST http://localhost:8000/self-improve/reject/abc12345 \
  -H "Authorization: Bearer PARENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Not needed right now"}'
```

---

### `POST /self-improve/toggle`
Requires: `parent`

Enable or disable the self-improvement engine.

```bash
curl -X POST http://localhost:8000/self-improve/toggle \
  -H "Authorization: Bearer PARENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

---

### `GET /growth/history`
Requires: `readonly`

History of all improvement actions taken.

```bash
curl http://localhost:8000/growth/history \
  -H "Authorization: Bearer TOKEN"
```

---

## Autonomous Learning

### `GET /learner/stats`
Requires: `readonly`

```bash
curl http://localhost:8000/learner/stats \
  -H "Authorization: Bearer TOKEN"
```
```json
{
  "queued": 2,
  "resolved": 14,
  "recent": [
    {"topic": "Python decorators", "memories": 5, "source": "uncertainty_response"}
  ]
}
```

---

### `POST /learner/queue`
Requires: `user`

Queue a topic for Myco to research in the background.

```bash
curl -X POST http://localhost:8000/learner/queue \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "quantum computing",
    "query": "quantum computing basics introduction tutorial"
  }'
```

---

## Plugins

### `GET /plugins`
Requires: `readonly`

```bash
curl http://localhost:8000/plugins \
  -H "Authorization: Bearer TOKEN"
```

---

### `POST /plugins/install`
Requires: `parent`

Install a plugin from Python code.

```bash
curl -X POST http://localhost:8000/plugins/install \
  -H "Authorization: Bearer PARENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Word Counter",
    "description": "Count words in text",
    "plugin_type": "tool",
    "icon": "📊",
    "code": "def count_words(text: str) -> str:\n    return str(len(text.split()))"
  }'
```

**Response:**
```json
{
  "ok": true,
  "plugin_id": "abc123def456",
  "manifest": {
    "name": "Word Counter",
    "plugin_type": "tool",
    "tools": ["abc123def456_count_words"],
    "ui_slot": false
  }
}
```

---

### `DELETE /plugins/{plugin_id}`
Requires: `parent`

Remove an installed plugin.

```bash
curl -X DELETE http://localhost:8000/plugins/abc123def456 \
  -H "Authorization: Bearer PARENT_TOKEN"
```

---

### `POST /plugins/{plugin_id}/toggle`
Requires: `parent`

Enable or disable without removing.

```bash
curl -X POST http://localhost:8000/plugins/abc123def456/toggle \
  -H "Authorization: Bearer PARENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

---

### `GET /plugins/{plugin_id}/widget`
Requires: `readonly`

Returns the HTML widget for a viewer plugin (used by the UI to render iframes).

```bash
curl http://localhost:8000/plugins/abc123def456/widget \
  -H "Authorization: Bearer TOKEN"
```

---

## Merge (GitHub / URL)

### `POST /merge/preview`
Requires: `parent`

Preview what a GitHub URL or code would add — **does not install anything**.

```bash
curl -X POST http://localhost:8000/merge/preview \
  -H "Authorization: Bearer PARENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/user/repo/blob/main/tool.py", "name": "My Tool"}'
```
```json
{
  "name": "tool",
  "preview": {
    "functions": ["process", "validate"],
    "imports": ["re", "json"],
    "safe_deps": [],
    "unsafe_deps": ["re"],
    "has_ui_widget": false,
    "violations": ["Banned node Import at line 1"],
    "safe_to_install": false,
    "lines": 45
  }
}
```

---

### `POST /merge/apply`
Requires: `parent`

Fetch from GitHub and install as a plugin.

```bash
curl -X POST http://localhost:8000/merge/apply \
  -H "Authorization: Bearer PARENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://github.com/user/repo/blob/main/tool.py",
    "name": "My Tool",
    "description": "Does something useful",
    "install_deps": true
  }'
```

---

### `POST /merge/install-deps`
Requires: `parent`

Install safe pip packages for a plugin (from whitelist only).

```bash
curl -X POST http://localhost:8000/merge/install-deps \
  -H "Authorization: Bearer PARENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"packages": ["numpy", "pandas"]}'
```
```json
{
  "installed": ["numpy", "pandas"],
  "skipped": [],
  "errors": []
}
```

---

## Snapshots & Rollback

### `POST /snapshot`
Requires: `parent`

Take a mind state snapshot (before risky changes).

```bash
curl -X POST http://localhost:8000/snapshot \
  -H "Authorization: Bearer PARENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"label": "before-experiment", "reason": "testing new plugin"}'
```

---

### `GET /snapshots`
Requires: `parent`

List available snapshots.

---

### `POST /rollback/{snapshot_id}`
Requires: `parent`

Roll back to a previous mind state.

```bash
curl -X POST http://localhost:8000/rollback/SNAPSHOT_ID \
  -H "Authorization: Bearer PARENT_TOKEN"
```

---

## Settings

### `GET /settings`
Requires: `readonly`

Read current configuration (API keys are masked).

---

### `POST /settings/update`
Requires: `parent`

Update a configuration value using dot-path notation.

```bash
curl -X POST http://localhost:8000/settings/update \
  -H "Authorization: Bearer PARENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "generation.max_tokens", "value": "512"}'
```

**Examples:**
- `"generation.max_tokens"` → `"256"`
- `"safety.self_improve_enabled"` → `"false"`
- `"models.prefer_local"` → `"true"`

---

## Terminal

### `GET /terminal/run`
Requires: `parent`

Run an allowlisted system command.

```bash
curl "http://localhost:8000/terminal/run?cmd=ollama+list" \
  -H "Authorization: Bearer PARENT_TOKEN"
```
```json
{
  "stdout": "NAME              ID              SIZE\nqwen2.5:1.5b    abc123          986 MB",
  "stderr": "",
  "returncode": 0
}
```

**Allowed commands:**
- `ollama list` — list installed models
- `ollama ps` — show running models
- `ollama pull <model>` — download a model
- `python3 --version`
- `pip list`
- `pip show <package>`
- `df -h` — disk space
- `free -h` — memory usage
- `uptime`

---

## Audit

### `GET /audit`
Requires: `parent`

View the security audit log.

```bash
curl "http://localhost:8000/audit?n=50&category=THREAT" \
  -H "Authorization: Bearer PARENT_TOKEN"
```

**Category filter options:** `AUTH`, `SANDBOX`, `CHANGE`, `INGEST`, `API`, `THREAT`

---

### `GET /audit/verify`
Requires: `parent`

Verify the audit log hash chain has not been tampered with.

```bash
curl http://localhost:8000/audit/verify \
  -H "Authorization: Bearer PARENT_TOKEN"
```
```json
{"valid": true, "message": "OK"}
```

---

## Token Management

### `POST /tokens/create`
Requires: `parent`

Create a new access token.

```bash
curl -X POST http://localhost:8000/tokens/create \
  -H "Authorization: Bearer PARENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"role": "user", "label": "my-phone", "ttl_days": 30}'
```
```json
{
  "token": "the-raw-token-shown-once-save-it",
  "warning": "Save this token — it will not be shown again."
}
```

**`role` options:** `readonly`, `user`, `parent`  
**`ttl_days`:** optional expiry (null = never expires)

---

### `GET /tokens`
Requires: `parent`

List all tokens (IDs only, never raw values).

---

### `DELETE /tokens/{token_id}`
Requires: `parent`

Revoke a token immediately.

```bash
curl -X DELETE http://localhost:8000/tokens/abc12345 \
  -H "Authorization: Bearer PARENT_TOKEN"
```
