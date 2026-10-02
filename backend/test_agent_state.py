"""
test_agent_state.py — Focused test suite for the agent state models.

Run from backend/ directory:

    .venv\\Scripts\\python test_agent_state.py

Tests verified:
1. Empty/default AgentState can be created.
2. State serializes to a dictionary.
3. State serializes to JSON.
4. State can be reconstructed from serialized data.
5. TaskStatus serializes correctly.
6. Constraint model works.
7. Observation model works.
8. DiscoveredItem model works.
9. RejectedItem model works.
10. ApprovalRequest model works.
11. Invalid empty task_id is rejected when supplied.
12. Invalid empty user_goal is rejected when supplied.
13. Invalid empty constraint name is rejected.
14. Defaults do not share mutable state between instances.
"""

import json
import logging
import sys

sys.path.insert(0, ".")

from pydantic import ValidationError

from app.agent.state import (
    TaskStatus,
    Constraint,
    Observation,
    RejectedItem,
    DiscoveredItem,
    ApprovalRequest,
    AgentState,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def run_agent_state_tests() -> bool:
    all_passed = True

    log.info("=" * 65)
    log.info("AI Browser Agent — AgentState Verification Test Suite")
    log.info("=" * 65)

    try:
        log.info("STEP 1 · Testing basic AgentState creation and defaults…")
        
        # 1. Empty/default AgentState can be created
        state1 = AgentState(task_id="task-123", user_goal="Apply for jobs")
        if state1.task_status != TaskStatus.IDLE:
            log.error("❌ FAILED: Default task_status is not IDLE")
            all_passed = False
        if state1.current_step is not None:
            log.error("❌ FAILED: Default current_step is not None")
            all_passed = False
        if state1.pending_approval is not None:
            log.error("❌ FAILED: Default pending_approval is not None")
            all_passed = False
        if state1.verification_status != "not_started":
            log.error("❌ FAILED: Default verification_status is incorrect")
            all_passed = False
        
        # 14. Defaults do not share mutable state between instances
        state2 = AgentState(task_id="task-456", user_goal="Find flights")
        state1.completed_steps.append("step1")
        if len(state2.completed_steps) != 0:
            log.error("❌ FAILED: Mutable state shared between instances!")
            all_passed = False
        
        log.info("✔ Basic creation and defaults PASSED!")

        log.info("\nSTEP 2 · Testing model creation and validation…")
        
        # 6. Constraint model works
        c = Constraint(name="location", value="Remote")
        if c.name != "location" or c.required is not True:
            log.error("❌ FAILED: Constraint model creation failed")
            all_passed = False
            
        # 13. Invalid empty constraint name is rejected
        try:
            Constraint(name="   ", value="Remote")
            log.error("❌ FAILED: Empty constraint name was accepted")
            all_passed = False
        except ValidationError:
            log.info("✔ Empty constraint name rejected correctly.")
            
        # 7. Observation model works
        obs = Observation(source="page", summary="Found 10 jobs", timestamp="2026-10-01", metadata={"count": 10})
        if obs.source != "page" or obs.metadata["count"] != 10:
            log.error("❌ FAILED: Observation model creation failed")
            all_passed = False
            
        # 8. DiscoveredItem model works
        disc = DiscoveredItem(title="Software Engineer", url="https://example.com/job1")
        if disc.status != "discovered":
            log.error("❌ FAILED: DiscoveredItem model creation failed")
            all_passed = False
            
        # 9. RejectedItem model works
        rej = RejectedItem(title="Junior Developer", url="https://example.com/job2", reason="Experience required")
        if rej.reason != "Experience required":
            log.error("❌ FAILED: RejectedItem model creation failed")
            all_passed = False
            
        # 10. ApprovalRequest model works
        appr = ApprovalRequest(action="submit", description="Submit application")
        if appr.required is not True:
            log.error("❌ FAILED: ApprovalRequest model creation failed")
            all_passed = False

        # 11. Invalid empty task_id is rejected when supplied
        try:
            AgentState(task_id="", user_goal="Find flights")
            log.error("❌ FAILED: Empty task_id was accepted")
            all_passed = False
        except ValidationError:
            log.info("✔ Empty task_id rejected correctly.")

        # 12. Invalid empty user_goal is rejected when supplied
        try:
            AgentState(task_id="task-123", user_goal="   ")
            log.error("❌ FAILED: Empty user_goal was accepted")
            all_passed = False
        except ValidationError:
            log.info("✔ Empty user_goal rejected correctly.")
            
        log.info("✔ Model creation and validation PASSED!")

        log.info("\nSTEP 3 · Testing serialization and reconstruction…")
        
        full_state = AgentState(
            task_id="task-999",
            user_goal="Complex task",
            extracted_constraints=[c],
            current_plan=["step1", "step2"],
            completed_steps=["step1"],
            current_step="step2",
            observations=[obs],
            discovered_items=[disc],
            rejected_items=[rej],
            selected_items=[],
            task_status=TaskStatus.RUNNING,
            pending_approval=appr,
            verification_status="verified",
            errors=["Network error"]
        )
        
        # 2. State serializes to a dictionary
        state_dict = full_state.model_dump()
        if not isinstance(state_dict, dict):
            log.error("❌ FAILED: model_dump() did not return a dict")
            all_passed = False
            
        # 5. TaskStatus serializes correctly (as string)
        if state_dict["task_status"] != "running":
            log.error("❌ FAILED: TaskStatus did not serialize to string, got: %s", type(state_dict["task_status"]))
            all_passed = False
            
        # 3. State serializes to JSON
        state_json = full_state.model_dump_json()
        if not isinstance(state_json, str):
            log.error("❌ FAILED: model_dump_json() did not return a string")
            all_passed = False
            
        # 4. State can be reconstructed from serialized data
        loaded_state_dict = json.loads(state_json)
        reconstructed_state = AgentState.model_validate(loaded_state_dict)
        
        if reconstructed_state.task_id != "task-999":
            log.error("❌ FAILED: Reconstruction task_id mismatch")
            all_passed = False
            
        if reconstructed_state.task_status != TaskStatus.RUNNING:
            log.error("❌ FAILED: Reconstruction task_status mismatch")
            all_passed = False
            
        if len(reconstructed_state.extracted_constraints) != 1:
            log.error("❌ FAILED: Reconstruction constraints mismatch")
            all_passed = False
            
        if reconstructed_state.pending_approval.action != "submit":
            log.error("❌ FAILED: Reconstruction pending_approval mismatch")
            all_passed = False
            
        log.info("✔ Serialization and reconstruction PASSED!")

    except Exception as exc:
        log.error("❌ Test suite crashed: %s", exc, exc_info=True)
        all_passed = False

    log.info("=" * 65)
    if all_passed:
        log.info("OVERALL RESULT: ALL AGENT STATE TESTS PASSED SUCCESSFULLY! 🎉")
    else:
        log.error("OVERALL RESULT: SOME TESTS FAILED.")
    log.info("=" * 65)
    return all_passed


if __name__ == "__main__":
    success = run_agent_state_tests()
    sys.exit(0 if success else 1)
