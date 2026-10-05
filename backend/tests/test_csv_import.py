"""CSV import: header detection, mapping, normalisation and replace-mode safety."""
import io
import json
from datetime import datetime

import pytest
from sqlalchemy import func, select

from app.etl import csv_import
from app.etl.pipeline import ingest_records, replace_workspace_content
from app.models import Experiment, Post, Workspace
from app.seed.generator import generate_posts

from datetime import datetime as _dt

AS_OF = _dt(2026, 10, 4)

# A realistic export: different names, semicolons-free, thousands separators, US dates.
EXPORT = (
    "Channel,Post Type,Date,Views,Accounts Reached,Reactions,Replies,Reposts,Bookmarks,Text\n"
    'Instagram,Reel,03/04/2026 18:30,"12,400","9,800",610,42,58,131,Why do teams ignore reports?\n'
    "LinkedIn,Text,2026-03-05 09:00,5000.0,4000,120,15,9,20,Notes on async work\n"
    "LinkedIn,Text,2026-03-06 09:00,0,0,0,0,0,0,zero impressions row\n"
)


def _file(text: str, name: str = "p.csv"):
    return {"file": (name, io.BytesIO(text.encode()), "text/csv")}


def test_suggest_mapping_matches_aliases_once():
    headers, _ = csv_import.parse_csv(EXPORT.encode())
    m = csv_import.suggest_mapping(headers)
    assert m["platform"] == "Channel" and m["format"] == "Post Type" and m["published_at"] == "Date"
    assert m["impressions"] == "Views" and m["reach"] == "Accounts Reached" and m["saves"] == "Bookmarks"
    assert m["caption"] == "Text" and m["topic"] is None
    assert len({v for v in m.values() if v}) == len([v for v in m.values() if v])  # one header -> one field


def test_parse_handles_semicolons_and_rejects_bad_files():
    headers, rows = csv_import.parse_csv(b"platform;format\nX;Text\n")
    assert headers == ["platform", "format"] and rows[0]["format"] == "Text"
    with pytest.raises(csv_import.CsvError) as e:
        csv_import.parse_csv(b"a,a\n1,2\n")
    assert e.value.code == "duplicate_headers"
    with pytest.raises(csv_import.CsvError) as e:
        csv_import.parse_csv(b"platform,format\n")
    assert e.value.code == "empty_file"
    with pytest.raises(csv_import.CsvError) as e:
        csv_import.parse_csv(b"\xff\xfe\x00bad")
    assert e.value.code == "bad_encoding"


def test_validate_mapping_rules():
    headers = ["a", "b", "c"]
    full = {f: None for f in csv_import.FIELDS}
    with pytest.raises(csv_import.CsvError) as e:
        csv_import.validate_mapping(full, headers)
    assert e.value.code == "missing_columns"
    ok = {**full, **{f: "a" for f in csv_import.REQUIRED_FIELDS}}
    with pytest.raises(csv_import.CsvError) as e:  # same column for many fields
        csv_import.validate_mapping(ok, headers)
    assert e.value.code == "bad_mapping"
    with pytest.raises(csv_import.CsvError):
        csv_import.validate_mapping({**full, "platform": "nope"}, headers)


def test_apply_mapping_normalises_without_inventing_measures():
    headers, rows = csv_import.parse_csv(EXPORT.encode())
    mapping = csv_import.validate_mapping(csv_import.suggest_mapping(headers), headers)
    recs, defaulted = csv_import.apply_mapping(rows, mapping, day_first=False)
    assert recs[0]["impressions"] == "12400" and recs[1]["impressions"] == "5000"
    assert recs[0]["published_at"].startswith("2026-03-04T18:30")
    assert recs[0]["topic"] == "Unspecified"
    assert {"topic", "hook_type", "tone", "external_id", "media_count"} <= set(defaulted)
    assert "impressions" not in defaulted and "likes" not in defaulted
    # id is a stable content hash so re-uploading the same file dedupes
    again, _ = csv_import.apply_mapping(rows, mapping)
    assert recs[0]["external_id"] == again[0]["external_id"]
    dayfirst, _ = csv_import.apply_mapping(rows, mapping, day_first=True)
    assert dayfirst[0]["published_at"].startswith("2026-04-03")


