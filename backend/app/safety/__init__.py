"""
Safety package for AI Browser Agent.
"""

from app.safety.approval import (
    ApprovalGate,
    ApprovalOutcome,
    CONSEQUENTIAL_ACTIONS,
    is_consequential,
)

__all__ = [
    "ApprovalGate",
    "ApprovalOutcome",
    "CONSEQUENTIAL_ACTIONS",
    "is_consequential",
]
