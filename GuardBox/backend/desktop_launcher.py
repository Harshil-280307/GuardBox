"""
TRINETRA Desktop Launcher
Professional Windows desktop launcher wrapping the TRINETRA backend and React frontend.
Provides single-instance execution, silent backend startup, readiness polling,
and an embedded native window (Edge WebView2) with zero CMD console.
"""

import sys
import os
import time
import ctypes
import logging
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

# Resolve base directories
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
    sys.path.insert(0, str(BUNDLE_DIR))
else:
    BASE_DIR = Path(__file__).resolve().parent
    BUNDLE_DIR = BASE_DIR
    sys.path.insert(0, str(BASE_DIR))

# Ensure required directories exist
LOGS_DIR = BASE_DIR / "data" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
(BASE_DIR / "snapshots").mkdir(parents=True, exist_ok=True)

# Configure internal launcher logging
log_file = LOGS_DIR / "trinetra-launcher.log"
logging.basicConfig(
    filename=str(log_file),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("TRINETRA_LAUNCHER")

from app.config import settings


class SingleInstanceLock:
    """Windows Mutex lock preventing duplicate launcher instances."""
    def __init__(self, mutex_name: str = "Global\\TRINETRA_DESKTOP_LAUNCHER_MUTEX"):
        self.mutex_name = mutex_name
        self.mutex = None
        self.is_already_running = False

        if sys.platform == "win32":
            ERROR_ALREADY_EXISTS = 183
            self.mutex = ctypes.windll.kernel32.CreateMutexW(None, False, self.mutex_name)
            last_error = ctypes.windll.kernel32.GetLastError()
            if last_error == ERROR_ALREADY_EXISTS:
                self.is_already_running = True

    def release(self):
        if self.mutex and sys.platform == "win32":
            ctypes.windll.kernel32.CloseHandle(self.mutex)
            self.mutex = None


class BackendManager:
    """Manages silent background child process execution for the TRINETRA backend."""
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.child_proc = None
        self.we_started_backend = False

    def is_backend_ready(self) -> bool:
        """Checks if backend HTTP endpoint is accepting requests."""
        url = f"http://127.0.0.1:{self.port}/"
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return resp.status in (200, 301, 302, 307, 308, 404)
        except Exception:
            return False

    def start_if_needed(self) -> bool:
        """Starts backend child process silently if not already running."""
        if self.is_backend_ready():
            logger.info(f"Existing TRINETRA backend detected on port {self.port}.")
            self.we_started_backend = False
            return True

        logger.info(f"Starting silent backend process on {self.host}:{self.port}...")
        self.we_started_backend = True

        env = os.environ.copy()
        env["PORT"] = str(self.port)
        env["HOST"] = str(self.host)

        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--server", "--port", str(self.port), "--host", str(self.host)]
        else:
            cmd = [sys.executable, __file__, "--server", "--port", str(self.port), "--host", str(self.host)]

        backend_log_path = LOGS_DIR / "trinetra-backend.log"
        self.backend_log_file = open(backend_log_path, "a", encoding="utf-8")

        self.child_proc = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            env=env,
            stdout=self.backend_log_file,
            stderr=self.backend_log_file,
            creationflags=flags
        )
        logger.info(f"Backend child process spawned with PID {self.child_proc.pid}")

        # Poll for readiness (up to 20 seconds)
        start_time = time.time()
        while time.time() - start_time < 20.0:
            if self.is_backend_ready():
                elapsed = round(time.time() - start_time, 2)
                logger.info(f"TRINETRA backend became ready in {elapsed}s.")
                return True
            time.sleep(0.3)

        logger.error("Timed out waiting for TRINETRA backend startup.")
        return False

    def stop(self):
        """Terminates only the child backend process spawned by this launcher."""
        if self.we_started_backend and self.child_proc:
            logger.info(f"Stopping backend child process (PID {self.child_proc.pid})...")
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/PID", str(self.child_proc.pid), "/F", "/T"], capture_output=True)
                else:
                    self.child_proc.terminate()
            except Exception as e:
                logger.warning(f"Error terminating backend process: {e}")
            self.child_proc = None
            logger.info("Backend child process stopped.")
        
        if hasattr(self, "backend_log_file") and self.backend_log_file:
            try:
                self.backend_log_file.close()
            except Exception:
                pass


def show_error_dialog(message: str, title: str = "TRINETRA"):
    """Displays a native Windows message dialog on startup failure."""
    if sys.platform == "win32":
        MB_ICONERROR = 0x10
        MB_OK = 0x00
        ctypes.windll.user32.MessageBoxW(0, message, title, MB_ICONERROR | MB_OK)
    else:
        print(f"[{title}] {message}", file=sys.stderr)


def run_backend_server():
    """Entrypoint for the internal backend server process."""
    import uvicorn
    import multiprocessing
    multiprocessing.freeze_support()
    
    # Parse explicit host and port if passed
    port = settings.PORT
    host = settings.HOST
    for i, arg in enumerate(sys.argv):
        if arg == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
        elif arg == "--host" and i + 1 < len(sys.argv):
            host = sys.argv[i + 1]

    from app.main import app
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True
    )


def main():
    import multiprocessing
    multiprocessing.freeze_support()

    # If launched with --server, run uvicorn server directly
    if "--server" in sys.argv:
        run_backend_server()
        return

    logger.info("TRINETRA Desktop Launcher initializing...")

    # Determine runtime port
    port = settings.PORT
    host = settings.HOST

    # 1. Single Instance Check
    lock = SingleInstanceLock()
    if lock.is_already_running:
        logger.warning("Another TRINETRA launcher instance is already active.")
        sys.exit(0)

    # 2. Start Backend & Wait for Readiness
    backend_mgr = BackendManager(host=host, port=port)
    ready = backend_mgr.start_if_needed()

    if not ready:
        logger.error("Failed to start or connect to TRINETRA backend.")
        show_error_dialog(
            "Unable to start TRINETRA.\n\nPlease restart the application or contact support.",
            title="TRINETRA"
        )
        lock.release()
        sys.exit(1)

    # 3. Import and launch pywebview window
    try:
        import webview

        app_url = f"http://127.0.0.1:{port}/"
        logger.info(f"Opening native desktop window for {app_url}...")

        # Create native window using Edge Chromium WebView2
        window = webview.create_window(
            title="TRINETRA",
            url=app_url,
            width=1280,
            height=800,
            min_size=(960, 600),
            resizable=True,
            confirm_close=False
        )

        def on_closed():
            logger.info("Desktop window closed by user.")
            backend_mgr.stop()

        window.events.closed += on_closed

        # Start desktop message loop (blocking until window is closed)
        webview.start(gui="edgechromium", debug=False)

    except Exception as e:
        logger.exception(f"Desktop window runtime exception: {e}")
        show_error_dialog(
            "TRINETRA Desktop Window could not be displayed.\n\nPlease ensure Microsoft Edge WebView2 is installed.",
            title="TRINETRA"
        )
    finally:
        backend_mgr.stop()
        lock.release()
        logger.info("TRINETRA Launcher exiting cleanly.")


if __name__ == "__main__":
    main()
