"""
TRINETRA Standalone Server Runner
Entrypoint for PyInstaller packaged Windows distribution.
"""
import sys
import multiprocessing
from pathlib import Path

# Add backend directory to sys.path
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
    sys.path.insert(0, str(BUNDLE_DIR))
else:
    BASE_DIR = Path(__file__).resolve().parent
    sys.path.insert(0, str(BASE_DIR))

import uvicorn
from app.config import settings
from app.main import app

def main():
    multiprocessing.freeze_support()
    print("==================================================")
    print(f"TRINETRA Security Server starting on {settings.HOST}:{settings.PORT}")
    print(f"Base Directory: {BASE_DIR}")
    print("==================================================")
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_level="info",
        access_log=True
    )

if __name__ == "__main__":
    main()
