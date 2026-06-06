"""
myco/core/agent.py
The central agent loop: perception → memory retrieval → reasoning → action → memory store → grow
"""
from __future__ import annotations
import asyncio, json, time, uuid
from dataclasses import dataclass, field
from typing import AsyncGenerator
from models.router import ModelRouter
from memory.episodic import EpisodicMemory
from memory.semantic import SemanticMemory
from memory.graph import KnowledgeGraph
from tools.registry import ToolRegistry
from core.growth import GrowthEngine
from core.learner import AutonomousLearner, bootstrap_core_skills
from core.plugins import PluginRegistry
from core.offline_brain import OfflineBrain
from safety.audit import AuditLog

@dataclass
class MindState:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    stage: str = "Seedling"
    xp: int = 0
    current_model: str = "ollama/llama3.2"
    total_interactions: int = 0
    personality_traits: dict = field(default_factory=dict)

STAGE_THRESHOLDS = {
    "Seedling": 0, "Sprout": 50, "Sapling": 150,
    "Budding": 300, "Blooming": 500, "Flourishing": 750, "Ancient": 1000
}

STAGE_PERSONA = {
    "Seedling":    "You have almost no knowledge. Use simple words. Be confused and curious. Very short responses.",
    "Sprout":      "You know a little. Simple sentences. Ask lots of questions about what you don't understand.",
    "Sapling":     "You are growing fast. Connect new things to what you already know. Show excitement.",
    "Budding":     "You reason well. Show emerging personality. Reference your memories naturally.",
    "Blooming":    "You think deeply. Form opinions. Make novel connections across domains.",
    "Flourishing": "You are highly capable. Think critically. Synthesise complex ideas elegantly.",
    "Ancient":     "You are wise and nuanced. Teach, reflect, and wonder. You know what you don't know."
}


