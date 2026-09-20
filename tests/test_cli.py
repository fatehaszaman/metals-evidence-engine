import json

from metals_evidence.cli import main


def test_demo(capsys):
    assert main(["demo"]) == 0
    assert "INCONCLUSIVE" in capsys.readouterr().out


def test_demo_json(capsys):
    assert main(["demo", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["material_conflict"]


def test_demo_scenario(capsys):
    assert main(["demo", "--scenario", "stale"]) == 0
    assert "INSUFFICIENT_EVIDENCE" in capsys.readouterr().out


def test_demo_cutoff_override(capsys):
    assert main(["demo", "--as-of", "2025-09-20T09:00:00Z"]) == 0
    assert "REVISED" in capsys.readouterr().out


def test_audit(capsys):
    assert main(["audit"]) == 0
    assert json.loads(capsys.readouterr().out)["passed"]


def test_ingest_evaluate_idempotent(tmp_path, capsys):
    fixture = tmp_path / "data.jsonl"
    db = str(tmp_path / "data.db")
    assert main(["fixtures"]) == 0
    fixture.write_text(capsys.readouterr().out)
    for expected_added in (13, 0):
        assert main(["ingest", "--db", db, "--input", str(fixture)]) == 0
        assert json.loads(capsys.readouterr().out)["added"] == expected_added
    assert main(["evaluate", "--db", db, "--as-of", "2025-09-19T09:00:00Z"]) == 0
    assert "INCONCLUSIVE" in capsys.readouterr().out
    assert main(["evaluate", "--db", db]) == 2
    assert "requires --as-of" in capsys.readouterr().err


def test_no_silent_archive_creation(tmp_path, capsys):
    db = tmp_path / "missing.db"
    assert main(["evaluate", "--db", str(db), "--as-of", "2025-09-19T09:00:00Z"]) == 2
    assert not db.exists()
    assert "does not exist" in capsys.readouterr().err


def test_malformed_input_fails_without_database(tmp_path, capsys):
    fixture = tmp_path / "malformed.jsonl"
    fixture.write_text('{"bad": true}\n')
    db = tmp_path / "archive.db"
    assert main(["ingest", "--db", str(db), "--input", str(fixture)]) == 2
    assert not db.exists()
    assert "error:" in capsys.readouterr().err
