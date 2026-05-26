from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from job_search_assistant.runtime import format_kv, get_logger
from job_search_assistant.runtime.bootstrap import bootstrap_runtime, ensure_runtime_ready

from .service import TaskManagerQueryService


logger = get_logger("task_manager.web")


def run_task_manager_server(*, repo_root: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    runtime = bootstrap_runtime(repo_root, force_logging=True)
    ensure_runtime_ready(runtime)
    service = TaskManagerQueryService(
        repo_root=repo_root,
        runtime_store=runtime.runtime_store,
        node_id=runtime.settings.browser_broker.node_id,
    )
    handler = _build_handler(service=service, runtime_close=runtime.close)
    server = ThreadingHTTPServer((host, port), handler)
    logger.info(format_kv("task_manager.started", host=host, port=port))
    try:
        server.serve_forever()
    finally:
        runtime.close()
        server.server_close()


def _build_handler(*, service: TaskManagerQueryService, runtime_close):
    class TaskManagerHandler(BaseHTTPRequestHandler):
        server_version = "JobFunnelTaskManager/0.1"

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            try:
                if parsed.path == "/":
                    self._send_html(_INDEX_HTML)
                    return
                if parsed.path == "/api/overview":
                    self._send_json(service.overview())
                    return
                if parsed.path == "/api/trackers":
                    self._send_json(service.trackers())
                    return
                if parsed.path == "/api/jobs/capture":
                    self._send_json(service.jobs("capture", status=_one(query, "status"), limit=_limit(query)))
                    return
                if parsed.path == "/api/jobs/analyzer":
                    self._send_json(service.jobs("analyzer", status=_one(query, "status"), limit=_limit(query)))
                    return
                if parsed.path == "/api/jobs/output":
                    self._send_json(service.jobs("output", status=_one(query, "status"), limit=_limit(query)))
                    return
                if parsed.path == "/api/cache":
                    self._send_json(service.cache_entries(namespace=_one(query, "namespace"), limit=_limit(query, 100)))
                    return
                if parsed.path == "/api/logs":
                    self._send_json(
                        service.log_tail(
                            service=_one(query, "service") or "tracker",
                            stream=_one(query, "stream") or "out",
                            limit=_limit(query, 200),
                        )
                    )
                    return
                self._send_error(HTTPStatus.NOT_FOUND, "not_found")
            except Exception as exc:
                logger.error(format_kv("task_manager.request_failed", method="GET", path=parsed.path, error=str(exc)))
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

        def do_HEAD(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/":
                self.send_response(HTTPStatus.NOT_FOUND)
                self.end_headers()
                return
            body = _INDEX_HTML.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                payload = self._read_json()
                if parsed.path == "/api/workers/tracker/control":
                    self._send_json(
                        service.set_worker_control(
                            component_name="tracker",
                            worker_id=str(payload.get("worker_id") or "default"),
                            desired_state=str(payload["state"]),
                            node_id=str(payload["node_id"]) if payload.get("node_id") else None,
                            reason=str(payload.get("reason") or "task manager"),
                        )
                    )
                    return
                if parsed.path == "/api/cache/invalidate":
                    deleted = service.invalidate_cache_entry(
                        namespace=str(payload["namespace"]),
                        subject_key=str(payload["subject_key"]),
                        field_name=str(payload["field_name"]),
                        source_platform=str(payload.get("source_platform") or ""),
                    )
                    self._send_json({"deleted_count": deleted})
                    return
                self._send_error(HTTPStatus.NOT_FOUND, "not_found")
            except KeyError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, f"missing field: {exc}")
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception as exc:
                logger.error(format_kv("task_manager.request_failed", method="POST", path=parsed.path, error=str(exc)))
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

        def log_message(self, format: str, *args: Any) -> None:
            logger.info(format_kv("task_manager.access", message=format % args))

        def _read_json(self) -> dict[str, Any]:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0:
                return {}
            raw = self.rfile.read(content_length)
            return dict(json.loads(raw.decode("utf-8")))

        def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, html: str) -> None:
            body = html.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_error(self, status: HTTPStatus, message: str) -> None:
            self._send_json({"error": message}, status=status)

    return TaskManagerHandler


