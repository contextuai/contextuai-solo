"""SPEC-29: Grammar-Locked Local Tool Calling & Loop Guard (`backend/services/tool_call_guard.py`) tests."""
from services.tool_call_guard import (
    ToolLoopCircuitBreaker,
    parse_and_repair_tool_call,
    schema_to_gbnf,
)


def test_schema_to_gbnf_contains_tool_names():
    tools = [
        {"function": {"name": "web_search", "description": "Search the web"}},
        {"function": {"name": "read_document", "description": "Read a KB doc"}},
    ]
    grammar = schema_to_gbnf(tools)
    assert "root ::=" in grammar
    assert "web_search" in grammar
    assert "read_document" in grammar


def test_parse_and_repair_tool_call_handles_fences_and_trailing_commas():
    # 1. Markdown fenced JSON with trailing comma
    raw1 = """Here is the tool call:
```json
{
  "tool": "web_search",
  "arguments": {"query": "contextuai local gguf",},
}
```"""
    parsed1 = parse_and_repair_tool_call(raw1, allowed_tools=["web_search"])
    assert parsed1 == {
        "tool": "web_search",
        "arguments": {"query": "contextuai local gguf"},
    }

    # 2. <tool_call> XML tags with name/parameters keys
    raw2 = '<tool_call>{"name": "read_document", "parameters": {"doc_id": "123"}}</tool_call>'
    parsed2 = parse_and_repair_tool_call(raw2, allowed_tools=["read_document"])
    assert parsed2 == {
        "tool": "read_document",
        "arguments": {"doc_id": "123"},
    }

    # 3. Disallowed tool is rejected
    assert parse_and_repair_tool_call(raw2, allowed_tools=["web_search"]) is None


def test_tool_loop_circuit_breaker_trips_on_identical_or_max_calls():
    breaker = ToolLoopCircuitBreaker(max_identical=3, max_total=8)

    assert breaker.record_call("web_search", {"q": "same"})["tripped"] is False
    assert breaker.record_call("web_search", {"q": "same"})["tripped"] is False
    third = breaker.record_call("web_search", {"q": "same"})
    assert third["tripped"] is True
    assert "identical" in third["reason"]

    breaker.reset()
    for i in range(7):
        assert breaker.record_call("tool_a", {"step": i})["tripped"] is False
    eighth = breaker.record_call("tool_a", {"step": 7})
    assert eighth["tripped"] is True
    assert "maximum" in eighth["reason"] or "8" in eighth["reason"]
