# docs/design/ui-redesign-plan.md — 前端 UI 评审与优化方案

> 状态：**已实施（v2.1.0）**。P0、P1 已全部落地；P2 已落地 `LogViewer` 与令牌化收口，`manual/images/` 截图待后续更新（见第 5 节验收清单）。
> 核心规范见 [AGENTS.md](../../AGENTS.md)；前端工程说明见 [docs/rules/frontend.md](../rules/frontend.md)；用户操作说明见 [manual/用户手册.md](../../manual/用户手册.md)。

- 评审对象：`frontend/src` 全部视图与样式层，及 `manual/images/` 下 16 张真实界面截图
- 评审日期：2026-11-05
- 前置约束：站点未来将新增与「任务调度」**平级的模块**，导航与路由必须按「模块 → 页面」两级设计

---

## 1. 现状问题清单

### P0（缺陷级，优先修）

| # | 问题 | 代码定位 |
|---|------|----------|
| 1 | 未注册 Element Plus 中文语言包，表格空状态显示 `No Data`、分页显示 `Total 2`、日期控件为英文 | `frontend/src/main.ts`（`app.use(ElementPlus)` 未传 `locale`） |
| 2 | 主操作「执行任务」位于长表单最后一行，小屏/长内容时落出首屏，关键动作不可见 | `frontend/src/views/OpenList/components/Execution.vue` 表单末尾按钮行 |
| 3 | 删除/批量删除确认弹窗标题统一为「提示」，未说明影响范围 | 各组件 `ElMessageBox.confirm` 调用处 |

### P1（体验/结构级）

| # | 问题 | 代码定位 |
|---|------|----------|
| 4 | 设计令牌形同虚设：`styles/variables.scss` 定义 8 个 `--up-video-strm-*` 变量，全项目引用次数为 0；`element-reset.scss` 主色覆盖被注释，全站仍是 EP 默认蓝 `#409EFF` | `frontend/src/styles/variables.scss`、`element-reset.scss` |
| 5 | 布局宽屏失衡：执行管理表单 `max-width: 720px`、全局配置描述表 `max-width: 640px`，卡片却全宽，右侧近半屏永久留白 | `Execution.vue`、`GlobalConfig.vue` 样式段 |
| 6 | 导航只有一层标签页（5 个 tab），无法承载未来第二个平级模块；顶栏塞产品名 + slogan，无页面级标题与全局运行状态 | `App.vue`、`views/OpenList/index.vue`、`router/index.ts`（扁平路由 `/`） |
| 7 | 增量/全量/仅 strm 三个互斥概念用三个独立开关表达，且存在「关闭强制生成时静默重置 strmOnly」的隐含联动 | `Execution.vue` watch 逻辑 |

### P2（打磨级）

| # | 问题 | 代码定位 |
|---|------|----------|
| 8 | 表格计数列（视频/字幕）左对齐、非等宽数字，`0/0` 无降噪 | 各 `el-table-column` |
| 9 | 实时日志无等宽字体、无级别着色、无行号，长路径换行错乱；进度信息表达弱 | `RealtimeLog.vue` |
| 10 | 暗色主题下页面/卡片/表头三层几乎同灰阶，层级靠 1px 边框硬撑；卡片悬停阴影 `rgba(0,0,0,.12)` 在深色背景不可见 | `dark.scss`、`variables.scss` |
| 11 | 危险操作与普通操作同为文字链接，无分隔与图标；无统一 `:focus-visible` 焦点环 | 各操作列 |

---

## 2. 目标信息架构（模块 → 页面两级）

### 2.1 导航结构

```text
Video-strm
├── 模块区（一级，可扩展）
│   ├── 任务调度        ← 现有模块（OpenList/STRM 生成）
│   └── 新模块（预留）  ← 未来平级模块，加一项即可
├── ──────────────
└── 模块内页面区（二级，随所选模块切换）
    任务调度 · 配置：全局配置 / 任务配置
    任务调度 · 运行：执行管理 / 实时日志（徽标：运行中 N）
    任务调度 · 记录：任务历史
底部固定：设置（跨模块全局设置）+ 主题切换
```

