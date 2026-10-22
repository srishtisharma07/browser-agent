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


class CandidateProfile(BaseModel):
    """
    Structured candidate profile used to guide internship discovery and match evaluation.
    """
    education: Optional[str] = Field(
        default=None,
        description="Candidate's education, degree, major, or institution (e.g. 'B.S. in Computer Science').",
    )
    graduation_year: Optional[int] = Field(
        default=None,
        description="Expected or actual graduation year (e.g. 2026).",
    )
    technical_skills: List[str] = Field(
        default_factory=list,
        description="List of technical skills (e.g. ['Python', 'React', 'FastAPI', 'Playwright']).",
    )
    experience_level: Optional[str] = Field(
        default=None,
        description="Candidate experience level (e.g. 'intern', 'undergraduate', 'entry-level').",
    )
    preferred_role: Optional[str] = Field(
        default=None,
        description="Target role title (e.g. 'Software Engineering Intern').",
    )
    location_preferences: List[str] = Field(
        default_factory=list,
        description="Preferred locations or working modes (e.g. ['Remote', 'San Francisco', 'Bangalore']).",
    )
    internship_constraints: List[str] = Field(
        default_factory=list,
        description="Constraints or term requirements (e.g. ['Summer 2026', 'Paid only']).",
    )

    @field_validator("graduation_year")
    def validate_graduation_year(cls, v: Optional[int]) -> Optional[int]:
        if v is not None:
            if v < 1980 or v > 2100:
                raise ValueError("graduation_year must be a valid year between 1980 and 2100")
        return v

    @field_validator("technical_skills", "location_preferences", "internship_constraints", mode="before")
    def validate_string_lists(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        if isinstance(v, (list, tuple, set)):
            return [str(item).strip() for item in v if str(item).strip()]
        return []


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


class DraftStatus(str, Enum):
    """Lifecycle status of an application draft."""
    DRAFT = "draft"
    READY_FOR_REVIEW = "ready_for_review"


class ApplicationDraft(BaseModel):
    """
    A structured application-preparation record.
    Represents a prepared (but NOT submitted) application for a selected item.
    """
    item_title: str = Field(description="Title of the item for which the application is prepared.")
    item_url: str = Field(description="URL of the item.")
    status: DraftStatus = Field(
        default=DraftStatus.DRAFT,
        description="Current lifecycle status of the draft.",
    )
    matched_requirements: List[str] = Field(
        default_factory=list,
        description="Requirements or criteria that the applicant already meets.",
    )
    missing_requirements: List[str] = Field(
        default_factory=list,
        description="Requirements or criteria that are not yet met or need clarification.",
    )
    notes: str = Field(
        default="",
        description="Additional preparation notes or context about the application.",
    )

    @field_validator("item_title")
    def validate_item_title(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("item_title cannot be empty")
        return v

    @field_validator("item_url")
    def validate_item_url(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("item_url cannot be empty")
        lower = v.strip().lower()
        if not (lower.startswith("http://") or lower.startswith("https://")):
            raise ValueError("item_url must be an HTTP or HTTPS URL")
        return v


class ApprovalRequest(BaseModel):
    """A request for human-in-the-loop approval."""
    action: str
    description: str
    target: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Saved arguments for the exact pending action.")
    request_id: Optional[str] = Field(default=None, description="Unique identifier for the pending approval request.")
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
    application_drafts: List[ApplicationDraft] = Field(default_factory=list)
    candidate_profile: Optional[CandidateProfile] = None
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
