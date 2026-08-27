"""Nodes covering resume parsing through profile validation."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from src.agents.profile_agent import ProfileAgent, ProfilePreferences
from src.graph.helpers import make_error, trace_event
from src.graph.state import HireLoopState
from src.llm.errors import RETRYABLE_ERROR_TYPES, HireLoopLLMError
from src.models.candidate import EmploymentPreferences
from src.models.enums import EmploymentType, WorkMode
from src.models.workflow_error import ErrorCategory
from src.models.workflow_status import WorkflowStatus
from src.services.resume_parser import parse_resume


def parse_resume_node(state: HireLoopState, config: RunnableConfig) -> dict:
    file_path = state.get("resume_file_path")
    if not file_path:
        error = make_error(
            "parse_resume", ErrorCategory.RESUME_PARSE_ERROR, "no resume file path was provided", retryable=False
        )
        return {"errors": [error], "workflow_status": WorkflowStatus.FAILED.value, "current_step": "parse_resume"}

    result = parse_resume(file_path)
    update: dict = {"resume_parse_result": result.model_dump(mode="json"), "current_step": "parse_resume"}

    if not result.success:
        error = make_error(
            "parse_resume", ErrorCategory.RESUME_PARSE_ERROR, result.error or "resume parsing failed", retryable=False
        )
        update["errors"] = [error]
        update["workflow_status"] = WorkflowStatus.FAILED.value
        return update

    update["decision_trace"] = [
        trace_event(
            "resume_parsing",
            "parse_resume",
            f"Resume parsed successfully: {result.character_count:,} characters extracted.",
            metadata={"warnings": len(result.warnings)},
        )
    ]
    update["workflow_status"] = WorkflowStatus.RUNNING.value
    return update


def _build_preferences(preferences_dict: dict) -> ProfilePreferences:
    employment_prefs = preferences_dict.get("employment_preferences") or {}
    return ProfilePreferences(
        target_roles=preferences_dict.get("target_roles", []),
        target_locations=preferences_dict.get("target_locations", []),
        preferred_work_modes=[WorkMode(m) for m in preferences_dict.get("preferred_work_modes", [])],
        employment_preferences=EmploymentPreferences(
            employment_types=[EmploymentType(t) for t in employment_prefs.get("employment_types", [])],
            minimum_salary=employment_prefs.get("minimum_salary"),
            notes=employment_prefs.get("notes"),
        ),
    )


def build_candidate_profile_node(state: HireLoopState, config: RunnableConfig) -> dict:
    parse_result = state.get("resume_parse_result")
    if not parse_result or not parse_result.get("success"):
        error = make_error(
            "build_candidate_profile",
            ErrorCategory.PROFILE_ERROR,
            "cannot build a candidate profile: resume was not successfully parsed",
            retryable=False,
        )
        return {
            "errors": [error],
            "workflow_status": WorkflowStatus.FAILED.value,
            "current_step": "build_candidate_profile",
        }

    llm_client = config["configurable"]["llm_client"]
    preferences = _build_preferences(state.get("preferences") or {})
    agent = ProfileAgent(llm_client)

    try:
        profile, validation = agent.build_profile(
            parse_result["extracted_text"], state["candidate_id"], preferences=preferences
        )
    except HireLoopLLMError as exc:
        error = make_error(
            "build_candidate_profile",
            ErrorCategory.LLM_ERROR,
            f"profile extraction failed: {exc.error_type.value}",
            retryable=exc.error_type in RETRYABLE_ERROR_TYPES,
            attempt=exc.attempts,
        )
        return {
            "errors": [error],
            "workflow_status": WorkflowStatus.FAILED.value,
            "current_step": "build_candidate_profile",
        }

    return {
        "candidate_profile": profile.model_dump(mode="json"),
        "profile_validation": validation.model_dump(mode="json"),
        "decision_trace": [
            trace_event(
                "profile",
                "build_candidate_profile",
                f"Candidate profile created: {len(profile.skills)} skills, "
                f"{len(profile.work_experience)} work experiences, {len(profile.projects)} projects.",
                metadata={"warnings": len(validation.warnings), "errors": len(validation.errors)},
            )
        ],
        "current_step": "build_candidate_profile",
    }


def validate_candidate_profile_node(state: HireLoopState, config: RunnableConfig) -> dict:
    validation = state.get("profile_validation") or {}
    errors = validation.get("errors", [])
    warnings = validation.get("warnings", [])

    if errors:
        message = f"Profile validation failed with {len(errors)} fatal error(s)."
    else:
        message = f"Profile validation completed with {len(warnings)} warning(s)."

    update: dict = {
        "decision_trace": [
            trace_event(
                "profile",
                "validate_candidate_profile",
                message,
                metadata={"errors": len(errors), "warnings": len(warnings)},
            )
        ],
        "current_step": "validate_candidate_profile",
    }

    if errors:
        update["errors"] = [
            make_error(
                "validate_candidate_profile",
                ErrorCategory.PROFILE_ERROR,
                f"{len(errors)} fatal profile validation error(s) prevent the workflow from continuing",
                retryable=False,
                details={"error_codes": errors[:10]},
            )
        ]
        update["workflow_status"] = WorkflowStatus.FAILED.value

    return update
