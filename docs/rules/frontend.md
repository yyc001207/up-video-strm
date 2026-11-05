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
│   ├── api/                # axios 实例 + openlist / uploader / desktop 接口封装
│   ├── stores/             # Pinia（openlist 业务 / theme 主题）
│   ├── views/
│   │   ├── schedule/       # 任务调度模块：四个路由页面 + components/DirTreePanel.vue
│   │   ├── upload/         # 上传管理模块：任务配置 / 重命名规则 / 执行管理 / 实时日志 + components/RemoteDirPanel.vue
│   │   ├── config/         # 全局配置模块：服务器配置 + 视频/字幕格式 + 123 云盘凭据
│   │   └── Settings/       # 桌面设置页
│   ├── components/         # 通用组件（StatusDot 状态点 / LogViewer 日志终端 / ThemeToggle 主题切换）
│   ├── types/ / utils/     # 类型（openlist / uploader / desktop）、工具（date / ws）
│   └── styles/             # variables（--up-strm-* 令牌）/ element-reset（EP 变量映射与表格统一）/ dark / global
├── index.html              # 标题「up-video-strm 任务调度」+ 首屏主题预加载
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
| `/schedule/history` | `views/schedule/TaskHistory.vue` | 任务历史列表与详情、日志回放/下载 |
| `/schedule/realtime` | `views/schedule/RealtimeLog.vue` | WebSocket 实时日志 |
| `/upload` | — | 重定向到 `/upload/tasks` |
| `/upload/tasks` | `views/upload/TaskConfig.vue` | 上传任务 CRUD：本地目录、云端目录、集数映射、命名规则 |
| `/upload/rename` | `views/upload/RenameRules.vue` | 重命名规则 CRUD 与模板预览 |
| `/upload/execution` | `views/upload/Execution.vue` | 执行管理：三卡片（选任务 / 执行参数 / 已选任务）+ 正在执行列表 |
| `/upload/realtime` | `views/upload/RealtimeLog.vue` | WebSocket 实时日志：6 阶段进度与逐文件输出，支持批量排队 |
| `/upload/history` | `views/upload/TaskHistory.vue` | 上传历史：按任务汇总 → 执行记录 → 文件明细、日志回放/下载、重跑 |
| `/settings` | `views/Settings/index.vue` | 桌面设置（desktop 外壳导航仍按此路径跳转） |
| 其它 | — | 重定向到 `/` |

- 侧栏由 [App.vue](../../frontend/src/App.vue) 的 `modules` 数据驱动（模块 → 分组 → 页面），当前三个平级模块：「全局配置」（`/config`）、「任务调度」（`/schedule/*`）与「上传管理」（`/upload/*`）；单页模块不显示分组标题，新增模块只需追加一项数据。折叠状态存 `localStorage` 的 `up-video-strm-sidebar-collapsed`。
- 顶栏标题/描述取路由 `meta.title` / `meta.description`；右侧运行状态胶囊轮询 `fetchRunning`（10s 间隔）。
- 原「五页签」语义改为独立路由页面：进入页面即按需加载，切换路由即刷新，不再依赖 tab 的 `reload`。
- 执行管理 → 实时日志通过路由 query 传参：任务调度为 `execs`（JSON 数组，元素 `{executionId, taskId, taskName, launch}`），上传管理为 `execs`（JSON 数组，元素 `{executionId, taskId, taskName}`）。实时日志页先建立 WebSocket，`onOpen` 后再调用 `startExecution`（保证先连日志再启动）；上传管理多个执行按队列串行启动与切换。
- 时间统一按**北京时间**解释与展示：一律使用 `utils/date.ts` 的 `formatDateTime`（`YYYY-MM-DD HH:mm:ss`）、`formatDate`（`YYYY-MM-DD`）或 `beijingMillis`（耗时计算），不要直接调用 dayjs 格式化；后端返回无时区墙钟字符串时按 `Asia/Shanghai` 解析，自带 Z / 偏移则先换算到北京时间。

## 页面与组件

