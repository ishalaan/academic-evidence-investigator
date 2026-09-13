"""Public activity messages derived only from known workflow event fields."""

from package.workflow.audit import STAGE_MESSAGES
from package.services.presentation import display_timestamp
import re


def activity_events(events):
    activity = []
    for event in events:
        component, action = event["component"], event["action"]
        details = event["details"]
        cycle = details.get("cycle")
        cycle = cycle if type(cycle) is int and cycle > 0 else None
        stage = component.lower()
        if stage not in ("planner", "retrieval", "processing", "critic", "reporter", "workflow"):
            continue
        section_names = {"summary": "the summary", "summary_answer": "the main answer", "summary_analysis": "the evidence analysis",
                         "summary_implications": "the practical implications", "findings": "the findings", "limitations": "the limitations"}
        rag_messages = {"fulltext_located": "Open-access full text located.",
            "fulltext_unavailable": "Accessible full text unavailable.", "pdf_extracted": "PDF text extracted with page references.",
            "pdf_failed": "PDF access or extraction failed; checking abstract fallback.",
            "pdf_downloaded": "PDF downloaded; extracting page-aware text.",
            "html_started": "Checking openly accessible HTML article text.",
            "metadata_checked": "Checked bibliographic metadata for a writing source.",
            "html_extracted": "HTML article text extracted with section and paragraph provenance.",
            "html_failed": "No usable HTML article body; checking abstract fallback.",
            "abstract_fallback": "Using abstract-only evidence.", "chunks_created": "Evidence chunks created.",
            "chunks_selected": "Relevant passages selected.", "semantic_completed": "Hybrid evidence retrieval completed."}
        if component == "Processing" and action in rag_messages:
            message = rag_messages[action]
            if action == "metadata_checked":
                message = {"verified":"Bibliographic metadata verified against its DOI record.",
                    "identity_mismatch":"DOI metadata did not match; retained the original reference metadata.",
                    "unavailable":"DOI metadata verification unavailable; retained the original reference metadata.",
                    "not_applicable":"No valid DOI for metadata verification; retained the original reference metadata."}.get(details.get('status'), message)
            failure_reasons = {
                "access_denied": "The host denied access", "not_found": "The document was not found",
                "rate_limited": "The host rate limit was reached", "http_error": "The host returned an HTTP error",
                "timeout": "The request timed out", "network_error": "The network request failed",
                "unsafe_url": "The URL failed public HTTPS validation", "access_error": "Full-text access failed",
                "download_time_limit": "The download time limit was reached", "pdf_size_limit": "The PDF size limit was reached",
                "html_size_limit": "The article metadata size limit was reached", "invalid_redirect": "The redirect was invalid",
                "redirect_limit": "The request/redirect limit was reached", "no_pdf_metadata": "The response was not a PDF and supplied no unambiguous PDF metadata",
                "not_pdf": "The PDF link returned a non-PDF response", "cross_host_pdf_metadata": "The PDF metadata pointed to another host",
                "password_required": "The PDF requires a password", "invalid_pdf": "The PDF could not be parsed",
                "page_limit": "The PDF page limit was reached", "no_usable_text": "The PDF contained no usable text"
            }
            failure_reasons.update({"html_access_blocked": "The HTML host requires access verification",
                "html_identity_mismatch": "The HTML page could not be matched to this paper",
                "html_no_article_body": "No recognised HTML article body was found",
                "html_insufficient_body": "The HTML page did not provide sufficient article-body text",
                "html_wrong_content_type": "The article URL did not return HTML"})
            if action in ("pdf_failed", "fulltext_unavailable", "html_failed") and details.get("reason") in failure_reasons:
                message = failure_reasons[details["reason"]] + "; checking abstract fallback."
            if action == "semantic_completed" and details.get("mode") == "lexical_fallback":
                message = "Local embeddings unavailable; used deterministic passage selection."
        elif action in ("section_started", "section_completed") and component == "Reporter":
            name = section_names.get(details.get("section"), "a report section")
            message = ("Developing " if action == "section_started" else "Completed ") + name + "."
        elif action == "started":
            stage = "replanning" if stage == "planner" and cycle and cycle > 1 else stage
            message = STAGE_MESSAGES.get(stage, "Starting investigation")
        elif action == "retrying" and component == "Reporter":
            message = "Checking report formatting and citations; generating a corrected report."
        elif action == "provider_paused" and component == "Retrieval":
            message = "Semantic Scholar request limit reached or access unavailable; using other sources for the rest of this investigation."
        elif action == "failed":
            message = "This stage could not be completed."
        elif action == "provider_failed" and component == "Retrieval":
            provider = details.get("provider")
            provider = provider if provider in ("Crossref", "Semantic Scholar") else "An academic source"
            reasons = {"rate_limit": "rate limit reached", "authentication": "access or authentication rejected",
                       "timeout": "request timed out", "service_error": "service error", "request_failed": "request failed"}
            reason = reasons.get(details.get("reason"))
            message = f"{provider} was unavailable. Continuing with available sources."
            if reason:
                message = f"{provider}: {reason}. Continuing with available sources."
            if details.get("disabled_for_run") is True:
                message += " No further Semantic Scholar requests will be made in this investigation."
        elif action == "completed":
            message = {
                "Planner": "Search plan prepared.",
                "Retrieval": "Academic sources retrieved.",
                "Processing": "Evidence validated, deduplicated and ranked.",
                "Critic": "Evidence sufficiency evaluated.",
                "Reporter": "Report generated and saved.",
                "Workflow": "Investigation complete.",
            }[component]
            if component == "Critic":
                if details.get("next_stage") == "planner":
                    message += " Further searching requested."
                elif details.get("cycle_limit_reached") is True:
                    message += " Search cycle limit reached; proceeding to the report."
                elif details.get("sufficient") is True:
                    message += " Evidence is sufficient for reporting."
        else:
            continue
        paper_id = details.get("paper_id")
        if isinstance(paper_id, str) and re.fullmatch(r"[a-f0-9]{20}", paper_id):
            title = details.get("paper_title")
            title = " ".join(title.split())[:120] if isinstance(title, str) else ""
            message += f" Paper {paper_id}" + (f" — {title}." if title else ".")
        activity.append({"id": event["id"], "timestamp": event["timestamp"], "display_timestamp": display_timestamp(event["timestamp"]),
                         "component": component, "action": action, "cycle": cycle,
                         "message": message})
    return activity