- 侧栏宽 220px，可折叠为 64px 图标栏（启用 `variables.scss` 中已定义但未使用的 sidebar 令牌）。
- 模块清单数据驱动（`id / 名称 / 图标 / 页面组`），壳层代码不因新增模块而改动；新模块页面少时二级导航可不分组、直接平铺。
- 顶栏只放「页面标题 + 一句话说明 + 全局运行状态胶囊」，产品名下沉到侧栏顶部。

### 2.2 路由命名空间

| 现路由 | 新路由 | 页面 |
|--------|--------|------|
| `/`（OpenList 整页 tabs） | `/schedule/execution` | 执行管理（默认页，`/` 重定向至此） |
| tab「全局配置」 | `/schedule/config` | 全局配置 |
| tab「任务配置」 | `/schedule/tasks` | 任务配置 |
| tab「任务历史」 | `/schedule/history` | 任务历史 |
| tab「实时日志」 | `/schedule/realtime` | 实时日志 |
| `/settings` | `/settings`（不变） | 全局设置 |

- **`/settings` 路径必须保持不变**：桌面托盘外壳经 `window.__upVideoStrmNavigate('/settings')` 跳转（见 `main.ts`）。
- 未来新模块使用自己的命名空间（如 `/new-module/*`），与 `/schedule/*` 互不影响。
- 原 `Execution → 实时日志` 的带参跳转（executionIds）改为路由 query/params 传递，仍保持「先连日志再启动执行」的时序。

---

## 3. 页面级改造要点

### 3.1 执行管理（改动最大）

- 一行三卡片：左「选择任务」（可搜索复选列表，行内显示任务最近一次执行的视频数量，选中行高亮）、中「执行参数」、右「已选任务」（逐条移除、清空选择、摘要「已选 N 任务 · M 视频」与「执行任务」主按钮）。服务器选择已随单服务器化移除。
- 执行参数重构：`增量 / 全量 / 仅 strm` 改为 **分段控件（el-segmented）** 表达互斥模式，消除三个开关的隐含联动。
- 操作入口由原「底部常驻操作条」（sticky footer）调整为「已选任务」卡片底部摘要 + 执行按钮，三卡片一行展示、内容区不再需要 sticky 底栏（4.1.1 验收调整）。
- 「正在执行」表：状态用「圆点 + 文字」，计数列右对齐，运行中行给 amber 左边条。
- 「正在执行」表：状态用「圆点 + 文字」，计数列右对齐，运行中行给 amber 左边条。

### 3.2 全局配置

- 左 8 栏「服务器配置」表 + 右 4 栏「运行参数摘要卡」双栏布局；摘要卡用 definition list 而非整行 `el-descriptions`，消除右侧留白。
- 弹窗内 remark 说明文字统一 12–13px 次要色，不再逐项硬编码。

### 3.3 实时日志

三段式：
1. 顶部进度摘要条：视频/字幕双进度条 + 计数 + 耗时；
2. 中部终端区：等宽字体、按 INFO/WARN/ERROR 着色、行号、自动滚动开关；
3. 底部工具条：级别过滤、关键字搜索、清屏、下载日志。

### 3.4 任务配置 / 任务历史

- 工具栏分组：搜索类靠左、动作类靠右且主次分明（新建=主按钮，快速添加=次按钮，批量删除=danger 描边按钮+图标）；统一空状态文案 + 空态主行动按钮。
- 历史表：状态「圆点 + 文字」替代灰 tag；计数列右对齐 `tabular-nums`，`0/0` 显示「—」；长路径列合并为「任务名主行 + 路径副行」。

### 3.5 全局交互规范

- 危险操作：图标 + danger 描边按钮；确认弹窗标题与文案写明影响对象与数量（如「删除 3 个任务？该操作不可恢复」）。
- 可访问性：全部交互元素 `:focus-visible` 2px 焦点环（offset 2）；触控目标 ≥ 32px；`prefers-reduced-motion: reduce` 时禁用过渡动画。

---

## 4. 设计令牌（实施时直接落地到样式层）

### 4.1 品牌色与语义色（写入 `element-reset.scss`，替换 EP 默认值）

