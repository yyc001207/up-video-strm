# 版本记录（CHANGELOG）

本文件专门记录 **up-video-strm** 的版本演进：每个交付版本的级别、日期、变更要点与提交号，以及版本级别为何这样判定。开发规范与交付流程见 [AGENTS.md](AGENTS.md)。

## 版本规则

版本号遵循 [SemVer](https://semver.org/lang/zh-CN/) `MAJOR.MINOR.PATCH`。唯一版本源是 `backend/app/version.py` 的 `__version__`，由 `packaging/bump_version.py` 同步到 `frontend/package.json`、`frontend/package-lock.json`、`packaging/version_info.txt`（四处必须一致，打包脚本会校验）。

| 位 | 何时递增 | 本项目实例 |
|----|----------|------------|
| `MAJOR` | 不兼容变更：接口移除/改名、配置或数据库结构破坏性调整、部署方式变更 | 3.0.0 单服务器化；4.0.0 移除接口字段与配置项 |
| `MINOR` | 新增功能：新页面、新接口、新交互、新配置项 | 2.1.0 前端 UI 重构；3.1.0 连通性测试；4.1.0 测试版打包 |
| `PATCH` | 缺陷修复、样式/文案微调、性能优化、依赖安全更新 | 2.0.1 重命名与 Docker 清理 |

- 一次交付只递增一次；多个改动合并按最高级别递增。
- 每次递增必须在本文件「未发布」下方新增对应条目，记录版本号、日期、级别与 commit。
- 纯文档 / 规范整理不递增版本，也不单独发版。
- 仓库内可追溯的起点为 **2.0.0**（首个 Git 提交），更早的产品历史不在本仓库。

## 未发布（Unreleased）

### 上传管理（阶段一：凭据与 API 客户端）

- 新增 `upload_platform_config` 表与 `/api/upload/config` 接口：123 云盘 Client ID / Client Secret 配置，密钥使用 Windows DPAPI 加密存储、接口只回显脱敏值；Token 缓存到期前 5 分钟自动刷新。
- 新增 `pan123_client.py`：123 云盘开放平台客户端（申请 Token、分页列目录、按路径解析目录且不自动创建、创建/分片/完成上传与异步结果、删除文件）。
- 全局配置页新增「123 云盘」卡：凭据脱敏回显、Token 状态、测试连接与保存。
- 文档：`manual/用户手册.md` §3、`docs/rules/frontend.md` 同步。

### 上传管理（阶段二：任务与重命名规则）

- 数据表 `upload_rename_rule`（命名模板）、`upload_task`（本地目录 / 云端目录 / 输出季数 / 源起始集号 / 规则引用），首次启动自动 seed 默认规则 `S{season:02}E{episode:02}.{ext}`。
- 重命名与集数映射：从文件名解析绝对集号（`S01E13` / `第13集` / `EP13` / `[13]` 等），输出名 `S{季:02}E{季内集:02}.{ext}`，季内集号 = 绝对集号 − 源起始集号 + 1；规则预校验必须含 episode 与 ext 且渲染为 `SxxExx.ext`。
- `/api/upload/rules`（CRUD + 预览）、`/api/upload/tasks`（CRUD）、`/api/upload/remote/dirs`（列云端目录）接口。
- 前端新增「上传管理」平级模块：任务配置页（表格 + 抽屉编辑 + 云端目录浏览）与重命名规则页（规则 CRUD + 预览）。
- 文档：`manual/用户手册.md` 新增 §9 上传管理（后续章节顺延）、`docs/rules/frontend.md` 同步。

## [4.2.0] - 2026-11-05

**级别：MINOR（新增模块 + 交互调整）** · 代码 `1abe694`

### 调整

- 全局配置升级为与「任务调度」**平级的独立模块**（路由 `/config`，侧栏排在任务调度之上；旧 `/schedule/config` 保留重定向）：模块内只保留服务器配置与视频/字幕格式，格式编辑改为右侧抽屉。
- 原全局配置的其他运行参数（并发度、限流间隔/暂停时间、SSL 校验、输出目录前缀/根目录）迁至**任务配置**页顶部「默认运行参数」卡与编辑抽屉，语义仍为全局默认。
- 壳层导航支持「单页模块不显示分组标题」，模块顺序改为数据驱动（全局配置 → 任务调度）。

## [4.1.2] - 2026-11-05

**级别：PATCH（缺陷修复）** · 代码 `88d8ebc`

### 修复

- 中文 Windows 下执行 `pip install -r packaging/requirements-build.txt` 报 `UnicodeDecodeError: 'gbk' codec can't decode byte 0x96`：该文件含中文注释但未声明编码，pip 按系统默认 GBK 解码失败。按 PEP 263 在首行加入 `# -*- coding: utf-8 -*-`，pip 可正确解析并安装 PyInstaller 等打包依赖（已用 `pip install --dry-run` 验证解析通过）。

## [4.1.1] - 2026-11-05

**级别：PATCH（缺陷修复 + 布局调整）** · 代码 `2274002`、`8f218eb`

### 修复

- 升级后旧数据库点击「执行任务」返回 500：旧库遗留的 `open_list_execution.strip_series` 为 `NOT NULL` 且无默认值，新代码不再写该列，`INSERT` 触发 `IntegrityError`。启动时由 `obsolete_column_statements()` 生成 `ALTER TABLE ... DROP COLUMN`（SQLite ≥ 3.35），清理 `open_list_execution.strip_series`/`server_name`、`open_list_config.log_to_db`、`open_list_server.name`，升级用户无需重建数据库。

### 变更

- 执行管理改为「选择任务 / 执行参数 / 已选任务」三卡片一行展示；「已选任务」卡片承载逐条移除、清空选择、摘要与「执行任务」按钮，移除底部常驻操作条；窄屏（< 1100px）回退为纵向堆叠。「正在执行」表格与业务流程不变。

### 文档

- `manual/用户手册.md` §6 执行管理、`docs/rules/frontend.md`、`docs/design/ui-redesign-plan.md` §3.1 与验收清单、`docs/rules/backend.md` 数据层同步。

## [4.1.0] - 2026-11-05

**级别：MINOR（新增能力）** · 代码 `b22fbc2`

- 新增测试版打包：`packaging/build-test.ps1`（内部以 `-Profile test` 复用 `build.ps1`）产出 `up-video-strm-test.exe` 与 `dist/up-video-strm-test-<版本>-win-x64-setup.exe`；应用名、安装目录、数据目录（`%LOCALAPPDATA%\up-video-strm-test`）、快捷方式、自启动项、单实例互斥体均与正式版隔离，可同时安装运行。
- `build.ps1` 新增 `-Profile prod|test`（默认 `prod`，行为不变）；`installer.iss` 通过 `MyTestBuild` 切换 AppId/安装目录/产物名；`paths.py` 新增 `APP_DIR_NAME` 与 `build_profile()`，测试版应用携带 `build_profile.json` 构建标记，`run.py`/`desktop.py`/`desktop_prefs.py`/`main.py` 的应用名统一取自 `APP_DIR_NAME`。
- 测试：新增 `backend/tests/test_build_profile.py`（6 例：源码/冻结、prod/test 标记、数据目录隔离、应用名），`test_smoke.py` 同步打包命名断言。
- 文档：README「构建与打包」新增测试版说明与 `-Profile` 参数；`docs/rules/project.md` 同步打包发布与冻结运行差异。

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
