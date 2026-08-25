var pageTitles={runs:'运行记录',trace:'正常 Trace 详情',incidents:'事故列表',workbench:'诊断工作台 · INC-2026-0814-003',diff:'成功/失败 Diff · TRC-4a7c vs TRC-9f21',review:'诊断复核 · 候选原因 1',gate:'回归集与发布门禁',checkup:'接入与采集体检',settings:'设置'};
function go(p,fromHistory){
  if(!pageTitles[p]){p='incidents';}
  document.querySelectorAll('.page').forEach(function(el){el.classList.remove('show')});
  document.getElementById('pg-'+p).classList.add('show');
  var navPage={trace:'runs',workbench:'incidents',diff:'incidents',review:'incidents'}[p]||p;document.querySelectorAll('#nav a').forEach(function(a){a.classList.toggle('active',a.dataset.page===navPage)});
  document.getElementById('pageTitle').textContent=pageTitles[p];
  if(!fromHistory&&window.location.hash!=='#'+p){window.history.pushState({page:p},'',window.location.pathname+window.location.search+'#'+p);}
  window.scrollTo(0,0);
  if(p==='gate'){var g=document.getElementById('gwarn');g.classList.remove('pulse');void g.offsetWidth;g.classList.add('pulse');}
}
document.querySelectorAll('#nav a').forEach(function(a){a.addEventListener('click',function(e){e.preventDefault();go(a.dataset.page)})});
window.addEventListener('popstate',function(){go(window.location.hash.slice(1)||'incidents',true)});
if(window.location.hash&&pageTitles[window.location.hash.slice(1)]){go(window.location.hash.slice(1),true);}else{window.history.replaceState({page:'incidents'},'',window.location.pathname+window.location.search+'#incidents');}

