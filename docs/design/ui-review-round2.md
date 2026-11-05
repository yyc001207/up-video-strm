# docs/design/ui-review-round2.md — 前端 UI 评审与优化方案（第二轮）

> 状态：**评审完成，未实施**。本文档只提出问题与方案，不包含代码改动。
> 上一轮评审见 [ui-redesign-plan.md](ui-redesign-plan.md)（已实施至 v2.1.0）；核心规范见 [AGENTS.md](../../AGENTS.md)；前端工程说明见 [docs/rules/frontend.md](../rules/frontend.md)。

- 评审对象：`frontend/src` 全部视图与样式层（约 6600 行，14 个视图组件）+ 真实界面截图
- 评审日期：2026-11-05
- 基线版本：**4.8.0**（commit `7983f0e`）
- 评审方法：Playwright 1440×900 截图（明色 5 页现存于 `frontend/shots/`）逐页目检 + 问题逐条回源码定位核实；所有结论均已在代码中找到对应行，未凭截图猜测
- 前置背景：相比第一轮（单模块五页签），当前已是「全局配置 / 任务调度 / 上传管理」三平级模块、11 个路由页面，本轮问题集中在**异常态处理**与**多模块全局状态聚合**，而非布局骨架

---

## 1. 第一轮落地情况核对

第一轮方案的 P0 / P1 已全部落地并验证有效，本轮无需重做：

| 第一轮目标 | 现状 |
|------------|------|
| 设计令牌体系（品牌色 / 中性色 / 暗色三层灰阶） | 已落地且质量良好，`element-reset.scss` / `dark.scss` / `variables.scss` 分层清晰 |
| 表格统一规范（40px 行高、表头 12px、计数列 `tabular-nums`） | 已落地（`element-reset.scss:36-62`） |
| `:focus-visible` 焦点环、`prefers-reduced-motion` | 已落地（`global.scss:50-66`） |
| 中文 locale、删除确认文案具体化 | 已落地 |
| 模块化导航壳层 | 已落地且扩展为三模块，数据驱动结构可继续复用 |

第一轮 P2 遗留（本轮顺带跟进）：

- [ ] `PageHeader / StatCard / DataTable` 基础组件未抽取（`LogViewer`、`StatusDot` 已抽）。
- [ ] `manual/images/` 16 张截图仍为旧版界面。

**同时核实两项「非问题」**（此前口头评审有误，特此更正）：

- 视图与组件层**没有**硬编码颜色：`#[0-9a-fA-F]{6}` 与 `rgba(` 匹配数均为 0（此前误将模板插槽语法 `#default` 当作十六进制色统计）。颜色令牌纪律执行得很好。
- 执行管理**并非没有响应式断点**：`schedule/Execution.vue:897-923` 已有 1200px（缩窄）与 1100px（堆叠）两级断点。真实问题是断点区间选取不当，见 P0-3。

---

## 2. 问题清单（均已在代码中定位核实）

### P0（缺陷级，优先修）

| # | 问题 | 代码定位 | 截图证据 |
|---|------|----------|----------|
| 1 | 全局错误提示无去重、无节流，轮询失败时弹窗轰炸：每 5–10 秒弹出一条相同「网络异常，请稍后重试」，连续堆叠并遮挡卡片头部 | `api/index.ts:34-37`（拦截器每错必弹）；`App.vue:158-168`（10s 轮询）→ `stores/openlist.ts:46`（`fetchRunning` 未传 `silent`）；`views/schedule/Execution.vue:146-154`（5s 轮询的 `silent` 参数只控制 loading，**未透传** axios `silent`） | `schedule-execution-light.png`：3 条相同 toast 纵向堆叠盖住卡片 |
| 2 | 顶栏运行状态胶囊语义失真且不聚合上传模块：接口失败时 `runningCount=0` 显示「空闲」；且 `runningCount` 只来自任务调度（openlist）执行，上传管理执行走独立接口，全局胶囊与导航徽标均不纳入；点击固定跳 `/schedule/realtime`，运行的是上传任务时会跳错模块 | `App.vue:150-176, 552-585`；`stores/openlist.ts:46-49`；`api/uploader.ts:75`（上传执行独立接口）；`views/upload/Execution.vue:63` | `schedule-tasks-light.png`：后端不可达时胶囊仍显示「空闲」 |
| 3 | 执行管理三卡片在 1100–1600px 区间中栏过窄：1440 视口下中栏仅 ≈285px，`el-segmented` 的「全量更新 / 仅更新 STRM」文字截断为省略号，核心参数不可读。两个模块同构复用此布局 | `views/schedule/Execution.vue:541`（`minmax(0,1.6fr) minmax(240px,0.85fr) minmax(260px,0.95fr)`）；`views/upload/Execution.vue:339` 同构 | `schedule-execution-light.png`：分段控件显示「全量重… / 仅更新 …」 |

