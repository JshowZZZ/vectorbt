"""Control panel entrypoint with routed handler dispatch (AWF-146)."""

from __future__ import annotations

import json
import mimetypes
import subprocess
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
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


PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = Path.cwd().resolve()
ARTIFACTS = ROOT / "artifacts"
STATUS_JSON = ARTIFACTS / "run_status.json"
STATUS_HTML = ARTIFACTS / "run_status.html"
RUN_LOG = ARTIFACTS / "run_console.log"
TEST_STATUS_JSON = ARTIFACTS / "test_status.json"
TEST_LOG = ARTIFACTS / "test_console.log"
DB_PATH = ARTIFACTS / "results.db"
CONFIG_JSON = ARTIFACTS / "sweep_config.json"
CONTROL_JSON = ARTIFACTS / "run_control.json"
SCRIPT = Path(__file__).resolve().parents[1] / "run_btc_regime_sweep.py"
CONTROL_PANEL_DIR = PACKAGE_DIR
STATIC_DIR = PACKAGE_DIR / "static"
STATIC_LEGACY_DIR = PACKAGE_DIR / "static_legacy"
BATCH_DEFAULT_MIN_FREE_GB = 20.0

PROCESS_LOCK = threading.Lock()
PROCESS = None
TEST_PROCESS_LOCK = threading.Lock()
TEST_PROCESS = None
BATCH_PROCESS_LOCK = threading.Lock()
BATCH_PROCESS = None
MAX_ROWS = 5000
LOG_MAX_LINES = 2000

SYMBOL_CACHE = {"ts": 0, "symbols": []}
TIMEFRAME_CACHE = {"ts": 0, "mtime": 0, "values": []}
DATA_REFRESH_INTERVAL_SECONDS = 1800
DATA_REFRESH_LOCK = threading.Lock()
DATA_REFRESH_THREAD_LOCK = threading.Lock()
DATA_REFRESH_THREAD = None
DATA_REFRESH_STOP = threading.Event()
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


def main():
    host = "127.0.0.1"
    port = 8787
    _ensure_data_refresh_thread()
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"AUTOWFO control panel serving at http://{host}:{port}")
    httpd.serve_forever()

