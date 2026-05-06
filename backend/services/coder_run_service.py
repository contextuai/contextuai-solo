"""Coder Run Service — manages running subprocesses for trusted projects.

Tracks per-project run state in an in-memory dict. Each entry holds the
``asyncio.subprocess.Process`` handle, a bounded stdout buffer (deque),
and the ``started_at`` timestamp.

Subprocesses are spawned via ``asyncio.create_subprocess_exec`` directly
from the Python sidecar — same pattern as ``services/autobuild/executor.py``.
We use ``shlex.split`` to tokenise the run command into argv so the shell
is never invoked (no command injection surface).

TODO(production): route command spawning through ``tauri-plugin-shell``
with an explicit binary allowlist instead of letting the sidecar fork
arbitrary commands. Today's "trust" gate is a single per-project boolean;
the spec calls for tool-grade allowlisting (per CLAUDE.md / spec section 6.6).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import time
from collections import deque
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

logger = logging.getLogger(__name__)


_BUFFER_LINES = 2000
_HEADLESS_LINE_CAP = 1000


def resolve_run_command(
    project: Dict[str, Any],
    template_service: Any = None,
    override: Optional[str] = None,
) -> Optional[str]:
    """Best-effort resolution of a project's run command.

    Order:
      1. ``override`` argument
      2. ``project["_resolved_run_command"]`` if pre-stamped
      3. The template manifest's ``run_command`` (when ``template_service`` is given)
      4. ``CoderTemplateService.infer_run_command`` heuristics on the folder

    Returns ``None`` if nothing matched. Pure helper so both ``start()``
    and ``run_headless()`` (and the automation output handler) can share
    the same logic.
    """
    if override:
        return override
    pre = project.get("_resolved_run_command")
    if pre:
        return pre

    template_id = project.get("template_id")
    if template_id and template_service is not None:
        try:
            manifest = template_service.get_raw_manifest(template_id)
            if manifest and manifest.get("run_command"):
                return manifest["run_command"]
        except Exception:  # pragma: no cover — defensive
            logger.exception("Failed to resolve template run_command")

    if template_service is not None:
        try:
            cmd, _port = template_service.infer_run_command(
                project.get("folder_path") or ""
            )
            if cmd:
                return cmd
        except Exception:  # pragma: no cover — defensive
            logger.exception("Failed to infer run command from folder")

    # Fallback: try inferring without an injected template service.
    try:
        from services.coder_template_service import CoderTemplateService

        cmd, _port = CoderTemplateService().infer_run_command(
            project.get("folder_path") or ""
        )
        return cmd
    except Exception:  # pragma: no cover — defensive
        return None


class _RunState:
    __slots__ = (
        "project_id",
        "process",
        "stdout_buffer",
        "started_at",
        "command",
        "_reader_task",
        "_subscribers",
    )

    def __init__(
        self,
        project_id: str,
        process: asyncio.subprocess.Process,
        command: str,
    ):
        self.project_id = project_id
        self.process = process
        self.command = command
        self.stdout_buffer: deque = deque(maxlen=_BUFFER_LINES)
        self.started_at = datetime.utcnow().isoformat()
        self._reader_task: Optional[asyncio.Task] = None
        self._subscribers: List[asyncio.Queue] = []


class CoderRunService:
    """In-memory registry of running subprocesses keyed by project_id."""

    def __init__(self):
        self._states: Dict[str, _RunState] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(
        self,
        project: Dict[str, Any],
        command_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Spawn the run command for a trusted project.

        Returns ``{status: "started", pid}`` on success or
        ``{status: "already_running"}`` if a process is already live.
        Raises ``PermissionError`` if the project is not trusted, and
        ``ValueError`` if no command can be resolved.
        """
        project_id = project["project_id"]
        if not project.get("trusted"):
            # TODO(production): enforce a per-binary allowlist here, not just
            # the "trusted" boolean — see ``tauri-plugin-shell`` migration note.
            raise PermissionError(
                "Project must be trusted before running commands."
            )

        async with self._lock:
            existing = self._states.get(project_id)
            if existing and existing.process.returncode is None:
                return {"status": "already_running", "pid": existing.process.pid}

            command = command_override or project.get("_resolved_run_command")
            if not command:
                raise ValueError("No run command provided or inferable.")

            cwd = project.get("folder_path")
            if not cwd or not os.path.isdir(cwd):
                raise ValueError(f"Project folder does not exist: {cwd!r}")

            try:
                argv = shlex.split(command, posix=(os.name != "nt"))
                if not argv:
                    raise ValueError("Empty command after shlex.split")
                process = await asyncio.create_subprocess_exec(
                    *argv,
                    cwd=cwd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
            except FileNotFoundError as exc:
                logger.warning(
                    "Coder run failed for %s: binary not found (%s)",
                    project_id,
                    exc,
                )
                raise ValueError(f"Command not found: {argv[0]}") from exc

            state = _RunState(project_id, process, command)
            state._reader_task = asyncio.create_task(self._consume_output(state))
            self._states[project_id] = state
            return {"status": "started", "pid": process.pid}

    async def stop(self, project_id: str) -> bool:
        """Terminate the process if running. Returns True if we killed it."""
        async with self._lock:
            state = self._states.get(project_id)
            if not state:
                return False
            proc = state.process
            killed = False
            if proc.returncode is None:
                try:
                    proc.terminate()
                except ProcessLookupError:
                    pass
                except Exception:
                    logger.exception("Failed to terminate process for %s", project_id)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    try:
                        proc.kill()
                        await proc.wait()
                    except Exception:
                        logger.exception("Failed to kill process for %s", project_id)
                killed = True
            # Cancel reader, drop state.
            if state._reader_task and not state._reader_task.done():
                state._reader_task.cancel()
            self._states.pop(project_id, None)
            return killed

    # ------------------------------------------------------------------
    # Headless one-shot
    # ------------------------------------------------------------------

    async def run_headless(
        self,
        project: Dict[str, Any],
        timeout_seconds: int = 60,
    ) -> Dict[str, Any]:
        """Run a trusted project to completion and capture output.

        Does NOT touch the in-memory ``_running`` registry — this is a
        one-shot transient run used by automations and other server-side
        callers. Streams stdout+stderr together (combined) and stops at
        ``timeout_seconds`` or process exit, whichever comes first.

        Returns ``{exit_code, output_lines: list[str], duration_seconds,
        timed_out: bool}``. Output is capped at 1000 lines.

        Raises ``RuntimeError`` if the project is not trusted, or
        ``ValueError`` if no run command can be resolved / the folder is
        invalid.
        """
        if not project.get("trusted"):
            raise RuntimeError(
                "Project is not trusted; cannot run headlessly."
            )

        command = resolve_run_command(project)
        if not command:
            raise ValueError(
                "No run command could be resolved for this project."
            )

        cwd = project.get("folder_path")
        if not cwd or not os.path.isdir(cwd):
            raise ValueError(f"Project folder does not exist: {cwd!r}")

        argv = shlex.split(command, posix=(os.name != "nt"))
        if not argv:
            raise ValueError("Empty command after shlex.split")

        started = time.monotonic()
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError as exc:
            raise ValueError(f"Command not found: {argv[0]}") from exc

        output_lines: List[str] = []
        timed_out = False

        async def _consume() -> None:
            assert process.stdout is not None
            while True:
                raw = await process.stdout.readline()
                if not raw:
                    break
                line = raw.decode(errors="replace").rstrip("\r\n")
                if len(output_lines) < _HEADLESS_LINE_CAP:
                    output_lines.append(line)

        try:
            await asyncio.wait_for(_consume(), timeout=timeout_seconds)
            await process.wait()
        except asyncio.TimeoutError:
            timed_out = True
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                try:
                    process.kill()
                    await process.wait()
                except Exception:  # pragma: no cover
                    logger.exception(
                        "Failed to kill headless process for %s",
                        project.get("project_id"),
                    )
            if len(output_lines) < _HEADLESS_LINE_CAP:
                output_lines.append("[truncated due to timeout]")

        duration = time.monotonic() - started
        return {
            "exit_code": process.returncode,
            "output_lines": output_lines,
            "duration_seconds": round(duration, 3),
            "timed_out": timed_out,
        }

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def is_running(self, project_id: str) -> bool:
        state = self._states.get(project_id)
        return bool(state and state.process.returncode is None)

    def get_pid(self, project_id: str) -> Optional[int]:
        state = self._states.get(project_id)
        if state and state.process.returncode is None:
            return state.process.pid
        return None

    def running_projects(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for state in self._states.values():
            if state.process.returncode is not None:
                continue
            last_line = state.stdout_buffer[-1] if state.stdout_buffer else ""
            out.append(
                {
                    "project_id": state.project_id,
                    "pid": state.process.pid,
                    "started_at": state.started_at,
                    "last_line": last_line,
                }
            )
        return out

    # ------------------------------------------------------------------
    # Output streaming
    # ------------------------------------------------------------------

    async def _consume_output(self, state: _RunState) -> None:
        """Read lines from the subprocess and fan out to subscribers."""
        proc = state.process
        if proc.stdout is None:
            return
        try:
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    break
                line = raw.decode(errors="replace").rstrip("\r\n")
                state.stdout_buffer.append(line)
                # Fan out to live subscribers (snapshot list to avoid mutation).
                for q in list(state._subscribers):
                    try:
                        q.put_nowait(line)
                    except asyncio.QueueFull:
                        # Drop the slowest subscriber — reader must not block.
                        pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Output reader crashed for %s", state.project_id
            )
        finally:
            # Signal end-of-stream to all subscribers.
            for q in list(state._subscribers):
                try:
                    q.put_nowait(None)
                except Exception:
                    pass

    async def tail_output(
        self, project_id: str
    ) -> AsyncGenerator[str, None]:
        """Async generator yielding stdout lines (existing buffer + live).

        Closes when the process exits.
        """
        state = self._states.get(project_id)
        if not state:
            return

        # Replay what we already have.
        for line in list(state.stdout_buffer):
            yield line

        # Subscribe for live lines.
        q: asyncio.Queue = asyncio.Queue(maxsize=1024)
        state._subscribers.append(q)
        try:
            while True:
                item = await q.get()
                if item is None:  # EOF sentinel
                    return
                yield item
        finally:
            try:
                state._subscribers.remove(q)
            except ValueError:
                pass


# Singleton accessor — the router and project service share one instance
# so PIDs survive across requests.
_default_run_service: Optional[CoderRunService] = None


def get_run_service() -> CoderRunService:
    global _default_run_service
    if _default_run_service is None:
        _default_run_service = CoderRunService()
    return _default_run_service
