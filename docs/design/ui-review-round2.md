# docs/design/ui-review-round2.md — 前端 UI 评审与优化方案（第二轮）

> 状态：**P0–P2 已实施（v4.9.0，commit `bde1752`）**；第 7 节为实施后回归问题的修复计划（**未实施**）。
> 上一轮评审见 [ui-redesign-plan.md](ui-redesign-plan.md)（已实施至 v2.1.0）；核心规范见 [AGENTS.md](../../AGENTS.md)；前端工程说明见 [docs/rules/frontend.md](../rules/frontend.md)。

- 评审对象：`frontend/src` 全部视图与样式层（约 6600 行，14 个视图组件）+ 真实界面截图
- 评审日期：2026-11-05
- 基线版本：**4.8.0**（commit `7983f0e`）
- 评审方法：Playwright 1440×900 截图逐页目检 + 问题逐条回源码定位核实；所有结论均已在代码中找到对应行，未凭截图猜测。截图属评审时的临时产物，脚本与图片均未入库，当前工作区已清理（见 P2-10）
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
| 4 | 重命名规则弹窗「集数提取正则」的说明文字被输入框遮挡：`.form-tip` 的 `margin-top: -4px` 在 `.el-form-item__content`（flex 容器）内直接把提示拉进输入框底边。Playwright 实测（1440×900，2026-11-05）：输入框底边 y=413、提示首行顶 y=409，重叠 4px，提示首行上半被裁切 | `views/upload/RenameRules.vue:186-189`（提示）+ `:250`（负外边距） | `.workbuddy/tmp/dialog-before.png`（复现截图） |

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
| 9 | 浏览器标签页标题过期：仍是「up-video-strm 任务调度」，实际已有三个平级模块 | `frontend/index.html:6`（改由 7.4 的动态 `document.title` 方案替代） |
| 10 | 截图基线缺失：评审用的截图脚本与基线图片均未入库，当前工作区已不存在 `frontend/.ui-review-shots.mjs` 与 `frontend/shots/`（曾覆盖 11 路由 × 明暗主题 + 折叠态）；`manual/images/` 16 张截图为第一轮之前的旧界面（第一轮 P2 遗留） | 需重建脚本并入库 |

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
| 10 | 重建截图脚本（11 路由 × 明暗 + 折叠态共 23 张）并纳入仓库，作为后续评审的可重复基线；`manual/images/` 16 张旧图重拍（可与第一轮 P2 遗留合并为一次文档交付） |

### 3.7 P0-4 重命名规则弹窗提示遮挡修复

**根因**：`RenameRules.vue` 的 `.form-tip` 定义了 `margin-top: calc(-1 * var(--up-strm-space-1))`（即 -4px）。该提示是 `el-form-item` 内容区（`.el-form-item__content`，flex 容器、行高 32px）的 flex 子项，换行后本已紧贴输入框下缘，再上提 4px 就直接压进输入框底边——实测输入框底边 y=413、提示首行顶 y=409，首行文字上半被裁切。

**方案（三处，均在 `RenameRules.vue` 单文件内）：**

1. **修正间距**：`.form-tip` 的负外边距改为正值并显式独占一行，杜绝未来再加内联元素时与输入框挤到同一行：

   ```scss
   .form-tip {
     flex-basis: 100%;                    // 独占 flex 一行
     margin-top: var(--up-strm-space-1);  // +4px（原 -4px 是遮挡根因）
     color: var(--el-text-color-secondary); // 由 placeholder 色改为次要色，12px 文字需 ≥4.5:1
   }
   ```

2. **提示归位**：把现挂在「集数提取正则」之后的「可用变量：{season} / {episode} / {ext}…」提示移入**命名模板**表单项的内容区——它解释的是模板字段，放错位置让用户在填模板时看不到提示、填正则时看到两条不相关说明。归位后弹窗内不再有游离于表单项之外的独立提示。
3. **顺带统一**：工具栏的 `.toolbar__hint`（模板变量提示）同步由 placeholder 色改为次要色，遵守第一轮令牌注释「placeholder 仅限占位/禁用，勿用于正文」。

**验证方式**：实现后重放 `.workbuddy/tmp/measure-dialog.mjs` 实测脚本，断言每条 `.form-tip` 的 top ≥ 所属输入框 bottom + 4px；并重截弹窗截图核对视觉。

**验收标准**：提示文字与输入框无任何像素重叠；两条提示各自紧邻其字段（模板变量提示在「命名模板」下、正则示例在「集数提取正则」下）；12px 提示文字对比度 ≥4.5:1。

