# docs/rules/backend.md — 后端工程说明

> 核心规范见 [AGENTS.md](../../AGENTS.md)；项目总览与打包流程见 [project.md](project.md)；前端见 [frontend.md](frontend.md)；用户操作说明见 [manual/用户手册.md](../../manual/用户手册.md)。

## 技术栈

- FastAPI 0.110 + Uvicorn + SQLAlchemy 2.0（async）+ aiosqlite + Pydantic v2 / pydantic-settings + httpx + aiofiles
- 依赖：[backend/requirements.txt](../../backend/requirements.txt)、[backend/requirements-dev.txt](../../backend/requirements-dev.txt)

## 目录结构

```text
backend/
├── app/
│   ├── main.py / desktop.py / version.py   # 入口、原生窗口外壳、版本源
│   ├── api/                # openlist / uploader / automation / renamer 业务路由、desktop 桌面设置路由
│   ├── business/openlist/  # 任务调度业务层（见下）
│   ├── business/uploader/  # 上传管理业务层（见下）
│   ├── business/automation/# 自动化任务业务层（见下）
│   ├── business/renamer/   # 本地改名业务层（见下）
│   ├── business/execution_registry.py  # 执行启动闸门（同任务互斥）
│   ├── core/               # settings / paths / database / desktop_prefs / logger / exceptions / tray_win
│   │   └── models/         # ORM 模型（openlist / uploader / automation）
│   ├── utils/              # 响应封装、helpers
│   └── websocket/          # 实时日志连接管理（manager.py）
├── tests/                  # unittest 冒烟测试（本地，不纳入版本管理）
├── requirements.txt / requirements-dev.txt / pytest.ini / .env.example
├── run.py                  # 启动入口（源码/冻结通用：端口探测、单实例、原生窗口）
└── data/ openlist_logs/ upload_logs/ automation_logs/ rename_logs/ output/  # 源码运行时生成（数据库/日志/输出）
```

## 业务层模块职责（`app/business/openlist/`）

| 文件 | 职责 |
|------|------|
| [service.py](../../backend/app/business/openlist/service.py) | 业务核心：全局配置、服务器 CRUD、父级目录校验与缓存、任务、执行管理、任务历史、日志读取、配置 seed |
| [strm_generator.py](../../backend/app/business/openlist/strm_generator.py) | STRM 生成器：递归扫描目录、生成 `.strm`、下载字幕、失效清理、限流暂停 |
| [openlist_api.py](../../backend/app/business/openlist/openlist_api.py) | OpenList/AList API 客户端（list_files / get / mkdir / remove / 流式下载，含重试） |
| [execution_engine.py](../../backend/app/business/openlist/execution_engine.py) | 执行引擎：后台运行任务、并发信号量、结果回写 |
| [execution_logger.py](../../backend/app/business/openlist/execution_logger.py) | 日志通道：日志 → WebSocket 广播 + 落库 + 日志文件 |
| [dir_cache.py](../../backend/app/business/openlist/dir_cache.py) | 目录缓存（内存，TTL 300s，超量清理） |
| [task_status_manager.py](../../backend/app/business/openlist/task_status_manager.py) | 任务取消标记（进程内） |
| [schema.py](../../backend/app/business/openlist/schema.py) | Pydantic 请求/响应模型 |

## 上传管理业务层（`app/business/uploader/`）

| 文件 | 职责 |
|------|------|
| [service.py](../../backend/app/business/uploader/service.py) | 123 云盘凭据（DPAPI 加密存储、Token 缓存与续期；凭据真正变化才清空缓存、并发刷新加锁、测试连接复用缓存令牌）、重命名规则、上传任务、执行记录/历史/日志读取、配置 seed |
| [pan123_client.py](../../backend/app/business/uploader/pan123_client.py) | 123 云盘开放平台客户端（token、文件列表/查重、目录解析、秒传/分片上传、异步结果、删除；`get_file_id` 兼容 `fileID`/`fileId`） |
| [scanner.py](../../backend/app/business/uploader/scanner.py) | 本地目录扫描与视频过滤（扩展名来自全局「视频格式」）、MD5 计算；跳过下载中/临时文件（`is_partial_file`：`.!qB`、`.part`、`.crdownload`、`.aria2` 等）并返回忽略数量供日志提示 |
| [subtitles.py](../../backend/app/business/uploader/subtitles.py) | 字幕配对与目标命名：固定字幕扩展名（`srt`/`ass`/`ssa`/`vtt`/`sub`/`idx`/`sup`），仅配对与视频同目录的字幕；优先按「视频主干前缀 + 语言标记」，否则按同集数（含任务自定义 `episode_pattern`）取公共前缀最长的视频兜底；目标名保留语言标记（`S01E03.chs.ass`），相同目标名去重；未匹配字幕不上传 |
| [rename_engine.py](../../backend/app/business/uploader/rename_engine.py) | 集数解析（`第03集`/`S01E03`/`EP03`/`[03]`/`03 - 标题`，排除分辨率与哈希数字）+ 可选自定义集数正则（`episode_pattern`，第 1 个分组为集号）+ 模板渲染（`{season}`/`{episode}`/`{ext}`） |
| [execution_engine.py](../../backend/app/business/uploader/execution_engine.py) | 六阶段执行流水线（扫描 → 过滤 → 重命名 → 清单 → 查重 → 上传）、并发上传与重试、取消、结果回写；字幕与视频进同一份清单、各自独立记录（字幕失败不影响视频） |
| [execution_logger.py](../../backend/app/business/uploader/execution_logger.py) | 日志通道：按执行写 `upload_logs/execution_{id}.log` + WebSocket 广播 log/progress/status 帧（不落库） |
| [schema.py](../../backend/app/business/uploader/schema.py) | Pydantic 请求/响应模型 |

