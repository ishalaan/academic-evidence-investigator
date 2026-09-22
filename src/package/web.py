from threading import BoundedSemaphore, Thread

from flask import Flask, abort, jsonify, render_template, request, url_for

from package.storage.database import initialise_database, load_report
from package.storage.audit import create_run, get_run, record_event
from package.workflow.audit import STAGE_MESSAGES
from package.workflow.activity import activity_events
from package.workflow.graph import workflow
from package.processing.chunking import paper_key
from package.services.presentation import display_timestamp, plain_abstract
from package.services.references import reference_entries, report_references, source_url
from package.services.report_errors import REPORT_ERRORS, failure_details, run_failure_message


def create_app() -> Flask:
    """
    Create and configure the Flask application.

    Using an application factory keeps web configuration separate from the
    executable entry point and makes the Flask layer easier to test.
    """

    app = Flask(
        __name__,
        template_folder="../../templates",
        static_folder="../../static",
    )
    initialise_database()
    # Limit background investigations in this app instance so repeated clicks
    # cannot create an unbounded number of model requests and worker threads.
    available_workers = BoundedSemaphore(2)

    @app.context_processor
    def report_helpers():
        return {"reference_entries": reference_entries, "report_references": report_references,
                "paper_key": paper_key, "display_timestamp": display_timestamp, "plain_abstract": plain_abstract, "source_url": source_url, "activity_events": activity_events}

    def investigate(question, run_id):
        try:
            return workflow.invoke({"research_question": question, "search_cycle": 0, "run_id": run_id})
        except Exception as exc:
            run = get_run(run_id, include_events=False)
            if run["status"] != "failed":
                record_event(run_id, "Workflow", "failed", failure_details(exc),
                             stage="failed", status="failed")
            raise

    def background_investigation(question, run_id):
        try:
            investigate(question, run_id)
        except Exception:
            # Failure is persisted; never send exception text or prompts to the browser.
            pass
        finally:
            available_workers.release()

    @app.post("/runs")
    def start_run():
        question = request.form.get("research_question", "").strip()
        if not question:
            return jsonify(error="Please enter a research question."), 400
        if not available_workers.acquire(blocking=False):
            return jsonify(error="Investigations are busy. Please try again shortly."), 503
        try:
            run_id = create_run()
            Thread(target=background_investigation, args=(question, run_id), daemon=True).start()
        except Exception:
            available_workers.release()
            raise
        return jsonify(run_id=run_id, status_url=url_for("run_status", run_id=run_id)), 202

    @app.get("/runs/<run_id>/status")
    def run_status(run_id):
        run = get_run(run_id)
        if run is None:
            abort(404)
        # An explicit allowlist keeps audit details and model output out of progress.
        response = jsonify(
            run_id=run_id, status=run["status"], stage=run["stage"],
            message=(run_failure_message(run) if run["status"] == "failed"
                     else STAGE_MESSAGES.get(run["stage"], STAGE_MESSAGES["queued"])),
            events=activity_events(run["events"]),
            report_url=url_for("run_report", run_id=run_id) if run["status"] == "completed" else None,
        )
        # A cached polling response could leave the page showing an old stage
        # after the investigation has already completed.
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/runs/<run_id>/report")
    def run_report(run_id):
        run = get_run(run_id)
        if run is None:
            abort(404)
        if run["status"] != "completed":
            return "The investigation has not completed.", 409
        report = load_report(run["report_id"])
        if report is None:
            abort(404)
        return render_template("report.html", report=report, report_id=run["report_id"], audit=run)

    # Keep a normal form submission path for clients that do not use JavaScript.
    @app.route("/", methods=["GET", "POST"])
    def index():
        if request.method == "POST":
            research_question = request.form.get("research_question", "").strip()

            if not research_question:
                return render_template(
                    "index.html",
                    error="Please enter a research question.",
                )

            run_id = create_run()
            try:
                result = investigate(research_question, run_id)
            except Exception as exc:
                return render_template("index.html", error=run_failure_message(get_run(run_id))), 500

            return render_template(
                "report.html",
                report=result["final_report"],
                report_id=result.get("report_id"),
                audit=get_run(run_id),
            )

        return render_template("index.html")

    return app
