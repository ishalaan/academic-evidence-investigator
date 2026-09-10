"""Public activity messages derived only from known workflow event fields."""

from package.workflow.audit import STAGE_MESSAGES


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
        if action in ("section_started", "section_completed") and component == "Reporter":
            name = section_names.get(details.get("section"), "a report section")
            message = ("Developing " if action == "section_started" else "Completed ") + name + "."
        elif action == "started":
            stage = "replanning" if stage == "planner" and cycle and cycle > 1 else stage
            message = STAGE_MESSAGES.get(stage, "Starting investigation")
        elif action == "retrying" and component == "Reporter":
            message = "Checking report formatting and citations; generating a corrected report."
        elif action == "failed":
            message = "This stage could not be completed."
        elif action == "provider_failed" and component == "Retrieval":
            provider = details.get("provider")
            provider = provider if provider in ("Crossref", "Semantic Scholar") else "An academic source"
            message = f"{provider} was unavailable. Continuing with available sources."
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
        activity.append({"id": event["id"], "timestamp": event["timestamp"],
                         "component": component, "action": action, "cycle": cycle,
                         "message": message})
    return activity
