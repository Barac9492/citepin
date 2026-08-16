#!/usr/bin/env python3
"""Citepin v0 — citation-grade pin of ONE public web page.

Python 3 standard library only. Not a crawler, not Wayback, not a
login/paywall bypass. Honors robots.txt. No cookies, no auth.

Disclosed-AI authorship: Income Bot for Ethan Cho. License: Apache-2.0.
See README.md, NOTICE.md, schema-v0.md in this directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

TOOL_NAME = "Citepin"
TOOL_VERSION = "0.1"
SCHEMA_VERSION = "0.0"
# Product token "Citepin" is what robots.txt matching uses.
USER_AGENT = (
    "Citepin/0.1 (+https://github.com/Barac9492/citepin; disclosed-AI; research)"
)
UA_PRODUCT = "Citepin"
TIMEOUT_S = 30
MAX_BODY = 2 * 1024 * 1024  # 2 MiB
MAX_ROBOTS = 512 * 1024
HERE = Path(__file__).resolve().parent
DEFAULT_PINS = HERE / "pins"

LOGIN_PATH_HINTS = (
    "/login",
    "/log-in",
    "/signin",
    "/sign-in",
    "/signup",
    "/sign-up",
    "/auth/",
    "/oauth/",
    "/account/login",
    "/session/new",
    "/wp-login",
    "/user/login",
)


class LoginWallError(Exception):
    """Redirect target looks like a login/auth wall; we refuse to follow."""

    def __init__(self, url: str, http_status: int) -> None:
        super().__init__(f"refusing login-wall redirect ({http_status}) -> {url}")
        self.url = url
        self.http_status = http_status


class TitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_title = False
        self.title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def looks_like_login(url: str) -> bool:
    path = urllib.parse.urlparse(url).path.lower()
    return any(hint in path for hint in LOGIN_PATH_HINTS)


def reject_embedded_credentials(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    if parsed.username or parsed.password:
        return "URL contains userinfo (login/password); Citepin never sends credentials"
    return None


class NoCookieRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow redirects but never forward cookies; stop at login walls."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        if looks_like_login(newurl) and not looks_like_login(req.full_url):
            raise LoginWallError(newurl, int(code))
        new_req = urllib.request.HTTPRedirectHandler.redirect_request(
            self, req, fp, code, msg, headers, newurl
        )
        if new_req is None:
            return None
        # urllib may copy headers; strip anything cookie-like just in case.
        for header in ("Cookie", "Authorization", "Proxy-Authorization"):
            if new_req.has_header(header):
                new_req.remove_header(header)
        return new_req


def opener() -> urllib.request.OpenerDirector:
    ctx = ssl.create_default_context()
    return urllib.request.build_opener(
        NoCookieRedirectHandler,
        urllib.request.HTTPSHandler(context=ctx),
    )


def read_capped(fp: Any, cap: int) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    total = 0
    truncated = False
    while True:
        chunk = fp.read(65536)
        if not chunk:
            break
        if total + len(chunk) > cap:
            chunks.append(chunk[: cap - total])
            total = cap
            truncated = True
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks), truncated


def http_get(
    url: str,
    *,
    timeout: int = TIMEOUT_S,
    cap: int = MAX_BODY,
    accept: str = "text/html,application/xhtml+xml,application/json,text/plain;q=0.9,*/*;q=0.5",
) -> dict[str, Any]:
    """GET one URL. No cookies, no auth. Fail-soft: never raises for network."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Accept-Language": "en,*;q=0.1",
        },
        method="GET",
    )
    try:
        with opener().open(req, timeout=timeout) as resp:
            body, truncated = read_capped(resp, cap)
            return {
                "ok": True,
                "http_status": int(resp.status),
                "final_url": resp.geturl(),
                "media_type": _media_type(resp.headers.get("Content-Type")),
                "content_type_raw": resp.headers.get("Content-Type"),
                "www_authenticate": resp.headers.get("WWW-Authenticate"),
                "body": body,
                "truncated": truncated,
                "error": None,
                "login_wall": False,
            }
    except LoginWallError as exc:
        return {
            "ok": False,
            "http_status": exc.http_status,
            "final_url": exc.url,
            "media_type": None,
            "content_type_raw": None,
            "www_authenticate": None,
            "body": None,
            "truncated": False,
            "error": str(exc),
            "login_wall": True,
        }
    except urllib.error.HTTPError as exc:
        try:
            body, truncated = read_capped(exc, cap)
        except Exception:
            body, truncated = b"", False
        return {
            "ok": False,
            "http_status": int(exc.code),
            "final_url": exc.geturl() if hasattr(exc, "geturl") else url,
            "media_type": _media_type(exc.headers.get("Content-Type") if exc.headers else None),
            "content_type_raw": exc.headers.get("Content-Type") if exc.headers else None,
            "www_authenticate": exc.headers.get("WWW-Authenticate") if exc.headers else None,
            "body": body,
            "truncated": truncated,
            "error": f"HTTP {exc.code} {exc.reason}",
            "login_wall": int(exc.code) in (401, 407),
        }
    except Exception as exc:
        return {
            "ok": False,
            "http_status": None,
            "final_url": url,
            "media_type": None,
            "content_type_raw": None,
            "www_authenticate": None,
            "body": None,
            "truncated": False,
            "error": f"{type(exc).__name__}: {exc}",
            "login_wall": False,
        }


