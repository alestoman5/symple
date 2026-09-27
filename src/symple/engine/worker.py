"""Runs the evaluator in a child process so long computations can be interrupted.

Python threads cannot be killed, so the only reliable way to stop a runaway
``int`` or infinite loop is to terminate the process that runs it. Interrupting
therefore also clears the session (like restarting a kernel).
"""
from __future__ import annotations

import multiprocessing as mp
import sys
import threading
import time
from dataclasses import dataclass, field

from .printing import Output


@dataclass
class RunResult:
    outputs: list[Output] = field(default_factory=list)
    names: list[str] = field(default_factory=list)   # names defined in the session afterwards
    elapsed: float = 0.0
    interrupted: bool = False
    crashed: bool = False


def _serve(conn) -> None:  # runs in the child process
    sys.setrecursionlimit(6000)
    from .evaluator import Evaluator
    ev = Evaluator()
    conn.send(("ready", None))
    while True:
        try:
            op, payload = conn.recv()
        except (EOFError, OSError):
            return
        if op == "run":
            t0 = time.perf_counter()
            outputs = ev.run(payload)
            conn.send(("result", RunResult(outputs, ev.defined_names(), time.perf_counter() - t0)))
        elif op == "reset":
            ev.reset()
            conn.send(("result", RunResult()))
        elif op == "quit":
            return


class EngineClient:
    """Owns the worker process. ``run`` blocks; call it from a background thread in a GUI."""

    def __init__(self):
        self._ctx = mp.get_context("spawn")
        self._proc = None
        self._conn = None
        self._lock = threading.Lock()
        self._interrupted = False

    def start(self) -> None:
        parent, child = self._ctx.Pipe()
        proc = self._ctx.Process(target=_serve, args=(child,), daemon=True, name="symple-engine")
        proc.start()
        child.close()
        self._proc, self._conn = proc, parent
        self._interrupted = False

    def _ensure(self) -> None:
        if self._proc is None or not self._proc.is_alive():
            self.start()

    def _request(self, op, payload=None) -> RunResult:
        with self._lock:
            self._ensure()
            conn, proc = self._conn, self._proc
            try:
                conn.send((op, payload))
                while True:
                    if conn.poll(0.05):
                        kind, value = conn.recv()
                        if kind == "result":
                            return value
                        continue  # "ready"
                    if not proc.is_alive():
                        interrupted = self._interrupted
                        self._proc = None
                        return RunResult(interrupted=interrupted, crashed=not interrupted)
            except (EOFError, OSError, BrokenPipeError):
                interrupted = self._interrupted
                self._proc = None
                return RunResult(interrupted=interrupted, crashed=not interrupted)

    def run(self, code: str) -> RunResult:
        result = self._request("run", code)
        if result.interrupted:
            result.outputs = [Output("warning", text="Computation interrupted; the session was restarted.")]
        elif result.crashed:
            result.outputs = [Output("error", text="Error, the computation engine stopped unexpectedly "
                                                   "(possibly too deep recursion); the session was restarted.")]
        return result

    def reset(self) -> None:
        self._request("reset")

    def interrupt(self) -> None:
        """Kill the running computation (safe to call from any thread)."""
        proc = self._proc
        if proc is not None and proc.is_alive():
            self._interrupted = True
            proc.kill()

    def shutdown(self) -> None:
        proc, conn = self._proc, self._conn
        self._proc = None
        if proc is not None and proc.is_alive():
            try:
                conn.send(("quit", None))
                proc.join(0.5)
            except (OSError, BrokenPipeError):
                pass
            if proc.is_alive():
                proc.kill()
