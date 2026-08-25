/* 寻迹原型逻辑 —— 全部页面由数据层渲染，数据源见 data.js（唯一事实源 second-week/docs/00） */
'use strict';

/* ============ 全局错误边界 ============ */
window.onerror = function(msg, url, line, col, error) {
  console.error('Runtime error:', error);
  const main = document.querySelector('.main');
  if (main) {
    main.innerHTML = `<div class="empty" style="padding:var(--s8);color:var(--bad)">
      ${icon('alert','lg')}<b style="display:block;margin-top:var(--s3)">页面遇到错误</b>
      <div style="margin-top:var(--s2);font-size:12.5px;color:var(--text-2)">${esc(String(msg))}</div>
      <button class="btn pri" style="margin-top:var(--s4)" onclick="location.reload()">刷新页面</button>
    </div>`;
  }
  return true;
};

function safeRender(fn, fallback = '<div class="empty">加载失败，请刷新重试</div>') {
  try { return fn(); }
  catch (e) { console.error('Render error:', e); return fallback; }
}

/* ============ 工具 ============ */
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
const fm = code => FAILURE_TYPES.find(f => f.code === code) || {};
const trace = id => TRACES.find(t => t.id === id) || {};
const incident = id => INCIDENTS.find(i => i.id === id) || {};
const icon = (name, cls) => `<svg class="ic ${cls || ''}"><use href="#i-${name}"/></svg>`;

const GRADE = { sufficient:['t-ok','证据充分'], partial:['t-warn','有一定依据'], insufficient:['t-gray','证据不足'] };
const SRC   = { rule:['t-rule','规则判定'], diff:['t-brand','Diff 对照'], model:['t-model','模型推断'], 'rule+diff':['t-rule','规则 + Diff'] };
const STAGE = { 'T1 已实现':'t-ok', 'T1 部分实现':'t-warn', 'T2 设计中':'t-gray' };
const STEP_TAG = { RETRIEVAL:'t-rule', MEMORY:'t-warn', STATE:'t-warn', TOOL:'t-brand', LLM:'t-model', HANDOFF:'t-brand', AGENT:'t-brand', OUTPUT:'t-gray', ENTRY:'t-gray', GUARDRAIL:'t-rule', OTHER:'t-gray' };

function tag(cls, text){ return `<span class="tag ${cls}">${esc(text)}</span>`; }

/* ============ 数据层抽象 ============ */
const DataSource = {
  async fetchTraces(filters) {
    // 原型模式：返回硬编码数据
    return Promise.resolve(TRACES.filter(t =>
      (filters.exec === 'all' || t.exec === filters.exec) &&
      (filters.quality === 'all' || t.quality === filters.quality) &&
      (filters.run === 'all' || t.run === filters.run) &&
      (filters.ver === 'all' || t.ver === filters.ver)
    ));
    // 生产模式示例：
    // return fetch('/api/traces', { method:'POST', body:JSON.stringify(filters), headers:{'Content-Type':'application/json'} })
    //   .then(r => r.ok ? r.json() : Promise.reject(new Error(r.statusText)));
  },
  async fetchIncidents(filters) {
    return Promise.resolve(INCIDENTS.filter(i => {
      const age = filters.age === 'all' ? Infinity : parseInt(filters.age);
      const matchFm = filters.fm === 'all' || i.fm === filters.fm;
      const matchStep = filters.step === 'all' || i.faultType === filters.step;
      const matchReview = filters.review === 'all' || i.review === filters.review;
      const matchEvidence = filters.evidence === 'all' || i.evidence === filters.evidence;
      const matchQ = !filters.q || i.id.includes(filters.q) || i.run.includes(filters.q) || i.symptom.includes(filters.q);
      const matchAge = i.age <= age;
      return matchFm && matchStep && matchReview && matchEvidence && matchQ && matchAge;
    }));
  },
  async fetchDiagnosis(incidentId) {
    return Promise.resolve(DIAGNOSES[incidentId] || null);
  },
  // 预留其他端点
  async submitReview(incidentId, verdict, reason) {
    console.log('Submit review:', incidentId, verdict, reason);
    return Promise.resolve({ ok: true });
  }
};

/* ============ 辅助函数 ============ */
function debounce(fn, delay) {
  let timer;
  return function(...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

function announce(msg) {
  const region = document.getElementById('liveRegion');
  if (region) {
    region.textContent = msg;
    setTimeout(() => { region.textContent = ''; }, 1000);
  }
}

/* 只读展示字段：用文本块而非 <input readonly> —— 单行输入框无法换行，
   长值（事故 ID、快照、不变量）会被静默截断。这些值仅用于展示，不参与提交。 */
function roField(label, value, mono){
  return `<div class="fld">
    <div class="rolabel">${esc(label)}</div>
    <div class="ro ${mono ? 'mono' : ''}">${esc(value)}</div>
  </div>`;
}
function gradeTag(g){ const [c,t] = GRADE[g] || GRADE.insufficient; return tag(c,t); }
function srcTag(s){ const [c,t] = SRC[s] || SRC.model; return tag(c,t); }

let toastTimer;
function toast(msg){
  const el = $('toast');
  el.textContent = msg; el.className = 'show';
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = ''; }, 2800);
}

/* ============ 路由 ============ */
const PAGES = {
  runs:      { title:'运行记录',        render:renderRuns },
  trace:     { title:'Trace 详情',      render:renderTrace,     nav:'runs' },
  incidents: { title:'事故列表',        render:renderIncidents },
  workbench: { title:'诊断工作台',      render:renderWorkbench, nav:'incidents' },
  diff:      { title:'成功/失败 Diff',  render:renderDiff,      nav:'incidents' },
  review:    { title:'诊断复核',        render:renderReview,    nav:'incidents' },
  gate:      { title:'回归集与门禁',    render:renderGate },
  checkup:   { title:'接入与采集体检',  render:renderCheckup },
  settings:  { title:'设置',            render:renderSettings },
};

const state = {
  page:'incidents',
  incidentId:'INC-2026-0821-017',   // 主线：FM-07 检索排序漂移
  traceId:'TRC-2b98',
  baselineId:'TRC-2b98',
  diagLoaded:{},                     // 每个事故的模型候选是否已异步加载
  verdicts:{},                       // incidentId -> confirmed/excluded/insufficient
  cases:[],                          // 新生成的回归用例
  filters:{ inc:{ fm:'all', step:'all', q:'', age:168, review:'all', evidence:'all' },
            run:{ exec:'all', quality:'all', run:'all', ver:'all' } },
};

function go(page, fromHistory){
  if (!PAGES[page]) page = 'incidents';
  state.page = page;
  document.querySelectorAll('.page').forEach(el => el.classList.remove('show'));
  const host = $('pg-' + page);
  host.innerHTML = safeRender(() => PAGES[page].render());
  host.classList.add('show');
  const navKey = PAGES[page].nav || page;
  document.querySelectorAll('#nav a').forEach(a => a.classList.toggle('active', a.dataset.page === navKey));
  $('pageTitle').textContent = PAGES[page].title;
  if (!fromHistory && location.hash !== '#' + page) history.pushState({ page }, '', location.pathname + '#' + page);
  window.scrollTo(0, 0);
  enhanceKeyboard();
  announce(PAGES[page].title + '已加载');
  if (PAGES[page].after) PAGES[page].after();
}

