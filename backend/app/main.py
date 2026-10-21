"""
AI Browser Agent – FastAPI backend entry point.
Provides task execution endpoints and status polling for the Agent Control Center.
"""

from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from app.agent.service import global_task_manager, TaskManager

app = FastAPI(
    title="AI Browser Agent",
    description="SIH260171 – AI-Powered Browser Assistant / Agent (backend API)",
    version="0.2.0",
)

# Attach task manager to app state for testability and lifecycle control
app.state.task_manager = global_task_manager

# Allow requests from the Vite dev server during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateTaskRequest(BaseModel):
    goal: str = Field(description="Natural language objective for the agent.")
    max_cycles: Optional[int] = Field(default=5, ge=1, le=20, description="Max execution cycles (1-20).")

    @field_validator("goal")
    def validate_goal(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Task goal cannot be empty.")
        return v.strip()


def get_task_mgr() -> TaskManager:
    return getattr(app.state, "task_manager", global_task_manager)


@app.get("/api/health", tags=["health"])
async def health_check() -> dict:
    """
    Simple liveness probe.

    Returns:
        JSON payload confirming the service is up.
    """
    return {
        "status": "ok",
        "service": "ai-browser-agent",
    }


@app.post("/api/tasks", status_code=status.HTTP_201_CREATED, tags=["tasks"])
async def create_task(req: CreateTaskRequest) -> Dict[str, Any]:
    """
    Start an autonomous agent task with a user-provided goal.
    Returns a unique task ID immediately and executes in the background.
    """
    mgr = get_task_mgr()
    try:
        task = mgr.create_and_start_task(goal=req.goal, max_cycles=req.max_cycles or 5)
        return task
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.get("/api/tasks/{task_id}", tags=["tasks"])
async def get_task_by_id(task_id: str) -> Dict[str, Any]:
    """
    Retrieve current task status, observations, discovered items, evaluations,
    application drafts, errors, and final response.
    """
    mgr = get_task_mgr()
    task = mgr.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found.",
        )
    return task


@app.get("/api/tasks", tags=["tasks"])
async def list_all_tasks() -> Dict[str, Any]:
    """
    List all executed and active tasks.
    """
    mgr = get_task_mgr()
    return {"tasks": mgr.list_tasks()}
