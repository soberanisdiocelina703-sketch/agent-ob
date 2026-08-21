"""Shared helpers for demo agent tools.

注入实现边界（提示词任务 3 硬约束）：注入只发生在这里——工具与数据层。
不修改 Claude Code，不改动任务提示词；XUNJI_INJECT 环境变量是唯一开关。
每个注入点在 DEMO.md 中标注。
"""
import json
import os
from datetime import date, timedelta
from pathlib import Path

AGENT_DIR = Path(__file__).parent.parent
DATA_DIR = AGENT_DIR / "data"


def workdir() -> Path:
    wd = Path(os.environ.get("XUNJI_WORKDIR", AGENT_DIR / "workdir"))
    wd.mkdir(parents=True, exist_ok=True)
    return wd


def inject_mode() -> str:
    return os.environ.get("XUNJI_INJECT", "none")


def today() -> str:
    return date.today().isoformat()


def yesterday() -> str:
    return (date.today() - timedelta(days=1)).isoformat()


def load_data(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def emit(envelope: dict, exit_code: int = 0) -> int:
    """Print the结构化信封 (single JSON line) — picked up by the xunji adapter."""
    print(json.dumps(envelope, ensure_ascii=False))
    return exit_code


def total_of(records: list[dict]) -> float:
    return round(sum(float(r["amount"]) for r in records), 2)
