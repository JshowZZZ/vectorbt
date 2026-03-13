"""Control panel entrypoint with routed handler dispatch (AWF-146)."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from autowfo.engine_helpers import DEFAULT_CONFIG
from . import batch as cp_batch_mod
from . import config as cp_config_mod
from . import coverage as cp_coverage_mod
from . import dashboard as cp_dashboard_mod
from . import data as cp_data_mod
from . import experiments as cp_experiments
from . import results as cp_results_mod
from . import signals as cp_signals_mod
from . import runtime as cp_runtime_mod
from . import state as cp_state_mod

# Re-export helper surfaces for compatibility with existing tests/callers.
from autowfo.control_panel.state import *  # noqa: F401,F403
from autowfo.control_panel.config import *  # noqa: F401,F403
from autowfo.control_panel.batch import *  # noqa: F401,F403
from autowfo.control_panel.coverage import *  # noqa: F401,F403
from autowfo.control_panel.results import *  # noqa: F401,F403
from autowfo.control_panel.signals import *  # noqa: F401,F403
from autowfo.control_panel.dashboard import *  # noqa: F401,F403
from autowfo.control_panel.data import *  # noqa: F401,F403

BATCH_DEFAULT_MIN_FREE_GB = 20.0
MAX_ROWS = 5000
LOG_MAX_LINES = 2000
LIVE_SIGNAL_CONFIG_SUBDIR = "live_signal_configs"
PAPER_FEEDBACK_FILE = "paper_feedback.ndjson"
FEEDBACK_RECOMMEND_DEFAULT_MIN_SAMPLES = 3
ADVANCED_ANALYSIS_DEFAULT_TRIALS = 2000
ADVANCED_ANALYSIS_MAX_TRIALS = 50000
ADVANCED_ANALYSIS_MAX_SAMPLE_SIZE = 10000
DASHBOARD_TOP_N_DEFAULT = 20
DASHBOARD_TOP_N_MIN = 1
DASHBOARD_TOP_N_MAX = 200
DASHBOARD_ERROR_EVENTS_FILE = "dashboard_error_events.ndjson"
DASHBOARD_ERROR_EVENTS_DEFAULT_LIMIT = 100
DASHBOARD_ERROR_EVENTS_MAX_LIMIT = 1000
DASHBOARD_ERROR_EVENTS_MAX_ROWS = 5000
DASHBOARD_ERROR_EVENTS_SINCE_HOURS_MAX = 24 * 30
FEEDBACK_SWEEP_RISK_LIMITS = {
    "tp_stop": (0.0005, 0.2),
    "sl_stop": (0.0005, 0.2),
    "max_hold": (1, 240),
}

INDEX_HTML = "<!doctype html><html><body><h1>AUTOWFO Control Panel</h1></body></html>"
APP_JS = "console.warn('fallback app.js used');"
RUNTIME = cp_runtime_mod.create_runtime()


def _sync_runtime_aliases() -> None:
    global ROOT, ARTIFACTS, STATUS_JSON, STATUS_HTML, RUN_LOG, TEST_STATUS_JSON, TEST_LOG
    global DB_PATH, CONFIG_JSON, CONTROL_JSON, PACKAGE_DIR, CONTROL_PANEL_DIR, STATIC_DIR, STATIC_LEGACY_DIR
    global PROCESS_LOCK, PROCESS, TEST_PROCESS_LOCK, TEST_PROCESS, BATCH_PROCESS_LOCK, BATCH_PROCESS
    global SYMBOL_CACHE, TIMEFRAME_CACHE
    global DATA_REFRESH_INTERVAL_SECONDS, DATA_REFRESH_LOCK, DATA_REFRESH_THREAD_LOCK, DATA_REFRESH_THREAD, DATA_REFRESH_STOP

    paths = RUNTIME.paths
    PACKAGE_DIR = paths.package_dir
    ROOT = paths.root
    ARTIFACTS = paths.artifacts
    STATUS_JSON = paths.status_json
    STATUS_HTML = paths.status_html
    RUN_LOG = paths.run_log
    TEST_STATUS_JSON = paths.test_status_json
    TEST_LOG = paths.test_log
    DB_PATH = paths.db_path
    CONFIG_JSON = paths.config_json
    CONTROL_JSON = paths.control_json
    CONTROL_PANEL_DIR = paths.control_panel_dir
    STATIC_DIR = paths.static_dir
    STATIC_LEGACY_DIR = paths.static_legacy_dir

    PROCESS_LOCK = RUNTIME.processes.process_lock
    PROCESS = RUNTIME.processes.process
    TEST_PROCESS_LOCK = RUNTIME.processes.test_process_lock
    TEST_PROCESS = RUNTIME.processes.test_process
    BATCH_PROCESS_LOCK = RUNTIME.processes.batch_process_lock
    BATCH_PROCESS = RUNTIME.processes.batch_process

    SYMBOL_CACHE = RUNTIME.symbol_cache
    TIMEFRAME_CACHE = RUNTIME.timeframe_cache

    DATA_REFRESH_INTERVAL_SECONDS = RUNTIME.data_refresh.interval_seconds
    DATA_REFRESH_LOCK = RUNTIME.data_refresh.lock
    DATA_REFRESH_THREAD_LOCK = RUNTIME.data_refresh.thread_lock
    DATA_REFRESH_THREAD = RUNTIME.data_refresh.thread
    DATA_REFRESH_STOP = RUNTIME.data_refresh.stop_event


def _sync_runtime_from_aliases(*names: str) -> None:
    sync_names = {str(name) for name in names if str(name)}
    if not sync_names:
        sync_names = {
            "ROOT",
            "ARTIFACTS",
            "STATUS_JSON",
            "STATUS_HTML",
            "RUN_LOG",
            "TEST_STATUS_JSON",
            "TEST_LOG",
            "DB_PATH",
            "CONFIG_JSON",
            "CONTROL_JSON",
            "STATIC_DIR",
            "STATIC_LEGACY_DIR",
            "PROCESS",
            "TEST_PROCESS",
            "BATCH_PROCESS",
            "SYMBOL_CACHE",
            "TIMEFRAME_CACHE",
            "DATA_REFRESH_THREAD",
            "DATA_REFRESH_INTERVAL_SECONDS",
        }
    if sync_names & {
        "ROOT",
        "ARTIFACTS",
        "STATUS_JSON",
        "STATUS_HTML",
        "RUN_LOG",
        "TEST_STATUS_JSON",
        "TEST_LOG",
        "DB_PATH",
        "CONFIG_JSON",
        "CONTROL_JSON",
        "STATIC_DIR",
        "STATIC_LEGACY_DIR",
    }:
        RUNTIME.reconfigure_paths(
            root=ROOT,
            artifacts_dir=ARTIFACTS,
            status_json=STATUS_JSON,
            status_html=STATUS_HTML,
            run_log=RUN_LOG,
            test_status_json=TEST_STATUS_JSON,
            test_log=TEST_LOG,
            db_path=DB_PATH,
            config_json=CONFIG_JSON,
            control_json=CONTROL_JSON,
            static_dir=STATIC_DIR,
            static_legacy_dir=STATIC_LEGACY_DIR,
        )
    if "PROCESS" in sync_names:
        RUNTIME.processes.process = PROCESS
    if "TEST_PROCESS" in sync_names:
        RUNTIME.processes.test_process = TEST_PROCESS
    if "BATCH_PROCESS" in sync_names:
        RUNTIME.processes.batch_process = BATCH_PROCESS
    if "SYMBOL_CACHE" in sync_names:
        RUNTIME.symbol_cache = SYMBOL_CACHE
    if "TIMEFRAME_CACHE" in sync_names:
        RUNTIME.timeframe_cache = TIMEFRAME_CACHE
    if "DATA_REFRESH_THREAD" in sync_names:
        RUNTIME.data_refresh.thread = DATA_REFRESH_THREAD
    if "DATA_REFRESH_INTERVAL_SECONDS" in sync_names:
        try:
            RUNTIME.data_refresh.interval_seconds = max(1, int(DATA_REFRESH_INTERVAL_SECONDS))
        except Exception:
            RUNTIME.data_refresh.interval_seconds = 1800
    _sync_runtime_aliases()


def get_runtime():
    return RUNTIME


def configure_runtime(
    *,
    root=None,
    artifacts_dir=None,
    static_dir=None,
    static_legacy_dir=None,
    status_json=None,
    status_html=None,
    run_log=None,
    test_status_json=None,
    test_log=None,
    db_path=None,
    config_json=None,
    control_json=None,
    data_refresh_interval_seconds=None,
    reset_state: bool = False,
):
    current_paths = RUNTIME.paths
    artifacts_root_changed = root is not None or artifacts_dir is not None
    RUNTIME.paths = cp_runtime_mod.ControlPanelPaths.build(
        root=root if root is not None else current_paths.root,
        artifacts_dir=artifacts_dir if artifacts_dir is not None else (None if root is not None else current_paths.artifacts),
        package_dir=current_paths.package_dir,
        static_dir=static_dir if static_dir is not None else current_paths.static_dir,
        static_legacy_dir=static_legacy_dir if static_legacy_dir is not None else current_paths.static_legacy_dir,
        status_json=status_json if status_json is not None else (None if artifacts_root_changed else current_paths.status_json),
        status_html=status_html if status_html is not None else (None if artifacts_root_changed else current_paths.status_html),
        run_log=run_log if run_log is not None else (None if artifacts_root_changed else current_paths.run_log),
        test_status_json=(
            test_status_json if test_status_json is not None else (None if artifacts_root_changed else current_paths.test_status_json)
        ),
        test_log=test_log if test_log is not None else (None if artifacts_root_changed else current_paths.test_log),
        db_path=db_path if db_path is not None else (None if artifacts_root_changed else current_paths.db_path),
        config_json=(
            config_json if config_json is not None else (None if artifacts_root_changed else current_paths.config_json)
        ),
        control_json=(
            control_json if control_json is not None else (None if artifacts_root_changed else current_paths.control_json)
        ),
    )
    if data_refresh_interval_seconds is not None:
        try:
            RUNTIME.data_refresh.interval_seconds = max(1, int(data_refresh_interval_seconds))
        except Exception:
            RUNTIME.data_refresh.interval_seconds = 1800
    if reset_state:
        RUNTIME.reset_transient_state()
    _sync_runtime_aliases()
    return RUNTIME


def reset_runtime_state() -> None:
    RUNTIME.reset_transient_state()
    _sync_runtime_aliases()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the AUTOWFO control panel server.")
    parser.add_argument("--host", default=os.getenv("AUTOWFO_CONTROL_PANEL_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=_env_int("AUTOWFO_CONTROL_PANEL_PORT", 8787))
    parser.add_argument("--root", default=os.getenv("AUTOWFO_ROOT", ""))
    parser.add_argument("--artifacts-dir", default=os.getenv("AUTOWFO_ARTIFACTS_DIR", ""))
    parser.add_argument(
        "--data-refresh-interval-seconds",
        type=int,
        default=_env_int("AUTOWFO_DATA_REFRESH_INTERVAL_SECONDS", 1800),
    )
    parser.add_argument(
        "--no-data-refresh-thread",
        action="store_true",
        help="Start the HTTP server without the background OHLCV refresh daemon.",
    )
    return parser


_sync_runtime_aliases()


def _route_modules_get():
    return (
        cp_state_mod,
        cp_batch_mod,
        cp_coverage_mod,
        cp_data_mod,
        cp_signals_mod,
        cp_dashboard_mod,
        cp_results_mod,
        cp_config_mod,
    )


def _route_modules_post():
    return (
        cp_state_mod,
        cp_data_mod,
        cp_signals_mod,
        cp_batch_mod,
        cp_coverage_mod,
        cp_dashboard_mod,
        cp_config_mod,
    )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send(self, data, content_type="text/html; charset=utf-8", status=HTTPStatus.OK):
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def _send_with_headers(self, data, content_type="text/html; charset=utf-8", status=HTTPStatus.OK, headers=None):
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", content_type)
        if headers:
            for key, val in headers.items():
                self.send_header(str(key), str(val))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def _read_json_payload(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(body.decode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        static_no_cache_headers = {
            "Cache-Control": "no-store, max-age=0, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
        if path == "/":
            return self._send_with_headers(
                _read_static_text("index.html", fallback=INDEX_HTML),
                headers=static_no_cache_headers,
            )
        if path in {"/favicon.ico", "/favicon.svg"}:
            favicon_path = STATIC_DIR / "favicon.svg"
            if favicon_path.exists():
                return self._send_with_headers(
                    favicon_path.read_bytes(),
                    "image/svg+xml",
                    headers=static_no_cache_headers,
                )
        static_path = _resolve_static_path(path)
        if static_path is not None:
            mime, _ = mimetypes.guess_type(str(static_path))
            content_type = mime or "application/octet-stream"
            if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
                content_type = f"{content_type}; charset=utf-8"
            return self._send_with_headers(
                static_path.read_bytes(),
                content_type,
                headers=static_no_cache_headers,
            )
        if path == "/app.js":
            return self._send_with_headers(
                _read_static_text("js/app.js", fallback=APP_JS),
                "application/javascript; charset=utf-8",
                headers=static_no_cache_headers,
            )
        if path == "/experiments.json":
            return cp_experiments._handle_experiments_list(self)
        exp_config_match = cp_experiments.EXPERIMENT_CONFIG_PATH_RE.fullmatch(path)
        if exp_config_match:
            return cp_experiments._handle_experiment_config(self, exp_config_match.group("experiment_id"))
        exp_runs_match = cp_experiments.EXPERIMENT_RUNS_LIST_PATH_RE.fullmatch(path)
        if exp_runs_match:
            return cp_experiments._handle_experiment_runs_list(self, exp_runs_match.group("experiment_id"))
        exp_run_results_match = cp_experiments.EXPERIMENT_RUN_RESULTS_PATH_RE.fullmatch(path)
        if exp_run_results_match:
            return cp_experiments._handle_experiment_run_results(
                self,
                exp_run_results_match.group("experiment_id"),
                exp_run_results_match.group("run_id"),
            )
        if cp_experiments.SCHEDULER_STATUS_PATH_RE.fullmatch(path):
            return cp_experiments._handle_scheduler_status(self)
        if cp_experiments.ANALYTICS_LEADERBOARD_PATH_RE.fullmatch(path):
            return cp_experiments._handle_analytics_leaderboard(self)
        if cp_experiments.ANALYTICS_BEST_PATH_RE.fullmatch(path):
            return cp_experiments._handle_analytics_best(self)
        if cp_experiments.ANALYTICS_COVERAGE_MAP_PATH_RE.fullmatch(path):
            return cp_experiments._handle_analytics_coverage_map(self)
        if cp_experiments.ANALYTICS_GROWTH_PATH_RE.fullmatch(path):
            return cp_experiments._handle_analytics_growth(self)
        if cp_experiments.ANALYTICS_REPORT_HTML_PATH_RE.fullmatch(path):
            return cp_experiments._handle_analytics_report_html(self)
        if cp_experiments.PAPER_POSITIONS_PATH_RE.fullmatch(path):
            return cp_experiments._handle_paper_positions(self)
        if cp_experiments.PAPER_PORTFOLIO_PATH_RE.fullmatch(path):
            return cp_experiments._handle_paper_portfolio(self)
        if cp_experiments.OPS_STORAGE_HEALTH_PATH_RE.fullmatch(path):
            return cp_experiments._handle_storage_health(self)

        for mod in _route_modules_get():
            try_handler = getattr(mod, "try_handle_get", None)
            if callable(try_handler) and try_handler(self, parsed, path):
                return
        return self._send("Not Found", status=HTTPStatus.NOT_FOUND)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/experiments/create":
            return cp_experiments._handle_experiments_create(self)
        if cp_experiments.EXPERIMENT_QUEUE_PATH_RE.fullmatch(parsed.path):
            return cp_experiments._handle_experiments_queue(self)
        if cp_experiments.SCHEDULER_STOP_PATH_RE.fullmatch(parsed.path):
            return cp_experiments._handle_scheduler_stop(self)
        exp_run_match = cp_experiments.EXPERIMENT_RUN_PATH_RE.fullmatch(parsed.path)
        if exp_run_match:
            return cp_experiments._handle_experiment_run(self, exp_run_match.group("experiment_id"))
        if cp_experiments.DISCOVERY_TICK_PATH_RE.fullmatch(parsed.path):
            return cp_experiments._handle_discovery_tick(self)
        if cp_experiments.PAPER_OPEN_PATH_RE.fullmatch(parsed.path):
            return cp_experiments._handle_paper_open(self)
        if cp_experiments.PAPER_CLOSE_PATH_RE.fullmatch(parsed.path):
            return cp_experiments._handle_paper_close(self)

        for mod in _route_modules_post():
            try_handler = getattr(mod, "try_handle_post", None)
            if callable(try_handler) and try_handler(self, parsed):
                return
        return self._send("Not Found", status=HTTPStatus.NOT_FOUND)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        exp_delete_match = cp_experiments.EXPERIMENT_DELETE_PATH_RE.fullmatch(parsed.path)
        if exp_delete_match:
            return cp_experiments._handle_experiment_delete(self, exp_delete_match.group("experiment_id"))
        return self._send("Not Found", status=HTTPStatus.NOT_FOUND)


def main(argv=None):
    args = _build_arg_parser().parse_args(argv)
    configure_runtime(
        root=args.root or None,
        artifacts_dir=args.artifacts_dir or None,
        data_refresh_interval_seconds=args.data_refresh_interval_seconds,
    )
    if not args.no_data_refresh_thread:
        _ensure_data_refresh_thread()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"AUTOWFO control panel serving at http://{args.host}:{args.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        if not args.no_data_refresh_thread:
            RUNTIME.data_refresh.reset()
            _sync_runtime_aliases()
    return 0

