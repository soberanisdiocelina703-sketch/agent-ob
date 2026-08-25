# -*- coding: utf-8 -*-
"""原型 (prototype.html) 自检：渲染后正文 WCAG AA 对比度审计（含各视图/弹层/设置页）。
用法：python midterm/check-contrast.py
注意：本文件的对比度 JS 片段被 check-deck.py 复用（按赋值标记切分），勿改该标记行。"""
import pathlib
from playwright.sync_api import sync_playwright

BASE = pathlib.Path(__file__).parent
URL = (BASE / "prototype.html").resolve().as_uri()
PAGES = ["runs", "trace", "incidents", "workbench", "diff", "review", "gate", "checkup", "settings"]

JS = r"""
(scope) => {
  const lin = c => { c/=255; return c<=0.03928 ? c/12.92 : Math.pow((c+0.055)/1.055,2.4); };
  const L = ([r,g,b]) => 0.2126*lin(r)+0.7152*lin(g)+0.0722*lin(b);
  const parse = s => { const m=s.match(/[\d.]+/g); return m ? m.slice(0,3).map(Number) : null; };
  const alpha = s => { const m=s.match(/[\d.]+/g); return m && m.length>3 ? +m[3] : 1; };
  const mix = (fg,bg,a) => fg.map((c,i)=>c*a+bg[i]*(1-a));

  // 渐变背景：computed backgroundColor 为透明，需从 background-image 的色标取最亮/最暗端
  // （取对文字最不利的一端，即与文字亮度最接近的那个色标）
  const gradStops = cs => {
    const bi = cs.backgroundImage || '';
    if (!bi.includes('gradient')) return null;
    const m = bi.match(/rgba?\([^)]*\)/g);
    if (!m) return null;
    return m.map(s => { const c = parse(s), a = alpha(s); return a >= 1 ? c : null; })
            .filter(Boolean);
  };

  const bgOf = (el, fgL) => {
    let n = el, acc = [255,255,255];
    const stack = [];
    while (n && n.nodeType === 1) {
      const cs = getComputedStyle(n);
      const g = gradStops(cs);
      if (g && g.length) {
        // 最不利色标：与前景亮度差最小者
        let worst = g[0], wd = Infinity;
        g.forEach(c => { const d = Math.abs(L(c) - fgL); if (d < wd) { wd = d; worst = c; } });
        stack.push([worst, 1]);
        break;
      }
      const c = parse(cs.backgroundColor), a = alpha(cs.backgroundColor);
      if (c && a > 0) stack.push([c,a]);
      if (a >= 1) break;
      n = n.parentElement;
    }
    for (let i = stack.length-1; i >= 0; i--) acc = mix(stack[i][0], acc, stack[i][1]);
    return acc;
  };

  const out = [];
  document.querySelectorAll(scope + ' *').forEach(el => {
    const cs = getComputedStyle(el);
    if (cs.display==='none' || cs.visibility==='hidden' || +cs.opacity===0) return;
    if (el.closest('[aria-hidden="true"]')) return;   // 装饰性内容不适用
    const own = Array.from(el.childNodes).some(n => n.nodeType===3 && n.textContent.trim());
    if (!own) return;
    const fgc = parse(cs.color), fa = alpha(cs.color);
    if (!fgc) return;
    const bg = bgOf(el, L(fgc));
    const fg = fa < 1 ? mix(fgc, bg, fa) : fgc;
    const l1 = L(fg), l2 = L(bg);
    const ratio = (Math.max(l1,l2)+0.05)/(Math.min(l1,l2)+0.05);
    const px = parseFloat(cs.fontSize), wt = +cs.fontWeight || 400;
    const large = px >= 24 || (px >= 18.66 && wt >= 700);
    const need = large ? 3 : 4.5;
    if (ratio < need)
      out.push({r:+ratio.toFixed(2), need, px:+px.toFixed(1), wt,
                c:(el.className||'').toString().slice(0,30),
                t:(el.textContent||'').trim().slice(0,34)});
  });
  const seen=new Set();
  return out.filter(o=>{const k=o.c+o.r+o.px; if(seen.has(k))return false; seen.add(k); return true;})
            .sort((a,b)=>a.r-b.r);
}
"""

with sync_playwright() as p:
    try:
        b = p.chromium.launch(channel="msedge")
    except Exception:
        b = p.chromium.launch(channel="chrome")
    page = b.new_page(viewport={"width": 1440, "height": 900})
    grand = 0
    for pg in PAGES:
        page.goto(URL + "#" + pg)
        page.wait_for_timeout(1700 if pg == "workbench" else 260)
        r = page.evaluate(JS, "#pg-" + pg)
        grand += len(r)
        print("\n=== %s : %d fail ===" % (pg, len(r)))
        for x in r[:9]:
            print("   %.2f (need %s) %5.1fpx w%s  %-28s %s" % (x["r"], x["need"], x["px"], x["wt"], x["c"], x["t"]))
    print("\n=== total contrast failures: %d ===" % grand)
    b.close()
