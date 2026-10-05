"""
test_agent_research.py — Verification test suite for Structured Browser Research.

Run from backend/ directory:

    .venv\Scripts\python test_agent_research.py

Tests verified:
1. AgentState correctly stores ResearchFinding objects.
2. The agent correctly extracts and saves structured research findings using a virtual tool.
3. The duplicate-page avoidance context is passed in the prompt.
4. The final state transitions to COMPLETED normally with findings preserved.
"""

import sys
import os
import logging
from typing import List

sys.path.insert(0, ".")

from app.agent.state import AgentState, TaskStatus, ResearchFinding
from app.agent.tools import ToolRegistry
from app.agent.decision import AgentDecisionEngine, build_decision_prompt
from app.agent.graph import create_agent_graph, run_agent_graph
from app.llm.provider import LLMProvider, LLMResponse, LLMToolCall
from app.browser.manager import BrowserManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

class MockSequentialLLMProvider(LLMProvider):
    def __init__(self, responses: List[LLMResponse]):
        self.responses = responses
        self.call_count = 0

    def generate(self, prompt, tools=None, system_instruction=None):
        if self.call_count < len(self.responses):
            res = self.responses[self.call_count]
        else:
            res = self.responses[-1]
        self.call_count += 1
        return res

def run_agent_research_tests() -> bool:
    all_passed = True

    log.info("=" * 65)
    log.info("AI Browser Agent — Structured Browser Research Test Suite")
    log.info("=" * 65)

    try:
        browser_mgr = BrowserManager()
        browser_mgr.start()
        registry = ToolRegistry(browser_mgr)

        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "test_pages", "research"))
        index_url = f"file:///{base_path}/index.html".replace("\\", "/")
        page_a_url = f"file:///{base_path}/page-a.html".replace("\\", "/")

        log.info("STEP 1 · Testing Agent Research Pipeline")

        state = AgentState(
            task_id="research-test-01",
            user_goal="Research the provided pages and identify which technologies are Python-based.",
            task_status=TaskStatus.RUNNING
        )

        seq_provider = MockSequentialLLMProvider([
            LLMResponse(tool_calls=[LLMToolCall(name="open_url", arguments={"url": index_url})]),
            LLMResponse(tool_calls=[LLMToolCall(name="get_links", arguments={"max_links": 10})]),
            LLMResponse(tool_calls=[LLMToolCall(name="open_url", arguments={"url": page_a_url})]),
            LLMResponse(tool_calls=[LLMToolCall(name="get_page_text", arguments={"max_length": 1000})]),
            LLMResponse(tool_calls=[LLMToolCall(name="record_research_finding", arguments={
                "title": "Page A",
                "url": page_a_url,
                "summary": "Python is a programming language used for web dev and data science.",
                "key_points": ["Programming language", "Web development", "Data science"],
                "source": "browser"
            })]),
            LLMResponse(text="I have finished the research. Python is a programming language.")
        ])

        graph = create_agent_graph(tool_registry=registry, llm_provider=seq_provider, max_cycles=10)
        res = run_agent_graph(graph, state, max_cycles=10)

        # Verification
        final_state = res.final_state
        if final_state.task_status != TaskStatus.COMPLETED:
            log.error("❌ FAILED: Final task status is not COMPLETED. Got: %s", final_state.task_status.value)
            all_passed = False
        else:
            log.info("✔ Final task status is COMPLETED")

        if len(final_state.research_findings) != 1:
            log.error("❌ FAILED: Expected 1 research finding, got %d", len(final_state.research_findings))
            all_passed = False
        else:
            finding = final_state.research_findings[0]
            if finding.title != "Page A":
                log.error("❌ FAILED: Finding title mismatch")
                all_passed = False
            elif finding.url != page_a_url:
                log.error("❌ FAILED: Finding URL mismatch")
                all_passed = False
            elif len(finding.key_points) != 3:
                log.error("❌ FAILED: Finding key points missing")
                all_passed = False
            else:
                log.info("✔ Research finding recorded correctly!")

        # Check prompt for recently visited URLs
        prompt = build_decision_prompt(final_state)
        if "Recently Visited URLs:" not in prompt:
            log.error("❌ FAILED: Prompt missing 'Recently Visited URLs:' section.")
            all_passed = False
        elif page_a_url not in prompt or index_url not in prompt:
            log.error("❌ FAILED: Prompt does not include the visited URLs.")
            all_passed = False
        else:
            log.info("✔ Duplicate-page avoidance context correctly formed!")
            
        if "Research Findings:" not in prompt or "Page A" not in prompt:
            log.error("❌ FAILED: Prompt missing 'Research Findings:' section or the finding itself.")
            all_passed = False
        else:
            log.info("✔ Research findings correctly populated in context!")

    except Exception as exc:
        log.error("❌ Test suite crashed: %s", exc, exc_info=True)
        all_passed = False
    finally:
        browser_mgr.close()

    log.info("=" * 65)
    if all_passed:
        log.info("OVERALL RESULT: ALL RESEARCH TESTS PASSED SUCCESSFULLY! 🎉")
    else:
        log.error("OVERALL RESULT: SOME TESTS FAILED.")
    log.info("=" * 65)
    return all_passed

if __name__ == "__main__":
    success = run_agent_research_tests()
    sys.exit(0 if success else 1)
