# rules/project.md — 项目总览与部署约定

> 核心开发规范见 [AGENTS.md](../AGENTS.md)。本文档描述项目定位、技术栈、端口与部署细节。

## 项目定位

**video-strm** 是 OpenList 任务调度独立服务（前后端一体）：扫描 OpenList/AList 云端目录，为视频生成 `.strm` 下载链接并下载字幕。面向本地/家庭 NAS 部署，**无登录**、**SQLite**（无 MySQL/Redis）、单进程 uvicorn worker。

## 技术栈总览

| 层 | 技术 |
|----|------|
| 后端 | FastAPI + SQLAlchemy 2.0(async) + aiosqlite + httpx + Pydantic v2 |
| 前端 | Vue 3.5 `<script setup>` + TypeScript + Vite + Element Plus + Pinia + vue-router |
| 部署 | Docker 多阶段构建；GitHub Actions 在推送 `v*` tag 时发布 Docker Hub |

## 端口约定

| 服务 | 默认端口 | 说明 |
|------|----------|------|
| 后端 | `8000` | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| 前端开发服务器 | `5173` | `vite`，`/api` 代理到后端 |

> 端口被占用时须自动切换可用端口（见 AGENTS.md 规则 4），并同步更新前端代理目标。

## 部署

- **镜像构建**：根目录 [Dockerfile](../Dockerfile)，阶段 1 用 Node 构建前端，阶段 2 用 python:3.11-slim 运行后端，并把前端产物拷到 `/app/frontend/dist`。
- **前端托管**：后端 [backend/app/main.py](../backend/app/main.py) 检测到 `frontend/dist` 存在时自动托管静态资源并做 SPA 回退。
- **数据持久化**：`/app/data`（SQLite）、`/app/openlist_logs`（执行日志）、`/app/output`（STRM/字幕输出）建议挂载卷。
- **自动发布**：[.github/workflows/docker-publish.yml](../.github/workflows/docker-publish.yml)，推送 `v*` 标签时构建并推送 Docker Hub（默认 amd64 + arm64 双架构）。
- **Compose 示例**：[docker-compose.example.yml](../docker-compose.example.yml)。
- **Windows 安装包**：[packaging/](../packaging/)（PyInstaller onedir + Inno Setup）：`build.ps1` 一键产出安装包 `dist/video-strm-<版本>-win-x64-setup.exe`（唯一交付物，onedir 中间目录编译后自动清理，`-KeepStage` 可保留）；打包需 Python 3.12（`pydantic==2.6.0` 无 3.13 轮子），安装器按当前用户安装、免管理员。
- **安装包 CI**：[.github/workflows/windows-setup.yml](../.github/workflows/windows-setup.yml)，推送 `v*` 标签时校验标签与 `app/version.py` 一致、构建并附加到 GitHub Release；master/main 与 PR 只上传 artifact。
- **冻结运行的差异**：数据目录固定为 `%LOCALAPPDATA%\video-strm`（可用 `VIDEO_STRM_HOME` 覆盖），端口占用自动顺延，单实例互斥，[backend/run.py](../backend/run.py) 在进程内启动 uvicorn（不再派生子进程），[main.py](../backend/app/main.py) 通过 `sys._MEIPASS`/exe 同级定位前端产物。
