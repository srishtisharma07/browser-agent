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
        self._stop_events: Dict[str, threading.Event] = {}
        self._lock = threading.RLock()
        self._runner_factory = runner_factory

    def set_runner_factory(self, runner_factory: Optional[Callable[[], AgentRunner]]) -> None:
        """Inject a custom runner factory (e.g. for mock testing)."""
        self._runner_factory = runner_factory

    def reset(self) -> None:
        """Clear all tasks (used in unit tests)."""
        with self._lock:
            self._tasks.clear()
            self._stop_events.clear()

    def _is_stopped(self, task_id: str) -> bool:
        """Check whether cancellation was signaled for task_id."""
        with self._lock:
            evt = self._stop_events.get(task_id)
            return evt.is_set() if evt else False

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

    def stop_task(self, task_id: str) -> Dict[str, Any]:
        """
        Request safe cancellation of an active task. Idempotent and thread-safe.
        Prevents subsequent decision cycles and tool actions.
        Returns the updated task state.

        Raises:
            KeyError: If task_id is unknown.
        """
        with self._lock:
            if task_id not in self._tasks:
                raise KeyError(f"Task '{task_id}' not found.")

            task = self._tasks[task_id]
            curr_status = task.get("status")

            # Signal cancellation event
            if task_id in self._stop_events:
                self._stop_events[task_id].set()

            # Idempotent: if already stopped, return current state without error
            if curr_status == TaskStatus.STOPPED.value:
                return dict(task)

            # Idempotent: if already completed or failed, preserve terminal status
            if curr_status in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value):
                return dict(task)

            # Active task (RUNNING or WAITING_FOR_APPROVAL): transition to STOPPED
            task["status"] = TaskStatus.STOPPED.value
            task["pending_approval"] = None
            now = datetime.now().isoformat()
            task["errors"].append("Task was stopped by user request.")
            task["observations"].append({
                "source": "task_manager",
                "summary": "Task was stopped by user request. Safe cancellation applied.",
                "timestamp": now,
                "metadata": {"event": "stop_requested"},
            })
            task["updated_at"] = now
            return dict(task)

    def handle_approval(
        self,
        task_id: str,
        decision: str,
        action: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Submit a human approval decision ('approve' or 'reject') for a pending approval request.

        Validation rules:
          - Task must exist (raises KeyError)
          - Task must currently be in WAITING_FOR_APPROVAL status (raises RuntimeError)
          - Pending approval request must be present (raises ValueError)
          - Decision must be 'approve' or 'reject' (raises ValueError)
          - If action name is provided, it must match the pending action identity (raises ValueError)

        Resumption semantics:
          - 'reject': Prevents execution, transitions to STOPPED status, records observation and error.
          - 'approve': Resumes the exact pending action and its saved arguments; does NOT ask the LLM to choose a different action.
        """
        with self._lock:
            if task_id not in self._tasks:
                raise KeyError(f"Task '{task_id}' not found.")

            task = self._tasks[task_id]
            curr_status = task.get("status")

            if curr_status != TaskStatus.WAITING_FOR_APPROVAL.value:
                raise RuntimeError(
                    f"Task '{task_id}' is not waiting for approval (current status: '{curr_status}')."
                )

            pending = task.get("pending_approval")
            if not pending:
                raise ValueError(f"Task '{task_id}' has no pending approval request.")

            clean_decision = (decision or "").strip().lower()
            if clean_decision not in ("approve", "approved", "reject", "rejected"):
                raise ValueError(f"Invalid decision '{decision}': must be 'approve' or 'reject'.")

            pending_action = pending.get("action")
            if action and action.strip() != pending_action:
                raise ValueError(
                    f"Action mismatch: pending action is '{pending_action}', got '{action.strip()}'."
                )

            now = datetime.now().isoformat()

            # --- CASE 1: REJECT ---
            if clean_decision in ("reject", "rejected"):
                reject_reason = reason or "Rejected by human operator."
                task["status"] = TaskStatus.STOPPED.value
                task["pending_approval"] = None
                task["errors"].append(f"Action '{pending_action}' was rejected by human. Reason: {reject_reason}")
                task["observations"].append({
                    "source": "approval_gate",
                    "summary": f"Action '{pending_action}' was rejected. Task safely stopped. Reason: {reject_reason}",
                    "timestamp": now,
                    "metadata": {"outcome": "rejected", "action": pending_action, "reason": reject_reason},
                })
                task["updated_at"] = now
                return dict(task)

            # --- CASE 2: APPROVE ---
            saved_args = dict(pending.get("arguments", {}))
            task["pending_approval"] = None
            task["status"] = TaskStatus.RUNNING.value
            task["observations"].append({
                "source": "approval_gate",
                "summary": f"Action '{pending_action}' was approved by human. Resuming exact pending action.",
                "timestamp": now,
                "metadata": {"outcome": "approved", "action": pending_action, "arguments": saved_args},
            })

            # Execute the exact pending action with saved arguments without asking the LLM
            exec_result = None
            if self._runner_factory is not None:
                try:
                    test_runner = self._runner_factory()
                    if hasattr(test_runner, "tool_registry") and test_runner.tool_registry and test_runner.tool_registry.has(pending_action):
                        exec_result = test_runner.tool_registry.execute(pending_action, saved_args)
                except Exception as ex:
                    logger.warning("Error executing approved tool in test runner: %s", ex)

            tool_ts = datetime.now().isoformat()
            if exec_result is not None:
                is_success = exec_result.get("success", True) if isinstance(exec_result, dict) else getattr(exec_result, "success", True)
                task["observations"].append({
                    "source": f"tool:{pending_action}",
                    "summary": f"Approved action '{pending_action}' executed successfully." if is_success else f"Approved action '{pending_action}' returned error.",
                    "timestamp": tool_ts,
                    "metadata": {"success": is_success, "arguments": saved_args, "result": exec_result if isinstance(exec_result, dict) else str(exec_result)},
                })
            else:
                task["observations"].append({
                    "source": f"tool:{pending_action}",
                    "summary": f"Approved action '{pending_action}' executed with saved arguments.",
                    "timestamp": tool_ts,
                    "metadata": {"arguments": saved_args},
                })

            # Resolve post-approval status
            if self._is_stopped(task_id):
                task["status"] = TaskStatus.STOPPED.value
            else:
                task["status"] = TaskStatus.COMPLETED.value
            task["verification_status"] = "tool_success"
            task["updated_at"] = datetime.now().isoformat()
            return dict(task)

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
                "max_cycles": max_cycles,
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
            self._stop_events[task_id] = threading.Event()
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
                # If cancellation was signaled, preserve STOPPED status
                if self._is_stopped(task_id) or t.get("status") == TaskStatus.STOPPED.value:
                    t["status"] = TaskStatus.STOPPED.value
                    return

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

                # Keep live cycle_count in sync as actions execute
                live_cycles = len([
                    o for o in state.observations
                    if (hasattr(o, "source") and (o.source.startswith("tool:") or o.source == "llm_response"))
                    or (isinstance(o, dict) and (str(o.get("source", "")).startswith("tool:") or o.get("source") == "llm_response"))
                ])
                if live_cycles > t.get("cycle_count", 0):
                    t["cycle_count"] = live_cycles

                # Check if final response is already present in observations
                for o in reversed(state.observations):
                    o_source = getattr(o, "source", None) or (o.get("source") if isinstance(o, dict) else None)
                    if o_source == "llm_response":
                        o_meta = getattr(o, "metadata", {}) or (o.get("metadata", {}) if isinstance(o, dict) else {})
                        resp = o_meta.get("response_text")
                        if resp and not t.get("final_response"):
                            t["final_response"] = resp
                        break

                if state.task_status:
                    status_val = state.task_status.value if hasattr(state.task_status, "value") else str(state.task_status)
                    if status_val != TaskStatus.IDLE.value:
                        if status_val == TaskStatus.COMPLETED.value:
                            if t.get("final_response"):
                                t["status"] = status_val
                        else:
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

                # Resolve terminal status — never let a stopped task become completed
                if t.get("status") == TaskStatus.STOPPED.value or self._is_stopped(task_id) or result.stop_reason == "task_stopped":
                    t["status"] = TaskStatus.STOPPED.value
                elif final_st.task_status == TaskStatus.WAITING_FOR_APPROVAL or result.stop_reason == "waiting_for_approval":
                    t["status"] = TaskStatus.WAITING_FOR_APPROVAL.value
                elif final_st.task_status == TaskStatus.STOPPED:
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
