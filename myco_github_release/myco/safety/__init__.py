# myco/safety/__init__.py
"""
Myco Security Layer
===================
All security concerns live here. Nothing in the rest of the codebase
should bypass this module.

Threat model (what we defend against):
  1. Prompt injection      — malicious text in user input tries to hijack the agent
  2. Code injection        — LLM-generated code with hidden malicious behaviour
  3. Sandbox escape        — generated code tries to break out of its execution jail
  4. Unauthenticated API   — any caller can read/write memory or trigger self-improvement
  5. Privilege escalation  — a user-level request trying to call admin endpoints
  6. Runaway self-improvement — Myco looping in unsafe self-modification without approval
  7. Data exfiltration     — generated code phoning home or reading secret files
  8. Supply-chain          — dynamically loaded code importing malicious packages
  9. Resource exhaustion   — sandbox running forever or consuming all CPU/RAM
 10. Audit gaps            — no record of what was run, by whom, and what changed
"""
