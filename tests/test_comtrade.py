"""Offline transport tests use invented data; no network is contacted in CI."""

import hashlib
import io
import json
import sqlite3
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from metals_evidence.cli import main
from metals_evidence.comtrade import (
    BLOCKERS,
    CollectionStore,
    NoRedirects,
    PreviewQuery,
    collect,
    parse_preview,
)
from metals_evidence.model import canonical

QUERY = PreviewQuery("IN", "BD", "202501", "740311")
ROW = {
    "reporterCode": 699,
    "partnerCode": 50,
    "period": "202501",
    "cmdCode": "740311",
    "flowCode": "M",
    "netWgt": "123.40",
    "isNetWgtEstimated": True,
    "synthetic_test": True,
}


class Response(io.BytesIO):
    def __init__(self, body, status=200, content_type="application/json", **headers):
        super().__init__(body)
        self.status = status
        self.headers = {"Content-Type": content_type, **headers}


def client(body=None, **kwargs):
    if body is None:
        body = canonical({"data": [ROW], "count": 1}).encode()
    return SimpleNamespace(open=lambda *a, **k: Response(body, **kwargs))


def test_verified_codes_and_scope():
    assert QUERY.params["reporterCode"] == "699"
    assert QUERY.params["partnerCode"] == "50"
    assert "subscription" not in QUERY.url
    assert PreviewQuery("BD", "WORLD", "202501", "740311", "X").params["partnerCode"] == "0"


@pytest.mark.parametrize(
    "args",
    [
        ("CN", "BD", "202501", "740311"),
        ("IN", "XX", "202501", "740311"),
        ("IN", "BD", "2025", "740311"),
        ("IN", "BD", "202513", "740311"),
        ("IN", "BD", "202501", "760110"),
        ("IN", "BD", "202501", "74"),
        ("IN", "BD", "202501", "740311", "bad"),
    ],
)
def test_query_rejects_unsupported_scope(args):
    with pytest.raises(ValueError):
        PreviewQuery(*args)


def test_durable_raw_staging_and_no_promotion(tmp_path):
    raw = canonical({"data": [ROW], "count": 1}).encode()
    with CollectionStore(tmp_path) as store:
        receipt = collect(QUERY, store, opener=client(raw))
        assert receipt["state"] == "QUARANTINED_PREVIEW"
        assert receipt["promoted_observations"] == 0
        assert receipt["blockers"] == BLOCKERS
        assert (tmp_path / receipt["raw_path"]).read_bytes() == raw
        assert receipt["raw_sha256"] == hashlib.sha256(raw).hexdigest()
        staged = json.loads((tmp_path / receipt["staging_path"]).read_text())
        assert staged["source_row"] == ROW
        assert staged["state"] == "UNVERIFIED_SOURCE_ROW"
        assert staged["receipt_id"] == receipt["receipt_id"]
        assert "published_time" not in staged
        assert not store.connection.execute(
            "SELECT name FROM sqlite_master WHERE name='observations'"
        ).fetchall()


