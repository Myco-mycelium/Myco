"""
myco/api/main.py  (security-hardened)
FastAPI backend with auth, rate limiting, injection screening, and audit logging.
"""
from __future__ import annotations
import asyncio, json, logging, logging.config, os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import yaml
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from core.agent import MycoBrain
from core.scheduler import MycoClock
from safety.audit import AuditLog
from safety.auth import (Role, Token, detect_injection, require_auth,
                          get_token_store, get_rate_limiter)

# ── logging setup ──────────────────────────────────────────────────────────────

def _setup_logging():
    log_cfg = Path("config/logging.yaml")
    if log_cfg.exists():
        with open(log_cfg) as f:
            cfg = yaml.safe_load(f)
        Path("data").mkdir(exist_ok=True)
        try:
            logging.config.dictConfig(cfg)
        except Exception:
            logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(
            level=os.getenv("MYCO_LOG_LEVEL", "INFO"),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )

_setup_logging()
log = logging.getLogger("myco.api")

app = FastAPI(title="Myco", version="2.0.0", docs_url=None, redoc_url=None)
_ALLOWED_ORIGINS = os.getenv("MYCO_CORS_ORIGINS","http://localhost:3000,http://localhost:5173").split(",")
app.add_middleware(CORSMiddleware, allow_origins=_ALLOWED_ORIGINS,
                   allow_methods=["GET","POST","DELETE"],
                   allow_headers=["Authorization","Content-Type","X-Request-ID"], allow_credentials=False)

# ── request ID middleware ─────────────────────────────────────────────────────
import uuid as _uuid
from starlette.middleware.base import BaseHTTPMiddleware

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or str(_uuid.uuid4())[:8]
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

app.add_middleware(RequestIDMiddleware)

audit       = AuditLog()
token_store = get_token_store()

def load_config() -> dict:
    p = Path("config/models.yaml")
    if p.exists():
        import yaml
        with open(p) as f: return yaml.safe_load(f)
    return {"db_path":"data/myco.db","chroma_path":"data/chroma",
            "models":{"prefer_local":True,"timeout_s":30,
                      "tiers":{"tier_powerful":["ollama/llama3.2:70b"],
                               "tier_balanced":["ollama/llama3.2"],
                               "tier_fast":["ollama/llama3.2"],
                               "tier_local":["ollama/llama3.2"]},
                      "api_keys":{"anthropic":os.getenv("ANTHROPIC_API_KEY",""),
                                  "openai":os.getenv("OPENAI_API_KEY",""),
                                  "google":os.getenv("GOOGLE_API_KEY",""),
                                  "mistral":os.getenv("MISTRAL_API_KEY",""),
                                  "cohere":os.getenv("COHERE_API_KEY","")},
                      "custom_endpoints":{"ollama":os.getenv("OLLAMA_HOST","http://localhost:11434")}},
            "tools":["calculator","current_time","web_search","write_memory"]}

brain = MycoBrain(load_config())
clock = MycoClock(brain)

@app.on_event("startup")
async def _startup():
    log.info("Myco starting up...")
    clock.start()
    brain.start()   # starts learner + bootstrap

@app.on_event("shutdown")
async def _shutdown():
    log.info("Myco shutting down — flushing state...")
    clock.stop()
    try:
        brain.episodic.save_mind_state(brain.mind)
        brain.graph.save()
    except Exception:
        pass

# ── auth dependency ───────────────────────────────────────────────────────────
def auth_dep(required_role: Role = Role.USER):
    from safety.auth import ROLE_HIERARCHY
    async def _dep(request: Request) -> Token:
        token = await require_auth(
            authorization=request.headers.get("Authorization",""),
            method=request.method, path=request.url.path, audit=audit)
        if ROLE_HIERARCHY[token.role] < ROLE_HIERARCHY[required_role]:
            raise HTTPException(403, f"Requires role '{required_role.value}' or higher")
        return token
    return Depends(_dep)

RequireUser   = auth_dep(Role.USER)
RequireParent = auth_dep(Role.PARENT)
RequireRead   = auth_dep(Role.READONLY)

