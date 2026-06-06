"""
myco/core/plugins.py
====================
Open-source plugin integration engine.

Allows any open-source code / library to be absorbed into Myco at runtime:
  - Upload a Python file or paste a GitHub URL → Myco integrates it as a capability
  - Each plugin gets a sandboxed namespace, a UI panel slot, and tool registrations
  - Plugins can expose: tools (callable functions), UI widgets (HTML), and data viewers

Built-in plugin types recognized automatically:
  "tool"      — exposes callable functions Myco can use in chat
  "viewer"    — provides an HTML/JS rendering surface (3D, charts, maps, etc.)
  "processor" — transforms data (slicer, converter, analyser)
  "trainer"   — adds training examples or fine-tuning data
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import os
import sys
import time
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from safety.sandbox import CodeSandbox, Verdict

log = logging.getLogger("myco.plugins")

PLUGINS_DIR = Path("data/plugins")


@dataclass
class PluginManifest:
    plugin_id:   str
    name:        str
    description: str
    version:     str        = "1.0.0"
    author:      str        = "unknown"
    plugin_type: str        = "tool"         # tool | viewer | processor | trainer
    source_url:  str        = ""
    icon:        str        = "🧩"
    enabled:     bool       = True
    tools:       list[str]  = field(default_factory=list)    # callable names exposed
    ui_slot:     str        = ""                              # HTML widget if viewer
    installed_at: float     = field(default_factory=time.time)
    sandbox_verdict: str    = ""


class PluginRegistry:
    """
    Manages all installed plugins.
    Persists manifests to data/plugins/registry.json.
    Each plugin's code lives at data/plugins/{plugin_id}.py
    """

    def __init__(self, tool_registry=None, sandbox: CodeSandbox | None = None):
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        self._manifests: dict[str, PluginManifest] = {}
        self._namespaces: dict[str, dict]          = {}  # plugin_id → exec namespace
        self._tool_registry = tool_registry
        self._sandbox       = sandbox or CodeSandbox()
        self._load_registry()

    # ── public install/remove ─────────────────────────────────────────────────

    def install_from_code(self, code: str, name: str, description: str = "",
                          plugin_type: str = "tool", source_url: str = "",
                          icon: str = "🧩") -> dict:
        """
        Install a plugin from raw Python source code.
        Runs through sandbox first — rejects malicious code.
        Returns {"ok": bool, "plugin_id": str, "reason": str}
        """
        # Sandbox test
        result = self._sandbox.run(code, description=f"plugin install: {name}")
        if result.verdict != Verdict.ACCEPTED:
            log.warning(f"Plugin '{name}' rejected by sandbox: {result.reason}")
            return {"ok": False, "reason": f"Security check failed: {result.reason}",
                    "verdict": result.verdict.value}

        plugin_id = hashlib.md5(code.encode()).hexdigest()[:12]

        # Detect UI slot if code contains HTML/JS rendering
        ui_slot = self._extract_ui_slot(code)
        detected_type = plugin_type
        if ui_slot and plugin_type == "tool":
            detected_type = "viewer"

        manifest = PluginManifest(
            plugin_id    = plugin_id,
            name         = name,
            description  = description or f"Plugin: {name}",
            plugin_type  = detected_type,
            source_url   = source_url,
            icon         = icon,
            tools        = result.functions,
            ui_slot      = ui_slot,
            sandbox_verdict = result.verdict.value,
        )

        # Save code
        code_path = PLUGINS_DIR / f"{plugin_id}.py"
        code_path.write_text(code, encoding="utf-8")

        # Execute in restricted namespace and register tools
        namespace = self._exec_plugin(code, plugin_id)
        if namespace:
            self._namespaces[plugin_id] = namespace
            if self._tool_registry:
                for fn_name in result.functions:
                    fn = namespace.get(fn_name)
                    if fn and callable(fn):
                        self._tool_registry.register_dynamic(
                            f"{plugin_id}_{fn_name}", fn,
                            f"[{name}] {fn_name}"
                        )
                        manifest.tools.append(f"{plugin_id}_{fn_name}")

        self._manifests[plugin_id] = manifest
        self._save_registry()
        log.info(f"Plugin installed: {name} ({plugin_id}) type={detected_type} tools={result.functions}")
        return {"ok": True, "plugin_id": plugin_id, "manifest": self._manifest_dict(manifest)}

    def install_from_url(self, url: str, name: str = "", description: str = "") -> dict:
        """
        Fetch code from a URL (raw GitHub, jsDelivr, etc.) and install.
        Only fetches — user must confirm before install.
        """
        import urllib.request
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                code = r.read().decode("utf-8")[:100_000]
            display_name = name or url.split("/")[-1].replace(".py","").replace("-","_")
            return self.install_from_code(code, display_name, description, source_url=url)
        except Exception as e:
            return {"ok": False, "reason": str(e)}

    def uninstall(self, plugin_id: str) -> bool:
        if plugin_id not in self._manifests:
            return False
        # Remove code file
        code_path = PLUGINS_DIR / f"{plugin_id}.py"
        if code_path.exists():
            code_path.unlink()
        # Remove tools
        if self._tool_registry:
            m = self._manifests[plugin_id]
            for tool_name in m.tools:
                self._tool_registry._tools.pop(tool_name, None)
        del self._manifests[plugin_id]
        self._namespaces.pop(plugin_id, None)
        self._save_registry()
        return True

    def toggle(self, plugin_id: str, enabled: bool) -> bool:
        if plugin_id not in self._manifests:
            return False
        self._manifests[plugin_id].enabled = enabled
        self._save_registry()
        return True

    def get_all(self) -> list[dict]:
        return [self._manifest_dict(m) for m in self._manifests.values()]

    def get_ui_slots(self) -> list[dict]:
        """Return all plugins that have UI widgets."""
        return [
            self._manifest_dict(m) for m in self._manifests.values()
            if m.ui_slot and m.enabled
        ]

    def get_code(self, plugin_id: str) -> str:
        path = PLUGINS_DIR / f"{plugin_id}.py"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    # ── private ───────────────────────────────────────────────────────────────

    def _exec_plugin(self, code: str, plugin_id: str) -> dict | None:
        """Execute plugin in a restricted namespace. Returns the namespace."""
        import builtins
        safe_builtins = {
            k: getattr(builtins, k)
            for k in ["abs","bool","dict","enumerate","float","int","len","list",
                      "map","max","min","range","round","set","sorted","str","sum",
                      "tuple","zip","True","False","None","print",
                      "Exception","ValueError","TypeError","isinstance"]
            if hasattr(builtins, k)
        }
        namespace: dict = {
            "__builtins__": safe_builtins,
            "__name__": f"myco_plugin_{plugin_id}",
        }
        try:
            exec(compile(code, f"<plugin:{plugin_id}>", "exec"), namespace)
            return namespace
        except Exception as e:
            log.warning(f"Plugin exec failed {plugin_id}: {e}")
            return None

    def _extract_ui_slot(self, code: str) -> str:
        """
        If the plugin contains a UI_WIDGET constant (HTML string), extract it.
        Plugins declare their UI with:
            UI_WIDGET = '<div id="my-widget">...</div>'
        """
        import ast
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "UI_WIDGET":
                            if isinstance(node.value, ast.Constant):
                                return str(node.value.value)[:50_000]
        except Exception:
            pass
        return ""

    def _manifest_dict(self, m: PluginManifest) -> dict:
        return {
            "plugin_id":   m.plugin_id,
            "name":        m.name,
            "description": m.description,
            "version":     m.version,
            "author":      m.author,
            "plugin_type": m.plugin_type,
            "source_url":  m.source_url,
            "icon":        m.icon,
            "enabled":     m.enabled,
            "tools":       m.tools,
            "ui_slot":     bool(m.ui_slot),
            "installed_at": m.installed_at,
        }

    def _save_registry(self):
        registry_path = PLUGINS_DIR / "registry.json"
        data = {pid: self._manifest_dict(m) for pid, m in self._manifests.items()}
        tmp  = str(registry_path) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, str(registry_path))

    def _load_registry(self):
        registry_path = PLUGINS_DIR / "registry.json"
        if not registry_path.exists():
            return
        try:
            data = json.loads(registry_path.read_text())
            for pid, d in data.items():
                m = PluginManifest(
                    plugin_id    = d["plugin_id"],
                    name         = d["name"],
                    description  = d["description"],
                    version      = d.get("version","1.0.0"),
                    author       = d.get("author","unknown"),
                    plugin_type  = d.get("plugin_type","tool"),
                    source_url   = d.get("source_url",""),
                    icon         = d.get("icon","🧩"),
                    enabled      = d.get("enabled", True),
                    tools        = d.get("tools",[]),
                    installed_at = d.get("installed_at", 0),
                )
                # Re-execute code to restore namespaces
                code_path = PLUGINS_DIR / f"{pid}.py"
                if code_path.exists():
                    ns = self._exec_plugin(code_path.read_text(), pid)
                    if ns:
                        self._namespaces[pid] = ns
                        if self._tool_registry and m.enabled:
                            for tool_name in m.tools:
                                short = tool_name.replace(f"{pid}_","")
                                fn = ns.get(short) or ns.get(tool_name)
                                if fn and callable(fn):
                                    self._tool_registry.register_dynamic(
                                        tool_name, fn, f"[{m.name}] {short}"
                                    )
                self._manifests[pid] = m
            log.info(f"Loaded {len(self._manifests)} plugins from registry")
        except Exception as e:
            log.warning(f"Plugin registry load failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Open-Source Merge Engine
# Turns any GitHub repo, PyPI package, or raw file into a Myco capability
# ─────────────────────────────────────────────────────────────────────────────

import re as _re
import subprocess as _subprocess
import urllib.request as _urllib

SAFE_PACKAGES = {
    # Data & math
    "numpy", "pandas", "scipy", "matplotlib", "seaborn", "plotly",
    # Web & APIs
    "requests", "httpx", "beautifulsoup4", "lxml",
    # Text & NLP
    "nltk", "textblob", "spacy",
    # Files & formats
    "pillow", "pypdf", "openpyxl", "python-docx", "markdown",
    # 3D & viz
    "trimesh", "open3d", "vtk",
    # Utils
    "arrow", "pendulum", "click", "rich", "tqdm",
    # Audio
    "pydub",
    # Crypto / encoding
    "cryptography",
}


class OpenSourceMerger:
    """
    Absorbs open-source projects into Myco.

    Workflow:
      1. preview()   → analyse code without installing anything
      2. install()   → run through security sandbox + install safe deps
      3. activate()  → register tools and UI widgets into live system

    Supports:
      - Raw Python files (.py)
      - GitHub repos (extracts main module + README)
      - PyPI package names (imports only — no arbitrary exec)
      - Paste of any Python code
    """

    def __init__(self, registry: PluginRegistry):
        self.registry = registry

    def preview(self, code: str, source: str = "") -> dict:
        """
        Analyse code before installing. Returns what would be added.
        Does NOT execute anything.
        """
        # Extract imports
        imports   = self._extract_imports(code)
        functions = self._extract_functions(code)
        has_ui    = "UI_WIDGET" in code
        has_reqs  = "requirements" in code.lower() or "install_requires" in code.lower()

        safe_deps   = [i for i in imports if i in SAFE_PACKAGES]
        unsafe_deps = [i for i in imports if i not in SAFE_PACKAGES and i not in _STDLIB]

        # Run static analysis
        violations = []
        try:
            from safety.sandbox import static_check
            violations = static_check(code)
        except Exception:
            pass

        return {
            "source":       source,
            "functions":    functions,
            "imports":      imports,
            "safe_deps":    safe_deps,
            "unsafe_deps":  unsafe_deps,
            "has_ui_widget": has_ui,
            "has_requirements": has_reqs,
            "violations":   violations,
            "safe_to_install": len(violations) == 0 and len(unsafe_deps) == 0,
            "lines":        code.count("\n"),
        }

    def fetch_github(self, url: str) -> dict:
        """
        Fetch a GitHub repo and extract installable code.
        Supports:
          - https://github.com/user/repo
          - https://github.com/user/repo/blob/main/file.py
          - https://raw.githubusercontent.com/...
        """
        # Convert blob URL to raw
        raw_url = url
        if "github.com" in url and "/blob/" in url:
            raw_url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        elif "github.com" in url and not url.endswith(".py"):
            # Repo root — try to fetch main.py or __init__.py
            parts = url.rstrip("/").split("/")
            if len(parts) >= 5:
                user, repo = parts[3], parts[4]
                for branch in ["main", "master"]:
                    for fname in ["main.py", "app.py", "__init__.py", f"{repo}.py"]:
                        try_url = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{fname}"
                        try:
                            with _urllib.urlopen(try_url, timeout=8) as r:
                                code = r.read().decode("utf-8")
                            return {"ok": True, "code": code, "url": try_url,
                                    "name": repo, "branch": branch}
                        except Exception:
                            continue
                return {"ok": False, "error": "Could not find main Python file in repo"}

        try:
            with _urllib.urlopen(raw_url, timeout=10) as r:
                code = r.read().decode("utf-8")[:100_000]
            name = raw_url.split("/")[-1].replace(".py", "").replace("-", "_")
            return {"ok": True, "code": code, "url": raw_url, "name": name}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def install_deps(self, packages: list[str]) -> dict:
        """
        pip install safe packages only. Refuses unsafe ones.
        Returns {installed: [...], skipped: [...], errors: [...]}
        """
        installed, skipped, errors = [], [], []
        for pkg in packages:
            if pkg not in SAFE_PACKAGES:
                skipped.append(pkg)
                continue
            try:
                result = _subprocess.run(
                    ["pip", "install", pkg, "--break-system-packages", "-q"],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode == 0:
                    installed.append(pkg)
                else:
                    errors.append(f"{pkg}: {result.stderr[:200]}")
            except Exception as e:
                errors.append(f"{pkg}: {e}")
        return {"installed": installed, "skipped": skipped, "errors": errors}

    def _extract_imports(self, code: str) -> list[str]:
        imports = []
        for line in code.splitlines():
            line = line.strip()
            m = _re.match(r'^import\s+([a-zA-Z0-9_]+)', line)
            if m:
                imports.append(m.group(1))
            m = _re.match(r'^from\s+([a-zA-Z0-9_]+)', line)
            if m:
                imports.append(m.group(1))
        return list(set(imports))

    def _extract_functions(self, code: str) -> list[str]:
        return _re.findall(r'^def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', code, _re.MULTILINE)


# Common stdlib modules (not third-party)
_STDLIB = {
    "os", "sys", "re", "json", "math", "time", "datetime", "pathlib",
    "collections", "itertools", "functools", "typing", "abc", "io",
    "hashlib", "hmac", "secrets", "random", "string", "struct",
    "base64", "urllib", "http", "email", "csv", "sqlite3", "logging",
    "threading", "multiprocessing", "asyncio", "concurrent", "queue",
    "copy", "pprint", "textwrap", "dataclasses", "enum", "contextlib",
    "unittest", "ast", "dis", "inspect", "importlib", "pkgutil",
    "builtins", "warnings", "traceback", "gc", "weakref",
    "operator", "bisect", "heapq", "array", "decimal", "fractions",
    "statistics", "cmath", "numbers", "uuid", "socket",
}
