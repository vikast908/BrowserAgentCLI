"""FastAPI server with WebSocket for the BrowseAgent web UI."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from browseagent.config import load_settings
from browseagent.engine import EngineResult, run_browser_use

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="BrowseAgent UI")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class UISession:
    """Manages a single agent run driven from the web UI."""

    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.settings = load_settings()
        self._paused = asyncio.Event()
        self._paused.set()
        self._stopped = False
        self._takeover = False
        self._current_page = None  # Playwright page for manual control
        self._run_task: asyncio.Task | None = None
        self._screenshot_task: asyncio.Task | None = None

    async def send(self, msg_type: str, data: dict[str, Any] | None = None) -> None:
        try:
            await self.ws.send_json({"type": msg_type, **(data or {})})
        except Exception:
            pass

    # ── Run task via engine ────────────────────────────
    async def run(self, task: str, max_steps: int = 40) -> None:
        self._stopped = False
        self._paused.set()
        self._takeover = False

        def on_step(step, max_s, desc):
            asyncio.create_task(self.send("step", {
                "step": step, "max_steps": max_s, "description": desc,
            }))

        def on_screenshot(b64):
            asyncio.create_task(self.send("screenshot", {"image": b64}))

        def on_error(step, msg):
            asyncio.create_task(self.send("step_error", {"step": step, "error": msg}))

        def on_status(state, data):
            asyncio.create_task(self.send("status", {"state": state, **data}))

        def store_page(page):
            self._current_page = page

        # Start background screenshot streaming for manual control
        self._screenshot_task = asyncio.create_task(self._stream_screenshots())

        try:
            result = await run_browser_use(
                task=task,
                model=self.settings.default_model,
                provider=self.settings.default_provider,
                lm_studio_url=self.settings.lm_studio_url,
                max_steps=max_steps,
                max_actions_per_step=10,
                headless=False,
                on_step=on_step,
                on_screenshot=on_screenshot,
                on_error=on_error,
                on_status=on_status,
                pause_event=self._paused,
                stop_flag=lambda: self._stopped,
                takeover_flag=lambda: self._takeover,
                get_page_callback=store_page,
            )
        except Exception as exc:
            logger.error("Run failed: %s", exc)
            result = EngineResult()
            result.status = "failed"
            result.task = task

        if self._screenshot_task:
            self._screenshot_task.cancel()
            try:
                await self._screenshot_task
            except asyncio.CancelledError:
                pass

        # Save to history
        from browseagent.storage.runs import RunStore
        from browseagent.llm.schemas import PlanSchema, RunResultSchema

        run_result = RunResultSchema(
            run_id=result.run_id,
            task=result.task,
            plan=PlanSchema(goal=result.task, steps_estimate=0, first_url="", plan_summary=""),
            data=result.data,
            total_steps=result.total_steps,
            elapsed_seconds=result.elapsed_seconds,
            status=result.status,
            started_at=result.started_at,
            finished_at=result.finished_at,
        )
        try:
            store = RunStore(self.settings.runs_dir)
            store.save_run(run_result)
        except Exception:
            pass

        await self.send("completed", {
            "status": result.status,
            "total_steps": result.total_steps,
            "elapsed": result.elapsed_seconds,
            "data": result.data,
            "run_id": result.run_id,
        })

    # ── Screenshot streaming ──────────────────────────
    async def _stream_screenshots(self) -> None:
        while not self._stopped:
            if self._current_page and self._takeover:
                try:
                    session_id = await self._current_page._ensure_session()
                    ss = await self._current_page._client.send(
                        "Page.captureScreenshot",
                        {"format": "png"},
                        session_id=session_id,
                    )
                    if ss and "data" in ss:
                        await self.send("screenshot", {"image": ss["data"]})
                except Exception:
                    pass
            await asyncio.sleep(0.6)

    # ── Manual control ────────────────────────────────
    async def mouse_click(self, x: int, y: int) -> None:
        if self._current_page:
            try:
                session_id = await self._current_page._ensure_session()
                # Use CDP Input.dispatchMouseEvent for precise clicks
                await self._current_page._client.send(
                    "Input.dispatchMouseEvent",
                    {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1},
                    session_id=session_id,
                )
                await self._current_page._client.send(
                    "Input.dispatchMouseEvent",
                    {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1},
                    session_id=session_id,
                )
                await asyncio.sleep(0.3)
                ss = await self._current_page._client.send(
                    "Page.captureScreenshot", {"format": "png"}, session_id=session_id,
                )
                if ss and "data" in ss:
                    await self.send("screenshot", {"image": ss["data"]})
            except Exception as exc:
                logger.warning("Click failed: %s", exc)

    async def mouse_dblclick(self, x: int, y: int) -> None:
        if self._current_page:
            try:
                session_id = await self._current_page._ensure_session()
                await self._current_page._client.send(
                    "Input.dispatchMouseEvent",
                    {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 2},
                    session_id=session_id,
                )
                await self._current_page._client.send(
                    "Input.dispatchMouseEvent",
                    {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 2},
                    session_id=session_id,
                )
                await asyncio.sleep(0.3)
                ss = await self._current_page._client.send(
                    "Page.captureScreenshot", {"format": "png"}, session_id=session_id,
                )
                if ss and "data" in ss:
                    await self.send("screenshot", {"image": ss["data"]})
            except Exception as exc:
                logger.warning("Double-click failed: %s", exc)

    async def key_press(self, key: str) -> None:
        if self._current_page and key:
            try:
                session_id = await self._current_page._ensure_session()
                await self._current_page._client.send(
                    "Input.dispatchKeyEvent",
                    {"type": "keyDown", "key": key},
                    session_id=session_id,
                )
                await self._current_page._client.send(
                    "Input.dispatchKeyEvent",
                    {"type": "keyUp", "key": key},
                    session_id=session_id,
                )
                await asyncio.sleep(0.15)
                ss = await self._current_page._client.send(
                    "Page.captureScreenshot", {"format": "png"}, session_id=session_id,
                )
                if ss and "data" in ss:
                    await self.send("screenshot", {"image": ss["data"]})
            except Exception as exc:
                logger.warning("Key press failed: %s", exc)

    async def type_text(self, text: str) -> None:
        if self._current_page and text:
            try:
                session_id = await self._current_page._ensure_session()
                for char in text:
                    await self._current_page._client.send(
                        "Input.dispatchKeyEvent",
                        {"type": "char", "text": char},
                        session_id=session_id,
                    )
                await asyncio.sleep(0.1)
                ss = await self._current_page._client.send(
                    "Page.captureScreenshot", {"format": "png"}, session_id=session_id,
                )
                if ss and "data" in ss:
                    await self.send("screenshot", {"image": ss["data"]})
            except Exception as exc:
                logger.warning("Type text failed: %s", exc)

    def pause(self) -> None:
        self._paused.clear()

    def resume(self) -> None:
        self._takeover = False
        self._paused.set()

    def stop(self) -> None:
        self._stopped = True
        self._paused.set()

    def takeover(self) -> None:
        self._takeover = True
        self._paused.set()


# ── Routes ────────────────────────────────────────────
_sessions: dict[int, UISession] = {}


@app.get("/")
async def index():
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    session = UISession(ws)
    sid = id(ws)
    _sessions[sid] = session

    await session.send("connected", {"message": "BrowseAgent UI connected"})

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            cmd = msg.get("command")

            if cmd == "run":
                task = msg.get("task", "").strip()
                if task:
                    session._run_task = asyncio.create_task(
                        session.run(task, max_steps=session.settings.max_steps)
                    )
            elif cmd == "pause":
                session.pause()
                await session.send("status", {"state": "paused"})
            elif cmd == "resume":
                session.resume()
                await session.send("status", {"state": "running"})
            elif cmd == "stop":
                session.stop()
                await session.send("status", {"state": "stopped"})
            elif cmd == "takeover":
                session.takeover()
                await session.send("status", {"state": "takeover"})
            elif cmd == "mouse_click":
                await session.mouse_click(msg.get("x", 0), msg.get("y", 0))
            elif cmd == "mouse_dblclick":
                await session.mouse_dblclick(msg.get("x", 0), msg.get("y", 0))
            elif cmd == "key_press":
                await session.key_press(msg.get("key", ""))
            elif cmd == "type_text":
                await session.type_text(msg.get("text", ""))
            elif cmd == "update_settings":
                if "max_steps" in msg:
                    session.settings.max_steps = int(msg["max_steps"])
                if "model" in msg:
                    session.settings.default_model = msg["model"]
                await session.send("status", {"state": "settings_updated"})

    except WebSocketDisconnect:
        session.stop()
    finally:
        _sessions.pop(sid, None)


def start_server(host: str = "127.0.0.1", port: int = 8899) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")
