from __future__ import annotations

import argparse
import json

from .bootstrap import get_bundle_info, validate


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect or validate bundled OpenUSD + MaterialX runtime")
    parser.add_argument("--validate", action="store_true", help="Run import and usdMtlx discovery checks")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()

    if args.validate:
        result = validate(verbose=not args.json)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        return

    info = get_bundle_info()
    payload = {
        "usd_root": str(info.usd_root),
        "python_paths": [str(p) for p in info.python_paths],
        "library_paths": [str(p) for p in info.library_paths],
        "plugin_paths": [str(p) for p in info.plugin_paths],
        "materialx_paths": [str(p) for p in info.materialx_paths],
        "platform": info.platform,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
