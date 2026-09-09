from flask import Flask, render_template, request

from package.storage.database import initialise_database
from package.workflow.graph import workflow


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

    @app.route("/", methods=["GET", "POST"])
    def index():
        if request.method == "POST":
            research_question = request.form["research_question"].strip()

            if not research_question:
                return render_template(
                    "index.html",
                    error="Please enter a research question.",
                )

            result = workflow.invoke(
                {
                    "research_question": research_question,
                    "search_cycle": 0,
                }
            )

            return render_template(
                "report.html",
                report=result["final_report"],
                report_id=result.get("report_id"),
            )

        return render_template("index.html")

    return app