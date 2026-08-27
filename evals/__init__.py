"""HireLoop AI evaluation harness (Phase 6, Parts 18-25).

This package exercises real backend code (agents, services, and the
LangGraph workflow) end to end, offline and deterministically, via the
Mock LLM provider. It is a separate, additional layer on top of the
pytest suite in tests/ -- it does not duplicate or modify those tests.

Run with: python -m evals.run_evals
"""
