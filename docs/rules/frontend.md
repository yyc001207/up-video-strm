# docs/rules/frontend.md — 前端工程说明

> 核心规范见 [AGENTS.md](../../AGENTS.md)；项目总览见 [project.md](project.md)；后端实现见 [backend.md](backend.md)。

## 技术栈

- Vue 3.5（`<script setup>` + TypeScript）+ Vite 8 + Element Plus 2.14（中文 locale `zhCn`，含 `@element-plus/icons-vue`）+ Pinia 4 + vue-router 5 + axios + dayjs + Sass
- Vite 开发服务器 `/api` 代理到后端并透传 WebSocket；包名 `up-video-strm-web`，npm / pnpm 均可
- 依赖清单：[frontend/package.json](../../frontend/package.json)

## 目录结构

```text
frontend/
├── src/
│   ├── main.ts / App.vue / router/index.ts  # 入口、壳层（侧栏 + 顶栏）、路由
│   ├── api/                # axios 实例 + openlist / uploader / automation / desktop 接口封装
│   ├── stores/             # Pinia（openlist 业务 / running 运行状态聚合 / theme 主题）
│   ├── views/
│   │   ├── schedule/       # 任务调度模块：四个路由页面 + components/DirTreePanel.vue
│   │   ├── upload/         # 上传管理模块：任务配置 / 重命名规则 / 执行管理 / 实时日志 / 任务历史 + components/RemoteDirPanel.vue
│   │   ├── automation/     # 自动化任务模块：任务配置 / 执行管理 / 实时日志 / 任务历史
│   │   ├── config/         # 全局配置模块：服务器配置 + 视频/字幕格式 + 123 云盘凭据
│   │   └── Settings/       # 桌面设置页
│   ├── components/         # 通用组件（StatusDot 状态点 / LogViewer 日志终端 / ThemeToggle 主题切换）
│   ├── types/ / utils/     # 类型（openlist / uploader / automation / desktop）、工具（date / ws）
│   └── styles/             # variables（--up-strm-* 令牌）/ element-reset（EP 变量映射与表格统一）/ dark / global
├── index.html              # 标题「up-video-strm 控制台」+ 首屏主题预加载
├── vite.config.ts          # 别名 @ → src；dev server :5173；/api 代理 → 127.0.0.1:8000（ws 透传）
├── .env.development / .env.production / tsconfig*.json
└── package.json / package-lock.json / pnpm-lock.yaml
```

## 路由与壳层

| 路由 | 页面文件 | 说明 |
|------|----------|------|
| `/` | — | 重定向到 `/schedule/execution` |
| `/schedule/execution` | `views/schedule/Execution.vue` | 执行管理：选任务、设执行模式并启动 |
| `/schedule/config` | — | 旧路径兼容，重定向到 `/config` |
| `/config` | `views/config/GlobalConfig.vue` | 全局配置：服务器配置 + 视频/字幕格式 + 123 云盘凭据 |
| `/schedule/tasks` | `views/schedule/TaskManage.vue` | 任务 CRUD、快速添加、批量删除、默认运行参数 |
| `/schedule/history` | `views/schedule/TaskHistory.vue` | 任务历史列表与详情、日志回放 / 打开日志文件夹 |
| `/schedule/realtime` | `views/schedule/RealtimeLog.vue` | WebSocket 实时日志 |
| `/upload` | — | 重定向到 `/upload/tasks` |
| `/upload/tasks` | `views/upload/TaskConfig.vue` | 上传任务 CRUD：本地目录、云端目录、集数映射、命名规则 |
| `/upload/rename` | `views/upload/RenameRules.vue` | 重命名规则 CRUD、可选自定义集数正则与模板预览 |
| `/upload/execution` | `views/upload/Execution.vue` | 执行管理：三卡片（选任务 / 执行参数 / 已选任务）+ 正在执行列表 |
| `/upload/realtime` | `views/upload/RealtimeLog.vue` | WebSocket 实时日志：6 阶段进度与逐文件输出，支持批量排队 |
| `/upload/history` | `views/upload/TaskHistory.vue` | 上传历史：按任务汇总 → 执行记录 → 文件明细、日志回放 / 打开日志文件夹、重跑 |
| `/automation` | — | 重定向到 `/automation/tasks` |
| `/automation/tasks` | `views/automation/TaskConfig.vue` | 自动化任务 CRUD：绑定上传/STRM 任务、校验目录检测与上传/生成参数 |
| `/automation/execution` | `views/automation/Execution.vue` | 执行管理：批量启动/停止、运行阶段与待校验文件、5 项时间参数（写回任务配置） |
| `/automation/realtime` | `views/automation/RealtimeLog.vue` | WebSocket 实时日志：按任务切换、最近 200 帧回放、异常通知 |
| `/automation/history` | `views/automation/TaskHistory.vue` | 运行历史：按任务/状态筛选，详情抽屉、日志回放、失败文件写回待校验 |
| `/settings` | `views/Settings/index.vue` | 桌面设置（desktop 外壳导航仍按此路径跳转） |
| 其它 | — | 重定向到 `/` |