def _media_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    return content_type.split(";", 1)[0].strip().lower() or None


def extract_title(body: bytes, media_type: str | None) -> str | None:
    if not body or not media_type:
        return None
    if media_type not in ("text/html", "application/xhtml+xml"):
        return None
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            text = body.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return None
    parser = TitleParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        return None
    title = re.sub(r"\s+", " ", "".join(parser.title_parts)).strip()
    return title[:300] or None


def _strip_robots_comment(line: str) -> str:
    i = line.find("#")
    if i >= 0:
        line = line[:i]
    return line.strip()


def _allow_disallow_path(line: str) -> tuple[str, str] | None:
    """Parse an Allow/Disallow line into (directive, path) or None."""
    line = _strip_robots_comment(line)
    if not line or ":" not in line:
        return None
    key, _, val = line.partition(":")
    key = key.strip().lower()
    if key not in ("allow", "disallow"):
        return None
    return key, val.strip()


def _norm_rule_path(path: str) -> str:
    """Same path normalization RuleLine.__init__ applies before quote()."""
    return urllib.parse.urlunparse(urllib.parse.urlparse(path))


def _query_pattern_disallow_prefixes(robots_text: str) -> tuple[set[str], set[str]]:
    """Split raw Disallow paths into query-pattern prefixes vs real prefixes.

    A path that ends with '?' (e.g. '/TR/?') means 'this path with a query
    string' in the Google/W3C convention used by https://www.w3.org/robots.txt.
    Real prefix Disallows (e.g. NLnet '/cgi-bin/') do not end with '?'.
    """
    query_prefixes: set[str] = set()
    real_prefixes: set[str] = set()
    for line in robots_text.splitlines():
        parsed = _allow_disallow_path(line)
        if not parsed:
            continue
        key, path = parsed
        if key != "disallow" or not path:
            continue
        if path.endswith("?"):
            query_prefixes.add(_norm_rule_path(path[:-1]))
        else:
            real_prefixes.add(_norm_rule_path(path))
    return query_prefixes, real_prefixes


