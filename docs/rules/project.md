# docs/rules/project.md — 项目总览与运行约定

> 核心开发规范见 [AGENTS.md](../../AGENTS.md)；后端/前端工程细节见 [backend.md](backend.md)、[frontend.md](frontend.md)；用户侧安装与操作说明见 [manual/用户手册.md](../../manual/用户手册.md)。

## 项目定位

**up-video-strm** 是 OpenList 任务调度独立服务（前后端一体）：扫描 OpenList / AList 云端目录，为视频生成 `.strm` 链接文件并下载字幕，供 Emby / Jellyfin 等媒体库使用。面向本地 / 家庭网络环境：**无登录**、SQLite（无 MySQL / Redis）、单个 uvicorn worker。

两种交付形态：

1. **Windows 桌面安装版**：PyInstaller onedir + Inno Setup 打包，双击即用，原生窗口 + 系统托盘。
2. **源码运行**：后端 `python run.py` + 前端 `npm run dev`，用于开发调试。

## 技术栈总览

| 层 | 技术 |
|----|------|
| 后端 | FastAPI + SQLAlchemy 2.0(async) + aiosqlite + httpx + Pydantic v2 |
| 前端 | Vue 3.5 `<script setup>` + TypeScript + Vite + Element Plus + Pinia + vue-router |
| 桌面外壳 | pywebview + Edge WebView2（原生窗口）、pystray（系统托盘） |
| 打包 | PyInstaller onedir + Inno Setup 6 |

## 端口约定

| 服务 | 默认端口 | 说明 |
|------|----------|------|
| 后端 | `8000` | 源码运行 `uvicorn` 监听 `127.0.0.1:8000`；桌面版由 [backend/run.py](../../backend/run.py) 探测可用端口 |
| 前端开发服务器 | `5173` | `vite`，`/api` 代理到后端 |

> 端口被占用时须自动切换（见 [AGENTS.md](../../AGENTS.md) 规则 4），并保持前端代理目标与后端实际端口一致；端口变更须在启动日志与交付说明中告知用户。

## 运行方式

### 一、桌面安装版

- 由 [packaging/build.ps1](../../packaging/build.ps1) 产出正式版安装包，安装后运行 `up-video-strm.exe`；[packaging/build-test.ps1](../../packaging/build-test.ps1) 产测试版（`up-video-strm-test.exe`，与正式版并存）。
- 主线程打开原生窗口、后台线程运行 uvicorn；关闭窗口默认收进托盘。
- 正式版数据目录 `%LOCALAPPDATA%\up-video-strm`、测试版 `%LOCALAPPDATA%\up-video-strm-test`，均可用 `UP_VIDEO_STRM_HOME` 覆盖；详见「冻结运行差异」。

### 二、源码运行

```bash
# 后端（默认 server 模式：控制台 uvicorn，不弹窗口）
cd backend
python run.py

# 前端（开发服务器 :5173，/api 代理 → 127.0.0.1:8000，含 WebSocket 透传）
cd frontend
npm run dev
```

- 源码运行时数据相对 CWD：`backend/data`（数据库）、`backend/openlist_logs`、`backend/output`。
- 设置 `UP_VIDEO_STRM_UI=window` 可在源码模式也打开原生窗口（便于调试桌面外壳）。
- 前端产物同步到 `backend/frontend/dist` 后，后端自动托管前端页面（含 SPA 回退）。

## 打包发布

- 一键脚本：正式版 [packaging/build.ps1](../../packaging/build.ps1)（`-Profile prod`，默认）；测试版 [packaging/build-test.ps1](../../packaging/build-test.ps1)（内部以 `-Profile test` 复用同一脚本）。流程：前端构建 → 同步产物到 `backend/frontend/dist` → PyInstaller onedir（[up-video-strm.spec](../../packaging/up-video-strm.spec)）→ Inno Setup（[installer.iss](../../packaging/installer.iss)）→ 清理中间目录。
- 交付物：正式版 `dist/up-video-strm-<版本>-win-x64-setup.exe`，测试版 `dist/up-video-strm-test-<版本>-win-x64-setup.exe`；中间目录 `dist/up-video-strm[-test]/` 编译后自动清理（`-KeepStage` 保留）。
- 安装包按当前用户安装、免管理员：正式版 `%LOCALAPPDATA%\Programs\up-video-strm`、测试版 `%LOCALAPPDATA%\Programs\up-video-strm-test`。正式版 AppId 固定、属同一产品升级；测试版使用独立 AppId/名称/自启动项/单实例，可与正式版并存。
- 测试版携带构建标记 `build_profile.json`，冻结运行时据此选择隔离的数据目录，无需额外配置。
- 构建机要求、常用参数、产物说明见 [README.md 构建与打包](../../README.md#构建与打包)；版本号约定见 [AGENTS.md](../../AGENTS.md) 规则 7（唯一源 `backend/app/version.py`，`build.ps1` 打包前校验四处一致）。

## 冻结运行差异

与源码运行相比，安装版（PyInstaller 冻结态）的差异集中在 [backend/run.py](../../backend/run.py)、[backend/app/core/paths.py](../../backend/app/core/paths.py) 与 [backend/app/core/settings.py](../../backend/app/core/settings.py)：

| 方面 | 冻结态行为 |
|------|-----------|
| 数据目录 | 正式版固定为 `%LOCALAPPDATA%\up-video-strm`，测试版为 `%LOCALAPPDATA%\up-video-strm-test`（由资源目录内 `build_profile.json` 区分；`UP_VIDEO_STRM_HOME` 均可覆盖）；启动后 `os.chdir(数据目录)`，`./data`、`./openlist_logs`、`./output` 等相对路径均落在数据目录下 |
| 资源定位 | `resource_dir()` 返回 `_MEIPASS`（onedir 为 `_internal`）定位打包的前端产物；exe 同级 `frontend/dist` 也可作为托管目录；`build_profile.json`（`prod`/`test`）记录构建类型 |
| 端口回退 | 首选 `8000`（`UP_VIDEO_STRM_PORT` 可改），被占用时顺延探测最多 20 个端口，全失败则报错退出 |
| 进程模型 | 不派生子进程：后台线程运行 uvicorn，主线程运行原生窗口；exe 为 GUI 进程（无控制台），stdio 重定向到 `logs/app.log`（超 5 MB 轮转） |
| 单实例 | Windows 命名互斥体 `Local\up-video-strm-single-instance`（测试版 `Local\up-video-strm-test-single-instance`）保证唯一实例，再次启动通过命名事件唤起已有窗口 |
| 配置读取 | `.env` 依次读取数据目录与 exe 同级（后者优先）；启动器环境变量（`UP_VIDEO_STRM_HOST` 等）只从进程环境读取，不读 `.env` |
| 前端托管 | [backend/app/main.py](../../backend/app/main.py) 依次尝试 exe 同级与资源目录下的 `frontend/dist`，存在即挂载静态资源并做 SPA 回退 |

> 旧版本数据目录与旧环境变量的兼容行为见 [manual/用户手册.md](../../manual/用户手册.md#12-旧版本数据兼容)。
