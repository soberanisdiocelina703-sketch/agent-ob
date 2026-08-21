"""Capture DEMO screenshots via system Chrome (playwright channel, 无需下载浏览器).

前置：后端 8756 + 前端 5173 已启动且库内有演示数据。
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent
OUT = ROOT / "docs" / "assets"
OUT.mkdir(parents=True, exist_ok=True)
BASE = "http://localhost:5173"


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1360, "height": 900})
        # 截图禁用入场动画，避免定格在半透明帧（CSS 已适配 reduced-motion）
        page.emulate_media(reduced_motion="reduce")

        page.goto(f"{BASE}/#/runs")
        page.wait_for_selector("table tbody tr", timeout=15000)
        page.screenshot(path=str(OUT / "01-runs.png"))
        # 打开一条失败 Trace 的详情
        page.locator("table tbody tr").first.click()
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT / "02-trace-detail.png"), full_page=True)

        page.goto(f"{BASE}/#/incidents")
        page.wait_for_selector("table tbody tr", timeout=15000)
        page.screenshot(path=str(OUT / "03-incidents.png"))

        # 进入第一条事故的诊断工作台
        page.locator("a", has_text="诊断").first.click()
        page.wait_for_selector(".cand", timeout=15000)
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / "04-diagnosis.png"), full_page=True)

        page.goto(f"{BASE}/#/gate")
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / "05-gate.png"))

        browser.close()
    print(f"screenshots → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