function filterIncidents(){
  var failure=document.getElementById('incidentFailureFilter').value,type=document.getElementById('incidentStepType').value,query=document.getElementById('incidentStepName').value.trim().toLowerCase(),maxAge=Number(document.getElementById('incidentTimeFilter').value),review=document.getElementById('incidentReviewFilter').value,evidence=document.getElementById('incidentEvidenceFilter').value;
  var rows=Array.from(document.querySelectorAll('.incident-row')),visible=0;
  rows.forEach(function(row){var show=(failure==='all'||row.dataset.failure===failure)&&(type==='all'||row.dataset.stepType===type)&&(!query||row.dataset.stepName.toLowerCase().indexOf(query)>=0)&&Number(row.dataset.age)<=maxAge&&(review==='all'||row.dataset.review===review)&&(evidence==='all'||row.dataset.evidence===evidence);row.style.display=show?'':'none';if(show)visible++;});
  document.getElementById('incidentVisibleCount').textContent=visible+' 条记录';document.getElementById('incidentEmpty').style.display=visible?'none':'block';
}
function resetIncidentFilters(){document.getElementById('incidentFailureFilter').value='all';document.getElementById('incidentStepType').value='all';document.getElementById('incidentStepName').value='';document.getElementById('incidentTimeFilter').value='24';document.getElementById('incidentReviewFilter').value='all';document.getElementById('incidentEvidenceFilter').value='all';filterIncidents();}
function filterRuns(){var execution=document.getElementById('runExecutionFilter').value,quality=document.getElementById('runQualityFilter').value,run=document.getElementById('runNameFilter').value,version=document.getElementById('runVersionFilter').value;var rows=Array.from(document.querySelectorAll('.run-row')),visible=0;rows.forEach(function(row){var show=(execution==='all'||row.dataset.execution===execution)&&(quality==='all'||row.dataset.quality===quality)&&(run==='all'||row.dataset.run===run)&&(version==='all'||row.dataset.version===version);row.classList.toggle('hidden',!show);if(show)visible++;});document.getElementById('runVisibleCount').textContent=visible+' 条记录';document.getElementById('runEmpty').style.display=visible?'none':'block';}
function resetRunFilters(){document.getElementById('runExecutionFilter').value='all';document.getElementById('runQualityFilter').value='all';document.getElementById('runNameFilter').value='all';document.getElementById('runVersionFilter').value='all';filterRuns();}
function focusIncident(failure,type){go('incidents');document.getElementById('incidentFailureFilter').value=failure;document.getElementById('incidentStepType').value=type;filterIncidents();document.getElementById('incList').scrollIntoView({behavior:'smooth',block:'start'});}
function showIncidentPreview(row){
  document.querySelectorAll('.incident-row').forEach(function(r){r.classList.remove('incident-selected')});
  row.classList.add('incident-selected');
  var panel=document.getElementById('incidentPreview'),cells=row.cells;
  document.getElementById('incidentPreviewId').textContent=cells[0].textContent.trim();
  document.getElementById('incidentPreviewSymptom').textContent=cells[3].textContent.trim();
  document.getElementById('incidentPreviewStep').textContent=cells[4].textContent.trim();
  document.getElementById('incidentPreviewEvidence').textContent=cells[5].textContent.trim();
  document.getElementById('incidentPreviewReview').textContent=cells[6].textContent.trim();
  panel.hidden=false;panel.scrollIntoView({behavior:'smooth',block:'nearest'});
  toast('已打开 '+cells[0].textContent.trim()+' 的事故概览');
}
var activeTraceId='TRC-9f21',activeTraceQuality='pass';
function openNormalTrace(id,task,time,duration,quality){
  activeTraceId=id;activeTraceQuality=quality;
  document.getElementById('traceDetailTitle').textContent=task+' · '+id;
  document.getElementById('traceDetailId').textContent=id;
  document.getElementById('traceDetailTime').textContent=time;
  document.getElementById('traceDetailDuration').textContent=duration;
  var passed=quality==='pass',badge=document.getElementById('traceQualityBadge'),button=document.getElementById('traceBaselineButton');
  badge.textContent=passed?'质量通过':'质量未评估';badge.className='tag '+(passed?'t-ok':'t-gray');
  document.getElementById('traceQualitySummary').textContent=passed?'本次执行技术状态成功，且质量评估通过；不生成事故候选原因。':'本次执行技术状态成功，但质量尚未评估；当前未立案，也不能作为推荐基线。';
  document.getElementById('traceStatusTitle').textContent=passed?'执行成功且质量通过':'执行成功，质量未评估';
  document.getElementById('traceStatusText').textContent=passed?'该结论同时满足技术执行与质量评估，可用于采集核对、性能分析和 Diff 基线。':'该 Trace 仍可浏览完整链路；完成质量评估前，不自动推荐为 Diff 基线。';
  button.disabled=!passed;button.classList.toggle('disabled',!passed);button.title=passed?'':'仅质量通过且满足兼容性条件的 Trace 可设为基线';
  go('trace');
}
function useTraceAsBaseline(){
  if(activeTraceQuality!=='pass'){toast('质量未评估，不能设为对比基线');return;}
  var label=document.getElementById('diffBaselineId');
  var head=document.getElementById('diffBaselineHead');
  if(label)label.textContent=activeTraceId;
  if(head)head.textContent=activeTraceId;
  pageTitles.diff='成功/失败 Diff · TRC-4a7c vs '+activeTraceId;
  go('diff');
  toast('已将 '+activeTraceId+' 设为本次成功/失败对比基线');
}

