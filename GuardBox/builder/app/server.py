"""
TRINETRA Builder - FastAPI Server
Exposes internal REST endpoints and serves the Builder Web UI on port 8090.
"""

import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

from .schemas import CustomerBuildConfig, ValidationResult, BuildExecutionResult
from .validator import validate_customer_config
from .build_engine import BuildEngine

app = FastAPI(
    title="TRINETRA Builder V1",
    description="Veronic Internal Tool for Customer Windows + Android Build Generation",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        loc = [str(x) for x in err.get("loc", []) if x != "body"]
        field = ".".join(loc)
        msg = err.get("msg", "Validation error")
        errors.append(f"{field}: {msg}" if field else msg)
    return JSONResponse(
        status_code=200,
        content={
            "is_valid": False,
            "errors": errors,
            "warnings": [],
            "sanitized_summary": {}
        }
    )

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


@app.get("/", response_class=HTMLResponse)
async def serve_builder_ui():
    """Serves the main single-page web UI."""
    index_file = TEMPLATES_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Builder UI template not found.")
    return HTMLResponse(content=index_file.read_text(encoding="utf-8"))


@app.get("/api/health")
async def health_check():
    """Basic health check and system info."""
    return {
        "status": "online",
        "tool": "TRINETRA Builder",
        "version": "1.0.0",
        "iscc_available": bool(BuildEngine.check_inno_setup())
    }


@app.post("/api/validate", response_model=ValidationResult)
async def validate_configuration(config: CustomerBuildConfig):
    """Validates full customer build configuration without exposing secrets."""
    return validate_customer_config(config)


@app.post("/api/build", response_model=BuildExecutionResult)
async def execute_customer_build(config: CustomerBuildConfig):
    """Executes customer build in isolated workspace."""
    engine = BuildEngine(config)
    result = engine.execute_build()
    return result
