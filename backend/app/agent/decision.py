"""
Single Agent Decision Engine for AI Browser Agent.
Executes exactly one decision cycle connecting AgentState, ToolRegistry, and LLMProvider.
"""

from datetime import datetime
from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field

from app.agent.state import AgentState, Observation
from app.agent.tools import ToolRegistry
from app.llm.provider import LLMProvider, LLMResponse


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
        "Rules:\n"
        "1. You must achieve the user's goal while respecting all constraints.\n"
        "2. Choose only from the supplied browser tools. Do NOT invent tool names or arguments.\n"
        "3. Request at most ONE tool call per step.\n"
        "4. If you have enough information to answer or if no further browser action is needed, provide a clear direct text response without requesting any tool.\n"
        "5. Do NOT invent browser observations or claim success without evidence.\n"
        "6. Do NOT output code, script, Python commands, or shell instructions."
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
        f"Discovered Items:\n{disc_str}\n\n"
        f"Rejected Items:\n{rej_str}\n\n"
        f"Instructions: Based on the state above, decide whether to call ONE browser tool or provide a direct final response."
    )


class AgentDecisionEngine:
    """
    Executes a single, controlled decision cycle for the AI Browser Agent.
    Strictly enforces security boundaries: LLM decisions -> ToolRegistry validation -> Execution.
    """

    def __init__(self, tool_registry: ToolRegistry, llm_provider: LLMProvider):
        self.tool_registry = tool_registry
        self.llm_provider = llm_provider

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

            # Validate tool exists in registry
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

            if isinstance(exec_result, dict):
                is_success = exec_result.get("success", False)
                result_url = exec_result.get("url")
                if not is_success:
                    summary = f"Tool '{tool_name}' failed: {exec_result.get('error', 'Unknown error')}"
                else:
                    summary = f"Tool '{tool_name}' executed successfully."
            elif hasattr(exec_result, "success"):
                is_success = getattr(exec_result, "success", False)
                result_url = getattr(exec_result, "url", None)
                if not is_success:
                    summary = f"Tool '{tool_name}' failed: {getattr(exec_result, 'error', 'Unknown error')}"
                else:
                    summary = f"Tool '{tool_name}' executed successfully."
            else:
                summary = f"Tool '{tool_name}' returned result."
                is_success = True

            new_state.observations.append(Observation(
                source=f"tool:{tool_name}",
                summary=summary,
                url=result_url,
                timestamp=timestamp,
                metadata={"success": is_success, "arguments": arguments}
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
