# -*- coding: utf-8 -*-
"""答辩 deck 自检：逐页正文对比度 + 溢出（横向/纵向/裁切），覆盖 5 种投影分辨率。
用法：python midterm/check-deck.py  → 控制台清单 + _deck_report.txt"""
import pathlib
from playwright.sync_api import sync_playwright

BASE = pathlib.Path(__file__).parent
URL = (BASE / "index.html").resolve().as_uri()
CONTRAST = (BASE / "check-contrast.py").read_text(encoding="utf-8").split('JS = r"""')[1].split('"""')[0]

OVER = r"""
(scope) => {
  const out=[]; const range=document.createRange();
  const root=document.querySelector(scope); if(!root) return out;
  // slide 自身可滚动是设计（overflow:auto），只查内部元素
  root.querySelectorAll('*').forEach(el=>{
    const cs=getComputedStyle(el);
    if(cs.display==='none'||cs.visibility==='hidden')return;
    const sc=['auto','scroll'].includes(cs.overflowX)||['auto','scroll'].includes(cs.overflowY);
    if(!sc && el.scrollWidth>el.clientWidth+1 && el.clientWidth>0)
      out.push({k:'scrollW',c:(el.className||'').toString().slice(0,30),
                d:el.scrollWidth+'>'+el.clientWidth,t:(el.textContent||'').trim().slice(0,30)});
    if(cs.textOverflow==='ellipsis' && el.scrollWidth>el.clientWidth+1)
      out.push({k:'ellips',c:(el.className||'').toString().slice(0,30),
                d:el.scrollWidth+'>'+el.clientWidth,t:(el.textContent||'').trim().slice(0,30)});
    Array.from(el.childNodes).forEach(n=>{
      if(n.nodeType!==3||!n.textContent.trim())return;
      range.selectNodeContents(n); const box=el.getBoundingClientRect();
      Array.from(range.getClientRects()).forEach(r=>{
        if(r.width>0&&(r.right>box.right+1.5||r.left<box.left-1.5))
          out.push({k:'textOut',c:(el.className||'').toString().slice(0,30),
                    d:Math.round(r.right)+' vs '+Math.round(box.right),t:n.textContent.trim().slice(0,30)});
      });
    });
  });
  // 竖向溢出：slide 内容超出视口高度（答辩稿不应需要滚动）
  const s=root;
  if(s.scrollHeight > s.clientHeight+2)
    out.push({k:'vScroll',c:'slide',d:s.scrollHeight+'>'+s.clientHeight,t:'内容超出一屏'});
  const seen=new Set();
  return out.filter(o=>{const k=o.k+o.c+o.d;if(seen.has(k))return false;seen.add(k);return true;});
}
"""

AGG = {}
with sync_playwright() as p:
    try: b = p.chromium.launch(channel="msedge")
    except Exception: b = p.chromium.launch(channel="chrome")
    grand = 0
    for W, H in [(1920,1080), (1600,900), (1440,900), (1366,768), (1280,720)]:
        page = b.new_page(viewport={"width":W,"height":H})
        page.goto(URL); page.wait_for_timeout(700)
        n = page.evaluate("document.querySelectorAll('.slide').length")
        hits = []
        for i in range(n):
            page.evaluate("(i)=>goTo(i)", i)
            page.wait_for_timeout(340)
            sid = page.evaluate("(i)=>{const s=document.querySelectorAll('.slide')[i];return s.id||('#'+(i+1));}", i)
            sel = ".slide.active"
            for r in page.evaluate(OVER, sel): hits.append((i+1, sid, "OVER", r))
            for r in page.evaluate(CONTRAST, sel): hits.append((i+1, sid, "CONTRAST", r))
            # 整页是否一屏放得下（答辩投影不允许滚动）
            fit = page.evaluate("""()=>{const s=document.querySelector('.slide.active');
                return {v:s.scrollHeight-s.clientHeight, h:s.scrollWidth-s.clientWidth,
                        t:s.dataset.title||''};}""")
            if fit["v"] > 2 or fit["h"] > 2:
                hits.append((i+1, sid, "FIT", fit))
        for idx, sid, kind, r in hits:
            if kind == "FIT":
                key = ("FIT", idx)
                line = "p%-2s 一屏放不下  纵向溢出 %dpx / 横向 %dpx   %s" % (
                    idx, r["v"], r["h"], r["t"])
            elif kind == "OVER":
                key = ("OVER", idx, r["k"], r["c"], r["t"])
                line = "p%-2s %-8s %-22s %-14s %s" % (idx, r["k"], r["c"], r["d"], r["t"])
            else:
                key = ("C", idx, r["c"], r["t"])
                line = "p%-2s contrast %.2f (need %s) %5.1fpx w%-4s %-20s %s" % (
                    idx, r["r"], r["need"], r["px"], r["wt"], r["c"], r["t"])
            AGG.setdefault(key, [line, []])[1].append("%dx%d" % (W, H))
        grand += len(hits); page.close()
    b.close()

rep = ["# deck 去重问题清单（共 %d 项，%d 次命中）\n" % (len(AGG), grand)]
for key in sorted(AGG, key=lambda k: (k[1], k[0])):
    line, vps = AGG[key]
    rep.append("%-96s  @ %s" % (line, ",".join(vps)))
(BASE / "_deck_report.txt").write_text("\n".join(rep), encoding="utf-8")
print("wrote _deck_report.txt : %d distinct / %d hits" % (len(AGG), grand))
