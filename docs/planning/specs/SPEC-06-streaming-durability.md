# SPEC-06 — Streaming Message Durability + Ollama Abort Parity

- **Links:** GAPS REL-3, REL-4
- **Priority:** P1 · **Effort:** S–M
- **Review status:** ⬜ pending review

## 1. Goal

A completed (or partially streamed) assistant response is never silently lost, and aborting a stream stops backend work for every provider path, not just local models.

## 2. Context (verify before coding — audit-sourced line refs)

- `backend/routers/ai_chat.py`, `local_event_generator` (~lines 472-517): collects chunks; after the stream, `store_message(...)` is wrapped in `try/except Exception: pass` — DB lock (WAL checkpoint, concurrent write) = message lost with no trace.
- The Ollama streaming generator (~lines 607-628) catches only `Exception` — not `GeneratorExit`/`asyncio.CancelledError` — so client aborts don't mark disconnect, and behavior diverges from the local path. Check the Anthropic/OpenAI/Gemini/Bedrock paths for the same gap while in there.
- Messages get client-generated IDs (audit claim — verify in `lib/api/chat-client.ts` / backend models); resubmits may duplicate.

## 3. Plan

1. **Retry storage:** replace the bare `except: pass` with a small retry (3 attempts, 0.2/0.5/1s backoff) around `store_message` + `update_session_stats`. On final failure, `logger.error` with session id and persist the payload to `~/.contextuai-solo/data/failed_messages.jsonl` as a dead-letter (so nothing is ever fully lost). Apply to every provider path that stores after streaming — factor a shared `await _store_streamed_response(...)` helper instead of copy-paste.
2. **Abort parity:** add `except (GeneratorExit, asyncio.CancelledError): disconnected = True` handling to the Ollama generator (and any other provider generator missing it), mirroring the local path: stop iterating, still attempt to store the partial transcript, skip the `[DONE]` frame.
3. **Idempotent store (cheap dedup):** if the message model has a client-supplied `message_id`, make `store_message` upsert on it rather than insert. If IDs are server-generated, note that and skip this step.

## 4. Acceptance criteria

- Simulated DB lock during store (test monkeypatches first N calls to raise `sqlite3.OperationalError: database is locked`) → message still persisted.
- Aborting an Ollama stream from the client stops backend chunk consumption (observable via log/counter in test) and stores the partial message.
- No duplicate messages when the same `message_id` is stored twice.

## 5. Out of scope

Frontend reconnect/replay UX; token-level resume of interrupted generations.

## 6. Test plan

pytest: new tests per acceptance criterion (the chat router has existing test patterns to copy — find them under `backend/tests/`). Full suite green.
