import threading
import webbrowser

from package.storage.database import initialise_database
from package.web import create_app


app = create_app()


def open_browser() -> None:
    """
    Open the local web interface shortly after the Flask server starts.

    The small delay gives Flask enough time to begin listening before the
    browser attempts to load the page.
    """

    webbrowser.open("http://127.0.0.1:5000")


if __name__ == "__main__":
    initialise_database()

    threading.Timer(
        1.0,
        open_browser,
    ).start()

    app.run(
        debug=True,
        use_reloader=False,
    )