/* ============ 运行记录 ============ */
function renderRuns(){
  const f = state.filters.run;
  const rows = TRACES.filter(t =>
    (f.exec === 'all' || t.exec === f.exec) &&
    (f.quality === 'all' || t.quality === f.quality) &&
    (f.run === 'all' || t.run === f.run) &&
    (f.ver === 'all' || t.ver === f.ver));
  const runNames = [...new Set(TRACES.map(t => t.run))];
  const vers = [...new Set(TRACES.map(t => t.ver))];
  const sel = (id, label, opts, cur) =>
    `<select id="${id}" aria-label="${esc(label)}" onchange="onRunFilter()">
       <option value="all">${esc(label)}：全部</option>
       ${opts.map(o => `<option value="${esc(o[0])}" ${cur === o[0] ? 'selected' : ''}>${esc(o[1])}</option>`).join('')}
     </select>`;

  return `
  <div class="grid g4 mb16">
    <div class="card bd"><div class="k">近 24 小时运行</div><div class="metric">1,284</div><div class="tiny muted">较昨日 +8.6%</div></div>
    <div class="card bd"><div class="k">执行成功率</div><div class="metric" style="color:var(--ok)">96.8%</div></div>
    <div class="card bd"><div class="k">质量评估覆盖率</div><div class="metric">72.4%</div><div class="tiny muted">通过 901 · 不通过 28 · 未评估 355</div></div>
    <div class="card bd"><div class="k">涉及事故</div><div class="metric" style="color:var(--bad)">${INCIDENTS.length}</div></div>
  </div>

  <div class="filters">
    ${sel('rfExec','执行状态',[['success','执行成功'],['failed','执行失败']],f.exec)}
    ${sel('rfQuality','质量结论',[['pass','通过'],['fail','不通过'],['unknown','未评估']],f.quality)}
    ${sel('rfRun','运行名称',runNames.map(r => [r,r]),f.run)}
    ${sel('rfVer','Agent 版本',vers.map(v => [v,v]),f.ver)}
    <button class="btn" onclick="resetRunFilter()">${icon('refresh')}清除筛选</button>
    <span class="tag t-gray" style="margin-left:auto">${rows.length} 条记录</span>
  </div>

  <div class="card">
    <table class="dt">
      <thead><tr><th>Trace ID</th><th>执行状态</th><th>质量结论</th><th>Judge</th><th>时间</th><th>运行名称</th><th>版本</th><th>步骤</th><th>耗时</th><th>关联事故</th></tr></thead>
      <tbody>${rows.map(t => {
        const inc = t.incident ? incident(t.incident) : null;
        const q = { pass:['t-ok','通过'], fail:['t-bad','不通过'], unknown:['t-gray','未评估'] }[t.quality];
        return `<tr class="click" onclick="openTrace('${t.id}')" role="button" tabindex="0">
          <td class="mono"><b>${esc(t.id)}</b>${t.baselineFor ? ' <span class="tag t-brand tiny">基线</span>' : ''}</td>
          <td><span class="rs ${t.exec}">${t.exec === 'success' ? '成功' : '失败'}</span></td>
          <td>${tag(q[0], q[1])}</td>
          <td class="mono small">${t.judge == null ? '—' : (t.judge < 0.6 ? `<span style="color:var(--bad);font-weight:700">${t.judge}</span>` : t.judge)}</td>
          <td class="small">${esc(t.at)}</td><td>${esc(t.run)}</td>
          <td class="mono small">${esc(t.ver)}</td><td>${t.steps}</td><td class="mono small">${esc(t.dur)}</td>
          <td>${inc ? `${tag('t-bad', t.incident.replace('INC-2026-',''))}<div class="tiny muted mt10">${esc(fm(inc.fm).name)}</div>` : '<span class="muted small">未立案</span>'}</td>
        </tr>`; }).join('')}
      </tbody>
    </table>
    ${rows.length ? '' : '<div class="empty">当前筛选条件下没有运行记录。</div>'}
  </div>`;
}

function onRunFilter(){
  const f = state.filters.run;
  f.exec = $('rfExec').value; f.quality = $('rfQuality').value;
  f.run = $('rfRun').value; f.ver = $('rfVer').value;
  debouncedRerender();
}
function resetRunFilter(){ state.filters.run = { exec:'all', quality:'all', run:'all', ver:'all' }; go('runs'); toast('已清除运行记录筛选'); }

const debouncedRerender = debounce(() => {
  go(state.page, true);
}, 300);
function openTrace(id){ state.traceId = id; go('trace'); }

/* ============ Trace 详情 ============ */
function renderTrace(){
  const t = trace(state.traceId);
  const spans = SPANS[t.id] || [];
  const inc = t.incident ? incident(t.incident) : null;
  const canBaseline = t.quality === 'pass';
  return `
  <div class="card mb16"><div class="bd">
    <div class="hero">
      <div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <span class="rs ${t.exec}">${t.exec === 'success' ? '执行成功' : '执行失败'}</span>
          ${tag({ pass:'t-ok', fail:'t-bad', unknown:'t-gray' }[t.quality], { pass:'质量通过', fail:'质量不通过', unknown:'质量未评估' }[t.quality])}
          ${t.judge != null ? tag(t.judge < 0.6 ? 't-bad' : 't-ok', 'Judge ' + t.judge) : ''}
        </div>
        <h2 style="font-size:20px;margin:8px 0 4px">${esc(t.run)} · ${esc(t.id)}</h2>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn" onclick="go('runs')">${icon('arrow-left')}返回运行记录</button>
        ${inc ? `<button class="btn pri" onclick="openIncident('${t.incident}')">${icon('alert')}查看关联事故</button>` : ''}
        <button class="btn ${canBaseline ? 'pri' : 'disabled'}" ${canBaseline ? '' : 'disabled'}
          onclick="setBaseline('${t.id}')">${icon('swap')}设为对比基线</button>
      </div>
    </div>
    <div class="facts">
      <div><div class="k">Trace ID</div><div class="v mono">${esc(t.id)}</div></div>
      <div><div class="k">开始时间</div><div class="v">${esc(t.at)}</div></div>
      <div><div class="k">Agent 版本</div><div class="v mono">${esc(t.ver)}</div></div>
      <div><div class="k">总耗时</div><div class="v mono">${esc(t.dur)}</div></div>
      <div><div class="k">步骤数</div><div class="v">${t.steps}</div></div>
    </div>
  </div></div>
  ${renderTree(spans, null, inc)}`;
}

