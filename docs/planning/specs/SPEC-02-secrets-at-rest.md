# SPEC-02 — Secrets at Rest

- **Links:** GAPS SEC-2 · FEATURES B2
- **Priority:** P1 · **Effort:** M
- **Review status:** ⬜ pending review

## 1. Goal

Cloud provider API keys and channel tokens are no longer readable by opening `~/.contextuai-solo/data/contextuai.db` in a SQLite browser (or by a cloud-sync service backing it up).

## 2. Context (verify before coding)

- Keys live as plaintext JSON in collections: `cloud_provider_keys` (`services/cloud_provider_service.py`), plus channel credentials (`reddit_accounts`, Telegram/Discord/Twitter tokens, SMTP/SendGrid, blog API keys) stored by the connections routers.
- `backend/models/cloud_provider_models.py` has an explicit "no encryption layer in v1" note.
- The backend is Python (PyInstaller-frozen); the Tauri shell is Rust — either side could hold the master key.

## 3. Plan (proposed — reviewer may prefer alternative)

1. **Master key via OS credential store, owned by the backend** (keeps Rust changes zero): use the `keyring` library (Windows Credential Manager / macOS Keychain / Secret Service). On first start, generate a 32-byte key, store under service `contextuai-solo`, account `db-master-key`.
2. **Field-level encryption helper** `services/secret_store.py`: `encrypt(str) -> "enc:v1:<fernet>"`, `decrypt(str)` that passes through non-`enc:`-prefixed values (= seamless migration of existing rows).
3. **Apply at the service layer, not the adapter:** wrap the specific secret fields (`api_key`, `secret`, `token`, `password`, `webhook_url`-credentials) on save/load in: `cloud_provider_service.py`, reddit/telegram/discord/twitter/linkedin/instagram/facebook/blog/email connection services. Grep for where each collection is written.
4. **Lazy migration:** on read, if a value lacks the `enc:` prefix, re-save encrypted. Plus one startup migration pass over the known collections.
5. **Fallback:** if `keyring` is unavailable (headless docker), fall back to a key file `~/.contextuai-solo/data/.master-key` with 0600 perms, and log a warning. (Reviewer: acceptable?)
6. Add `keyring` + `cryptography` to `requirements.txt` (pinned) and to the PyInstaller spec hidden imports if needed.

## 4. Acceptance criteria

- New keys saved → DB row contains `enc:v1:` blob, not the key.
- Existing plaintext rows keep working and become encrypted after first read or the startup migration.
- Test-connection flows for at least Anthropic + Telegram still pass.
- Works in pytest (keyring mocked or file fallback).

## 5. Out of scope

Full-DB encryption (SQLCipher) — heavier, breaks aiosqlite; revisit only if field-level proves insufficient. KB content/chat history encryption.

## 6. Test plan

- Unit tests for `secret_store` round-trip + passthrough + migration.
- Integration test: save provider key → read raw row via sqlite3 → assert no plaintext.
