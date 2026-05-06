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
from collections import deque
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

logger = logging.getLogger(__name__)


_BUFFER_LINES = 2000


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