function renderTree(spans, highlight, inc){
  return `<div class="card">
    <div class="hd"><b>完整 Trace</b><span class="small muted">共 ${spans.length} 步</span>
      ${inc ? `<span class="sp">${tag('t-bad','首故障 ' + inc.faultStep)}${tag('t-warn','症状 ' + inc.symptomStep.split(' ')[0])}</span>` : ''}</div>
    <div class="bd tree" role="tree" aria-label="调用链路">${spans.map((s, idx) => {
      const cls = s.st === 'fault' ? 'fault' : s.st === 'symptom' ? 'symptom' : s.st === 'bad' ? 'bad' : s.st === 'warn' ? 'warn' : '';
      return `<div class="trow ${cls} ${highlight === s.id ? 'hl' : ''}" id="span-${s.id}" role="treeitem" aria-level="${s.ind + 1}" aria-setsize="${spans.length}" aria-posinset="${idx + 1}">
        <span class="ind" aria-hidden="true">${'│&nbsp;&nbsp;'.repeat(Math.max(0, s.ind - 1))}${s.ind ? '├─' : ''}</span>
        <span class="mono muted sid">${esc(s.id)}</span>
        ${tag(STEP_TAG[s.type] || 't-gray', s.type)}
        <span class="sname">${esc(s.name)}
          ${s.note ? `<div class="tiny ${s.st === 'fault' ? 'fault-note' : 'muted'}">${s.st === 'fault' ? '⚑ ' : ''}${esc(s.note)}</div>` : ''}</span>
        <span class="dur mono">${esc(s.dur)}</span>
      </div>`; }).join('')}</div>
  </div>`;
}

function setBaseline(id){
  state.baselineId = id;
  toast('已将 ' + id + ' 设为本次成功/失败对比基线');
}

/* ============ 事故列表 ============ */
function renderIncidents(){
  const f = state.filters.inc;
  const rows = INCIDENTS.filter(i =>
    (f.fm === 'all' || i.fm === f.fm) &&
    (f.step === 'all' || i.faultType === f.step) &&
    (!f.q || (i.faultName + i.symptom + i.id).toLowerCase().includes(f.q.toLowerCase())) &&
    i.age <= f.age &&
    (f.review === 'all' || (state.verdicts[i.id] ? 'confirmed' : i.review) === f.review) &&
    (f.evidence === 'all' || i.evidence === f.evidence));

  const heroCards = FAILURE_TYPES.filter(t => t.hero).concat(FAILURE_TYPES.filter(t => !t.hero).slice(0, 1));

  return `
  <div class="grid g4 mb16">
    ${heroCards.map(t => `
      <div class="card cluster ${f.fm === t.code ? 'selected' : ''}" onclick="selectCluster('${t.code}')" role="button" tabindex="0">
        <div class="ch"><b>${esc(t.name)}</b>${tag(t.hero ? 't-bad' : 't-gray', t.code)}</div>
        <div class="cnt" style="color:${t.hero ? 'var(--bad)' : 'var(--muted)'}">${t.count}<span class="tiny muted"> 起 / 24h</span></div>
        <div class="tiny" style="color:${t.trend > 0 ? 'var(--bad)' : t.trend < 0 ? 'var(--ok)' : 'var(--muted)'}">
          ${t.trend > 0 ? '▲ +' + t.trend : t.trend < 0 ? '▼ ' + t.trend : '— 持平'} · 影响 ${t.sessions} 个会话</div>
        <div class="cmeta">
          <div>低成本解法：<b style="color:${t.cheapFix === '无' ? 'var(--bad)' : 'var(--ink2)'}">${esc(t.cheapFix)}</b></div>
          <div class="mt10">${tag(STAGE[t.stage], t.stage)}</div>
        </div>
      </div>`).join('')}
  </div>

  <div class="filters">
    <select id="ifFm" aria-label="故障类型" onchange="onIncFilter()">
      <option value="all">故障类型：全部（九类）</option>
      ${FAILURE_TYPES.map(t => `<option value="${t.code}" ${f.fm === t.code ? 'selected' : ''}>${t.code} ${esc(t.name)}</option>`).join('')}
    </select>
    <select id="ifStep" aria-label="步骤类型" onchange="onIncFilter()">
      <option value="all">步骤类型：全部</option>
      ${['RETRIEVAL','STATE','MEMORY','TOOL','LLM','HANDOFF','AGENT'].map(s => `<option value="${s}" ${f.step === s ? 'selected' : ''}>${s}</option>`).join('')}
    </select>
    <input id="ifQ" type="search" aria-label="搜索事故或步骤" placeholder="搜索：事故 ID / 步骤 / 症状" value="${esc(f.q)}" oninput="onIncFilter()">
    <select id="ifAge" aria-label="时间范围" onchange="onIncFilter()">
      <option value="24" ${f.age === 24 ? 'selected' : ''}>时间：近 24 小时</option>
      <option value="168" ${f.age === 168 ? 'selected' : ''}>近 7 天</option>
      <option value="720" ${f.age === 720 ? 'selected' : ''}>近 30 天</option>
    </select>
    <select id="ifReview" aria-label="复核状态" onchange="onIncFilter()">
      <option value="all">复核状态：全部</option>
      <option value="pending" ${f.review === 'pending' ? 'selected' : ''}>待复核</option>
      <option value="confirmed" ${f.review === 'confirmed' ? 'selected' : ''}>已确认</option>
    </select>
    <select id="ifEvidence" aria-label="证据等级" onchange="onIncFilter()">
      <option value="all">证据等级：全部</option>
      <option value="sufficient" ${f.evidence === 'sufficient' ? 'selected' : ''}>证据充分</option>
      <option value="partial" ${f.evidence === 'partial' ? 'selected' : ''}>有一定依据</option>
    </select>
    <button class="btn" onclick="resetIncFilter()">${icon('refresh')}清除筛选</button>
  </div>

  <div class="card">
    <div class="hd"><b>事故列表</b><span class="tag t-gray">${rows.length} 条记录</span></div>
    <table class="dt">
      <thead><tr><th>事故 ID</th><th>故障类型</th><th>时间</th><th>运行</th><th>症状</th><th>首故障步骤</th><th>距离</th><th>影响</th><th>证据等级</th><th>复核状态</th></tr></thead>
      <tbody>${rows.map(i => {
        const t = fm(i.fm);
        const d = DIAGNOSES[i.id];
        const gap = d ? d.gap : null;
        const rev = state.verdicts[i.id] || i.review;
        const revTag = rev === 'confirmed' ? tag('t-ok','已确认') : rev === 'excluded' ? tag('t-gray','已排除') : tag('t-warn','待复核');
        return `<tr class="click ${i.hero ? 'hero-row' : ''}" onclick="openIncident('${i.id}')" role="button" tabindex="0">
          <td class="mono"><b>${esc(i.id)}</b></td>
          <td>${tag(i.hero ? 't-bad' : 't-gray', i.fm)}<div class="tiny muted mt10">${esc(t.name)}</div></td>
          <td class="small">${esc(i.at)}</td>
          <td class="small">${esc(i.run)}<div class="tiny mono muted">${esc(i.trace)}</div></td>
          <td class="small">${esc(i.symptom)}<div class="tiny muted mt10">${esc(i.symptomStep)}</div></td>
          <td>${tag(STEP_TAG[i.faultType] || 't-gray', i.faultStep + ' ' + i.faultType)}<div class="tiny mt10">${esc(i.faultName)}</div></td>
          <td class="small">${gap ? `<b style="color:var(--bad)">早 ${gap} 步</b>` : '<span class="muted">—</span>'}</td>
          <td class="small">${i.sessions} 会话</td>
          <td>${gradeTag(i.evidence)}</td>
          <td>${revTag}</td></tr>`;
      }).join('')}</tbody>
    </table>
    ${rows.length ? '' : '<div class="empty">当前筛选条件下没有事故记录。<button class="btn" onclick="resetIncFilter()">清除筛选</button></div>'}
  </div>`;
}

