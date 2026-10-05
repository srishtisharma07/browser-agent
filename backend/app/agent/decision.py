"""
Single Agent Decision Engine for AI Browser Agent.
Executes exactly one decision cycle connecting AgentState, ToolRegistry, and LLMProvider.
Includes Human-in-the-Loop approval gate before consequential actions.
"""

from datetime import datetime
from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field

from app.agent.state import AgentState, DiscoveredItem, EvaluationDecision, ItemEvaluation, Observation, RejectedItem, TaskStatus
from app.agent.tools import ToolRegistry
from app.llm.provider import LLMProvider, LLMResponse
from app.safety.approval import ApprovalGate, is_consequential


class AgentDecisionResult(BaseModel):
    """
    Typed result of a single agent decision cycle.
    Provider-agnostic representation of the LLM's choice and resulting state update.
    """
    action: Literal["respond", "tool_call", "error"] = Field(
        description="Action type decided by the agent."
    )
    response_text: Optional[str] = Field(
        default=None,
        description="Direct text response if action is 'respond' or error details if action is 'error'."
    )
    tool_name: Optional[str] = Field(
        default=None,
        description="Name of the executed tool if action is 'tool_call'."
    )
    arguments: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments passed to the tool if action is 'tool_call'."
    )
    tool_result: Optional[Any] = Field(
        default=None,
        description="Structured execution result returned by ToolRegistry."
    )
    updated_state: AgentState = Field(
        description="The updated AgentState following the decision cycle."
    )


def build_system_instruction() -> str:
    """Returns system instruction prompt guiding the LLM as a browser control agent."""
    return (
        "You are an AI Browser Agent controlling a web browser via predefined tools.\n"
        "For research tasks, you should:\n"
        " - Understand the research goal and identify useful sources/pages.\n"
        " - Navigate using registered browser tools and inspect page content.\n"
        " - Extract relevant facts using the record_research_finding tool, and keep track of useful findings.\n"
        " - After inspecting an item, use the evaluate_item tool to record whether it is 'selected' (relevant) or 'rejected' (not relevant), with a brief reason.\n"
        " - Avoid irrelevant pages and avoid repeatedly visiting the same page.\n"
        " - Produce a concise final synthesis when complete, summarising selected items and why rejected items were discarded.\n"
        "Rules:\n"
        "1. You must achieve the user's goal while respecting all constraints.\n"
        "2. Choose only from the supplied browser tools. Do NOT invent tool names or arguments.\n"
        "3. Request at most ONE tool call per step.\n"
        "4. If you have enough information to answer or if no further browser action is needed, provide a clear direct text response without requesting any tool.\n"
        "5. Do NOT invent browser observations or claim success without evidence.\n"
        "6. Do not claim that information was found unless it came from an observed browser page or another provided observation.\n"
        "7. Do NOT output code, script, Python commands, or shell instructions."
    )