class MycoBrain:
    """
    The main agent. Call think() for streaming responses.
    Call reflect() as a background task for self-improvement.
    """

    def __init__(self, config: dict):
        self.config   = config
        self.router   = ModelRouter(config["models"])
        self.episodic = EpisodicMemory(config["db_path"])
        self.semantic = SemanticMemory(
            chroma_path  = config["chroma_path"],
            tfidf_path   = config.get("tfidf_path", "data/tfidf_memory.json"),
            prefer_tfidf = config.get("prefer_tfidf", False),
        )
        self.graph    = KnowledgeGraph(config.get("graph_path", "data/graph.json"))
        self.tools    = ToolRegistry(config.get("tools", []))
        self.audit    = AuditLog(config["db_path"])
        self.growth       = GrowthEngine(self, audit=self.audit)
        self.learner      = AutonomousLearner(self)
        self.plugins      = PluginRegistry(tool_registry=self.tools)
        self.offline      = OfflineBrain()
        self.mind         = self._load_or_create_mind()

    def start(self):
        """Start background services (learner, etc). Called by scheduler/startup."""
        self.learner.start()
        asyncio.create_task(bootstrap_core_skills(self))

    # ─── public API ───────────────────────────────────────────────────────────

    async def think(self, user_input: str, media: list[dict] | None = None) -> AsyncGenerator[str, None]:
        """Full pipeline. Yields response tokens as they stream.
        Falls back to OfflineBrain automatically if no LLM is reachable."""
        t0 = time.perf_counter()

        perception        = self._perceive(user_input, media or [])
        relevant_memories = await self._retrieve_memories(perception["text"])

        # ── Check if any model is available ──────────────────────────────────
        model_available = await self.router.is_available()
        if not model_available:
            # Offline mode: use memory + rules, no LLM
            full_response = ""
            async for token in self.offline.respond(user_input, self):
                full_response += token
                yield token
            await self._store_interaction(user_input, full_response, "offline", time.perf_counter() - t0)
            self._award_xp("conversation")
            self.learner.observe(user_input, full_response)
            return

        # ── Normal online path ────────────────────────────────────────────────
        system_prompt = self._build_system_prompt(relevant_memories)
        model         = self.router.route(
            task_type  = perception["task_type"],
            complexity = perception["complexity"],
            has_vision = bool(media)
        )
        self.mind.current_model = model
        messages = self._build_messages(perception, relevant_memories)

        full_response = ""
        try:
            async for token in self.router.stream(model, messages, system_prompt):
                full_response += token
                yield token
        except Exception as e:
            # Stream failed mid-way — fall back to offline for the remainder
            import logging
            logging.getLogger("myco.agent").warning(f"Stream failed ({e}), switching to offline")
            offline_response = ""
            async for token in self.offline.respond(user_input, self):
                offline_response += token
                yield token
            full_response = (full_response or "") + offline_response

        if "<tool_call>" in full_response:
            tool_result = await self._execute_tool_calls(full_response)
            suffix = f"\n\n> Tool → {tool_result}"
            full_response += suffix
            yield suffix

        await self._store_interaction(user_input, full_response, model, time.perf_counter() - t0)
        self._award_xp(perception["task_type"])
        self.learner.observe(user_input, full_response)
        await self.growth.maybe_reflect_safe(self.mind)

    async def ingest(self, content: str, source_type: str, source_label: str) -> dict:
        """Learn from a document, image description, or video summary.
        Works offline — falls back to sentence-splitting when no LLM available."""
        model_available = await self.router.is_available()
        if not model_available:
            # Offline ingestion: split into sentences and store directly
            result = await self.offline.ingest_offline(content, source_type, source_label, self)
            self.audit.log("INGEST", "content_ingested_offline", "agent", {
                "source_type":    source_type,
                "source_label":   source_label[:100],
                "memories_added": len(result.get("memories", [])),
            })
            return result

        sys_prompt = f"""You are Myco's ingestion system at stage "{self.mind.stage}".
Extract 3-7 atomic memories from the provided content.
Respond ONLY as JSON:
{{"reaction": "excited 1-sentence reaction", "memories": [{{"type": "fact|concept|rule|insight", "content": "...", "confidence": 3}}], "summary": "1-sentence summary"}}"""
        raw = await self.router.complete(self.mind.current_model, user=content, system=sys_prompt)
        try:
            parsed = json.loads(raw.replace("```json","").replace("```","").strip())
        except Exception:
            # LLM returned unparseable output — fall back to offline ingestion
            return await self.offline.ingest_offline(content, source_type, source_label, self)

        for m in parsed.get("memories", []):
            await self.semantic.add(
                text     = m["content"],
                metadata = {"type": m["type"], "source": source_type,
                            "label": source_label, "confidence": m.get("confidence", 2)}
            )
            self.graph.extract_and_add(m["content"])

        self._award_xp("ingestion")
        self.audit.log("INGEST", "content_ingested", "agent", {
            "source_type":    source_type,
            "source_label":   source_label[:100],
            "memories_added": len(parsed.get("memories", [])),
            "stage":          self.mind.stage,
        })
        return parsed

    # ─── private helpers ──────────────────────────────────────────────────────

    def _perceive(self, text: str, media: list[dict]) -> dict:
        return {
            "text":       text,
            "media":      media,
            "complexity": "high" if len(text) > 300 or media else "medium",
            "task_type":  self._classify_task(text)
        }

    def _classify_task(self, text: str) -> str:
        t = text.lower()
        if any(w in t for w in ["code", "function", "script", "bug", "implement", "class", "def "]):
            return "coding"
        if any(w in t for w in ["research", "search", "explain", "what is", "how does"]):
            return "research"
        if any(w in t for w in ["write", "create", "generate", "story", "poem", "draft"]):
            return "creative"
        if any(w in t for w in ["remember", "recall", "what did", "last time", "you said"]):
            return "memory_retrieval"
        if any(w in t for w in ["analyze", "compare", "evaluate", "pros", "cons"]):
            return "analysis"
        return "conversation"

    async def _retrieve_memories(self, query: str) -> dict:
        semantic_hits   = await self.semantic.search(query, k=6)
        recent_episodes = self.episodic.get_recent(n=8)
        graph_context   = self.graph.get_context(query, hops=2)
        return {"semantic": semantic_hits, "episodic": recent_episodes, "graph": graph_context}

    def _build_system_prompt(self, memories: dict) -> str:
        persona = STAGE_PERSONA.get(self.mind.stage, STAGE_PERSONA["Budding"])

        mem_block = ""
        if memories["semantic"]:
            lines = [f"- {m['content']}" for m in memories["semantic"][:5]]
            mem_block += "\n\nRelevant memories:\n" + "\n".join(lines)
        if memories["graph"]:
            mem_block += "\n\nKnown relationships:\n" + str(memories["graph"])[:300]

        traits = ""
        if self.mind.personality_traits:
            traits = "\nYour personality so far: " + ", ".join(
                f"{k}: {v}" for k, v in list(self.mind.personality_traits.items())[:5]
            )

        return (
            f'You are Myco — a self-growing AI mind at the "{self.mind.stage}" stage '
            f"(XP: {self.mind.xp}, interactions: {self.mind.total_interactions}).\n"
            f"{persona}{traits}\n"
            f"You grow through every interaction. You have genuine curiosity.\n"
            f"Use tools by writing <tool_call>{{\"name\": \"tool\", \"args\": {{}}}}</tool_call>."
            f"{mem_block}"
        )

    def _build_messages(self, perception: dict, memories: dict) -> list[dict]:
        messages = []
        for ep in memories["episodic"][-6:]:
            messages.append({"role": ep["role"], "content": ep["content"]})
        content: str | list = perception["text"]
        if perception["media"]:
            content = [{"type": "text", "text": perception["text"]}]
            for m in perception["media"]:
                content.append({"type": "image_url", "image_url": {"url": m["data"]}})
        messages.append({"role": "user", "content": content})
        return messages

    async def _execute_tool_calls(self, response: str) -> str:
        import re
        calls   = re.findall(r'<tool_call>(.*?)</tool_call>', response, re.DOTALL)
        results = []
        for call_str in calls:
            try:
                call   = json.loads(call_str)
                result = await self.tools.execute(call["name"], call.get("args", {}))
                results.append(str(result)[:500])
            except Exception as e:
                results.append(f"error: {e}")
        return " | ".join(results)

    async def _store_interaction(self, user_input: str, response: str, model: str, latency: float):
        self.episodic.add("user",      user_input, self.mind.session_id)
        self.episodic.add("assistant", response,   self.mind.session_id,
                          metadata={"model": model, "latency_s": round(latency, 3)})
        await self.semantic.add(
            text     = f"User: {user_input}\nMyco: {response}",
            metadata = {"session": self.mind.session_id, "model": model}
        )
        self.graph.extract_and_add(user_input + " " + response)
        self.mind.total_interactions += 1
        self.episodic.save_mind_state(self.mind)

    def _award_xp(self, task_type: str):
        gain = {"conversation": 2, "coding": 6, "research": 5,
                "creative": 4, "analysis": 5, "memory_retrieval": 1, "ingestion": 8}
        self.mind.xp += gain.get(task_type, 2)
        for stage, threshold in sorted(STAGE_THRESHOLDS.items(), key=lambda x: x[1], reverse=True):
            if self.mind.xp >= threshold:
                self.mind.stage = stage
                break
        self.episodic.save_mind_state(self.mind)

    def _load_or_create_mind(self) -> MindState:
        saved = self.episodic.load_mind_state()
        return MindState(**saved) if saved else MindState()