function onIncFilter(){
  const f = state.filters.inc;
  f.fm = $('ifFm').value; f.step = $('ifStep').value; f.q = $('ifQ').value;
  f.age = Number($('ifAge').value); f.review = $('ifReview').value; f.evidence = $('ifEvidence').value;
  const pos = $('ifQ') === document.activeElement, caret = pos ? $('ifQ').selectionStart : null;
  debouncedIncRerender(pos, caret);
}

const debouncedIncRerender = debounce((keepFocus, caret) => {
  go('incidents', true);
  if (keepFocus){ const el = $('ifQ'); if(el){el.focus(); el.setSelectionRange(caret, caret);} }
}, 300);
function resetIncFilter(){
  state.filters.inc = { fm:'all', step:'all', q:'', age:168, review:'all', evidence:'all' };
  go('incidents', true); toast('已清除全部筛选条件');
}
function selectCluster(code){
  state.filters.inc.fm = state.filters.inc.fm === code ? 'all' : code;
  go('incidents', true);
  toast(state.filters.inc.fm === 'all' ? '已取消簇筛选' : '已按 ' + code + ' ' + fm(code).name + ' 筛选');
}

function openIncident(id){
  state.incidentId = id;
  const d = DIFFS[id];
  if (d) state.baselineId = d.baseline;
  go('workbench');
}

/* ============ 诊断工作台 ============ */
function renderWorkbench(){
  const i = incident(state.incidentId), d = DIAGNOSES[state.incidentId], t = fm(i.fm);
  if (!d) return `<div class="card bd">该事故暂无诊断结果。<button class="btn" onclick="go('incidents')">返回事故列表</button></div>`;

  const loaded = state.diagLoaded[state.incidentId];
  const ruleCands = d.candidates.filter(c => c.source !== 'model');
  const modelCands = d.candidates.filter(c => c.source === 'model');

  return `
  <div class="card mb16">
    <div class="bd">
      <div class="wbhead">
        <div>
          <div class="mb10">${tag('t-bad', i.fm)} ${tag(STAGE[t.stage], t.stage)} ${gradeTag(i.evidence)}
            <span class="tiny muted" style="margin-left:6px">规则包 ${esc(d.rulePack)} · 模型 ${esc(d.model)}</span></div>
          <h2 class="mono">${esc(i.id)}</h2>
          <div class="small muted">${esc(t.name)} · ${esc(i.run)} · ${esc(i.at)} · 影响 ${i.sessions} 个会话</div>
        </div>
        <div class="wbact">
          <button class="btn" onclick="go('incidents')">${icon('arrow-left')}返回列表</button>
          <button class="btn" onclick="go('diff')">${icon('swap')}成功/失败 Diff</button>
          <button class="btn pri" onclick="go('review')">${icon('check')}进入诊断复核</button>
        </div>
      </div>
    </div>
  </div>

  <div class="grid g2 mb16">
    <div class="card sym">
      <div class="hd"><b>症状</b></div>
      <div class="bd">
        <div class="symrow"><div class="k">症状步骤</div><div class="v mono">${esc(i.symptomStep)}</div></div>
        <div class="symrow"><div class="k">现象</div><div class="v">${esc(i.symptom)}</div></div>
        <div class="symrow"><div class="k">失败 Trace</div><div class="v mono click" onclick="openTrace('${i.trace}')" role="button" tabindex="0">${esc(i.trace)}</div></div>
        <div class="symrow"><div class="k">执行状态</div><div class="v">${trace(i.trace).exec === 'success'
          ? '<span class="tag t-ok">全部步骤成功</span>'
          : '<span class="tag t-bad">执行失败</span>'}</div></div>
      </div>
    </div>
    <div class="card fault">
      <div class="hd"><b>首故障点</b>${tag('t-bad','早 ' + d.gap + ' 步')}</div>
      <div class="bd">
        <div class="symrow"><div class="k">首故障步骤</div><div class="v mono">${esc(i.faultStep)} ${esc(i.faultType)}</div></div>
        <div class="symrow"><div class="k">步骤名称</div><div class="v">${esc(i.faultName)}</div></div>
        <div class="symrow"><div class="k">与症状距离</div><div class="v" style="color:var(--bad)">相隔 ${d.gap} 个步骤</div></div>
      </div>
    </div>
  </div>

  <div class="card mb16">
    <div class="hd"><b>因果传播路径</b></div>
    <div class="bd">
      <div class="causal">
        ${d.causal.map((step, idx) => {
          const isFirst = idx === 0, isLast = idx === d.causal.length - 1;
          return `<div class="cnode ${isFirst ? 'first' : ''} ${isLast ? 'last' : ''}">
            <div class="cbadge">${isFirst ? icon('flag') : isLast ? icon('alert') : idx + 1}</div>
            <div class="ctext">${esc(step)}</div>
          </div>${isLast ? '' : `<div class="carrow">${icon('arrow-right')}</div>`}`;
        }).join('')}
      </div>
    </div>
  </div>

  <div class="card">
    <div class="hd"><b>候选原因（Top-${d.candidates.length}）</b>
      <div class="sp">
        ${loaded ? tag('t-model','模型候选已加载') : tag('t-gray','模型语义分析中…')}
      </div>
    </div>
    <div class="bd">
      ${ruleCands.map(c => candidateCard(c)).join('')}
      ${loaded ? modelCands.map(c => candidateCard(c)).join('')
               : `<div class="diagload" id="diagload">${icon('refresh','spin')}<span>模型语义分析中…</span></div>`}
    </div>
  </div>`;
}
PAGES.workbench.after = function(){
  const id = state.incidentId;
  if (state.diagLoaded[id]) return;
  setTimeout(() => {
    state.diagLoaded[id] = true;
    if (state.page === 'workbench') { go('workbench', true); toast('模型语义候选已追加（含反证与替代解释）'); }
  }, 1100);
};

