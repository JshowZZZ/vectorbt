"""Run workspace path helpers for AUTOWFO evidence isolation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict


@dataclass(frozen=True)
class RunWorkspace:
    """Derive run-local workspace paths without mutating execution behavior."""

    cwd: Path
    run_id: str
    artifacts_dir_name: str = "artifacts"

    @property
    def artifacts_dir(self) -> Path:
        return self.cwd / self.artifacts_dir_name

    @property
    def runs_dir(self) -> Path:
        return self.artifacts_dir / "runs"

    @property
    def run_root(self) -> Path:
        return self.runs_dir / self.run_id

    @property
    def runtime_dir(self) -> Path:
        return self.run_root / "runtime"

    @property
    def status_dir(self) -> Path:
        return self.run_root / "status"

    @property
    def results_dir(self) -> Path:
        return self.run_root / "results"

    @property
    def reports_dir(self) -> Path:
        return self.run_root / "reports"

    @property
    def metadata_dir(self) -> Path:
        return self.run_root / "metadata"

    @property
    def runtime_config_path(self) -> Path:
        return self.runtime_dir / "sweep_config.json"

    @property
    def status_json_path(self) -> Path:
        return self.status_dir / "run_status.json"

    @property
    def status_html_path(self) -> Path:
        return self.status_dir / "run_status.html"

    @property
    def combo_summary_path(self) -> Path:
        return self.results_dir / "param_sweep_combo_summary.csv"

    @property
    def symbol_summary_path(self) -> Path:
        return self.results_dir / "param_sweep_symbol_summary.csv"

    @property
    def leaderboard_path(self) -> Path:
        return self.results_dir / "leaderboard.csv"

    @property
    def registry_path(self) -> Path:
        return self.results_dir / "run_registry.json"

    @property
    def top10_path(self) -> Path:
        return self.results_dir / f"param_sweep_top10_{self.run_id}.csv"

    @property
    def db_path(self) -> Path:
        return self.results_dir / "results.db"

    @property
    def control_path(self) -> Path:
        return self.status_dir / "run_control.json"

    @property
    def run_metadata_path(self) -> Path:
        return self.metadata_dir / "run_metadata.json"

    @property
    def run_metadata_run_path(self) -> Path:
        return self.metadata_dir / f"run_metadata_{self.run_id}.json"

    def ensure_directories(self) -> None:
        for path in (
            self.artifacts_dir,
            self.runs_dir,
            self.run_root,
            self.runtime_dir,
            self.status_dir,
            self.results_dir,
            self.reports_dir,
            self.metadata_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def report_paths(self, report_file_run: str) -> Dict[str, Path]:
        report_name = Path(report_file_run).name
        latest_name = report_name.replace(f"_{self.run_id}", "")
        return {
            "report_run": self.reports_dir / report_name,
            "report_latest": self.reports_dir / latest_name,
        }

    def as_dict(self) -> Dict[str, str]:
        return {
            key: str(value)
            for key, value in asdict(_RunWorkspaceSerializable.from_workspace(self)).items()
        }


@dataclass(frozen=True)
class _RunWorkspaceSerializable:
    cwd: Path
    artifacts_dir: Path
    runs_dir: Path
    run_root: Path
    runtime_dir: Path
    status_dir: Path
    results_dir: Path
    reports_dir: Path
    metadata_dir: Path
    runtime_config_path: Path
    status_json_path: Path
    status_html_path: Path
    combo_summary_path: Path
    symbol_summary_path: Path
    leaderboard_path: Path
    registry_path: Path
    top10_path: Path
    db_path: Path
    control_path: Path
    run_metadata_path: Path
    run_metadata_run_path: Path

    @classmethod
    def from_workspace(cls, workspace: RunWorkspace) -> "_RunWorkspaceSerializable":
        return cls(
            cwd=workspace.cwd,
            artifacts_dir=workspace.artifacts_dir,
            runs_dir=workspace.runs_dir,
            run_root=workspace.run_root,
            runtime_dir=workspace.runtime_dir,
            status_dir=workspace.status_dir,
            results_dir=workspace.results_dir,
            reports_dir=workspace.reports_dir,
            metadata_dir=workspace.metadata_dir,
            runtime_config_path=workspace.runtime_config_path,
            status_json_path=workspace.status_json_path,
            status_html_path=workspace.status_html_path,
            combo_summary_path=workspace.combo_summary_path,
            symbol_summary_path=workspace.symbol_summary_path,
            leaderboard_path=workspace.leaderboard_path,
            registry_path=workspace.registry_path,
            top10_path=workspace.top10_path,
            db_path=workspace.db_path,
            control_path=workspace.control_path,
            run_metadata_path=workspace.run_metadata_path,
            run_metadata_run_path=workspace.run_metadata_run_path,
        )


def build_run_workspace(cwd: str | Path, run_id: str, artifacts_dir_name: str = "artifacts") -> RunWorkspace:
    """Build a run-local workspace description for future path migration."""

    return RunWorkspace(cwd=Path(cwd), run_id=run_id, artifacts_dir_name=artifacts_dir_name)


def get_runs_dir(cwd: str | Path, artifacts_dir_name: str = "artifacts") -> Path:
    """Return the shared runs archive root for a working directory."""

    return Path(cwd) / artifacts_dir_name / "runs"
