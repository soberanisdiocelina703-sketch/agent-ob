"""`npm run demo` — start backend (8756) + web dev server (5173).

真实态前置条件：本机已安装并登录 Claude Code CLI（跑 demo-run 需要）；
未安装也可启动本命令后改跑 `npm run demo-offline` 灌入真实录制数据。
"""
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")


def main() -> int:
    procs = []
    env_server = {"XUNJI_DB": str(ROOT / "data" / "xunji.db"),
                  "PYTHONPATH": str(ROOT / "sdk")}
    import os

    procs.append(subprocess.Popen(
        [PY, "-m", "uvicorn", "xunji.api:app", "--port", "8756",
         "--app-dir", "server", "--log-level", "warning"],
        cwd=ROOT, env={**os.environ, **env_server}))
    print("后端: http://127.0.0.1:8756  (OpenAPI: /docs)")

    npm = shutil.which("npm")
    if npm and (ROOT / "web" / "node_modules").exists():
        procs.append(subprocess.Popen([npm, "run", "dev"], cwd=ROOT / "web"))
        print("前端: http://localhost:5173")
    else:
        print("前端未安装依赖：cd web && npm install && npm run dev")

    print("\n下一步：另开终端执行 `npm run demo-run`（真实态）或 "
          "`npm run demo-offline`（离线态灌数）。Ctrl+C 退出。")
    try:
        procs[0].wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
