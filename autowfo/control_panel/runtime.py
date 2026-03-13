"""Runtime and path primitives for the AUTOWFO control panel."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import threading


PACKAGE_DIR = Path(__file__).resolve().parent


def _resolve_path(value, base: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (base / path).resolve()
    else:
        path = path.resolve()
    return path


@dataclass(frozen=True)
class ControlPanelPaths:
    root: Path
    artifacts: Path
    package_dir: Path
    control_panel_dir: Path
    static_dir: Path
    static_legacy_dir: Path
    status_json: Path
    status_html: Path
    run_log: Path
    test_status_json: Path
    test_log: Path
    db_path: Path
    config_json: Path
    control_json: Path

    @classmethod
    def build(
        cls,
        *,
        root: str | Path | None = None,
        artifacts_dir: str | Path | None = None,
        package_dir: str | Path | None = None,
        static_dir: str | Path | None = None,
        static_legacy_dir: str | Path | None = None,
        status_json: str | Path | None = None,
        status_html: str | Path | None = None,
        run_log: str | Path | None = None,
        test_status_json: str | Path | None = None,
        test_log: str | Path | None = None,
        db_path: str | Path | None = None,
        config_json: str | Path | None = None,
        control_json: str | Path | None = None,
    ) -> "ControlPanelPaths":
        package_dir_path = _resolve_path(package_dir, PACKAGE_DIR.parent) if package_dir else PACKAGE_DIR
        root_path = _resolve_path(root, Path.cwd()) if root else Path.cwd().resolve()
        artifacts_path = (
            _resolve_path(artifacts_dir, root_path) if artifacts_dir is not None else (root_path / "artifacts").resolve()
        )
        control_panel_dir = package_dir_path
        static_dir_path = (
            _resolve_path(static_dir, package_dir_path) if static_dir is not None else (package_dir_path / "static").resolve()
        )
        static_legacy_dir_path = (
            _resolve_path(static_legacy_dir, package_dir_path)
            if static_legacy_dir is not None
            else (package_dir_path / "static_legacy").resolve()
        )
        return cls(
            root=root_path,
            artifacts=artifacts_path,
            package_dir=package_dir_path,
            control_panel_dir=control_panel_dir,
            static_dir=static_dir_path,
            static_legacy_dir=static_legacy_dir_path,
            status_json=_resolve_path(status_json, artifacts_path) if status_json is not None else artifacts_path / "run_status.json",
            status_html=_resolve_path(status_html, artifacts_path) if status_html is not None else artifacts_path / "run_status.html",
            run_log=_resolve_path(run_log, artifacts_path) if run_log is not None else artifacts_path / "run_console.log",
            test_status_json=(
                _resolve_path(test_status_json, artifacts_path)
                if test_status_json is not None
                else artifacts_path / "test_status.json"
            ),
            test_log=_resolve_path(test_log, artifacts_path) if test_log is not None else artifacts_path / "test_console.log",
            db_path=_resolve_path(db_path, artifacts_path) if db_path is not None else artifacts_path / "results.db",
            config_json=(
                _resolve_path(config_json, artifacts_path) if config_json is not None else artifacts_path / "sweep_config.json"
            ),
            control_json=(
                _resolve_path(control_json, artifacts_path)
                if control_json is not None
                else artifacts_path / "run_control.json"
            ),
        )


@dataclass
class ProcessRuntime:
    process_lock: threading.Lock = field(default_factory=threading.Lock)
    test_process_lock: threading.Lock = field(default_factory=threading.Lock)
    batch_process_lock: threading.Lock = field(default_factory=threading.Lock)
    process: object | None = None
    test_process: object | None = None
    batch_process: object | None = None

    @staticmethod
    def _is_active(proc: object | None) -> bool:
        return bool(proc is not None and getattr(proc, "poll", lambda: 1)() is None)

    def is_running(self) -> bool:
        return self._is_active(self.process)

    def is_test_running(self) -> bool:
        return self._is_active(self.test_process)

    def is_batch_running(self) -> bool:
        return self._is_active(self.batch_process)

    def reset(self) -> None:
        self.process = None
        self.test_process = None
        self.batch_process = None


@dataclass
class DataRefreshRuntime:
    interval_seconds: int = 1800
    lock: threading.Lock = field(default_factory=threading.Lock)
    thread_lock: threading.Lock = field(default_factory=threading.Lock)
    thread: threading.Thread | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)

    def reset(self, join_timeout: float = 1.0) -> None:
        self.stop_event.set()
        thread = self.thread
        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(timeout=max(0.0, float(join_timeout)))
        self.thread = None
        self.stop_event.clear()


@dataclass
class SchedulerRuntime:
    lock: threading.Lock = field(default_factory=threading.Lock)
    thread_lock: threading.Lock = field(default_factory=threading.Lock)
    thread: threading.Thread | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    running: bool = False
    last_error: str = ""
    last_run_utc: str = ""

    def mark(self, *, running: bool, last_run_utc: str, last_error: str | None = None) -> None:
        with self.lock:
            self.running = bool(running)
            self.last_run_utc = str(last_run_utc or "")
            if last_error is not None:
                self.last_error = str(last_error or "")

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "is_running": bool(self.running),
                "last_run_utc": str(self.last_run_utc or ""),
                "last_error": str(self.last_error or ""),
            }

    def reset(self, join_timeout: float = 1.0) -> None:
        self.stop_event.set()
        thread = self.thread
        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(timeout=max(0.0, float(join_timeout)))
        self.thread = None
        self.stop_event.clear()
        with self.lock:
            self.running = False
            self.last_error = ""
            self.last_run_utc = ""


@dataclass
class ControlPanelRuntime:
    paths: ControlPanelPaths
    processes: ProcessRuntime = field(default_factory=ProcessRuntime)
    data_refresh: DataRefreshRuntime = field(default_factory=DataRefreshRuntime)
    scheduler: SchedulerRuntime = field(default_factory=SchedulerRuntime)
    symbol_cache: dict = field(default_factory=lambda: {"ts": 0, "symbols": []})
    timeframe_cache: dict = field(default_factory=lambda: {"ts": 0, "mtime": 0, "values": []})

    def reconfigure_paths(self, **kwargs) -> None:
        self.paths = ControlPanelPaths.build(
            root=kwargs.get("root", self.paths.root),
            artifacts_dir=kwargs.get("artifacts_dir", self.paths.artifacts),
            package_dir=kwargs.get("package_dir", self.paths.package_dir),
            static_dir=kwargs.get("static_dir", self.paths.static_dir),
            static_legacy_dir=kwargs.get("static_legacy_dir", self.paths.static_legacy_dir),
            status_json=kwargs.get("status_json", self.paths.status_json),
            status_html=kwargs.get("status_html", self.paths.status_html),
            run_log=kwargs.get("run_log", self.paths.run_log),
            test_status_json=kwargs.get("test_status_json", self.paths.test_status_json),
            test_log=kwargs.get("test_log", self.paths.test_log),
            db_path=kwargs.get("db_path", self.paths.db_path),
            config_json=kwargs.get("config_json", self.paths.config_json),
            control_json=kwargs.get("control_json", self.paths.control_json),
        )

    def reset_transient_state(self) -> None:
        self.processes.reset()
        self.data_refresh.reset()
        self.scheduler.reset()
        self.symbol_cache = {"ts": 0, "symbols": []}
        self.timeframe_cache = {"ts": 0, "mtime": 0, "values": []}


def create_runtime(**kwargs) -> ControlPanelRuntime:
    return ControlPanelRuntime(paths=ControlPanelPaths.build(**kwargs))