function selectCluster(el,failure){
  document.querySelectorAll('.cluster').forEach(function(c){c.classList.remove('selected')});
  el.classList.add('selected');
  document.getElementById('incList').scrollIntoView({behavior:'smooth',block:'start'});
  document.getElementById('incidentFailureFilter').value=failure;filterIncidents();
}
var diagLoaded=false;
function openIncident(){
  go('workbench');
  var c=document.getElementById('cand1');if(!c.classList.contains('open'))togglecand('cand1');
  if(!diagLoaded){
    diagLoaded=true;
    var l=document.getElementById('diagload'),c2=document.getElementById('cand2'),c3=document.getElementById('cand3');
    l.style.display='flex';c2.style.display='none';c3.style.display='none';
    setTimeout(function(){
      l.style.display='none';
      c2.style.display='block';c3.style.display='block';
      c2.classList.add('fadein');c3.classList.add('fadein');
      toast('语义分析完成：已追加 2 条模型候选与反证');
    },1100);
  }
}
function togglecand(id){document.getElementById(id).classList.toggle('open')}
function hlSpan(s){
  go('workbench');
  var t=document.getElementById('ttree');t.style.display='block';
  var row=document.getElementById('sp-'+s);
  if(row){
    document.querySelectorAll('.trow').forEach(function(r){r.classList.remove('located','flash')});
    row.scrollIntoView({behavior:'smooth',block:'center'});
    void row.offsetWidth;
    row.classList.add('located','flash');
  }
  toast('已定位到原始事件 '+s+'（驻留高亮，可回看）');
}
var reviewDone=false;
function submitReview(v){
  if(v==='confirmed'){
    reviewDone=true;
    document.getElementById('reviewbar').style.display='none';
    document.getElementById('vd-done').classList.add('show');
    document.getElementById('vstat-wb').innerHTML='<span class="tag t-ok">已确认根因 · 李工</span>';
    document.getElementById('vstat-list').innerHTML='<span class="tag t-ok">已确认 · 李工</span>';
    toast('复核结论已写入校准日志与历史案例库');
  }else if(v==='excluded'){openModal('m-reject');}
  else{openModal('m-insuff');}
}
var modalReturnFocus=null;
function openModal(id){var mask=document.getElementById(id);modalReturnFocus=document.activeElement;mask.classList.add('show');var first=mask.querySelector('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])');if(first){setTimeout(function(){first.focus()},0);}}
function closeModal(id){document.getElementById(id).classList.remove('show');if(modalReturnFocus&&typeof modalReturnFocus.focus==='function'){modalReturnFocus.focus();}modalReturnFocus=null;}
function openCaseModal(){openModal('m-case')}
function createCase(){
  closeModal('m-case');
  document.getElementById('newCaseRow').style.display='table-row';
  document.getElementById('caseCount').textContent='13 个用例';
  go('gate');
  toast('已生成回归用例 REG-1041（待复核）—— 点击该行复核不变量，确认生效后才参与门禁');
}
var caseReviewed=false;
function openReviewModal(){
  if(caseReviewed){toast('REG-1041 已复核生效，无需重复复核');return;}
  openModal('m-review');
}
function approveCase(){
  caseReviewed=true;
  closeModal('m-review');
  document.getElementById('revStat').innerHTML='<span class="tag t-ok">已复核 · 李工</span>';
  document.getElementById('gateNewRow').style.display='table-row';
  document.getElementById('gwarnCnt').textContent='2';
  toast('复核通过 · REG-1041 已生效并加入门禁运行');
}
var toastTimer;
function toast(msg){
  var t=document.getElementById('toast');t.textContent=msg;
  t.classList.remove('in');void t.offsetWidth;t.classList.add('in');
  clearTimeout(toastTimer);toastTimer=setTimeout(function(){t.classList.remove('in')},2800);
}

document.querySelectorAll('[onclick]').forEach(function(el){if(!/^(BUTTON|A|INPUT|SELECT|TEXTAREA)$/.test(el.tagName)){el.setAttribute('role','button');el.setAttribute('tabindex','0');el.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();el.click();}});}});
document.querySelectorAll('.mask').forEach(function(mask){mask.setAttribute('role','dialog');mask.setAttribute('aria-modal','true');});
document.addEventListener('keydown',function(e){if(e.key==='Escape'){var open=document.querySelector('.mask.show');if(open){e.preventDefault();closeModal(open.id);}}});
