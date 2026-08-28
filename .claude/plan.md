# midterm/prototype.html 生产就绪重构计划

## 现状分析

### 当前架构
- **HTML**: 72 行骨架，外部依赖 Google Fonts（离线失败风险）
- **CSS**: 964 行，已有完整 token 系统、响应式、无障碍基础
- **JS**: 868 行原型逻辑，data.js 487 行硬编码数据
- **质量**: 已通过对比度 WCAG AA、无语法错误、键盘基础可达

### 核心问题

#### 1. 生产环境缺陷（P0）
- **字体依赖**: Google Fonts CDN，离线/内网失败
- **无错误边界**: JS 运行时异常导致白屏
- **缺少元信息**: 无 meta description、favicon、OG 标签
- **硬编码数据**: 无 API 集成准备、无加载/错误状态

#### 2. 性能问题（P1）
- **无防抖**: 筛选输入直接触发全表过滤
- **全量渲染**: 每次页面切换重新生成完整 HTML 字符串
- **无懒加载**: 模态框内容预渲染

#### 3. 无障碍缺失（P1）
- **焦点管理**: 模态框打开后焦点未捕获、关闭后未恢复
- **动态通知**: 页面切换/数据更新无 aria-live 通知
- **语义结构**: 树形结构缺少 role="tree/treeitem"
- **键盘陷阱**: 模态框内 Tab 可逃逸到背景

#### 4. 可维护性（P2）
- **状态分散**: state 对象与 DOM 事件耦合紧密
- **魔法字符串**: 页面 ID、数据字段散布全局
- **无类型安全**: 纯 JS 无运行时校验

## 重构方案

### A. 生产环境加固（P0）

#### A1. 自托管字体回退
```html
<!-- 保留 Google Fonts preconnect 作为性能优化 -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
<!-- 添加本地 fallback 到 CSS -->
@font-face {
  font-family: 'Inter Fallback';
  src: local('Segoe UI'), local('Microsoft YaHei');
  /* 仅当 CDN 失败时生效 */
}
:root { --font: "Inter", "Inter Fallback", "Segoe UI", ... }
```

**决策**: 不内嵌 WOFF2（Inter 完整字重 ~800KB），保持离线可用的系统字体 fallback。

#### A2. 全局错误边界
```javascript
// 顶层 try-catch + window.onerror
window.onerror = (msg, url, line, col, error) => {
  console.error('Runtime error:', error);
  showErrorPage('页面遇到错误，请刷新重试', error);
  return true; // 阻止默认错误处理
};

// 关键函数包裹 try-catch
function safeRender(fn, fallback) {
  try { return fn(); }
  catch (e) { console.error(e); return fallback || '<div class="empty">加载失败</div>'; }
}
```

#### A3. 元信息与 favicon
```html
<meta name="description" content="寻迹 Agent 链路诊断平台 - 证据化根因定位演示原型">
<meta name="theme-color" content="#2563EB">
<!-- Favicon: inline SVG data URI -->
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><circle cx='12' cy='12' r='10' fill='%232563EB'/><path d='...' fill='white'/></svg>">
```

#### A4. API 就绪架构
```javascript
// 数据层抽象
const DataSource = {
  async fetchTraces(filters) {
    // 原型模式：返回硬编码数据
    return Promise.resolve(TRACES.filter(...));
    // 生产模式：调用 API
    // return fetch('/api/traces', { method:'POST', body:JSON.stringify(filters) })
    //   .then(r => r.ok ? r.json() : Promise.reject(r.statusText));
  },
  async fetchDiagnosis(incidentId) { /* 同上 */ },
  // ... 其他端点
};

// 渲染层带加载/错误态
async function renderRunsAsync() {
  const container = $('pg-runs');
  container.innerHTML = '<div class="diagload">加载中...</div>';
  try {
    const data = await DataSource.fetchTraces(state.filters.run);
    container.innerHTML = renderRunsContent(data);
  } catch (e) {
    container.innerHTML = `<div class="empty">${icon('alert')}加载失败：${esc(e.message)}</div>`;
  }
}
```

### B. 性能优化（P1）

#### B1. 输入防抖
```javascript
function debounce(fn, delay) {
  let timer;
  return function(...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}
// 应用到筛选输入
const debouncedFilter = debounce(() => {
  go(state.page, true); // 重新渲染当前页
}, 300);
```

#### B2. 虚拟滚动（可选，需评估收益）
- 当前 TRACES 仅 12 条，INCIDENTS 9 条，**暂不需要**
- 预留扩展点：表格渲染函数接受 `slice(start, end)` 参数

