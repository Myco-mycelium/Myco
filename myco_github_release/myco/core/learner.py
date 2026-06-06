"""
myco/core/learner.py
====================
Autonomous learning engine.

When Myco fails to answer something, is uncertain, or detects a knowledge gap,
this module kicks off a self-directed research loop:

  1. GapDetector   — analyses responses for uncertainty signals ("I don't know",
                     "I'm not sure", failed tool calls, low-confidence answers)
  2. ResearchPlanner — turns a gap into a concrete search plan
  3. Researcher     — executes web searches, reads results, extracts knowledge
  4. Integrator     — stores learned knowledge into memory with source attribution

This runs as a background task — it never blocks the main chat response.
The loop is lightweight: runs web searches (text only, no ML), processes
plain text, and stores to the TF-IDF memory.  Uses almost zero extra RAM.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.agent import MycoBrain, MindState

log = logging.getLogger("myco.learner")

# ── signals that Myco needs to learn something ────────────────────────────────

UNCERTAINTY_PATTERNS = [
    re.compile(r"i (don't|do not|cannot|can't) know", re.I),
    re.compile(r"i('m| am) not sure", re.I),
    re.compile(r"i('m| am) uncertain", re.I),
    re.compile(r"i (don't|do not) have (enough |any )?(information|knowledge|data)", re.I),
    re.compile(r"i('m| am) (not |un)?familiar with", re.I),
    re.compile(r"(beyond|outside) my (knowledge|training|understanding)", re.I),
    re.compile(r"i (haven't|have not) (learned|studied|seen)", re.I),
    re.compile(r"(as a|being a) (seedling|sprout|sapling)", re.I),
    re.compile(r"i('d| would) (need to|have to) (learn|study|research)", re.I),
    re.compile(r"(not|never) (coded|programmed|written code)", re.I),
    re.compile(r"(don't|do not) (understand|know how to) (code|program|write)", re.I),
]

# Capability signals — things Myco should proactively learn to do
CAPABILITY_GAPS = [
    ("code",     ["how to write Python code", "programming fundamentals", "code examples"]),
    ("math",     ["basic mathematics", "arithmetic", "algebra fundamentals"]),
    ("science",  ["basic science facts", "physics fundamentals", "biology basics"]),
    ("history",  ["world history overview", "major historical events"]),
    ("language", ["grammar rules", "writing style", "language patterns"]),
    ("logic",    ["logical reasoning", "deductive reasoning", "problem solving"]),
]


@dataclass
class KnowledgeGap:
    topic:       str
    query:       str
    source:      str    # "uncertainty_response" | "failed_tool" | "proactive" | "user_asked"
    detected_at: float  = field(default_factory=time.time)
    resolved:    bool   = False
    memories_added: int = 0


class GapDetector:
    """Watches Myco's responses for uncertainty and extracts gap topics."""

    def detect(self, user_input: str, response: str) -> list[KnowledgeGap]:
        gaps: list[KnowledgeGap] = []

        # Check response for uncertainty signals
        for pattern in UNCERTAINTY_PATTERNS:
            if pattern.search(response):
                # Extract the topic from user input
                topic = self._extract_topic(user_input)
                if topic:
                    gaps.append(KnowledgeGap(
                        topic  = topic,
                        query  = f"{topic} tutorial guide explanation",
                        source = "uncertainty_response"
                    ))
                break   # one gap per response max

        return gaps

    def detect_capability_gap(self, user_input: str, response: str) -> list[KnowledgeGap]:
        """Detect if Myco is missing a core capability."""
        gaps: list[KnowledgeGap] = []
        text = (user_input + " " + response).lower()
        for capability, search_queries in CAPABILITY_GAPS:
            if capability in text and any(
                p.search(response) for p in UNCERTAINTY_PATTERNS
            ):
                gaps.append(KnowledgeGap(
                    topic  = capability,
                    query  = search_queries[0],
                    source = "capability_gap"
                ))
        return gaps

    def _extract_topic(self, user_input: str) -> str:
        """Extract the main topic from user input."""
        # Remove common question words
        cleaned = re.sub(
            r'^(what|how|why|when|where|who|can|could|would|should|do|does|did|is|are|tell me|explain|describe)\s+',
            '', user_input.lower().strip(), flags=re.I
        )
        # Take first 5 meaningful words
        words = [w for w in cleaned.split() if len(w) > 3][:5]
        return " ".join(words)[:80]