## 自动化任务业务层（`app/business/automation/`）

| 文件 | 职责 |
|------|------|
| [service.py](../../backend/app/business/automation/service.py) | 任务 CRUD、绑定唯一性校验（同一上传/STRM 任务只能绑定一个自动化任务）、绑定选项、校验目录探测、运行历史查询、失败文件写回待校验 |
| [schema.py](../../backend/app/business/automation/schema.py) | Pydantic 请求模型（创建/更新/批量删除/校验目录/启动参数/清空待校验） |
| [registry.py](../../backend/app/business/automation/registry.py) | 进程内运行登记：运行任务、停止事件、每任务锁、运行态快照（阶段 / 下一轮时间 / 当前运行 id） |
| [execution_engine.py](../../backend/app/business/automation/execution_engine.py) | 每任务后台循环：指纹判断 → 等待 A/B 空闲 → 触发上传 → 可见性校验 → 触发 STRM → 收尾（待校验 / 指纹 / 连续失败计数）；超时、退避与停止 |
| [change_detector.py](../../backend/app/business/automation/change_detector.py) | 本地目录 stat 指纹（路径 + 大小 + mtime_ns，按视频格式过滤）；跳过下载中/临时文件并返回忽略数量 |
| [adapters.py](../../backend/app/business/automation/adapters.py) | A/B 调用适配层：按模式创建并启动执行、查询终态、读取上传成功的远端文件名、取消 |
| [execution_logger.py](../../backend/app/business/automation/execution_logger.py) | 每轮日志文件 `automation_logs/automation_run_{run_id}.log` + WebSocket 广播（log / progress / status） |
| [notifier.py](../../backend/app/business/automation/notifier.py) | 异常终止托盘通知 + 网页 `alert` 帧；主动停止不通知 |
| [relay.py](../../backend/app/business/automation/relay.py) | A/B 执行日志镜像：尾随 A/B 执行日志文件，按行还原级别后转写进当前轮次自动化日志（前缀 `[A#id]` / `[B#id]`），使自动化实时日志与历史日志可看到完整链路 |
| [refs.py](../../backend/app/business/automation/refs.py) | A/B 任务、服务器删除前的自动化绑定引用检查 |
| [retention.py](../../backend/app/business/automation/retention.py) | 历史与日志清理：运行记录保留 90 天且每任务最多 1000 条、日志保留 90 天且每任务最多 200 个 |

## 本地改名业务层（`app/business/renamer/`）

| 文件 | 职责 |
|------|------|
| [planner.py](../../backend/app/business/renamer/planner.py) | 纯逻辑：视频/字幕扩展名、集数解析（`S01E03` / `EP03` / `E03` / `第03集` / `[03]` / `(03)`，排除年份与分辨率）、季数解析（`S00` / `Special` / `特别篇` / `OVA` / `OAD` 等特别篇目录输出 `S00Exx`，避免被误判为第 1 季）、语言标记、`.5` 特殊集、目标名 `SxxExx.lang.ext`、目录结构识别（一级 / 二级）、目标冲突标记（`exists` / `duplicate` / `chain` / `noop` / `caseonly`）与自动编号 |
| [service.py](../../backend/app/business/renamer/service.py) | 扫描（校验目录、拒绝磁盘根、限制 500 文件、计划缓存供改名校验）、批量重命名（冲突策略 `skip` / `overwrite` / `autonum`、仅允许重命名上次扫描到的文件、目标必须在根目录内、仅大小写调整走两步改名）、操作日志 `rename_logs/rename.log` 与最近日志读取 |
| [schema.py](../../backend/app/business/renamer/schema.py) | Pydantic 请求模型（扫描 / 重命名 / 文件条目） |

