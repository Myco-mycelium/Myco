"""
myco/models/router.py
Routes any task to the best available model. Supports cloud, local (Ollama),
open-source (vLLM/LM Studio), and any OpenAI-compatible custom endpoint.
Falls back gracefully when a model is unavailable.
"""
from __future__ import annotations
import asyncio, os, time, logging
from typing import AsyncGenerator, Any
import litellm
from litellm import acompletion

log = logging.getLogger("myco.router")

# ── routing rules ─────────────────────────────────────────────────────────────
# Each rule maps (task_type, complexity) → preferred model tier
ROUTING_TABLE: dict[tuple[str, str], str] = {
    ("coding",           "high"):   "tier_powerful",
    ("coding",           "medium"): "tier_balanced",
    ("research",         "high"):   "tier_powerful",
    ("research",         "medium"): "tier_balanced",
    ("analysis",         "high"):   "tier_powerful",
    ("analysis",         "medium"): "tier_balanced",
    ("creative",         "high"):   "tier_balanced",
    ("creative",         "medium"): "tier_fast",
    ("conversation",     "medium"): "tier_fast",
    ("conversation",     "low"):    "tier_local",
    ("memory_retrieval", "medium"): "tier_fast",
    ("ingestion",        "high"):   "tier_balanced",
}

DEFAULT_TIER = "tier_fast"

# ── tier definitions (overridden by config) ────────────────────────────────────
DEFAULT_TIERS = {
    "tier_powerful":  ["anthropic/claude-opus-4-5", "openai/gpt-4o", "google/gemini-1.5-pro"],
    "tier_balanced":  ["anthropic/claude-sonnet-4-20250514", "openai/gpt-4o-mini", "ollama/llama3.2:70b"],
    "tier_fast":      ["anthropic/claude-haiku-4-5-20251001", "openai/gpt-4o-mini", "ollama/llama3.2"],
    "tier_local":     ["ollama/llama3.2", "ollama/mistral", "ollama/qwen2.5"],
}