- 侧栏由 [App.vue](../../frontend/src/App.vue) 的 `modules` 数据驱动（模块 → 分组 → 页面），当前四个平级模块：「全局配置」（`/config`）、「任务调度」（`/schedule/*`）、「上传管理」（`/upload/*`）与「自动化任务」（`/automation/*`）；单页模块不显示分组标题，新增模块只需追加一项数据。折叠状态存 `localStorage` 的 `up-video-strm-sidebar-collapsed`。导航选中态只用「主色文字 + 12% 主色底 + 左侧 2px 主色指示条」表达，**不使用 `font-weight` 加重**（Windows 微软雅黑会把 600 映射为 Bold，导致文字变宽跳位）。
- 顶栏标题按「模块 · 页面」拼接（`pageTitle`），单页模块与页面同名只显示一次（如「全局配置」），无模块归属时显示页面名（如「设置」）；描述取路由 `meta.description`；`document.title` 同步为「`<页面标题> - up-video-strm`」，默认「up-video-strm 控制台」。默认进入「全局配置」（`/` 与未匹配路由均重定向 `/config`）。顶栏右侧不提供运行状态入口；导航「实时日志」仍按 [stores/running.ts](../../frontend/src/stores/running.ts)（聚合三模块运行数：调度/上传 `listExecutions({status:'running'})` 与自动化 `GET /active`，30s 轮询且页面隐藏时跳过）显示运行数徽标。后端不可达时顶栏下方展示可关闭的 `el-alert`「无法连接后端服务，正在自动重试…」，恢复后消失。
- 原「五页签」语义改为独立路由页面：进入页面即按需加载，切换路由即刷新，不再依赖 tab 的 `reload`。
- 执行管理 → 实时日志通过路由 query 传参：任务调度为 `execs`（JSON 数组，元素 `{executionId, taskId, taskName, launch}`），上传管理为 `execs`（JSON 数组，元素 `{executionId, taskId, taskName}`）。实时日志页先建立 WebSocket，`onOpen` 后再调用 `startExecution`（保证先连日志再启动）；上传管理多个执行按队列串行启动与切换。
- 时间统一按**北京时间**解释与展示：一律使用 `utils/date.ts` 的 `formatDateTime`（`YYYY-MM-DD HH:mm:ss`）、`formatDate`（`YYYY-MM-DD`）或 `beijingMillis`（耗时计算），不要直接调用 dayjs 格式化；后端返回无时区墙钟字符串时按 `Asia/Shanghai` 解析，自带 Z / 偏移则先换算到北京时间。
- 列表页工具栏统一使用 `styles/global.scss` 的 `.toolbar` 原语：`.toolbar__left` 放搜索/筛选/提示，`.toolbar__right` 放操作组且恒贴右（`margin-left: auto`），间距 12px / 组内 8px；页面样式只保留专有规则（如 `.toolbar__keyword`、`.toolbar__hint`），不再各自定义布局。
- 执行类页面的卡片区（调度 `.exec-workspace`、上传 `.upload-execution__cards` 与 `.running-card`）固定 `flex: none`：窗口变矮时不压缩卡片，内容过高由外层容器滚动。
- 列表页统一使用 `styles/global.scss` 的列表页骨架：根 `.page.page--fill.list-page`（flex 列、`overflow: hidden`）、表格卡 `.list-card`、滚动容器 `.list-card__table`、分页 `.list-card__pager`。所有列表默认每页 20 条（可选 10 / 20 / 50），筛选或数据变化后回到第 1 页；滚动条只出现在表格卡片内部，页面上不得出现整页滚动条。`.page--fill` 基础样式不含纵向 `gap`，工具栏与列表卡之间的间距由页面自身提供（如 `.automation-tasks { gap: var(--up-strm-space-4) }`）。
- 列表筛选约定：工具栏 `__left` 放「关键字 / 状态 / 时间范围」筛选，`__right` 放操作按钮与刷新；筛选在客户端完成（单模块数据量小），详情与执行记录仍走服务端分页。时间范围按北京时间自然日 `[开始日 00:00:00, 结束日 23:59:59]`，取「完成时间 → 开始时间 → 创建时间」中第一个可用值；「未执行」用哨兵值（任务调度 `'unexecuted'`、上传历史 `last_execution?.status ?? 'none'`）。

