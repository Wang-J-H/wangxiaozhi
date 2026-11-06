from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "dev"


def _load_script(name: str):
    path = SCRIPTS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("script_name", ["run_native_api", "run_native_worker"])
def test_native_launcher_bootstraps_backend_and_package_paths(script_name: str, monkeypatch):
    module = _load_script(script_name)
    monkeypatch.setattr(sys, "path", list(sys.path))

    backend_dir, package_dir = module.configure_import_paths()

    assert sys.path[0] == str(package_dir)
    assert str(backend_dir) in sys.path[:2]


@pytest.mark.parametrize("script_name", ["run_native_api", "run_native_worker"])
def test_native_launcher_does_not_patch_database_schema(script_name: str):
    source = (SCRIPTS_DIR / f"{script_name}.py").read_text(encoding="utf-8")

    assert "User.__table__" not in source
    assert "append_constraint" not in source


def test_smoke_config_requires_base_url_and_api_key():
    module = _load_script("smoke_agent_hub_contract")

    with pytest.raises(module.SmokeFailure, match="XIAOZHI_BASE_URL"):
        module.SmokeConfig.from_environ({})
    with pytest.raises(module.SmokeFailure, match="XIAOZHI_API_KEY"):
        module.SmokeConfig.from_environ({"XIAOZHI_BASE_URL": "http://127.0.0.1:5050"})


def test_sse_parser_ignores_heartbeat_and_decodes_nested_message_event():
    module = _load_script("smoke_agent_hub_contract")
    lines = [
        ": heartbeat",
        "",
        "id: 12-0",
        "event: messages",
        'data: {"payload":{"items":[{"stream_event":{"type":"message_delta","content":"ok"}}]}}',
        "",
        "event: end",
        'data: {"payload":{"status":"completed"}}',
        "",
    ]

    events = list(module.parse_sse_lines(lines))

    assert [(item.event, item.event_id) for item in events] == [("messages", "12-0"), ("end", None)]
    assert module.stream_event_types(events[0].data) == {"message_delta"}


def test_redact_removes_api_key_from_errors():
    module = _load_script("smoke_agent_hub_contract")
    secret = "yxkey_super_secret"

    assert secret not in module.redact(f"request failed for {secret}", secret)


def test_cancel_stream_allows_terminal_end_before_first_message():
    module = _load_script("smoke_agent_hub_contract")

    module.validate_stream_observation(
        "cancel-run",
        seen_events={"end"},
        nested_types=set(),
        require_messages=False,
    )
