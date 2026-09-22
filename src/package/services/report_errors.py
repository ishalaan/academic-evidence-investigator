"""Safe diagnostic categories, without model output or provider exception text."""

import json
import sqlite3
import httpx
from pydantic import ValidationError

REPORT_ERRORS = {
    "report_grounding_invalid": "The report repeatedly overstated its supplied evidence. Review the evidence or retry the investigation.",
    "model_credits_required": "The model provider rejected the request because payment or inference credits are required (HTTP 402). Check the Hugging Face account billing and inference credits before retrying.",
    "model_timeout": "The model request timed out. Please try again shortly.",
    "model_connection": "The connection to the model service was interrupted. This may be a temporary service or network problem. Please try again shortly.",
    "model_certificate": "The model connection failed certificate verification. Check the system certificate configuration.",
    "model_authentication": "The model service rejected authentication or access. Check the configured token and model permissions.",
    "model_rate_limit": "The model service rate limit was reached. Wait a little before retrying.",
    "model_service_error": "The model service returned a server error. Please try again shortly.",
    "model_request_rejected": "The model service rejected the request. Check model availability and request limits.",
    "invalid_json": "The agent returned an incomplete or invalid JSON response. Please retry the investigation.",
    "invalid_structure": "The agent response did not match the required structure. Please retry the investigation.",
    "database_error": "The investigation could not read or save its database. Check database access and available disk space.",
    "workflow_stage_failed": "An unexpected application error stopped this stage. Use the run identifier to investigate.",
    "report_repetition": "The reporting model repeatedly returned duplicated passages. Please try again.",
    "report_invented_restriction": "The reporting model repeatedly invented a source restriction. Please try again.",
    "report_context_too_large": "The Reporter could not fit the minimum evidence and instructions within its request budget. Check the reporting configuration; shortening the research question may not resolve this error.",
    "report_model_unavailable": "The reporting model could not be reached. Please try again shortly.",
    "report_citations_invalid": "The report's citations could not be verified after retrying. Please try the investigation again.",
    "report_format_invalid": "The reporting model could not produce a complete report after retrying. Please try again.",
    "report_output_truncated": "The reporting model stopped before completing the report, even after retrying. Please try again.",
}


class ReportGenerationError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(REPORT_ERRORS[code])


def failure_details(error):
    code = "workflow_stage_failed"
    if isinstance(error, ReportGenerationError):
        if error.code == "report_model_unavailable" and isinstance(error.__context__, httpx.HTTPError):
            return failure_details(error.__context__)
        code = error.code
    elif getattr(getattr(error, "response", None), "status_code", None) is not None:
        status = error.response.status_code
        code = ("model_credits_required" if status == 402 else
                "model_authentication" if status in (401, 403) else
                "model_rate_limit" if status == 429 else
                "model_service_error" if status >= 500 else "model_request_rejected")
    elif isinstance(error, httpx.TimeoutException):
        code = "model_timeout"
    elif isinstance(error, httpx.ConnectError):
        code = "model_certificate" if "CERTIFICATE_VERIFY_FAILED" in str(error) else "model_connection"
    elif isinstance(error, httpx.HTTPError):
        code = "model_connection"
    elif isinstance(error, json.JSONDecodeError):
        code = "invalid_json"
    elif isinstance(error, ValidationError):
        code = "invalid_structure"
    elif isinstance(error, sqlite3.Error):
        code = "database_error"
    # Return a known message rather than str(error), which may contain request
    # details, model output or a remote response body.
    details = {"error_code": code, "message": REPORT_ERRORS[code]}
    reason = getattr(error, "validation_reason", None)
    if reason in {"missing_citation", "unknown_source", "author_year_format", "invalid_syntax"}:
        details["validation_reason"] = reason
    return details


def run_failure_message(run):
    """Render only allowlisted diagnostics; never expose raw exception text."""
    event = next((e for e in reversed(run["events"]) if e["action"] == "failed"), {})
    code = event.get("details", {}).get("error_code", "workflow_stage_failed")
    if code not in REPORT_ERRORS:
        code = "workflow_stage_failed"
    component = event.get("component", "Workflow")
    if component not in {"Planner", "Retrieval", "Processing", "Critic", "Reporter", "Workflow"}:
        component = "Workflow"
    reason = event.get("details", {}).get("validation_reason")
    explanation = {
        "missing_citation": " A paragraph or finding lacked a supporting citation.",
        "unknown_source": " The model cited a source identifier outside the supplied evidence.",
        "author_year_format": " The model used author-year text instead of traceable source identifiers.",
        "invalid_syntax": " A citation token had an invalid format.",
    }.get(reason, "")
    return f"{component} failed:{explanation} {REPORT_ERRORS[code]} Error code: {code}. Run: {run['id']}."
