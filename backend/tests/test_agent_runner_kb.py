"""Tests for the KB-binding resolver used by the workspace agent runner."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.workspace.agent_runner import resolve_kb_ids


def test_agent_overrides_crew():
    assert resolve_kb_ids(
        agent={"knowledge_base_ids": ["a"]},
        crew={"knowledge_base_ids": ["b"]},
    ) == ["a"]


def test_agent_empty_falls_back_to_crew():
    assert resolve_kb_ids(
        agent={"knowledge_base_ids": []},
        crew={"knowledge_base_ids": ["c"]},
    ) == ["c"]


def test_both_empty_returns_empty():
    assert resolve_kb_ids(agent={}, crew={}) == []


def test_missing_keys_treated_as_empty():
    # ``None`` field on the agent should still fall back to the crew
    assert resolve_kb_ids(
        agent={"knowledge_base_ids": None},
        crew={"knowledge_base_ids": ["only-crew"]},
    ) == ["only-crew"]