```scss
:root {
  // 品牌主色阶（替代 EP 默认 #409EFF）
  --el-color-primary: #2b6cf6;
  --el-color-primary-light-3: #6c97f8;
  --el-color-primary-light-5: #95b4fa;
  --el-color-primary-light-7: #bfd3fc;
  --el-color-primary-light-8: #d8e3fd;
  --el-color-primary-light-9: #eff4ff;
  --el-color-primary-dark-2: #1e55d6;

  // 语义色
  --el-color-success: #12b76a;
  --el-color-warning: #f79009;
  --el-color-danger: #e24b4a;
  --el-color-error: #e24b4a;
  --el-color-info: #667085;
}
```

### 4.2 中性色 / 表面色 / 文字色（明色主题）

```scss
:root {
  --el-bg-color-page: #f7f8fa;        // 页面底
  --el-bg-color: #ffffff;             // 卡片
  --el-bg-color-overlay: #ffffff;     // 浮层
  --el-text-color-primary: #1a1d23;   // 正文 16.9:1（AA）
  --el-text-color-regular: #3d4552;
  --el-text-color-secondary: #5b6472; // 次要 6.0:1（AA）
  --el-text-color-placeholder: #8a93a2; // 仅占位/禁用，勿用于正文
  --el-border-color: #d9dee6;
  --el-border-color-light: #e3e6eb;
  --el-border-color-lighter: #edf0f4;
  --el-fill-color-light: #f4f5f7;
  --el-border-radius-base: 6px;
}
```

### 4.3 暗色主题表面色（写入 `dark.scss`，拉开三层灰阶）

```scss
html.dark {
  --el-bg-color-page: #0e1116;   // 页面底（最深）
  --el-bg-color: #171b22;        // 卡片
  --el-bg-color-overlay: #1f2530;// 浮层（最浅）
  --el-border-color: #2a3140;
  --el-border-color-light: #262c38;
  --el-border-color-lighter: #202634;
  --el-fill-color-light: #20262f;
  --el-text-color-primary: #e6e9ef;
  --el-text-color-regular: #c3c9d4;
  --el-text-color-secondary: #9aa3b2;
  --el-color-primary: #6c97f8;   // 暗色下提亮主色，保证对比
}
```

### 4.4 项目自定义令牌（重写 `variables.scss`，删除无人引用的旧值）

```scss
:root {
  // 布局
  --up-strm-sidebar-width: 220px;
  --up-strm-sidebar-collapsed-width: 64px;
  --up-strm-topbar-height: 56px;
  --up-strm-content-max-width: 1400px;

  // 圆角：控件 6 / 卡片 8 / 容器 12
  --up-strm-radius-sm: 6px;
  --up-strm-radius-md: 8px;
  --up-strm-radius-lg: 12px;

  // 间距（4px 基数）
  --up-strm-space-1: 4px;
  --up-strm-space-2: 8px;
  --up-strm-space-3: 12px;
  --up-strm-space-4: 16px;
  --up-strm-space-6: 24px;
  --up-strm-space-8: 32px;

  // 阴影（亮/暗各一套，暗色用深投影代替浅阴影）
  --up-strm-shadow-sm: 0 1px 2px rgba(16, 24, 40, 0.06);
  --up-strm-shadow-md: 0 4px 12px rgba(16, 24, 40, 0.1);
  --up-strm-shadow-lg: 0 8px 24px rgba(16, 24, 40, 0.14);

  // 字号阶（行高 1.5，标题 1.4）
  --up-strm-font-size-xs: 12px;   // 标注/元信息
  --up-strm-font-size-sm: 13px;   // 辅助说明
  --up-strm-font-size-base: 14px; // 正文与表格
  --up-strm-font-size-lg: 16px;   // 卡片标题
  --up-strm-font-size-xl: 20px;   // 页面标题
}

html.dark {
  --up-strm-shadow-sm: 0 0 0 1px rgba(255, 255, 255, 0.04);
  --up-strm-shadow-md: 0 8px 24px rgba(0, 0, 0, 0.45);
  --up-strm-shadow-lg: 0 12px 32px rgba(0, 0, 0, 0.55);
}
```

> 命名前缀建议从 `--up-video-strm-` 缩短为 `--up-strm-`；如需保持旧前缀亦可，但必须全站唯一且实际使用，禁止再出现「定义了但 0 引用」的令牌。

