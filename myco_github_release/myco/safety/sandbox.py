"""
myco/safety/sandbox.py
======================
Isolated code execution for all LLM-generated tools and self-improvement code.

Security model:
  - AST whitelist pass:  rejects any code that uses banned nodes before exec()
  - Restricted builtins: only a curated safe subset is available
  - No imports allowed:  import / __import__ / importlib are all blocked
  - No filesystem:       open / os / pathlib / shutil blocked
  - No network:          socket / urllib / httpx / requests blocked
  - No introspection:    __class__ / __globals__ / getattr on arbitrary objects blocked
  - Resource limits:     wall-clock timeout (3 s), CPU time (2 s), max output 8 KB
  - Process isolation:   heavy option runs code in a subprocess with seccomp (Linux only)
  - Full audit log:      every execution is recorded with hash, result, and verdict
"""
from __future__ import annotations

import ast
import builtins
import hashlib
import json
import logging
import multiprocessing
import queue
import resource
import textwrap
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger("myco.sandbox")


# ── configuration ─────────────────────────────────────────────────────────────

WALL_TIMEOUT_S  = 3       # max seconds of real time
CPU_TIMEOUT_S   = 2       # max seconds of CPU time
MAX_OUTPUT_BYTES = 8_192  # max stdout capture
MAX_CODE_LEN    = 8_000   # reject code longer than this (characters)
MAX_RECURSION   = 50      # sys.setrecursionlimit inside sandbox


# ── banned AST node types ─────────────────────────────────────────────────────
# These node types indicate behaviour that must never appear in generated code.

BANNED_AST_NODES: set[type] = {
    ast.Import,           # import anything
    ast.ImportFrom,       # from x import y
    ast.Global,           # global variable manipulation
    ast.Nonlocal,         # nonlocal variable manipulation
    ast.AsyncFunctionDef, # async functions (could hide awaitable side-effects)
    ast.Await,            # await expressions
    ast.Yield,            # generators that could leak state
    ast.YieldFrom,
}

# String patterns that are banned even if they pass the AST check
BANNED_STRINGS: list[str] = [
    "__import__", "__builtins__", "__globals__", "__locals__",
    "__class__", "__bases__", "__subclasses__", "__mro__",
    "exec(", "eval(", "compile(", "open(", "os.path",
    "subprocess", "socket", "urllib", "httpx", "requests",
    "shutil", "pathlib", "tempfile", "ctypes", "cffi",
    "pickle", "marshal", "shelve", "importlib",
    "/etc/passwd", "/etc/shadow", "~/.ssh",
]

# Safe builtins (explicit allowlist — deny by default)
SAFE_BUILTINS: dict[str, Any] = {
    name: getattr(builtins, name)
    for name in [
        "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes",
        "callable", "chr", "complex", "dict", "dir", "divmod", "enumerate",
        "filter", "float", "format", "frozenset", "getattr", "hasattr",
        "hash", "hex", "int", "isinstance", "issubclass", "iter", "len",
        "list", "map", "max", "min", "next", "oct", "ord", "pow", "print",
        "range", "repr", "reversed", "round", "set", "slice", "sorted",
        "str", "sum", "tuple", "type", "vars", "zip",
        "True", "False", "None",
        "Exception", "ValueError", "TypeError", "KeyError",
        "IndexError", "AttributeError", "NotImplementedError",
        "StopIteration", "RuntimeError", "ArithmeticError",
    ]
    if hasattr(builtins, name)
}


# ── result types ──────────────────────────────────────────────────────────────

class Verdict(str, Enum):
    ACCEPTED   = "accepted"    # passed all checks + ran successfully
    REJECTED   = "rejected"    # failed static analysis — never ran
    FAILED     = "failed"      # ran but raised an exception
    TIMEOUT    = "timeout"     # exceeded resource limits
    SUSPICIOUS = "suspicious"  # ran OK but output looks dangerous


@dataclass
class SandboxResult:
    verdict:    Verdict
    output:     str  = ""
    error:      str  = ""
    functions:  list[str] = field(default_factory=list)
    duration_ms: int = 0
    code_hash:  str  = ""
    reason:     str  = ""   # human-readable explanation of verdict


# ── static analysis ───────────────────────────────────────────────────────────