---

## 4. 实施路线（建议，未实施）

| 批次 | 内容 | 建议发布级别 | 预估改动面 |
|------|------|--------------|------------|
| 第一批 | P0-1 错误治理 + P0-2 状态聚合（两项都集中在 `api/index.ts` / `App.vue` / store，建议同一批次一次 `minor` 交付） | `minor` | 4 个文件 + 新增 1 个 store |
| 第二批 | P0-3 三卡片宽度（两个 Execution 同步）+ P1-4 空态引导 + P0-4 弹窗提示遮挡（单文件小改，也可单独 `fix` 提前交付）+ 第 6 节刷新控件位置统一（与空态同批，避免同一文件反复改） | `patch` | 7 个文件 |
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
| 截图脚本（重建）与 `frontend/shots/`、`manual/images/` | 截图基线补全 |
| `frontend/src/views/upload/RenameRules.vue` | 正则提示遮挡修复 + 提示归位（见 3.7）与刷新控件位置统一（见第 6 节） |
| `frontend/src/views/schedule/TaskHistory.vue`、`views/schedule/TaskManage.vue` | 刷新控件位置统一（见第 6 节） |
| `docs/rules/frontend.md`、`manual/用户手册.md` | 实施后同步 |

---

## 6. 追加议题：刷新类控件的位置规范（2026-11-05 补充）

> 起因：评审后追加确认「刷新按钮位置是否需要调整」。**位置按用户偏好定为工具栏右侧**（不在左侧），本节只统一「同系统内左右混用、覆盖面不齐、形态发散、组内次序未定义」这四件事。级别 **P2（一致性，不影响功能）**，建议并入第二批交付（与任务配置页空态改动同批，避免同一文件反复改）。

### 6.1 现状盘点（逐处核实）

| 页面 / 组件 | 控件 | 位置 | 形态 |
|-------------|------|------|------|
| `schedule/TaskHistory.vue:116-121` | 刷新 | 工具栏**右侧**（该侧唯一按钮） | 默认按钮 |
| `schedule/TaskManage.vue:448-476` | **无刷新** | — | — |
| `upload/TaskConfig.vue:165-172` | 刷新 | 工具栏**左侧首位** | 默认按钮 |
| `upload/RenameRules.vue:126-128` | 刷新 | 工具栏左侧首位（后接提示文案） | 默认按钮 |
| `schedule/Execution.vue:471-473` | 刷新「正在执行」 | 卡片标题右侧 | `link` 文字按钮 |
| `upload/Execution.vue:297` | 刷新「正在执行」 | 卡片标题右侧 | `link` 文字按钮 |
| `Settings/index.vue:104` | 刷新 | 卡片标题右侧 | `link type="primary"` |
| `config/GlobalConfig.vue:379-381` | 刷新缓存 | 服务器卡头部操作组 | `plain` 按钮 |
| `schedule/components/DirTreePanel.vue:206` | 刷新缓存 | 面板工具区 | 默认按钮 |
| `upload/components/RemoteDirPanel.vue:99-101` | 刷新 | 面板头部 | `small` 按钮 |
| `views/schedule/RealtimeLog.vue`、`views/upload/RealtimeLog.vue` | 仅「重新连接 / 重连」 | 连接状态区旁 | `link` / 默认按钮 |

> 位置定案：页面级刷新统一放**工具栏右侧组首位**（R1）。上表中「左侧」的 2 处需迁移，「无刷新」的 1 处需补齐，其余保持。

### 6.2 问题定性

1. **页面级刷新左右混用（不是「右侧错」，而是不统一）**：任务历史在右侧、上传模块两个列表页在左侧，同系统两套约定，用户每换一个模块都要重新找一次位置。按用户偏好统一为**右侧**后，需要补的是一条「右侧组内次序」规则，否则刷新容易被误读为主操作。
2. **覆盖面不齐**：`TaskManage` 完全没有刷新，而它的数据（任务列表）会因外部操作（目录缓存、其他端修改）变化；上传任务配置页有刷新，同一层级的两个模块行为不一致。
3. **同语义五种形态**：默认按钮 / `link` / `link primary` / `plain` / `small`，图标+文字与纯文字混用；用户需要在不同页面重新识别「哪个是刷新」。
4. **提示文案与按钮挤在一起**：`RenameRules` 的模板变量提示与刷新同排，容易被读成「刷新说明」而非页面级帮助信息。刷新移到右侧后，提示文案自然独占左侧，问题随之消解。