function candidateCard(c){
  const open = c.rank === 1;
  return `
  <div class="cand ${c.locked ? 'locked' : ''}" id="cand-${c.rank}">
    <div class="candhd" onclick="toggleCand(${c.rank})" role="button" tabindex="0" aria-expanded="${open}">
      <div class="rank">${c.rank}</div>
      <div class="candtitle">
        <div class="ct">${esc(c.title)}</div>
        <div class="cmetarow">${srcTag(c.source)} ${gradeTag(c.grade)}
          ${c.faultStep ? tag('t-brand','首故障点 ' + c.faultStep) : ''}
          <span class="tiny muted">支持证据 ${c.support.length} 条 · 反证 ${c.refute.length} 条</span></div>
      </div>
      <div class="candtoggle">${icon('arrow-right')}</div>
    </div>
    <div class="candbody" ${open ? '' : 'hidden'} id="candbody-${c.rank}">
      ${c.locked ? `<div class="lockbox">${icon('lock')}<div class="small">${esc(c.lockReason)}</div></div>` : ''}
      <div class="evgroup">
        <div class="evhd support">${icon('check')}支持证据（${c.support.length}）</div>
        ${c.support.map(e => evidenceCard(e, 'support')).join('')}
      </div>
      ${c.refute.length ? `
      <div class="evgroup">
        <div class="evhd refute">${icon('alert')}反面证据与替代解释（${c.refute.length}）</div>
        ${c.refute.map(e => evidenceCard(e, 'refute')).join('')}
      </div>` : ''}
      ${c.locked ? '' : `
      <div class="candfoot">
        <button class="btn" onclick="go('diff')">${icon('swap')}用 Diff 验证该候选</button>
        <button class="btn pri" onclick="go('review')">${icon('check')}对该候选做复核结论</button>
      </div>`}
    </div>
  </div>`;
}

function evidenceCard(e, side){
  return `
  <div class="evi ${side}">
    <div class="evid mono">${esc(e.id)}</div>
    <div class="evbody">
      <div class="evmeta">${tag(side === 'support' ? 't-rule' : 't-warn', e.kind)}
        ${e.from ? `<span class="tiny muted">来源：${esc(e.from)}</span>` : ''}
        ${e.span && e.span !== '—' ? `<button class="evjump" onclick="jumpToSpan('${esc(e.span)}')">${icon('target')}跳转原始事件 ${esc(e.span)}</button>` : ''}</div>
      <div class="evtext">${esc(e.text)}</div>
      ${e.impact ? `<div class="evimpact">${esc(e.impact)}</div>` : ''}
    </div>
  </div>`;
}

function toggleCand(rank){
  const body = $('candbody-' + rank), hd = document.querySelector(`#cand-${rank} .candhd`);
  const willOpen = body.hasAttribute('hidden');
  if (willOpen) body.removeAttribute('hidden'); else body.setAttribute('hidden','');
  $('cand-' + rank).classList.toggle('open', willOpen);
  hd.setAttribute('aria-expanded', String(willOpen));
}

function jumpToSpan(spanId){
  state.traceId = incident(state.incidentId).trace;
  state.highlightSpan = spanId;
  go('trace');
  toast('已跳转到原始事件 ' + spanId + '，该步骤保持高亮');
}

/* ============ 成功/失败 Diff ============ */
function renderDiff(){
  const i = incident(state.incidentId), d = DIFFS[state.incidentId];
  if (!d) return `<div class="card bd">
    <div class="lockbox">${icon('lock')}<div class="small">该事故暂无可用对比基线</div></div>
    <button class="btn mt16" onclick="go('workbench')">${icon('arrow-left')}返回诊断工作台</button></div>`;

  return `
  <div class="card mb16"><div class="bd">
    <div class="wbhead">
      <div>
        <div class="mb10">${tag('t-bad', i.fm)} <span class="tiny muted">首个分歧点 ${esc(d.firstDiv)}</span></div>
        <h2>成功 / 失败三维对比</h2>
        <div class="small muted">失败链 <b class="mono">${esc(d.failed)}</b> vs 基线 <b class="mono">${esc(d.baseline)}</b>
          · ${d.dims.filter(x => !x.same).length} 个维度存在差异</div>
      </div>
      <div class="wbact">
        <button class="btn" onclick="go('workbench')">${icon('arrow-left')}返回工作台</button>
        <button class="btn pri" onclick="go('review')">${icon('check')}进入诊断复核</button>
      </div>
    </div>
  </div></div>

  <div class="diffhead mb16">
    <div class="dcol base"><div class="k">对比基线（成功）</div><div class="v mono">${esc(d.baseline)}</div>
      <div class="tiny muted">${esc(trace(d.baseline).at)} · Judge ${trace(d.baseline).judge ?? '—'} · 质量通过</div></div>
    <div class="dcol fail"><div class="k">失败链</div><div class="v mono">${esc(d.failed)}</div>
      <div class="tiny muted">${esc(trace(d.failed).at)} · Judge ${trace(d.failed).judge ?? '—'} · 质量不通过</div></div>
  </div>

  ${d.dims.map((dim, idx) => `
    <div class="card dimcard mb16">
      <div class="hd">
        <b>${esc(dim.dim)}</b>
        <span class="tag ${dim.same ? 't-ok' : 't-bad'}">${dim.same ? '一致' : '存在差异'}</span>
        <span class="tiny muted mono">${esc(dim.step)}</span>
        ${dim.step.startsWith(d.firstDiv) ? tag('t-warn','首个分歧点') : ''}
      </div>
      <div class="dimbody">
        <div class="dimcell base"><div class="k">基线</div><div class="small">${esc(dim.base)}</div></div>
        <div class="dimcell fail"><div class="k">失败链</div><div class="small">${esc(dim.fail)}</div></div>
      </div>
      ${dim.keys && dim.keys.length ? `
      <table class="dt keydiff">
        <thead><tr><th>字段</th><th>基线值</th><th>失败链值</th></tr></thead>
        <tbody>${dim.keys.map(k => `<tr>
          <td class="mono small">${esc(k.k)}</td>
          <td class="mono small basecell">${esc(k.b)}</td>
          <td class="mono small failcell">${esc(k.f)}</td></tr>`).join('')}</tbody>
      </table>` : ''}
    </div>`).join('')}`;
}

