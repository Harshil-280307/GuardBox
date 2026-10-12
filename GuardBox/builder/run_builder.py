"""
TRINETRA Builder - Server Launcher
Runs the local builder server on port 8090.
"""

import sys
import os
from pathlib import Path
import uvicorn

# Ensure builder package is in sys.path
BUILDER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BUILDER_DIR))

if __name__ == "__main__":
    port = int(os.environ.get("BUILDER_PORT", "8090"))
    print("=" * 60)
    print(f"TRINETRA BUILDER V1 (Veronic Internal Tool)")
    print(f"Starting server on http://127.0.0.1:{port}")
    print("=" * 60)
    uvicorn.run("app.server:app", host="127.0.0.1", port=port, log_level="info", reload=False)
