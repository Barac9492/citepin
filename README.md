# Citepin v0 (prototype)

A tiny FLOSS CLI + JSON schema for a **citation-grade pin of one public web page**.

This folder is a working prototype of the tool described in the NLnet Restack draft at `/workspace/income-bot/experiments/nlnet-draft/` (€19,800, DO NOT SUBMIT — calls are closed as of 2026-08-17). It is also the seed for a later [itch.io](https://itch.io/docs/creators/quality-guidelines) listing: **one original tool**, **disclosed AI**, **not a farm**.

A pin records: URL, UTC fetch time, HTTP status, media type, SHA-256 of the received payload, the robots.txt decision, and the tool version. Optional later (not in v0): WARC / WACZ pointer, minisign.

## What it is not

- Not a site-wide crawler
- Not a Wayback Machine or hosted archive
- Not a headless-browser / JavaScript renderer
- Not a login or paywall bypass
- Not a legal-admissibility / courtroom-evidence product

Replay of rich archives is out of scope here. JS-heavy pages that need a real browser are an explicit later interop path (attach a WACZ from Webrecorder tools), not something this v0 fakes.

## Authorship and license

- **Accountable human:** Ethan Cho
- **Author of this v0:** Income Bot (disclosed AI / Cursor agent), 2026-08-17, Asia/Seoul
- **License:** [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)
- See `NOTICE.md` (AI disclosure) and `schema-v0.md` (pin fields)

Copyright 2026 Ethan Cho

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.

This prototype is **purely AI-generated** in this session. NLnet will not pay for purely generated outcomes; do not invoice it as a grant milestone. Ethan remains accountable for any later human-reviewed release.

## How to run

Python 3, standard library only (`urllib`, `hashlib`, `json`, `argparse`, `html.parser`, `ssl`). No `pip install`.

```bash
git clone https://github.com/Barac9492/citepin.git && cd citepin

# Pin one public URL (honors robots.txt; no cookies; no auth; 30s timeout; 2 MiB cap)
python3 citepin.py add https://nlnet.nl/propose/

# Re-hash the stored payload if present; otherwise re-fetch and compare
python3 citepin.py verify pins/<pin>.json

# One markdown citation line (URL, fetch time, hash prefix)
python3 citepin.py cite pins/<pin>.json
```

User-Agent sent on every request:

```text
Citepin/0.1 (+https://github.com/Barac9492/citepin; disclosed-AI; research)
```

Pins land under `pins/` as JSON; the exact received bytes (or a 2 MiB prefix) land under `pins/payloads/`. The JSON is the citation record; the sidecar is only there so `verify` can re-hash without hitting the network.

### `verify` modes (exactly one per run)

1. **`stored-payload`** — if the pin says `payload_stored` and the sidecar file exists, SHA-256 that file and compare to `payload_sha256`. This is the default after a successful `add`.
2. **`refetch`** — if no sidecar is on disk, re-check robots.txt, re-GET the URL, hash the new bytes, and compare. Live pages change; a mismatch is often “the web moved,” not a corrupt pin.

## Ethics (first-class, not a footnote)

- **robots.txt is actually checked** (stdlib `urllib.robotparser`) before the page body is fetched. If disallowed, the decision is written on the pin and **the body is not fetched**.
- Query-pattern workaround: a `Disallow` that ends with `?` (W3C `Disallow: /TR/?`) means **this path with a query string**, not this path and all children. Python's `urllib.robotparser` drops the trailing `?` and would otherwise prefix-block `/TR/webarch/`. Citepin rewrites those stored rules to keep the `?` so real prefix Disallows (NLnet `/cgi-bin/`) still block and query-pattern rules do not over-block. Not a full robots rewrite.
- RFC 9309: HTTP 401/403 on `robots.txt` is treated as complete disallow. 404/410 means no file, allow. Network errors on `robots.txt` are recorded as `unavailable` and fail-soft (allow, with a note).
- **No cookies. No `Authorization`. No URL userinfo.** Embedded `user:pass@host` is refused.
- Redirects that look like a login wall (`/login`, `/signin`, `/auth/`, …) are not followed. 401/407 responses are recorded; the challenge body is not stored.
- One URL per invocation. Size cap 2 MiB. Timeout 30s. Fail-soft on network errors (a pin is still written with `error`).
- Public web only. Do not point this at paywalled, authenticated, or private resources and expect a bypass — there isn’t one.

## v0 limits (honest)

| Present | Not yet (promised in the NLnet draft, not this folder) |
| --- | --- |
| `add` / `verify` / `cite` | CSL-JSON, BibTeX, `pinset` static site |
| SHA-256 of exact received bytes | Normalized / parsed-HTML hashes |
| robots decision on the pin | Rate-limit budget across many hosts |
| Sidecar payload for verify | WARC write, WACZ wrap, minisign |
| HTML `<title>` when cheap | JavaScript rendering / headless browser |
| Stdlib only | JSON-LD context, test fixtures, packaging |

HTML is unstable (ads, timestamps, A/B). The pin hashes **the bytes this client received**, not “what the page means.” A pin is a claim about a fetch, not a claim that “the web said X forever.”

## Itch.io later (not today)

itch.io quality guidelines (fetched into the 2026-08-17 income-bot log): disclose generative AI; no mass AI-asset farms. This repo is one original CLI. **No itch account is created in this session.**

## What was not done from this folder

Public source is this repo. No itch account, no NLnet submit, no emails.