- 路由：`POST /api/renamer/scan`、`POST /api/renamer/rename`、`GET /api/renamer/logs`（前缀 `/api/renamer`，见 [api/renamer.py](../../backend/app/api/renamer.py)）。
- 无数据库表：改名计划保存在进程内（最近 20 次扫描），执行前必须先用同一根目录扫描一次；进程重启后需重新扫描。

## 数据层

- 无 Alembic；启动时 [database.py](../../backend/app/core/database.py) 用 `create_all` 建表 + `PRAGMA`/`ALTER TABLE` 轻量列级迁移，并写入默认全局配置。上传模块的 `episode_pattern` 列由 `_ensure_upload_columns()` 为旧库自动 `ADD COLUMN`（`upload_rename_rule`、`upload_execution`）。
- 废弃列清理：`obsolete_column_statements()` 会针对旧库中已不再映射的物理列（`open_list_execution.strip_series`/`server_name`、`open_list_config.log_to_db`、`open_list_server.name`）生成 `ALTER TABLE ... DROP COLUMN`，`init_db()` 在 SQLite ≥ 3.35 时执行，避免旧库 `NOT NULL` 列导致新代码 INSERT 失败（4.1.1 修复）。
- 数据表：`open_list_config`、`open_list_server`、`open_list_server_dir`、`open_list_task`、`open_list_execution`、`open_list_log`；上传管理另有 `upload_platform_config`、`upload_rename_rule`、`upload_task`、`upload_execution`、`upload_file_record`；自动化任务另有 `automation_task`、`automation_run`。
- 输出根目录：`open_list_config.output_root`（可空）。任务输出目录以 `/` 开头时由 [strm_generator.resolve_output_base()](../../backend/app/business/openlist/strm_generator.py) 相对其解析；为空回退 `CWD/output`（源码运行即 `backend/output`；冻结运行已 `chdir` 到数据目录，落在 `%LOCALAPPDATA%\up-video-strm\output`）。
- 默认 SQLite 路径：`./data/up_video_strm.db`（见 [settings.py](../../backend/app/core/settings.py)）；冻结运行指向数据目录下 `data/up_video_strm.db`。
- 旧库兼容：同目录下新库 `up_video_strm.db` 不存在、而旧库 `video_strm.db` 存在时，[settings.py](../../backend/app/core/settings.py) 自动沿用旧库文件（源码 `./data` 与冻结数据目录规则一致），避免升级后数据「消失」。

## 关键流程

