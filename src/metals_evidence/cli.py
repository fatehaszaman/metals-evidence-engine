"""CLI for fixture demos, canonical-envelope ingestion, and as-of evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from metals_evidence.archive import Archive
from metals_evidence.capture import Intake, load_policy, watch
from metals_evidence.comtrade import CollectionStore, PreviewQuery, collect
from metals_evidence.demo import DEFAULT_CUTOFF, parity_audit, records, scenario
from metals_evidence.evidence import Hypothesis, evaluate, json_report, markdown
from metals_evidence.judge import review_files
from metals_evidence.model import Observation, canonical
from metals_evidence.quality import assess


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("demo", "evaluate", "audit"):
        sub = commands.add_parser(name)
        sub.add_argument("--hypothesis", default="hypotheses/in_bd_copper_availability.json")
        if name != "audit":
            sub.add_argument("--as-of", default=DEFAULT_CUTOFF if name == "demo" else None)
            sub.add_argument("--format", choices=("json", "markdown"), default="markdown")
        if name == "demo":
            sub.add_argument(
                "--scenario",
                choices=("conflict", "stale", "definition-break"),
                default="conflict",
            )
        if name == "evaluate":
            sub.add_argument("--db", required=True)
    ingest = commands.add_parser("ingest")
    ingest.add_argument("--db", required=True)
    ingest.add_argument("--input", required=True, help="Canonical observation envelopes in JSONL")
    commands.add_parser("fixtures")
    capture = commands.add_parser("capture", help="Watch provider-delivered files; no network feed")
    capture.add_argument("--db", required=True)
    capture.add_argument("--inbox", required=True)
    capture.add_argument("--policy", required=True)
    capture.add_argument("--interval", type=float, default=30)
    capture.add_argument("--once", action="store_true")
    judge = commands.add_parser("review", help="Audit an external LLM verdict; never apply it")
    for flag in ("db", "raw", "candidate", "verdict", "reviewer", "reviewed-at"):
        judge.add_argument(f"--{flag}", required=True)
    score = commands.add_parser("score", help="Preview requirement scores without accepting data")
    for flag in ("input", "policy", "as-of"):
        score.add_argument(f"--{flag}", required=True)
    score.add_argument("--db", help="Existing archive for baseline/revision checks")
    api = commands.add_parser(
        "collect-comtrade", help="Collect real API preview into quarantine only"
    )
    api.add_argument("--reporter", choices=("IN", "BD"), required=True)
    api.add_argument("--partner", choices=("IN", "BD", "WORLD"), required=True)
    api.add_argument("--period", required=True, help="YYYYMM, not a publication timestamp")
    api.add_argument("--commodity", required=True, help="Explicit six-digit copper code")
    api.add_argument("--flow", choices=("M", "X"), default="M")
    api.add_argument("--output", required=True, help="Private raw/staging archive directory")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "collect-comtrade":
            query = PreviewQuery(
                args.reporter, args.partner, args.period, args.commodity, args.flow
            )
            with CollectionStore(args.output) as store:
                receipt = collect(query, store)
            print(canonical(receipt))
            return 0 if receipt["state"] in {"QUARANTINED_PREVIEW", "NO_DATA_REPORTED"} else 1
        if args.command == "score":
            if args.db and not Path(args.db).is_file():
                raise ValueError("score archive does not exist")
            candidate = json.loads(Path(args.input).read_text())
            policies = load_policy(args.policy)
            with Archive(args.db or ":memory:") as archive:
                _, scorecard = assess(archive, candidate, policies, args.as_of)
            print(canonical(scorecard))
            return 1 if scorecard["mandatory_failures"] else 0
        if args.command == "review":
            with Archive(args.db) as archive:
                record = review_files(
                    archive,
                    args.raw,
                    args.candidate,
                    args.verdict,
                    args.reviewer,
                    args.reviewed_at,
                )
            print(canonical(record))
            return 0 if record["status"] == "REQUIRES_HUMAN_REVIEW" else 1
        if args.command == "capture":
            policies = load_policy(args.policy)
            with Archive(args.db) as archive:
                watch(
                    Intake(archive),
                    Path(args.inbox),
                    policies,
                    args.interval,
                    once=args.once,
                )
            return 0
        if args.command == "fixtures":
            for record in records():
                print(canonical(record.to_dict()))
            return 0
        if args.command == "ingest":
            # Validate the entire file before appending any malformed input.
            records_to_load = [
                Observation.from_dict(json.loads(line))
                for line in Path(args.input).read_text().splitlines()
                if line.strip()
            ]
            with Archive(args.db) as archive:
                added = sum(archive.append(record) for record in records_to_load)
                print(canonical({"added": added, "stored": archive.count()}))
            return 0
        hypothesis = Hypothesis.load(args.hypothesis)
        if args.command == "audit":
            audit = parity_audit(hypothesis)
            print(json.dumps(audit, indent=2))
            return 0 if audit["passed"] else 1
        if args.command == "demo":
            data, scenario_cutoff = scenario(args.scenario)
            cutoff = scenario_cutoff if args.as_of == DEFAULT_CUTOFF else args.as_of
            with Archive() as archive:
                for record in data:
                    archive.append(record)
                report = evaluate(archive, hypothesis, cutoff)
        else:
            if not args.as_of:
                raise ValueError("evaluate requires --as-of with an explicit timezone")
            if not Path(args.db).is_file():
                raise ValueError("archive does not exist; ingest observations first")
            with Archive(args.db) as archive:
                report = evaluate(archive, hypothesis, args.as_of)
        print(markdown(report) if args.format == "markdown" else json_report(report), end="")
        return 0
    except KeyboardInterrupt:
        return 130
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
