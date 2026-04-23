from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Sequence

from .logging import format_kv, get_logger


logger = get_logger("runtime.browser")


@dataclass(frozen=True)
class ChromeWindowSnapshot:
    chrome_running: bool
    window_ids: tuple[int, ...]


class BrowserWindowLease:
    """Manage one automation-scoped Chrome window lifecycle.

    The lease captures existing window ids before the task, opens one dedicated
    automation window, and on cleanup closes only windows created during this
    lease. Chrome itself stays running.
    """

    def __init__(self, *, task_name: str, initial_url: str | None = None) -> None:
        self.task_name = task_name
        self.initial_url = initial_url
        self.before_snapshot: ChromeWindowSnapshot | None = None
        self.root_window_id: int | None = None

    def __enter__(self) -> BrowserWindowLease:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cleanup()

    def acquire(self) -> int:
        self.before_snapshot = snapshot_chrome_windows()
        logger.info(
            format_kv(
                "browser.lease.acquire",
                task=self.task_name,
                before_window_count=len(self.before_snapshot.window_ids),
                chrome_running=self.before_snapshot.chrome_running,
                initial_url=self.initial_url,
            )
        )
        self.root_window_id = open_chrome_automation_window(initial_url=self.initial_url)
        logger.info(
            format_kv(
                "browser.window.opened",
                task=self.task_name,
                root_window_id=self.root_window_id,
                initial_url=self.initial_url,
            )
        )
        return self.root_window_id

    def cleanup(self) -> tuple[int, ...]:
        before_snapshot = self.before_snapshot or snapshot_chrome_windows()
        after_snapshot = snapshot_chrome_windows()
        before_ids = set(before_snapshot.window_ids)
        after_ids = set(after_snapshot.window_ids)
        created_ids = sorted(after_ids - before_ids)
        if created_ids:
            close_chrome_windows(created_ids)
        logger.info(
            format_kv(
                "browser.cleanup.done",
                task=self.task_name,
                closed_window_count=len(created_ids),
                closed_window_ids=",".join(str(item) for item in created_ids) if created_ids else None,
                before_window_count=len(before_ids),
                after_window_count=len(after_ids),
            )
        )
        return tuple(created_ids)

    def prompt_hint(self) -> str:
        if self.root_window_id is None:
            raise RuntimeError("BrowserWindowLease.prompt_hint() called before acquire().")
        location_hint = (
            "当前专用窗口已经打开了目标页面。"
            if self.initial_url
            else "当前专用窗口已经打开并置顶。"
        )
        return (
            "浏览器执行约束：\n"
            f"- 宿主机已经为你打开并置顶了一个专用 Chrome 自动化窗口，window_id={self.root_window_id}。\n"
            f"- {location_hint}\n"
            "- 你必须优先在这个窗口里完成任务，尽量不要新开额外窗口。\n"
            "- 如果需要打开更多页面，优先复用当前窗口或在同一窗口内切换标签。\n"
            "- 宿主机会在任务结束后关闭本次新增窗口；不要依赖用户手动清理。\n"
        ).strip()


def snapshot_chrome_windows() -> ChromeWindowSnapshot:
    output = _run_osascript(
        [
            'tell application "Google Chrome"',
            "if it is running then",
            "return id of every window",
            "else",
            'return ""',
            "end if",
            "end tell",
        ]
    ).strip()
    if not output:
        return ChromeWindowSnapshot(chrome_running=False, window_ids=())
    window_ids = tuple(int(part.strip()) for part in output.split(",") if part.strip())
    return ChromeWindowSnapshot(chrome_running=True, window_ids=window_ids)


def open_chrome_automation_window(*, initial_url: str | None = None) -> int:
    before_ids = set(snapshot_chrome_windows().window_ids)
    url_literal = _applescript_string(initial_url or "about:blank")
    _run_osascript(
        [
            'tell application "Google Chrome"',
            "activate",
            "make new window",
            f"set URL of active tab of front window to {url_literal}",
            "return id of front window",
            "end tell",
        ]
    )
    after_ids = set(snapshot_chrome_windows().window_ids)
    created_ids = sorted(after_ids - before_ids)
    if created_ids:
        return created_ids[-1]
    front_output = _run_osascript(
        [
            'tell application "Google Chrome"',
            "if it is running and (count of windows) > 0 then",
            "return id of front window",
            "else",
            'error "No Chrome window available after open."',
            "end if",
            "end tell",
        ]
    ).strip()
    return int(front_output)


def close_chrome_windows(window_ids: Sequence[int]) -> None:
    ids = [int(item) for item in window_ids]
    if not ids:
        return
    list_literal = "{" + ", ".join(str(item) for item in ids) + "}"
    _run_osascript(
        [
            'tell application "Google Chrome"',
            "if it is running then",
            f"repeat with targetId in {list_literal}",
            "try",
            "close (every window whose id is (contents of targetId))",
            "end try",
            "end repeat",
            "end if",
            "end tell",
        ]
    )


def _run_osascript(lines: list[str]) -> str:
    command = ["osascript"]
    for line in lines:
        command.extend(["-e", line])
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(f"osascript failed with code {result.returncode}: {stderr}")
    return result.stdout


def _applescript_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