/* ============ 诊断复核 ============ */
function renderReview(){
  const i = incident(state.incidentId), d = DIAGNOSES[state.incidentId];
  if (!d) return `<div class="card bd">该事故暂无诊断结果。<button class="btn" onclick="go('incidents')">返回列表</button></div>`;
  const c = d.candidates[0];
  const verdict = state.verdicts[state.incidentId];

  return `
  <div class="card mb16"><div class="bd">
    <div class="wbhead">
      <div>
        <div class="mb10">${tag('t-bad', i.fm)} ${srcTag(c.source)} ${gradeTag(c.grade)}</div>
        <h2>诊断复核 · 候选原因 1</h2>
        <div class="small muted">${esc(i.id)} · 复核人 李工 · 支持证据 ${c.support.length} 条 vs 反面证据 ${c.refute.length} 条</div>
      </div>
      <div class="wbact">
        <button class="btn" onclick="go('workbench')">${icon('arrow-left')}返回工作台</button>
        <button class="btn" onclick="go('diff')">${icon('swap')}再看 Diff</button>
      </div>
    </div>
  </div></div>

  <div class="card mb16"><div class="hd"><b>待复核的结论</b></div>
    <div class="bd"><div class="claim">${esc(c.title)}</div>
      <div class="small muted mt10">首故障点 <b class="mono">${esc(c.faultStep || '—')}</b> · 症状点 <b class="mono">${esc(i.symptomStep)}</b> · 相隔 ${d.gap} 个步骤</div></div>
  </div>

  <div class="revcols mb16">
    <div class="card revcol support">
      <div class="hd"><b>${icon('check')}支持证据（${c.support.length}）</b></div>
      <div class="bd">${c.support.map(e => `
        <div class="revitem">
          <div class="ritop"><span class="eid">${esc(e.id)}</span>${tag('t-gray', e.kind)}${srcTag(e.from === '规则判定' ? 'rule' : e.from === 'Diff 对照' ? 'diff' : 'model')}</div>
          <div class="small">${esc(e.text)}</div>
          ${e.span && e.span !== '—' ? `<button class="btn tiny mt10" onclick="jumpToSpan('${esc(e.span)}')">${icon('search')}查看原始事件 ${esc(e.span)}</button>` : ''}
        </div>`).join('')}</div>
    </div>
    <div class="card revcol refute">
      <div class="hd"><b>${icon('alert')}反面证据与替代解释（${c.refute.length}）</b></div>
      <div class="bd">${c.refute.map(e => `
        <div class="revitem">
          <div class="ritop"><span class="eid refute">${esc(e.id)}</span></div>
          <div class="small">${esc(e.text)}</div>
          <div class="impact">${esc(e.impact)}</div>
        </div>`).join('')}
        ${c.refute.length ? '' : '<div class="small muted">模型未找到反面证据。</div>'}
      </div>
    </div>
  </div>

  <div class="card">
    <div class="hd"><b>复核结论</b></div>
    <div class="bd">
      ${verdict ? `<div class="verdictdone">${icon('check')}
        <div><b>已提交：${verdict === 'confirmed' ? '确认是根因' : verdict === 'excluded' ? '排除该原因' : '暂需补充证据'}</b>
        <div class="small mt10">复核人 李工 · 已写入校准日志</div></div></div>
        ${verdict === 'confirmed' ? `<button class="btn pri mt16" onclick="openCaseModal()">${icon('file')}转回归用例</button>` : ''}`
      : `<div class="revact">
          <button class="btn ok" onclick="submitVerdict('confirmed')">${icon('check')}确认是根因</button>
          <button class="btn bad" onclick="submitVerdict('excluded')">${icon('x')}排除该原因</button>
          <button class="btn" onclick="submitVerdict('insufficient')">${icon('alert')}暂需补充证据</button>
        </div>`}
    </div>
  </div>`;
}

function submitVerdict(v){
  if (v === 'confirmed'){
    state.verdicts[state.incidentId] = 'confirmed';
    go('review', true);
    toast('已确认根因，复核结论写入校准日志');
  } else if (v === 'excluded'){
    openModal('排除该原因', `
      <div class="radios">
        <label><input type="radio" name="rj" checked> 证据错误</label>
        <label><input type="radio" name="rj"> 因果不成立</label>
        <label><input type="radio" name="rj"> 另有根因</label>
      </div>`,
      [{ label:'返回', cls:'btn', act:'closeModal()' },
       { label:'提交复核', cls:'btn pri', act:`applyExclude()` }]);
  } else {
    openModal('待补数据清单', `
      ${(DIAGNOSES[state.incidentId].gaps || ['补充采集该步骤的输入输出 payload']).map(g =>
        `<div class="gapitem">${icon('file')}<div class="small">${esc(g)}</div></div>`).join('')}`,
      [{ label:'返回', cls:'btn', act:'closeModal()' },
       { label:'提交复核', cls:'btn pri', act:`applyInsufficient()` }]);
  }
}
function applyExclude(){
  state.verdicts[state.incidentId] = 'excluded';
  closeModal(); go('review', true);
  toast('已记录排除结论与理由，校准信号已更新');
}
function applyInsufficient(){
  state.verdicts[state.incidentId] = 'insufficient';
  closeModal(); go('review', true);
  toast('已记录「暂需补充证据」，待补数据清单已生成');
}

/* ============ 回归集与门禁 ============ */
function renderGate(){
  const run = GATE_RUNS[0];
  const allCases = SUITES.flatMap(s => s.cases).concat(state.cases);
  return `
  <div class="grid g4 mb16">
    <div class="card bd"><div class="k">回归用例总数</div><div class="metric">${allCases.length}</div>
      <div class="tiny muted">来自 ${new Set(allCases.map(c => c.from)).size} 起已确认事故</div></div>
    <div class="card bd"><div class="k">最近门禁结果</div>
      <div class="metric" style="color:var(--warn)">警告</div>
      <div class="tiny muted">${esc(run.release)} · ${run.passed}/${run.total} 通过</div></div>
    <div class="card bd"><div class="k">门禁模式</div>
      <div class="metric" style="font-size:20px">${run.mode === 'warn' ? '警告不阻断' : '失败即阻断'}</div></div>
    <div class="card bd"><div class="k">语义类用例占比</div>
      <div class="metric">${Math.round(allCases.filter(c => ['FM-07','FM-08','FM-09'].includes(c.fm)).length / allCases.length * 100)}%</div>
      <div class="tiny muted">FM-07/08/09 三类</div></div>
  </div>

  <div class="card mb16 gatewarn" id="gatewarn">
    <div class="bd gaterow">
      <div class="gicon warn">${icon('alert','lg')}</div>
      <div>
        <b>发布检查：警告</b>
        <div class="small muted mt10">版本 ${esc(run.release)} · ${esc(run.at)} · 共 ${run.total} 条，通过 ${run.passed}，失败 ${run.failed}</div>
      </div>
      <div class="gact">
        <button class="btn" onclick="pushWebhook()">${icon('zap')}推送到 Webhook</button>
        <button class="btn pri" onclick="rerunGate()">${icon('refresh')}重跑回归集</button>
      </div>
    </div>
  </div>

  <div class="card mb16">
    <div class="hd"><b>本次门禁明细</b></div>
    <table class="dt">
      <thead><tr><th>用例</th><th>故障类型</th><th>结果</th><th>说明</th></tr></thead>
      <tbody>${run.detail.map(x => `<tr>
        <td class="mono">${esc(x.case)}</td>
        <td>${tag(['FM-07','FM-08','FM-09'].includes(x.fm) ? 't-bad' : 't-gray', x.fm)}</td>
        <td>${x.result === 'pass' ? tag('t-ok','通过') : tag('t-bad','未通过')}</td>
        <td class="small">${esc(x.why)}</td></tr>`).join('')}</tbody>
    </table>
  </div>

  ${SUITES.map(s => `
    <div class="card mb16">
      <div class="hd"><b>${esc(s.name)}</b><span class="tag t-gray">${s.cases.length + state.cases.filter(c => c.suite === s.id).length} 条用例</span>
        <span class="tiny muted mono">${esc(s.id)}</span></div>
      <div class="bd">
        ${s.cases.concat(state.cases.filter(c => c.suite === s.id)).map(c => `
          <div class="caseitem ${c.isNew ? 'newcase' : ''}">
            <div class="citop">
              <span class="mono"><b>${esc(c.id)}</b></span>
              ${tag(['FM-07','FM-08','FM-09'].includes(c.fm) ? 't-bad' : 't-gray', c.fm)}
              ${c.status === 'pending' ? tag('t-warn','待复核') : tag('t-ok','已生效')}
              <span class="tiny muted mono">来源 ${esc(c.from)}</span>
              ${c.status === 'pending' ? `<button class="btn tiny" style="margin-left:auto" onclick="openCaseReview('${esc(c.id)}')">复核不变量</button>` : ''}
            </div>
            <div class="invlist">${c.inv.map(v => `<div class="inv mono">${esc(v)}</div>`).join('')}</div>
            <div class="tiny muted mt10">快照：${esc(c.snapshot)}</div>
          </div>`).join('')}
      </div>
    </div>`).join('')}

  <div class="card">
    <div class="hd"><b>历史门禁运行</b></div>
    <table class="dt">
      <thead><tr><th>运行 ID</th><th>版本</th><th>时间</th><th>模式</th><th>结果</th><th>通过/总数</th></tr></thead>
      <tbody>${GATE_RUNS.map(r => `<tr>
        <td class="mono">${esc(r.id)}</td><td class="mono small">${esc(r.release)}</td><td class="small">${esc(r.at)}</td>
        <td class="small">${r.mode === 'warn' ? '警告不阻断' : '失败即阻断'}</td>
        <td>${r.result === 'pass' ? tag('t-ok','通过') : r.result === 'warn' ? tag('t-warn','警告') : tag('t-bad','阻断')}</td>
        <td class="small">${r.passed}/${r.total}</td></tr>`).join('')}</tbody>
    </table>
  </div>`;
}

