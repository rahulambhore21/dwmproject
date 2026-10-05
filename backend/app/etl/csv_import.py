"""CSV import: header detection, column mapping and row normalisation.

Turns an arbitrary user CSV into the records `ingest_records` validates. Nothing is
invented: required measures must be mapped, and the only defaults applied are for
descriptive attributes (topic, hook, tone, caption, id), which the report names.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from typing import Any

import pandas as pd

# field -> (required, aliases). Aliases are matched on a normalised header.
FIELDS: dict[str, tuple[bool, list[str]]] = {
    "platform": (True, ["platform", "channel", "network", "social_network", "social_platform"]),
    "format": (True, ["format", "post_type", "type", "media_type", "content_type", "content_format"]),
    "published_at": (True, ["published_at", "published", "date", "datetime", "timestamp", "posted_at", "post_date", "publish_date", "publish_time", "created_at", "time"]),
    "impressions": (True, ["impressions", "impr", "views", "total_impressions", "post_impressions", "video_views"]),
    "reach": (True, ["reach", "unique_reach", "accounts_reached", "post_reach", "people_reached"]),
    "likes": (True, ["likes", "like_count", "reactions", "total_reactions", "favorites"]),
    "comments": (True, ["comments", "comment_count", "replies"]),
    "shares": (True, ["shares", "share_count", "reposts", "retweets", "forwards"]),
    "saves": (True, ["saves", "save_count", "bookmarks", "saved"]),
    "external_id": (False, ["external_id", "id", "post_id", "postid", "post_url", "permalink", "url"]),
    "topic": (False, ["topic", "category", "theme", "pillar", "content_pillar"]),
    "hook_type": (False, ["hook_type", "hook", "opening", "hook_style"]),
    "tone": (False, ["tone", "voice", "style"]),
    "caption": (False, ["caption", "text", "content", "post", "message", "description", "copy", "body", "post_text", "post_copy"]),
    "media_count": (False, ["media_count", "media", "num_media", "images", "image_count", "slides"]),
}
REQUIRED_FIELDS = [f for f, (req, _) in FIELDS.items() if req]
OPTIONAL_DEFAULTS = {"topic": "Unspecified", "hook_type": "Unspecified", "tone": "Unspecified", "caption": ""}
_INT_FIELDS = ("impressions", "reach", "likes", "comments", "shares", "saves", "media_count")
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
PREVIEW_ROWS = 5


class CsvError(Exception):
    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _norm(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")


def parse_csv(raw: bytes) -> tuple[list[str], list[dict[str, str]]]:
    if len(raw) > MAX_UPLOAD_BYTES:
        raise CsvError("file_too_large", "CSV must be 5 MB or smaller.", 413)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvError("bad_encoding", "CSV must be UTF-8 encoded.") from exc
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = [h.strip() for h in (reader.fieldnames or []) if h and h.strip()]
    if not headers:
        raise CsvError("empty_file", "CSV has no header row.")
    if len(set(headers)) != len(headers):
        raise CsvError("duplicate_headers", "CSV has duplicate column names; rename them and retry.")
    rows = [{(k or "").strip(): v for k, v in row.items() if k} for row in reader]
    if not rows:
        raise CsvError("empty_file", "CSV contains no data rows.")
    return headers, rows


def suggest_mapping(headers: list[str]) -> dict[str, str | None]:
    """Best header for each field (exact normalised alias match, first alias wins; one header -> one field)."""
    by_norm = {_norm(h): h for h in headers}
    used: set[str] = set()
    mapping: dict[str, str | None] = {}
    for field, (_, aliases) in FIELDS.items():
        pick = next((by_norm[a] for a in aliases if a in by_norm and by_norm[a] not in used), None)
        if pick:
            used.add(pick)
        mapping[field] = pick
    return mapping


def validate_mapping(mapping: dict[str, Any], headers: list[str]) -> dict[str, str | None]:
    clean: dict[str, str | None] = {}
    seen: dict[str, str] = {}
    for field, col in mapping.items():
        if field not in FIELDS:
            raise CsvError("bad_mapping", f"Unknown field '{field}'.")
        if col in (None, ""):
            clean[field] = None
            continue
        if col not in headers:
            raise CsvError("bad_mapping", f"Column '{col}' (for {field}) is not in the file.")
        if col in seen:
            raise CsvError("bad_mapping", f"Column '{col}' is mapped to both {seen[col]} and {field}.")
        seen[col] = field
        clean[field] = col
    missing = [f for f in REQUIRED_FIELDS if not clean.get(f)]
    if missing:
        raise CsvError("missing_columns", f"Map a column for: {', '.join(missing)}.")
    return clean


def _int_text(v: str) -> str:
    """'1,234' / '12.0' -> '1234' / '12'. Anything else is left for validation to reject."""
    s = v.replace(",", "").replace("_", "").strip()
    try:
        f = float(s)
    except ValueError:
        return v
    return str(int(f)) if f.is_integer() else v


def _date_text(v: str, day_first: bool) -> str:
    try:
        ts = pd.to_datetime(v, dayfirst=day_first)
    except (ValueError, TypeError, OverflowError):
        return v
    if pd.isna(ts):
        return v
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts.isoformat()


def apply_mapping(rows: list[dict[str, str]], mapping: dict[str, str | None], day_first: bool = False) -> tuple[list[dict], list[str]]:
    """Build ingest records; returns (records, optional fields filled with defaults)."""
    records: list[dict] = []
    for row in rows:
        rec: dict[str, Any] = {}
        for field, col in mapping.items():
            if not col:
                continue
            v = (row.get(col) or "").strip()
            if v == "":
                continue
            if field in _INT_FIELDS:
                v = _int_text(v)
            elif field == "published_at":
                v = _date_text(v, day_first)
            rec[field] = v
        for field, default in OPTIONAL_DEFAULTS.items():
            rec.setdefault(field, default)
        if "external_id" not in rec:
            basis = "|".join(str(rec.get(k, "")) for k in ("platform", "published_at", "caption", "impressions", "likes"))
            rec["external_id"] = "csv-" + hashlib.sha1(basis.encode()).hexdigest()[:12]
        records.append(rec)
    defaulted = [f for f in OPTIONAL_DEFAULTS if not mapping.get(f)]
    if not mapping.get("external_id"):
        defaulted.append("external_id")
    if not mapping.get("media_count"):
        defaulted.append("media_count")
    return records, defaulted


def template_csv() -> str:
    cols = list(FIELDS)
    example = {
        "platform": "Instagram", "format": "Reel", "published_at": "2026-03-04 18:30", "impressions": "12400",
        "reach": "9800", "likes": "610", "comments": "42", "shares": "58", "saves": "131", "external_id": "ig-0001",
        "topic": "Education", "hook_type": "Question", "tone": "Warm", "caption": "Why do most teams ignore weekly reports?",
        "media_count": "1",
    }
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(cols)
    w.writerow([example[c] for c in cols])
    return out.getvalue()