## 页面与组件

- `Execution.vue`：一行三卡片（选择任务 / 执行参数 / 已选任务），执行模式用 `el-segmented`（增量 / 全量 / 仅 strm）；「选择任务」卡支持关键字过滤，底部右侧为「全选 / 取消全选」（只作用于当前筛选结果中的可选任务，左侧显示「可选 N · 已选 N」）；「已选任务」卡承载摘要与「清空选择 / 执行任务」操作；「正在执行」表支持查看日志与取消，5s 轮询刷新。
- `GlobalConfig.vue`：全局配置模块单页——左侧单服务器卡片（无服务器时为空态 + 新增；标题右侧显示连通状态标签：在线 / 离线 / 未配置 / 检测中，进入页面及每 60s 轮询探测；卡片展示服务器地址 / Token 是否配置 / 父级目录标签，可编辑、刷新缓存、删除），右侧视频与字幕格式摘要卡 + 编辑抽屉；底部 123 云盘「摘要卡 + 编辑弹框」：卡头为状态标签与测试连接 / 编辑 / 删除按钮（删除需二次确认，调用 `DELETE /api/upload/config` 清空凭据与缓存 Token），卡体展示 Client ID、脱敏后的 Client Secret、Token 状态与过期时间（`formatDateTime`），未配置时为空态「立即配置」，编辑入口打开 `el-dialog` 修改 Client ID / Secret。三张卡片头部的操作按钮统一为 `plain`（镂空）风格，删除一律 `type="danger" plain`。
- `TaskManage.vue`：页顶部「默认运行参数」卡（最大并发、限流、SSL 校验、输出目录前缀与根目录、OpenList 远程目录前缀）+ 编辑抽屉（配置全局生效，任务未单独设置时使用）；工具栏分组（搜索 / 新建、快速添加、批量删除）；表格任务名与路径双行；快速添加使用 `DirTreePanel.vue`（目录树勾选 + 搜索下钻 + 缓存刷新）。
- `TaskHistory.vue`：列表（每任务最近执行 + 状态点，工具栏三项筛选：关键字 / 时间范围 / 状态，客户端分页 20 / 10 / 50）与页面级详情（服务端分页 20、日志抽屉、「日志文件夹」在资源管理器中打开日志目录）；顶部 `.page-hint` 说明筛选与分页规则。
- `RealtimeLog.vue`：两模块共用同一套页面骨架（`views/schedule/RealtimeLog.vue` 与 `views/upload/RealtimeLog.vue`，类名与样式一致）：顶部说明段（`.realtime-page__desc`）→ 工具条（`.realtime-toolbar`：执行选择 260px、连接状态、启动中、执行状态点 /「无运行中任务」；右侧「重连 / 清空 / 打开日志文件夹」）→ 进度卡（`.progress-card`：6 个统计项 + 1 个宽项「当前文件 / 当前任务」）→ 日志工具条（`.log-toolbar`：级别筛选、关键字、行数；右侧「返回执行管理」）→ 日志区（`LogViewer`）；状态帧结束即断开并提示前往任务历史。
- 通用组件：`StatusDot.vue`（执行状态点 + 文案）、`LogViewer.vue`（可复用日志终端）、`ThemeToggle.vue`（浅色 / 深色 / 跟随系统）。
- `TaskConfig.vue`（上传管理）：上传任务列表与抽屉编辑（任务名 / 本地目录 / 云端目录 / 输出季数 / 源起始集号 / 命名规则）；工具栏支持任务名称搜索与「批量删除」，列表使用 `list-page` 骨架并客户端分页（20 / 10 / 50），滚动只在卡片内部；本地目录可点「浏览」调用桌面端 `window.pywebview.api.pick_directory()` 快速选择（网页版提示手动输入）；云端目录不预填 `/test`，用 `RemoteDirPanel.vue` **逐级导航**选择（打开只请求根目录一次，点击目录行进入下级、每次进入仅一次接口；面包屑与「返回上级」可回退；底部醒目展示当前目录，确认后回填；只读浏览、不自动建目录，提示仅使用 `/test`）；集号换算提示为「季内集号 = 绝对集号 − 起始集号 + 1」。
- `RenameRules.vue`（上传管理）：规则列表 + 模板编辑对话框（变量 `{season}` / `{episode}` / `{ext}`，`:02` 补零）+ 文件名预览（显示解析出的绝对集号或原因）；工具栏支持规则名称搜索与「批量删除」，列表同样分页 20 / 10 / 50；被任务引用的规则不可删除（后端返回具体规则名）。
- `Execution.vue`（上传管理）：与任务调度执行管理采用同一套骨架与样式常量——`exec-page / exec-body / exec-workspace / exec-panel / exec-panel__head / exec-panel__body / exec-panel__footer`，卡片区高度固定（`clamp(380px, 52vh, 560px)`），勾选数量变化不改变卡片高度，列表超高时在卡片内部滚动；三卡头部均有标题与一句用途说明；「选择任务」卡支持名称 / 目录关键字搜索，底部右侧「全选 / 取消全选」+ 左侧「可选 N · 已选 N」；「已选任务」卡头部与摘要均显示已选数量，可移除或清空；执行参数为冲突策略（跳过 / 覆盖 / 追加后缀）、并发上传、失败重试、试运行，底部带参数说明；批量创建执行记录后跳转实时日志页，由 WS 连接成功后逐个启动；「正在执行」表 5s 轮询，可查看日志或取消。
- `RealtimeLog.vue`（上传管理）：与「任务调度 · 实时日志」共用同一套页面骨架与样式（类名 `.realtime-page / .realtime-toolbar / .progress-card / .log-toolbar / .log-area`，见上）：说明段 → 工具条 → 7 项进度卡（文件总数 / 成功 / 跳过 / 失败 / 已上传 / 用时 / 当前文件）→ 日志工具条（级别「全部级别 / 信息 / 警告 / 错误」、关键字、行数、返回执行管理）→ 日志终端；状态帧结束后自动切到下一个排队执行，全部结束停留回放最近日志。无执行记录时展示「无运行中任务」而不是「运行中」；WS 连接建立后若执行已结束，直接显示最终状态并断开连接。
- `TaskHistory.vue`（上传管理）：与「任务调度 · 任务历史」采用同一套列表结构（顶部 `.page-hint` 说明 + `.toolbar` 筛选 + `.list-card` 表格 + `.list-card__pager` 分页）：任务名主行 + 本地目录副行（悬停显示云端目录）、状态彩色圆点、文件计数右对齐、耗时、执行时间、执行次数与右侧固定「详情」；工具栏筛选关键字 / 时间范围 / 状态（成功 / 失败 / 已取消 / 未执行）三项，客户端分页 20 / 10 / 50；详情页展示该任务全部执行记录（状态 / 冲突策略 / 文件统计），可查看文件粒度明细抽屉、日志回放 / 打开日志文件夹，并按原执行固化参数重跑（跳转实时日志自动启动）。
- 自动化任务四页：`TaskConfig.vue`（列表服务端分页 + 抽屉编辑；绑定上传/STRM 任务时被占用项置灰并显示绑定者；上传/STRM 任务选择框未选中时为 `null`（不回显 0）；「检测」按钮调用 `POST /tasks/check-dir` 展示目录一致性与前 20 个文件样例；运行中任务每 5s 自动刷新；根节点 `.automation-tasks` 用 `gap` 补齐工具栏与列表卡间距；抽屉仅保留上传并发 / 失败重试 / 生成模式，5 项时间参数移至执行管理）、`Execution.vue`（与「任务调度 · 执行管理」同一套三栏骨架 `exec-page / exec-body / exec-workspace / exec-panel`：左「选择任务」（底部含「全选 / 取消全选」「重置指纹」「清空待校验」）、中「执行参数」（可见性轮询间隔 / 可见性等待上限 / 空闲等待上限 / 阶段超时 / 轮次间隔，留空沿用任务配置，提交时写回任务配置并持续生效）、右「已选任务」（摘要、清空选择 / 启动）；启动成功后自动跳转 `/automation/realtime?task_id=`；仅当存在运行中任务且页面可见时每 5s 轮询 `GET /active`，轮次结束相位变化时静默刷新任务行）、`RealtimeLog.vue`（与「任务调度 · 实时日志」共用 `.realtime-page / .realtime-toolbar / .progress-card / .log-toolbar / .log-area` 骨架：7 项摘要为轮次 / 待校验 / 已校验 / 缺失文件 / 当前阶段 / 执行状态 / 用时与当前任务；工具条「重连 / 清空 / 打开日志文件夹」，日志工具条级别 / 关键字 / 行数 / 返回执行管理；`connectAutomationWs(taskId)` 连接 `/api/automation/ws/{task_id}`，status 帧携带 `pending`/`checked`/`missed` 时同步摘要，alert 使用常驻通知；日志含 A/B 镜像行（`[A#id]` / `[B#id]`）；任务未运行时自动回放最近一轮日志）、`TaskHistory.vue`（服务端分页，任务 / 状态 / 时间范围筛选（`start_time`/`end_time` 传 YYYY-MM-DD）；表格展示轮次、阶段、新增/待校验/已校验/跳过、缺失文件与 A/B 执行摘要；详情抽屉展示错误码/错误信息/缺失文件清单，日志抽屉回放该轮日志文件，失败记录可「重试失败」写回待校验；工具栏含「日志文件夹」）。
- 任务调度 / 上传管理的「执行管理」与「任务历史」表格均新增「触发方式」列：`trigger_source === 'automation'` 时显示自动化任务名（`trigger_name`），否则显示「手动」；两者的任务历史工具栏均提供「日志文件夹」入口。