### 6.3 摆放规范（建议写入 `docs/rules/frontend.md`）

- **R1 页面级列表刷新**：固定在工具栏**右侧组首位**（批量操作与主操作的左侧），使用默认按钮（图标 + 文字）、不加主色；主操作始终固定在最右端。刷新与主操作间距不小于 `--up-strm-space-3`（12px），必要时加 1px 竖分隔线，确保刷新不会被误读为主操作。
- **R2 卡片 / 局部刷新**：位于卡片标题右侧，使用 `link` 文字按钮，不抢卡片主按钮位置。
- **R3 资源级动作**（刷新缓存、重新连接）：归属该资源的头部操作组，与同组按钮保持同一形态（`plain` 或 `small`），不与页面级刷新混排。
- **R4 实时推送页不设刷新**：实时日志靠 WebSocket 推送，只保留「重新连接」，且紧邻连接状态标签；避免出现「刷新」与「重连」两个语义重叠的入口。
- **R5 刷新行为**：成功不弹 toast（列表静默更新）；失败统一交给全局错误治理（P0-1）；刷新期间按钮 `loading` 并禁止重复点击。

### 6.4 具体调整

| 文件 | 调整 |
|------|------|
| `views/schedule/TaskHistory.vue` | 位置保持右侧（作为规范基线）；该侧目前只有刷新一个按钮，未来加筛选 / 导出时刷新仍留组首位 |
| `views/upload/TaskConfig.vue` | 刷新从 `toolbar__left` 移到 `toolbar__right` 首位（主操作「新建任务」左侧），左侧只留搜索 |
| `views/schedule/TaskManage.vue` | 工具栏右侧组首位补「刷新」（`:loading="loading"`，位于批量删除之前），补齐与上传任务配置页的能力差 |
| `views/upload/RenameRules.vue` | 刷新移到右侧组首位；模板变量提示留在左侧（独占，避免与按钮争夺扫读焦点） |
| `views/schedule/Execution.vue`、`views/upload/Execution.vue` | 位置不动（已符合 R2），仅按 P0-1 修 `silent` 透传，使刷新失败不再弹窗 |
| `views/Settings/index.vue` | 位置不动（R2），形态从 `link primary` 收敛为 `link`（主色留给真正的主动作） |
| `components/DirTreePanel.vue`、`upload/components/RemoteDirPanel.vue` | 均为面板工具条内的「刷新缓存」，尺寸统一为 `small`，避免同一交互在抽屉里一大一小 |
| `config/GlobalConfig.vue` | 保持 `plain`（与同组「编辑 / 删除 / 测试连接」一致，符合 R3） |

### 6.5 验收标准

- 三个列表页（任务配置 / 上传任务配置 / 重命名规则）工具栏结构一致：左侧「搜索 / 筛选」，右侧「**刷新 → 批量操作 → 主操作**」，主操作恒在最右端。
- 任务历史与上传历史的刷新入口位置、形态一致；同一页面不出现两个刷新入口。
- 键盘 Tab 顺序为「搜索 → 刷新 → 批量操作 → 主操作」，不因位置调整产生跨区跳跃。
- 刷新按钮 100% 有 loading 态，且刷新失败时无独立 toast（走全局离线状态条）。

> 说明：
> 1. 不采用「顶栏全局刷新」——顶栏已有运行状态胶囊与 10s 自动轮询，再加全局刷新会与自动刷新语义冲突。
> 2. 不采用「表格右上角悬浮刷新」——会遮挡表头，并与工具栏、分页形成三个操作区。
> 3. 不在右侧**末端**另设纯图标刷新——末端位置必须留给主操作，否则会削弱主操作的固定位置与点击命中率；刷新统一以「图标 + 文字」出现在右侧组首位。


---

## 7. 实施后回归问题与修复计划（v4.9.0，2026-11-05 晚补充）

> 背景：v4.9.0（commit `bde1752`）已按本方案实施完毕。实施后回归发现 4 个问题，本节逐条以 Playwright 实测定位（脚本留存于 `.workbuddy/tmp/`），给出修复计划。行号均基于 v4.9.0 代码。
>
> **状态：已于 v4.9.1 按本节方案修复**（见 CHANGELOG）：7.1 两个执行管理页卡片区 `flex: none`；7.2 重建并同步 `frontend/dist`、`backend/frontend/dist`，`.toolbar` 原语收敛到 `global.scss` 并删除五个列表页重复定义；7.3 采用方案 A（移除选中项 `font-weight: 600`，加左侧 2px 主色指示条）；7.4 顶栏标题改「模块 · 页面」并新增动态 `document.title`。

