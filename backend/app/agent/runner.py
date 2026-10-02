"""
Public Agent Runner for AI Browser Agent.
Provides a clean, high-level entry point to execute autonomous browser research tasks.
"""

import uuid
import logging
from typing import List, Optional
from pydantic import BaseModel, Field

from app.agent.state import AgentState, Constraint, TaskStatus
from app.agent.tools import ToolRegistry
from app.agent.decision import AgentDecisionEngine
from app.agent.graph import create_agent_graph, run_agent_graph, AgentGraphResult
from app.llm.provider import LLMProvider
from app.llm.gemini import GeminiLLMProvider
from app.browser.manager import BrowserManager

logger = logging.getLogger(__name__)


class AgentRunner:
    """
    Runner for autonomous browser research tasks.
    Manages dependency injection, initializes AgentState, and executes the LangGraph loop.
    """

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        llm_provider: Optional[LLMProvider] = None,
        browser_manager: Optional[BrowserManager] = None,
        decision_engine: Optional[AgentDecisionEngine] = None,
    ):
        """
        Initialize AgentRunner with optional injected dependencies.
        Allows full mocking for deterministic unit testing.
        """
        self.browser_manager = browser_manager
        self.tool_registry = tool_registry
        self.llm_provider = llm_provider
        self.decision_engine = decision_engine

    def run_task(
        self,
        user_goal: str,
        task_id: Optional[str] = None,
        max_cycles: int = 5,
        constraints: Optional[List[Constraint]] = None,
    ) -> AgentGraphResult:
        """
        Execute an autonomous research task for a user goal.

        Args:
            user_goal: Natural language goal for the agent.
            task_id: Optional unique task identifier (generated if omitted).
            max_cycles: Maximum allowed decision cycles (default: 5).
            constraints: Optional initial constraints list.

        Returns:
            AgentGraphResult containing final AgentState, last decision, verification status, and cycle metrics.
        """
        if not user_goal or not user_goal.strip():
            raise ValueError("user_goal cannot be empty.")

        tid = task_id or f"task-{uuid.uuid4().hex[:8]}"

        initial_state = AgentState(
            task_id=tid,
            user_goal=user_goal.strip(),
            extracted_constraints=constraints or [],
            task_status=TaskStatus.RUNNING,
        )

        own_browser_manager = None
        try:
            if self.decision_engine:
                engine = self.decision_engine
            else:
                registry = self.tool_registry
                provider = self.llm_provider

                if registry is None:
                    if self.browser_manager is None:
                        own_browser_manager = BrowserManager()
                        own_browser_manager.start()
                        mgr = own_browser_manager
                    else:
                        mgr = self.browser_manager
                    registry = ToolRegistry(mgr)

                if provider is None:
                    provider = GeminiLLMProvider()

                engine = AgentDecisionEngine(tool_registry=registry, llm_provider=provider)

            graph = create_agent_graph(decision_engine=engine, max_cycles=max_cycles)
            result = run_agent_graph(graph, initial_state=initial_state, max_cycles=max_cycles)
            return result

        finally:
            if own_browser_manager:
                try:
                    own_browser_manager.stop()
                except Exception as e:
                    logger.warning("Error stopping auto-created BrowserManager: %s", e)


def run_agent_task(
    user_goal: str,
    task_id: Optional[str] = None,
    max_cycles: int = 5,
    tool_registry: Optional[ToolRegistry] = None,
    llm_provider: Optional[LLMProvider] = None,
    browser_manager: Optional[BrowserManager] = None,
) -> AgentGraphResult:
    """
    Convenience function for executing an autonomous agent task.
    """
    runner = AgentRunner(
        tool_registry=tool_registry,
        llm_provider=llm_provider,
        browser_manager=browser_manager,
    )
    return runner.run_task(user_goal=user_goal, task_id=task_id, max_cycles=max_cycles)
