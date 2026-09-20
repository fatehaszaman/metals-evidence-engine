"""Bounded anonymous Comtrade preview collector. Staging only, never evidence promotion."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from metals_evidence.model import canonical

HOST = "https://comtradeapi.un.org"
ENDPOINT = HOST + "/public/v1/preview/C/M/HS"
# Verified against official Reporters.json on 2026-09-20; these are provider codes.
COUNTRIES = {"IN": "699", "BD": "50"}
MAX_BYTES = 4 * 1024 * 1024
BLOCKERS = [
    "PREVIEW_COMPLETENESS_UNVERIFIED",
    "PUBLICATION_TIME_UNVERIFIED",
    "REVISION_MAPPING_UNVERIFIED",
]
SCHEMA = """
CREATE TABLE IF NOT EXISTS collector_receipts (
    receipt_id TEXT PRIMARY KEY, envelope TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS receipt_no_update BEFORE UPDATE ON collector_receipts
BEGIN SELECT RAISE(ABORT, 'collector receipts are append-only'); END;
CREATE TRIGGER IF NOT EXISTS receipt_no_delete BEFORE DELETE ON collector_receipts
BEGIN SELECT RAISE(ABORT, 'collector receipts are append-only'); END;
"""


@dataclass(frozen=True)
class PreviewQuery:
    reporter: str
    partner: str
    period: str
    commodity: str
    flow: str = "M"

    def __post_init__(self):
        if self.reporter not in COUNTRIES or self.partner not in {*COUNTRIES, "WORLD"}:
            raise ValueError("use IN or BD reporter; partner must be IN, BD or WORLD")
        if not re.fullmatch(r"\d{6}", self.period):
            raise ValueError("period must be YYYYMM")
        datetime.strptime(self.period, "%Y%m")
        if not re.fullmatch(r"74\d{4}", self.commodity):
            raise ValueError("collector V1 requires an explicit six-digit copper code (74xxxx)")
        if self.flow not in {"M", "X"}:
            raise ValueError("flow must be M or X")

    @property
    def params(self) -> dict:
        return {
            "reporterCode": COUNTRIES[self.reporter],
            "partnerCode": "0" if self.partner == "WORLD" else COUNTRIES[self.partner],
            "period": self.period,
            "cmdCode": self.commodity,
            "flowCode": self.flow,
            "maxrecords": "500",
        }

    @property
    def url(self) -> str:
        return ENDPOINT + "?" + urlencode(self.params)


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "redirect refused", headers, fp)


class CollectionStore:
    """Content-addressed bytes plus distinct immutable receipt events for every attempt."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        (self.root / "raw").mkdir(parents=True, exist_ok=True)
        (self.root / "staging").mkdir(exist_ok=True)
        self.connection = sqlite3.connect(self.root / "collector.db")
        self.connection.executescript(SCHEMA)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.connection.close()

    def archive_body(self, stream, max_bytes: int) -> dict:
        """Read at most limit + 1 bytes; preserve a flagged prefix if oversized."""
        digest = hashlib.sha256()
        size = 0
        with tempfile.NamedTemporaryFile(dir=self.root / "raw", delete=False) as output:
            temp = Path(output.name)
            try:
                while size <= max_bytes:
                    chunk = stream.read(min(65536, max_bytes + 1 - size))
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                output.flush()
                os.fsync(output.fileno())
            except BaseException:
                temp.unlink(missing_ok=True)
                raise
        sha = digest.hexdigest()
        partial = size > max_bytes
        destination = self.root / "raw" / (sha + (".partial" if partial else ".json"))
        try:
            os.link(temp, destination)  # atomic create; never replace an existing payload
        except FileExistsError:
            # Detect local corruption rather than trusting a matching filename.
            with destination.open("rb") as existing:
                existing_hash = hashlib.file_digest(existing, "sha256").hexdigest()
            if existing_hash != sha:
                raise ValueError("existing raw payload is corrupt") from None
        finally:
            temp.unlink(missing_ok=True)
        return {
            "raw_sha256": sha,
            "raw_path": str(destination.relative_to(self.root)),
            "bytes_archived": size,
            "complete_body": not partial,
        }

    def save(self, record: dict):
        with self.connection:
            self.connection.execute(
                "INSERT INTO collector_receipts VALUES (?, ?)",
                (record["receipt_id"], canonical(record)),
            )


def now() -> str:
    return datetime.now(UTC).isoformat()


def parse_preview(payload: bytes, query: PreviewQuery) -> list[dict]:
    # Preserve source decimal lexical values as strings in derived staging only.
    data = json.loads(payload, parse_float=str)
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise ValueError("response must contain a data array")
    if data.get("error"):
        raise ValueError("provider returned an error envelope")
    rows = data["data"]
    if len(rows) > 500:
        raise ValueError("response exceeds the configured preview row bound")
    count = data.get("count")
    if count is not None and (type(count) is not int or count != len(rows)):
        raise ValueError("response count disagrees with returned rows")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("trade row must be an object")
        for field in ("reporterCode", "partnerCode", "period", "cmdCode", "flowCode"):
            if str(row.get(field)) != query.params[field]:
                raise ValueError(f"response scope mismatch: {field}")
    return rows


def collect(
    query: PreviewQuery,
    store: CollectionStore,
    *,
    opener=None,
    clock=now,
    timeout: float = 30,
    max_bytes: int = MAX_BYTES,
) -> dict:
    """One bounded attempt. HTTP failures are logged; no invisible retries or promotion."""
    if not 0 < timeout <= 60 or type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES:
        raise ValueError("timeout must be <=60 seconds and response limit <=4 MiB")
    started = clock()
    record = {
        "collector_version": "comtrade-preview-v1",
        "receipt_id": str(uuid.uuid4()),
        "source": "UN_COMTRADE_PUBLIC_PREVIEW",
        "request_url": query.url,
        "request_parameters": query.params,
        "started_at": started,
        "received_at": None,
        "http_status": None,
        "state": "FETCH_FAILED",
        "row_count": 0,
        "promoted_observations": 0,
        "blockers": list(BLOCKERS),
        "boundary": (
            "Real source collection is not real-time market data. Preview rows are "
            "unverified staging, never canonical evidence or historical vintage proof."
        ),
    }
    response = None
    try:
        request = Request(
            query.url,
            headers={"Accept": "application/json", "User-Agent": "metals-evidence-engine/0.1"},
        )
        client = opener if opener is not None else build_opener(NoRedirects())
        try:
            response = client.open(request, timeout=timeout)
        except HTTPError as exc:
            response = exc
        with response:
            record["http_status"] = response.status
            # Standard HTTPMessage and proxy/test mappings may differ in key casing.
            headers = {key.lower(): value for key, value in response.headers.items()}
            record["response_headers"] = {
                key: headers[key.lower()]
                for key in ("Content-Type", "ETag", "Last-Modified", "Retry-After")
                if headers.get(key.lower()) is not None
            }
            # Durable bytes before JSON parsing or economic-field interpretation.
            record.update(store.archive_body(response, max_bytes))
        record["received_at"] = clock()
        code = record["http_status"]
        if code == 429:
            record["state"] = "RATE_LIMITED"
        elif code in (401, 403):
            record["state"] = "ACCESS_BLOCKED"
        elif code != 200:
            record["state"] = "HTTP_ERROR"
        elif not record["complete_body"]:
            record["state"] = "OVERSIZED_RESPONSE"
        else:
            content_type = record["response_headers"].get("Content-Type", "").lower()
            media_type = content_type.split(";", 1)[0].strip()
            if not media_type:
                record["blockers"].append("CONTENT_TYPE_UNVERIFIED")
            elif media_type != "application/json" and not (
                media_type.startswith("application/") and media_type.endswith("+json")
            ):
                raise ValueError("unexpected content type; refusing an HTML/error page")
            rows = parse_preview((store.root / record["raw_path"]).read_bytes(), query)
            record["row_count"] = len(rows)
            record["state"] = "QUARANTINED_PREVIEW" if rows else "NO_DATA_REPORTED"
            if len(rows) == 500:
                record["blockers"].append("PREVIEW_LIMIT_REACHED")
            staging = store.root / "staging" / (record["receipt_id"] + ".jsonl")
            with staging.open("x", encoding="utf-8") as output:
                for row_number, row in enumerate(rows):
                    output.write(
                        canonical(
                            {
                                "receipt_id": record["receipt_id"],
                                "row_number": row_number,
                                "raw_sha256": record["raw_sha256"],
                                "source_row": row,
                                "state": "UNVERIFIED_SOURCE_ROW",
                                "blockers": record["blockers"],
                            }
                        )
                        + "\n"
                    )
                output.flush()
                os.fsync(output.fileno())
            record["staging_path"] = str(staging.relative_to(store.root))
    except (URLError, TimeoutError, OSError) as exc:
        record["state"] = "FETCH_FAILED"
        record["failure_type"] = type(exc).__name__
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        record["state"] = "SCHEMA_REJECTED"
        record["reason"] = str(exc)
    record["received_at"] = record["received_at"] or clock()
    store.save(record)
    return record
