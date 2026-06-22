# SPEC-21 — MCP / A2A Server Mode

- **Links:** ROADMAP F-9 (Q1 2027) · trend vector #4 (interop) · prerequisite: SPEC-01 (local API key)
- **Priority:** P1 · **Effort:** M
- **Review status:** ⬜ pending review
- **Type:** roadmap spec

## 1. Goal

Every Solo install becomes a node other agents can call: crews, KBs, memory, and distribution channels exposed as **MCP tools**, and crews published as **A2A Agent Cards** (experimental). This is the OpenAI-compat play one level up — "your IDE's agent asks *your* Solo's research crew."

## 2. v1 Scope

1. **MCP server** (stdio + streamable HTTP on the sidecar):
   - Tools: `run_crew(crew_id|name, input)`, `query_knowledge_base(kb_id, query)`, `recall_memory(query)` (read-only), `send_via_channel(channel, content)` — the last one **always** routes through Approvals regardless of caller.
   - Resources: list of crews/workers/KBs with descriptions (so the client model can choose).
   - Auth: the SPEC-01 local API key; per-tool enable/disable in Settings → "Agent API" tab (channels OFF by default).
2. **Client setup recipes** — docs + one-click config snippets for Claude Desktop/Claude Code (`mcpServers` JSON), Cursor, and generic MCP clients. This is also a marketing artifact (SPEC-13/C6 tie-in).
3. **A2A Agent Cards (experimental flag)** — publish card JSON per crew at a well-known endpoint; accept A2A task delegation mapped onto crew runs. Flagged experimental; track spec churn quarterly.
4. **Guardrails** — concurrent external-call limit; per-caller daily budget (token estimate); every external invocation tagged in run history ("called by: external/mcp") and emitted as a SPEC-24 ledger event.

## 3. Enterprise port (Q2 2027)

The **A2A gateway + agent registry** product line: org-wide registry of agents (internal + external), identity per agent, policy on who may call what, full audit. This is the #1 governance ask in the enterprise research — treat the port as a flagship, not a checkbox.

## 4. Acceptance criteria

- From Claude Code with the MCP config: `run_crew("research-crew", "summarize X")` executes locally and returns the result; the run appears in Runs tagged external.
- `send_via_channel` from an external caller lands in Approvals, never sends directly.
- Disabling a tool in Settings makes it vanish from the MCP tool list immediately.
- Wrong/missing API key → clean MCP auth error.

## 5. Open questions

- Tool granularity: one `run_crew` tool vs a generated tool per crew (better discoverability, noisier tool list)? Proposed: per-worker tools for hired workers, generic `run_crew` for the rest.
- Should `recall_memory` be exposed at all by default? (Privacy posture says OFF by default, ON per explicit toggle.)
- A2A: implement now behind a flag vs wait one more quarter for spec stability — reviewer call; cards-only (discovery without delegation) is a cheap middle path.