# ── request models ────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message:    str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = None
    media:      list[dict] | None = None
    @field_validator("message")
    @classmethod
    def no_null_bytes(cls, v):
        if "\x00" in v: raise ValueError("Null bytes not allowed")
        return v

class IngestRequest(BaseModel):
    content:      str = Field(..., min_length=1, max_length=50000)
    source_type:  str = Field(..., pattern=r"^(image|document|video|url|text)$")
    source_label: str = Field(..., max_length=200)

class ModelAddRequest(BaseModel):
    provider:  str = Field(..., max_length=50,  pattern=r"^[a-zA-Z0-9_\-]+$")
    model:     str = Field(..., max_length=100, pattern=r"^[a-zA-Z0-9_\-:.]+$")
    api_key:   str | None = Field(None, max_length=200)
    endpoint:  str | None = Field(None, max_length=500)
    tier:      str = Field("tier_balanced", pattern=r"^tier_(powerful|balanced|fast|local)$")

class SnapshotRequest(BaseModel):
    label:  str = Field("", max_length=100)
    reason: str = Field("", max_length=300)

class SelfImproveToggle(BaseModel):
    enabled: bool

class PlanDecision(BaseModel):
    reason: str = Field("", max_length=300)

class TokenCreateRequest(BaseModel):
    role:     str   = Field(..., pattern=r"^(user|readonly|parent)$")
    label:    str   = Field(..., max_length=80)
    ttl_days: float | None = Field(None, ge=0.1, le=365)

# ── public ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """No auth required — liveness probe. Reports online/offline mode."""
    model_ok = await brain.router.is_available()
    return {
        "status":  "alive",
        "stage":   brain.mind.stage,
        "xp":      brain.mind.xp,
        "model":   brain.mind.current_model,
        "offline": not model_ok,
        "mode":    "online" if model_ok else "offline",
    }

@app.get("/status")
async def full_status(_token: Token = RequireRead):
    """Detailed system status including offline mode info."""
    import sys
    model_ok = await brain.router.is_available()
    return {
        "online":          model_ok,
        "mode":            "online" if model_ok else "offline",
        "offline_message": (
            "" if model_ok else
            "No AI model is reachable. Myco is running in offline mode — "
            "memory search, tools, plugins, and document ingestion still work. "
            "Start Ollama or add an API key in Settings › AI Models to enable full AI."
        ),
        "model_status":    brain.router.get_status(),
        "memory_backend":  brain.semantic.backend_name,
        "memory_count":    brain.semantic.count(),
        "graph_nodes":     brain.graph.get_stats().get("nodes", 0),
        "stage":           brain.mind.stage,
        "xp":              brain.mind.xp,
        "tools":           brain.tools.list_available(),
        "plugins":         len(brain.plugins.get_all()),
        "python":          sys.version.split()[0],
    }

# ── mind ──────────────────────────────────────────────────────────────────────
@app.get("/mind")
async def get_mind(_token: Token = RequireRead):
    mind = brain.mind
    return {"stage":mind.stage,"xp":mind.xp,"current_model":mind.current_model,
            "total_interactions":mind.total_interactions,
            "personality_traits":mind.personality_traits,
            "memory_count":brain.semantic.count(),
            "graph_stats":brain.graph.get_stats(),
            "tools":brain.tools.list_available()}

# ── chat ──────────────────────────────────────────────────────────────────────
@app.post("/chat")
async def chat(req: ChatRequest, token: Token = RequireUser):
    check = detect_injection(req.message)
    if not check.clean:
        audit.log_threat("injection_attempt", token.token_id,
                         {"prefix":req.message[:100],"findings":check.findings})
        raise HTTPException(400, "Message rejected: possible prompt injection detected.")
    audit.log("API", "/chat", token.token_id, {"len":len(req.message),"media":bool(req.media)})
    async def stream() -> AsyncGenerator[str, None]:
        try:
            async for t in brain.think(req.message, req.media):
                yield f"data: {json.dumps({'token': t})}\n\n"
            yield f"data: {json.dumps({'done':True,'stage':brain.mind.stage,'xp':brain.mind.xp})}\n\n"
        except Exception as e:
            log.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'error':'Internal error'})}\n\n"
    return StreamingResponse(stream(), media_type="text/event-stream")