## 设计与令牌

- 颜色一律使用 `var(--el-*)`（Element Plus 变量在 `styles/element-reset.scss` 中映射为设计色板）；壳层尺寸、间距、圆角、字号、阴影使用 `var(--up-strm-*)`（定义于 `styles/variables.scss`，暗色阴影在 `styles/dark.scss` 覆盖）。
- 表格统一：行高 40px、表头 12px、计数列右对齐 `font-variant-numeric: tabular-nums`、`0/0` 显示为 `—`。
- 交互细节：`:focus-visible` 焦点环；尊重 `prefers-reduced-motion`；删除类确认弹窗写明对象、数量与不可恢复。
- 设计依据：[docs/design/ui-redesign-plan.md](../design/ui-redesign-plan.md)。

## 接口与状态

- axios 实例：[api/index.ts](../../frontend/src/api/index.ts)（响应拦截统一拆包 `code === 200`；错误提示按文案 3s 去重；请求 config 传 `{ silent: true }` 时不弹提示，供轮询使用）；业务接口：[api/openlist.ts](../../frontend/src/api/openlist.ts)；桌面接口：[api/desktop.ts](../../frontend/src/api/desktop.ts)（含 `openLogDir('openlist' | 'upload' | 'automation')`，调用 `POST /api/desktop/open-log-dir` 在资源管理器中打开对应日志目录；网页版返回 400 提示仅 Windows 本地环境支持）。
- 后端 API 基址由 `VITE_API_BASE_URL` 控制（默认 `/api`）。
- Pinia store：[stores/openlist.ts](../../frontend/src/stores/openlist.ts)（业务，含 `runningCount` 与 `fetchRunning(silent)`）、[stores/running.ts](../../frontend/src/stores/running.ts)（壳层运行状态聚合：三模块运行中数量、离线判定与导航徽标；每 30s 轮询且页面隐藏时跳过）、[stores/theme.ts](../../frontend/src/stores/theme.ts)（浅色/深色/跟随系统，localStorage 记忆，键名 `up-video-strm-theme`，首屏无闪烁）。
- WebSocket 工具：[utils/ws.ts](../../frontend/src/utils/ws.ts)，连接 `ws://.../api/openlist/ws/{execution_id}`；`connectAutomationWs(taskId)` 连接 `ws://.../api/automation/ws/{task_id}`。
- 桌面外壳导航桥：[main.ts](../../frontend/src/main.ts) 把路由挂到 `window.__upVideoStrmNavigate(path)`，托盘菜单「设置…」通过它直接切页而不整页重载（后端 [desktop.py](../../backend/app/desktop.py) 调用）。

## 常用命令

安装、启动与构建命令见 [README.md 快速开始](../../README.md#方式二源码运行)（`npm run build` = `vue-tsc` + `vite build`）。

- 本地完整类型检查：`npx vue-tsc -b --force`（`tsconfig.json` 为 solution 风格，裸 `vue-tsc` 不会真正检查 `src`）。
- TypeScript 6 起 `baseUrl` 弃用，`tsconfig.app.json` 已显式设置 `ignoreDeprecations: "6.0"`。
- 受限环境（如沙箱）中 Vite 构建可能因 `exec("net use")` 报 `spawn EPERM`，需放宽文件/进程权限后重试。

> 开发服务器与后端端口被占用时须自动切换，并保持 [vite.config.ts](../../frontend/vite.config.ts) 代理目标与后端实际端口一致（见 [AGENTS.md](../../AGENTS.md) 规则 4）。