### 4.5 对比度核验（WCAG AA）

| 组合 | 对比度 | 结论 |
|------|--------|------|
| 正文 `#1A1D23` / 白底 | 16.9:1 | AA 通过 |
| 次要 `#5B6472` / 白底 | 6.0:1 | AA 通过 |
| 主按钮白字 / `#2B6CF6` | 4.58:1 | AA 通过（≥4.5） |
| 占位 `#8A93A2` / 白底 | 约 3.2:1 | 仅限占位/禁用文本 |

---

## 5. 实施路线

### P0 · 缺陷修补（不改结构，建议单独一次 `patch` 发布）

- [x] `main.ts` 注册 `app.use(ElementPlus, { locale: zhCn })`，消除英文 `No Data` / `Total`
- [x] 落地 4.1–4.3 令牌（品牌主色、中性色、暗色三层灰阶）
- [x] 表格统一：行高 40px、表头 12px、计数列右对齐 `font-variant-numeric: tabular-nums`、`0/0` → `—`
- [x] 删除类确认弹窗文案具体化（对象 + 数量 + 不可恢复提示）
- [x] `:focus-visible` 全局焦点环 + `prefers-reduced-motion`

### P1 · 壳层与路由重构（建议 `minor` 发布）

- [x] 路由命名空间化（见 2.2），`/` 重定向 `/schedule/execution`，`/settings` 保持不变
- [x] `App.vue` 改为侧栏（数据驱动模块清单）+ 顶栏页面头 + 全局状态胶囊
- [x] 5 个 tab 页拆为独立路由页面，保留 tab 内 `reload` 的按需加载语义（改由路由切换触发）
- [x] 执行管理分段控件 + 带参跳实时日志改路由传参（布局于 4.1.1 验收后改为三卡片一行：选择任务 / 执行参数 / 已选任务）
- [x] 回归点：5 个页面 `height: 100%` 滚动链、sticky 表现、暗色主题、托盘跳设置

### P2 · 收口（可选）

- [ ] 抽基础组件：`PageHeader / StatCard / DataTable / LogViewer`（`LogViewer`、`StatusDot` 已抽；其余页面内样式已按同一套令牌统一，暂未单独抽组件）
- [x] 全站硬编码颜色/间距替换为令牌引用；删除遗留未用令牌
- [ ] 更新 `docs/rules/frontend.md` 与 `manual/用户手册.md` 截图（文档正文已同步更新；16 张截图仍为旧版界面，待后续重拍）


> 实施纪律（见 AGENTS.md）：每步独立 commit（`fix:` / `feat:` / `docs:` + 中文描述）；逐项 `git add`；测试全绿后再交付；P1 交付前用 `packaging/bump_version.py` 按 `minor` 递增版本并保持四处一致。

---

## 6. 涉及文件清单（实施结果）

| 文件 | 改动类型 |
|------|----------|
| `frontend/src/main.ts` | 注册 zhCn locale、引入样式 |
| `frontend/src/styles/variables.scss` / `element-reset.scss` / `dark.scss` / `global.scss` | 4.1–4.3 令牌、EP 变量映射、暗色表面色、焦点环与减少动效 |
| `frontend/src/router/index.ts` | 命名空间路由 + `/` 重定向 + catch-all |
| `frontend/src/App.vue` | 壳层：侧栏 + 顶栏 + 运行状态胶囊 + 主题切换 |
| `frontend/src/views/schedule/{Execution,GlobalConfig,TaskManage,TaskHistory,RealtimeLog}.vue` | 五个页面按第 3 节新建（旧 `views/OpenList/` 已删除） |
| `frontend/src/views/schedule/components/DirTreePanel.vue` | 目录树组件迁移 |
| `frontend/src/components/{StatusDot,LogViewer}.vue` | 新增通用组件（`ThemeToggle` 沿用） |
| `frontend/src/stores/openlist.ts` | 补充运行中数量供导航徽标 / 状态胶囊使用 |
| `frontend/src/types/openlist.ts`、`frontend/src/api/index.ts` | 内联 `Res` 类型、收口响应拦截器类型 |
| `frontend/tsconfig.app.json` | TS 6 的 `ignoreDeprecations`（保留 `baseUrl` 别名） |

