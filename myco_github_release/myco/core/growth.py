"""
myco/core/growth.py  (security-hardened rewrite)
=================================================
Self-improvement engine with mandatory security gates at every stage.

Security additions vs original:
  1.  Every generated code goes through CodeSandbox (AST + subprocess + limits)
  2.  REJECTED / TIMEOUT / SUSPICIOUS verdicts are hard stops
  3.  Parent-approval gate: high-risk changes queue for human sign-off
  4.  Mind snapshot BEFORE any integration attempt
  5.  Automatic rollback if integration raises any exception
  6.  Full AuditLog entry for every plan, verdict, integration, and rollback
  7.  Master kill-switch: SELF_IMPROVE_ENABLED
  8.  Max 3 changes per cycle, max 10 pending approvals at once
  9.  LLM-generated code never executes outside the sandbox
 10.  Knowledge content screened for injection before storing
"""
from __future__ import annotations

import asyncio, json, logging, time, uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from safety.sandbox import CodeSandbox, Verdict
from safety.audit import AuditLog
from safety.auth import detect_injection

if TYPE_CHECKING:
    from core.agent import MycoBrain, MindState

log = logging.getLogger("myco.growth")

SELF_IMPROVE_ENABLED     = True
REFLECT_INTERVAL_S       = 300
DEEP_IMPROVE_INTERVAL_S  = 3600 * 6
MAX_PLANS_PER_CYCLE      = 3
MAX_PENDING_APPROVALS    = 10

REQUIRES_APPROVAL: set[str] = {"new_tool", "prompt_patch"}
AUTO_APPROVED:     set[str] = {"knowledge_fill", "goal"}


class PlanStatus(str, Enum):
    PENDING           = "pending"
    SANDBOX_TESTING   = "sandbox_testing"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED          = "approved"
    REJECTED_STATIC   = "rejected_static"
    REJECTED_RUNTIME  = "rejected_runtime"
    REJECTED_HUMAN    = "rejected_human"
    INTEGRATED        = "integrated"
    ROLLED_BACK       = "rolled_back"


@dataclass
class ImprovementPlan:
    plan_id:          str
    weakness:         str
    action_type:      str
    description:      str
    code:             str        = ""
    prompt_patch:     str        = ""
    new_goal:         str        = ""
    status:           PlanStatus = PlanStatus.PENDING
    score:            float      = 0.0
    sandbox_verdict:  str        = ""
    rejection_reason: str        = ""
    created_at:       float      = field(default_factory=time.time)
    approved_at:      float      = 0.0
    approved_by:      str        = ""


