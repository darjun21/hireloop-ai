"""
Reserved for LLM structured-output schemas used only at the agent call
boundary (e.g. tool-call argument schemas), once agents are implemented in
a later phase.

Domain models live in their own dedicated modules instead:
MatchAnalysis -> src/models/match_analysis.py
ResumeModification -> src/models/resume_modification.py
TruthGuardResult -> src/models/truth_guard.py

Nothing implemented yet in this phase.
"""

from __future__ import annotations