def _patch_query_pattern_rules(
    rp: urllib.robotparser.RobotFileParser, robots_text: str
) -> list[str]:
    """Keep trailing-'?' Disallows from becoming child-prefix blocks.

    Why: urllib.robotparser.RuleLine does urlparse+urlunparse, which drops
    an empty query. 'Disallow: /TR/?' is stored as '/TR/', and applies_to()
    is startswith(), so /TR/webarch/ is refused. That is a stdlib misread
    of a query-string pattern, not a real prefix Disallow.

    Workaround (not a full robots rewrite): if a Disallow ends with '?' and
    the file has no same-path Disallow without '?', rewrite the stored rule
    to 'prefix?' (quoted %3F) so startswith only matches that path + query.
    NLnet 'Disallow: /cgi-bin/' is left untouched. If both '/TR/' and
    '/TR/?' exist, we keep the real prefix (conservative).
    """
    query_prefixes, real_prefixes = _query_pattern_disallow_prefixes(robots_text)
    query_only = query_prefixes - real_prefixes
    patched: list[str] = []
    entries = list(rp.entries)
    if rp.default_entry:
        entries.append(rp.default_entry)
    for entry in entries:
        for rule in entry.rulelines:
            if rule.allowance:
                continue
            stored = urllib.parse.unquote(getattr(rule, "path", "") or "")
            if stored in query_only:
                rule.path = urllib.parse.quote(stored + "?")
                raw = stored + "?"
                if raw not in patched:
                    patched.append(raw)
    return patched


def _url_has_query(url: str) -> bool:
    """True if the URL includes a '?' (even with an empty query)."""
    return "?" in url.split("#", 1)[0]


def _matched_disallow_paths(rp: urllib.robotparser.RobotFileParser, url: str) -> list[str]:
    """Best-effort: which parsed Disallow paths prefix-match this URL.

    After _patch_query_pattern_rules, a 'Disallow: /TR/?' is stored as
    '/TR/?' (quoted /TR/%3F) and only matches URLs with that path + query.
    can_fetch() percent-encodes the URL's path+query the same way, so
    startswith stays consistent. We also check the URL path alone so
    notes still make sense for path-only pins.
    """
    parsed = urllib.parse.urlparse(url)
    path = parsed.path or "/"
    # Mirror RobotFileParser.can_fetch quoting of path + query.
    filename = urllib.parse.quote(
        urllib.parse.urlunparse(("", "", path, parsed.params, parsed.query, ""))
    )
    found: list[str] = []
    entries = list(rp.entries)
    if rp.default_entry:
        entries.append(rp.default_entry)
    for entry in entries:
        for rule in entry.rulelines:
            rpath = urllib.parse.unquote(getattr(rule, "path", "") or "")
            if rule.allowance or not rpath:
                continue
            stored = getattr(rule, "path", "") or ""
            path_hit = path.startswith(rpath) or path.startswith(rpath.rstrip("*"))
            query_hit = bool(filename) and (
                filename.startswith(stored) or filename.startswith(stored.rstrip("*"))
            )
            if path_hit or query_hit:
                if rpath not in found:
                    found.append(rpath)
    return found


