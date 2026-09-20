"""CLI for fixture demos, canonical-envelope ingestion, and as-of evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from metals_evidence.archive import Archive
from metals_evidence.demo import DEFAULT_CUTOFF, parity_audit, records, scenario
from metals_evidence.evidence import Hypothesis, evaluate, json_report, markdown
from metals_evidence.model import Observation, canonical


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("demo", "evaluate", "audit"):
        sub = commands.add_parser(name)
        sub.add_argument("--hypothesis", default="hypotheses/cn_copper_tightening.json")
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
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
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
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
