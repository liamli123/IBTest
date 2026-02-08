"""
Simple launcher for the IB demo scripts.

Usage:
  python run_demo.py --demo basic
  python run_demo.py --demo advanced
  python run_demo.py --demo uncovered
"""

from __future__ import annotations

import argparse
import importlib
import sys
from typing import List, Tuple


DEMO_MODULES = {
    "basic": "tws_api_demo",
    "advanced": "tws_api_advanced_demo",
    "uncovered": "tws_api_uncovered_demo",
    "valuation": "value_investor_model",
    "dashboard": "buffett_munger_dashboard",
}


def parse_args() -> Tuple[argparse.Namespace, List[str]]:
    parser = argparse.ArgumentParser(description="Run one IB demo by name.")
    parser.add_argument(
        "--demo",
        choices=sorted(DEMO_MODULES.keys()),
        default="basic",
        help="Which demo to run (default: basic).",
    )
    return parser.parse_known_args()


def main() -> int:
    args, passthrough_args = parse_args()
    module_name = DEMO_MODULES[args.demo]

    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        print(f"Failed to import '{module_name}': {exc}")
        return 1

    if not hasattr(module, "main"):
        print(f"Module '{module_name}' has no main() function.")
        return 1

    if args.demo in {"valuation", "dashboard"} and not passthrough_args:
        print("Valuation demo requires ticker args, for example:")
        print("  python run_demo.py --demo valuation -- --ticker AAPL")
        return 1

    sys.argv = [module_name, *passthrough_args]
    print(f"Launching demo: {args.demo} ({module_name}.main)")
    module.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
