"""`npm run check` — lint + full test suite with per-module coverage gate."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")

STEPS = [
    ([PY, "-m", "ruff", "check", "server", "sdk", "agent", "scripts", "e2e"], "ruff lint"),
    ([PY, "-m", "pytest", "server/tests", "sdk/tests", "agent/tests", "e2e", "-q",
      "--cov=server/xunji", "--cov=sdk/xunji_sdk", "--cov-report=term",
      "--cov-fail-under=80"], "pytest + coverage(>=80%)"),
]


def main() -> int:
    for cmd, label in STEPS:
        print(f"\n=== {label} ===")
        if subprocess.call(cmd, cwd=ROOT) != 0:
            print(f"check FAILED at: {label}")
            return 1
    print("\ncheck: ALL GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