# ── ingest ────────────────────────────────────────────────────────────────────
@app.post("/ingest")
async def ingest(req: IngestRequest, token: Token = RequireUser):
    check = detect_injection(req.content[:2000])
    if not check.clean:
        audit.log_threat("injection_in_ingest", token.token_id,
                         {"source":req.source_label,"findings":check.findings})
        raise HTTPException(400, "Content rejected: possible injection attempt.")
    audit.log("API","/ingest",token.token_id,{"source_type":req.source_type,"label":req.source_label})
    result = await brain.ingest(req.content, req.source_type, req.source_label)
    return {**result,"xp":brain.mind.xp,"stage":brain.mind.stage}

# ── memory ────────────────────────────────────────────────────────────────────
@app.get("/memory")
async def get_memory(q:str="", limit:int=20, _token:Token=RequireRead):
    results = await brain.semantic.search(q or "recent", k=min(limit,100))
    return {"results":results,"total":brain.semantic.count()}

@app.get("/episodes")
async def get_episodes(n:int=20, _token:Token=RequireRead):
    return {"episodes":brain.episodic.get_recent(n=min(n,100))}

@app.get("/sessions")
async def get_sessions(_token:Token=RequireRead):
    return {"sessions":brain.episodic.get_sessions()}

@app.get("/graph")
async def get_graph(_token:Token=RequireRead):
    return {"stats":brain.graph.get_stats(),"most_connected":brain.graph.most_connected(20)}

# ── models ────────────────────────────────────────────────────────────────────
@app.get("/models")
async def get_models(_token:Token=RequireRead):
    return {"current":brain.mind.current_model,"tiers":brain.router.list_models()}

@app.post("/models/add")
async def add_model(req:ModelAddRequest, token:Token=RequireParent):
    audit.log_api("/models/add",token.token_id,{"provider":req.provider,"model":req.model})
    brain.router.add_model(provider=req.provider,model_name=req.model,
                           api_key=req.api_key,endpoint=req.endpoint,tier=req.tier)
    return {"status":"registered","model":f"{req.provider}/{req.model}"}

@app.post("/models/switch")
async def switch_model(body:dict, token:Token=RequireUser):
    model = str(body.get("model",""))[:150]
    if not model: raise HTTPException(400,"model required")
    brain.mind.current_model = model
    brain.episodic.save_mind_state(brain.mind)
    audit.log_api("/models/switch",token.token_id,{"model":model})
    return {"status":"switched","model":model}

# ── self-improvement (all parent-only) ───────────────────────────────────────
@app.post("/reflect")
async def trigger_reflection(token:Token=RequireParent):
    audit.log_api("/reflect",token.token_id,{})
    asyncio.create_task(brain.growth.maybe_reflect(brain.mind))
    return {"status":"reflection queued"}

@app.post("/self-improve/toggle")
async def toggle_self_improve(body:SelfImproveToggle, token:Token=RequireParent):
    brain.growth.toggle_self_improvement(body.enabled, token.token_id)
    return {"self_improve_enabled":body.enabled}

@app.get("/self-improve/pending")
async def get_pending(token:Token=RequireParent):
    return {"pending":brain.growth.get_pending_approvals()}

@app.post("/self-improve/approve/{plan_id}")
async def approve_plan(plan_id:str, token:Token=RequireParent):
    ok = brain.growth.approve_plan(plan_id, token.token_id)
    if not ok: raise HTTPException(404,"Plan not found")
    return {"status":"approved","plan_id":plan_id}

@app.post("/self-improve/reject/{plan_id}")
async def reject_plan(plan_id:str, body:PlanDecision, token:Token=RequireParent):
    ok = brain.growth.reject_plan(plan_id, token.token_id, body.reason)
    if not ok: raise HTTPException(404,"Plan not found")
    return {"status":"rejected","plan_id":plan_id}

@app.get("/growth/history")
async def growth_history(_token:Token=RequireRead):
    return {"history":brain.growth.get_history()}