### P1（体验 / 信息架构级）

| # | 问题 | 代码定位 |
|---|------|----------|
| 4 | 首访空态引导断裂：任务配置页同时存在两块独立空态（「默认运行参数」卡空态 + 任务表空态），表格空态内的「新建任务」按钮与工具栏主按钮重复；首访用户无法判断先配参数还是先建任务。上传任务配置页同构 | `views/schedule/TaskManage.vue:444, 475, 504-507`；`views/upload/TaskConfig.vue:171, 198-200` |
| 5 | 触控目标低于项目自身规范（第一轮 3.5 节约定 ≥32px）：侧栏折叠按钮 28×28、顶栏状态胶囊高 28px | `App.vue:344-351, 552-557` |
| 6 | 导航分组标题使用占位色 `--el-text-color-placeholder`，与第一轮令牌注释「仅占位/禁用，勿用于正文」自相矛盾；12px 文字对比度仅约 3.2:1，低于 AA | `App.vue:414-420` |

### P2（打磨级）

| # | 问题 | 代码定位 / 证据 |
|---|------|----------|
| 7 | 实时日志页顶部三行（连接选择 / 进度摘要 / 过滤工具条）间距节奏不均，进度条与右侧「—」耗时数值基线对齐松散 | `schedule-realtime-light.png`、`views/schedule/RealtimeLog.vue` |
| 8 | 全局配置页 2:1 栅格下双卡空态失衡：左卡空态占位 ~250px 高，右卡大留白，页面重心偏左上 | `config-light.png`；`views/config/GlobalConfig.vue:365-452` |
| 9 | 浏览器标签页标题过期：仍是「up-video-strm 任务调度」，实际已有三个平级模块 | `frontend/index.html:6` |
| 10 | 截图基线残缺：`frontend/.ui-review-shots.mjs` 设计覆盖 11 路由 × 明暗主题 + 折叠态，但 `frontend/shots/` 仅存 5 张明色旧图；`manual/images/` 16 张截图为第一轮之前的旧界面（第一轮 P2 遗留） | `frontend/shots/`、`manual/images/` |

---

## 3. 优化方案

### 3.1 P0-1 全局错误提示治理（改动最小、收益最大）

**方案：三层收口，全部集中在 `api/index.ts` 与 `App.vue`，不触碰业务视图。**

1. **拦截器去重节流**（`api/index.ts`）：维护 `lastError = { message, timestamp }`，同一文案 3 秒窗口内只弹一次；并发失败（页面加载同时打 4 个接口）合并为一条。
2. **轮询全部静默**：
   - `stores/openlist.ts` `fetchRunning` 增加 `silent` 透传，`App.vue` 轮询调用改为 silent；
   - `views/schedule/Execution.vue` `refreshRunning` 的 `silent` 参数同时透传给 axios（修正现在「只关 loading 不静默」的语义偏差）；
   - 同样检查 `views/upload/Execution.vue` 的 5s 轮询与两个 `RealtimeLog` 的状态轮询。
3. **全局离线状态条**（新增，替代弹窗表达持续性故障）：`stores/openlist.ts` 增加 `lastNetworkErrorAt` 状态；`App.vue` 顶栏下方渲染一条 `el-alert`（`type="error"`，可关闭）：「无法连接后端服务，正在自动重试…」。间歇性单次失败不再打扰，持续性故障有稳定可见的出口，弹窗只保留用户主动操作触发的失败。

**验收标准**：后端停机时，任意页面停留 1 分钟，toast 出现 ≤1 条；顶栏出现离线状态条；后端恢复后状态条自动消失。

### 3.2 P0-2 运行状态聚合与三态胶囊

**方案：**

1. 新建 `stores/running.ts`（或扩展现有 store）：聚合两条轮询——`openlistApi.listExecutions({status:'running'})` 与 `uploaderApi.listExecutions({status:'running'})`，输出 `{ scheduleCount, uploadCount, total, lastErrorAt }`；App 壳层单处轮询（保持 10s），两个执行管理页可继续保留各自的页面内轮询。
2. 胶囊三态：
   - `lastErrorAt` 距今 < 30s → 「连接失败」（danger 点）；
   - `total > 0` → 「运行中 N」（warning 点，保留现有样式）；
   - 其余 → 「空闲」（info 点）。
3. 点击跳转按来源分流：`scheduleCount > 0` → `/schedule/realtime`；否则 `uploadCount > 0` → `/upload/realtime`；都为 0 时维持现状（跳任务调度实时日志）。
4. 导航「实时日志」徽标（`App.vue:224-226`）同步改为聚合值，上传管理「实时日志」项也支持 `badge`。

**验收标准**：仅启动上传任务时，胶囊显示「运行中 1」且点击进入上传实时日志；后端停机时显示「连接失败」而非「空闲」。

