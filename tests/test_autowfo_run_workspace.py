from pathlib import Path

from autowfo.commands import core_workflow
from autowfo.run_workspace import build_run_workspace, get_runs_dir


def test_build_run_workspace_derives_run_local_paths(tmp_path):
    workspace = build_run_workspace(tmp_path, "20260314_010203")

    assert workspace.artifacts_dir == tmp_path / "artifacts"
    assert workspace.runs_dir == tmp_path / "artifacts" / "runs"
    assert workspace.run_root == tmp_path / "artifacts" / "runs" / "20260314_010203"
    assert workspace.runtime_config_path == workspace.runtime_dir / "sweep_config.json"
    assert workspace.status_json_path == workspace.status_dir / "run_status.json"
    assert workspace.status_html_path == workspace.status_dir / "run_status.html"
    assert workspace.combo_summary_path == workspace.results_dir / "param_sweep_combo_summary.csv"
    assert workspace.symbol_summary_path == workspace.results_dir / "param_sweep_symbol_summary.csv"
    assert workspace.top10_path == workspace.results_dir / "param_sweep_top10_20260314_010203.csv"
    assert workspace.run_metadata_path == workspace.metadata_dir / "run_metadata.json"
    assert workspace.run_metadata_run_path == workspace.metadata_dir / "run_metadata_20260314_010203.json"


def test_run_workspace_as_dict_serializes_paths(tmp_path):
    workspace = build_run_workspace(tmp_path, "r1")

    payload = workspace.as_dict()

    assert payload["cwd"] == str(tmp_path)
    assert payload["run_root"] == str(tmp_path / "artifacts" / "runs" / "r1")
    assert payload["db_path"] == str(tmp_path / "artifacts" / "runs" / "r1" / "results" / "results.db")


def test_core_workflow_uses_workspace_runs_dir_helpers(tmp_path):
    runs_dir = get_runs_dir(tmp_path)
    (runs_dir / "run_b").mkdir(parents=True)
    (runs_dir / "run_a").mkdir(parents=True)

    assert core_workflow._list_run_labels(tmp_path) == {"run_a", "run_b"}
    assert core_workflow._resolve_gate_c_run_dir(tmp_path, "run_a", "combo") == runs_dir / "run_a"


def test_core_workflow_build_run_workspace_returns_run_workspace(tmp_path):
    workspace = core_workflow._build_run_workspace(Path(tmp_path), "abc123")

    assert workspace.run_id == "abc123"
    assert workspace.run_root == tmp_path / "artifacts" / "runs" / "abc123"