/* 转回归用例：字段由已确认的诊断结果自动填充 */
function openCaseModal(){
  const i = incident(state.incidentId), d = DIAGNOSES[state.incidentId];
  const c = d.candidates[0];
  const preset = CASE_PRESETS[state.incidentId];
  if (!preset){ toast('该事故暂无可用的用例模板'); return; }
  openModal('转回归用例', `
    ${roField('来源事故', `${i.id} · ${c.title}`)}
    ${roField('输入（脱敏后）', preset.input, true)}
    ${roField('上下文快照', preset.snapshot, true)}
    <div class="fld"><div class="rolabel">期望不变量</div>
      <div class="invlist">${preset.inv.map(v => `<div class="inv mono">${esc(v)}</div>`).join('')}</div></div>
    <div class="fld"><label>归入回归集</label>
      <select id="caseSuite">
        ${SUITES.map(s => `<option value="${esc(s.id)}" ${s.id === preset.suite ? 'selected' : ''}>${esc(s.name)}（现有 ${s.cases.length} 条）</option>`).join('')}
        <option value="NEW">新建回归集…</option>
      </select></div>`,
    `<button class="btn" onclick="closeModal()">取消</button>
     <button class="btn pri" onclick="createCase()">生成用例 ${esc(preset.caseId)}</button>`);
}

function createCase(){
  const i = incident(state.incidentId);
  const preset = CASE_PRESETS[state.incidentId];
  const suite = $('caseSuite') ? $('caseSuite').value : preset.suite;
  if (state.cases.some(c => c.id === preset.caseId)){ closeModal(); toast(preset.caseId + ' 已存在，未重复生成'); return; }
  state.cases.push({
    id:preset.caseId, from:i.id, fm:i.fm, status:'pending', isNew:true,
    inv:preset.inv, snapshot:preset.snapshot,
    suite:suite === 'NEW' ? SUITES[0].id : suite,
  });
  closeModal();
  go('gate');
  toast(preset.caseId + ' 已生成并归入回归集，待复核不变量后生效');
}

function pushWebhook(){ toast('门禁报告已推送到企业微信机器人与 CI 回调地址'); }
function rerunGate(){
  toast('已触发回归集重跑，预计 2 分钟后返回结果');
  setTimeout(() => toast('回归集重跑完成：13 条用例，通过 11，失败 2（结果未变）'), 2400);
}
function openCaseReview(caseId){
  const c = SUITES.flatMap(s => s.cases).concat(state.cases).find(x => x.id === caseId);
  openModal('复核回归用例 ' + caseId, `
    ${roField('来源事故', `${c.from} · ${c.fm}`, true)}
    ${roField('快照录制', c.snapshot, true)}
    <div class="fld"><label>期望不变量</label>
      <textarea id="invEdit" rows="3">${esc(c.inv.join('\n'))}</textarea></div>`,
    `<button class="btn bad" onclick="closeModal();toast('已退回：用例保持待复核，退回理由已通知生成人')">退回</button>
     <button class="btn" onclick="closeModal()">取消</button>
     <button class="btn pri" onclick="approveCase('${esc(caseId)}')">确认生效</button>`);
}
function approveCase(caseId){
  const c = state.cases.find(x => x.id === caseId);
  if (c) c.status = 'active';
  else { const s = SUITES.flatMap(x => x.cases).find(x => x.id === caseId); if (s) s.status = 'active'; }
  closeModal(); go('gate', true);
  toast(caseId + ' 已确认生效，将参与下次发布门禁');
}

