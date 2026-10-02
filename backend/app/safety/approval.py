"""
Human-in-the-Loop Approval Safety Gate for AI Browser Agent.

Provides:
  - A policy of which actions require human approval before execution.
  - ApprovalGate: the mechanism to pause, approve, or reject pending actions.
  - Integration helpers for the DecisionEngine to check before executing.

The approval check happens BEFORE any consequential browser action executes.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from app.agent.state import AgentState, ApprovalRequest, TaskStatus, Observation


# ---------------------------------------------------------------------------
# Consequential action policy
# ---------------------------------------------------------------------------

CONSEQUENTIAL_ACTIONS: frozenset = frozenset({
    "submit_application",
    "send_email",
    "purchase",
    "delete",
    "confirm",
})

# Safe browser observation/navigation tools that never require approval.
SAFE_BROWSER_TOOLS: frozenset = frozenset({
    "open_url",
    "get_page_text",
    "click",
    "fill",
    "press",
    "scroll",
    "go_back",
    "get_links",
    "screenshot",
})


def is_consequential(action_name: str) -> bool:
    """
    Returns True if the named action requires human approval before execution.

    Args:
        action_name: Name of the tool or action to check.

    Returns:
        True if approval is required, False if the action is safe to auto-execute.
    """
    return action_name in CONSEQUENTIAL_ACTIONS


# ---------------------------------------------------------------------------
# Approval outcome
# ---------------------------------------------------------------------------

class ApprovalOutcome(str, Enum):
    """Result of an approval decision."""
    PENDING   = "pending"
    APPROVED  = "approved"
    REJECTED  = "rejected"


# ---------------------------------------------------------------------------
# Approval gate
# ---------------------------------------------------------------------------

class ApprovalGate:
    """
    Human-in-the-Loop approval safety gate.

    Sits between the DecisionEngine and ToolRegistry.
    For consequential actions: pauses execution and updates AgentState.
    For safe actions: passes through immediately.

    The gate NEVER executes browser actions itself.
    All execution still flows through ToolRegistry → BrowserManager → Playwright.
    """

    def check(
        self,
        action_name: str,
        description: str,
        state: AgentState,
        target: Optional[str] = None,
    ) -> AgentState:
        """
        Check whether an action requires approval before execution.

        If the action is consequential:
          - Sets task_status to WAITING_FOR_APPROVAL.
          - Populates pending_approval with an ApprovalRequest.
          - Adds an observation recording the pause.
          - Returns the updated state WITHOUT executing the action.

        If the action is safe:
          - Returns state unchanged.

        Args:
            action_name: Name of the tool/action the LLM requested.
            description: Human-readable description of what is about to happen.
            state: Current AgentState (will be deep-copied internally).
            target: Optional target element/URL/address.

        Returns:
            Updated AgentState. Caller must check task_status before executing.
        """
        if not is_consequential(action_name):
            return state

        # Deep copy so we do not mutate the original
        new_state = state.model_copy(deep=True)

        approval_request = ApprovalRequest(
            action=action_name,
            description=description,
            target=target,
            required=True,
        )

        new_state.task_status = TaskStatus.WAITING_FOR_APPROVAL
        new_state.pending_approval = approval_request
        new_state.observations.append(Observation(
            source="approval_gate",
            summary=(
                f"Action '{action_name}' requires human approval before execution. "
                f"Description: {description}"
            ),
            timestamp=datetime.now().isoformat(),
            metadata={"action": action_name, "target": target},
        ))

        return new_state

    def approve(self, state: AgentState) -> AgentState:
        """
        Approve the currently pending action.

        Validates that a pending approval exists, then clears it and
        restores the task to RUNNING status so execution can proceed.

        Args:
            state: AgentState containing a pending_approval.

        Returns:
            Updated AgentState with pending_approval cleared and status RUNNING.

        Raises:
            ValueError: If no pending approval exists.
        """
        if state.pending_approval is None:
            raise ValueError("Cannot approve: no pending approval request found in AgentState.")

        new_state = state.model_copy(deep=True)
        approved_action = new_state.pending_approval.action
        new_state.pending_approval = None
        new_state.task_status = TaskStatus.RUNNING
        new_state.observations.append(Observation(
            source="approval_gate",
            summary=f"Action '{approved_action}' was approved by human. Execution may proceed.",
            timestamp=datetime.now().isoformat(),
            metadata={"outcome": ApprovalOutcome.APPROVED, "action": approved_action},
        ))

        return new_state

    def reject(self, state: AgentState, reason: str = "Rejected by human.") -> AgentState:
        """
        Reject the currently pending action.

        Validates that a pending approval exists, then clears it and
        sets the task to STOPPED status so the agent does not continue.

        Args:
            state: AgentState containing a pending_approval.
            reason: Human-readable rejection reason.

        Returns:
            Updated AgentState with pending_approval cleared and status STOPPED.

        Raises:
            ValueError: If no pending approval exists.
        """
        if state.pending_approval is None:
            raise ValueError("Cannot reject: no pending approval request found in AgentState.")

        new_state = state.model_copy(deep=True)
        rejected_action = new_state.pending_approval.action
        new_state.pending_approval = None
        new_state.task_status = TaskStatus.STOPPED
        new_state.errors.append(
            f"Action '{rejected_action}' was rejected by human. Reason: {reason}"
        )
        new_state.observations.append(Observation(
            source="approval_gate",
            summary=f"Action '{rejected_action}' was rejected. Task stopped. Reason: {reason}",
            timestamp=datetime.now().isoformat(),
            metadata={"outcome": ApprovalOutcome.REJECTED, "action": rejected_action, "reason": reason},
        ))

        return new_state
