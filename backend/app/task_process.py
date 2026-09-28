"""Isolated task entrypoint. Real adapters must replace this with verified work."""
import json
import sys


def main() -> int:
    # Never claim a task succeeded while adapters are absent.
    print(json.dumps({"code": "UNSUPPORTED_JOB", "message": "No production task adapter is installed"}), flush=True)
    return 65


if __name__ == "__main__":
    sys.exit(main())