### 3.3 P0-3 执行管理三卡片宽度修正

**方案（两个 Execution 同步修改，保持同构）：**

- 中栏最小宽度从 240px 提到 **300px**：`grid-template-columns: minmax(0, 1.6fr) minmax(300px, 0.9fr) minmax(280px, 1fr)`；
- 堆叠断点从 1100px 提到 **1280px**（1200px 档微调断点删除，避免三档过碎）；
- `el-segmented` 选项文案精简为「增量 / 全量 / 仅 strm」，完整含义由选项下方已有的说明文字承载（现文案已存在，无需新增）；模式说明保留原文。

**验收标准**：1440×900 视口下三个模式选项完整显示不出现省略号；1280px 以下自动堆叠。

### 3.4 P1-4 首访空态引导分层

**方案（任务配置页，调度与上传同构）：**

- 空态按「是否已配置默认运行参数」分两步引导：
  - 未配置参数：参数卡显示空态 +「配置默认参数」主按钮；任务表区域暂不渲染空态 CTA，仅显示说明文案「先完成默认运行参数，再创建任务」；
  - 已配置参数：参数卡显示摘要，任务表空态保留「新建任务」主按钮，**删除工具栏以外的重复按钮或在表格空态与工具栏二选一**（建议保留工具栏主按钮、空态内保留，二者文案区分：工具栏「新建任务」、空态「创建第一个任务」）；
- 上传任务配置页同规则执行（`views/upload/TaskConfig.vue:198-200`）。

**验收标准**：全新数据库首访任务配置页，视线动线为「参数卡 CTA → 表格引导文案 → 工具栏新建」，同屏不出现两个相同的「新建任务」主按钮。

### 3.5 P1-5/P1-6 可访问性细节回补

- 折叠按钮与状态胶囊高度 28px → **32px**（`App.vue`），图标尺寸同步微调；
- `nav-group__title` 颜色 `--el-text-color-placeholder` → `--el-text-color-secondary`（6.0:1，AA 通过）。

### 3.6 P2 打磨项

| # | 方案 |
|---|------|
| 7 | 实时日志页顶部三行统一间距节奏（统一 `--up-strm-space-3`），进度条行改为单行 flex 基线对齐，右侧耗时数值固定最小宽 |
| 8 | 全局配置页空态时压缩 `el-empty` 占位（`:image-size="60"` + 缩短说明），两卡 `align-items: start` 按内容自适应高度，消除右卡大留白 |
| 9 | `index.html` 标题改为「up-video-strm 控制台」 |
| 10 | 用现成的 `.ui-review-shots.mjs` 补全 11 路由 × 明暗 + 折叠态共 23 张基线截图；`manual/images/` 16 张旧图重拍（可与第一轮 P2 遗留合并为一次文档交付） |

---

## 4. 实施路线（建议，未实施）

| 批次 | 内容 | 建议发布级别 | 预估改动面 |
|------|------|--------------|------------|
| 第一批 | P0-1 错误治理 + P0-2 状态聚合（两项都集中在 `api/index.ts` / `App.vue` / store，建议同一批次一次 `minor` 交付） | `minor` | 4 个文件 + 新增 1 个 store |
| 第二批 | P0-3 三卡片宽度（两个 Execution 同步）+ P1-4 空态引导 | `patch` | 4 个文件 |
| 第三批 | P1-5/6 可访问性回补 + P2 全部打磨项 | `patch` | 6 个文件 + 文档截图 |

实施纪律沿用 [AGENTS.md](../../AGENTS.md)：每批独立 commit、逐项 `git add`、测试全绿后交付、按上表递增版本并更新 [CHANGELOG.md](../../CHANGELOG.md)。

## 5. 涉及文件清单（若实施）

| 文件 | 改动 |
|------|------|
| `frontend/src/api/index.ts` | 拦截器错误去重节流 |
| `frontend/src/stores/openlist.ts` | `fetchRunning` 静默透传、网络失败状态 |
| `frontend/src/stores/running.ts`（新增，或并入现有 store） | 双模块运行数聚合 |
| `frontend/src/App.vue` | 离线状态条、三态胶囊、跳转分流、触控目标 32px、分组标题色 |
| `frontend/src/views/schedule/Execution.vue` | silent 透传修正、栅格与断点 |
| `frontend/src/views/upload/Execution.vue` | 同上（同构） |
| `frontend/src/views/schedule/TaskManage.vue`、`views/upload/TaskConfig.vue` | 空态引导分层 |
| `frontend/src/views/{schedule,upload}/RealtimeLog.vue`、`views/config/GlobalConfig.vue` | P2 打磨 |
| `frontend/index.html` | 标题 |
| `frontend/.ui-review-shots.mjs` + `frontend/shots/`、`manual/images/` | 截图基线补全 |
| `docs/rules/frontend.md`、`manual/用户手册.md` | 实施后同步 |