# ── snapshots ─────────────────────────────────────────────────────────────────
@app.post("/snapshot")
async def create_snapshot(req:SnapshotRequest, token:Token=RequireParent):
    sid = brain.episodic.snapshot(req.label, req.reason)
    audit.log_change("manual_snapshot",token.token_id,{"snapshot_id":sid,"label":req.label})
    return {"snapshot_id":sid}

@app.get("/snapshots")
async def list_snapshots(_token:Token=RequireParent):
    return {"snapshots":brain.episodic.list_snapshots()}

@app.post("/rollback/{snapshot_id}")
async def rollback(snapshot_id:str, token:Token=RequireParent):
    if not snapshot_id.replace("-","").isalnum(): raise HTTPException(400,"Invalid snapshot ID")
    success = brain.episodic.rollback(snapshot_id)
    if not success: raise HTTPException(404,"Snapshot not found")
    audit.log_change("manual_rollback",token.token_id,{"snapshot_id":snapshot_id})
    return {"status":"rolled back","snapshot_id":snapshot_id}

# ── audit ─────────────────────────────────────────────────────────────────────
@app.get("/audit")
async def get_audit(n:int=50, category:str|None=None, _token:Token=RequireParent):
    return {"entries":audit.recent(n=min(n,200),category=category),"stats":audit.stats()}

@app.get("/audit/verify")
async def verify_audit(_token:Token=RequireParent):
    valid, message = audit.verify()
    return {"valid":valid,"message":message}

# ── token management ──────────────────────────────────────────────────────────
@app.post("/tokens/create")
async def create_token(req:TokenCreateRequest, token:Token=RequireParent):
    raw = token_store.create(role=Role(req.role), label=req.label, ttl_days=req.ttl_days)
    audit.log_auth("token_created",token.token_id,{"new_role":req.role,"label":req.label})
    return {"token":raw,"warning":"Save this token — it will not be shown again."}

@app.get("/tokens")
async def list_tokens(_token:Token=RequireParent):
    return {"tokens":token_store.list_tokens()}

@app.delete("/tokens/{token_id}")
async def revoke_token(token_id:str, token:Token=RequireParent):
    ok = token_store.revoke(token_id)
    if not ok: raise HTTPException(404,"Token not found")
    audit.log_auth("token_revoked",token.token_id,{"revoked_id":token_id})
    return {"status":"revoked","token_id":token_id}

@app.get("/learner/stats")
async def learner_stats(_token: Token = RequireRead):
    return brain.learner.get_stats()

@app.post("/learner/queue")
async def queue_learning(body: dict, token: Token = RequireUser):
    topic = str(body.get("topic",""))[:100].strip()
    query = str(body.get("query", topic + " tutorial explanation"))[:200].strip()
    if not topic:
        raise HTTPException(400, "topic required")
    brain.learner.queue_gap(topic, query, source="manual_api")
    audit.log("API", "/learner/queue", token.token_id, {"topic": topic})
    return {"status": "queued", "topic": topic}

@app.get("/system/info")
async def system_info(_token: Token = RequireRead):
    """Resource and backend info — useful for low-end PC diagnostics."""
    import sys
    return {
        "python":          sys.version.split()[0],
        "memory_backend":  brain.semantic.backend_name,
        "memory_count":    brain.semantic.count(),
        "graph_nodes":     brain.graph.get_stats().get("nodes", 0),
        "graph_edges":     brain.graph.get_stats().get("edges", 0),
        "learner_queued":  brain.learner.get_stats()["queued"],
        "learner_resolved":brain.learner.get_stats()["resolved"],
        "stage":           brain.mind.stage,
        "xp":              brain.mind.xp,
    }

# ── serve UI ──────────────────────────────────────────────────────────────────
ui_path = Path("ui/out")
if ui_path.exists():
    app.mount("/", StaticFiles(directory=str(ui_path), html=True), name="ui")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=False, log_level="info")

# ── plugin system ─────────────────────────────────────────────────────────────

class PluginInstallRequest(BaseModel):
    code:        str  = Field("", max_length=200_000)
    url:         str  = Field("", max_length=500)
    name:        str  = Field(..., max_length=80)
    description: str  = Field("", max_length=300)
    plugin_type: str  = Field("tool", pattern=r"^(tool|viewer|processor|trainer)$")
    icon:        str  = Field("🧩", max_length=10)

