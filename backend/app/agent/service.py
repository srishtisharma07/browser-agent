"""
Task Service and in-memory execution manager for AI Browser Agent.
Coordinates asynchronous task execution, state tracking, and background worker threads.
"""

import uuid
import logging
import threading
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from app.agent.state import AgentState, CandidateProfile, TaskStatus
from app.agent.runner import AgentRunner, AgentGraphResult
from app.config import LLMConfigurationError

logger = logging.getLogger(__name__)


class TaskManager:
    """
    In-memory task manager coordinating task states and non-blocking background execution.
    Thread-safe and supports dependency injection for deterministic testing.
    """

    def __init__(self, runner_factory: Optional[Callable[[], AgentRunner]] = None):
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._runner_factory = runner_factory

    def set_runner_factory(self, runner_factory: Optional[Callable[[], AgentRunner]]) -> None:
        """Inject a custom runner factory (e.g. for mock testing)."""
        self._runner_factory = runner_factory

    def reset(self) -> None:
        """Clear all tasks (used in unit tests)."""
        with self._lock:
            self._tasks.clear()

    def get_active_task(self) -> Optional[Dict[str, Any]]:
        """
        Return the first currently active task (running or waiting for approval), if any.
        """
        with self._lock:
            for task in self._tasks.values():
                if task.get("status") in (TaskStatus.RUNNING.value, TaskStatus.WAITING_FOR_APPROVAL.value):
                    return dict(task)
            return None

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a snapshot of the task state by task_id.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            return dict(task) if task else None

    def list_tasks(self) -> List[Dict[str, Any]]:
        """
        Retrieve all tasks ordered by creation time descending.
        """
        with self._lock:
            return [dict(t) for t in reversed(list(self._tasks.values()))]

    def create_and_start_task(
        self,
        goal: str,
        max_cycles: int = 5,
        candidate_profile: Optional[CandidateProfile] = None,
    ) -> Dict[str, Any]:
        """
        Validate input, ensure no duplicate running task, initialize in-memory state,
        and spawn background execution.

        Raises:
            ValueError: If goal is empty.
            RuntimeError: If a task is already running.
        """
        if not goal or not goal.strip():
            raise ValueError("Task goal cannot be empty.")

        clean_goal = goal.strip()

        with self._lock:
            for t in self._tasks.values():
                if t.get("status") in (TaskStatus.RUNNING.value, TaskStatus.WAITING_FOR_APPROVAL.value):
                    raise RuntimeError(
                        f"A task is already running (ID: {t['task_id']}). Duplicate starts are prevented."
                    )

            task_id = f"task-{uuid.uuid4().hex[:8]}"
            now = datetime.now().isoformat()
            task_record: Dict[str, Any] = {
                "task_id": task_id,
                "goal": clean_goal,
                "status": TaskStatus.RUNNING.value,
                "candidate_profile": self._serialize_model(candidate_profile) if candidate_profile else None,
                "observations": [],
                "discovered_items": [],
                "evaluations": [],
                "application_drafts": [],
                "selected_items": [],
                "rejected_items": [],
                "current_step": "Task initialized, starting execution...",
                "pending_approval": None,
                "verification_status": "not_started",
                "cycle_count": 0,
                "errors": [],
                "final_response": None,
                "created_at": now,
                "updated_at": now,
            }
            self._tasks[task_id] = task_record

        # Spawn background execution thread
        worker = threading.Thread(
            target=self._run_task_worker,
            args=(task_id, clean_goal, max_cycles, candidate_profile),
            daemon=True,
            name=f"AgentTaskWorker-{task_id}",
        )
        worker.start()

        return dict(task_record)

    def _serialize_model(self, obj: Any) -> Any:
        """Helper to serialize Pydantic models or dicts safely."""
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        elif hasattr(obj, "dict"):
            return obj.dict()
        return obj

    def _run_task_worker(
        self,
        task_id: str,
        goal: str,
        max_cycles: int,
        candidate_profile: Optional[CandidateProfile] = None,
    ) -> None:
        """
        Background worker that executes the AgentRunner loop and safely records all state changes.
        """
        def on_state_update(state: AgentState) -> None:
            with self._lock:
                if task_id not in self._tasks:
                    return
                t = self._tasks[task_id]
                t["observations"] = [self._serialize_model(o) for o in state.observations]
                t["discovered_items"] = [self._serialize_model(i) for i in state.discovered_items]
                t["evaluations"] = [self._serialize_model(e) for e in state.evaluations]
                t["application_drafts"] = [self._serialize_model(d) for d in state.application_drafts]
                t["selected_items"] = [self._serialize_model(s) for s in state.selected_items]
                t["rejected_items"] = [self._serialize_model(r) for r in state.rejected_items]
                t["current_step"] = state.current_step
                t["pending_approval"] = self._serialize_model(state.pending_approval) if state.pending_approval else None
                t["verification_status"] = state.verification_status
                if state.errors:
                    t["errors"] = list(state.errors)
                if state.task_status:
                    status_val = state.task_status.value if hasattr(state.task_status, "value") else str(state.task_status)
                    if status_val != TaskStatus.IDLE.value:
                        t["status"] = status_val
                t["updated_at"] = datetime.now().isoformat()

        try:
            if self._runner_factory is not None:
                runner = self._runner_factory()
            else:
                runner = AgentRunner()

            result: AgentGraphResult = runner.run_task(
                user_goal=goal,
                task_id=task_id,
                max_cycles=max_cycles,
                candidate_profile=candidate_profile,
                on_state_update=on_state_update,
            )

            with self._lock:
                if task_id not in self._tasks:
                    return
                t = self._tasks[task_id]
                final_st = result.final_state
                t["observations"] = [self._serialize_model(o) for o in final_st.observations]
                t["discovered_items"] = [self._serialize_model(i) for i in final_st.discovered_items]
                t["evaluations"] = [self._serialize_model(e) for e in final_st.evaluations]
                t["application_drafts"] = [self._serialize_model(d) for d in final_st.application_drafts]
                t["selected_items"] = [self._serialize_model(s) for s in final_st.selected_items]
                t["rejected_items"] = [self._serialize_model(r) for r in final_st.rejected_items]
                t["verification_status"] = result.verification_status
                t["cycle_count"] = result.cycle_count
                t["errors"] = list(final_st.errors)
                t["current_step"] = final_st.current_step
                t["pending_approval"] = self._serialize_model(final_st.pending_approval) if final_st.pending_approval else None
                if result.decision and result.decision.action == "respond":
                    t["final_response"] = result.decision.response_text

                # Resolve terminal status
                if final_st.task_status == TaskStatus.WAITING_FOR_APPROVAL:
                    t["status"] = TaskStatus.WAITING_FOR_APPROVAL.value
                elif final_st.task_status == TaskStatus.STOPPED or result.stop_reason == "task_stopped":
                    t["status"] = TaskStatus.STOPPED.value
                elif final_st.task_status == TaskStatus.FAILED or result.stop_reason == "execution_error":
                    t["status"] = TaskStatus.FAILED.value
                elif final_st.task_status == TaskStatus.COMPLETED or result.stop_reason in (
                    "completed_response",
                    "completed",
                    "max_cycles_reached",
                ):
                    t["status"] = TaskStatus.COMPLETED.value
                else:
                    status_val = final_st.task_status.value if hasattr(final_st.task_status, "value") else str(final_st.task_status)
                    t["status"] = status_val

                t["updated_at"] = datetime.now().isoformat()

        except LLMConfigurationError as e:
            logger.error("LLM Configuration error for task %s: %s", task_id, e)
            with self._lock:
                if task_id in self._tasks:
                    t = self._tasks[task_id]
                    t["status"] = TaskStatus.FAILED.value
                    t["errors"].append(str(e))
                    t["updated_at"] = datetime.now().isoformat()

        except Exception as e:
            logger.exception("Unexpected execution error for task %s: %s", task_id, e)
            with self._lock:
                if task_id in self._tasks:
                    t = self._tasks[task_id]
                    t["status"] = TaskStatus.FAILED.value
                    t["errors"].append(f"Execution error: {type(e).__name__}: {str(e)}")
                    t["updated_at"] = datetime.now().isoformat()


# Global default task manager instance
global_task_manager = TaskManager()