#### B3. 懒加载诊断候选
```javascript
// 现状：renderWorkbench 直接渲染 DIAGNOSES[id].candidates
// 改进：首次渲染骨架 + 1.1s 后异步填充模型候选
function renderWorkbench() {
  const d = DIAGNOSES[state.incidentId];
  if (!d) return '<div class="empty">诊断数据缺失</div>';
  
  // 规则候选立即渲染
  let html = d.candidates.filter(c => c.source === 'rule').map(renderCandidate).join('');
  
  // 模型候选异步
  if (!state.diagLoaded[state.incidentId]) {
    html += '<div class="diagload" id="modelCandPlaceholder">模型推断中...</div>';
    setTimeout(() => loadModelCandidates(state.incidentId), 1100);
  } else {
    html += d.candidates.filter(c => c.source === 'model').map(renderCandidate).join('');
  }
  return `<div class="card mb16">... ${html}</div>`;
}
```

### C. 无障碍完善（P1）

#### C1. 焦点管理
```javascript
let lastFocus = null;
function openModal(title, body, footer) {
  lastFocus = document.activeElement;
  // ... 原渲染逻辑
  const modal = document.querySelector('.modal');
  const focusable = modal.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
  if (focusable.length) focusable[0].focus();
  
  // 焦点陷阱
  modal.addEventListener('keydown', trapFocus);
}
function closeModal() {
  $('modalRoot').innerHTML = '';
  if (lastFocus) lastFocus.focus();
}
function trapFocus(e) {
  if (e.key !== 'Tab') return;
  const focusable = Array.from(this.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'));
  const first = focusable[0], last = focusable[focusable.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}
```

#### C2. 动态通知
```html
<!-- 在 body 添加 -->
<div id="liveRegion" role="status" aria-live="polite" aria-atomic="true" class="sr-only"></div>
```
```javascript
function announce(msg) {
  const region = $('liveRegion');
  region.textContent = msg;
  setTimeout(() => { region.textContent = ''; }, 1000);
}
// 在页面切换、数据加载完成时调用
function go(page, fromHistory) {
  // ... 原逻辑
  announce(PAGES[page].title + '已加载');
}
```

#### C3. 树形语义
```javascript
// renderTree 改为带 ARIA 角色
function renderTree(spans, highlight, inc) {
  return `<div class="tree" role="tree" aria-label="调用链路">
    ${spans.map((s, i) => `
      <div class="trow ${...}" role="treeitem" aria-level="${s.level}" aria-setsize="${spans.length}" aria-posinset="${i+1}">
        ...
      </div>`).join('')}
  </div>`;
}
```

#### C4. 键盘增强
```javascript
// 可点击行 Enter/Space 触发
document.addEventListener('keydown', e => {
  if ((e.key === 'Enter' || e.key === ' ') && e.target.classList.contains('click')) {
    e.preventDefault();
    e.target.click();
  }
});
```

### D. 可维护性提升（P2）

#### D1. 配置集中化
```javascript
const CONFIG = {
  PAGES: { /* 现有 PAGES 对象 */ },
  LABELS: {
    EXEC_STATUS: { success:'执行成功', failed:'执行失败', timeout:'超时', running:'运行中' },
    QUALITY: { pass:'质量通过', fail:'不通过', unknown:'未评估' },
    // ... 其他枚举
  },
  API_ENDPOINTS: { /* 预留 */ },
  FEATURE_FLAGS: {
    USE_REAL_API: false,
    ENABLE_VIRTUAL_SCROLL: false,
  }
};
```

#### D2. 数据校验（运行时）
```javascript
function validate(data, schema) {
  // 简化版 schema 校验，避免引入第三方库
  for (const [key, rule] of Object.entries(schema)) {
    if (rule.required && !(key in data)) throw new Error(`Missing required field: ${key}`);
    if (rule.type && typeof data[key] !== rule.type) throw new Error(`${key} must be ${rule.type}`);
  }
  return true;
}
// 应用到 DataSource
async fetchTraces(filters) {
  validate(filters, { exec:{type:'string'}, quality:{type:'string'} });
  // ...
}
```

