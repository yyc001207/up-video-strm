# rules/project.md — 项目总览与运行约定

> 核心开发规范见 [AGENTS.md](../AGENTS.md)。本文档描述项目定位、技术栈、端口、两种运行方式、打包发布与冻结运行差异。
> 用户侧安装与操作说明见 [docs/用户手册.md](../docs/用户手册.md)。

## 项目定位

**up-video-strm** 是 OpenList 任务调度独立服务（前后端一体）：扫描 OpenList / AList 云端目录，为视频生成 `.strm` 下载链接并下载字幕。面向本地 / 家庭网络环境，**无登录**、**SQLite**（无 MySQL / Redis）、单进程 uvicorn worker。

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
| 后端 | `8000` | 源码运行 `uvicorn` 监听 `127.0.0.1:8000`；桌面版由 [backend/run.py](../backend/run.py) 探测可用端口 |
| 前端开发服务器 | `5173` | `vite`，`/api` 代理到后端 |

> 端口被占用时须自动切换可用端口（见 [AGENTS.md](../AGENTS.md) 规则 4），并保持前端代理目标与后端实际端口一致；端口变更需在启动日志与交付说明中告知用户。

## 运行方式

### 一、桌面安装版

- 由 [packaging/build.ps1](../packaging/build.ps1) 产出安装包，安装后运行 `up-video-strm.exe`。
- 启动后在**主线程**打开原生窗口，**后台线程**运行 uvicorn；关闭窗口默认收进托盘。
- 数据目录固定为 `%LOCALAPPDATA%\up-video-strm`，可用 `UP_VIDEO_STRM_HOME` 覆盖。
- 详见下文「冻结运行差异」。

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
- 前端构建产物同步到 `backend/frontend/dist` 后，后端会自动托管前端页面（含 SPA 回退）。

## 打包发布

- 打包脚本：[packaging/build.ps1](../packaging/build.ps1)；流程为 前端构建 → 同步产物 → PyInstaller onedir（[packaging/up-video-strm.spec](../packaging/up-video-strm.spec)） → Inno Setup（[packaging/installer.iss](../packaging/installer.iss)） → 清理中间目录。
- 唯一交付物：`dist/up-video-strm-<版本>-win-x64-setup.exe`；中间目录 `dist/up-video-strm/` 编译后自动清理（`-KeepStage` 保留）。
- 安装包按当前用户安装、免管理员，安装目录 `%LOCALAPPDATA%\Programs\up-video-strm`；AppId 固定，属同一产品升级（升级时先卸载旧版本，数据目录保留）。
- 打包环境要求：Windows x64 + Node.js >= 18 + Python **3.12**（`pydantic==2.6.0` 的 `pydantic-core` 无 3.13 预编译轮子）+ Inno Setup 6（缺失时脚本停在中间目录并提示）。
- 打包依赖见 [packaging/requirements-build.txt](../packaging/requirements-build.txt)（PyInstaller、pywebview、Pillow、pystray）。
- 版本号唯一来源为 [backend/app/version.py](../backend/app/version.py) 的 `__version__`，通过 [packaging/bump_version.py](../packaging/bump_version.py) 递增（同步前端与打包资源文件）；`build.ps1` 打包前会校验版本一致，禁止手改单处。

## 冻结运行差异

与源码运行相比，安装版（PyInstaller 冻结态）有以下差异，集中在 [backend/run.py](../backend/run.py)、[backend/app/core/paths.py](../backend/app/core/paths.py) 与 [backend/app/core/settings.py](../backend/app/core/settings.py)：

| 方面 | 冻结态行为 |
|------|-----------|
| 数据目录 | [data_root()](../backend/app/core/paths.py) 固定为 `%LOCALAPPDATA%\up-video-strm`（`UP_VIDEO_STRM_HOME` 可覆盖）；启动后 `os.chdir(数据目录)`，因此 `./data`、`./openlist_logs`、`./output` 等相对路径都落在数据目录下 |
| 资源定位 | `resource_dir()` 返回 `_MEIPASS`（onedir 为 `_internal`），用于定位打包进去的前端产物；exe 同级的 `frontend/dist` 也可作为托管目录 |
| 端口回退 | 首选 `8000`（`UP_VIDEO_STRM_PORT` 可改），被占用时顺延探测最多 20 个端口；全部失败则报错退出 |
| 进程模型 | 不派生子进程：后台线程运行 uvicorn，主线程运行原生窗口；exe 为 GUI 进程（无控制台），stdio 重定向到 `logs/app.log`（超 5 MB 轮转） |
| 单实例 | Windows 命名互斥体 `Local\up-video-strm-single-instance` 保证唯一实例，再次启动通过命名事件唤起已有窗口 |
| 配置读取 | `.env` 依次读取数据目录与 exe 同级（后者优先）；启动器环境变量（`UP_VIDEO_STRM_HOST` 等）只从进程环境读取，不读 `.env` |
| 前端托管 | [backend/app/main.py](../backend/app/main.py) 依次尝试 exe 同级与资源目录下的 `frontend/dist`，存在即挂载静态资源并做 SPA 回退 |

> 旧版本数据目录与旧环境变量的兼容行为见 [docs/用户手册.md](../docs/用户手册.md#12-旧版本数据兼容)。
