# SPEC-13 — Marketing Site Quick Wins

- **Links:** GAPS MKT-1..7 · FEATURES C1–C7
- **Repo:** `contextuai-marketing-site` (NOT the solo repo)
- **Priority:** P1 · **Effort:** S–M (bundle of small items)
- **Review status:** ⬜ pending review
- **Note for reviewer:** C5 (KB landing page) and C6 (For Developers section) involve real copywriting — drafts should come back to you for tone approval before deploy.

## 1. Goal

Close the discoverability/credibility gaps on the site: no dead links, the orphaned cookbook reachable, Reddit + developer-facing features visible, basic SEO hygiene in place.

## 2. Context

Static Vite + Handlebars site (`partials/` for shared nav/footer), Tailwind, Firebase Hosting (`firebase.json`). Pages: index, solo, features, crews, enterprise, docs, cookbook. Deploy via Firebase CLI.

## 3. Work items

1. **(MKT-1)** Add Reddit to the channels grid on `solo.html` (logo + one-liner: inbound polling, keyword triggers, auto-reply with approval). Check `index.html`/`features.html` channel mentions for consistency.
2. **(MKT-2)** Link `cookbook.html` from navbar (under a "Learn"/"Resources" item) and footer — edit the shared partials, verify on every page.
3. **(MKT-3)** Footer + blog placeholders: replace each `href="#"` with a real target or remove the item. The 3 homepage blog cards: hide the section behind a comment until real posts exist (or write them — reviewer call).
4. **(MKT-4)** Persistent "Download Solo (Free)" CTA in the navbar (links to GitHub releases — confirm the canonical download URL).
5. **(MKT-5)** `public/robots.txt` + `public/sitemap.xml` (all routed pages); custom `404.html` wired in `firebase.json`; pass over `<img>` alt text on solo/features pages (descriptive, feature-named).
6. **(MKT-6a / C6)** "For Developers" section on `solo.html` (or features): OpenAI-compatible API at `localhost:18741/v1` with 3 short recipes (Continue.dev, Aider, Cursor) — copy drafts for review.
7. **(MKT-6b / C5)** New `knowledge.html` landing page: folder-mapped local RAG story (pick folder → auto-sync 1h/6h/24h → cited answers), screenshots from the app, CTA to download. Copy draft for review.
8. **(MKT-7)** Verify `firestore.rules` and `functions/` referenced by `firebase.json` exist and deploy cleanly (`firebase deploy --only hosting` dry-run at minimum); fix or remove references. Replace outdated "Workshop" naming on `index.html` with current Crews/Projects naming.

## 4. Acceptance criteria

- Zero `href="#"` anchors site-wide (`grep -r 'href="#"' --include=*.html` clean, excluding legitimate same-page anchors like `href="#features"`).
- Cookbook reachable from every page; Reddit visible on solo page; navbar CTA present on all pages.
- `vite build` clean; all pages render locally; Firebase deploy config validates.
- Sitemap lists every routed page; 404 page serves on a bogus path in Firebase emulator/preview.

## 5. Out of scope

Pricing page, changelog page, competitive-comparison page, video walkthroughs (FEATURES Tier 2/3 — separate effort after these land).
