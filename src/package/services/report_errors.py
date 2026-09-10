"""Safe diagnostic categories, without model output or provider exception text."""

REPORT_ERRORS = {
    "report_repetition": "The reporting model repeatedly returned duplicated passages. Please try again.",
    "report_invented_restriction": "The reporting model repeatedly invented a source restriction. Please try again.",
    "report_context_too_large": "The evidence is too large for this reporting request. Please use a shorter research question.",
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
    if isinstance(error, ReportGenerationError):
        return {"error_code": error.code, "message": REPORT_ERRORS[error.code]}
    return {"error_code": "workflow_stage_failed",
            "message": "Investigation could not be completed. Please try again."}
