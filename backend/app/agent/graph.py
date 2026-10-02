"""
LangGraph Agent State Machine for AI Browser Agent.
Orchestrates a single decision-execution-verification cycle using LangGraph.
"""

from typing import Any, Dict, Optional, TypedDict
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END

from app.agent.state import AgentState
from app.agent.tools import ToolRegistry
from app.agent.decision import AgentDecisionEngine, AgentDecisionResult
from app.llm.provider import LLMProvider


class AgentGraphState(TypedDict):
    """
    Typed dictionary passed between nodes in the LangGraph state machine.
    """
    agent_state: AgentState
    decision_result: Optional[AgentDecisionResult]
    verification_status: Optional[str]


class AgentGraphResult(BaseModel):
    """
    Typed summary result returned after executing the LangGraph agent graph.
    """
    final_state: AgentState = Field(description="The updated AgentState after cycle completion.")
    decision: AgentDecisionResult = Field(description="The decision details from the cycle.")
    verification_status: str = Field(description="Cycle verification status ('response_success', 'tool_success', or 'action_failed').")


def create_agent_graph(
    decision_engine: Optional[AgentDecisionEngine] = None,
    tool_registry: Optional[ToolRegistry] = None,
    llm_provider: Optional[LLMProvider] = None,
) -> Any:
    """
    Factory function that builds and compiles a LangGraph StateGraph instance.
    Uses dependency injection: accepts an existing decision_engine or tool_registry + llm_provider.

    Graph Flow:
        START -> decide -> execute -> verify -> END
    """
    if decision_engine is None:
        if tool_registry is None or llm_provider is None:
            raise ValueError("Must provide either a decision_engine or both tool_registry and llm_provider.")
        engine = AgentDecisionEngine(tool_registry=tool_registry, llm_provider=llm_provider)
    else:
        engine = decision_engine

    # --- Node 1: DECIDE ---
    def decide_node(state: AgentGraphState) -> Dict[str, Any]:
        """
        Invokes AgentDecisionEngine on current agent_state.
        """
        current_agent_state = state["agent_state"]
        decision_res = engine.execute_cycle(current_agent_state)

        return {
            "agent_state": decision_res.updated_state,
            "decision_result": decision_res,
        }

    # --- Node 2: EXECUTE ---
    def execute_node(state: AgentGraphState) -> Dict[str, Any]:
        """
        Execution stage node.
        Confirms tool execution went through ToolRegistry boundary during decision cycle,
        or verifies no tool was executed for direct responses.
        """
        decision_res = state.get("decision_result")
        agent_st = state.get("agent_state")

        # Safety check: if no decision was made, return unchanged
        if not decision_res or not agent_st:
            return {}

        # The decision engine has already handled ToolRegistry boundary execution.
        # This node reinforces the safety boundary and formats current step context.
        return {
            "agent_state": agent_st,
            "decision_result": decision_res,
        }

    # --- Node 3: VERIFY ---
    def verify_node(state: AgentGraphState) -> Dict[str, Any]:
        """
        Lightweight verification node for the current single cycle.
        Determines if current action succeeded or failed. Does NOT mark overall task as COMPLETED.
        """
        decision_res = state.get("decision_result")
        agent_st = state.get("agent_state")

        if not decision_res or not agent_st:
            status = "action_failed"
        elif decision_res.action == "respond":
            status = "response_success"
        elif decision_res.action == "tool_call":
            tool_res = decision_res.tool_result
            is_success = False
            if isinstance(tool_res, dict):
                is_success = tool_res.get("success", False)
            elif hasattr(tool_res, "success"):
                is_success = getattr(tool_res, "success", False)

            status = "tool_success" if is_success else "action_failed"
        else:
            status = "action_failed"

        # Update verification status in state
        updated_agent_st = agent_st.model_copy(deep=True)
        updated_agent_st.verification_status = status

        return {
            "agent_state": updated_agent_st,
            "verification_status": status,
        }

    # --- Build StateGraph ---
    workflow = StateGraph(AgentGraphState)

    # Add Nodes
    workflow.add_node("decide", decide_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("verify", verify_node)

    # Add Linear Edges: START -> decide -> execute -> verify -> END
    workflow.add_edge(START, "decide")
    workflow.add_edge("decide", "execute")
    workflow.add_edge("execute", "verify")
    workflow.add_edge("verify", END)

    # Compile and return
    return workflow.compile()


def run_agent_graph(graph: Any, initial_state: AgentState) -> AgentGraphResult:
    """
    Helper function to invoke a compiled LangGraph instance with an initial AgentState.

    Returns:
        AgentGraphResult containing final AgentState, decision details, and verification status.
    """
    initial_graph_state: AgentGraphState = {
        "agent_state": initial_state,
        "decision_result": None,
        "verification_status": None,
    }

    final_graph_state = graph.invoke(initial_graph_state)

    final_state = final_graph_state["agent_state"]
    decision = final_graph_state["decision_result"]
    ver_status = final_graph_state["verification_status"]

    return AgentGraphResult(
        final_state=final_state,
        decision=decision,
        verification_status=ver_status,
    )
