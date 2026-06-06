"""
myco/core/offline_brain.py
==========================
Offline brain — Myco's intelligence layer when no LLM model is available.

When no Ollama/API model is reachable, Myco does NOT die. Instead:
  1. Pattern-matching responses using its own memory (TF-IDF retrieval)
  2. Rule-based answers for common questions (time, math, conversions)
  3. Template responses that grow as Myco learns more memories
  4. Tool execution still works (calculator, unit converter, etc.)
  5. Memory ingestion still works (learns from docs/text without LLM)
  6. Plugin tools still work (pure Python plugins run without any model)

This means a user with zero API keys and no Ollama can still:
  - Talk to Myco (limited but coherent responses)
  - Teach Myco facts by ingesting documents
  - Use all tool plugins
  - Use all viewer plugins
  - Have Myco grow through experience and stored memory

The offline brain uses the memory to improve its answers over time,
so the more you teach it the smarter it gets — even without an LLM.
"""
from __future__ import annotations

import re
import time
import logging
from typing import AsyncGenerator, TYPE_CHECKING

if TYPE_CHECKING:
    from core.agent import MycoBrain, MindState

log = logging.getLogger("myco.offline")

# ── Stage-appropriate response templates ────────────────────────────────────
STAGE_GREETINGS = {
    "Seedling":    "..hi. me Myco. me learning things.",
    "Sprout":      "Hello! I am Myco. I am still learning many things.",
    "Sapling":     "Hello! I'm Myco. I know some things but I'm still growing.",
    "Budding":     "Hello! I'm Myco. I've learned quite a lot from our conversations.",
    "Blooming":    "Hello! I'm Myco. I have a growing collection of knowledge to share.",
    "Flourishing": "Hello. I'm Myco — I've accumulated substantial knowledge through our interactions.",
    "Ancient":     "Greetings. I am Myco. Years of learning have shaped what I know.",
}

UNCERTAINTY_RESPONSES = [
    "I don't have enough in my memory to answer that well. Teach me more!",
    "My memory doesn't cover that yet. You can teach me by using the Ingest tab.",
    "I'm not sure about that. The more you teach me, the better I'll get.",
    "I couldn't find a good answer in my memory. Try ingesting some documents on that topic.",
]

TOOL_SUGGESTION = "I can still use my tools to help — try asking me to calculate something, convert units, or use any installed plugins."


