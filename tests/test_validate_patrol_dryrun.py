import json

import pytest


@pytest.mark.slow
def test_validate_patrol_dryrun_script_runs_and_writes_patrol_log(tmp_path):
    pytest.importorskip("duckdb")
    pytest.importorskip("vectorbt")

    from scripts.validate_patrol_dryrun import main as dryrun_main

    workdir = tmp_path / "dryrun_case"
    summary_path = workdir / "summary.json"
    code = dryrun_main(["--workdir", str(workdir), "--rounds", "3", "--summary-out", str(summary_path)])
    assert code == 0

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["ok"] is True
    assert len(summary["rounds"]) == 3
    assert summary["patrol_log_lines"] == 3

    growth_combos = [int(row["growth_total_combos"]) for row in summary["rounds"]]
    assert growth_combos[0] > 0
    assert growth_combos[1] > growth_combos[0]
    assert growth_combos[2] > growth_combos[1]

    patrol_log_path = workdir / "artifacts" / "patrol_log.ndjson"
    lines = [line for line in patrol_log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 3
    for raw in lines:
        row = json.loads(raw)
        assert set(row.keys()) >= {"utc", "tick_generated", "tick_enqueued", "runs_executed", "runs_errors", "queue_remaining"}

