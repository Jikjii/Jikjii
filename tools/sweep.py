#!/usr/bin/env python3
"""
sweep.py - checks every service in profile.toml once and appends what it saw
to log/sweeps.jsonl, one JSON line per service, all stamped with the same time.

The log is append-only: nothing here rewrites or deletes a line, so a bad
sweep is just one bad line, and the history the tiles are drawn from survives it.

    GITHUB_TOKEN=... python tools/sweep.py

Standard library only. A service being down is a result, not an error: the
script exits 0 unless it cannot write the log.
"""

from __future__ import annotations

import json
import os
import sys
import time
import tomllib
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = "jikjii-control-plane/1.0 (+https://github.com/Jikjii/Jikjii)"
FAILED = {"failure", "timed_out", "startup_failure"}


def probe(url: str, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read(65536)
            code = resp.status
    except urllib.error.HTTPError as e:
        code = e.code
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        kind = "timeout" if "timed out" in str(reason).lower() or isinstance(reason, TimeoutError) else "no response"
        return {"ok": False, "code": None, "ms": None, "error": kind}
    ms = round((time.perf_counter() - start) * 1000)
    return {"ok": 200 <= code < 400, "code": code, "ms": ms}


def github(path: str):
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": UA}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"https://api.github.com{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, None


def check_repo(repo: str, workflow: str | None):
    """-> (repo visibility, latest finished run or None, last push)"""
    status, meta = github(f"/repos/{repo}")
    if status == 404:
        return "missing", None, None
    if status != 200 or not meta:
        return "unknown", None, None
    visibility = "private" if meta.get("private") else "public"
    branch = meta.get("default_branch", "main")
    base = f"/repos/{repo}/actions/workflows/{workflow}/runs" if workflow else f"/repos/{repo}/actions/runs"
    status, runs = github(f"{base}?per_page=15&branch={branch}&exclude_pull_requests=true")
    ci = None
    for run in (runs or {}).get("workflow_runs", []):
        if run.get("status") == "completed":
            ci = {"conclusion": run.get("conclusion") or "unknown", "run": run.get("run_number"),
                  "workflow": run.get("name"), "at": run.get("updated_at")}
            break
    return visibility, ci, meta.get("pushed_at")


def verdict(http, ci, visibility) -> str:
    if http and not http["ok"]:
        return "down"
    if ci and ci["conclusion"] in FAILED:
        return "failing"
    if (http and http["ok"]) or (ci and ci["conclusion"] == "success"):
        return "up"
    if visibility == "missing":
        return "private"
    if visibility == "unknown":
        return "unknown"  # GitHub did not answer; say so rather than guess
    return "idle"


def main():
    cfg = tomllib.loads((ROOT / "profile.toml").read_text())
    now = datetime.now(timezone.utc).replace(microsecond=0)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = []
    for svc in cfg.get("service", []):
        http = probe(svc["probe"]) if svc.get("probe") else None
        visibility, ci, pushed = (None, None, None)
        if svc.get("repo"):
            visibility, ci, pushed = check_repo(svc["repo"], svc.get("workflow"))
        rec = {"t": stamp, "id": svc["id"], "state": verdict(http, ci, visibility),
               "http": http, "ci": ci, "repo": visibility}
        if pushed:
            rec["pushed"] = pushed
        lines.append(rec)
        detail = []
        if http:
            detail.append(f'http {http["code"] or http.get("error")}' + (f' {http["ms"]}ms' if http.get("ms") else ""))
        if ci:
            detail.append(f'run #{ci["run"]} {ci["conclusion"]}')
        if visibility:
            detail.append(f"repo {visibility}")
        print(f'{svc["id"]:<20} {rec["state"]:<8} {", ".join(detail)}')
    log = ROOT / "log" / "sweeps.jsonl"
    log.parent.mkdir(exist_ok=True)
    with log.open("a") as f:
        for rec in lines:
            f.write(json.dumps(rec, ensure_ascii=False, separators=(", ", ": ")) + "\n")
    print(f"appended {len(lines)} line(s) to log/sweeps.jsonl at {stamp}")


if __name__ == "__main__":
    try:
        main()
    except OSError as e:
        print(f"sweep failed: {e}", file=sys.stderr)
        sys.exit(1)