### 7.1 执行管理竖排时遮挡「正在执行」卡片（P0 级，缺陷）

**实测**（1440×900 起，逐步收窄）：

| 视口 | schedule 执行管理 | upload 执行管理 |
|------|-------------------|-----------------|
| 1440 / 1366 | 一行三卡，`height: clamp(380px, 52vh, 560px)`（实测 468px），面板内部滚动——**这是既定设计，保留** | 一行三卡，高度随内容（149 / 342 / 331px），正常 |
| ≤1280 竖排 | `.exec-workspace` 被压缩为 630.6px（内容实际需要 992px），面板 2（y=408–728）与面板 3（y=744–1064）溢出容器，**「正在执行」卡（y=718.6 起）压在面板之上，重叠 345px** | 「正在执行」卡被 flex 压缩到 **2px 高**（y=950.6–952.7），内容完全不可见 |

**根因**：两个页面根节点（`.page page--fill exec-page` / `.page upload-execution`）都是**可滚动的 flex 列容器**，子项默认 `flex-shrink: 1`。当子项总高超过视口，浏览器不是让容器滚动，而是先按比例压缩子项：

- schedule：`.exec-running` 已是 `flex: none`（:748），于是被压的是 `.exec-workspace`——但网格行高不会跟随收缩，面板溢出容器底边，与下一个兄弟（正在执行卡）互相压盖；
- upload：`.upload-execution__cards` 与 `.running-card` 都没有豁免，running 卡被压到 2px。

**方案**（两个文件各加一行）：

1. `views/schedule/Execution.vue`：`.exec-workspace` 增加 `flex: none`（基础规则，两种模式均生效——行模式它有确定高度不受影响；竖排模式不再被压缩，滚动交给 `.exec-body`）。
2. `views/upload/Execution.vue`：`.upload-execution__cards` 与 `.running-card` 各增加 `flex: none`。
3. 可选治本：在 `styles/global.scss` 增加约定「滚动型 flex 列容器的直接子块不参与高度分配」：`.page > * { flex-shrink: 0; }`（若担心波及其他页面，可只改两个执行页）。

**验收**：1440 / 1280 / 1180 / 1024 四档宽度下「正在执行」卡完整可见、与三卡片无任何像素重叠（实测脚本 `overlapRunning ≤ -16`）；内容超高时出现的是容器滚动条而非子块压缩。

### 7.2 上传任务配置工具栏对齐与间距（核实：当前代码已合规）

**实测**（Playwright，1440 / 1280 / 1100 / 1024 / 900 五档视口）：

- `.toolbar` 均为 `display: flex; justify-content: space-between`，按钮组右缘 = 内容区右缘（1416，含 `.page` 24px 内边距），完全靠右；
- 工具栏与列表卡间距恒为 **12px**（`gap: var(--up-strm-space-3)`）；
- 五个列表页横向审计（schedule-tasks / upload-tasks / upload-rules / schedule-history / upload-history）：按钮组全部右缘对齐，无越界、无水平滚动条。

**结论**：观察到的「没靠右、没间距」在当前 dev 代码中**无法复现**。最可能原因是观察环境为旧构建：`dist/` 产物早于实施提交（`bde1752`，22:10），桌面安装版与后端 `:8000` 端口提供的都是 dist 产物；vite dev（5173/5175）才是新代码。

**方案**：

1. **环境核对（先做）**：确认观察入口是 dev server 还是 8000 端口 / 桌面版；若是后者，先 `npm run build` 重新构建并重启后端（或重新打包）再核对。
2. **防漂移加固（建议做）**：`.toolbar` 样式目前在 4 个页面各自定义一份（TaskManage :758 / TaskConfig :274 / RenameRules / TaskHistory，其中 TaskHistory 是 `justify-content: flex-end` 变体）。收敛为 `styles/global.scss` 的全局工具栏原语（`.toolbar / .toolbar__left / .toolbar__right` + 与后续内容的 12px 间距），四个页面删除各自定义——规则只写一处，杜绝再次漂移。
3. 若完成 1 后仍可复现：记录视口宽度 + 截图，再按实测定位（勿凭印象改样式）。

