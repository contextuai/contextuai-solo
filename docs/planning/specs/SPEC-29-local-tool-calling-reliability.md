# SPEC-29 — Local Tool-Calling Reliability Layer

- **Links:** MARKET-PAINS-2026 P-3 · relates to SPEC-23 (evals), crew system, `agent_runner.py`, llama-cpp-python local inference
- **Priority:** P1 · **Effort:** M-L
- **Review status:** ⬜ pending review
- **Type:** gap-driven product spec (community pain research)
- **Why ours is different:** the #1 agent complaint is "works on Claude, breaks locally" — small models emit invalid tool calls and loop forever. Because we own the llama.cpp stack we can constrain decoding at the sampler level (grammars), which frameworks bolted onto a cloud API cannot. This is the difference between agents that demo and agents that work — and we are agent-first, so it matters more to us than to anyone.

## 1. Problem

The same crew/agent logic that runs cleanly against a cloud API degrades badly on a local 8B: malformed tool-call JSON, wrong/irrelevant tool selection, bad arguments, and — most visibly — infinite loops where the model calls a tool repeatedly without ever producing a final answer (openai-agents #1544: *"keeps calling the tool over and over... Is this an issue or user error?"*). Users blame themselves or conclude local agents are useless. For an agent-first product this is existential, not cosmetic.

## 2. v1 Scope

Four layers, each independently valuable:

1. **Grammar-constrained tool calls (the big one).** When a local model must emit a tool call, constrain generation with a GBNF grammar derived from the tool's JSON schema so the output is *syntactically guaranteed* valid. llama-cpp-python supports grammar-based sampling — wire the tool schema → grammar at the inference call in the local path. This eliminates the malformed-JSON class of failures outright.
2. **Tolerant parser (fallback for non-grammar paths / cloud-via-Ollama).** When a tool call comes back as text (no grammar available), a forgiving parser: extract JSON from markdown fences, repair common breakage (trailing commas, single quotes, unescaped newlines), and validate against the tool schema before dispatch. On failure, one structured **repair retry** ("your last tool call was invalid JSON; here is the schema; re-emit only the JSON") before giving up.
3. **Loop detection / circuit breaker.** Track (tool name + normalized args) per agent turn. If the same call repeats N times (default 3), or total tool calls in a turn exceed a cap, break the loop and force a final-answer turn ("you've called tools enough; answer with what you have"). Surface it instead of hanging. Configurable, with sane defaults.
4. **Honest failure + retry budget.** When an agent genuinely can't produce a valid action after the budget, return a clear "this local model struggled with this tool task" message — and, if a cloud key is configured, *offer* (not force) escalating that step to a stronger model. Ties to P-7 hybrid framing.

## 3. Architecture sketch

- **Where:** the tool-execution path in `services/workspace/agent_runner.py` (and the crew runner that shares it). Add a `tool_call_guard` module that wraps: schema→grammar compilation, the tolerant parse+repair, and loop tracking. Keep it model-agnostic so cloud paths benefit from loop detection + parsing even though they rarely need the grammar.
- **Grammar:** generate GBNF from each tool's parameter schema at registration time (cache it). For the local path, pass it through to the llama-cpp-python call. Verify current llama-cpp-python version supports the grammar kwarg in this codebase before committing.
- **Loop state:** per-run, in-memory, keyed by run id; emit a SPEC-24 ledger event when a circuit-breaker trips (visible, auditable).
- **Observability:** record per-step tool-call validity + retry counts so SPEC-23 evals can measure "tool-call success rate per model" — this metric becomes a catalog signal (which models are actually agent-capable, feeding SPEC-27's badges).

## 4. Enterprise port

Same guard server-side; the tool-call success metrics roll into the governance/evals dashboard. "Which models are reliable for agentic work" becomes an admin-visible, data-backed answer rather than folklore.

## 5. Acceptance criteria

- A local small model (e.g. an 8B in the catalog) driving a 2-tool crew completes a task that previously looped, with no malformed-JSON dispatch errors. (Reproduce a known-bad case first; assert it passes after.)
- Grammar-constrained path: a unit/integration test asserts emitted tool calls always parse + validate against the schema across a sample of prompts.
- Loop guard: a forced-repeat scenario trips the circuit breaker within N calls, returns a final answer, and logs a ledger event — no hang.
- Tolerant parser repairs a curated set of real-world malformed outputs (fenced JSON, trailing comma, single quotes) and rejects unrepairable ones cleanly.
- Cloud paths are unaffected except for added loop protection.

## 6. Out of scope (v1)

Fine-tuning models for tool use; multi-tool planning/reflection frameworks; changing the crew execution-mode design. This spec hardens the *mechanics* of a single tool call and the loop around it, not the orchestration model.

## 7. Open questions

- Does the pinned llama-cpp-python version expose grammar sampling through the call path we use? If not, what's the upgrade cost? (Verify first — this gates layer 1.)
- Grammar generation for deeply nested / union schemas can get hairy — cap supported schema complexity in v1 and fall back to the tolerant parser for the rest.
- Default loop thresholds: 3 identical / 10 total per turn proposed — tune against real crews before locking.
