"""
TRINETRA Builder - CLI Utility
Command-line interface for automated customer packaging and validation testing.
"""

import sys
import json
import argparse
from pathlib import Path

# Add builder root to sys.path
BUILDER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BUILDER_DIR))

from app.schemas import CustomerBuildConfig
from app.validator import validate_customer_config
from app.build_engine import BuildEngine


def main():
    parser = argparse.ArgumentParser(description="TRINETRA Builder V1 CLI")
    parser.add_argument("--config", type=str, help="Path to customer build config JSON file")
    parser.add_argument("--validate-only", action="store_true", help="Only validate configuration without building")
    args = parser.parse_args()

    if not args.config:
        print("Error: --config <path_to_json> is required.")
        sys.exit(1)

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Config file not found at '{config_path}'")
        sys.exit(1)

    try:
        raw_data = json.loads(config_path.read_text(encoding="utf-8"))
        cfg = CustomerBuildConfig(**raw_data)
    except Exception as e:
        print(f"Error parsing configuration JSON: {e}")
        sys.exit(1)

    # Validate
    val = validate_customer_config(cfg)
    if not val.is_valid:
        print("\n[VALIDATION FAILED]")
        for err in val.errors:
            print(f"  • {err}")
        sys.exit(1)

    print("\n[VALIDATION PASSED]")
    print(f"Shop: {cfg.shop_name} ({cfg.shop_id})")
    print(f"Device: {cfg.device_name} ({cfg.device_id})")

    if args.validate_only:
        print("\nValidation only requested. Exiting.")
        sys.exit(0)

    print("\n=== EXECUTING BUILD ===")
    engine = BuildEngine(cfg)
    res = engine.execute_build()

    print("\n=== BUILD LOGS ===")
    for log in res.logs:
        print(log)

    print("\n=== BUILD SUMMARY ===")
    print(f"Status: {'SUCCESS' if res.is_success else 'FAILED'}")
    print(f"Windows Package: {res.windows_status}")
    print(f"Android APK: {res.android_status}")
    print(f"Security Scan: {res.security_scan_status}")
    print(f"Output Directory: {res.output_directory}")
    print(f"Artifacts: {len(res.artifacts)}")
    for a in res.artifacts:
        print(f"  • {a}")

    if not res.is_success:
        sys.exit(1)


if __name__ == "__main__":
    main()