def robots_decision(url: str) -> dict[str, Any]:

    """Fetch and honor robots.txt for UA_PRODUCT.

    RFC 9309: 404/410 => allow all; 401/403 => disallow all.
    Network errors: decision=unavailable, fail-soft allow (recorded).
    """
    parsed = urllib.parse.urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rec: dict[str, Any] = {
        "robots_url": robots_url,
        "robots_http_status": None,
        "robots_fetched_at_utc": utc_now(),
        "user_agent_product": UA_PRODUCT,
        "user_agent": USER_AGENT,
        "decision": "unavailable",
        "allowed": False,
        "note": None,
    }
    got = http_get(
        robots_url,
        cap=MAX_ROBOTS,
        accept="text/plain,*/*;q=0.1",
    )
    rec["robots_http_status"] = got["http_status"]
    status = got["http_status"]

    if got["error"] and status is None:
        rec["decision"] = "unavailable"
        rec["allowed"] = True  # fail-soft: do not invent a disallow
        rec["note"] = f"robots.txt network error; fail-soft allow. {got['error']}"
        return rec

    if status in (401, 403):
        rec["decision"] = "disallow"
        rec["allowed"] = False
        rec["note"] = (
            "RFC 9309: 401/403 on robots.txt is treated as complete disallow"
        )
        return rec

    if status in (404, 410):
        rec["decision"] = "allow"
        rec["allowed"] = True
        rec["note"] = f"no robots.txt ({status}); allow all"
        return rec

    if status is None or status >= 500 or got["body"] is None:
        rec["decision"] = "unavailable"
        rec["allowed"] = True
        rec["note"] = (
            f"robots.txt not usable (status={status}, error={got['error']}); "
            "fail-soft allow"
        )
        return rec

    text = got["body"].decode("utf-8", errors="replace")
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    rp.parse(text.splitlines())
    patched = _patch_query_pattern_rules(rp, text)
    allowed = bool(rp.can_fetch(UA_PRODUCT, url))
    # stdlib urlunparse also drops an empty '?' on the *URL*, so /TR/? would
    # not startswith /TR/%3F. Honor the query-pattern meaning ourselves.
    if allowed and _url_has_query(url):
        path = urllib.parse.urlparse(url).path or "/"
        if path in {p[:-1] for p in patched}:
            allowed = False
    rec["decision"] = "allow" if allowed else "disallow"
    rec["allowed"] = allowed
    matched = _matched_disallow_paths(rp, url)
    rec["matched_rule_paths"] = matched or None
    rec["note"] = (
        f"parsed robots.txt; can_fetch({UA_PRODUCT!r}) = {allowed}"
    )
    if patched:
        path = urllib.parse.urlparse(url).path or "/"
        relevant = [p for p in patched if path.startswith(p[:-1] or "/")]
        rec["note"] += (
            "; query-pattern Disallow workaround: a Disallow that ends with "
            "'?' is treated as this path with a query string, not this path "
            "and all children (Python urllib.robotparser drops the trailing "
            f"'?' and would over-block). Applied to {len(patched)} rule(s)"
        )
        if relevant:
            rec["note"] += f"; relevant to this URL: {relevant}"
    if not allowed and matched:
        rec["note"] += f"; stdlib rule paths that prefix-match: {matched}"
    return rec


def slug_for(url: str, fetched_at: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.netloc or "unknown").replace(":", "_")
    path = (parsed.path or "/").strip("/") or "root"
    path = path.replace("/", "-")
    raw = f"{host}-{path}"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-")[:80] or "page"
    ts = fetched_at.replace(":", "").replace("-", "")
    return f"{ts}_{slug}"


