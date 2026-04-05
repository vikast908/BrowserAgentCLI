"""FastAPI server with WebSocket for the BrowseAgent web UI."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from browseagent.agent.executor import AgentExecutor
from browseagent.browser.extractor import extract_by_llm_data
from browseagent.config import Settings, load_settings
from browseagent.llm.schemas import ActionType, PlanSchema, RunResultSchema
from browseagent.storage.runs import RunStore

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="BrowseAgent UI")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class UISession:
    """Manages a single agent run driven from the web UI.

    Bridges the AgentExecutor to the WebSocket, streaming screenshots,
    step updates, and handling pause/resume/takeover commands.
    """

    def __init__(self, ws: WebSocket, settings: Settings) -> None:
        self.ws = ws
        self.settings = settings
        self.executor: AgentExecutor | None = None
        self._paused = asyncio.Event()
        self._paused.set()  # Not paused initially
        self._stopped = False
        self._screenshot_task: asyncio.Task | None = None
        self._run_task: asyncio.Task | None = None
        self._takeover_active = False

    async def send(self, msg_type: str, data: dict[str, Any] | None = None) -> None:
        """Send a typed JSON message over the WebSocket."""
        try:
            await self.ws.send_json({"type": msg_type, **(data or {})})
        except Exception:
            pass  # Connection may have closed

    async def run_task(self, task: str) -> None:
        """Execute an agent task with live UI streaming."""
        self._stopped = False
        self._paused.set()
        self._takeover_active = False

        # Always launch visible (not headless) for the UI
        self.executor = AgentExecutor(
            settings=self.settings,
            headless=False,
            max_steps=self.settings.max_steps,
            take_screenshots=True,
        )

        # Wire up callbacks
        self.executor.on_plan = self._on_plan
        self.executor.on_step = self._on_step
        self.executor.on_error = self._on_error

        await self.send("status", {"state": "planning", "task": task})

        start_time = time.time()
        started_at = datetime.now()

        try:
            # Phase 1: Plan
            from browseagent.agent.planner import plan_task
            plan = await plan_task(self.executor.llm, task)
            self.executor.plan = plan
            self._on_plan(plan)

            # Phase 2: Launch browser
            await self.send("status", {"state": "launching"})
            await self.executor.driver.launch()
            await self.executor.driver.navigate(plan.first_url)

            # Start screenshot streaming
            self._screenshot_task = asyncio.create_task(self._stream_screenshots())

            # Phase 3: Run the execution loop with pause/stop support
            status = await self._ui_execution_loop(task)

        except Exception as exc:
            logger.error("UI agent run failed: %s", exc)
            status = "failed"
            await self.send("error", {"message": str(exc)})
        finally:
            if self._screenshot_task:
                self._screenshot_task.cancel()
                try:
                    await self._screenshot_task
                except asyncio.CancelledError:
                    pass
            await self.executor.driver.close()

        elapsed = time.time() - start_time
        result = RunResultSchema(
            run_id=self.executor.run_id,
            task=task,
            plan=plan if "plan" in dir() else PlanSchema(goal=task, steps_estimate=0, first_url="", plan_summary=""),
            steps=self.executor.memory.all_steps,
            data=self.executor.memory.all_results,
            total_steps=self.executor.memory.step_count,
            elapsed_seconds=round(elapsed, 2),
            status=status,
            started_at=started_at,
            finished_at=datetime.now(),
        )

        # Save run
        store = RunStore(self.settings.runs_dir)
        store.save_run(result)

        await self.send("completed", {
            "status": status,
            "total_steps": result.total_steps,
            "elapsed": result.elapsed_seconds,
            "data": result.data,
            "run_id": result.run_id,
        })

    async def _ui_execution_loop(self, task: str) -> str:
        """Execution loop with pause/stop/takeover support."""
        assert self.executor is not None and self.executor.plan is not None
        plan = self.executor.plan
        memory = self.executor.memory
        driver = self.executor.driver
        llm = self.executor.llm

        from browseagent.agent.observer import observe_page
        from browseagent.browser.extractor import extract_list_items
        from browseagent.llm.prompts import build_executor_messages
        from browseagent.llm.schemas import ActionSchema, StepRecord

        for step_num in range(1, self.executor.max_steps + 1):
            # Check stop
            if self._stopped:
                return "stopped"

            # Check pause — wait until resumed
            await self._paused.wait()

            # If takeover is active, just wait until user resumes
            if self._takeover_active:
                await self.send("status", {"state": "takeover"})
                while self._takeover_active and not self._stopped:
                    await asyncio.sleep(0.5)
                if self._stopped:
                    return "stopped"
                continue

            # Observe
            observation = await observe_page(driver, take_screenshot=True)

            # Send screenshot
            if observation.screenshot_b64:
                await self.send("screenshot", {"image": observation.screenshot_b64})

            # Truncate DOM
            dom_text = observation.dom_text
            if len(dom_text) > 6000:
                dom_text = dom_text[:6000] + "\n... (truncated)"

            # Decide
            messages = build_executor_messages(
                task=task,
                plan_summary=plan.plan_summary,
                observation_dom=dom_text,
                action_history=memory.action_history,
                screenshot_b64=observation.screenshot_b64,
            )

            action = await llm.chat_structured(
                messages=messages,
                schema=ActionSchema,
                temperature=0.1,
                max_tokens=4000,
            )
            assert isinstance(action, ActionSchema)

            # Notify UI
            action_desc = f"{action.action.value}"
            if action.target:
                action_desc += f" → {action.target}"
            self._on_step(step_num, self.executor.max_steps, action_desc)

            # Done?
            if action.action == ActionType.DONE:
                if action.data:
                    normalized = await extract_by_llm_data(action.data)
                    memory.add_results(normalized)
                step_record = StepRecord(
                    step_number=step_num, observation=observation,
                    action=action, success=True,
                )
                memory.record_step(step_record)
                memory.record_action(action, success=True)

                # Final screenshot
                try:
                    final_ss = await driver.screenshot()
                    await self.send("screenshot", {"image": final_ss})
                except Exception:
                    pass

                return "completed"

            # Execute
            success = await driver.execute_action(action)

            # Handle extract
            if action.action == ActionType.EXTRACT:
                if action.data:
                    normalized = await extract_by_llm_data(action.data)
                    memory.add_results(normalized)
                elif action.target:
                    try:
                        selector = action.target.strip()
                        if selector.startswith("[") and selector.endswith("]") and "=" not in selector:
                            selector = selector[1:-1]
                        items = await extract_list_items(driver.page, selector)
                        if items:
                            memory.add_results(items)
                    except Exception as exc:
                        logger.warning("DOM extraction failed for %s: %s", action.target, exc)

            # Update memory
            error_msg = None if success else f"Failed to execute {action.action.value} on {action.target}"
            memory.record_action(action, success=success, error=error_msg)
            step_record = StepRecord(
                step_number=step_num, observation=observation,
                action=action, success=success, error=error_msg,
            )
            memory.record_step(step_record)

            if not success:
                self._on_error(step_num, error_msg or "unknown error")
                recent_failures = sum(
                    1 for h in memory.action_history[-3:]
                    if h.get("error") and h.get("target") == action.target
                )
                if recent_failures >= 2:
                    continue

            # Small delay so screenshots can be seen
            await asyncio.sleep(0.3)

        return "max_steps_reached"

    async def _stream_screenshots(self) -> None:
        """Continuously stream browser screenshots to the UI."""
        while not self._stopped:
            try:
                if self.executor and self.executor.driver._page:
                    ss = await self.executor.driver.screenshot()
                    await self.send("screenshot", {"image": ss})
            except Exception:
                pass
            await asyncio.sleep(0.8)

    def _on_plan(self, plan: PlanSchema) -> None:
        asyncio.create_task(self.send("plan", {
            "goal": plan.goal,
            "steps_estimate": plan.steps_estimate,
            "first_url": plan.first_url,
            "plan_summary": plan.plan_summary,
        }))

    def _on_step(self, step_num: int, max_steps: int, desc: str) -> None:
        asyncio.create_task(self.send("step", {
            "step": step_num,
            "max_steps": max_steps,
            "description": desc,
        }))

    def _on_error(self, step_num: int, error_msg: str) -> None:
        asyncio.create_task(self.send("step_error", {
            "step": step_num,
            "error": error_msg,
        }))

    def pause(self) -> None:
        self._paused.clear()

    def resume(self) -> None:
        self._takeover_active = False
        self._paused.set()

    def stop(self) -> None:
        self._stopped = True
        self._paused.set()  # Unblock if paused

    def takeover(self) -> None:
        """User takes manual control of the browser."""
        self._takeover_active = True
        self._paused.set()  # Don't block the loop, let it enter takeover wait


# Active sessions keyed by WebSocket
_sessions: dict[int, UISession] = {}


@app.get("/")
async def index():
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    settings = load_settings()
    session = UISession(ws, settings)
    session_id = id(ws)
    _sessions[session_id] = session

    await session.send("connected", {"message": "BrowseAgent UI connected"})

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            cmd = msg.get("command")

            if cmd == "run":
                task = msg.get("task", "")
                if task.strip():
                    # Run in background so we can still receive commands
                    session._run_task = asyncio.create_task(session.run_task(task))

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

            elif cmd == "update_settings":
                if "max_steps" in msg:
                    settings.max_steps = int(msg["max_steps"])
                if "model" in msg:
                    settings.default_model = msg["model"]
                await session.send("status", {"state": "settings_updated"})

    except WebSocketDisconnect:
        session.stop()
    finally:
        _sessions.pop(session_id, None)


def start_server(host: str = "127.0.0.1", port: int = 8899) -> None:
    """Launch the UI server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")
