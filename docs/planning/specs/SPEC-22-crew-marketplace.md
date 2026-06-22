# SPEC-22 — Crew & Worker Marketplace v1

- **Links:** ROADMAP F-10 (Q1 2027) · FEATURES A5 · MOONSHOT BL-5 · depends on SPEC-18 (workers shareable)
- **Priority:** P1 · **Effort:** M
- **Review status:** ⬜ pending review
- **Type:** roadmap spec

## 1. Goal

Users share crews and Digital Workers; the community becomes the content engine. Export/import locally, plus an in-app "Community" tab fed from a public GitHub repo — the cheapest acquisition channel an OSS desktop app has.

## 2. v1 Scope

1. **Export** — crew or worker → single JSON: schema_version, metadata (name, description, author, tags), agents (full prompt configs), execution mode, triggers, blueprint refs, KB *descriptions* (not content), channel bindings as **typed placeholders** (`{platform: telegram, purpose: "support inbox"}`). **Secrets and credentials never serialize** (assert in tests, not just code review).
2. **Import** — validate schema, clone with new IDs, then a **fix-up wizard**: bind placeholders to the user's real connections/KBs (or skip → crew imports paused with "needs setup" badges).
3. **Community repo** — public `contextuai-crews` GitHub repo: one folder per template (`template.json` + `README.md` + optional screenshot), CI validates schema + scans for secrets/URLs on every PR, `manifest.json` built by CI.
4. **In-app Community tab** — in the crews/workers library picker: fetches the manifest (cache 24h, fully optional/offline-safe), browse/search/install. Install = import flow above. Submissions are PRs (link out; in-app submission is v2).
5. **Moderation** — PR review + CI scanning is the v1 moderation story; templates run with the same approval gates as anything else (a malicious prompt can't send outbound silently). Document the threat model honestly in the repo README.

## 3. Enterprise port

Private org registry: "approved workers only" policy, internal submission/review flow, version pinning. Same JSON schema — design the schema with org metadata fields reserved from day one.

## 4. Acceptance criteria

- Round-trip: export a 4-agent crew with a Telegram binding on machine A → import on machine B → fix-up wizard binds B's Telegram → crew runs. Raw JSON contains zero tokens/keys (automated test greps for credential shapes).
- Schema versioning: importing a future-versioned file fails with a clear "update the app" message.
- Community tab renders the live repo manifest, installs a template end-to-end, and works (degrades to hidden) offline.

## 5. Open questions

- License for community templates (CC0 vs Apache-2.0)? Affects enterprise reuse.
- Ratings/install counts need telemetry we don't collect — launch without numbers (curated "featured" instead), or add opt-in anonymous install pings? (Privacy posture suggests: featured-only.)
- Naming: "Community Crews" vs "Worker Marketplace" — align with SPEC-18 naming decision.