def _one(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    value = values[0].strip()
    return value or None


def _limit(query: dict[str, list[str]], default: int = 50) -> int:
    value = _one(query, "limit")
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


_INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Job Funnel Task Manager</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #17201a;
      --muted: #667066;
      --card: rgba(255,255,255,.78);
      --line: rgba(23,32,26,.12);
      --accent: #1f7a4d;
      --warn: #aa5a12;
      --bad: #b42318;
      --bg1: #f2efe5;
      --bg2: #d9ead7;
    }
    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, #f7d9ae 0, transparent 34rem),
        radial-gradient(circle at top right, #b6ddc8 0, transparent 28rem),
        linear-gradient(135deg, var(--bg1), var(--bg2));
      min-height: 100vh;
    }
    main { max-width: 1180px; margin: 0 auto; padding: 32px 20px 64px; }
    h1 { font-size: clamp(32px, 6vw, 64px); margin: 0 0 8px; letter-spacing: -.05em; }
    h2 { margin: 0 0 12px; font-size: 20px; }
    p { color: var(--muted); }
    button, select {
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 999px;
      padding: 8px 12px;
      cursor: pointer;
    }
    button.primary { background: var(--accent); color: white; border-color: var(--accent); }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 16px; margin: 20px 0; }
    .card {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 18px;
      box-shadow: 0 20px 60px rgba(23,32,26,.08);
      backdrop-filter: blur(10px);
    }
    .metric { font-size: 34px; font-weight: 800; letter-spacing: -.04em; }
    .muted { color: var(--muted); font-size: 13px; }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th, td { text-align: left; padding: 10px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
    th { color: var(--muted); font-weight: 600; }
    .pill { display: inline-block; padding: 4px 8px; border-radius: 999px; background: rgba(31,122,77,.12); color: var(--accent); font-size: 12px; }
    .pill.bad { background: rgba(180,35,24,.12); color: var(--bad); }
    .pill.warn { background: rgba(170,90,18,.12); color: var(--warn); }
    pre { white-space: pre-wrap; overflow: auto; background: #152018; color: #ddf3df; padding: 16px; border-radius: 18px; max-height: 360px; }
  </style>
</head>
<body>
  <main>
    <h1>Job Funnel Task Manager</h1>
    <p>本地运行时控制台：Tracker、Capture、Analyzer、Output、Cache 和 worker controls。</p>
    <div>
      <button class="primary" onclick="refreshAll()">刷新</button>
      <button onclick="setTrackerState('drain-current')">Tracker drain-current</button>
      <button onclick="setTrackerState('running')">Tracker running</button>
    </div>
    <section class="grid" id="overview"></section>
    <section class="card"><h2>Tracker List</h2><div id="trackers"></div></section>
    <section class="grid">
      <div class="card"><h2>Capture Jobs</h2><div id="capture"></div></div>
      <div class="card"><h2>Analyzer Jobs</h2><div id="analyzer"></div></div>
    </section>
    <section class="card"><h2>Cache</h2><div id="cache"></div></section>
    <section class="card"><h2>Tracker Log Tail</h2><pre id="logs">loading...</pre></section>
  </main>
  <script>
    async function getJson(url) {
      const res = await fetch(url);
      if (!res.ok) throw new Error(await res.text());
      return await res.json();
    }
    function esc(value) {
      return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }
    function pill(text, kind='') { return `<span class="pill ${kind}">${esc(text)}</span>`; }
    function renderJobs(rows) {
      if (!rows.length) return '<p class="muted">暂无记录</p>';
      return `<table><thead><tr><th>Status</th><th>Updated</th><th>Title / URL</th><th>Error</th></tr></thead><tbody>${
        rows.map(r => `<tr><td>${pill(r.status, r.status === 'failed' ? 'bad' : '')}</td><td>${esc(r.updated_at)}</td><td>${esc(r.job_title || r.decision || r.job_url || r.bundle_dir || r.analysis_id || '')}</td><td>${esc(r.last_error || '')}</td></tr>`).join('')
      }</tbody></table>`;
    }
    async function refreshAll() {
      const [overview, trackers, capture, analyzer, cache, logs] = await Promise.all([
        getJson('/api/overview'),
        getJson('/api/trackers'),
        getJson('/api/jobs/capture?limit=12'),
        getJson('/api/jobs/analyzer?limit=12'),
        getJson('/api/cache?limit=12'),
        getJson('/api/logs?service=tracker&stream=out&limit=80'),
      ]);
      document.getElementById('overview').innerHTML = [
        ['Launch Agents', overview.launch_agents.length],
        ['Tracker Due', trackers.due_count],
        ['Capture Backlog', (overview.job_counts.capture.queued || 0) + (overview.job_counts.capture.running || 0)],
        ['Analyzer Backlog', (overview.job_counts.analyzer.queued || 0) + (overview.job_counts.analyzer.running || 0)],
        ['Cache Entries', overview.cache_summary.total_entries],
      ].map(([k,v]) => `<div class="card"><div class="muted">${esc(k)}</div><div class="metric">${esc(v)}</div></div>`).join('');
      document.getElementById('trackers').innerHTML = `<table><thead><tr><th>ID</th><th>Enabled</th><th>Freq</th><th>Due</th><th>Last</th><th>Runs</th><th>New</th></tr></thead><tbody>${
        trackers.trackers.map(t => `<tr><td>${esc(t.id)}<br><span class="muted">${esc(t.label)}</span></td><td>${t.enabled ? pill('on') : pill('off','warn')}</td><td>${esc(t.source_frequency)}</td><td>${t.due ? pill('due','warn') : pill('not due')}</td><td>${esc(t.latest_run?.finished_at || '')}</td><td>${esc(t.summary?.run_count || 0)}</td><td>${esc(t.summary?.global_new_count || 0)}</td></tr>`).join('')
      }</tbody></table>`;
      document.getElementById('capture').innerHTML = renderJobs(capture);
      document.getElementById('analyzer').innerHTML = renderJobs(analyzer);
      document.getElementById('cache').innerHTML = `<table><thead><tr><th>Namespace</th><th>Subject</th><th>Field</th><th>TTL</th><th>Updated</th></tr></thead><tbody>${
        cache.entries.map(c => `<tr><td>${esc(c.namespace)}</td><td>${esc(c.subject_key)}</td><td>${esc(c.field_name)}</td><td>${pill(c.ttl_state, c.ttl_state === 'expired' ? 'bad' : c.ttl_state === 'stale' ? 'warn' : '')}</td><td>${esc(c.updated_at)}</td></tr>`).join('')
      }</tbody></table>`;
      document.getElementById('logs').textContent = logs.lines.join('\n');
    }
    async function setTrackerState(state) {
      await fetch('/api/workers/tracker/control', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({state, worker_id: 'default', reason: 'task manager ui'})
      });
      await refreshAll();
    }
    refreshAll();
    setInterval(refreshAll, 15000);
  </script>
</body>
</html>"""
