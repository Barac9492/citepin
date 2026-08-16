# Citepin schema v0

Tiny JSON record for **one** public-web fetch. This is schema version `0.0` — a prototype of the v0.1 JSON (+ later JSON-LD context) named in the NLnet draft. It is not WARC, not WACZ, and not a signature envelope.

A pin should be small enough to commit to git, paste into a paper, or attach to a grant report. The optional sidecar payload is for local `verify`, not for replay.

## File layout

```text
pins/<utc>_<host>-<path>.json     # the pin (this schema)
pins/payloads/<utc>_<host>-<path>.<ext>   # exact received bytes, if stored
```

`<utc>` is the fetch timestamp with `:` and `-` stripped (`20260816T213000Z`).

## Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `schema` | string | Always `"citepin"`. |
| `schema_version` | string | `"0.0"` for this prototype. |
| `tool_name` | string | `"Citepin"`. |
| `tool_version` | string | `"0.1"`. |
| `user_agent` | string | Exact UA sent: `Citepin/0.1 (+https://github.com/Barac9492/citepin; disclosed-AI; research)`. |
| `requested_url` | string | URL passed to `add`. |
| `final_url` | string or null | URL after redirects, if a fetch happened. |
| `fetched_at_utc` | string | Fetch time, UTC, RFC 3339 with `Z`. |
| `http_status` | integer or null | Final HTTP status of the **page** GET. Null if the body was never requested (robots deny, or fail before request). |
| `media_type` | string or null | MIME type from `Content-Type` (parameters stripped). |
| `page_title` | string or null | HTML `<title>` when the media type is HTML and a title is cheap to parse. Not a content hash input. |
| `payload_sha256` | string or null | Lowercase hex SHA-256 of the **exact received bytes** (or of the 2 MiB prefix if truncated). Never a normalized/parsed hash. |
| `payload_bytes` | integer or null | Length of the hashed bytes. |
| `payload_truncated` | boolean | `true` if the 2 MiB cap stopped the read. The hash is then of the prefix only — the pin must not pretend otherwise. |
| `payload_stored` | boolean | Whether a sidecar file was written. |
| `payload_file` | string or null | Path relative to the pins directory, e.g. `payloads/….html`. |
| `robots` | object or null | See below. Always filled on `add`. |
| `login_wall` | boolean | `true` if a login/auth wall was detected (401/407 or login-like redirect). Body is not stored. |
| `www_authenticate` | string or null | `WWW-Authenticate` header if present. |
| `error` | string or null | Fail-soft message (robots deny, network error, login wall, HTTP 4xx/5xx). |
| `warc` | null | Reserved. v0 does not write WARC. |
| `wacz` | null | Reserved. v0 does not wrap WACZ. |
| `signature` | null | Reserved. v0 does not minisign. |
| `notes` | string | Human reminder of v0 limits. |

### `robots` object

| Field | Type | Meaning |
| --- | --- | --- |
| `robots_url` | string | `{scheme}://{host}/robots.txt`. |
| `robots_http_status` | integer or null | Status of the robots.txt GET. |
| `robots_fetched_at_utc` | string | When robots.txt was fetched. |
| `user_agent_product` | string | `"Citepin"` — token used for `can_fetch`. |
| `user_agent` | string | Full UA string. |
| `decision` | string | `allow` \| `disallow` \| `unavailable`. |
| `allowed` | boolean | Whether the **page body** may be fetched. |
| `note` | string or null | Why that decision was made. |
| `matched_rule_paths` | array or null | Best-effort Disallow paths from the stdlib parser that prefix-match the URL. Present on later pins when a parse happened. |

Decision rules (RFC 9309 + fail-soft):

- HTTP 200 (or other success) + parse: `urllib.robotparser` `can_fetch("Citepin", url)`, after a small query-pattern workaround (below).
- HTTP 404 / 410: no file → `allow`.
- HTTP 401 / 403: complete `disallow` (do not fetch the page).
- Network error or 5xx: `unavailable`, `allowed=true` (fail-soft), reason in `note`.
- **Query-pattern Disallow:** a raw `Disallow: /path?` is treated as “`/path` with a query string”, not “`/path` and all children”. Stdlib `RuleLine` does `urlparse`+`urlunparse`, which drops a trailing empty `?` and stores `/path`; `startswith` then over-blocks (W3C `/TR/?` vs `/TR/webarch/`). Citepin rewrites only those stored rules to keep the `?` (quoted `%3F`). A real prefix `Disallow: /cgi-bin/` is not rewritten. If the file has both `/path` and `/path?`, the prefix rule wins (conservative). The pin `note` records that the workaround ran.

If `allowed` is false, Citepin **does not GET the page body**. The pin still exists so the refusal is citable.

## What is hashed

The hash is over the HTTP response body bytes this client stored, as received, after the size cap. It is **not**:

- a hash of rendered DOM
- a hash of normalized HTML
- a hash of the pin JSON itself

If `payload_truncated` is true, say so when you cite the hash.

## `verify`

See README. Default after `add`: re-hash the sidecar (`mode=stored-payload`). Only if the sidecar is missing does verify re-fetch (`mode=refetch`) and compare. A live mismatch does not rewrite the pin.

## Out of scope for v0

WARC/WACZ, minisign, JSON-LD `@context`, CSL-JSON, BibTeX, pinset HTML, browser capture, cookies, authenticated fetches, multi-URL crawls.
