from __future__ import annotations

import json
import os
import sys
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


ACTIVE_RUN_STATUSES = {"pending", "running", "cancel_requested"}
TERMINAL_SSE_EVENTS = {"end", "error"}


class SmokeFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class SmokeConfig:
    base_url: str
    api_key: str = field(repr=False)
    timeout_seconds: float = 180.0
    query: str = "请只用一句简短中文回复：Agent Hub 契约 smoke 已通过。"
    cancel_query: str = "请详细列出二十条办公室整理建议，每条附一句说明。"

    @classmethod
    def from_environ(cls, environ: Mapping[str, str] = os.environ) -> "SmokeConfig":
        base_url = environ.get("XIAOZHI_BASE_URL", "").strip().rstrip("/")
        if not base_url:
            raise SmokeFailure("XIAOZHI_BASE_URL 未配置")
        if not base_url.startswith(("http://", "https://")):
            raise SmokeFailure("XIAOZHI_BASE_URL 必须是 http(s) URL")

        api_key = environ.get("XIAOZHI_API_KEY", "").strip()
        if not api_key:
            raise SmokeFailure("XIAOZHI_API_KEY 未配置")

        timeout_value = environ.get("XIAOZHI_SMOKE_TIMEOUT", "180").strip()
        try:
            timeout_seconds = float(timeout_value)
        except ValueError as exc:
            raise SmokeFailure("XIAOZHI_SMOKE_TIMEOUT 必须是数字") from exc
        if timeout_seconds <= 0:
            raise SmokeFailure("XIAOZHI_SMOKE_TIMEOUT 必须大于 0")

        return cls(
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            query=environ.get("XIAOZHI_SMOKE_QUERY", cls.query).strip() or cls.query,
            cancel_query=environ.get("XIAOZHI_SMOKE_CANCEL_QUERY", cls.cancel_query).strip() or cls.cancel_query,
        )


@dataclass(frozen=True)
class SseEvent:
    event: str
    data: dict[str, Any]
    event_id: str | None = None


def redact(value: str, secret: str) -> str:
    return value.replace(secret, "[REDACTED]") if secret else value


def parse_sse_lines(lines: Iterable[str]) -> Iterable[SseEvent]:
    event_name: str | None = None
    event_id: str | None = None
    data_lines: list[str] = []

    for raw_line in lines:
        line = raw_line.rstrip("\r\n")
        if not line:
            if data_lines:
                raw_data = "\n".join(data_lines)
                try:
                    parsed = json.loads(raw_data)
                except json.JSONDecodeError as exc:
                    raise SmokeFailure("SSE data 不是合法 JSON") from exc
                if not isinstance(parsed, dict):
                    raise SmokeFailure("SSE data 必须是 JSON object")
                yield SseEvent(event=event_name or "message", data=parsed, event_id=event_id)
            event_name = None
            event_id = None
            data_lines = []
            continue

        if line.startswith(":"):
            continue
        field_name, separator, field_value = line.partition(":")
        if separator and field_value.startswith(" "):
            field_value = field_value[1:]
        if field_name == "event":
            event_name = field_value
        elif field_name == "id":
            event_id = field_value
        elif field_name == "data":
            data_lines.append(field_value)

    if data_lines:
        raw_data = "\n".join(data_lines)
        try:
            parsed = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            raise SmokeFailure("SSE data 不是合法 JSON") from exc
        if not isinstance(parsed, dict):
            raise SmokeFailure("SSE data 必须是 JSON object")
        yield SseEvent(event=event_name or "message", data=parsed, event_id=event_id)


def stream_event_types(event_data: Mapping[str, Any]) -> set[str]:
    payload = event_data.get("payload")
    if not isinstance(payload, dict):
        return set()

    chunks: list[Any] = []
    if isinstance(payload.get("chunk"), dict):
        chunks.append(payload["chunk"])
    if isinstance(payload.get("items"), list):
        chunks.extend(payload["items"])

    result: set[str] = set()
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        stream_event = chunk.get("stream_event")
        if isinstance(stream_event, dict) and isinstance(stream_event.get("type"), str):
            result.add(stream_event["type"])
    return result


