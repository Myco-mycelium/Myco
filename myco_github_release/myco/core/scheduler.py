"""
myco/core/scheduler.py
======================
Background job scheduler for Myco's autonomous maintenance tasks.
Uses APScheduler to run nightly memory consolidation, health checks, and growth triggers.

Jobs:
  - memory_consolidation   : nightly at 03:00 — compress episodic → semantic
  - growth_heartbeat       : every 10 minutes — trigger light reflection if due
  - audit_integrity_check  : daily — verify audit chain has not been tampered
  - health_ping            : every 60 seconds — mark models healthy/unhealthy
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

log = logging.getLogger("myco.scheduler")

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    _HAS_APSCHEDULER = True
except ImportError:
    _HAS_APSCHEDULER = False
    log.warning("APScheduler not installed — background jobs disabled. pip install apscheduler")

if TYPE_CHECKING:
    from core.agent import MycoBrain


class MycoClock:
    """
    Wraps APScheduler to run Myco's background jobs.
    Gracefully degrades if APScheduler is not installed.
    """

    def __init__(self, brain: "MycoBrain"):
        self.brain     = brain
        self._scheduler = None
        self._running   = False

    def start(self):
        if not _HAS_APSCHEDULER:
            log.warning("APScheduler unavailable — no background jobs will run.")
            return
        if self._running:
            return

        self._scheduler = AsyncIOScheduler(timezone="UTC")

        # 1. Memory consolidation — nightly at 03:00 UTC
        self._scheduler.add_job(
            self._consolidate_memory,
            CronTrigger(hour=3, minute=0),
            id="memory_consolidation",
            name="Nightly memory consolidation",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # 2. Growth heartbeat — every 30 minutes (reduced from 10 for low-end PCs)
        heartbeat_mins = int(os.getenv("MYCO_HEARTBEAT_MINS", "30"))
        self._scheduler.add_job(
            self._growth_heartbeat,
            IntervalTrigger(minutes=heartbeat_mins),
            id="growth_heartbeat",
            name="Growth heartbeat",
            replace_existing=True,
        )

        # 3. Audit integrity check — daily at 04:00 UTC
        self._scheduler.add_job(
            self._check_audit_integrity,
            CronTrigger(hour=4, minute=0),
            id="audit_check",
            name="Daily audit chain integrity check",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # 4. Model health reset — every 5 minutes
        self._scheduler.add_job(
            self._reset_model_health,
            IntervalTrigger(minutes=5),
            id="model_health",
            name="Model health reset",
            replace_existing=True,
        )

        # 5. Graph persistence — every 15 minutes
        self._scheduler.add_job(
            self._persist_graph,
            IntervalTrigger(minutes=15),
            id="graph_persist",
            name="Knowledge graph persistence",
            replace_existing=True,
        )

        self._scheduler.start()
        self._running = True

        # Start the autonomous learner
        self.brain.learner.start()
        log.info("MycoClock started — background jobs active")

    def stop(self):
        if self._scheduler and self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
        self.brain.learner.stop()
        self.brain.graph.save()
        log.info("MycoClock stopped")

    # ── job implementations ───────────────────────────────────────────────────

    async def _consolidate_memory(self):
        """Compress episodic memory into semantic store. Deduplicate near-duplicates."""
        log.info("[scheduler] Starting nightly memory consolidation...")
        try:
            count_before = self.brain.semantic.count()
            await self.brain.semantic.consolidate()
            count_after  = self.brain.semantic.count()
            log.info(f"[scheduler] Consolidation done: {count_before} → {count_after} semantic memories")
            self.brain.audit.log("API", "memory_consolidation", "scheduler",
                                  {"before": count_before, "after": count_after})
        except Exception as e:
            log.error(f"[scheduler] Memory consolidation failed: {e}")

    async def _growth_heartbeat(self):
        """Trigger light reflection if the interval has elapsed."""
        try:
            await self.brain.growth.maybe_reflect(self.brain.mind)
        except Exception as e:
            log.error(f"[scheduler] Growth heartbeat failed: {e}")

    async def _check_audit_integrity(self):
        """Verify the audit chain has not been tampered with."""
        try:
            valid, message = self.brain.audit.verify()
            if valid:
                log.info("[scheduler] Audit chain: OK")
            else:
                log.critical(f"[scheduler] AUDIT CHAIN INTEGRITY FAILURE: {message}")
                # In production: send alert, page on-call, halt self-improvement
                self.brain.growth.toggle_self_improvement(False, "scheduler-integrity-check")
        except Exception as e:
            log.error(f"[scheduler] Audit check failed: {e}")

    async def _reset_model_health(self):
        """Models are marked unhealthy for 60s after failure. This logs current state."""
        try:
            models_dict = self.brain.router.list_models()
            total = sum(len(v) for v in models_dict.values())
            log.debug(f"[scheduler] {total} models in rotation")
        except Exception as e:
            log.error(f"[scheduler] Model health check failed: {e}")

    async def _persist_graph(self):
        """Periodically save the knowledge graph to disk."""
        try:
            self.brain.graph.save()
            log.debug("[scheduler] Knowledge graph saved")
        except Exception as e:
            log.error(f'[scheduler] Graph persist failed: {e}')