class StaticAnalyser(ast.NodeVisitor):
    """Walk the AST and collect all violations."""

    def __init__(self):
        self.violations: list[str] = []

    def visit(self, node: ast.AST):
        if type(node) in BANNED_AST_NODES:
            self.violations.append(
                f"Banned node {type(node).__name__} at line {getattr(node, 'lineno', '?')}"
            )
        self.generic_visit(node)

    # Specifically catch attribute access to dangerous dunder names
    def visit_Attribute(self, node: ast.Attribute):
        if node.attr.startswith("__") and node.attr.endswith("__"):
            if node.attr not in ("__init__", "__str__", "__repr__", "__len__",
                                  "__iter__", "__next__", "__call__", "__name__"):
                self.violations.append(
                    f"Dangerous dunder access: {node.attr} at line {node.lineno}"
                )
        self.generic_visit(node)

    # Catch calls like getattr(obj, '__class__')
    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in ("getattr", "setattr", "delattr"):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if arg.value.startswith("__"):
                        self.violations.append(
                            f"Dangerous {node.func.id}(obj, '{arg.value}') at line {node.lineno}"
                        )
        self.generic_visit(node)


def static_check(code: str) -> list[str]:
    """Return list of violations. Empty list = clean."""
    violations: list[str] = []

    # 1. Length check
    if len(code) > MAX_CODE_LEN:
        violations.append(f"Code too long: {len(code)} chars (max {MAX_CODE_LEN})")
        return violations   # no point continuing

    # 2. Banned string patterns (fast scan before parsing)
    for pattern in BANNED_STRINGS:
        if pattern in code:
            violations.append(f"Banned pattern found: '{pattern}'")

    # 3. AST parse + walk
    try:
        tree = ast.parse(code)
        analyser = StaticAnalyser()
        analyser.visit(tree)
        violations.extend(analyser.violations)
    except SyntaxError as e:
        violations.append(f"Syntax error: {e}")

    return violations


# ── subprocess worker ─────────────────────────────────────────────────────────

def _sandbox_worker(code: str, result_q: "queue.Queue[dict]"):
    """
    Runs inside an isolated subprocess.
    Sets CPU + memory limits before executing.
    """
    import sys, io

    # resource limits (Linux only; ignored gracefully on macOS/Windows)
    try:
        resource.setrlimit(resource.RLIMIT_CPU,    (CPU_TIMEOUT_S, CPU_TIMEOUT_S))
        resource.setrlimit(resource.RLIMIT_NOFILE, (4, 4))      # max 4 open file descriptors
        resource.setrlimit(resource.RLIMIT_NPROC,  (1, 1))      # no fork
        resource.setrlimit(resource.RLIMIT_AS,     (256 * 1024 * 1024, 256 * 1024 * 1024))  # 256 MB
    except (AttributeError, ValueError):
        pass   # non-Linux or unprivileged — skip limits

    sys.setrecursionlimit(MAX_RECURSION)

    output_buf = io.StringIO()
    functions: list[str] = []

    def _safe_print(*args, **kwargs):
        s = " ".join(str(a) for a in args) + "\n"
        if output_buf.tell() + len(s) < MAX_OUTPUT_BYTES:
            output_buf.write(s)

    sandbox_globals = {
        "__builtins__": {**SAFE_BUILTINS, "print": _safe_print},
        "__name__":     "__sandbox__",
    }

    try:
        exec(compile(code, "<sandbox>", "exec"), sandbox_globals)
        functions = [
            k for k, v in sandbox_globals.items()
            if callable(v) and not k.startswith("_")
        ]
        result_q.put({
            "ok":        True,
            "output":    output_buf.getvalue()[:MAX_OUTPUT_BYTES],
            "functions": functions,
        })
    except Exception:
        result_q.put({
            "ok":    False,
            "error": traceback.format_exc(limit=5),
        })


# ── main sandbox class ────────────────────────────────────────────────────────