def build_decision_prompt(state: AgentState) -> str:
    """Constructs a structured prompt from current AgentState for the LLM."""
    constraints_str = "\n".join(
        f"- {c.name}: {c.value} (Required: {c.required})"
        for c in state.extracted_constraints
    ) or "None"

    plan_str = "\n".join(f"- {step}" for step in state.current_plan) or "None"
    completed_str = "\n".join(f"- {step}" for step in state.completed_steps) or "None"

    obs_str = "\n".join(
        f"- [{o.source}] {o.summary}" + (f" (URL: {o.url})" if o.url else "")
        for o in state.observations[-5:]
    ) or "None"

    disc_str = "\n".join(
        f"- {d.title} ({d.url})" for d in state.discovered_items
    ) or "None"

    rej_str = "\n".join(
        f"- {r.title}: {r.reason}" for r in state.rejected_items
    ) or "None"

    # Explicitly surface recent errors so the LLM can reason about failures
    # and choose an alternative action (recovery). This is the mechanism that
    # makes recovery LLM-driven rather than hard-coded.
    recent_errors = state.errors[-3:] if state.errors else []
    errors_str = "\n".join(f"- {e}" for e in recent_errors) or "None"

    visited_urls = []
    for obs in state.observations:
        if obs.source == "tool:open_url" and obs.metadata.get("success"):
            url = obs.metadata.get("arguments", {}).get("url")
            if url and url not in visited_urls:
                visited_urls.append(url)
    visited_str = "\n".join(f"- {u}" for u in visited_urls[-10:]) or "None"

    findings_str = "\n".join(
        f"- {f.title} ({f.url}): {f.summary}" for f in state.research_findings
    ) or "None"

    evals_str = "\n".join(
        f"- [{e.decision.value.upper()}] {e.item} ({e.url}): {e.reason}"
        for e in state.evaluations
    ) or "None"

    return (
        f"CURRENT TASK STATE:\n"
        f"Task ID: {state.task_id}\n"
        f"User Goal: {state.user_goal}\n"
        f"Status: {state.task_status.value}\n\n"
        f"Extracted Constraints:\n{constraints_str}\n\n"
        f"Current Plan:\n{plan_str}\n\n"
        f"Completed Steps:\n{completed_str}\n\n"
        f"Current Step: {state.current_step or 'Starting'}\n\n"
        f"Recent Observations:\n{obs_str}\n\n"
        f"Recent Errors (use these to choose a recovery action if needed):\n{errors_str}\n\n"
        f"Discovered Items:\n{disc_str}\n\n"
        f"Rejected Items:\n{rej_str}\n\n"
        f"Research Findings:\n{findings_str}\n\n"
        f"Item Evaluations (selected/rejected):\n{evals_str}\n\n"
        f"Recently Visited URLs:\n{visited_str}\n\n"
        f"Instructions: Based on the state above, decide whether to call ONE browser tool or provide a direct final response."
    )