@app.get("/plugins")
async def list_plugins(_token: Token = RequireRead):
    return {"plugins": brain.plugins.get_all()}

@app.get("/plugins/ui-slots")
async def plugin_ui_slots(_token: Token = RequireRead):
    return {"slots": brain.plugins.get_ui_slots()}

@app.get("/plugins/{plugin_id}/code")
async def get_plugin_code(plugin_id: str, token: Token = RequireParent):
    code = brain.plugins.get_code(plugin_id)
    if not code:
        raise HTTPException(404, "Plugin not found")
    return {"code": code}

@app.post("/plugins/install")
async def install_plugin(req: PluginInstallRequest, token: Token = RequireParent):
    audit.log_api("/plugins/install", token.token_id,
                  {"name": req.name, "has_code": bool(req.code), "url": req.url[:80]})
    if req.url:
        result = brain.plugins.install_from_url(req.url, req.name, req.description)
    elif req.code:
        result = brain.plugins.install_from_code(
            req.code, req.name, req.description, req.plugin_type, icon=req.icon
        )
    else:
        raise HTTPException(400, "Provide either code or url")
    if not result.get("ok"):
        raise HTTPException(400, result.get("reason", "Install failed"))
    return result

@app.delete("/plugins/{plugin_id}")
async def uninstall_plugin(plugin_id: str, token: Token = RequireParent):
    ok = brain.plugins.uninstall(plugin_id)
    if not ok:
        raise HTTPException(404, "Plugin not found")
    audit.log_api("/plugins/uninstall", token.token_id, {"plugin_id": plugin_id})
    return {"status": "uninstalled"}

@app.post("/plugins/{plugin_id}/toggle")
async def toggle_plugin(plugin_id: str, body: dict, token: Token = RequireParent):
    ok = brain.plugins.toggle(plugin_id, body.get("enabled", True))
    if not ok:
        raise HTTPException(404, "Plugin not found")
    return {"status": "ok"}

# ── settings (full config read/write) ────────────────────────────────────────

@app.get("/settings")
async def get_settings(_token: Token = RequireRead):
    """Return current config (without API keys)."""
    import yaml
    p = Path("config/models.yaml")
    if not p.exists():
        return {"settings": {}}
    cfg = yaml.safe_load(p.read_text()) or {}
    # Strip API keys from response
    if "models" in cfg and "api_keys" in cfg["models"]:
        cfg["models"]["api_keys"] = {k: "***" if v else "" for k, v in cfg["models"]["api_keys"].items()}
    return {"settings": cfg}

class SettingsUpdate(BaseModel):
    key:   str = Field(..., max_length=100)
    value: str = Field(..., max_length=500)

@app.post("/settings/update")
async def update_setting(req: SettingsUpdate, token: Token = RequireParent):
    """Update a dot-path key in models.yaml (e.g. 'generation.max_tokens' = '512')."""
    import yaml
    p = Path("config/models.yaml")
    cfg = yaml.safe_load(p.read_text()) if p.exists() else {}
    # Navigate dot path
    keys = req.key.split(".")
    obj = cfg
    for k in keys[:-1]:
        if k not in obj:
            obj[k] = {}
        obj = obj[k]
    # Type coerce
    raw = req.value
    try:
        val = int(raw) if raw.isdigit() else float(raw) if "." in raw else \
              True if raw.lower()=="true" else False if raw.lower()=="false" else raw
    except Exception:
        val = raw
    obj[keys[-1]] = val
    tmp = str(p) + ".tmp"
    with open(tmp, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)
    os.replace(tmp, str(p))
    audit.log_api("/settings/update", token.token_id, {"key": req.key})
    return {"status": "updated", "key": req.key, "value": val}

