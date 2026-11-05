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
│   ├── api/                # axios 实例 + openlist / desktop 接口封装
│   ├── stores/             # Pinia（openlist 业务 / theme 主题）
│   ├── views/
│   │   ├── schedule/       # 任务调度模块：四个路由页面 + components/DirTreePanel.vue
│   │   ├── config/         # 全局配置模块：服务器配置 + 视频/字幕格式
│   │   └── Settings/       # 桌面设置页
│   ├── components/         # 通用组件（StatusDot 状态点 / LogViewer 日志终端 / ThemeToggle 主题切换）
│   ├── types/ / utils/     # 类型（openlist / desktop）、工具（date / ws）
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
| `/settings` | `views/Settings/index.vue` | 桌面设置（desktop 外壳导航仍按此路径跳转） |
| 其它 | — | 重定向到 `/` |

- 侧栏由 [App.vue](../../frontend/src/App.vue) 的 `modules` 数据驱动（模块 → 分组 → 页面），当前两个平级模块：「任务调度」（`/schedule/*`）与「全局配置」（`/config`）；单页模块不显示分组标题，新增模块只需追加一项数据。折叠状态存 `localStorage` 的 `up-video-strm-sidebar-collapsed`。
- 顶栏标题/描述取路由 `meta.title` / `meta.description`；右侧运行状态胶囊轮询 `fetchRunning`（10s 间隔）。
- 原「五页签」语义改为独立路由页面：进入页面即按需加载，切换路由即刷新，不再依赖 tab 的 `reload`。
- 执行管理 → 实时日志通过路由 query 传参：`execs`（JSON 数组，元素 `{executionId, taskId, taskName, launch}`）。实时日志页先建立 WebSocket，`onOpen` 后才对 `launch=true` 的执行调用 `startExecution`（保证先连日志再启动）。

## 页面与组件

- `Execution.vue`：一行三卡片（选择任务 / 执行参数 / 已选任务），执行模式用 `el-segmented`（增量 / 全量 / 仅 strm）；「已选任务」卡片承载摘要与「清空选择 / 执行任务」操作；「正在执行」表支持查看日志与取消，5s 轮询刷新。
- `GlobalConfig.vue`：全局配置模块单页——左侧单服务器卡片（无服务器时为空态 + 新增；标题右侧显示连通状态标签：在线 / 离线 / 未配置 / 检测中，进入页面及每 60s 轮询探测；卡片展示服务器地址 / Token 是否配置 / 父级目录标签，可编辑、刷新缓存、删除），右侧视频与字幕格式摘要卡 + 编辑抽屉；底部 123 云盘卡（Client ID / Client Secret 脱敏回显、Token 状态标签、测试连接与保存，凭据加密存储、Token 自动续期）。
- `TaskManage.vue`：页顶部「默认运行参数」卡（最大并发、限流、SSL 校验、输出目录前缀与根目录）+ 编辑抽屉（配置全局生效，任务未单独设置时使用）；工具栏分组（搜索 / 新建、快速添加、批量删除）；表格任务名与路径双行；快速添加使用 `DirTreePanel.vue`（目录树勾选 + 搜索下钻 + 缓存刷新）。
- `TaskHistory.vue`：列表（每任务最近执行 + 状态点）与页面级详情（分页 20、日志抽屉、下载日志）。
- `RealtimeLog.vue`：三段式（进度摘要 / `LogViewer` 终端 / 级别与关键字过滤、清屏、下载日志）；状态帧结束即断开并提示前往任务历史。
- 通用组件：`StatusDot.vue`（执行状态点 + 文案）、`LogViewer.vue`（可复用日志终端）、`ThemeToggle.vue`（浅色 / 深色 / 跟随系统）。

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