def _response_json(response: Any, label: str, api_key: str) -> dict[str, Any] | list[Any]:
    if not 200 <= response.status_code < 300:
        body = redact(response.text[:500], api_key)
        raise SmokeFailure(f"{label} HTTP {response.status_code}: {body}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise SmokeFailure(f"{label} 未返回 JSON") from exc
    if not isinstance(payload, (dict, list)):
        raise SmokeFailure(f"{label} JSON 类型错误")
    return payload


def _dict_payload(payload: dict[str, Any] | list[Any], label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SmokeFailure(f"{label} 应返回 JSON object")
    return payload


def _pass(label: str, detail: str | None = None) -> None:
    suffix = f" ({detail})" if detail else ""
    print(f"[PASS] {label}{suffix}")


def validate_stream_observation(
    run_id: str,
    *,
    seen_events: set[str],
    nested_types: set[str],
    require_messages: bool,
) -> None:
    if require_messages and "messages" not in seen_events:
        raise SmokeFailure(f"run {run_id} 未观察到 messages SSE")
    if "end" not in seen_events:
        raise SmokeFailure(f"run {run_id} 未观察到 end SSE")
    if require_messages and not nested_types:
        raise SmokeFailure(f"run {run_id} messages SSE 不含 stream_event")


def _stream_run(
    client: Any,
    run_id: str,
    api_key: str,
    *,
    require_messages: bool = True,
) -> tuple[set[str], str]:
    seen_events: set[str] = set()
    nested_types: set[str] = set()
    terminal_status = ""

    with client.stream(
        "GET",
        f"/api/agent/runs/{run_id}/events",
        params={"after_seq": "0-0", "verbose": "false"},
    ) as response:
        if not 200 <= response.status_code < 300:
            response.read()
            body = redact(response.text[:500], api_key)
            raise SmokeFailure(f"SSE HTTP {response.status_code}: {body}")

        for item in parse_sse_lines(response.iter_lines()):
            seen_events.add(item.event)
            if item.event == "messages":
                nested_types.update(stream_event_types(item.data))
            if item.event in TERMINAL_SSE_EVENTS:
                payload = item.data.get("payload")
                if isinstance(payload, dict):
                    terminal_status = str(payload.get("status") or "")
                if item.event == "error":
                    raise SmokeFailure(f"run {run_id} SSE 返回 error")
                break

    validate_stream_observation(
        run_id,
        seen_events=seen_events,
        nested_types=nested_types,
        require_messages=require_messages,
    )
    return nested_types, terminal_status


def run_smoke(config: SmokeConfig) -> None:
    import httpx

    headers = {"Authorization": f"Bearer {config.api_key}"}
    timeout = httpx.Timeout(config.timeout_seconds, connect=min(15.0, config.timeout_seconds))

    with httpx.Client(base_url=config.base_url, headers=headers, timeout=timeout) as client:
        health = _dict_payload(
            _response_json(client.get("/api/system/health"), "health", config.api_key),
            "health",
        )
        if str(health.get("status") or "").lower() not in {"ok", "healthy"}:
            raise SmokeFailure(f"health 状态异常: {health.get('status')!r}")
        _pass("health")

        default_payload = _dict_payload(
            _response_json(client.get("/api/agent/default"), "default agent", config.api_key),
            "default agent",
        )
        agent = default_payload.get("agent")
        if not isinstance(agent, dict):
            raise SmokeFailure("default agent 缺少 agent object")
        agent_slug = str(agent.get("slug") or agent.get("agent_id") or agent.get("id") or "").strip()
        if not agent_slug:
            raise SmokeFailure("default agent 缺少 slug")
        _pass("default agent", agent_slug)

        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        thread_payload = _dict_payload(
            _response_json(
                client.post(
                    "/api/chat/thread",
                    json={"title": f"Agent Hub smoke {timestamp}", "agent_id": agent_slug},
                ),
                "create thread",
                config.api_key,
            ),
            "create thread",
        )
        thread_id = str(thread_payload.get("id") or "").strip()
        if not thread_id:
            raise SmokeFailure("create thread 缺少 id")
        _pass("create thread", thread_id)

        run_payload = _dict_payload(
            _response_json(
                client.post(
                    "/api/agent/runs",
                    json={
                        "query": config.query,
                        "agent_slug": agent_slug,
                        "thread_id": thread_id,
                        "meta": {"request_id": f"agent-hub-smoke-{uuid.uuid4()}"},
                    },
                ),
                "create run",
                config.api_key,
            ),
            "create run",
        )
        run_id = str(run_payload.get("run_id") or "").strip()
        if not run_id:
            raise SmokeFailure("create run 缺少 run_id")
        _pass("create run", run_id)

        nested_types, terminal_status = _stream_run(client, run_id, config.api_key)
        _pass("compact SSE", f"types={','.join(sorted(nested_types))}; status={terminal_status or 'unknown'}")

        result_payload = _dict_payload(
            _response_json(client.get(f"/api/agent/runs/{run_id}/result"), "run result", config.api_key),
            "run result",
        )
        if result_payload.get("status") != "completed":
            raise SmokeFailure(f"run result 状态不是 completed: {result_payload.get('status')!r}")
        output = str(result_payload.get("output") or "").strip()
        if not output:
            raise SmokeFailure("run result output 为空")
        _pass("run result", "completed + non-empty output")

        threads_payload = _response_json(
            client.get("/api/chat/threads", params={"agent_id": agent_slug}),
            "list threads",
            config.api_key,
        )
        if not isinstance(threads_payload, list) or not any(
            isinstance(item, dict) and item.get("id") == thread_id for item in threads_payload
        ):
            raise SmokeFailure("新 thread 未出现在 threads 列表")
        _pass("thread list contains new thread")

        history_payload = _dict_payload(
            _response_json(
                client.get(f"/api/chat/thread/{thread_id}/history"),
                "thread history",
                config.api_key,
            ),
            "thread history",
        )
        history = history_payload.get("history")
        if not isinstance(history, list):
            raise SmokeFailure("thread history 缺少 history list")
        has_user = any(
            isinstance(item, dict) and item.get("type") == "human" and item.get("content") == config.query
            for item in history
        )
        has_assistant = any(
            isinstance(item, dict)
            and item.get("type") == "ai"
            and item.get("run_id") == run_id
            and bool(str(item.get("content") or "").strip())
            for item in history
        )
        if not (has_user and has_assistant):
            raise SmokeFailure("thread history 不含本轮 user/assistant 正文")
        _pass("thread history contains user + assistant")

        cancel_run_payload = _dict_payload(
            _response_json(
                client.post(
                    "/api/agent/runs",
                    json={
                        "query": config.cancel_query,
                        "agent_slug": agent_slug,
                        "thread_id": thread_id,
                        "meta": {"request_id": f"agent-hub-cancel-smoke-{uuid.uuid4()}"},
                    },
                ),
                "create cancel run",
                config.api_key,
            ),
            "create cancel run",
        )
        cancel_run_id = str(cancel_run_payload.get("run_id") or "").strip()
        if not cancel_run_id:
            raise SmokeFailure("create cancel run 缺少 run_id")

        cancel_payload = _dict_payload(
            _response_json(
                client.post(f"/api/agent/runs/{cancel_run_id}/cancel"),
                "cancel run",
                config.api_key,
            ),
            "cancel run",
        )
        cancelled_run = cancel_payload.get("run")
        if not isinstance(cancelled_run, dict):
            raise SmokeFailure("cancel run 缺少 run object")
        cancel_ack_status = str(cancelled_run.get("status") or "")
        if cancel_ack_status in {"pending", "running"}:
            raise SmokeFailure(f"cancel 后仍是活跃状态: {cancel_ack_status}")

        _stream_run(client, cancel_run_id, config.api_key, require_messages=False)
        cancelled_result = _dict_payload(
            _response_json(
                client.get(f"/api/agent/runs/{cancel_run_id}/result"),
                "cancelled run result",
                config.api_key,
            ),
            "cancelled run result",
        )
        final_cancel_status = str(cancelled_result.get("status") or "")
        if final_cancel_status in ACTIVE_RUN_STATUSES:
            raise SmokeFailure(f"cancel run 终态仍活跃: {final_cancel_status}")
        _pass("cancel reaches non-active terminal state", f"{cancel_run_id}: {final_cancel_status}")


def main() -> int:
    config: SmokeConfig | None = None
    try:
        config = SmokeConfig.from_environ()
        run_smoke(config)
    except Exception as exc:
        secret = config.api_key if config else os.environ.get("XIAOZHI_API_KEY", "")
        print(f"[FAIL] {redact(str(exc), secret)}", file=sys.stderr)
        return 1

    print("[PASS] Agent Hub Xiaozhi contract smoke complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
