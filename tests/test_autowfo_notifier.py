import json

from autowfo.notifier import NotificationEvent, notify


def test_notify_noop_when_config_absent(tmp_path):
    result = notify(
        NotificationEvent.STRATEGY_CHANGED,
        {"experiment_id": "exp_missing"},
        config_path=tmp_path / "artifacts" / "notifier_config.json",
    )
    assert result["ok"] is True
    assert result["sent"] == []
    assert "config_missing" in result["skipped"]


def test_notify_webhook_posts_event_payload_schema(tmp_path, monkeypatch):
    cfg_path = tmp_path / "artifacts" / "notifier_config.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        json.dumps(
            {
                "webhook": {
                    "enabled": True,
                    "url": "https://example.com/hook",
                    "timeout_seconds": 3,
                }
            }
        ),
        encoding="utf-8",
    )

    captured = {}

    class _DummyResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            _ = (exc_type, exc, tb)
            return False

    def _fake_urlopen(req, timeout=10):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(req.headers)
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _DummyResponse()

    import autowfo.notifier as notifier_mod

    monkeypatch.setattr(notifier_mod.urllib_request, "urlopen", _fake_urlopen)
    result = notify(
        NotificationEvent.STRATEGY_CHANGED,
        {"previous_experiment_id": "exp_a", "experiment_id": "exp_b"},
        config_path=cfg_path,
    )

    assert result["ok"] is True
    assert result["sent"] == ["webhook"]
    assert captured["url"] == "https://example.com/hook"
    assert captured["timeout"] == 3
    assert captured["body"]["event_type"] == "STRATEGY_CHANGED"
    assert "event_utc" in captured["body"]
    assert captured["body"]["payload"]["experiment_id"] == "exp_b"


def test_notify_telegram_missing_credentials_is_graceful_skip(tmp_path):
    cfg_path = tmp_path / "artifacts" / "notifier_config.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        json.dumps(
            {
                "telegram": {
                    "enabled": True,
                    "bot_token": "",
                    "chat_id": "",
                }
            }
        ),
        encoding="utf-8",
    )

    result = notify(
        NotificationEvent.POSITION_CLOSED,
        {"experiment_id": "exp_tg", "pnl_pct": 1.5},
        config_path=cfg_path,
    )
    assert result["ok"] is True
    assert result["sent"] == []
    assert "telegram_missing_credentials" in result["skipped"]

