"""
State definitions for the AI Browser Agent.
Uses Pydantic for strong typing and serialization.
"""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class TaskStatus(str, Enum):
    """Status of the agent's current task."""
    IDLE = "idle"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class Constraint(BaseModel):
    """A constraint for the current task."""
    name: str
    value: str
    required: bool = True

    @field_validator("name")
    def validate_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Constraint name cannot be empty")
        return v


class Observation(BaseModel):
    """A concise factual observation from the environment."""
    source: str
    summary: str
    url: Optional[str] = None
    timestamp: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RejectedItem(BaseModel):
    """An item that was evaluated and rejected based on constraints."""
    title: str
    url: str
    reason: str


class DiscoveredItem(BaseModel):
    """An item that was discovered and matches constraints."""
    title: str
    url: str
    source: Optional[str] = None
    status: str = "discovered"


class EvaluationDecision(str, Enum):
    """Structured relevance decision for an evaluated item."""
    SELECTED = "selected"
    REJECTED = "rejected"


class ItemEvaluation(BaseModel):
    """Structured relevance evaluation result for a discovered or researched item."""
    item: str = Field(description="Short descriptive name or title of the item.")
    url: str = Field(description="URL of the item being evaluated.")
    decision: EvaluationDecision = Field(description="'selected' if the item is relevant; 'rejected' if not.")
    reason: str = Field(description="Brief justification explaining the decision.")


class ResearchFinding(BaseModel):
    """Structured information extracted during research."""
    title: str
    url: str
    summary: str
    key_points: List[str] = Field(default_factory=list)
    source: str = "browser"


class ApprovalRequest(BaseModel):
    """A request for human-in-the-loop approval."""
    action: str
    description: str
    target: Optional[str] = None
    required: bool = True


class AgentState(BaseModel):
    """
    Observable task state for the AI Browser Agent.
    Does NOT include private reasoning or chain-of-thought.
    """
    task_id: str
    user_goal: str
    extracted_constraints: List[Constraint] = Field(default_factory=list)
    current_plan: List[str] = Field(default_factory=list)
    completed_steps: List[str] = Field(default_factory=list)
    current_step: Optional[str] = None
    observations: List[Observation] = Field(default_factory=list)
    discovered_items: List[DiscoveredItem] = Field(default_factory=list)
    rejected_items: List[RejectedItem] = Field(default_factory=list)
    selected_items: List[DiscoveredItem] = Field(default_factory=list)
    research_findings: List[ResearchFinding] = Field(default_factory=list)
    evaluations: List[ItemEvaluation] = Field(default_factory=list)
    task_status: TaskStatus = TaskStatus.IDLE
    pending_approval: Optional[ApprovalRequest] = None
    verification_status: str = "not_started"
    errors: List[str] = Field(default_factory=list)

    @field_validator("task_id")
    def validate_task_id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("task_id cannot be empty")
        return v

    @field_validator("user_goal")
    def validate_user_goal(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("user_goal cannot be empty")
        return v