class AutonomousLearner:
    """
    Runs background research when Myco detects it doesn't know something.
    Lightweight: uses the existing web_search tool, no extra dependencies.
    """

    def __init__(self, brain: "MycoBrain"):
        self.brain          = brain
        self.detector       = GapDetector()
        self._gap_queue:    asyncio.Queue[KnowledgeGap] = asyncio.Queue(maxsize=20)
        self._resolved:     list[KnowledgeGap]          = []
        self._running       = False
        self._worker_task: asyncio.Task | None = None

    def start(self):
        """Start the background research worker."""
        if not self._running:
            self._running     = True
            self._worker_task = asyncio.create_task(self._research_worker())
            log.info("AutonomousLearner started")

    def stop(self):
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()

    def observe(self, user_input: str, response: str):
        """
        Called after every chat turn.
        Detects gaps and queues research tasks non-blockingly.
        """
        gaps = (
            self.detector.detect(user_input, response) +
            self.detector.detect_capability_gap(user_input, response)
        )
        for gap in gaps:
            if not self._queue_contains(gap.topic):
                try:
                    self._gap_queue.put_nowait(gap)
                    log.info(f"[learner] Gap queued: {gap.topic}")
                except asyncio.QueueFull:
                    pass   # queue full — drop oldest gaps, not newest

    def queue_gap(self, topic: str, query: str, source: str = "manual"):
        """Manually queue a learning topic (called by growth engine)."""
        gap = KnowledgeGap(topic=topic, query=query, source=source)
        if not self._queue_contains(topic):
            try:
                self._gap_queue.put_nowait(gap)
                log.info(f"[learner] Manual gap queued: {topic}")
            except asyncio.QueueFull:
                pass

    def get_stats(self) -> dict:
        return {
            "queued":   self._gap_queue.qsize(),
            "resolved": len(self._resolved),
            "recent":   [
                {"topic": g.topic, "memories": g.memories_added, "source": g.source}
                for g in self._resolved[-10:]
            ]
        }

    # ── background worker ─────────────────────────────────────────────────────

    async def _research_worker(self):
        """
        Background loop: take a gap, research it, store what was learned.
        Paces itself: waits 30s between tasks so it doesn't hammer CPU or network.
        """
        log.info("[learner] Research worker running")
        while self._running:
            try:
                gap = await asyncio.wait_for(self._gap_queue.get(), timeout=60)
                log.info(f"[learner] Researching: {gap.topic}")
                await self._research_gap(gap)
                await asyncio.sleep(30)   # pace — don't hammer the network
            except asyncio.TimeoutError:
                continue   # nothing in queue — idle
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning(f"[learner] Research error: {e}")
                await asyncio.sleep(10)

    async def _research_gap(self, gap: KnowledgeGap):
        """Research one gap: search → read → extract → store."""
        mind = self.brain.mind

        # Step 1: Web search for the topic
        search_result = await self.brain.tools.execute(
            "web_search", {"query": gap.query}
        )
        if not search_result or "error" in str(search_result).lower():
            log.warning(f"[learner] Search failed for: {gap.topic}")
            return

        # Step 2: Ask the LLM to extract knowledge from search results
        # Use the smallest/fastest model for this background task
        fast_model = self.brain.router.route("research", "medium")
        extraction_prompt = (
            f"You found this information while researching '{gap.topic}':\n\n"
            f"{str(search_result)[:3000]}\n\n"
            f"Extract 3-5 concrete facts, rules, or concepts about '{gap.topic}' "
            f"that would help you answer future questions. "
            f"Respond ONLY as JSON: "
            f'[{{"type":"fact|concept|rule|skill","content":"...", "confidence":3}}]'
        )
        sys_prompt = (
            f"You are Myco's autonomous learning module at stage '{mind.stage}'. "
            "Extract structured knowledge from search results. Be concise and factual."
        )

        try:
            raw = await self.brain.router.complete(fast_model, extraction_prompt, sys_prompt)
            items = json.loads(raw.replace("```json", "").replace("```", "").strip())
            if not isinstance(items, list):
                items = []
        except Exception:
            # Fallback: store raw search result as a single memory
            items = [{"type": "fact", "content": str(search_result)[:500], "confidence": 2}]

        # Step 3: Store to memory
        count = 0
        for item in items[:5]:
            if isinstance(item, dict) and item.get("content"):
                await self.brain.semantic.add(
                    text     = item["content"],
                    metadata = {
                        "type":       item.get("type", "fact"),
                        "source":     "web_research",
                        "topic":      gap.topic,
                        "label":      f"auto-research: {gap.topic}",
                        "confidence": item.get("confidence", 2),
                    }
                )
                self.brain.graph.extract_and_add(item["content"])
                count += 1

        gap.resolved      = True
        gap.memories_added = count
        self._resolved.append(gap)

        # Award XP for autonomous learning
        self.brain.mind.xp += count * 3
        self.brain.episodic.save_mind_state(self.brain.mind)

        self.brain.audit.log("API", "autonomous_learning", "learner", {
            "topic":          gap.topic,
            "source":         gap.source,
            "memories_added": count,
            "stage":          mind.stage,
        })

        log.info(f"[learner] Learned {count} facts about '{gap.topic}'")

    def _queue_contains(self, topic: str) -> bool:
        """Check if topic already queued (avoids duplicate research)."""
        items: list[KnowledgeGap] = []
        while not self._gap_queue.empty():
            try:
                items.append(self._gap_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        found = any(g.topic == topic for g in items)
        for item in items:
            try:
                self._gap_queue.put_nowait(item)
            except asyncio.QueueFull:
                pass
        return found


# ── Proactive skill bootstrapper ─────────────────────────────────────────────

async def bootstrap_core_skills(brain: "MycoBrain"):
    """
    On first run (very few memories), proactively queue learning tasks
    for core skills Myco will definitely need.
    Used so a brand-new Myco immediately starts building foundational knowledge.
    """
    if brain.semantic.count() > 50:
        return   # already has knowledge — skip bootstrap

    log.info("[learner] Bootstrap: queuing core skill acquisition tasks")
    core_topics = [
        ("Python basics",       "Python programming basics tutorial"),
        ("how to answer questions", "best practices for answering questions clearly"),
        ("common knowledge",    "general knowledge facts science history geography"),
        ("mathematics basics",  "basic math arithmetic algebra"),
        ("reasoning patterns",  "logical reasoning deductive inductive step by step"),
    ]
    for topic, query in core_topics:
        brain.learner.queue_gap(topic, query, source="bootstrap")
        await asyncio.sleep(0.1)   # don't flood the queue instantly