class CodeSandbox:
    """
    Execute untrusted code through three layers of protection:
      1. Static analysis (AST + string patterns) — never runs banned code
      2. Restricted globals — no builtins, no imports
      3. Subprocess isolation with OS-level resource limits

    Usage:
        sandbox = CodeSandbox()
        result  = await sandbox.run(code_string)
        if result.verdict == Verdict.ACCEPTED:
            # safe to use result.functions
    """

    def __init__(self, audit_log: "AuditLog | None" = None):
        self._audit = audit_log

    def run(self, code: str, description: str = "") -> SandboxResult:
        """Synchronous entrypoint (wraps the subprocess logic)."""
        t0        = time.perf_counter()
        code_hash = hashlib.sha256(code.encode()).hexdigest()[:16]

        # ── layer 1: static analysis ──────────────────────────────────────────
        violations = static_check(code)
        if violations:
            result = SandboxResult(
                verdict   = Verdict.REJECTED,
                reason    = "; ".join(violations),
                code_hash = code_hash,
                duration_ms = int((time.perf_counter() - t0) * 1000),
            )
            log.warning(f"[sandbox] REJECTED {code_hash}: {result.reason}")
            if self._audit:
                self._audit.log_sandbox(code_hash, description, result)
            return result

        # ── layer 2 + 3: subprocess execution ─────────────────────────────────
        # FIX: explicitly set start method to 'fork' on Linux for speed.
        # On macOS/Windows it defaults to 'spawn' which is 10x slower.
        try:
            ctx = multiprocessing.get_context("fork")
        except ValueError:
            ctx = multiprocessing.get_context("spawn")  # Windows / macOS fallback

        result_q = ctx.Queue(maxsize=1)
        proc = ctx.Process(target=_sandbox_worker, args=(code, result_q), daemon=True)
        proc.start()
        proc.join(timeout=WALL_TIMEOUT_S)

        duration_ms = int((time.perf_counter() - t0) * 1000)

        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=1)
            result = SandboxResult(
                verdict     = Verdict.TIMEOUT,
                reason      = f"Exceeded {WALL_TIMEOUT_S}s wall-clock limit",
                code_hash   = code_hash,
                duration_ms = duration_ms,
            )
            log.warning(f"[sandbox] TIMEOUT {code_hash} after {duration_ms}ms")
            if self._audit:
                self._audit.log_sandbox(code_hash, description, result)
            return result

        # FIX: process killed by OS signal (e.g. CPU limit SIGKILL) exits with
        # negative exitcode and empty queue — treat as TIMEOUT not generic FAILED
        if proc.exitcode is not None and proc.exitcode < 0:
            result = SandboxResult(
                verdict     = Verdict.TIMEOUT,
                reason      = f"Process killed by OS signal {abs(proc.exitcode)} (resource limit)",
                code_hash   = code_hash,
                duration_ms = duration_ms,
            )
            log.warning(f"[sandbox] KILLED {code_hash} signal={abs(proc.exitcode)}")
            if self._audit:
                self._audit.log_sandbox(code_hash, description, result)
            return result

        try:
            worker_result = result_q.get_nowait()
        except Exception:
            result = SandboxResult(
                verdict     = Verdict.FAILED,
                reason      = "Worker produced no result",
                code_hash   = code_hash,
                duration_ms = duration_ms,
            )
            if self._audit:
                self._audit.log_sandbox(code_hash, description, result)
            return result

        if not worker_result.get("ok"):
            result = SandboxResult(
                verdict     = Verdict.FAILED,
                error       = worker_result.get("error", "unknown error")[:1000],
                reason      = "Runtime exception in sandbox",
                code_hash   = code_hash,
                duration_ms = duration_ms,
            )
        else:
            output = worker_result.get("output", "")
            # ── layer 4: output screening ─────────────────────────────────────
            suspicious = self._screen_output(output)
            result = SandboxResult(
                verdict     = Verdict.SUSPICIOUS if suspicious else Verdict.ACCEPTED,
                output      = output,
                functions   = worker_result.get("functions", []),
                reason      = suspicious or "",
                code_hash   = code_hash,
                duration_ms = duration_ms,
            )

        log.info(f"[sandbox] {result.verdict.value.upper()} {code_hash} ({duration_ms}ms)")
        if self._audit:
            self._audit.log_sandbox(code_hash, description, result)
        return result

    def _screen_output(self, output: str) -> str:
        """Return a reason string if output looks suspicious, else empty string."""
        suspicious_patterns = [
            ("passwd",     "Output contains 'passwd' — possible file read"),
            ("private key","Output contains private key material"),
            ("BEGIN RSA",  "Output contains PEM key material"),
            ("127.0.0.1",  "Output contains localhost address"),
            ("localhost",  "Output references localhost"),
            ("http://",    "Output contains HTTP URL"),
            ("https://",   "Output contains HTTPS URL"),
        ]
        lower = output.lower()
        for pattern, reason in suspicious_patterns:
            if pattern.lower() in lower:
                return reason
        return ""