1. 前端先 `POST /api/openlist/executions`（或 `/batch`、`/dirs`）落库拿 `execution_id` → 连 WebSocket 日志 → 再 `POST /executions/start` 启动，保证日志不丢帧。
2. `start_execution` 校验后 `asyncio.create_task(run_generation)`，受全局 `max_concurrent` 信号量限流。
3. 生成器产出 `.strm`（内容 `{base}/d/{path}`）与字幕，结束后回写执行记录并推送状态帧。
4. 日志以文件为权威源：任务调度 `openlist_logs/execution_{id}.log`、上传管理 `upload_logs/execution_{id}.log`、自动化任务 `automation_logs/`（模块 C），均经 WebSocket 实时推送；执行结束会输出汇总行（`上传完成：成功/跳过/失败/剩余待处理`、`任务结束：状态/处理数量/用时`）。
5. 执行记录扩展字段（阶段⓿）：`open_list_execution` 与 `upload_execution` 均有 `error_code` / `error_message`（失败原因分级）与 `trigger_source`（`manual` / `automation`）/ `trigger_ref` / `trigger_name`（触发来源）；列表查询支持按 `execution_id` / 时间过滤。
6. 启动闸门（阶段⓿）：[execution_registry.py](../../backend/app/business/execution_registry.py) 在 `start_execution` 入队前按 `(模块, execution_id) -> task_id` 登记，引擎 `finally` 注销；同模块同 `task_id` 已有活跃执行时返回 400「任务正在执行，请等待当前执行结束」，`task_id=0`（目录执行）不互斥。
7. 进程重启清理（阶段⓿）：[database.py](../../backend/app/core/database.py) 的 `init_db` 在建表/列迁移后把遗留 `running` 执行置为 `fail` 并写 `error_code='PROCESS_RESTART'`、`error_message='进程重启中断'`；不自动恢复执行。
8. 引用保护（阶段⓿）：[automation/refs.py](../../backend/app/business/automation/refs.py) 在 A/B 任务或服务器删除前检查是否被自动化任务绑定，命中返回 400「任务正被自动化任务「X」绑定，请先解除绑定后再删除」。
9. 自动化任务链路：由 `POST /api/automation/tasks/{id}/start` 启动后台循环，每轮先按本地目录指纹判断是否有新增/变化（无变化不建运行记录）；有待校验文件时跳过上传直接校验，否则等待 A/B 空闲后创建并启动上传（冲突策略固定跳过）。上传成功后按 `remote_name` 轮询 `check_dir` 可见性，全部可见后触发 STRM 任务；成功后清空待校验并提交指纹，失败保留待校验供下一轮补偿。轮次间隔取任务配置 `interval_seconds`（默认 60s，可在执行管理启动时填写并写回任务），连续 3 次轮次失败终止，进程重启不自动恢复（残留 `running` 置 `fail` + `PROCESS_RESTART`）。启动参数 `AutomationStartRequest` 只包含 5 项时间参数（可见性轮询间隔 / 可见性等待上限 / 空闲等待上限 / 阶段超时 / 轮次间隔），由 `service.apply_run_params` 写入任务配置后启动；上传/STRM 参数不再作为执行参数。等待 A/B 执行期间由 [relay.py](../../backend/app/business/automation/relay.py) 尾随 A/B 日志文件并逐行转写进本轮自动化日志，因此自动化实时日志与历史日志都能看到 A/B 的详细执行行（`[A#id]` / `[B#id]` 前缀）。扫描会跳过下载中/临时文件（`.!qB` / `.part` / `.crdownload` 等）；若本轮只有这类文件，则不建运行记录，仅通过 `execution_logger.broadcast_notice` 广播一行「忽略下载中文件 N 个」。
10. 自动化任务接口：任务 CRUD / 批量删除 / 绑定选项 / 校验目录、启动 / 批量启动 / 停止 / 重置指纹 / 清空待校验、`GET /api/automation/active`、运行历史 `/api/automation/runs`（`task_id` / `status` / `start_time` / `end_time` 筛选，日期按北京时间含首尾两天，按 `coalesce(started_time, created_time)` 过滤）、运行日志 `/runs/{id}/logs`、失败重试 `/runs/{id}/retry-failed`，以及 WebSocket `/api/automation/ws/{task_id}`（log / progress / status / alert 帧）。历史与日志清理由 [retention.py](../../backend/app/business/automation/retention.py) 在启动时执行一次并每日定时执行。
11. 本地改名链路：`POST /api/renamer/scan` 扫描并缓存文件计划（返回剧集 / 季 / 文件与冲突标记）→ 前端按需修改目标名后分批（每批 20 条）`POST /api/renamer/rename`；后端只允许重命名缓存计划中的文件，目标必须在扫描根目录内，冲突策略为跳过 / 覆盖 / 自动编号；每批结果即时返回，前端全部批次完成后重新扫描刷新。操作日志写入 `rename_logs/rename.log`，可通过桌面接口 `kind=rename` 打开日志目录。
12. 字幕随视频上传（上传执行）：扫描阶段同时扫固定字幕扩展名（不随全局「视频格式」变化）→ 为每个视频生成计划后，[subtitles.py](../../backend/app/business/uploader/subtitles.py) 把同目录字幕配对到视频（主干前缀优先、同集数兜底）→ 字幕作为独立 `upload_file_record`（`remote_name = SxxExx.lang.ext`）与视频加入同一份清单，查重 / 冲突策略 / 并发 / 重试与视频一致；未匹配字幕只写日志、不上传；单条字幕失败只记该条为 failed，不影响视频。

## 环境变量（backend/.env，应用配置）

| 变量 | 默认 | 说明 |
|------|------|------|
| `SQLITE_PATH` | `./data/up_video_strm.db` | SQLite 数据库路径（冻结运行相对数据目录） |
| `OPENLIST_LOG_DIR` | `./openlist_logs` | 任务调度执行日志目录 |
| `UPLOAD_LOG_DIR` | `./upload_logs` | 上传管理执行日志目录 |
| `AUTOMATION_LOG_DIR` | `./automation_logs` | 自动化任务执行日志目录（模块 C 使用） |
| `RENAME_LOG_DIR` | `./rename_logs` | 本地改名操作日志目录 |
| `ALLOWED_ORIGINS` | `["http://localhost:5173","http://127.0.0.1:5173"]` | CORS 允许来源 |

> 读取顺序：源码运行读 `backend/.env`；冻结运行先读数据目录 `.env`，再读 exe 同级 `.env`（后者优先）。