class AgentDecisionEngine:
    """
    Executes a single, controlled decision cycle for the AI Browser Agent.
    Strictly enforces security boundaries: LLM decisions -> ApprovalGate -> ToolRegistry -> Execution.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        llm_provider: LLMProvider,
        approval_gate: Optional[ApprovalGate] = None,
    ):
        self.tool_registry = tool_registry
        self.llm_provider = llm_provider
        self.approval_gate: ApprovalGate = approval_gate or ApprovalGate()

    def execute_cycle(self, state: AgentState) -> AgentDecisionResult:
        """
        Runs one decision cycle on the provided state.

        Args:
            state: The current AgentState instance.

        Returns:
            AgentDecisionResult containing action type, details, and updated AgentState.
        """
        new_state = state.model_copy(deep=True)

        prompt = build_decision_prompt(new_state)
        system_instruction = build_system_instruction()
        tools_schema = self.tool_registry.get_tool_schemas()

        response: LLMResponse = self.llm_provider.generate(
            prompt=prompt,
            tools=tools_schema,
            system_instruction=system_instruction,
        )

        timestamp = datetime.now().isoformat()

        # Handle provider-level error
        if response.error:
            error_msg = f"LLM provider error: {response.error}"
            new_state.errors.append(error_msg)
            new_state.observations.append(Observation(
                source="decision_engine",
                summary=error_msg,
                timestamp=timestamp,
            ))
            return AgentDecisionResult(
                action="error",
                response_text=error_msg,
                updated_state=new_state,
            )

        # Check for multiple tool calls - explicitly reject multiple calls
        if len(response.tool_calls) > 1:
            error_msg = f"Rejected multiple tool calls: received {len(response.tool_calls)} calls, max allowed is 1."
            new_state.errors.append(error_msg)
            new_state.observations.append(Observation(
                source="decision_engine",
                summary=error_msg,
                timestamp=timestamp,
            ))
            return AgentDecisionResult(
                action="error",
                response_text=error_msg,
                updated_state=new_state,
            )

        # Case 1: LLM requested a single tool call
        if len(response.tool_calls) == 1:
            tool_call = response.tool_calls[0]
            tool_name = tool_call.name
            arguments = tool_call.arguments

            # --- Approval Gate: check BEFORE registry validation ---
            # Consequential actions (e.g. submit_application) are intercepted here
            # even if they are not registered in ToolRegistry.
            gated_state = self.approval_gate.check(
                action_name=tool_name,
                description=f"Agent wants to execute '{tool_name}' with args: {arguments}",
                state=new_state,
                target=arguments.get("url") or arguments.get("selector"),
            )
            if gated_state.task_status == TaskStatus.WAITING_FOR_APPROVAL:
                # Action is paused — do NOT execute. Return approval-pending result.
                return AgentDecisionResult(
                    action="tool_call",
                    tool_name=tool_name,
                    arguments=arguments,
                    tool_result=None,
                    updated_state=gated_state,
                )
            new_state = gated_state

            # Validate tool exists in registry (only reached for non-consequential tools)
            if not self.tool_registry.has(tool_name):
                error_msg = f"Rejected unknown tool call: '{tool_name}' is not registered."
                new_state.errors.append(error_msg)
                new_state.observations.append(Observation(
                    source="decision_engine",
                    summary=error_msg,
                    timestamp=timestamp,
                ))
                return AgentDecisionResult(
                    action="error",
                    response_text=error_msg,
                    updated_state=new_state,
                )

            step_desc = f"Executing tool: {tool_name}"
            new_state.current_step = step_desc

            # Execute tool strictly through ToolRegistry boundary
            exec_result = self.tool_registry.execute(tool_name, arguments)

            is_success = False
            result_url = None
            summary = ""
            observation_data = None

            if isinstance(exec_result, dict):
                is_success = exec_result.get("success", False)
                result_url = exec_result.get("url")
                observation_data = exec_result.get("observation")
                if not is_success:
                    summary = f"Tool '{tool_name}' failed: {exec_result.get('error', 'Unknown error')}"
                else:
                    summary = f"Tool '{tool_name}' executed successfully."
            elif hasattr(exec_result, "success"):
                is_success = getattr(exec_result, "success", False)
                result_url = getattr(exec_result, "url", None)
                observation_data = getattr(exec_result, "observation", None)
                if not is_success:
                    summary = f"Tool '{tool_name}' failed: {getattr(exec_result, 'error', 'Unknown error')}"
                else:
                    summary = f"Tool '{tool_name}' executed successfully."
            else:
                summary = f"Tool '{tool_name}' returned result."
                is_success = True

            metadata = {"success": is_success, "arguments": arguments}
            if observation_data:
                if hasattr(observation_data, "to_dict"):
                    metadata.update(observation_data.to_dict())
                elif isinstance(observation_data, dict):
                    metadata.update(observation_data)
                else:
                    try:
                        metadata.update(vars(observation_data))
                    except TypeError:
                        pass

            # Update structured state for research findings directly
            if tool_name == "record_research_finding" and is_success:
                try:
                    from app.agent.state import ResearchFinding
                    finding = ResearchFinding(**arguments)
                    new_state.research_findings.append(finding)
                except Exception:
                    pass

            # Update structured state for item evaluations
            if tool_name == "evaluate_item" and is_success:
                try:
                    evaluation = ItemEvaluation(**arguments)
                    new_state.evaluations.append(evaluation)
                    # Mirror into legacy selected_items / rejected_items for backward compat
                    if evaluation.decision == EvaluationDecision.SELECTED:
                        new_state.selected_items.append(
                            DiscoveredItem(
                                title=evaluation.item,
                                url=evaluation.url,
                                status="selected",
                            )
                        )
                    else:
                        new_state.rejected_items.append(
                            RejectedItem(
                                title=evaluation.item,
                                url=evaluation.url,
                                reason=evaluation.reason,
                            )
                        )
                except Exception:
                    pass

            new_state.observations.append(Observation(
                source=f"tool:{tool_name}",
                summary=summary,
                url=result_url,
                timestamp=timestamp,
                metadata=metadata
            ))

            new_state.completed_steps.append(step_desc)

            if not is_success:
                new_state.errors.append(summary)

            return AgentDecisionResult(
                action="tool_call",
                tool_name=tool_name,
                arguments=arguments,
                tool_result=exec_result,
                updated_state=new_state,
            )

        # Case 2: Direct text response (action = "respond")
        response_text = response.text or "No response text generated."
        new_state.observations.append(Observation(
            source="llm_response",
            summary=f"Agent response: {response_text[:100]}...",
            timestamp=timestamp,
        ))

        return AgentDecisionResult(
            action="respond",
            response_text=response_text,
            updated_state=new_state,
        )
