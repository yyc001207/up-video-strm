# up-video-strm

**up-video-strm** 是面向 OpenList / AList 的 **任务调度独立服务（前后端一体）**：扫描云端目录，为视频生成 `.strm` 链接文件并下载字幕，供 Emby / Jellyfin 等媒体库使用。既可作为 Windows 桌面应用（原生窗口 + 系统托盘）直接运行，也可以从源码启动前后端进行开发与调试。

- **本地优先、无登录**：本地直接访问，无 JWT / 权限体系
- **单文件存储**：SQLite 本地数据库，无需 MySQL / Redis
- **前后端一体**：FastAPI 后端 + Vue 3 前端，后端检测到前端构建产物时自动托管页面（含 SPA 回退）
- **桌面化运行**：PyInstaller + Inno Setup 打包的安装包，双击即用，支持系统托盘、开机自启与单实例

> 📖 安装、配置、执行、日志、设置与常见问题，见 [用户手册](manual/用户手册.md)。

## 特性概览

| 模块 | 说明 |
|------|------|
| 全局配置 | 与任务调度平级的独立模块：单台 OpenList / AList 服务器（地址、Token、启停），父级目录保存时校验并缓存一级子目录，可手动刷新缓存；视频/字幕格式；123 云盘凭据（加密存储）与连通性测试 |
| 任务配置 | 任务自动绑定唯一服务器；支持新建、复制、批量删除与「快速添加」（目录树勾选 / 搜索 / 下钻）；页顶部集中管理默认运行参数（并发度、限流、SSL 校验、输出目录前缀与根目录） |
| 执行管理 | 多选任务批量执行、取消 |
| 任务历史 | 每任务最近执行 + 全部记录、日志回放 / 下载 |
| 实时日志 | WebSocket 实时推送，多任务切换查看 |
| 上传管理 | 与任务调度平级的独立模块，面向 123 云盘：上传任务（本地/云端目录、季数与起始集号）、重命名规则（`SxxExx` 模板预览）、执行管理（冲突策略 / 并发 / 重试 / 试运行）、实时日志、任务历史（文件明细 / 打开日志文件夹 / 重跑） |
| 上传执行 | 六阶段流水线（扫描 → 过滤 → 重命名 → 预上传清单 → 重复检查 → 上传）；同名冲突支持跳过 / 覆盖 / 追加后缀，进度与日志经 WebSocket 实时推送 |
| 自动化任务 | 与任务调度、上传管理平级的独立模块：把「上传任务」与「STRM 任务」串联为轮询链路——本地新增 → 上传到 123 云盘 → 校验 OpenList 可见性 → 触发 STRM 生成；含任务配置、执行管理、实时日志、任务历史与失败文件补偿 |
| 桌面版 | 原生 WebView2 窗口、系统托盘常驻、开机自启、启动/关闭最小化到托盘、单实例唤起 |
| 界面主题 | 浅色 / 深色 / 跟随系统一键切换，本地记忆、首屏无闪烁 |

> 各功能的操作步骤与说明统一见 [用户手册](manual/用户手册.md)，此处不再重复。

## 快速开始

### 方式一：Windows 安装包（推荐）

适合只想使用、不搭建开发环境的情况：无需安装 Python / Node。

