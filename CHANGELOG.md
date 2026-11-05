# 版本记录（CHANGELOG）

本文件专门记录 **up-video-strm** 的版本演进：每个交付版本的级别、日期、变更要点与提交号，以及版本级别为何这样判定。开发规范与交付流程见 [AGENTS.md](AGENTS.md)。

## 版本规则

版本号遵循 [SemVer](https://semver.org/lang/zh-CN/) `MAJOR.MINOR.PATCH`。唯一版本源是 `backend/app/version.py` 的 `__version__`，由 `packaging/bump_version.py` 同步到 `frontend/package.json`、`frontend/package-lock.json`、`packaging/version_info.txt`（四处必须一致，打包脚本会校验）。

| 位 | 何时递增 | 本项目实例 |
|----|----------|------------|
| `MAJOR` | 不兼容变更：接口移除/改名、配置或数据库结构破坏性调整、部署方式变更 | 3.0.0 单服务器化；4.0.0 移除接口字段与配置项 |
| `MINOR` | 新增功能：新页面、新接口、新交互、新配置项 | 2.1.0 前端 UI 重构；3.1.0 连通性测试 |
| `PATCH` | 缺陷修复、样式/文案微调、性能优化、依赖安全更新 | 2.0.1 重命名与 Docker 清理 |

- 一次交付只递增一次；多个改动合并按最高级别递增。
- 每次递增必须在本文件「未发布」下方新增对应条目，记录版本号、日期、级别与 commit。
- 纯文档 / 规范整理不递增版本，也不单独发版。
- 仓库内可追溯的起点为 **2.0.0**（首个 Git 提交），更早的产品历史不在本仓库。

## 未发布（Unreleased）

- 暂无。

## [4.0.0] - 2026-11-05

**级别：MAJOR（不兼容）** · 代码 `1d2fe82` · 文档 `5cc2e17`

**为什么是 MAJOR**：移除了对外接口字段（服务器 `name`、任务/执行响应中的 `server_name`、全局配置的 `log_to_db`），属于「接口移除 + 配置结构破坏性调整」，按规则必须递增 MAJOR。

### 不兼容变更

- 删除服务器「名称」字段：`OpenListServerCreate` / `OpenListServerUpdate` / `OpenListServerResponse`、`OpenListServer` 模型、前端类型与表单/卡片全部移除；删除确认改用服务器地址标识。
- 删除全局配置 `log_to_db`：`OpenListConfigUpdate` / `OpenListConfigResponse`、`get_config` / `get_config_for_run`、前端类型与摘要卡同步移除。
- 任务 / 执行响应不再返回 `server_name`。

### 新增

- 服务器配置卡片标题右侧显示连通状态：在线（绿）/ 离线（红）/ 未配置（灰）/ 检测中（黄）；进入页面探测一次，之后每 60s 轮询（后台失败静默）。
- 「编辑配置」由弹窗改为右侧抽屉（520px，底部固定「取消 / 保存」）。
- axios 请求新增 `silent` 选项：后台轮询等场景失败不弹全局错误提示。

### 变更

- 执行日志只写文件，移除 `LogPump` 的批量落库分支（WebSocket 推送 + 追加文件）。
- 数据库旧列 `config.log_to_db`、`server.name`、`execution.server_name` 物理保留但不再读写，升级不丢历史数据。

### 文档

- 用户手册：全局配置参数表移除日志入库项、编辑配置改为抽屉；服务器配置去掉「名称」字段与卡片名称展示，改为标题右侧状态标签说明。
- `docs/rules/frontend.md`：同步 `GlobalConfig.vue` 页面职责。

## [3.1.0] - 2026-11-05

**级别：MINOR（新增功能）** · 代码 `de27dff` · 文档 `f34bc75`

- 新增服务器连通性测试：后端 `POST /openlist/servers/test-connection`（可带 `server_id` 复用已保存 Token），前端服务器弹窗提供「测试连通性」按钮。
- 成功时返回「连接成功」及根目录条目数；失败时返回具体原因（超时、地址不可达、Token 无效等）。

## [3.0.0] - 2026-11-05

**级别：MAJOR（不兼容）** · 代码 `afb63b3` · 文档 `b48bff3`

**为什么是 MAJOR**：接口请求/响应字段变更，并删除配置项（系列层优化），属于破坏性调整。

### 不兼容变更

- 服务器配置单服务器化：创建第二个服务器会被拒绝；任务创建、执行/目录执行批量创建均可省略 `server_id`，自动绑定唯一启用服务器；相关 schema 的 `server_id` 改为可选。
- 移除「系列层优化」：前后端彻底删除 `strip_series` / `stripSeries`（schema、执行引擎、STRM 生成器、前端类型与请求体）；数据库旧列保留但不再读写。
- 执行接口响应不再返回 `strip_series`。

### 变更

- 前端移除所有服务器选择器、筛选条件与多服务器相关文案。

### 文档

- 用户手册与工程规范同步单服务器化与系列层移除说明。

## [2.1.0] - 2026-11-05

**级别：MINOR（新增功能）** · 代码 `9491fbe` · 文档 `3a5ea57`

- 前端按 [docs/design/ui-redesign-plan.md](docs/design/ui-redesign-plan.md) 重建：
  - 侧栏壳层（220/64 可折叠、模块 → 分组 → 页面数据驱动）+ 顶栏页面标题/描述/运行状态胶囊；
  - 路由拆分为 `/schedule/{config,tasks,execution,history,realtime}` 与 `/settings`；
  - 五个页面重写：执行管理（双栏）、全局配置（8/4 布局）、任务管理（工具栏分组）、任务历史（状态点 + 页面级详情）、实时日志（三段式）；
  - 新增设计令牌与 Element Plus 变量映射、`zh-cn` 语言包、焦点环与减动效支持，新增 `StatusDot.vue` / `LogViewer.vue`。

## [2.0.1] - 2026-11-04

**级别：PATCH（修正 / 清理）** · 代码 `34b5af7` · 文档 `6ad41a2`

- 项目整体重命名 `video-strm` → `up-video-strm`：进程名、窗口标题、数据目录（`%LOCALAPPDATA%\up-video-strm`）、数据库名 `up_video_strm.db`、打包产物与前端包名；旧数据目录 / 旧库原地沿用做兼容。
- 移除 Docker 与相关发布物：Dockerfile、docker-compose、镜像相关文档与 CI 引用；文档去掉部署 / 镜像章节。
- 版本号 2.0.0 → 2.0.1。

## [2.0.0] - 2026-11-04

**级别：基线（Git 首个提交 `3b09166`）**

- 仓库纳入 Git 时的既有状态：FastAPI + SQLite 后端、Vue 3 + Element Plus 前端、pywebview 桌面外壳、PyInstaller + Inno Setup 打包，已具备 STRM 生成与任务调度核心功能。更早的产品版本历史不在本仓库，故作为基线记录。