class ModelRouter:
    """
    Selects and calls the best model for a given task.
    Falls back through a chain if the primary model fails.

    Config shape:
        {
          "tiers": { "tier_fast": ["ollama/llama3.2", ...], ... },
          "api_keys": { "anthropic": "sk-ant-...", "openai": "sk-..." },
          "custom_endpoints": { "myllm": "http://localhost:8000/v1" },
          "prefer_local": true,
          "timeout_s": 30
        }
    """

    def __init__(self, config: dict):
        self.config           = config
        self.tiers            = {**DEFAULT_TIERS, **config.get("tiers", {})}
        self.api_keys         = config.get("api_keys", {})
        self.custom_endpoints = config.get("custom_endpoints", {})
        self.prefer_local     = config.get("prefer_local", False)
        self.timeout          = config.get("timeout_s", 30)
        self._health: dict[str, float] = {}
        self._configure_litellm()

    # ── public ─────────────────────────────────────────────────────────────────

    def route(self, task_type: str, complexity: str = "medium", has_vision: bool = False) -> str:
        """Return the best available model name for this task."""
        tier_name = ROUTING_TABLE.get((task_type, complexity), DEFAULT_TIER)

        if self.prefer_local:
            tier_name = "tier_local"

        candidates = self.tiers.get(tier_name, self.tiers[DEFAULT_TIER])

        if has_vision:
            candidates = [m for m in candidates if self._supports_vision(m)] or candidates

        for model in candidates:
            if self._is_healthy(model):
                log.debug(f"Routing {task_type}/{complexity} → {model}")
                return model

        # all preferred models unhealthy — try any local model as last resort
        for model in self.tiers.get("tier_local", []):
            if self._is_healthy(model):
                log.warning(f"Fallback to local: {model}")
                return model

        # give up and try anyway (will surface the error to the user)
        return candidates[0]

    async def stream(self, model: str, messages: list[dict], system: str) -> AsyncGenerator[str, None]:
        """Stream tokens from the chosen model, falling back on error."""
        fallback_chain = self._build_fallback_chain(model)
        for attempt_model in fallback_chain:
            try:
                async for token in self._stream_once(attempt_model, messages, system):
                    yield token
                return
            except Exception as e:
                log.warning(f"Model {attempt_model} failed: {e}. Trying next.")
                self._mark_unhealthy(attempt_model)

        yield "\n\n[Myco: all models unavailable. Check your config or start Ollama locally.]"

    async def complete(self, model: str, user: str, system: str) -> str:
        """Non-streaming completion. Returns full text."""
        full = ""
        async for token in self.stream(model, [{"role": "user", "content": user}], system):
            full += token
        return full

    async def is_available(self) -> bool:
        """
        Quick check: is ANY model reachable right now?
        Tries a tiny probe request against the best available model.
        Returns True if at least one model responds, False if fully offline.
        Caches the result for 30 seconds to avoid hammering the endpoint.
        """
        now = time.time()
        # Use cached result if fresh
        if hasattr(self, '_available_cache'):
            cached_time, cached_result = self._available_cache
            if now - cached_time < 30:
                return cached_result

        # Try the fastest/smallest model first
        candidate = self.route("conversation", "low", False)
        try:
            kwargs = self._build_kwargs(
                candidate,
                [{"role": "user", "content": "hi"}],
                "Reply with just 'ok'."
            )
            kwargs["max_tokens"] = 5
            kwargs["timeout"]    = 5  # very short timeout for probe
            import litellm
            response = await litellm.acompletion(**kwargs)
            result = bool(response.choices)
        except Exception:
            result = False

        self._available_cache = (now, result)
        if not result:
            log.info("Model probe failed — switching to offline mode")
        return result

    def get_status(self) -> dict:
        """Return current availability status of all model tiers."""
        return {
            "tiers": {
                tier: [
                    {"model": m, "healthy": self._is_healthy(m)}
                    for m in models
                ]
                for tier, models in self.tiers.items()
            },
            "prefer_local": self.prefer_local,
        }

    def add_model(self, provider: str, model_name: str, api_key: str | None = None,
                  endpoint: str | None = None, tier: str = "tier_balanced"):
        """Runtime model registration — no restart needed."""
        full_name = f"{provider}/{model_name}"
        if api_key:
            self.api_keys[provider] = api_key
            self._configure_litellm()
        if endpoint:
            # FIX: store per-model endpoint in custom_endpoints, NOT in litellm.api_base
            # (litellm.api_base is a global that would affect ALL models)
            self.custom_endpoints[model_name] = endpoint
        if tier in self.tiers:
            if full_name not in self.tiers[tier]:
                self.tiers[tier].insert(0, full_name)
        log.info(f"Registered model: {full_name} in {tier}")

    def list_models(self) -> dict[str, list[str]]:
        return {tier: list(models) for tier, models in self.tiers.items()}

    # ── private ────────────────────────────────────────────────────────────────

    async def _stream_once(self, model: str, messages: list[dict], system: str) -> AsyncGenerator[str, None]:
        kwargs = self._build_kwargs(model, messages, system)
        response = await acompletion(**kwargs, stream=True)
        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    def _build_kwargs(self, model: str, messages: list[dict], system: str) -> dict:
        all_messages = [{"role": "system", "content": system}] + messages
        kwargs: dict[str, Any] = {
            "model":      model,
            "messages":   all_messages,
            "timeout":    self.timeout,
            "max_tokens": self.config.get("max_tokens", 1024),
        }
        # Stage-aware temperature: lower = more coherent at early stages
        temp = self.config.get("temperature", 0.7)
        kwargs["temperature"] = temp

        # inject API keys per provider
        provider = model.split("/")[0]
        if provider in self.api_keys and self.api_keys[provider]:
            kwargs["api_key"] = self.api_keys[provider]

        # custom endpoints (Ollama, LM Studio, vLLM, llama.cpp server)
        model_short = model.split("/")[-1]
        if model_short in self.custom_endpoints:
            kwargs["api_base"] = self.custom_endpoints[model_short]
        elif provider == "ollama":
            kwargs["api_base"] = self.custom_endpoints.get("ollama", "http://localhost:11434")
        return kwargs

    def set_temperature(self, temp: float):
        """Allow agent to adjust temperature based on growth stage."""
        self.config["temperature"] = max(0.0, min(2.0, temp))

    def _build_fallback_chain(self, primary: str) -> list[str]:
        chain = [primary]
        provider = primary.split("/")[0]
        # add same-provider alternatives
        for tier_models in self.tiers.values():
            for m in tier_models:
                if m not in chain and m.split("/")[0] == provider:
                    chain.append(m)
        # add local fallbacks last
        for m in self.tiers.get("tier_local", []):
            if m not in chain:
                chain.append(m)
        return chain

    def _configure_litellm(self):
        litellm.drop_params  = True    # ignore unsupported params per provider
        litellm.set_verbose  = False
        for provider, key in self.api_keys.items():
            if not key:
                continue
            if provider == "anthropic":
                litellm.anthropic_key = key
            elif provider == "openai":
                litellm.openai_key = key
            elif provider == "google":
                # FIX: litellm.vertex_key does not exist.
                # Google auth is handled via api_key in _build_kwargs,
                # or via GOOGLE_API_KEY / GOOGLE_APPLICATION_CREDENTIALS env vars.
                os.environ["GOOGLE_API_KEY"] = key
            elif provider == "mistral":
                litellm.mistral_key = key
            elif provider == "cohere":
                litellm.cohere_key = key

    def _supports_vision(self, model: str) -> bool:
        vision_models = {
            "claude-opus", "claude-sonnet", "claude-haiku",
            "gpt-4o", "gpt-4-turbo", "gemini"
        }
        return any(v in model for v in vision_models)

    def _is_healthy(self, model: str) -> bool:
        last_fail = self._health.get(model, 0)
        return (time.time() - last_fail) > 60   # 60-second cooldown

    def _mark_unhealthy(self, model: str):
        self._health[model] = time.time()