def payload_suffix(media_type: str | None) -> str:
    mapping = {
        "text/html": ".html",
        "application/xhtml+xml": ".xhtml",
        "text/plain": ".txt",
        "application/json": ".json",
        "application/xml": ".xml",
        "text/xml": ".xml",
        "text/css": ".css",
        "application/javascript": ".js",
        "text/javascript": ".js",
    }
    return mapping.get(media_type or "", ".bin")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def empty_pin(requested_url: str, fetched_at: str) -> dict[str, Any]:
    return {
        "schema": "citepin",
        "schema_version": SCHEMA_VERSION,
        "tool_name": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "user_agent": USER_AGENT,
        "requested_url": requested_url,
        "final_url": None,
        "fetched_at_utc": fetched_at,
        "http_status": None,
        "media_type": None,
        "page_title": None,
        "payload_sha256": None,
        "payload_bytes": None,
        "payload_truncated": False,
        "payload_stored": False,
        "payload_file": None,
        "robots": None,
        "login_wall": False,
        "www_authenticate": None,
        "error": None,
        "warc": None,
        "wacz": None,
        "signature": None,
        "notes": (
            "v0 pin: exact received bytes (or 2 MiB prefix if truncated). "
            "No WARC/WACZ, no minisign, no JS rendering."
        ),
    }


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def cmd_add(url: str, pins_dir: Path) -> int:
    cred_err = reject_embedded_credentials(url)
    if cred_err:
        print(f"citepin: refuse: {cred_err}", file=sys.stderr)
        return 1

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        print("citepin: URL must be http(s) with a host", file=sys.stderr)
        return 1

    fetched_at = utc_now()
    pin = empty_pin(url, fetched_at)
    robots = robots_decision(url)
    pin["robots"] = robots

    if not robots["allowed"]:
        pin["error"] = (
            "robots.txt disallows this URL for Citepin; body not fetched"
        )
        slug = slug_for(url, fetched_at)
        out = pins_dir / f"{slug}.json"
        write_json(out, pin)
        print(f"citepin: robots {robots['decision']} — body not fetched")
        print(f"citepin: pin written {out}")
        return 0

    got = http_get(url)
    pin["http_status"] = got["http_status"]
    pin["final_url"] = got["final_url"]
    pin["media_type"] = got["media_type"]
    pin["login_wall"] = bool(got["login_wall"])
    pin["www_authenticate"] = got["www_authenticate"]

    if got["login_wall"]:
        pin["error"] = got["error"] or "login/auth wall; body not stored"
        # Do not store a login-challenge body.
        slug = slug_for(url, fetched_at)
        out = pins_dir / f"{slug}.json"
        write_json(out, pin)
        print(f"citepin: login wall — body not stored ({got['error']})")
        print(f"citepin: pin written {out}")
        return 2

    if got["body"] is None:
        pin["error"] = got["error"] or "fetch failed"
        slug = slug_for(url, fetched_at)
        out = pins_dir / f"{slug}.json"
        write_json(out, pin)
        print(f"citepin: fail-soft {pin['error']}")
        print(f"citepin: pin written {out}")
        return 2

    body: bytes = got["body"]
    pin["payload_sha256"] = sha256_hex(body)
    pin["payload_bytes"] = len(body)
    pin["payload_truncated"] = bool(got["truncated"])
    pin["page_title"] = extract_title(body, got["media_type"])
    if got["error"] and got["http_status"] and got["http_status"] >= 400:
        pin["error"] = got["error"]

    slug = slug_for(url, fetched_at)
    suf = payload_suffix(got["media_type"])
    payload_name = f"payloads/{slug}" if slug.endswith(suf) else f"payloads/{slug}{suf}"
    payload_path = pins_dir / payload_name
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_bytes(body)
    pin["payload_stored"] = True
    pin["payload_file"] = payload_name

    out = pins_dir / f"{slug}.json"
    write_json(out, pin)
    status = pin["http_status"]
    digest = pin["payload_sha256"][:12]
    extra = " (truncated at 2 MiB)" if pin["payload_truncated"] else ""
    print(
        f"citepin: pinned HTTP {status}  sha256:{digest}…  "
        f"{pin['payload_bytes']} bytes{extra}"
    )
    print(f"citepin: robots {robots['decision']} ({robots['robots_url']})")
    print(f"citepin: pin written {out}")
    return 0


