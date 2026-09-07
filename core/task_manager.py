"""
ALEX — Task Manager
Background task execution, scheduling, and lifecycle management.
Supports one-shot tasks, periodic tasks, and condition monitors.
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from utils.logger import log


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskRecord:
    """Record of a background task."""
    id: str
    name: str
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    progress: str = ""          # Human-readable progress message
    is_recurring: bool = False
    interval_seconds: float | None = None
    next_run: float | None = None

    @property
    def duration(self) -> float | None:
        if self.started_at and self.finished_at:
            return round(self.finished_at - self.started_at, 2)
        return None

    def to_dict(self) -> dict:
        return {
            "id": self.id[:8],  # Short ID for display
            "name": self.name,
            "status": self.status.value,
            "result": str(self.result)[:200] if self.result else None,
            "error": self.error,
            "created_at": self.created_at,
            "duration": self.duration,
            "progress": self.progress,
            "is_recurring": self.is_recurring,
            "next_run": self.next_run,
        }


class TaskManager:
    """
    Manages background tasks for Alex.

    Features:
    - Run tasks in background threads (non-blocking)
    - Schedule recurring tasks with intervals
    - Monitor conditions and alert on trigger
    - Cancel running/pending tasks
    - Query task status
    """

    def __init__(self, alert_callback: Callable | None = None):
        """
        Args:
            alert_callback: Called when a monitor triggers. Signature: (message: str)
        """
        self._tasks: dict[str, TaskRecord] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._alert_callback = alert_callback
        self._task_listeners: list[Callable] = []

        log.info("⚙️ TaskManager initialized")

    def add_task_listener(self, callback: Callable):
        """Register callback for task state changes."""
        self._task_listeners.append(callback)

    def _notify_listeners(self, event: str, task: TaskRecord):
        for cb in self._task_listeners:
            try:
                cb(event, task.to_dict())
            except Exception as e:
                log.warning(f"Task listener error: {e}")

    # ─── SUBMIT TASKS ────────────────────────────────────────────────────────

    def submit(
        self,
        fn: Callable,
        name: str,
        args: tuple = (),
        kwargs: dict | None = None,
    ) -> str:
        """
        Submit a one-shot background task.

        Args:
            fn: Function to run
            name: Human-readable task name
            args: Positional arguments for fn
            kwargs: Keyword arguments for fn

        Returns:
            Task ID
        """
        task_id = str(uuid.uuid4())
        cancel_event = threading.Event()

        record = TaskRecord(id=task_id, name=name)

        with self._lock:
            self._tasks[task_id] = record
            self._cancel_events[task_id] = cancel_event

        thread = threading.Thread(
            target=self._run_task,
            args=(task_id, fn, args, kwargs or {}),
            daemon=True,
            name=f"alex-task-{name[:20]}",
        )

        with self._lock:
            self._threads[task_id] = thread

        thread.start()
        log.info(f"🚀 Task submitted: '{name}' [{task_id[:8]}]")
        self._notify_listeners("submitted", record)
        return task_id

    def schedule(
        self,
        fn: Callable,
        name: str,
        interval_seconds: float,
        args: tuple = (),
        kwargs: dict | None = None,
        max_runs: int | None = None,
    ) -> str:
        """
        Schedule a recurring task at a fixed interval.

        Args:
            fn: Function to run repeatedly
            name: Task name
            interval_seconds: Seconds between each run
            max_runs: Maximum number of runs (None = infinite)
        """
        task_id = str(uuid.uuid4())
        cancel_event = threading.Event()

        record = TaskRecord(
            id=task_id,
            name=name,
            is_recurring=True,
            interval_seconds=interval_seconds,
            next_run=time.time() + interval_seconds,
        )

        with self._lock:
            self._tasks[task_id] = record
            self._cancel_events[task_id] = cancel_event

        thread = threading.Thread(
            target=self._run_recurring,
            args=(task_id, fn, args, kwargs or {}, interval_seconds, max_runs, cancel_event),
            daemon=True,
            name=f"alex-sched-{name[:20]}",
        )

        with self._lock:
            self._threads[task_id] = thread

        thread.start()
        log.info(f"📅 Recurring task scheduled: '{name}' every {interval_seconds}s [{task_id[:8]}]")
        self._notify_listeners("scheduled", record)
        return task_id

    def watch_condition(
        self,
        condition_fn: Callable[[], bool],
        alert_message: str,
        name: str,
        check_interval: float = 60.0,
        max_alerts: int | None = None,
    ) -> str:
        """
        Monitor a condition and alert when it becomes True.

        Args:
            condition_fn: Returns True when alert should trigger
            alert_message: Message to display/speak when triggered
            name: Monitor name
            check_interval: How often to check (seconds)
            max_alerts: Maximum number of times to alert (None = infinite)
        """
        def _monitor():
            alerts = 0
            while True:
                try:
                    if condition_fn():
                        alerts += 1
                        log.warning(f"🚨 Condition triggered: {name} — {alert_message}")
                        if self._alert_callback:
                            self._alert_callback(alert_message)
                        if max_alerts and alerts >= max_alerts:
                            break
                except Exception as e:
                    log.error(f"Monitor '{name}' error: {e}")

        return self.schedule(_monitor, f"Monitor: {name}", check_interval)

    # ─── CANCEL & QUERY ──────────────────────────────────────────────────────

    def cancel(self, task_id: str) -> bool:
        """Cancel a running or scheduled task."""
        with self._lock:
            if task_id not in self._tasks:
                # Try partial match
                matches = [tid for tid in self._tasks if tid.startswith(task_id)]
                if not matches:
                    return False
                task_id = matches[0]

            self._cancel_events.get(task_id, threading.Event()).set()
            self._tasks[task_id].status = TaskStatus.CANCELLED

        log.info(f"🛑 Task cancelled: {task_id[:8]}")
        self._notify_listeners("cancelled", self._tasks[task_id])
        return True

    def cancel_all(self):
        """Cancel all running tasks."""
        with self._lock:
            for cancel_event in self._cancel_events.values():
                cancel_event.set()
            for record in self._tasks.values():
                if record.status in (TaskStatus.RUNNING, TaskStatus.PENDING):
                    record.status = TaskStatus.CANCELLED
        log.info("🛑 All tasks cancelled")

    def status(self, task_id: str) -> TaskRecord | None:
        """Get status of a task by ID."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                # Try short ID match
                for tid, t in self._tasks.items():
                    if tid.startswith(task_id):
                        return t
        return task

    def list_tasks(self, include_done: bool = False) -> list[TaskRecord]:
        """List all tasks."""
        with self._lock:
            tasks = list(self._tasks.values())

        if not include_done:
            tasks = [t for t in tasks if t.status not in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED)]

        return sorted(tasks, key=lambda t: t.created_at, reverse=True)

    def get_summary(self) -> str:
        """Get a human-readable summary of running tasks."""
        running = self.list_tasks(include_done=False)
        if not running:
            return "No background tasks running."

        lines = [f"{len(running)} background task(s) running:"]
        for t in running:
            status_emoji = {"running": "🔄", "pending": "⏳", "done": "✅", "failed": "❌", "cancelled": "🚫"}.get(t.status.value, "?")
            lines.append(f"  {status_emoji} [{t.id[:8]}] {t.name}")
            if t.progress:
                lines.append(f"      {t.progress}")
        return "\n".join(lines)

    # ─── INTERNAL RUNNERS ────────────────────────────────────────────────────

    def _run_task(self, task_id: str, fn: Callable, args: tuple, kwargs: dict):
        """Internal: Run a one-shot task and update its record."""
        with self._lock:
            record = self._tasks.get(task_id)
            if not record:
                return
            record.status = TaskStatus.RUNNING
            record.started_at = time.time()

        self._notify_listeners("started", record)

        try:
            result = fn(*args, **kwargs)
            with self._lock:
                record.status = TaskStatus.DONE
                record.result = result
                record.finished_at = time.time()
            log.info(f"✅ Task done: '{record.name}' [{task_id[:8]}]")
            self._notify_listeners("done", record)
        except Exception as e:
            with self._lock:
                record.status = TaskStatus.FAILED
                record.error = str(e)
                record.finished_at = time.time()
            log.error(f"❌ Task failed: '{record.name}' [{task_id[:8]}]: {e}")
            self._notify_listeners("failed", record)

    def _run_recurring(
        self,
        task_id: str,
        fn: Callable,
        args: tuple,
        kwargs: dict,
        interval: float,
        max_runs: int | None,
        cancel_event: threading.Event,
    ):
        """Internal: Run a task repeatedly at interval."""
        runs = 0

        with self._lock:
            record = self._tasks.get(task_id)
            if record:
                record.status = TaskStatus.RUNNING

        while not cancel_event.is_set():
            # Wait for interval (interruptible)
            cancelled = cancel_event.wait(timeout=interval)
            if cancelled:
                break

            with self._lock:
                record = self._tasks.get(task_id)
                if not record or record.status == TaskStatus.CANCELLED:
                    break

            try:
                result = fn(*args, **kwargs)
                runs += 1
                with self._lock:
                    if record:
                        record.result = result
                        record.next_run = time.time() + interval
                        record.progress = f"Ran {runs} time(s), last: {time.strftime('%H:%M:%S')}"

            except Exception as e:
                log.error(f"Recurring task '{record.name if record else task_id[:8]}' error: {e}")

            if max_runs and runs >= max_runs:
                break

        with self._lock:
            record = self._tasks.get(task_id)
            if record and record.status != TaskStatus.CANCELLED:
                record.status = TaskStatus.DONE
                record.finished_at = time.time()

        log.info(f"📅 Recurring task ended: [{task_id[:8]}] after {runs} runs")