1. 获取 `up-video-strm-<版本>-win-x64-setup.exe`（使用 [构建与打包](#构建与打包) 自行产出）。
2. 双击安装包，按向导完成安装（按当前用户安装，**免管理员权限**；安装目录为 `%LOCALAPPDATA%\Programs\up-video-strm`）。
3. 从开始菜单或桌面快捷方式启动，直接弹出应用窗口，**不经过浏览器、没有控制台窗口**。

- 系统要求：Windows 10 / 11 x64；应用窗口依赖 Microsoft Edge WebView2 运行时（Windows 10/11 通常自带，缺失时安装程序与启动都会给出提示）。
- 内置后端默认监听 `127.0.0.1:18765`（正式版/测试版一致，避开 `8000`/`8080` 等常用端口），端口占用时自动向后顺延，窗口地址始终使用实际端口。
- 运行数据统一存放在 `%LOCALAPPDATA%\up-video-strm`，卸载不会删除，重装沿用。
- 详细说明：[安装与启动](manual/用户手册.md#31-安装启动与托盘)、[桌面设置](manual/用户手册.md#312-设置与主题)。

### 方式二：源码运行

适合开发与调试，需要 Python 与 Node.js。

环境要求：

- Python >= 3.11
- Node.js >= 18 + npm（或 pnpm）

后端：

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt

python run.py                     # 默认 http://127.0.0.1:8000
```

- API 文档：`http://127.0.0.1:8000/docs`；健康检查：`GET /api/health`
- 首次启动会自动创建 SQLite 数据库 `backend/data/up_video_strm.db` 并写入默认全局配置，无需手动迁移
- 配置项见 `backend/.env.example`（SQLite 路径 / 日志目录 / CORS）；`DEBUG=true` 开启热重载
- 默认端口 `8000`，被占用时自动顺延到 `8001`、`8002`…，启动日志会打印实际地址

前端：

```bash
cd frontend
npm install                       # 或 pnpm install
npm run dev                       # 开发服务器 :5173，/api 代理到 http://127.0.0.1:8000（含 WebSocket）
```

生产构建与托管：

```bash
npm run build                     # vue-tsc 类型检查 + vite build，产出 frontend/dist/
npm run preview                   # 本地预览构建产物
```

前端 API 基址由 `VITE_API_BASE_URL` 控制（默认 `/api`）。后端检测到 `backend/frontend/dist` 存在时会自动托管前端页面（含 SPA 回退）；单独部署前端时需自行反代或同源部署。

> 源码运行时后端默认是控制台服务模式；若后端端口被占用自动顺延，需同步调整 `frontend/vite.config.ts` 中 `/api` 代理目标，避免页面请求打到错误端口。

## 文档导航

| 文档 | 内容 |
|------|------|
| [manual/用户手册.md](manual/用户手册.md) | 使用者视角：功能概述、业务流程、各页面操作步骤、常见场景、注意事项与常见问题 |
| [docs/rules/project.md](docs/rules/project.md) | 工程总览：定位、技术栈、端口、运行方式、打包发布、冻结运行差异 |
| [docs/rules/backend.md](docs/rules/backend.md) | 后端目录结构、业务模块、数据层、关键流程、环境变量、冻结运行 |
| [docs/rules/frontend.md](docs/rules/frontend.md) | 前端技术栈、目录结构、页面组件、接口与状态 |
| [CHANGELOG.md](CHANGELOG.md) | 版本演进记录：各版本的级别、变更要点与版本判定依据 |
| [docs/design/upload-module-plan.md](docs/design/upload-module-plan.md) | 上传管理模块设计计划：信息架构、数据模型、执行流水线、123 云盘对接与测试约束 |
| [docs/design/automation-module-plan.md](docs/design/automation-module-plan.md) | 自动化任务模块设计计划：四模块平级、B→OpenList 校验→A 链路、等待机制与触发来源 |
| [AGENTS.md](AGENTS.md) | 开发规范与交付前检查清单 |
| [LICENSE](LICENSE) | MIT 许可证 |

## 项目结构

```text
up-video-strm/
├── backend/                    # FastAPI 后端（SQLite）
│   ├── app/
│   │   ├── main.py             # 应用入口（路由挂载、前端托管、健康检查）
│   │   ├── desktop.py          # 原生窗口外壳（pywebview + WebView2）
│   │   ├── api/                # openlist 业务路由 / desktop 桌面设置路由
│   │   ├── business/openlist/  # 执行引擎、STRM 生成、日志、业务服务
│   │   ├── core/               # settings / database / models / paths / desktop_prefs
│   │   ├── utils/              # 响应封装与工具
│   │   └── websocket/          # 实时日志连接管理
│   ├── tests/                  # 冒烟测试（unittest，本地，不纳入版本管理）
│   ├── frontend/dist/          # 前端构建产物（由 build.ps1 自动同步生成）
│   ├── requirements.txt / requirements-dev.txt
│   ├── pytest.ini
│   ├── run.py                  # 启动入口（源码 / 冻结运行通用）
│   └── .env.example
├── frontend/                   # Vue 3 + Vite + Element Plus 前端
│   └── src/                    # views / components / stores / api / types / utils / styles
├── packaging/                  # Windows 打包：up-video-strm.spec / build.ps1 / installer.iss / bump_version.py
├── docs/                       # 工程规则（rules/）与设计 / 计划文档（design/）
├── manual/                     # 用户手册与界面截图
├── CHANGELOG.md                # 版本记录
├── AGENTS.md
├── LICENSE
└── README.md
```

## 构建与打包

Windows 安装包由 [packaging/build.ps1](packaging/build.ps1) 一键构建；测试版由 [packaging/build-test.ps1](packaging/build-test.ps1) 构建（内部以 `-Profile test` 复用同一脚本）。

构建机要求：Windows x64 + Node.js >= 18 + Python **3.12**（项目锁定 `pydantic==2.6.0`，其 `pydantic-core` 无 3.13 预编译轮子），并安装 Inno Setup 6（缺失时脚本会停在中间目录并给出提示）。

首次准备 Python 打包环境：

```bash
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r ..\packaging\requirements-build.txt
```

一键构建：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

脚本依次执行：`npm run build` → 同步前端产物到 `backend/frontend/dist` → PyInstaller（onedir，[packaging/up-video-strm.spec](packaging/up-video-strm.spec)）→ Inno Setup 生成安装包（[packaging/installer.iss](packaging/installer.iss)）→ 清理中间目录。

常用参数：

| 参数 | 作用 |
|------|------|
| `-Profile prod\|test` | 构建正式版 / 测试版，默认 `prod`；测试版隔离数据与安装，可并存 |
| `-SkipFrontend` | 复用已有前端产物，跳过 `npm run build` |
| `-SkipInstaller` | 只构建 onedir 中间目录，不生成安装包（调试用） |
| `-KeepStage` | 保留 `dist/<应用名>/` 中间目录（正式版 `up-video-strm`，测试版 `up-video-strm-test`） |
| `-Dev` | 只构建 onedir 并保留，直接运行 `dist\up-video-strm\up-video-strm.exe`（正式版）或 `dist\up-video-strm-test\up-video-strm-test.exe`（测试版） |
| `-Python <path>` | 指定打包用 Python；默认取 `backend\.venv\Scripts\python.exe`，其次 PATH 上的 `python` |

产物：

| 路径 | 说明 |
|------|------|
| `dist/up-video-strm-<版本>-win-x64-setup.exe` | 正式版交付物：按当前用户安装、免管理员、含开始菜单/桌面快捷方式与可选开机自启（数据目录卸载保留） |
| `dist/up-video-strm-test-<版本>-win-x64-setup.exe` | 测试版交付物：独立名称/安装目录/数据目录/自启动项/单实例，可与正式版同时安装运行 |
| `dist/up-video-strm/` | 正式版 PyInstaller onedir 中间目录（供 Inno Setup 收集文件，编译完成后自动删除；`-KeepStage` 可保留） |
| `dist/up-video-strm-test/` | 测试版 PyInstaller onedir 中间目录（同上，自动删除；`-KeepStage` 可保留） |

### 测试版（数据与正式版隔离）

测试版用于验证新功能而不影响正式使用：exe 名（`up-video-strm-test.exe`）、安装目录（`%LOCALAPPDATA%\Programs\up-video-strm-test`）、数据目录（`%LOCALAPPDATA%\up-video-strm-test`）、快捷方式、自启动项、单实例互斥体均与正式版区分，可同时安装、同时运行。版本号与正式版相同，产物名带 `-test`。

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build-test.ps1
```

构建时会把 `build_profile.json` 标记烘焙进应用资源目录，冻结运行时据此选择隔离数据目录，无需额外配置；源码运行不受影响。

版本号与打包约定：

- 唯一版本源是 `backend/app/version.py` 的 `__version__`；请通过 `packaging/bump_version.py` 修改（同步 `frontend/package.json`、`frontend/package-lock.json` 与 `packaging/version_info.txt`）。
- 打包前 `build.ps1` 会校验上述几处版本号一致，不一致直接失败。
- 正式版安装包使用固定 AppId，属于同一产品的升级；升级时先卸载旧版本（数据目录保留）再安装新版本。测试版使用独立 AppId 与名称，可与正式版并存。
- 若双击安装包提示「应用程序控制策略已阻止此文件」，说明系统启用了 Smart App Control / WDAC：开发期可用 `-Dev` 构建后直接运行 `dist\up-video-strm\up-video-strm.exe`；正式分发需要代码签名，或在系统设置中关闭 Smart App Control（关闭后需重装系统才能重新开启）。

### 发布（GitHub Actions）

推送 `v*` 标签时由 GitHub Actions 自动构建正式版安装包并发布到 GitHub Release；**分支 push 与 PR 不会触发**。

```bash
# 1) 先 bump 版本并提交（版本号必须与标签一致，流水线会校验）
backend/.venv/Scripts/python.exe packaging/bump_version.py minor
git add -A && git commit -m "chore: 发布 v<版本>"
# 2) 打并推送匹配的标签（推送标签即发布）
git tag v<版本>
git push origin v<版本>
```

流水线（[.github/workflows/release.yml](.github/workflows/release.yml)）依次：校验标签与版本一致 → 安装 Node/Python/Inno Setup → `npm ci` 与 Python 打包依赖 → 构建安装包 → 上传 artifact → 创建 Release 并附加 `up-video-strm-<版本>-win-x64-setup.exe`。仓库需启用 Actions；标签与版本不一致时流水线直接失败。

## 测试

后端测试使用标准库 `unittest`（无额外测试依赖）：

```bash
cd backend
python -m unittest discover -s tests -v
```

测试文件位于 `backend/tests/`，不纳入版本管理；提交前必须全部通过。

## 许可证

本项目采用 [MIT License](LICENSE)，可自由使用、修改与分发（含商用），需保留版权声明。