def load_pin(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_verify(pin_path: Path, pins_dir: Path) -> int:
    """Re-hash stored payload if present; otherwise re-fetch and compare.

    Mode is printed and is the only verify strategy used for that pin.
    """
    pin = load_pin(pin_path)
    expected = pin.get("payload_sha256")
    payload_rel = pin.get("payload_file")
    payload_path = None
    if payload_rel:
        # Prefer sidecar next to the pin file, then --pins-dir.
        candidate = pin_path.parent / payload_rel
        if candidate.is_file():
            payload_path = candidate
        else:
            other = pins_dir / payload_rel
            if other.is_file():
                payload_path = other

    if pin.get("payload_stored") and payload_path is not None:
        mode = "stored-payload"
        data = payload_path.read_bytes()
        actual = sha256_hex(data)
        print(f"citepin verify: mode={mode}")
        print(f"citepin verify: file={payload_path}")
        print(f"citepin verify: expected {expected}")
        print(f"citepin verify: actual   {actual}")
        if expected and actual == expected:
            if len(data) != pin.get("payload_bytes"):
                print(
                    f"citepin verify: WARN size {len(data)} != "
                    f"pin.payload_bytes {pin.get('payload_bytes')}"
                )
            print("citepin verify: MATCH")
            return 0
        print("citepin verify: MISMATCH")
        return 2

    if not expected:
        print("citepin verify: no payload_sha256 on pin (nothing to compare)")
        if pin.get("robots") and not pin["robots"].get("allowed"):
            print("citepin verify: original fetch was robots-disallowed")
        if pin.get("error"):
            print(f"citepin verify: original error: {pin['error']}")
        return 2

    mode = "refetch"
    print(f"citepin verify: mode={mode} (no stored payload on disk)")
    url = pin.get("final_url") or pin.get("requested_url")
    robots = robots_decision(url)
    print(
        f"citepin verify: robots {robots['decision']} "
        f"(status {robots['robots_http_status']})"
    )
    if not robots["allowed"]:
        print("citepin verify: robots disallows re-fetch; cannot compare")
        return 2
    got = http_get(url)
    if got["body"] is None:
        print(f"citepin verify: re-fetch failed: {got['error']}")
        return 2
    actual = sha256_hex(got["body"])
    print(f"citepin verify: expected {expected}")
    print(f"citepin verify: actual   {actual}")
    if actual == expected:
        print("citepin verify: MATCH")
        return 0
    print(
        "citepin verify: MISMATCH (live page may have changed; "
        "v0 hashes exact received bytes, which are often unstable)"
    )
    return 2


def cmd_cite(pin_path: Path) -> int:
    pin = load_pin(pin_path)
    url = pin.get("final_url") or pin.get("requested_url") or ""
    title = pin.get("page_title") or url
    when = pin.get("fetched_at_utc") or "unknown-time"
    digest = pin.get("payload_sha256")
    prefix = (digest[:12] + "…") if digest else "no-hash"
    status = pin.get("http_status")
    status_bit = f"HTTP {status}, " if status is not None else ""
    robots = (pin.get("robots") or {}).get("decision")
    robots_bit = f", robots {robots}" if robots else ""
    line = (
        f"[{title}]({url}) — fetched {when}, {status_bit}"
        f"sha256 `{prefix}` (Citepin/{TOOL_VERSION}{robots_bit})."
    )
    print(line)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="citepin.py",
        description=(
            "Citation-grade pin of one public web page "
            "(URL, UTC time, status, type, SHA-256, robots decision)."
        ),
    )
    p.add_argument(
        "--pins-dir",
        type=Path,
        default=DEFAULT_PINS,
        help=f"directory for pin JSON + payloads (default: {DEFAULT_PINS})",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"{TOOL_NAME}/{TOOL_VERSION} schema {SCHEMA_VERSION}",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    add_p = sub.add_parser("add", help="fetch one public URL and write a pin")
    add_p.add_argument("url", help="http(s) URL of a public page")

    ver_p = sub.add_parser(
        "verify",
        help="re-hash stored payload, or re-fetch if no payload is stored",
    )
    ver_p.add_argument("pin", type=Path, help="path to pin JSON")

    cite_p = sub.add_parser("cite", help="print one markdown citation line")
    cite_p.add_argument("pin", type=Path, help="path to pin JSON")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pins_dir: Path = args.pins_dir
    if args.cmd == "add":
        return cmd_add(args.url, pins_dir)
    if args.cmd == "verify":
        return cmd_verify(args.pin, pins_dir)
    if args.cmd == "cite":
        return cmd_cite(args.pin)
    return 1


if __name__ == "__main__":
    sys.exit(main())