- `Execution.vue`：一行三卡片（选择任务 / 执行参数 / 已选任务），执行模式用 `el-segmented`（增量 / 全量 / 仅 strm）；「已选任务」卡片承载摘要与「清空选择 / 执行任务」操作；「正在执行」表支持查看日志与取消，5s 轮询刷新。
- `GlobalConfig.vue`：全局配置模块单页——左侧单服务器卡片（无服务器时为空态 + 新增；标题右侧显示连通状态标签：在线 / 离线 / 未配置 / 检测中，进入页面及每 60s 轮询探测；卡片展示服务器地址 / Token 是否配置 / 父级目录标签，可编辑、刷新缓存、删除），右侧视频与字幕格式摘要卡 + 编辑抽屉；底部 123 云盘「摘要卡 + 编辑弹框」：卡头为状态标签与测试连接 / 编辑按钮，卡体展示 Client ID、脱敏后的 Client Secret、Token 状态与过期时间（`formatDateTime`），未配置时为空态「立即配置」，编辑入口打开 `el-dialog` 修改 Client ID / Secret。
- `TaskManage.vue`：页顶部「默认运行参数」卡（最大并发、限流、SSL 校验、输出目录前缀与根目录）+ 编辑抽屉（配置全局生效，任务未单独设置时使用）；工具栏分组（搜索 / 新建、快速添加、批量删除）；表格任务名与路径双行；快速添加使用 `DirTreePanel.vue`（目录树勾选 + 搜索下钻 + 缓存刷新）。
- `TaskHistory.vue`：列表（每任务最近执行 + 状态点）与页面级详情（分页 20、日志抽屉、下载日志）。
- `RealtimeLog.vue`：三段式（进度摘要 / `LogViewer` 终端 / 级别与关键字过滤、清屏、下载日志）；日志工具条位于**页面顶部**（终端之上），状态帧结束即断开并提示前往任务历史。
- 通用组件：`StatusDot.vue`（执行状态点 + 文案）、`LogViewer.vue`（可复用日志终端）、`ThemeToggle.vue`（浅色 / 深色 / 跟随系统）。
- `TaskConfig.vue`（上传管理）：上传任务列表与抽屉编辑（任务名 / 本地目录 / 云端目录 / 输出季数 / 源起始集号 / 命名规则）；本地目录可点「浏览」调用桌面端 `window.pywebview.api.pick_directory()` 快速选择（网页版提示手动输入）；云端目录不预填 `/test`，用 `RemoteDirPanel.vue` 懒加载目录树（可逐级下钻、单击选中、底部醒目展示已选路径，只读浏览、不自动建目录，提示仅使用 `/test`）；集号换算提示为「季内集号 = 绝对集号 − 起始集号 + 1」。
- `RenameRules.vue`（上传管理）：规则列表 + 模板编辑对话框（变量 `{season}` / `{episode}` / `{ext}`，`:02` 补零）+ 文件名预览（显示解析出的绝对集号或原因）；被任务引用的规则不可删除。
- `Execution.vue`（上传管理）：一行三卡片（选择任务 / 执行参数 / 已选任务），卡片高度随各自内容自适应（列表超高时内部滚动）；执行参数为冲突策略（跳过 / 覆盖 / 追加后缀）、并发上传、失败重试、试运行；批量创建执行记录后跳转实时日志页，由 WS 连接成功后逐个启动；「正在执行」表 5s 轮询，可查看日志或取消。
- `RealtimeLog.vue`（上传管理）：顶部连接状态与执行选择、6 阶段进度摘要（总数 / 成功 / 跳过 / 失败 / 已上传字节 / 用时 / 当前文件）、日志终端与级别 / 关键字过滤；状态帧结束后自动切到下一个排队执行，全部结束停留回放最近日志。
- `TaskHistory.vue`（上传管理）：列表按任务汇总（最近执行 + 累计次数），进入详情后展示该任务全部执行记录（状态 / 冲突策略 / 文件统计），可查看文件粒度明细抽屉、日志回放 / 下载，并按原执行固化参数重跑（跳转实时日志自动启动）。

## 设计与令牌

- 颜色一律使用 `var(--el-*)`（Element Plus 变量在 `styles/element-reset.scss` 中映射为设计色板）；壳层尺寸、间距、圆角、字号、阴影使用 `var(--up-strm-*)`（定义于 `styles/variables.scss`，暗色阴影在 `styles/dark.scss` 覆盖）。
- 表格统一：行高 40px、表头 12px、计数列右对齐 `font-variant-numeric: tabular-nums`、`0/0` 显示为 `—`。
- 交互细节：`:focus-visible` 焦点环；尊重 `prefers-reduced-motion`；删除类确认弹窗写明对象、数量与不可恢复。
- 设计依据：[docs/design/ui-redesign-plan.md](../design/ui-redesign-plan.md)。

## 接口与状态

- axios 实例：[api/index.ts](../../frontend/src/api/index.ts)（响应拦截统一拆包 `code === 200`）；业务接口：[api/openlist.ts](../../frontend/src/api/openlist.ts)；桌面接口：[api/desktop.ts](../../frontend/src/api/desktop.ts)。
- 后端 API 基址由 `VITE_API_BASE_URL` 控制（默认 `/api`）。
- Pinia store：[stores/openlist.ts](../../frontend/src/stores/openlist.ts)（业务，含 `runningCount`）、[stores/theme.ts](../../frontend/src/stores/theme.ts)（浅色/深色/跟随系统，localStorage 记忆，键名 `up-video-strm-theme`，首屏无闪烁）。
- WebSocket 工具：[utils/ws.ts](../../frontend/src/utils/ws.ts)，连接 `ws://.../api/openlist/ws/{execution_id}`。
- 桌面外壳导航桥：[main.ts](../../frontend/src/main.ts) 把路由挂到 `window.__upVideoStrmNavigate(path)`，托盘菜单「设置…」通过它直接切页而不整页重载（后端 [desktop.py](../../backend/app/desktop.py) 调用）。

## 常用命令

安装、启动与构建命令见 [README.md 快速开始](../../README.md#方式二源码运行)（`npm run build` = `vue-tsc` + `vite build`）。

- 本地完整类型检查：`npx vue-tsc -b --force`（`tsconfig.json` 为 solution 风格，裸 `vue-tsc` 不会真正检查 `src`）。
- TypeScript 6 起 `baseUrl` 弃用，`tsconfig.app.json` 已显式设置 `ignoreDeprecations: "6.0"`。
- 受限环境（如沙箱）中 Vite 构建可能因 `exec("net use")` 报 `spawn EPERM`，需放宽文件/进程权限后重试。

> 开发服务器与后端端口被占用时须自动切换，并保持 [vite.config.ts](../../frontend/vite.config.ts) 代理目标与后端实际端口一致（见 [AGENTS.md](../../AGENTS.md) 规则 4）。