/* ============ 接入与采集体检 ============ */
function renderCheckup(){
  return `
  <div class="grid g3 mb16">
    ${CHECKUP.map(c => `
      <div class="card bd chk ${c.status}">
        <div class="chkhd"><b>${esc(c.name)}</b>${tag(c.status === 'ok' ? 't-ok' : c.status === 'warn' ? 't-warn' : 't-gray',
          c.status === 'ok' ? '正常' : c.status === 'warn' ? '需处理' : '未采集')}</div>
        <div class="metric" style="font-size:22px">${esc(c.value)}</div>
        <div class="small muted">${esc(c.detail)}</div>
        ${c.fix ? `<button class="btn tiny mt10" onclick="toggleFix('fix-${esc(c.key)}')">${icon('file')}查看修复指引</button>
          <div class="fixbox" id="fix-${esc(c.key)}" hidden>
            <ol>${c.fix.map(f => `<li>${esc(f)}</li>`).join('')}</ol>
          </div>` : ''}
      </div>`).join('')}
  </div>

  <div class="card">
    <div class="hd"><b>字段采集矩阵</b></div>
    <table class="dt">
      <thead><tr><th>事件类型</th><th>字段</th><th>用途</th><th>采集状态</th><th>影响的故障类型</th></tr></thead>
      <tbody>
        <tr><td class="mono">LLM</td><td class="mono small">input/output_payload, token</td><td class="small">模型调用还原</td><td>${tag('t-ok','已采集')}</td><td class="small">FM-05</td></tr>
        <tr><td class="mono">TOOL</td><td class="mono small">args, result, http_status</td><td class="small">工具契约校验</td><td>${tag('t-ok','已采集')}</td><td class="small">FM-02 / FM-03</td></tr>
        <tr><td class="mono">RETRIEVAL</td><td class="mono small">query, result_count</td><td class="small">空结果判定</td><td>${tag('t-ok','已采集')}</td><td class="small">FM-04</td></tr>
        <tr class="t2row"><td class="mono">RETRIEVAL</td><td class="mono small">top_k 明细, score, doc_version, effective_date</td><td class="small">排序漂移与版本时效判定</td><td>${tag('t-gray','T2 设计中')}</td><td class="small"><b>FM-07</b></td></tr>
        <tr class="t2row"><td class="mono">STATE</td><td class="mono small">entities, turn_index, supersedes, writer/reader</td><td class="small">上下文冲突消解</td><td>${tag('t-gray','T2 设计中')}</td><td class="small"><b>FM-08</b></td></tr>
        <tr class="t2row"><td class="mono">TOOL</td><td class="mono small">idempotency_key, req_id, retry_of</td><td class="small">重试幂等性判定</td><td>${tag('t-gray','T2 设计中')}</td><td class="small"><b>FM-09</b></td></tr>
        <tr class="t2row"><td class="mono">MEMORY</td><td class="mono small">key, version, written_at, expiry</td><td class="small">快照时效判定</td><td>${tag('t-gray','T2 设计中')}</td><td class="small">FM-01</td></tr>
        <tr class="t2row"><td class="mono">HANDOFF</td><td class="mono small">source/target_agent, contract</td><td class="small">跨 Agent 交接校验</td><td>${tag('t-gray','T2 设计中')}</td><td class="small">FM-06</td></tr>
      </tbody>
    </table>
  </div>`;
}
function toggleFix(id){
  const el = $(id);
  el.hidden = !el.hidden;
}

/* ============ 设置 ============ */
function renderSettings(){
  return `
  <div class="grid g2 mb16">
    <div class="card"><div class="hd"><b>项目与环境</b></div><div class="bd">
      ${roField('项目名称', '订单助手（生产环境）')}
      ${roField('Agent 版本', 'v1.4.0 · 上线 2026-08-20', true)}
      ${roField('接入方式', 'OTLP over gRPC · Agent SDK 探针 v0.9.2', true)}
    </div></div>
    <div class="card"><div class="hd"><b>门禁策略</b></div><div class="bd">
      <div class="fld"><label>门禁模式</label>
        <select id="gateMode" onchange="switchGateMode()">
          <option value="warn">警告不阻断（当前）</option>
          <option value="block">失败即阻断</option>
        </select></div>
      <div class="fld"><label>回归集触发时机</label>
        <select onchange="toast('已更新回归集触发时机')">
          <option>每次发布前自动运行</option><option>仅手动触发</option><option>每日定时 + 发布前</option>
        </select></div>
    </div></div>
  </div>

  <div class="grid g2">
    <div class="card"><div class="hd"><b>脱敏策略</b></div><div class="bd">
      <div class="switchrow"><span>手机号掩码</span><button class="sw on" onclick="toggleSwitch(this,'手机号掩码')" role="switch" aria-checked="true"></button></div>
      <div class="switchrow"><span>身份证号掩码</span><button class="sw on" onclick="toggleSwitch(this,'身份证号掩码')" role="switch" aria-checked="true"></button></div>
      <div class="switchrow"><span>订单金额脱敏</span><button class="sw" onclick="toggleSwitch(this,'订单金额脱敏')" role="switch" aria-checked="false"></button></div>
    </div></div>
    <div class="card"><div class="hd"><b>成员与权限</b></div><div class="bd">
      <table class="dt"><thead><tr><th>成员</th><th>角色</th><th>权限</th></tr></thead>
      <tbody>
        <tr><td>李工</td><td>复核人</td><td class="small">诊断复核、转用例</td></tr>
        <tr><td>王工</td><td>Agent Owner</td><td class="small">全部读写</td></tr>
        <tr><td>张工</td><td>SRE</td><td class="small">只读 + 门禁触发</td></tr>
      </tbody></table>
    </div></div>
  </div>`;
}
function switchGateMode(){
  const v = $('gateMode').value;
  GATE_RUNS[0].mode = v;
  toast(v === 'warn' ? '门禁模式：警告不阻断' : '门禁模式：失败即阻断（语义类用例误拦风险已提示）');
}
function toggleSwitch(el, name){
  const on = el.classList.toggle('on');
  el.setAttribute('aria-checked', on ? 'true' : 'false');
  toast(name + (on ? ' 已开启' : ' 已关闭'));
}

/* ============ 弹窗 ============ */
let lastFocusBeforeModal = null;

function openModal(title, body, footer){
  lastFocusBeforeModal = document.activeElement;
  $('modalRoot').innerHTML = `
    <div class="mask show" onclick="if(event.target===this)closeModal()">
      <div class="modal" role="dialog" aria-modal="true" aria-label="${esc(title)}">
        <div class="mh"><b>${esc(title)}</b><button class="mx" onclick="closeModal()" aria-label="关闭">${icon('x')}</button></div>
        <div class="mb">${body}</div>
        <div class="mf">${footer}</div>
      </div>
    </div>`;
  enhanceKeyboard();

  // 焦点捕获与陷阱
  const modal = document.querySelector('.modal');
  if (modal) {
    const focusable = modal.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    if (focusable.length) focusable[0].focus();
    modal.addEventListener('keydown', trapFocus);
  }
}

function closeModal(){
  $('modalRoot').innerHTML = '';
  if (lastFocusBeforeModal) {
    lastFocusBeforeModal.focus();
    lastFocusBeforeModal = null;
  }
}

function trapFocus(e) {
  if (e.key !== 'Tab') return;
  const focusable = Array.from(this.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'));
  if (!focusable.length) return;
  const first = focusable[0], last = focusable[focusable.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
}

/* ============ 键盘可达 ============ */
function enhanceKeyboard(){
  document.querySelectorAll('[role="button"]:not([data-kb])').forEach(el => {
    el.dataset.kb = '1';
    el.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); el.click(); }
    });
  });
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

/* ============ 初始化 ============ */
document.querySelectorAll('#nav a').forEach(a => {
  a.addEventListener('click', e => { e.preventDefault(); go(a.dataset.page); });
});
window.addEventListener('popstate', () => go(location.hash.slice(1) || 'incidents', true));
$('navIncBadge').textContent = INCIDENTS.length;

const initial = location.hash.slice(1);
if (PAGES[initial]) go(initial, true);
else { history.replaceState({ page:'incidents' }, '', location.pathname + '#incidents'); go('incidents', true); }
