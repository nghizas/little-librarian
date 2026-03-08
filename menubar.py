"""macOS menu bar app for Little Librarian server."""
import subprocess
import signal
import os

import rumps

APP_DIR = os.path.dirname(os.path.abspath(__file__))
HOST = "0.0.0.0"
PORT = "5151"


class LibrarianBarApp(rumps.App):
    def __init__(self):
        super().__init__("📚", quit_button=None)
        self.server_proc = None
        self.status_item = rumps.MenuItem("Status: Stopped", callback=None)
        self.toggle_item = rumps.MenuItem("Start Server", callback=self.toggle_server)
        self.menu = [
            self.status_item,
            None,
            self.toggle_item,
            rumps.MenuItem("Open in Browser", callback=self.open_browser),
            None,
            rumps.MenuItem("Quit", callback=self.quit_app),
        ]
        self.start_server()

    def start_server(self):
        try:
            self.server_proc = subprocess.Popen(
                [
                    os.path.join(APP_DIR, ".venv", "bin", "python"),
                    "-m", "flask", "run",
                    "--host", HOST,
                    "--port", PORT,
                ],
                cwd=APP_DIR,
                env={**os.environ, "FLASK_APP": "app.py"},
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self.status_item.title = f"Status: Running on :{PORT}"
            self.toggle_item.title = "Stop Server"
        except Exception as e:
            rumps.notification("Little Librarian", "Failed to start", str(e))

    def stop_server(self):
        if self.server_proc:
            try:
                os.killpg(os.getpgid(self.server_proc.pid), signal.SIGTERM)
                self.server_proc.wait(timeout=5)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                try:
                    os.killpg(os.getpgid(self.server_proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self.server_proc = None
        self.status_item.title = "Status: Stopped"
        self.toggle_item.title = "Start Server"

    def toggle_server(self, _):
        if self.server_proc and self.server_proc.poll() is None:
            self.stop_server()
        else:
            self.start_server()

    def open_browser(self, _):
        subprocess.Popen(["open", f"http://localhost:{PORT}"])

    def quit_app(self, _):
        self.stop_server()
        rumps.quit_application()

    @rumps.timer(5)
    def check_server(self, _):
        if self.server_proc and self.server_proc.poll() is not None:
            self.server_proc = None
            self.status_item.title = "Status: Stopped"
            self.toggle_item.title = "Start Server"


if __name__ == "__main__":
    LibrarianBarApp().run()