#### D3. 事件委托优化
```javascript
// 现状：每个按钮 onclick="fn()" 内联事件
// 改进：顶层委托 + data-action
document.addEventListener('click', e => {
  const action = e.target.closest('[data-action]')?.dataset.action;
  if (!action) return;
  const handlers = {
    'go-trace': () => { state.traceId = e.target.dataset.id; go('trace'); },
    'open-workbench': () => { state.incidentId = e.target.dataset.id; go('workbench'); },
    // ... 其他动作
  };
  handlers[action]?.();
});
// HTML 改为 <button data-action="go-trace" data-id="TRC-123">
```
**权衡**: 内联事件可读性更高、调试容易，委托适合大量重复元素。本原型保持内联，仅在表格行点击等高频场景使用委托。

## 实施计划

### 第 1 步：加固（P0，30 分钟）
1. 添加 meta 标签、favicon data URI
2. 字体 fallback 到 CSS `:root { --font }`
3. 全局 `window.onerror` + `safeRender` 包裹关键渲染函数
4. 抽离 `DataSource` 层（现阶段返回硬编码数据）

### 第 2 步：无障碍（P1，20 分钟）
1. 焦点管理：`openModal` 捕获、`closeModal` 恢复、焦点陷阱
2. `aria-live` 通知区域 + `announce()` 函数
3. 树形 `role="tree"` + `aria-level`
4. ESC 关闭模态框（已有，验证）

### 第 3 步：性能（P1，15 分钟）
1. 筛选输入 `debounce(300ms)`
2. 诊断工作台模型候选懒加载（`setTimeout 1100ms`）

### 第 4 步：可维护性（P2，可选）
- 配置常量提取到 `CONFIG` 对象
- 运行时数据校验（轻量级）

### 第 5 步：文档与测试（10 分钟）
- 更新 `说明.md`：标注「生产就绪版本」
- 添加 `CHANGELOG.md` 记录改动
- 手动烟雾测试清单（9 页 × 关键交互）

## 预期产出

### 文件变更
- `prototype.html`: +12 行（meta、favicon、aria-live 区域）
- `css/prototype.css`: +8 行（字体 fallback、`.sr-only`）
- `js/prototype.js`: +120 行（错误边界、DataSource、焦点管理、防抖），重构 -30 行
- `说明.md`: +1 节「生产就绪特性」
- `CHANGELOG.md`: 新增

### 质量指标
- **错误处理**: 0 → 100%（全局 + 关键路径）
- **无障碍**: WCAG AA 文本对比度（已达标）+ 焦点管理 + 动态通知 + 语义角色
- **离线可用**: 字体 fallback 后完全离线
- **API 就绪**: 数据层抽象完成，生产环境切换配置即可

### 不改动项（明确排除）
- **框架重写**: 保持原生 JS，不引入 React/Vue
- **构建工具**: 保持单文件、无编译、双击可开
- **CSS 预处理**: 保持原生 CSS，已有 token 系统足够
- **虚拟滚动**: 当前数据量小，过度工程
- **后端 Mock**: 硬编码数据已足够演示，API 集成由实际后端对接时完成

## 风险与权衡

### 风险 1：向后兼容
- **影响**: 内联事件改委托会破坏现有调用
- **缓解**: 保持内联事件，仅在新增功能使用委托

### 风险 2：测试覆盖
- **影响**: 无自动化测试，重构可能引入回归
- **缓解**: 分步提交 + 每步手动烟雾测试 + Git 可回滚

### 风险 3：过度设计
- **影响**: 添加太多「生产特性」偏离原型定位
- **缓解**: 仅实施 P0/P1，P2 可选；保持「双击可开、无构建」约束

## 验收标准

1. ✅ 断网环境下打开 `prototype.html`，字体回退正常、页面完整可用
2. ✅ 控制台注入错误 `throw new Error('test')`，显示错误页而非白屏
3. ✅ 键盘操作：Tab 遍历、Enter/Space 触发、Esc 关闭模态框、模态框内焦点不逃逸
4. ✅ 屏幕阅读器（NVDA/VoiceOver）：页面切换有通知、树形结构有层级、表格有列头
5. ✅ 筛选输入快速敲击 10 次，仅触发 1 次渲染（防抖生效）
6. ✅ 诊断工作台打开后 1.1s，模型候选从骨架变为实际内容
7. ✅ `check-contrast.py` 对比度检查通过（保持 WCAG AA）
8. ✅ 所有现有功能回归测试通过（9 页 × 主流程）

---

**评审要点**
- 是否同意「保持单文件 + 无构建」约束？
- P2 可维护性改进是否需要（CONFIG 提取、事件委托）？
- 是否需要补充其他生产特性（如：CSP、Subresource Integrity）？