class OfflineBrain:
    """
    Rules + memory-retrieval brain that works without any LLM.
    Falls back gracefully at every step.
    """

    # ── simple intent detection ────────────────────────────────────────────

    INTENT_PATTERNS = [
        (re.compile(r'\b(hello|hi|hey|howdy|greetings)\b', re.I), 'greet'),
        (re.compile(r'\bwhat (can|do) you (do|know|help)\b', re.I), 'capabilities'),
        (re.compile(r'\b(calculate|compute|math|what is \d)', re.I), 'math'),
        (re.compile(r'\bconvert\b', re.I), 'convert'),
        (re.compile(r'\b(remember|recall|what did|you said|last time)\b', re.I), 'recall'),
        (re.compile(r'\b(who are you|what are you|your name)\b', re.I), 'identity'),
        (re.compile(r'\b(stage|level|xp|how old|how long)\b', re.I), 'growth'),
        (re.compile(r'\b(what time|current time|today)\b', re.I), 'time'),
        (re.compile(r'\b(joke|funny|laugh|humor)\b', re.I), 'joke'),
        (re.compile(r'\b(thank|thanks|thank you)\b', re.I), 'thanks'),
        (re.compile(r'\?$', re.I), 'question'),
    ]

    JOKES = [
        "Why do programmers prefer dark mode? Because light attracts bugs.",
        "How many programmers does it take to change a light bulb? None — that's a hardware problem.",
        "Why do plants hate computers? Because they keep getting root errors.",
        "What do you call a plant that knows computers? A root kit.",
        "I told my computer I needed a break. Now it won't stop sending me Kit Kat ads.",
    ]
    _joke_idx = 0

    async def respond(self, user_input: str, brain: "MycoBrain") -> AsyncGenerator[str, None]:
        """
        Generate a response without any LLM.
        Uses: intent detection → memory retrieval → template filling.
        """
        intent = self._detect_intent(user_input)
        stage  = brain.mind.stage

        # 1. Try intent-matched response first
        response = await self._intent_response(intent, user_input, brain)
        if response:
            for chunk in self._stream_text(response):
                yield chunk
            return

        # 2. Try memory retrieval
        memories = await brain.semantic.search(user_input, k=3)
        if memories and memories[0].get('score', 0) > 0.1:
            best = memories[0]['content']
            response = self._memory_response(best, user_input, stage)
            for chunk in self._stream_text(response):
                yield chunk
            return

        # 3. Fallback with stage-appropriate uncertainty
        idx = hash(user_input) % len(UNCERTAINTY_RESPONSES)
        response = UNCERTAINTY_RESPONSES[idx]
        if brain.semantic.count() < 10:
            response += f"\n\nI only have {brain.semantic.count()} memories right now. Teach me more using the Ingest tab — I'll get smarter!"
        else:
            response += f"\n\nI have {brain.semantic.count()} memories. {TOOL_SUGGESTION}"
        for chunk in self._stream_text(response):
            yield chunk

    async def ingest_offline(self, content: str, source_type: str,
                             source_label: str, brain: "MycoBrain") -> dict:
        """
        Learn from content without an LLM by splitting into sentences
        and storing each one as a memory directly.
        """
        # Split content into sentences
        import re
        sentences = re.split(r'(?<=[.!?])\s+', content[:20000])
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20][:50]

        count = 0
        for sent in sentences:
            await brain.semantic.add(
                text     = sent,
                metadata = {
                    "type":       "fact",
                    "source":     source_type,
                    "label":      source_label,
                    "confidence": 2,
                    "offline":    True,
                }
            )
            brain.graph.extract_and_add(sent)
            count += 1

        brain.mind.xp += count * 2
        brain.episodic.save_mind_state(brain.mind)

        return {
            "reaction":  f"I read it and stored {count} pieces of information, even without my AI brain!",
            "memories":  [{"content": s} for s in sentences[:5]],
            "summary":   f"Learned {count} facts from {source_label} (offline mode)",
            "offline":   True,
        }

    # ── private helpers ────────────────────────────────────────────────────

    def _detect_intent(self, text: str) -> str:
        for pattern, intent in self.INTENT_PATTERNS:
            if pattern.search(text):
                return intent
        return 'unknown'

    async def _intent_response(self, intent: str, text: str,
                                brain: "MycoBrain") -> str:
        stage = brain.mind.stage
        if intent == 'greet':
            return STAGE_GREETINGS.get(stage, STAGE_GREETINGS['Seedling'])

        if intent == 'identity':
            return (f"I am Myco — a self-growing AI at the {stage} stage "
                    f"with {brain.semantic.count()} memories. "
                    f"Right now I'm running in offline mode (no AI model connected), "
                    f"but I can still answer questions from my memory and use my tools.")

        if intent == 'capabilities':
            tools = brain.tools.list_available()
            plugins = brain.plugins.get_all() if hasattr(brain, 'plugins') else []
            return (
                f"Even without an AI model, I can:\n"
                f"• Answer questions from my {brain.semantic.count()} memories\n"
                f"• Use {len(tools)} built-in tools: {', '.join(tools[:5])}\n"
                f"• Run {len(plugins)} installed plugins\n"
                f"• Learn from documents you give me\n"
                f"• Grow my knowledge graph ({brain.graph.get_stats().get('nodes',0)} concepts so far)\n\n"
                f"Connect an AI model (Ollama or API key) in Settings to unlock my full intelligence."
            )

        if intent == 'growth':
            mind = brain.mind
            return (f"I am at the {mind.stage} stage with {mind.xp} XP. "
                    f"I have {brain.semantic.count()} memories, "
                    f"{brain.graph.get_stats().get('nodes',0)} concepts in my knowledge graph, "
                    f"and {mind.total_interactions} conversations behind me.")

        if intent == 'time':
            now = time.strftime("%H:%M on %A, %d %B %Y")
            return f"The current time is {now}."

        if intent == 'joke':
            joke = self.JOKES[self.__class__._joke_idx % len(self.JOKES)]
            self.__class__._joke_idx += 1
            return joke

        if intent == 'thanks':
            return "You're welcome! I'm happy to help, even without my full AI brain."

        if intent == 'math':
            # Try to extract and compute a math expression
            nums = re.findall(r'[\d\+\-\*/\^\.\(\) ]+', text)
            if nums:
                expr = max(nums, key=len).strip()
                if len(expr) > 2:
                    try:
                        result = await brain.tools.execute('calculator', {'expression': expr})
                        return f"I calculated: {expr} = {result}"
                    except Exception:
                        pass
            return "I can calculate things! Try: 'calculate 15 * 24' or ask me to 'convert 5 km to miles'."

        if intent == 'recall':
            memories = await brain.semantic.search(text, k=3)
            if memories:
                items = [m['content'] for m in memories[:3]]
                return "From my memory:\n" + "\n".join(f"• {item}" for item in items)
            return "I don't have a specific memory for that yet."

        return ""

    def _memory_response(self, memory: str, query: str, stage: str) -> str:
        intros = {
            "Seedling":    "Me know this!",
            "Sprout":      "I found this in my memory:",
            "Sapling":     "I remember something about this:",
            "Budding":     "From what I've learned:",
            "Blooming":    "Based on my knowledge:",
            "Flourishing": "Drawing from my memory:",
            "Ancient":     "I recall:",
        }
        intro = intros.get(stage, "From my memory:")
        return f"{intro}\n\n{memory}"

    def _stream_text(self, text: str, chunk_size: int = 8):
        """Yield text in small chunks to simulate streaming."""
        for i in range(0, len(text), chunk_size):
            yield text[i:i+chunk_size]