@app.get("/terminal/run")
async def run_command(cmd: str, token: Token = RequireParent):
    """Safe terminal command proxy — allowlist only."""
    import subprocess, shlex
    ALLOWED = {
        "ollama list", "ollama ps", "ollama pull", "python3 --version",
        "pip list", "pip show", "df -h", "free -h", "uptime",
    }
    safe = any(cmd.strip().startswith(a) for a in ALLOWED)
    if not safe:
        raise HTTPException(403, f"Command not in allowlist. Allowed prefixes: {list(ALLOWED)}")
    audit.log_api("/terminal/run", token.token_id, {"cmd": cmd[:100]})
    try:
        result = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=30)
        return {"stdout": result.stdout[:5000], "stderr": result.stderr[:1000],
                "returncode": result.returncode}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── open-source merge endpoints ───────────────────────────────────────────────

class MergeRequest(BaseModel):
    url:          str  = Field("", max_length=500)
    code:         str  = Field("", max_length=200_000)
    name:         str  = Field("", max_length=80)
    description:  str  = Field("", max_length=300)
    install_deps: bool = False

@app.post("/merge/preview")
async def merge_preview(req: MergeRequest, token: Token = RequireParent):
    """Preview what a GitHub URL or code would add — before installing anything."""
    from core.plugins import OpenSourceMerger
    merger = OpenSourceMerger(brain.plugins)
    code = req.code
    name = req.name
    if req.url and not code:
        result = merger.fetch_github(req.url)
        if not result.get("ok"):
            raise HTTPException(400, result.get("error","Fetch failed"))
        code = result["code"]
        name = name or result.get("name", "plugin")
    if not code:
        raise HTTPException(400, "Provide code or URL")
    preview = merger.preview(code, req.url or "paste")
    return {"name": name, "preview": preview, "code_snippet": code[:500]}

@app.post("/merge/install-deps")
async def merge_install_deps(body: dict, token: Token = RequireParent):
    """Install safe pip packages for a plugin."""
    from core.plugins import OpenSourceMerger
    packages = body.get("packages", [])
    if not isinstance(packages, list):
        raise HTTPException(400, "packages must be a list")
    merger = OpenSourceMerger(brain.plugins)
    result = merger.install_deps([str(p)[:50] for p in packages[:20]])
    audit.log_api("/merge/install-deps", token.token_id, {"installed": result["installed"]})
    return result

@app.post("/merge/apply")
async def merge_apply(req: MergeRequest, token: Token = RequireParent):
    """Fetch (if URL) + preview + sandbox-test + install as plugin."""
    from core.plugins import OpenSourceMerger
    merger = OpenSourceMerger(brain.plugins)
    code = req.code
    name = req.name
    if req.url and not code:
        result = merger.fetch_github(req.url)
        if not result.get("ok"):
            raise HTTPException(400, result.get("error", "Fetch failed"))
        code = result["code"]
        name = name or result.get("name", "plugin")
    if not code:
        raise HTTPException(400, "Provide code or URL")
    # Install safe deps first if requested
    if req.install_deps:
        preview = merger.preview(code)
        merger.install_deps(preview.get("safe_deps", []))
    # Install plugin
    install_result = brain.plugins.install_from_code(
        code, name or "merged-plugin", req.description,
        source_url=req.url
    )
    if not install_result.get("ok"):
        raise HTTPException(400, install_result.get("reason", "Install failed"))
    audit.log_api("/merge/apply", token.token_id, {"name": name, "url": req.url[:80]})
    return install_result

@app.get("/plugins/{plugin_id}/widget")
async def get_plugin_widget(plugin_id: str, _token: Token = RequireRead):
    """Return the HTML widget for a viewer plugin."""
    code_path = __import__('pathlib').Path(f"data/plugins/{plugin_id}.py")
    if not code_path.exists():
        raise HTTPException(404, "Plugin not found")
    import ast as _ast
    src = code_path.read_text(encoding="utf-8")
    try:
        tree = _ast.parse(src)
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Assign):
                for t in node.targets:
                    if isinstance(t, _ast.Name) and t.id == "UI_WIDGET":
                        if isinstance(node.value, _ast.Constant):
                            from fastapi.responses import HTMLResponse
                            return HTMLResponse(content=str(node.value.value))
    except Exception:
        pass
    raise HTTPException(404, "No UI_WIDGET in plugin")