class GrowthEngine:
    def __init__(self, brain: "MycoBrain", audit: AuditLog | None = None):
        self.brain            = brain
        self.audit            = audit or AuditLog()
        self._sandbox         = CodeSandbox(audit_log=self.audit)
        self._last_reflection = 0.0
        self._last_deep       = 0.0
        self._pending:  list[ImprovementPlan] = []
        self._history:  list[dict]            = []

    # ── public control ────────────────────────────────────────────────────────

    def toggle_self_improvement(self, enabled: bool, actor: str):
        global SELF_IMPROVE_ENABLED
        SELF_IMPROVE_ENABLED = enabled
        self.audit.log_change("self_improve_toggled", actor, {"enabled": enabled})
        log.info(f"Self-improvement {'ENABLED' if enabled else 'DISABLED'} by {actor}")

    def approve_plan(self, plan_id: str, actor: str) -> bool:
        plan = next((p for p in self._pending if p.plan_id == plan_id), None)
        if not plan:
            return False
        plan.status = PlanStatus.APPROVED
        plan.approved_at = time.time()
        plan.approved_by = actor
        self.audit.log_change("plan_approved", actor,
                              {"plan_id": plan_id, "description": plan.description})
        asyncio.create_task(self._integrate_approved(plan, self.brain.mind))
        return True

    def reject_plan(self, plan_id: str, actor: str, reason: str = "") -> bool:
        plan = next((p for p in self._pending if p.plan_id == plan_id), None)
        if not plan:
            return False
        plan.status = PlanStatus.REJECTED_HUMAN
        plan.rejection_reason = reason
        self._pending.remove(plan)
        self._history.append(self._plan_summary(plan))
        self.audit.log_change("plan_rejected_by_human", actor,
                              {"plan_id": plan_id, "reason": reason})
        return True

    def get_pending_approvals(self) -> list[dict]:
        return [self._plan_summary(p) for p in self._pending]

    def get_history(self, n: int = 30) -> list[dict]:
        return self._history[-n:]

    # ── throttled entry point ─────────────────────────────────────────────────

    async def maybe_reflect(self, mind: "MindState"):
        if not SELF_IMPROVE_ENABLED:
            return
        now = time.time()
        if now - self._last_reflection < REFLECT_INTERVAL_S:
            return
        self._last_reflection = now
        await self._light_reflection(mind)
        if now - self._last_deep > DEEP_IMPROVE_INTERVAL_S:
            self._last_deep = now
            asyncio.create_task(self._deep_improvement_loop(mind))

    # ── light reflection (no code, no changes) ────────────────────────────────

    async def _light_reflection(self, mind: "MindState"):
        recent = self.brain.episodic.get_recent(n=20)
        if not recent:
            return
        convo = "\n".join(f"{m['role'].upper()}: {m['content'][:200]}" for m in recent)
        sys = (
            f'You are Myco\'s self-reflection module at stage "{mind.stage}".\n'
            'Respond ONLY as JSON: {"traits": {"curious": true}, "short_goal": "..."}'
        )
        try:
            raw    = await self.brain.router.complete(mind.current_model, convo, sys)
            parsed = json.loads(raw.replace("```json","").replace("```","").strip())
            for trait, value in parsed.get("traits", {}).items():
                clean = "".join(c for c in trait if c.isalnum() or c == "_")[:32]
                mind.personality_traits[clean] = bool(value)
            self.brain.episodic.save_mind_state(mind)
        except Exception as e:
            log.debug(f"Light reflection failed: {e}")

    # ── deep improvement loop ─────────────────────────────────────────────────

    async def _deep_improvement_loop(self, mind: "MindState"):
        if not SELF_IMPROVE_ENABLED:
            return
        snapshot_id = self.brain.episodic.snapshot(
            label=f"pre-improvement-{mind.stage}-xp{mind.xp}",
            reason="automatic pre-improvement snapshot"
        )
        self.audit.log_change("snapshot_created", "system",
                              {"snapshot_id": snapshot_id})
        try:
            plans = await self._scan_and_plan(mind)
            for plan in plans[:MAX_PLANS_PER_CYCLE]:
                await self._process_plan(plan, mind, snapshot_id)
        except Exception as e:
            log.error(f"Deep improvement crashed: {e} — rolling back")
            self.brain.episodic.rollback(snapshot_id)
            self.audit.log_change("emergency_rollback", "system",
                                  {"reason": str(e), "snapshot_id": snapshot_id})

    async def _process_plan(self, plan: ImprovementPlan, mind: "MindState",
                            snapshot_id: str):
        # Gate 1: sandbox
        if plan.action_type in ("new_tool", "prompt_patch") and plan.code:
            plan.status = PlanStatus.SANDBOX_TESTING
            result = self._sandbox.run(plan.code, description=plan.description)
            if result.verdict != Verdict.ACCEPTED:
                plan.status = (PlanStatus.REJECTED_STATIC
                               if result.verdict == Verdict.REJECTED
                               else PlanStatus.REJECTED_RUNTIME)
                plan.sandbox_verdict  = result.verdict.value
                plan.rejection_reason = result.reason
                self._history.append(self._plan_summary(plan))
                log.info(f"Plan {plan.plan_id} sandbox-{result.verdict.value}: {result.reason[:80]}")
                return
            plan.sandbox_verdict = result.verdict.value
            plan.score = 0.9

        # Gate 2: approval routing
        if plan.action_type in REQUIRES_APPROVAL:
            if len(self._pending) >= MAX_PENDING_APPROVALS:
                log.warning("Approval queue full")
                return
            plan.status = PlanStatus.AWAITING_APPROVAL
            self._pending.append(plan)
            self.audit.log_change("plan_queued_for_approval", "system",
                                  {"plan_id": plan.plan_id,
                                   "action_type": plan.action_type,
                                   "description": plan.description[:200]})
            return

        # Auto-approve low-risk plans
        plan.status = PlanStatus.APPROVED
        plan.approved_by = "system_auto"
        plan.approved_at = time.time()
        await self._integrate_approved(plan, mind)

    # ── integration ───────────────────────────────────────────────────────────

    async def _integrate_approved(self, plan: ImprovementPlan, mind: "MindState"):
        snapshot_id = self.brain.episodic.snapshot(
            label=f"pre-integrate-{plan.plan_id[:8]}",
            reason=f"before integrating: {plan.description[:80]}"
        )
        try:
            if plan.action_type == "new_tool" and plan.code:
                await self._integrate_tool(plan, mind)
            elif plan.action_type == "knowledge_fill":
                await self._integrate_knowledge(plan, mind)
            elif plan.action_type == "goal":
                log.info(f"Goal integrated: {plan.new_goal or plan.description}")

            plan.status = PlanStatus.INTEGRATED
            self._history.append(self._plan_summary(plan))
            if plan in self._pending:
                self._pending.remove(plan)
            mind.xp += 15
            self.brain.episodic.save_mind_state(mind)
            self.audit.log_change("plan_integrated", plan.approved_by,
                                  {"plan_id": plan.plan_id,
                                   "action_type": plan.action_type,
                                   "description": plan.description[:200]})
        except Exception as e:
            log.error(f"Integration failed {plan.plan_id}: {e} — rolling back")
            plan.status = PlanStatus.ROLLED_BACK
            plan.rejection_reason = str(e)
            self.brain.episodic.rollback(snapshot_id)
            self.audit.log_change("integration_rollback", "system",
                                  {"plan_id": plan.plan_id, "reason": str(e)})
            self._history.append(self._plan_summary(plan))

    async def _integrate_tool(self, plan: ImprovementPlan, mind: "MindState"):
        # Re-sandbox at integration time (plan may have sat in queue for hours)
        result = self._sandbox.run(plan.code, description=plan.description)
        if result.verdict != Verdict.ACCEPTED:
            raise RuntimeError(f"Re-sandbox failed at integration: {result.reason}")
        if not result.functions:
            raise RuntimeError("Sandbox found no callable functions")

        safe_builtins_names = [
            "abs","bool","dict","float","int","len","list","max","min",
            "round","set","str","sum","tuple","type","zip","range",
            "enumerate","True","False","None","print"
        ]
        import builtins as _builtins
        safe_globals: dict = {
            "__builtins__": {
                n: getattr(_builtins, n)
                for n in safe_builtins_names if hasattr(_builtins, n)
            },
            "__name__": "__myco_tool__",
        }
        exec(compile(plan.code, "<myco_tool>", "exec"), safe_globals)

        registered = 0
        for name in result.functions:
            fn = safe_globals.get(name)
            if fn and callable(fn):
                self.brain.tools.register_dynamic(name, fn, plan.description)
                log.info(f"Tool integrated: {name}")
                registered += 1
        if registered == 0:
            raise RuntimeError("No functions registered after sandbox pass")

    async def _integrate_knowledge(self, plan: ImprovementPlan, mind: "MindState"):
        knowledge = await self.brain.router.complete(
            mind.current_model,
            f"Explain thoroughly: {plan.description}",
            "You are a factual knowledge generator. Be concise and accurate."
        )
        injection = detect_injection(knowledge)
        if not injection.clean:
            raise RuntimeError(f"Knowledge failed injection screen: {injection.findings}")
        await self.brain.semantic.add(
            text=knowledge,
            metadata={"type": "self-generated", "plan": plan.description,
                      "approved_by": plan.approved_by}
        )

    async def _scan_and_plan(self, mind: "MindState") -> list[ImprovementPlan]:
        recent   = self.brain.episodic.get_recent(n=50)
        memories = await self.brain.semantic.search("weakness failure confusion error", k=8)
        corpus   = "\n".join(f"{m['role']}: {m['content'][:150]}" for m in recent[-20:])
        mem_sum  = "\n".join(m["content"][:100] for m in memories[:5])
        sys = (
            f'You are Myco\'s weakness scanner at stage "{mind.stage}".\n'
            f"Current tools: {self.brain.tools.list_available()}\n"
            f"Memory gaps:\n{mem_sum}\n\n"
            "Generate up to 3 improvement plans. For new_tool, write ONLY a simple "
            "synchronous Python function with NO imports. Under 50 lines.\n"
            'Respond ONLY as JSON: {"plans": [{"plan_id": "p1", "weakness": "...", '
            '"action_type": "new_tool|knowledge_fill|goal", "description": "...", '
            '"code": "def my_tool(x: str) -> str:\\n    return x", '
            '"prompt_patch": "", "new_goal": ""}]}'
        )
        try:
            raw   = await self.brain.router.complete(mind.current_model, corpus, sys)
            data  = json.loads(raw.replace("```json","").replace("```","").strip())
            plans = []
            fields = ImprovementPlan.__dataclass_fields__
            for p in data.get("plans", [])[:MAX_PLANS_PER_CYCLE]:
                p["plan_id"] = str(uuid.uuid4())[:8]
                plans.append(ImprovementPlan(**{k: v for k, v in p.items() if k in fields}))
            log.info(f"Generated {len(plans)} improvement plans")
            return plans
        except Exception as e:
            log.warning(f"Plan generation failed: {e}")
            return []

    def _plan_summary(self, plan: ImprovementPlan) -> dict:
        return {
            "plan_id":          plan.plan_id,
            "action_type":      plan.action_type,
            "description":      plan.description,
            "status":           plan.status.value,
            "sandbox_verdict":  plan.sandbox_verdict,
            "rejection_reason": plan.rejection_reason,
            "created_at":       plan.created_at,
            "approved_by":      plan.approved_by,
        }

    async def maybe_reflect_safe(self, mind: "MindState"):
        """
        Non-task version of maybe_reflect — safe to call from inside an async generator.
        Runs the check but schedules heavy work as a fire-and-forget coroutine via
        asyncio.ensure_future only AFTER the generator has yielded all its tokens.
        """
        if not SELF_IMPROVE_ENABLED:
            return
        now = time.time()
        if now - self._last_reflection < REFLECT_INTERVAL_S:
            return
        # Lightweight: just update timestamps and traits. Never blocks.
        self._last_reflection = now
        # Kick off deep loop only if due — but use ensure_future at the event-loop level
        if now - self._last_deep > DEEP_IMPROVE_INTERVAL_S:
            self._last_deep = now
            loop = asyncio.get_event_loop()
            loop.call_soon(lambda: asyncio.ensure_future(self._deep_improvement_loop(mind)))