def test_dedup_content_without_losing_receipt_events(tmp_path):
    with CollectionStore(tmp_path) as store:
        first = collect(QUERY, store, opener=client())
        second = collect(QUERY, store, opener=client())
        assert first["receipt_id"] != second["receipt_id"]
        assert first["raw_path"] == second["raw_path"]
        assert len(list((tmp_path / "raw").iterdir())) == 1
        assert (
            store.connection.execute("SELECT COUNT(*) FROM collector_receipts").fetchone()[0] == 2
        )
        for sql in (
            "DELETE FROM collector_receipts",
            "UPDATE collector_receipts SET envelope='{}'",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                store.connection.execute(sql)


def test_changed_same_url_preserves_both_versions(tmp_path):
    with CollectionStore(tmp_path) as store:
        first = collect(QUERY, store, opener=client())
        changed = canonical({"data": [ROW | {"netWgt": "150"}], "count": 1}).encode()
        second = collect(QUERY, store, opener=client(changed))
        assert first["request_url"] == second["request_url"]
        assert first["raw_sha256"] != second["raw_sha256"]
        assert len(list((tmp_path / "raw").iterdir())) == 2


@pytest.mark.parametrize(
    "status,state",
    [
        (429, "RATE_LIMITED"),
        (401, "ACCESS_BLOCKED"),
        (403, "ACCESS_BLOCKED"),
        (500, "HTTP_ERROR"),
        (302, "HTTP_ERROR"),
    ],
)
def test_http_statuses_preserved_without_retries(tmp_path, status, state):
    with CollectionStore(tmp_path) as store:
        record = collect(QUERY, store, opener=client(status=status, **{"Retry-After": "60"}))
        assert record["state"] == state
        assert record["response_headers"]["Retry-After"] == "60"
        assert record["http_status"] == status
        assert record["row_count"] == 0


def test_real_http_error_exception_path(tmp_path):
    def error(*a, **k):
        raise HTTPError(QUERY.url, 429, "rate limit", {}, io.BytesIO(b"slow down"))

    with CollectionStore(tmp_path) as store:
        record = collect(QUERY, store, opener=SimpleNamespace(open=error))
        assert record["state"] == "RATE_LIMITED"
        assert (tmp_path / record["raw_path"]).read_bytes() == b"slow down"


def test_redirect_handler_refuses_other_hosts():
    with pytest.raises(HTTPError, match="redirect refused"):
        NoRedirects().redirect_request(
            Request(QUERY.url), io.BytesIO(), 302, "moved", {}, "https://evil.example/"
        )


@pytest.mark.parametrize("error", [URLError("offline"), TimeoutError(), OSError("broken")])
def test_transport_failures_are_receipts(tmp_path, error):
    def fail(*a, **k):
        raise error

    with CollectionStore(tmp_path) as store:
        record = collect(QUERY, store, opener=SimpleNamespace(open=fail))
        assert record["state"] == "FETCH_FAILED"
        assert record["received_at"]
        assert record["failure_type"] == type(error).__name__
        assert "raw_sha256" not in record


@pytest.mark.parametrize(
    "body",
    [
        b"<html>blocked</html>",
        b"\xff",
        b"[]",
        b"{}",
        b'{"data":{}}',
        b'{"data":[null]}',
        b'{"data":[],"error":"invalid query"}',
        b'{"data":[],"count":2}',
        b'{"data":[],"count":false}',
    ],
)
def test_bad_json_or_schema_never_becomes_data(tmp_path, body):
    with CollectionStore(tmp_path) as store:
        receipt = collect(QUERY, store, opener=client(body))
        assert receipt["state"] == "SCHEMA_REJECTED"
        assert receipt["promoted_observations"] == 0
        assert (tmp_path / receipt["raw_path"]).read_bytes() == body


def test_wrong_content_type_is_not_silently_parsed(tmp_path):
    with CollectionStore(tmp_path) as store:
        receipt = collect(QUERY, store, opener=client(content_type="text/html"))
        assert receipt["state"] == "SCHEMA_REJECTED"
        assert "content type" in receipt["reason"]


def test_case_insensitive_http_headers(tmp_path):
    response = Response(canonical({"data": [ROW], "count": 1}).encode())
    response.headers = {"content-type": "application/json", "etag": "version"}
    with CollectionStore(tmp_path) as store:
        receipt = collect(QUERY, store, opener=SimpleNamespace(open=lambda *a, **k: response))
        assert receipt["state"] == "QUARANTINED_PREVIEW"
        assert receipt["response_headers"]["ETag"] == "version"


@pytest.mark.parametrize(
    "body,expected",
    [
        (canonical({"data": [ROW]}).encode(), "QUARANTINED_PREVIEW"),
        (b"<html>not data</html>", "SCHEMA_REJECTED"),
    ],
)
def test_missing_content_type_remains_unverified(tmp_path, body, expected):
    response = Response(body)
    response.headers = {}
    with CollectionStore(tmp_path) as store:
        receipt = collect(QUERY, store, opener=SimpleNamespace(open=lambda *a, **k: response))
        assert receipt["state"] == expected
        assert "CONTENT_TYPE_UNVERIFIED" in receipt["blockers"]
        assert receipt["promoted_observations"] == 0


@pytest.mark.parametrize(
    "media,expected",
    [
        ("application/problem+json; charset=utf-8", "QUARANTINED_PREVIEW"),
        ("text/html; spoof=application/json", "SCHEMA_REJECTED"),
        ("application/jsonp", "SCHEMA_REJECTED"),
    ],
)
def test_media_type_is_exact_not_substring(tmp_path, media, expected):
    with CollectionStore(tmp_path) as store:
        assert collect(QUERY, store, opener=client(content_type=media))["state"] == expected


@pytest.mark.parametrize("field", ["reporterCode", "partnerCode", "period", "cmdCode", "flowCode"])
def test_unexpected_data_scope_rejected(field):
    with pytest.raises(ValueError, match="scope mismatch"):
        parse_preview(canonical({"data": [ROW | {field: "wrong"}]}).encode(), QUERY)


def test_empty_is_not_zero(tmp_path):
    with CollectionStore(tmp_path) as store:
        receipt = collect(QUERY, store, opener=client(b'{"data":[],"count":0}'))
        assert receipt["state"] == "NO_DATA_REPORTED"
        assert receipt["promoted_observations"] == 0


def test_preview_at_cap_remains_incomplete(tmp_path):
    body = canonical({"data": [ROW] * 500, "count": 500}).encode()
    with CollectionStore(tmp_path) as store:
        receipt = collect(QUERY, store, opener=client(body))
        assert "PREVIEW_LIMIT_REACHED" in receipt["blockers"]
    with pytest.raises(ValueError, match="row bound"):
        parse_preview(canonical({"data": [ROW] * 501}).encode(), QUERY)


def test_bounded_read_preserves_only_flagged_prefix(tmp_path):
    with CollectionStore(tmp_path) as store:
        receipt = collect(QUERY, store, opener=client(b"x" * 100), max_bytes=20)
        assert receipt["state"] == "OVERSIZED_RESPONSE"
        assert receipt["bytes_archived"] == 21
        assert receipt["complete_body"] is False
        assert receipt["raw_path"].endswith(".partial")


def test_decimal_lexical_value_preserved_in_staging():
    body = canonical({"data": [ROW]}).replace('"123.40"', "123.40").encode()
    assert parse_preview(body, QUERY)[0]["netWgt"] == "123.40"


def test_corrupt_raw_file_not_overwritten(tmp_path):
    with CollectionStore(tmp_path) as store:
        first = collect(QUERY, store, opener=client())
        (tmp_path / first["raw_path"]).write_bytes(b"corrupt")
        second = collect(QUERY, store, opener=client())
        assert second["state"] == "SCHEMA_REJECTED"
        assert "corrupt" in second["reason"]
        assert (tmp_path / first["raw_path"]).read_bytes() == b"corrupt"


def test_interrupted_stream_cleans_temporary_file(tmp_path):
    class BrokenStream:
        def read(self, _):
            raise OSError("interrupted")

    with CollectionStore(tmp_path) as store:
        with pytest.raises(OSError):
            store.archive_body(BrokenStream(), 20)
        assert not list((tmp_path / "raw").iterdir())


@pytest.mark.parametrize("kwargs", [{"timeout": 0}, {"max_bytes": 0}, {"timeout": float("nan")}])
def test_limits_are_enforced_before_request(tmp_path, kwargs):
    with CollectionStore(tmp_path) as store, pytest.raises(ValueError):
        collect(QUERY, store, opener=client(), **kwargs)


@pytest.mark.parametrize(
    "state,expected",
    [
        ("QUARANTINED_PREVIEW", 0),
        ("NO_DATA_REPORTED", 0),
        ("FETCH_FAILED", 1),
    ],
)
def test_cli_collection_is_not_approval(monkeypatch, tmp_path, capsys, state, expected):
    monkeypatch.setattr("metals_evidence.cli.collect", lambda *a: {"state": state})
    assert (
        main(
            [
                "collect-comtrade",
                "--reporter",
                "IN",
                "--partner",
                "BD",
                "--period",
                "202501",
                "--commodity",
                "740311",
                "--output",
                str(tmp_path),
            ]
        )
        == expected
    )
    assert json.loads(capsys.readouterr().out)["state"] == state
