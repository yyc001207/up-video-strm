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
│   ├── api/                # openlist 业务路由 / desktop 桌面设置路由
│   ├── business/openlist/  # 业务层（见下）
│   ├── core/               # settings / paths / database / desktop_prefs / logger / exceptions / tray_win
│   │   └── models/openlist/# ORM 模型
│   ├── utils/              # 响应封装、helpers
│   └── websocket/          # 实时日志连接管理（manager.py）
├── tests/                  # unittest 冒烟测试（本地，不纳入版本管理）
├── requirements.txt / requirements-dev.txt / pytest.ini / .env.example
├── run.py                  # 启动入口（源码/冻结通用：端口探测、单实例、原生窗口）
└── data/ openlist_logs/ upload_logs/ output/  # 源码运行时生成（数据库/日志/输出）
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
| [service.py](../../backend/app/business/uploader/service.py) | 123 云盘凭据（DPAPI 加密存储、Token 缓存与续期）、重命名规则、上传任务、执行记录/历史/日志读取、配置 seed |
| [pan123_client.py](../../backend/app/business/uploader/pan123_client.py) | 123 云盘开放平台客户端（token、文件列表/查重、目录解析、秒传/分片上传、异步结果、删除；`get_file_id` 兼容 `fileID`/`fileId`） |
| [scanner.py](../../backend/app/business/uploader/scanner.py) | 本地目录扫描与视频过滤（扩展名来自全局「视频格式」）、MD5 计算 |
| [rename_engine.py](../../backend/app/business/uploader/rename_engine.py) | 集数解析（`第03集`/`S01E03`/`EP03`/`[03]`/`03 - 标题`）+ 模板渲染（`{season}`/`{episode}`/`{ext}`） |
| [execution_engine.py](../../backend/app/business/uploader/execution_engine.py) | 六阶段执行流水线（扫描 → 过滤 → 重命名 → 清单 → 查重 → 上传）、并发上传与重试、取消、结果回写 |
| [execution_logger.py](../../backend/app/business/uploader/execution_logger.py) | 日志通道：按执行写 `upload_logs/execution_{id}.log` + WebSocket 广播 log/progress/status 帧（不落库） |
| [schema.py](../../backend/app/business/uploader/schema.py) | Pydantic 请求/响应模型 |

## 数据层

- 无 Alembic；启动时 [database.py](../../backend/app/core/database.py) 用 `create_all` 建表 + `PRAGMA`/`ALTER TABLE` 轻量列级迁移，并写入默认全局配置。
- 废弃列清理：`obsolete_column_statements()` 会针对旧库中已不再映射的物理列（`open_list_execution.strip_series`/`server_name`、`open_list_config.log_to_db`、`open_list_server.name`）生成 `ALTER TABLE ... DROP COLUMN`，`init_db()` 在 SQLite ≥ 3.35 时执行，避免旧库 `NOT NULL` 列导致新代码 INSERT 失败（4.1.1 修复）。
- 数据表：`open_list_config`、`open_list_server`、`open_list_server_dir`、`open_list_task`、`open_list_execution`、`open_list_log`；上传管理另有 `upload_platform_config`、`upload_rename_rule`、`upload_task`、`upload_execution`、`upload_file_record`。
- 输出根目录：`open_list_config.output_root`（可空）。任务输出目录以 `/` 开头时由 [strm_generator.resolve_output_base()](../../backend/app/business/openlist/strm_generator.py) 相对其解析；为空回退 `CWD/output`（源码运行即 `backend/output`；冻结运行已 `chdir` 到数据目录，落在 `%LOCALAPPDATA%\up-video-strm\output`）。
- 默认 SQLite 路径：`./data/up_video_strm.db`（见 [settings.py](../../backend/app/core/settings.py)）；冻结运行指向数据目录下 `data/up_video_strm.db`。
- 旧库兼容：同目录下新库 `up_video_strm.db` 不存在、而旧库 `video_strm.db` 存在时，[settings.py](../../backend/app/core/settings.py) 自动沿用旧库文件（源码 `./data` 与冻结数据目录规则一致），避免升级后数据「消失」。

## 关键流程

1. 前端先 `POST /api/openlist/executions`（或 `/batch`、`/dirs`）落库拿 `execution_id` → 连 WebSocket 日志 → 再 `POST /executions/start` 启动，保证日志不丢帧。
2. `start_execution` 校验后 `asyncio.create_task(run_generation)`，受全局 `max_concurrent` 信号量限流。
3. 生成器产出 `.strm`（内容 `{base}/d/{path}`）与字幕，结束后回写执行记录并推送状态帧。
4. 日志以文件为权威源：任务调度 `openlist_logs/execution_{id}.log`、上传管理 `upload_logs/execution_{id}.log`，均经 WebSocket 实时推送；执行结束会输出汇总行（`上传完成：成功/跳过/失败/剩余待处理`、`任务结束：状态/处理数量/用时`）。