## 桌面外壳与冻结运行（后端专属补充）

冻结态路径解析（`data_root()` / `resource_dir()`）、端口回退、单实例互斥、stdio 重定向等通用行为见 [project.md](project.md)；`run.py` 实现要点：冻结态 `os.chdir(data_root)` → stdio 重定向到 `logs/app.log`（超 5 MB 转 `app.log.1`）→ 后台线程 `uvicorn.Server`（`timeout_graceful_shutdown=2`）+ 主线程 [app/desktop.py](../../backend/app/desktop.py) 原生窗口；exe 为 GUI 进程（`console=False`），不派生子进程。

- 桌面偏好与自启：[app/core/desktop_prefs.py](../../backend/app/core/desktop_prefs.py) 把 `start_minimized` / `close_to_tray` 存数据目录 `desktop.json`（不落库，避免桌面偏好影响其他运行方式）；开机自启读写 `HKCU\...\CurrentVersion\Run` 的 `up-video-strm` 值（仅冻结态；启动时若检测到旧版值 `video-strm` 已启用，自动改写成新值并删除旧值）。[api/desktop.py](../../backend/app/api/desktop.py) 暴露 `/api/desktop/info|autostart|preferences|fix-tray|open-taskbar-settings|open-data-dir|open-log-dir` 等接口（`open-log-dir` 按 `kind=openlist|upload|automation|rename` 用资源管理器打开对应日志目录），非桌面态只读、写操作返回 400。
- 入口页缓存：[app/main.py](../../backend/app/main.py) 的 SPA 回退对 `index.html` 返回 `Cache-Control: no-cache, no-store, must-revalidate`（带哈希的 `/assets/*` 仍按文件缓存）；[desktop.py](../../backend/app/desktop.py) 原生窗口首屏地址带 `?v=<版本号>`，升级安装后换用新 URL，避免 WebView2 直接复用旧版本入口 HTML 加载旧 bundle，导致新页面不可见（4.20.1）。
- 窗口关闭默认走托盘：[desktop.py](../../backend/app/desktop.py) 监听 `closing` 事件返回 False 取消关闭，并延迟隐藏窗口（事件内直接 hide 会被 WinForms 取消关闭流程重新显示）；关窗时现读 `desktop.json` 的 `close_to_tray`，设置页/托盘改完立即生效。pystray 菜单「打开主界面 / 设置… / 快捷设置（开机自启、启动最小化、关窗收进托盘）/ 打开数据目录 / 退出」，「设置…」通过 `window.__upVideoStrmNavigate('/settings')`（前端 [main.ts](../../frontend/src/main.ts) 注册）切页而非整页重载；退出时 `icon.stop()` → `window.destroy()` → 服务关停。
- 窗口相关辅助：[app/core/tray_win.py](../../backend/app/core/tray_win.py) 负责 Windows 托盘图标探测与可见性（Win11 的 `HKCU\Control Panel\NotifyIconSettings\<hash>` 的 `IsPromoted`）：启动时 `check_tray` 调 `hide_tray_icon()` 写 `0`，让图标**默认收进「^」**；设置页「修复托盘图标」接口（`POST /api/desktop/fix-tray`）仍调 `promote_tray_icon()` 写 `1` 供用户临时固定到常驻区。

启动器环境变量（进程环境，**不读取 .env**）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `UP_VIDEO_STRM_HOME` | `%LOCALAPPDATA%\up-video-strm` | 冻结态数据根目录（数据库/日志/输出） |
| `UP_VIDEO_STRM_HOST` | `127.0.0.1` | 监听地址 |
| `UP_VIDEO_STRM_PORT` | 源码 `8000`、安装包 `18765` | 首选端口，占用时自动顺延（最多 20 个）；安装包默认避开 8000/8080 等常用端口 |
| `UP_VIDEO_STRM_UI` | 冻结态 `window`、源码 `server` | `window` 开原生窗口；`server` 只跑控制台服务（配合浏览器排查） |
| `UP_VIDEO_STRM_TRAY` | `1` | 关闭窗口是否收进托盘；`0` 表示关窗即退出 |

> 旧名兼容：仅当 `UP_VIDEO_STRM_HOME` 未设置时回退读取旧变量 `VIDEO_STRM_HOME`；旧版 `VIDEO_STRM_HOST` / `VIDEO_STRM_PORT` / `VIDEO_STRM_UI` / `VIDEO_STRM_TRAY` 不再读取。

## 常用命令

安装、启动与测试命令见 [README.md 快速开始](../../README.md#方式二源码运行)；接口文档 `http://127.0.0.1:8000/docs`，健康检查 `GET /api/health`。