def test_template_round_trips_through_the_importer(empty_session):
    headers, rows = csv_import.parse_csv(csv_import.template_csv().encode())
    m = csv_import.validate_mapping(csv_import.suggest_mapping(headers), headers)
    recs, defaulted = csv_import.apply_mapping(rows, m)
    assert defaulted == []
    s = empty_session
    ws = Workspace(name="t", slug="t")
    s.add(ws)
    s.commit()
    rep = ingest_records(s, ws.id, recs, source="template")
    assert rep["rows_loaded"] == 1 and rep["rows_rejected"] == 0


def test_replace_wipes_old_content_and_clears_demo_flag(empty_session):
    s = empty_session
    ws = Workspace(name="Demo", slug="demo", is_demo=True)
    s.add(ws)
    s.commit()
    ingest_records(s, ws.id, generate_posts(30, AS_OF, 1), source="seed")
    s.add(Experiment(workspace_id=ws.id, name="old", hypothesis="h", variable="hook", platform="X"))
    s.commit()
    replace_workspace_content(s, ws.id, "My brand")
    assert s.scalar(select(func.count()).select_from(Post)) == 0
    assert s.scalar(select(func.count()).select_from(Experiment)) == 0
    ws = s.get(Workspace, ws.id)
    assert ws.name == "My brand" and ws.is_demo is False


# ------------------------------------------------------------------ API
def test_preview_is_read_only_and_suggests_mapping(client):
    before = client.get("/api/health").json()["posts"]
    j = client.post("/api/ingest/csv/preview", files=_file(EXPORT)).json()
    assert j["row_count"] == 3 and j["mapping"]["platform"] == "Channel" and j["missing_required"] == []
    assert len(j["sample"]) == 3 and {f["name"] for f in j["fields"]} == set(csv_import.FIELDS)
    assert client.get("/api/health").json()["posts"] == before


def test_preview_flags_unmapped_required_fields(client):
    j = client.post("/api/ingest/csv/preview", files=_file("foo,bar\n1,2\n")).json()
    assert set(j["missing_required"]) == set(csv_import.REQUIRED_FIELDS)


def test_import_with_custom_mapping_reports_defaults(client):
    r = client.post("/api/ingest/csv", files=_file(EXPORT), data={"mode": "append"})
    assert r.status_code == 200, r.text
    rep = r.json()["report"]
    assert rep["rows_loaded"] == 2 and rep["rows_rejected"] == 1  # zero-impression row rejected, not imputed
    assert "topic" in rep["defaulted_fields"] and rep["mode"] == "append"
    again = client.post("/api/ingest/csv", files=_file(EXPORT)).json()["report"]
    assert again["rows_loaded"] == 0 and again["duplicates_skipped"] == 2


def test_import_rejects_unmapped_and_bad_mapping(client):
    r = client.post("/api/ingest/csv", files=_file("a,b\n1,2\n"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "missing_columns"
    bad = client.post("/api/ingest/csv", files=_file(EXPORT), data={"mapping": "not json"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "bad_mapping"
    wrong = client.post("/api/ingest/csv", files=_file(EXPORT), data={"mapping": json.dumps({"platform": "Nope"})})
    assert wrong.status_code == 422


def test_replace_with_no_valid_rows_leaves_data_untouched(client):
    before = client.get("/api/health").json()["posts"]
    only_bad = EXPORT.split("\n")[0] + "\nInstagram,Reel,2026-03-06 09:00,0,0,0,0,0,0,x\n"
    r = client.post("/api/ingest/csv", files=_file(only_bad), data={"mode": "replace"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "nothing_valid"
    assert client.get("/api/health").json()["posts"] == before


def test_template_download(client):
    r = client.get("/api/ingest/template.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[0].split(",")[:3] == ["platform", "format", "published_at"]


def test_etl_runs_lists_required_and_optional_columns(client):
    j = client.get("/api/etl/runs").json()
    assert "platform" in j["required_columns"] and "caption" in j["optional_columns"]


_ = datetime