## 环境变量（backend/.env，应用配置）

| 变量 | 默认 | 说明 |
|------|------|------|
| `SQLITE_PATH` | `./data/up_video_strm.db` | SQLite 数据库路径（冻结运行相对数据目录） |
| `OPENLIST_LOG_DIR` | `./openlist_logs` | 任务调度执行日志目录 |
| `UPLOAD_LOG_DIR` | `./upload_logs` | 上传管理执行日志目录 |
| `ALLOWED_ORIGINS` | `["http://localhost:5173","http://127.0.0.1:5173"]` | CORS 允许来源 |

> 读取顺序：源码运行读 `backend/.env`；冻结运行先读数据目录 `.env`，再读 exe 同级 `.env`（后者优先）。

## 桌面外壳与冻结运行（后端专属补充）

冻结态路径解析（`data_root()` / `resource_dir()`）、端口回退、单实例互斥、stdio 重定向等通用行为见 [project.md](project.md)；`run.py` 实现要点：冻结态 `os.chdir(data_root)` → stdio 重定向到 `logs/app.log`（超 5 MB 转 `app.log.1`）→ 后台线程 `uvicorn.Server`（`timeout_graceful_shutdown=2`）+ 主线程 [app/desktop.py](../../backend/app/desktop.py) 原生窗口；exe 为 GUI 进程（`console=False`），不派生子进程。

- 桌面偏好与自启：[app/core/desktop_prefs.py](../../backend/app/core/desktop_prefs.py) 把 `start_minimized` / `close_to_tray` 存数据目录 `desktop.json`（不落库，避免桌面偏好影响其他运行方式）；开机自启读写 `HKCU\...\CurrentVersion\Run` 的 `up-video-strm` 值（仅冻结态；启动时若检测到旧版值 `video-strm` 已启用，自动改写成新值并删除旧值）。[api/desktop.py](../../backend/app/api/desktop.py) 暴露 `/api/desktop/info|autostart|preferences|open-data-dir|open-log-dir` 等接口（`open-log-dir` 按 `kind=openlist|upload` 用资源管理器打开对应日志目录），非桌面态只读、写操作返回 400。
- 窗口关闭默认走托盘：[desktop.py](../../backend/app/desktop.py) 监听 `closing` 事件返回 False 取消关闭，并延迟隐藏窗口（事件内直接 hide 会被 WinForms 取消关闭流程重新显示）；关窗时现读 `desktop.json` 的 `close_to_tray`，设置页/托盘改完立即生效。pystray 菜单「打开主界面 / 设置… / 快捷设置（开机自启、启动最小化、关窗收进托盘）/ 打开数据目录 / 退出」，「设置…」通过 `window.__upVideoStrmNavigate('/settings')`（前端 [main.ts](../../frontend/src/main.ts) 注册）切页而非整页重载；退出时 `icon.stop()` → `window.destroy()` → 服务关停。
- 窗口相关辅助：[app/core/tray_win.py](../../backend/app/core/tray_win.py) 负责 Windows 托盘图标探测与还原（Windows 11 托盘折叠场景），供托盘菜单与「修复托盘图标」接口调用。

启动器环境变量（进程环境，**不读取 .env**）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `UP_VIDEO_STRM_HOME` | `%LOCALAPPDATA%\up-video-strm` | 冻结态数据根目录（数据库/日志/输出） |
| `UP_VIDEO_STRM_HOST` | `127.0.0.1` | 监听地址 |
| `UP_VIDEO_STRM_PORT` | `8000` | 首选端口，占用时自动顺延（最多 20 个） |
| `UP_VIDEO_STRM_UI` | 冻结态 `window`、源码 `server` | `window` 开原生窗口；`server` 只跑控制台服务（配合浏览器排查） |
| `UP_VIDEO_STRM_TRAY` | `1` | 关闭窗口是否收进托盘；`0` 表示关窗即退出 |

> 旧名兼容：仅当 `UP_VIDEO_STRM_HOME` 未设置时回退读取旧变量 `VIDEO_STRM_HOME`；旧版 `VIDEO_STRM_HOST` / `VIDEO_STRM_PORT` / `VIDEO_STRM_UI` / `VIDEO_STRM_TRAY` 不再读取。

## 常用命令

安装、启动与测试命令见 [README.md 快速开始](../../README.md#方式二源码运行)；接口文档 `http://127.0.0.1:8000/docs`，健康检查 `GET /api/health`。
