# video-strm 任务调度

从 Navly 个人导航页中提取的 **OpenList 任务调度模块**独立项目（前后端一体），面向本地部署：
扫描 OpenList 云端目录，为视频生成 `.strm` 下载链接并下载字幕。

- **无登录**：本地直接访问，无 JWT/权限体系
- **SQLite**：数据存本地文件，无需 MySQL/Redis
- **前后端一体**：FastAPI 后端 + Vue 3 前端，官方镜像 `yyc001207/video-strm:latest` 开箱即用

[![Build Windows Installer](https://github.com/yyc001207/video-strm/actions/workflows/windows-setup.yml/badge.svg)](https://github.com/yyc001207/video-strm/actions/workflows/windows-setup.yml)

> 📖 详细使用说明见 [用户手册](docs/用户手册.md)

## 快速部署（开箱即用）

使用已发布的 Docker 镜像 `yyc001207/video-strm:latest`，无需安装 Python / Node，只需 Docker。

### 环境要求

- 已安装 [Docker](https://www.docker.com/)（含 Docker Compose，Docker Desktop / 群晖 Container Manager 均已内置）

### 1. 准备 docker-compose.yml

创建部署目录并新建 `docker-compose.yml`：

```bash
mkdir video-strm && cd video-strm
```

内容如下（也可直接复制仓库内的 `docker-compose.example.yml`）：

```yaml
services:
  video-strm:
    image: yyc001207/video-strm:latest
    container_name: video-strm
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data                 # SQLite 数据库
      - ./openlist_logs:/app/openlist_logs  # 执行日志
      - ./output:/app/output             # STRM/字幕输出目录
    environment:
      - TZ=Asia/Shanghai
```

三个目录的作用：

| 主机目录 | 容器目录 | 说明 |
|----------|----------|------|
| `./data` | `/app/data` | SQLite 数据库（任务/服务器等配置） |
| `./openlist_logs` | `/app/openlist_logs` | 每次执行的日志文件 |
| `./output` | `/app/output` | STRM/字幕输出目录，任务输出目录以 `/` 开头（如 `/emby/电视剧`）时生成到 `/app/output/emby/电视剧` |

### 2. 启动服务

```bash
docker compose up -d
```

首次启动会自动拉取镜像并创建容器，查看状态：

```bash
docker compose ps          # 状态为 Up 即正常
docker compose logs -f     # 实时查看日志
```

### 3. 验证访问

- 前端页面：http://127.0.0.1:8000（远程服务器则用 `http://<服务器IP>:8000`）
- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/health（返回 `{"code": 200, ...}`）

> 首次访问后按「[使用流程](#使用流程)」配置：添加 OpenList 服务器（**默认不预置任何服务器**，不会出现示例地址）→ 创建任务 → 执行生成。

### 4. 升级更新

重新发布后执行以下命令即可更新到最新镜像（数据保留在 `./data` 等目录中）：

```bash
docker compose pull && docker compose up -d
```

### 常见问题

- **端口被占用**：把 `ports` 改为 `"8080:8000"`，访问地址相应变为 `http://127.0.0.1:8080`
- **生成的文件属主是 root**：容器以 root 运行，映射目录内文件属主为 uid 0，与媒体库共用目录时注意权限
- **想要直写宿主绝对路径**：任务输出目录以 `/` 开头会被统一收敛到 `/app/output` 下（安全设计）；如需输出到任意宿主路径，可把宿主媒体目录挂载到容器并调整任务输出目录

## 功能

| 模块 | 说明 |
|------|------|
| 全局配置 | 视频/字幕格式、并发度（`max_concurrent`）、生成限流（`pause_count`/`pause_time`）、输出目录前缀、输出根目录、SSL 校验开关、日志落库开关 |
| 服务器 | 多服务器配置（地址/Token/启停），支持多个父级目录（保存时校验格式/存在性/读写权限，通过后自动缓存一级子目录，可手动刷新缓存） |
| 任务 | 处理路径/输出目录/限流参数，强关联服务器（表格展示服务器地址、可按服务器筛选）；支持「快速添加」（抽屉式：目录树勾选/搜索，搜索可进入目录下钻选择子目录，批量生成任务配置），复制、单删、批量删除 |
| 执行管理 | 选服务器 + 多选任务配置批量执行（事务性）、取消；可选「系列层优化」（移除「电影」目录下的「系列」目录层级，默认关闭，strm 链接保留原始路径） |
| 任务历史 | 每任务最近执行 + 全部执行记录 + 日志回放/下载；按服务器筛选、详情页面化（展示处理路径/输出目录） |
| 实时日志 | WebSocket 实时推送，多任务切换查看 |
| 设置 | 顶栏「设置」进入独立页面（带返回）：开机自启、启动时/关闭时最小化到托盘、打开数据目录、版本与运行模式（桌面版专属，网页版只读） |
| 界面主题 | 浅色 / 深色 / 跟随系统一键切换（localStorage 记忆，首屏无闪烁） |

## 项目结构

```
video-strm/
├── backend/               # FastAPI 后端（SQLite）
│   ├── app/
│   │   ├── main.py            # 应用入口（仅 OpenList 路由）
│   │   ├── desktop.py         # 原生窗口外壳（pywebview/WebView2，打包运行使用）
│   │   ├── api/openlist.py    # 路由
│   │   ├── business/openlist/ # 业务（执行引擎/STRM 生成/日志泵/服务）
│   │   ├── core/              # settings（SQLite）/ database / models
│   │   ├── utils/             # 响应/工具
│   │   └── websocket/         # 实时日志连接管理
│   ├── tests/                 # pytest 冒烟测试
│   ├── requirements.txt
│   └── run.py
├── frontend/              # Vue 3 + Vite + Element Plus 前端
│   └── src/
│       ├── views/OpenList/    # 五页签（配置/任务/执行/历史/实时日志）
│       ├── components/        # 通用组件（如主题切换）
│       ├── stores/            # Pinia（openlist 业务 / theme 主题）
│       ├── api / types / utils
│       └── styles
├── Dockerfile             # 多阶段构建：前端构建 + 后端运行（前后端一体镜像）
├── packaging/             # Windows 打包：PyInstaller spec、构建脚本、Inno Setup 安装包脚本
├── .dockerignore
├── docker-compose.example.yml  # Docker Compose 部署示例
├── .github/workflows/     # GitHub Actions：自动构建并发布 Docker Hub
├── LICENSE                # MIT 许可证
└── README.md
```

## 本地开发（快速开始）

### 环境要求

- Python >= 3.11
- Node.js >= 18 + npm / pnpm

### 1. 后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

cp .env.example .env            # 可选，默认值即可运行

python run.py                   # 启动 http://127.0.0.1:8000（DEBUG=true 开启热重载；端口占用自动顺延）
```

- Swagger 文档：http://127.0.0.1:8000/docs
- 首次启动自动创建 SQLite 数据库（`backend/data/video_strm.db`）与默认全局配置，无需迁移
- 配置项见 `backend/.env.example`（SQLite 路径 / 日志目录 / CORS）

### 2. 前端

```bash
cd frontend
npm install          # 或 pnpm install
npm run dev          # 开发服务器 :5173（/api 代理 → http://127.0.0.1:8000，含 WebSocket）
```

生产构建：

```bash
npm run build        # vue-tsc 类型检查 + vite build，产出 frontend/dist/
npm run preview      # 本地预览构建产物
```

构建产物可由任意静态服务器托管（后端 API 地址通过 `VITE_API_BASE_URL` 配置，默认 `/api`，需自行反代或同源部署）。
后端在检测到 `backend/frontend/dist` 存在时也会自动托管前端页面（含 SPA 回退），Docker 镜像已内置该产物，开箱即用。

## Windows 安装包（exe）

无需 Python / Node 运行环境，安装后双击即用。构建机需 Windows x64 + Node.js ≥ 18 + Python **3.12**。

### 1. 准备打包环境（仅首次）

```bash
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r ..\packaging\requirements-build.txt
```

> 必须用 3.12：项目锁定 `pydantic==2.6.0`，其 `pydantic-core` 无 3.13 预编译轮子。用 pyenv 时可先 `pyenv local 3.12.8`。

### 2. 一键构建

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

脚本依次执行：`npm run build` → 同步产物到 `backend/frontend/dist` → PyInstaller（onedir）→ Inno Setup 生成安装包 → 清理中间目录，最终只留 `setup.exe`。
`-SkipFrontend` 复用已有前端产物，`-SkipInstaller` 只出中间目录（调试用），`-KeepStage` 保留 `dist/video-strm/`，
`-Dev` 只构建 onedir 并保留（本机调试用，不生成安装包）。

> **Inno Setup 6 未安装时**，脚本会停在中间目录并给出提示；装上 Inno Setup 6 后重跑即可得到 `setup.exe`。

> **安装包被系统拦截？** 若双击 setup 提示「应用程序控制策略已阻止此文件」，说明系统启用了 Smart App Control / WDAC。
> 开发期可用 `-Dev` 构建后直接运行 `dist\video-strm\video-strm.exe`；正式分发需要代码签名，或在系统设置中关闭 Smart App Control（关闭后需重装系统才能重新开启）。

### 3. CI 自动构建（GitHub Actions）

[.github/workflows/windows-setup.yml](.github/workflows/windows-setup.yml) 在 `windows-latest` 上跑同一条构建链路：

| 触发 | 行为 |
|------|------|
| 推送 `v*` 标签 | 校验标签与 `version.py` 一致 → 构建 → 上传 artifact → 附加到同名 GitHub Release |
| 推送 `master` / `main`、提交 PR（改动 `backend/`、`frontend/`、`packaging/`） | 构建 → 上传 artifact（保留 30 天），不发布 |
| Actions 页面手动触发 | 同分支推送 |

CI 使用 Python 3.12（`setup-python`）+ Node 22（`setup-node`），Inno Setup 6 由 Chocolatey 安装，pip/npm 均带缓存。
`build.ps1` 在 `backend/.venv` 不存在时会回退到 PATH 上的 `python`，因此 CI 不需要手动建虚拟环境。

### 4. 产物

| 路径 | 说明 |
|------|------|
| `dist/video-strm-<版本>-win-x64-setup.exe` | 唯一交付物：按当前用户安装、免管理员、含开始菜单/桌面快捷方式与可选开机自启（数据目录卸载保留） |

> 构建过程会在 `dist/video-strm/` 生成 onedir 中间目录供 Inno Setup 收集文件，编译完成后自动删除。

### 5. 运行行为

- **界面**：双击后直接弹出应用窗口（pywebview + Edge WebView2），**不需要浏览器、没有控制台窗口**
- **托盘常驻**：点窗口关闭按钮会收进系统托盘，服务继续在后台运行（适合长时间任务）；托盘菜单可「打开主界面 / 设置… / 打开数据目录 / 退出」，「退出」才会真正结束进程；「快捷设置」子菜单能直接勾选开机自启、启动时最小化、关窗收进托盘。`VIDEO_STRM_TRAY=0` 可改回关窗即退出
- **托盘图标可见性**：Windows 11 默认把新图标折叠进任务栏「^」，这一行为由系统控制、程序无法强制置顶；应用会把图标写入 `IsPromoted`（Explorer 重启或下次登录后生效），首次落在折叠区时会弹气泡提示，设置页也提供「固定到任务栏 / 任务栏设置」两个入口
- **重复启动**：再次双击 exe 或快捷方式不会另起一份，而是把已运行的窗口唤到前台；若上个进程正在退出，会自动等它释放后再启动，不会再误报「已在运行」
- **设置页**：可在应用内开关「开机自动启动」（写 HKCU Run）、「启动时最小化到托盘」、「关闭窗口时最小化到托盘」；关窗行为改完**立即生效**，启动最小化需重启应用；托盘「快捷设置」子菜单提供同样的开关，卸载时会自动清理自启项
- **环境依赖**：Windows 10/11 通常自带 WebView2 运行时；若提示缺失，安装 [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)（安装包可内置引导，见 `packaging/installer.iss`）
- **数据目录**：`%LOCALAPPDATA%\video-strm`（`data` / `openlist_logs` / `output` / `logs` / `webview`），可用 `VIDEO_STRM_HOME` 覆盖；卸载不删除，重装沿用
- **输出位置**：默认 `%LOCALAPPDATA%\video-strm\output`；在「全局配置 → 输出根目录」填媒体库绝对路径（如 `D:\Media\strm`，或点「选择」唤起系统文件夹选择框）后，任务的 `/xxx` 输出目录将改到该目录下。Docker 部署保持原样，留空即可
- **端口**：默认 8000，被占用时自动顺延到 8001、8002…（`VIDEO_STRM_PORT` 改首选端口），窗口按实际端口加载
- **单实例**：重复双击提示「已在运行」，不会起第二个服务或产生两套数据
- **日志**：`%LOCALAPPDATA%\video-strm\logs\app.log`，超过 5MB 轮转为 `app.log.1`
- **配置覆盖**：exe 同级或数据目录下的 `.env` 优先于内置默认值
- **调试**：`VIDEO_STRM_UI=server python run.py` 可退回控制台服务模式，便于排查启动问题

## 镜像构建与自动发布

### 本地构建镜像

```bash
# 构建镜像（Dockerfile 多阶段：先构建前端，再打包后端运行时）
docker build -t video-strm .

# 运行：挂载数据、日志与输出目录以便持久化
docker run -d --name video-strm \
  -p 8000:8000 \
  -v /path/to/data:/app/data \
  -v /path/to/openlist_logs:/app/openlist_logs \
  -v /path/to/output:/app/output \
  video-strm
```

- 访问 `http://<主机>:8000` 即前端页面；API 文档 `http://<主机>:8000/docs`
- 容器内默认 `ALLOWED_ORIGINS` 为空（同源访问无需跨域）；如前端与后端分离部署，可传环境变量覆盖：`-e 'ALLOWED_ORIGINS=["http://your-frontend:5173"]'`

### GitHub Actions 自动发布 Docker Hub

仓库已内置 `.github/workflows/docker-publish.yml`：**仅当推送 `v*` 标签（如 `v1.2.3`）时**自动构建并推送镜像。

#### 触发规则与镜像标签

| 触发 | 镜像标签 |
|------|----------|
| 推送标签 `v1.2.3` | `yyc001207/video-strm:latest`、`1.2.3`、`1.2`、`sha-<短哈希>` |
| 手动 `workflow_dispatch` | 按当前 ref 生成（分支上手动触发时仅 `latest` + `sha-<短哈希>`） |

- `latest` 始终指向最近一次发布的版本，便于稳定拉取
- 默认构建 **linux/amd64 + linux/arm64** 双架构，可直接在 x86 服务器与 ARM 群晖/NAS 上运行
- 如需单架构加速构建，删去工作流中 `platforms` 一行即可

#### 配置步骤（一次性）

1. 在 [Docker Hub](https://hub.docker.com/settings/security) 创建访问令牌（Access Token）
2. 仓库 → **Settings → Secrets and variables → Actions** 添加两个 Secret：
   - `DOCKERHUB_USERNAME`：Docker Hub 用户名
   - `DOCKERHUB_TOKEN`：上面创建的访问令牌
3. 推送标签（如 `git tag v1.0.0 && git push origin v1.0.0`）触发，镜像即发布到 `Docker Hub/yyc001207/video-strm`

#### 拉取部署

```bash
docker pull yyc001207/video-strm:latest
docker run -d --name video-strm -p 8000:8000 \
  -v /path/to/data:/app/data \
  -v /path/to/openlist_logs:/app/openlist_logs \
  -v /path/to/output:/app/output \
  yyc001207/video-strm:latest
```

## 测试

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest -v             # 覆盖配置自动 seed / 服务器 CRUD / 批量删除 / 执行创建与取消
```

## 使用流程

1. **全局配置**：确认视频/字幕格式与并发度（默认并发 1，可调大）
2. **服务器配置**：添加 OpenList 服务器地址与 Token，并配置父级目录（每行一个，自动补全 `/`）；保存时自动校验格式、存在性与读写权限，校验通过后自动缓存一级子目录，可随时点击「刷新缓存」更新
3. **任务配置**：手动新建（选择所属服务器 + 填写处理路径/输出目录/限流）或使用「快速添加」：选服务器 → 父级目录 → 目录树勾选目录（逐层展开、可搜索已缓存目录，搜索结果可**进入**继续下钻浏览其子目录并选择，可刷新缓存）→ 可选"输出目录带父级目录"（选中以父级目录开头，如 `/emby/电视剧`；不选以一级子目录开头，如 `/电视剧`）→ 一键生成多条任务配置（自动关联所选服务器；季文件夹自动命名为「上级名S季号」）；表格展示服务器地址，可按服务器筛选
4. **执行管理**：选择服务器 → 勾选该服务器的任务配置（可多选）→ 按需开启「系列层优化」（默认关闭：开启后输出目录移除「电影」目录下的「系列」层级，如 `动画电影/哆啦A梦系列/剧场版` → `动画电影/剧场版`，strm 内链接仍为原始完整路径）→ 批量执行（任务与服务器强关联，跨服务器执行会被拒绝）
5. **实时日志**：自动切换展示第一个任务日志，可下拉切换；完成后前往「任务历史」（可按服务器筛选，详情为独立页面，展示处理路径/输出目录）查看回放与下载

> 任务输出目录为 STRM/字幕落盘目录；远程 OpenList 服务器仅提供目录列表与下载接口，STRM 为链接文件不占媒体空间。

## 许可证

本项目采用 [MIT License](LICENSE)，可自由使用、修改与分发（含商用），需保留版权声明。
