#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import time
import urllib.request
from pathlib import Path
from typing import Any


URLS = {
    "aw1_latest": "https://aw1.awai.vn/log/latest.json",
    "aw1_index": "https://aw1.awai.vn/log/",
    "aw1_queue": "https://aw1.awai.vn/log/model_improvement_queue_public.json",
    "chat_latest": "https://chat.awai.vn/log/latest.json",
}


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def body_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def extract_generated_at_from_html(text: str) -> str | None:
    patterns = [
        r'"generated_at"\s*:\s*"([^"]+)"',
        r"generated_at[:=]\s*([0-9T:\-]+Z)",
        r"Generated(?: at)?:?\s*([0-9T:\-]+Z)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def parse_body(name: str, url: str, status_code: int, headers: Any, body: bytes, elapsed_ms: int) -> dict[str, Any]:
    text = body.decode("utf-8", "replace")
    row: dict[str, Any] = {
        "name": name,
        "url": url,
        "status_code": status_code,
        "cache_control": headers.get("cache-control"),
        "etag": headers.get("etag"),
        "last_modified": headers.get("last-modified"),
        "body_hash": body_hash(body),
        "elapsed_ms": elapsed_ms,
        "generated_at": None,
        "contains_PASS_WITH_NEWER_RUNTIME_LOG": "PASS_WITH_NEWER_RUNTIME_LOG" in text,
        "contains_stale_latest_true": "stale_latest=true" in text or '"stale_latest": true' in text,
    }
    stripped = text.lstrip()
    if stripped.startswith("{"):
        data = json.loads(text)
        for key in [
            "generated_at",
            "effective_verdict",
            "latest_effective_verdict",
            "verdict",
            "latest_verdict",
            "stale_latest",
            "queue_item_count",
            "model_improvement_candidate_count",
            "render_result",
            "newest_receipt_name",
        ]:
            if key in data:
                row[key] = data[key]
    else:
        row["generated_at"] = extract_generated_at_from_html(text)
    return row


def fetch(name: str, url: str) -> dict[str, Any]:
    started = time.time()
    full_url = url + ("&" if "?" in url else "?") + "github_watchdog=" + str(time.time_ns())
    request = urllib.request.Request(
        full_url,
        headers={
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": "AW1-GitHub-PublicTruthWatchdog/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read()
            return parse_body(name, url, response.status, response.headers, body, int((time.time() - started) * 1000))
    except Exception as exc:
        return {
            "name": name,
            "url": url,
            "error": type(exc).__name__,
            "detail": str(exc)[:240],
            "elapsed_ms": int((time.time() - started) * 1000),
        }


def row_fail_reasons(row: dict[str, Any]) -> list[str]:
    name = str(row.get("name") or row.get("url") or "unknown")
    if row.get("error"):
        return [f"{name}:transport_error"]
    if row.get("status_code") != 200:
        return [f"{name}:http_{row.get('status_code')}"]
    if row.get("contains_PASS_WITH_NEWER_RUNTIME_LOG"):
        return [f"{name}:pass_with_newer_runtime_log_marker"]
    if row.get("contains_stale_latest_true"):
        return [f"{name}:stale_latest_marker"]
    url = str(row.get("url") or "")
    if url.endswith("/log/latest.json") and "aw1.awai.vn" in url:
        if row.get("effective_verdict") != "PASS" and row.get("latest_effective_verdict") != "PASS":
            return ["aw1_latest:not_pass"]
        if row.get("stale_latest") is not False:
            return ["aw1_latest:stale_latest_not_false"]
    if "model_improvement_queue_public.json" in url:
        reasons = []
        if row.get("queue_item_count") != 0:
            reasons.append("aw1_queue:queue_item_count_not_zero")
        if row.get("model_improvement_candidate_count") != 0:
            reasons.append("aw1_queue:model_improvement_candidate_count_not_zero")
        return reasons
    if url.endswith("/log/latest.json") and "chat.awai.vn" in url:
        reasons = []
        if row.get("verdict") != "PASS":
            reasons.append("chat_latest:verdict_not_pass")
        if row.get("render_result") != "PASS":
            reasons.append("chat_latest:render_result_not_pass")
        return reasons
    return []


def main() -> int:
    fetched_at = utc_now()
    rows = [fetch(name, url) for name, url in URLS.items()]
    fail_reasons: list[str] = []
    for row in rows:
        fail_reasons.extend(row_fail_reasons(row))
    running_on_github_actions = os.getenv("GITHUB_ACTIONS") == "true"
    if not running_on_github_actions:
        fail_reasons.append("not_running_on_github_actions_hosted_runner")

    payload = {
        "vantage_id": "external_github_actions",
        "network": "GitHub Actions hosted runner" if running_on_github_actions else "local dry run; not a valid external independent vantage",
        "runner_os": os.getenv("RUNNER_OS") or platform.system(),
        "run_id": os.getenv("GITHUB_RUN_ID"),
        "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT"),
        "repository": os.getenv("GITHUB_REPOSITORY"),
        "github_actions": running_on_github_actions,
        "fetched_at": fetched_at,
        "generated_at": fetched_at,
        "verdict": "PASS" if not fail_reasons else "FAIL",
        "pass": not fail_reasons,
        "fail_reason": fail_reasons,
        "results": rows,
        "no_fake_pass": True,
    }

    for output_dir in [Path("results"), Path("docs")]:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "aw1_github_public_truth_result.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