**验收**：四个列表页在任意视口宽度下按钮组右缘与内容区右缘对齐、与列表间距 12px，且样式只存在于 `global.scss` 一处。

### 7.3 导航选中态「字体像换了」（P2 级，观感）

**实测**：选中项与未选中项的 computed `font-family` **逐字符完全一致**，仅 `font-weight` 400 → 600（`App.vue` `.nav-page--active`）。字体栈没有变——观感差异来自 Windows 字体能力：

- 全局字体栈 `'Helvetica Neue' → Helvetica → 'PingFang SC' → 'Hiragino Sans GB' → 'Microsoft YaHei' → Arial`，在 Windows 上前四个全部不存在，**中英文统一落到微软雅黑**；
- 微软雅黑只有 400 / 700 两档字重，`600` 被映射到 Bold；
- 14px 的雅黑 Bold 笔画显著加重，看起来像「换了字体」。**在当前字体栈下这是无解的——Windows 不存在「半粗」中文字重**（canvas 实测 400/500/600/700 的 CJK advance 宽度完全相同，无法用字重做出中间档）。

**方案（二选一）**：

- **方案 A（零依赖，可立即做）**：选中态强调改用「主色文字 + 12% 主色底（现状已有）+ 左侧 2–3px 主色指示条」，移除 `font-weight: 600`。理由：导航是位置指示而非内容强调，VS Code、GitHub 侧栏均不以字重表达选中；附带好处是文字零宽度变化、零渲染开销。
- **方案 B（根治，若坚持要「轻加粗」）：自托管可变字体**——MiSans 或 Noto Sans SC Variable（免费商用 / OFL），woff2 子集（常用汉字 + Latin，约 2–3MB）随安装包分发，写入 `global.scss` 字体栈。此后 500/600 是真实字重，且全站十余处 `font-weight: 600`（卡片标题、表头、导航徽标等）同时从「雅黑 Bold 映射」升级为真实 Semibold，观感统一提级。改动面：字体文件 + `global.scss` + 打包配置，建议单独立项（`minor`）。

**验收**：方案 A——选中项与未选中项同字重同宽度，仅颜色 / 底色 / 指示条变化；方案 B——DevTools 中 600 渲染为真实 Semibold，字体栈含自托管字体且离线可用。

### 7.4 顶栏标题改为「一级 · 二级」（P1 级，信息架构）

**实测**：`.app-topbar__title` 只显示 `route.meta.title`（如「任务配置」，`App.vue:125`），模块名只体现在侧栏，顶栏缺失层级上下文。

**方案**（`App.vue` 单文件）：

1. `pageTitle` 计算改为拼接：存在 `currentModule` 时 = `` `${currentModule.label} · ${route.meta.title}` ``；单页模块且页面与模块同名（全局配置）时只显示「全局配置」，避免「全局配置 · 全局配置」；`/settings` 无所属模块，显示「设置」。
2. 分隔符统一「 ` · ` 」（空格 + 间隔号 + 空格），符合中文排版习惯。
3. 顺带收尾 P2-9（浏览器标签页标题过期）：新增 `watchEffect(() => { document.title = pageTitle.value === 'up-video-strm' ? 'up-video-strm 控制台' : `${pageTitle.value} - up-video-strm` })`，标签页随页面联动，替代 P2-9 的静态改法（二者取其一，推荐动态方案）。
4. `router/index.ts` 的 `meta.title` 保持单页名不变——拼接只在壳层做，不影响侧栏高亮与 `isActive` 判断。

**验收**：任务调度四页标题分别为「任务调度 · 任务配置 / 执行管理 / 实时日志 / 任务历史」，上传管理同理；全局配置显示「全局配置」；设置显示「设置」；浏览器标签页标题同步变化。

### 7.5 批次建议

| 顺序 | 内容 | 建议级别 |
|------|------|----------|
| 1 | 7.1 布局遮挡（缺陷，影响可用性） | `fix:` · patch |
| 2 | 7.4 标题拼接（App.vue 单文件小改，可与 1 同批） | 并入同批 patch |
| 3 | 7.2 环境核对 + 工具栏原语收敛到 global.scss | 并入同批 patch |
| 4 | 7.3 方案 A 立即可做；方案 B（可变字体）单独立项 | patch / 单独 minor |

实施纪律沿用 [AGENTS.md](../../AGENTS.md)：每批独立 commit、逐项 `git add`、`npm run type-check` + 构建（涉及产物时 `npm run build`）通过后交付，版本按最高级别递增。
