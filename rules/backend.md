# rules/backend.md — 后端工程说明

> 核心开发规范见 [AGENTS.md](../AGENTS.md)。本文档描述后端技术栈、目录结构、数据层、关键流程、环境变量与冻结运行行为。
> 项目定位与打包流程见 [rules/project.md](project.md)；用户侧说明见 [docs/用户手册.md](../docs/用户手册.md)。

## 技术栈

- FastAPI 0.110 + Uvicorn + SQLAlchemy 2.0（async）+ aiosqlite
- Pydantic v2 / pydantic-settings
- httpx（调用 OpenList/AList API），aiofiles
- 依赖清单：[backend/requirements.txt](../backend/requirements.txt)，测试依赖：[backend/requirements-dev.txt](../backend/requirements-dev.txt)

## 目录结构

```text
backend/
├── app/
│   ├── main.py                 # 应用入口（FastAPI 实例、异常处理、路由挂载、前端托管）
│   ├── desktop.py              # 原生窗口外壳（pywebview/WebView2 + pystray 托盘，冻结运行使用）
│   ├── version.py              # 唯一版本源 __version__
│   ├── api/openlist.py         # OpenList 路由（配置/服务器/任务/执行/历史/WebSocket）
│   ├── api/desktop.py          # 桌面版设置路由（信息 / 开机自启 / 托盘偏好 / 打开数据目录）
│   ├── business/openlist/      # 业务层（见下）
│   ├── core/                   # settings / paths / database / desktop_prefs / logger / exceptions / tray_win
│   │   └── models/openlist/    # ORM 模型
│   ├── utils/                  # 响应封装、helpers
│   └── websocket/              # 实时日志连接管理（manager.py）
├── tests/                      # pytest 冒烟测试（本地，不纳入版本管理）
├── requirements.txt / requirements-dev.txt
├── pytest.ini
├── run.py                      # 启动入口（源码/打包通用：端口探测、单实例、原生窗口）
├── .env.example                # 环境变量示例
└── data/ openlist_logs/ output/  # 源码运行时生成（数据库/日志/输出）
```

## 业务层模块职责（`app/business/openlist/`）

| 文件 | 职责 |
|------|------|
| [service.py](../backend/app/business/openlist/service.py) | 业务核心：全局配置、服务器 CRUD、父级目录校验与缓存、任务、执行管理、任务历史、日志读取、配置 seed |
| [strm_generator.py](../backend/app/business/openlist/strm_generator.py) | STRM 生成器：递归扫描目录、生成 `.strm`、下载字幕、失效清理、限流暂停 |
| [openlist_api.py](../backend/app/business/openlist/openlist_api.py) | OpenList/AList API 客户端（list_files / get / mkdir / remove / 流式下载，含重试） |
| [execution_engine.py](../backend/app/business/openlist/execution_engine.py) | 执行引擎：后台运行任务、并发信号量、结果回写 |
| [execution_logger.py](../backend/app/business/openlist/execution_logger.py) | 日志通道：日志 → WebSocket 广播 + 落库 + 日志文件 |
| [dir_cache.py](../backend/app/business/openlist/dir_cache.py) | 目录缓存（内存，TTL 300s，超量清理） |
| [task_status_manager.py](../backend/app/business/openlist/task_status_manager.py) | 任务取消标记（进程内） |
| [schema.py](../backend/app/business/openlist/schema.py) | Pydantic 请求/响应模型 |

## 数据层

- 无 Alembic；启动时 [database.py](../backend/app/core/database.py) 用 `create_all` 建表 + `PRAGMA`/`ALTER TABLE` 做轻量列级迁移 + 写入默认全局配置。
- 数据表：`open_list_config`、`open_list_server`、`open_list_server_dir`、`open_list_task`、`open_list_execution`、`open_list_log`。
- 输出根目录：`open_list_config.output_root`（可空）。任务输出目录以 `/` 开头时由 [strm_generator.resolve_output_base()](../backend/app/business/openlist/strm_generator.py) 相对该目录解析；为空回退 `CWD/output`——源码运行即 `backend/output`，冻结运行启动时已 `chdir` 到数据目录，因此落在 `%LOCALAPPDATA%\up-video-strm\output`。
- 默认 SQLite 路径：`./data/up_video_strm.db`（见 [settings.py](../backend/app/core/settings.py)）；冻结运行指向数据目录下 `data/up_video_strm.db`。
- 旧库兼容：同目录下新库 `up_video_strm.db` 不存在、而旧库 `video_strm.db` 存在时，[settings.py](../backend/app/core/settings.py) 自动沿用旧库文件（源码的 `./data` 与冻结数据目录规则一致），避免升级后数据「消失」。

## 关键流程

