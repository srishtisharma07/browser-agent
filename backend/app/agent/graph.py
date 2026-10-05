"""
LangGraph Agent State Machine for AI Browser Agent.
Orchestrates a bounded autonomous decision-execution-verification loop using LangGraph.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END

from app.agent.state import AgentState, Observation, TaskStatus
from app.agent.tools import ToolRegistry
from app.agent.decision import AgentDecisionEngine, AgentDecisionResult
from app.llm.provider import LLMProvider


class AgentGraphState(TypedDict):
    """
    Typed dictionary passed between nodes in the LangGraph state machine.
    Accumulates observations and cycle counts across execution turns.
    """
    agent_state: AgentState
    decision_result: Optional[AgentDecisionResult]
    verification_status: Optional[str]
    cycle_count: int
    max_cycles: int
    action_history: List[str]
    stop_reason: Optional[str]


class AgentGraphResult(BaseModel):
    """
    Typed summary result returned after executing the LangGraph agent graph loop.
    """
    final_state: AgentState = Field(description="The updated AgentState after graph loop completion.")
    decision: Optional[AgentDecisionResult] = Field(default=None, description="The decision details from the last executed cycle.")
    verification_status: str = Field(description="Final cycle verification status ('response_success', 'tool_success', or 'action_failed').")
    cycle_count: int = Field(default=0, description="Total number of cycles executed.")
    stop_reason: str = Field(default="completed", description="Reason why the loop terminated.")


def create_agent_graph(
    decision_engine: Optional[AgentDecisionEngine] = None,
    tool_registry: Optional[ToolRegistry] = None,
    llm_provider: Optional[LLMProvider] = None,
    max_cycles: int = 5,
) -> Any:
    """
    Factory function that builds and compiles a LangGraph StateGraph instance.
    Uses dependency injection: accepts an existing decision_engine or tool_registry + llm_provider.

    Graph Flow:
        START -> decide -> execute -> verify -> should_continue?
                                                    ├── "continue" -> decide
                                                    └── "stop"     -> END
    """
    if not isinstance(max_cycles, int) or max_cycles <= 0:
        raise ValueError("max_cycles must be a positive integer.")

    if decision_engine is None:
        if tool_registry is None or llm_provider is None:
            raise ValueError("Must provide either a decision_engine or both tool_registry and llm_provider.")
        engine = AgentDecisionEngine(tool_registry=tool_registry, llm_provider=llm_provider)
    else:
        engine = decision_engine

    # --- Node 1: DECIDE ---
    def decide_node(state: AgentGraphState) -> Dict[str, Any]:
        """
        Increments cycle counter and invokes AgentDecisionEngine on current agent_state.
        Accumulates observations from all previous cycles.
        """
        current_agent_state = state["agent_state"]

        # Check explicit STOPPED status before decision
        if current_agent_state.task_status == TaskStatus.STOPPED:
            return {
                "stop_reason": "task_stopped",
                "verification_status": "action_failed",
            }

        current_cycle = state.get("cycle_count", 0) + 1
        history = list(state.get("action_history", []))

        decision_res = engine.execute_cycle(current_agent_state)

        # Track action signature for loop detection
        if decision_res.action == "tool_call" and decision_res.tool_name:
            args_str = json.dumps(decision_res.arguments, sort_keys=True)
            sig = f"{decision_res.tool_name}:{args_str}"
            history.append(sig)
        elif decision_res.action == "respond":
            history.append("action:respond")

        return {
            "agent_state": decision_res.updated_state,
            "decision_result": decision_res,
            "cycle_count": current_cycle,
            "action_history": history,
            "stop_reason": None,
        }

    # --- Node 2: EXECUTE ---
    def execute_node(state: AgentGraphState) -> Dict[str, Any]:
        """
        Execution stage node.
        Confirms tool execution went through ToolRegistry boundary during decision cycle.
        """
        if state.get("stop_reason"):
            return {}

        decision_res = state.get("decision_result")
        agent_st = state.get("agent_state")

        if not decision_res or not agent_st:
            return {}

        return {
            "agent_state": agent_st,
            "decision_result": decision_res,
        }

    # --- Node 3: VERIFY ---
    def verify_node(state: AgentGraphState) -> Dict[str, Any]:
        """
        Lightweight verification node for the current cycle.
        Determines verification_status and evaluates loop termination criteria.
        """
        if state.get("stop_reason"):
            return {}

        decision_res = state.get("decision_result")
        agent_st = state.get("agent_state")
        cycle_count = state.get("cycle_count", 0)
        limit = state.get("max_cycles", max_cycles)
        history = state.get("action_history", [])

        status = "action_failed"
        if decision_res:
            if decision_res.action == "respond":
                status = "response_success"
            elif decision_res.action == "tool_call":
                tool_res = decision_res.tool_result
                is_success = False
                if isinstance(tool_res, dict):
                    is_success = tool_res.get("success", False)
                elif hasattr(tool_res, "success"):
                    is_success = getattr(tool_res, "success", False)

                status = "tool_success" if is_success else "action_failed"

        updated_agent_st = agent_st.model_copy(deep=True) if agent_st else AgentState(task_id="empty", user_goal="empty")
        updated_agent_st.verification_status = status

        # Evaluate termination conditions
        stop_reason = None

        if agent_st and agent_st.task_status == TaskStatus.STOPPED:
            stop_reason = "task_stopped"
        elif decision_res and decision_res.action == "respond":
            stop_reason = "completed_response"
            updated_agent_st.task_status = TaskStatus.COMPLETED
        elif len(history) >= 3 and history[-1] == history[-2] == history[-3] and history[-1] != "action:respond":
            err_msg = "Loop protection triggered: 3 consecutive identical tool calls detected."
            updated_agent_st.errors.append(err_msg)
            updated_agent_st.observations.append(Observation(
                source="loop_protection",
                summary=err_msg,
                timestamp=datetime.now().isoformat(),
            ))
            stop_reason = "consecutive_duplicate_action"
        elif decision_res and decision_res.action == "error":
            stop_reason = "execution_error"
        elif cycle_count >= limit:
            stop_reason = "max_cycles_reached"

        return {
            "agent_state": updated_agent_st,
            "verification_status": status,
            "stop_reason": stop_reason,
        }

    # --- Conditional Edge: SHOULD_CONTINUE ---
    def should_continue(state: AgentGraphState) -> str:
        """
        Determines whether the loop should execute another cycle or terminate.
        """
        if state.get("stop_reason") is not None:
            return "stop"
        return "continue"

    # --- Build StateGraph ---
    workflow = StateGraph(AgentGraphState)

    # Add Nodes
    workflow.add_node("decide", decide_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("verify", verify_node)

    # Add Edges
    workflow.add_edge(START, "decide")
    workflow.add_edge("decide", "execute")
    workflow.add_edge("execute", "verify")

    # Add Conditional Edge from verify
    workflow.add_conditional_edges(
        "verify",
        should_continue,
        {
            "continue": "decide",
            "stop": END,
        }
    )

    # Compile and return
    return workflow.compile()


def run_agent_graph(
    graph: Any,
    initial_state: AgentState,
    max_cycles: int = 5,
) -> AgentGraphResult:
    """
    Helper function to invoke a compiled LangGraph instance with an initial AgentState.

    Args:
        graph: Compiled LangGraph instance.
        initial_state: Starting AgentState.
        max_cycles: Maximum allowed execution turns (default: 5).

    Returns:
        AgentGraphResult containing final AgentState, last decision details, verification status, cycle count, and stop reason.
    """
    if not isinstance(max_cycles, int) or max_cycles <= 0:
        raise ValueError("max_cycles must be a positive integer.")

    initial_graph_state: AgentGraphState = {
        "agent_state": initial_state,
        "decision_result": None,
        "verification_status": None,
        "cycle_count": 0,
        "max_cycles": max_cycles,
        "action_history": [],
        "stop_reason": None,
    }

    final_graph_state = graph.invoke(initial_graph_state)

    final_state = final_graph_state["agent_state"]
    decision = final_graph_state.get("decision_result")
    ver_status = final_graph_state.get("verification_status") or "action_failed"
    cycles_run = final_graph_state.get("cycle_count", 0)
    reason = final_graph_state.get("stop_reason") or "completed"

    return AgentGraphResult(
        final_state=final_state,
        decision=decision,
        verification_status=ver_status,
        cycle_count=cycles_run,
        stop_reason=reason,
    )
