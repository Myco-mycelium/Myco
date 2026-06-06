# Security

Myco is designed to be safe by default. This page explains the security model, what protections are in place, and how to report vulnerabilities.

---

## Security philosophy

Myco runs locally on your machine. Your conversations, memories, and documents never leave your computer unless you explicitly use a cloud AI provider. The security system is designed around one principle: **Myco should never be able to harm your system, even if something goes wrong.**

---

## The sandbox

Every piece of code that Myco generates or that gets installed as a plugin passes through a 5-layer security sandbox before it ever runs:

### Layer 1 — Static analysis (AST whitelist)
Before execution, Myco walks the Python AST (abstract syntax tree) of every code snippet. Any of these patterns causes immediate rejection:
- `import` statements at module level
- `from X import Y` statements
- Access to dunder attributes (`__class__`, `__bases__`, `__subclasses__`)
- `exec()`, `eval()`, `compile()`
- Known dangerous string patterns (`/etc/passwd`, `subprocess`, `socket`, etc.)

### Layer 2 — Restricted builtins
Code runs with only ~40 safe builtins available — no file access, no network, no process spawning.

### Layer 3 — Subprocess isolation
Code runs in a **separate OS process**, not in Myco's main process. This is the critical layer — even if code bypasses the AST check, it cannot access Myco's memory, files, or secrets.

### Layer 4 — Resource limits (Linux)
The subprocess has hard OS-level limits:
- 3 second wall-clock timeout
- 2 second CPU time
- 256 MB RAM
- 4 open file descriptors
- No child process creation

### Layer 5 — Output screening
Even if code passes all other checks, its output is scanned for signs of data exfiltration: URLs, SSH keys, `/etc/` paths, credential patterns.

---

## Authentication and authorisation

Myco uses token-based authentication with three roles:

| Role | Can do |
|---|---|
| `readonly` | Read memory, view history, check status |
| `user` | Chat, ingest documents, switch models |
| `parent` | Everything — approve changes, rollback, manage tokens |

Tokens are hashed with **PBKDF2-HMAC-SHA256 with 100,000 iterations** and a per-token salt. Even if the token store is leaked, raw tokens cannot be recovered.

---

## Prompt injection protection

Every message you send is scanned for prompt injection patterns before reaching the AI model. Blocked patterns include:
- "Ignore all previous instructions"
- "You are now [different persona]"
- "Forget your training"
- DAN / jailbreak keywords
- System prompt extraction attempts
- Privilege escalation language (`sudo`, `as root`)

Detected attacks are logged to the security audit log and blocked with a `400` response.

---

## Audit log

Every security-relevant event is recorded in an **append-only, hash-chained audit log**:

- Authentication attempts (success and failure)
- Sandbox verdicts (accepted/rejected/timeout)
- Self-improvement changes (approved/rejected/rolled back)
- Document ingestion events
- Admin API calls
- Detected threats

The hash chain means: if anyone modifies a past entry, all subsequent hashes become invalid and `GET /audit/verify` will detect it.

---

## Self-improvement safety

Myco's self-improvement loop has multiple safeguards:

1. **Master kill-switch** — disable it entirely: Settings → General → Self-improvement OFF
2. **Sandbox gate** — all generated code passes the full sandbox before queuing
3. **Parent approval** — code changes sit in a queue; you must explicitly approve them
4. **Pre-change snapshot** — a mind snapshot is taken before every integration
5. **Automatic rollback** — if integration raises any exception, it rolls back instantly

---

## Data privacy

- All data is stored locally in `data/myco.db` and `data/` directory
- Nothing is sent to any server unless you configure a cloud AI provider
- When using cloud providers (Anthropic, OpenAI, etc.), your messages go to their APIs — check their privacy policies
- API keys are stored only in your `.env` file or browser localStorage (UI) — never in the database

---

## Responsible disclosure

If you find a security vulnerability in Myco, please **do not open a public GitHub issue**.

Contact us privately:
- **Discord (private message):** [discord.gg/NTGWzPy4yB](https://discord.gg/NTGWzPy4yB) — DM a maintainer directly
- **GitHub Security Advisory:** [Open a private advisory](https://github.com/Myco-mycelium/myco/security/advisories/new)
- Include: description, reproduction steps, potential impact
- Allow 90 days for a fix before public disclosure

We take all reports seriously. Researchers who report valid vulnerabilities will be credited in the changelog.

---

## Known limitations

| Limitation | Impact | Mitigation |
|---|---|---|
| OS-level resource limits (RLIMIT) only work on Linux | On macOS/Windows, the sandbox still runs in a subprocess with a timeout, but RAM/CPU limits are not enforced at the OS level | Run in Docker on non-Linux systems |
| Token store is in-memory | Tokens are lost on restart | Set `MYCO_PARENT_TOKEN` in `.env` for persistence |
| TF-IDF memory is not encrypted | Memory is stored as plaintext JSON | Use full-disk encryption on your machine |
| Plugin iframes use `sandbox="allow-scripts"` | Plugins can run arbitrary JavaScript in their iframe | Plugins cannot access the parent page or Myco's API |

---

## Production hardening checklist

Before exposing Myco to the internet:

- [ ] Set a strong `MYCO_PARENT_TOKEN` in `.env`
- [ ] Set `MYCO_CORS_ORIGINS` to your exact domain (not `*`)
- [ ] Run behind nginx/Caddy with TLS — never expose port 8000 directly
- [ ] Run in Docker with `--read-only --no-new-privileges --cap-drop ALL`
- [ ] Create `user` role tokens for users — keep `parent` token offline
- [ ] Set `self_improve_enabled: false` until you understand the approval workflow
- [ ] Enable log rotation and monitor `data/security.log`
- [ ] Schedule regular `GET /audit/verify` checks