1. 前端先 `POST /api/openlist/executions`（或 `/batch`、`/dirs`）落库拿 `execution_id` → 连 WebSocket 日志 → 再 `POST /executions/start` 启动，保证日志不丢帧。
2. `start_execution` 校验后 `asyncio.create_task(run_generation)`；受全局 `max_concurrent` 信号量限流。
3. 生成器产出 `.strm`（内容 `{base}/d/{path}`）与字幕，结束后回写执行记录并推送状态帧。
4. 日志以文件 `openlist_logs/execution_{id}.log` 为权威源，DB 仅作回退。

## 环境变量（backend/.env，应用配置）

| 变量 | 默认 | 说明 |
|------|------|------|
| `SQLITE_PATH` | `./data/up_video_strm.db` | SQLite 数据库路径（冻结运行相对数据目录） |
| `OPENLIST_LOG_DIR` | `./openlist_logs` | 执行日志目录 |
| `ALLOWED_ORIGINS` | `["http://localhost:5173","http://127.0.0.1:5173"]` | CORS 允许来源 |

> 读取顺序：源码运行读 `backend/.env`；冻结运行先读数据目录 `.env`，再读 exe 同级 `.env`（后者优先）。

## 打包与冻结运行

- 打包配置在 [packaging/](../packaging/)：`build.ps1`（前端构建 → PyInstaller onedir → Inno Setup → 清理中间目录），唯一交付物为 `dist/up-video-strm-<版本>-win-x64-setup.exe`；打包额外依赖见 [requirements-build.txt](../packaging/requirements-build.txt)（PyInstaller、pywebview、Pillow、pystray）。
- 冻结态路径解析集中在 [app/core/paths.py](../backend/app/core/paths.py)：`resource_dir()` 取 `_MEIPASS`（onedir 为 `_internal`）定位前端产物；`data_root()` 给出可写数据根目录（默认 `%LOCALAPPDATA%\up-video-strm`，`UP_VIDEO_STRM_HOME` 可覆盖；旧版目录 `%LOCALAPPDATA%\video-strm` 存在且新目录不存在时原地沿用旧目录，不复制、不搬移）。
- [settings.py](../backend/app/core/settings.py) 在冻结态把 `sqlite_path` / `openlist_log_dir` 默认值指向数据根目录；源码运行仍是相对 CWD 的 `./data`、`./openlist_logs`。
- [run.py](../backend/run.py) 在冻结态：`os.chdir(data_root)` → stdio 重定向到 `logs/app.log`（超 5 MB 轮转为 `app.log.1`）→ 单实例互斥 → 端口探测 → 后台线程 `uvicorn.Server`（`timeout_graceful_shutdown=2`）+ 主线程 [app/desktop.py](../backend/app/desktop.py) 原生窗口（pywebview/WebView2）；exe 为 GUI 进程（`console=False`），不派生子进程（冻结后 `sys.executable` 就是 exe 本身）。
- 窗口关闭默认走托盘：[desktop.py](../backend/app/desktop.py) 监听 `closing` 事件返回 False 取消关闭，并延迟隐藏窗口（事件内直接 hide 会被 WinForms 取消关闭流程重新显示）；关窗时现读 `desktop.json` 的 `close_to_tray`，设置页/托盘改完立即生效。pystray 菜单「打开主界面 / 设置… / 快捷设置（开机自启、启动最小化、关窗收进托盘）/ 打开数据目录 / 退出」，「设置…」通过 `window.__upVideoStrmNavigate('/settings')`（前端 [main.ts](../frontend/src/main.ts) 注册）切页而非整页重载；退出时 `icon.stop()` → `window.destroy()` → 服务关停。
- 桌面偏好与自启：[app/core/desktop_prefs.py](../backend/app/core/desktop_prefs.py) 把 `start_minimized` / `close_to_tray` 存数据目录 `desktop.json`（不落库，避免桌面偏好影响其他运行方式），开机自启读写 `HKCU\...\CurrentVersion\Run` 的 `up-video-strm` 值（仅冻结态；启动时若检测到旧版值 `video-strm` 已启用，会自动改写成新值并删除旧值）；[api/desktop.py](../backend/app/api/desktop.py) 暴露 `/api/desktop/info|autostart|preferences|open-data-dir` 等接口，非桌面态只读、写操作返回 400。
- 窗口相关辅助：[app/core/tray_win.py](../backend/app/core/tray_win.py) 负责 Windows 托盘图标的探测与还原（Windows 11 托盘折叠场景），供托盘菜单与「修复托盘图标」接口调用。

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

```bash
# 在 backend/ 下
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
python run.py                                     # 启动 http://127.0.0.1:8000（DEBUG=true 热重载）

pip install -r requirements-dev.txt
python -m pytest -v                               # 运行测试
```

接口文档：`http://127.0.0.1:8000/docs`；健康检查：`GET /api/health`。
