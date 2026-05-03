# Knowledge Base Packs

Starter packs of curated documents that ContextuAI Solo users can download
and import into their local Knowledge Bases.

## Why

Every Solo user starts with an empty `/knowledge` page. The first 30 minutes
matter: a blank state kills momentum. These packs give people something to
play with the moment they install the app.

## Pack format

Each pack is a folder under this directory. Layout:

```
knowledge-base-packs/
└── irs-tax-2024/
    ├── manifest.json          # name, description, version, license, sources
    ├── README.md              # human-readable overview, download links
    └── docs/
        ├── 1040-instructions.pdf
        ├── standard-deductions.md
        └── ...
```

The desktop app does not ingest these directly. Instead, the build pipeline
zips each pack and publishes it to GitHub Releases (or the marketing site).
Users:

1. Click "Browse RAG packs" on the `/knowledge` page (TODO).
2. Pick a pack → it downloads + auto-creates a KB + uploads the docs.

For now, the pack is a `.zip` the user unpacks and drag-drops into a new KB.

## `manifest.json` schema

```json
{
  "id": "irs-tax-2024",
  "name": "US IRS Tax Forms (2024)",
  "description": "Form 1040 + schedules + standard deductions for tax year 2024.",
  "version": "1.0.0",
  "license": "Public domain (US Government)",
  "size_mb": 12,
  "doc_count": 18,
  "sources": [
    "https://www.irs.gov/forms-pubs/about-form-1040"
  ],
  "tags": ["tax", "personal-finance", "us"],
  "recommended_models": ["qwen3-3b-instruct", "gemma-4-9b"]
}
```

## The first three packs (planned)

1. **`irs-tax-2024/`** — IRS Form 1040 + common schedules + standard
   deductions. All public domain. Use case: "What's my standard deduction
   if I'm married filing jointly?"
2. **`personal-finance-101/`** — A curated reading list: index funds, tax-
   advantaged accounts, emergency fund sizing, budgeting frameworks. Sources:
   public articles + open-licensed books. Use case: "Should I max my Roth
   before paying down 5% student loans?"
3. **`cybersecurity-101/`** — NIST CSF, OWASP top 10, common phishing
   patterns, SOC 2 baseline controls. Sources: NIST + OWASP (both public).
   Use case: "What controls do I need for SOC 2 type 1?"

## Licensing

- Pack contents must be public-domain, openly licensed, or owned by us.
- Each pack's `manifest.json` declares its license.
- Don't ship copyrighted content (academic papers, news articles, etc.).

## Status

- [ ] `irs-tax-2024/` — sourcing in progress
- [ ] `personal-finance-101/` — planning
- [ ] `cybersecurity-101/` — planning
- [ ] Browse-and-install UI on `/knowledge` page
- [ ] Build pipeline (CI step that publishes `*.zip` to releases)
