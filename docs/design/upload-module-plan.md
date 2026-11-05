# 上传管理模块 · 设计计划

> 状态：计划评审中（未实施，先对齐方案再开发）
> 模块定位：与「任务调度」平级的新模块，自动把本地视频上传到 123 云盘
> 参考实现：任务调度模块（`frontend/src/views/schedule/`、`backend/app/business/openlist/`、`App.vue` 模块化导航）
> 外部依赖：123 云盘开放平台 API（凭据 `clientID` + `clientSecret`）

本文档为需求的完整计划：模块结构、全局配置扩展、数据模型、执行流水线、123 云盘对接、页面设计、测试约束与实施阶段。开发完成后同步更新 `docs/rules/`、`manual/用户手册.md`、`README.md` 与 `CHANGELOG.md`。

## 1. 背景与目标

- **背景**：任务调度模块已实现云端 STRM 生成；本地视频若要放到 123 云盘观看，目前只能手工整理、重命名、上传。
- **目标**：一条可配置、可观测的自动化流水线：

```text
扫描本地文件 → 过滤出视频文件 → 重命名 → 预上传文件清单 → 重复检查 → 上传到 123 云盘
```

- 提供五个子功能：任务配置、重命名规则、执行管理、实时日志、任务历史。
- **非目标（一期）**：定时执行、多网盘 / 多 123 账号、上传后删除本地源文件、跨进程断点续传（进程重启后恢复）。
- **硬性约束**：所有涉及 123 云盘的联调与测试，**只允许使用 123 云盘的 `/test` 目录**（见 §8），不得操作其他目录。

## 2. 信息架构与导航

侧栏包含三个平级模块，顺序数据化（`frontend/src/App.vue` 的 `modules`）：

| 顺序 | 模块 | 路由命名空间 | 说明 |
|------|------|--------------|------|
| 1 | 全局配置 | `/config` | 现有：服务器 + 视频/字幕格式；**新增「123 云盘」卡片** |
| 2 | 任务调度 | `/schedule/*` | 现有，不变 |
| 3 | 上传管理 | `/upload/*` | 新增，页面结构 / 交互样式对齐任务调度 |

上传管理内部路由（默认页为任务配置：首次使用需先配置凭据与任务）：

| 路由 | 页面文件 | 对应任务调度页面 | 说明 |
|------|----------|------------------|------|
| `/upload` | — | — | 重定向到 `/upload/tasks` |
| `/upload/tasks` | `views/upload/TaskConfig.vue` | `TaskManage.vue` | 上传任务 CRUD + 顶部「默认运行参数」卡 |
| `/upload/rename` | `views/upload/RenameRules.vue` | 新增页面 | 命名模板列表（重命名规则） |
| `/upload/execution` | `views/upload/Execution.vue` | `Execution.vue` | 三卡片：选择任务 / 执行参数 / 已选任务 + 正在执行表 |
| `/upload/realtime` | `views/upload/RealtimeLog.vue` | `RealtimeLog.vue` | WebSocket 实时日志（三段式） |
| `/upload/history` | `views/upload/TaskHistory.vue` | `TaskHistory.vue` | 执行历史 + 文件粒度详情、日志回放 / 下载 |

- 路由 meta：`title`/`description` 供顶栏标题与说明；`/upload/*` 与 `/schedule/*` 互不影响。
- 复用壳层：侧栏折叠、主题切换、运行中状态胶囊（`/upload/*` 页面的「运行中 N」计入全局胶囊）。
- 新增组件：`views/upload/components/RemoteDirPanel.vue`（123 云盘目录选择器，参考 `schedule/components/DirTreePanel.vue`，数据源换成 123 云盘目录接口）。

## 3. 全局配置扩展：123 云盘凭据

在全局配置模块（`frontend/src/views/config/GlobalConfig.vue`）新增第三张卡「123 云盘」，与「服务器配置」「视频与字幕格式」并列：

| 项 | 说明 |
|----|------|
| clientID | 123 云盘开放平台应用 ID |
| clientSecret | 应用密钥，**加密存储、回显脱敏**（只回显如 `****abcd`），任何日志不得输出明文 |
| 凭据状态 | 未配置 / 已配置 / 鉴权失败（附错误原因） |
| 测试连接 | 用当前凭据换取 access_token 并读取根目录，验证凭据与网络 |
| Token 缓存 | access_token 由后端自动获取与续期（有效期约 30 天，提前刷新），用户无需手填 |

- 后端：新增 `upload_platform_config` 表（单行）：`client_id`、`client_secret`（密文）、`access_token`（密文）、`token_expires_at`、`updated_time`。
- 接口：`GET /api/upload/config`（脱敏返回）、`PUT /api/upload/config`（只提交有值的字段，留空表示不修改 secret）、`POST /api/upload/config/test-connection`。
- 配置读取优先级不做环境变量覆盖（一期仅界面配置），与服务器配置保持一致。

## 4. 数据模型（新增表，SQLite）

| 表 | 关键字段 | 说明 |
|----|----------|------|
| `upload_platform_config` | `id`、`client_id`、`client_secret`、`access_token`、`token_expires_at`、`updated_time` | §3，单行 |
| `upload_rename_rule` | `id`、`name`、`template`、`description`、`enabled`、`created_time`、`updated_time` | 命名模板列表（§6.2） |
| `upload_task` | `id`、`name`、`local_dirs`(JSON)、`remote_dir`、`recursive`、`exclude_dirs`(JSON)、`created_time`、`updated_time` | 上传任务；`remote_dir` 为 123 云盘目标目录路径（如 `/test`） |
| `upload_execution` | `id`、`task_id`、`task_name`、`local_dirs`(JSON)、`remote_dir`、`conflict_policy`、`concurrency`、`slice_size`、`max_retries`、`dry_run`、`status`、`file_total`、`file_success`、`file_skipped`、`file_overwritten`、`file_failed`、`bytes_uploaded`、`duration_seconds`、`log_path`、`started_time`、`finished_time`、`created_time` | 一次执行（`status`: running/success/fail/cancelled） |
| `upload_file_record` | `id`、`execution_id`、`local_path`、`remote_name`、`size`、`md5`、`status`、`phase`、`reason`、`remote_file_id`、`replaced_file_id`、`created_time` | 文件粒度历史（支持「仅重跑失败项」、覆盖留痕） |

- 迁移策略对齐现有模块：`core/database.py` 启动时建表 / `_ensure_*_columns` 兼容旧库，不破坏已有数据。
- 日志与 WS 复用任务调度的模式：日志只写文件（`execution_logger` 的 `LogPump` 模式），WS 推送进度/日志帧；历史查询不依赖数据库日志表。

## 5. 123 云盘开放平台对接（`business/uploader/pan123_client.py`）

所有 HTTP 调用集中在 `pan123_client.py` 封装（`httpx.AsyncClient`），业务层不直接拼 URL。

### 5.1 鉴权与限流

- `POST /api/v1/access_token`（`clientID` + `clientSecret`）→ `accessToken`、有效期；缓存到 `upload_platform_config`，过期前自动刷新。
- 后续请求头：`Authorization: Bearer <accessToken>`、`Platform: open`。
- 限流：全局并发上限（默认 1–2），HTTP 429 / 5xx 指数退避重试（默认 3 次，可配置）。
- 端点与字段以[官方开放平台文档](https://www.123pan.com/developer)为准，接入时逐一核对；本文档只约束流程与封装边界。

### 5.2 上传流程（官方 v2 分片流程）

```text
create_file(parentFileId, filename, etag/md5, size, duplicate)
  ├─ reuse = true  → 秒传成功，结束
  └─ reuse = false → 返回 preuploadID + sliceSize
        → 逐片（sliceNo 从 1 开始）获取 presignedURL → PUT 上传分片
        → （可选）列举已上传分片做 MD5 比对（文件 < sliceSize 时跳过）
        → 上传完毕：async=false 且 fileID≠0 → 完成；async=true → 每 1s 轮询结果
```

- `duplicate`：`1` = 保留两者（同名并存），`2` = 覆盖原文件。**覆盖策略优先用 `duplicate=2`**（服务端替换，等价于「上传成功后旧文件被替换」）；上传完成后按预检记录的旧 `fileID` 做一次幂等删除兜底，兼容 API 对该参数语义的差异。
- 其他封装：`list_files(parentFileId, 分页)`（列目标目录全部文件，构建 `filename → fileId` 索引）、`delete_files([fileId])`（删除进回收站，可人工找回）、`find_file(name)`。
- 远端目录路径需转为 `parentFileId`：从根目录逐级匹配目录名，不存在时一期直接报错（不自动建目录），提示先手工创建。

## 6. 执行流水线（`business/uploader/`）

### 6.1 六个阶段（对应需求流程）

| 阶段 | 说明 | 失败处理 |
|------|------|----------|
| 1. 扫描本地文件 | 遍历任务 `local_dirs`（`recursive` 控制递归，跳过 `exclude_dirs`）、跳过系统/隐藏文件 | 目录不存在 → 执行失败并提示 |
| 2. 过滤视频文件 | 复用**全局配置的「视频格式」**扩展名列表（如 `mp4,mkv,avi`） | 无匹配 → 执行成功但文件数为 0 |
| 3. 重命名 | 使用指定命名模板（§6.2）生成 `remote_name`；非法字符清洗（`\ / : * ? " < > \|`）、长度截断、保留扩展名 | 模板无法生成合法名 → 该文件标记失败，继续后续文件 |
| 4. 预上传清单 | 产出 `本地路径 / 大小 / MD5 / 新文件名`，落 `upload_file_record`；`dry_run` 时到此为止，页面可预览清单 | — |
| 5. 重复检查 | 分页拉取目标目录文件列表并缓存为 `name → fileId`；同名文件按执行参数决策 | 目标目录读取失败 → 执行失败（不盲传） |
| 6. 上传 | 逐文件走 §5.2 流程；并发受限额；每文件状态写入记录与日志 | 单文件失败不影响其他文件，执行最终标记为 fail 并给出失败数 |

### 6.2 重命名规则（命名模板）

- 规则列表是「候选命名模板」，每个上传任务指定使用其中一条（新增任务时默认选中第一条启用的规则；执行时也可临时使用任务绑定的模板）。
- 模板变量：

| 变量 | 含义 | 示例 |
|------|------|------|
| `{name}` | 原文件名（去扩展名） | `第01集` |
| `{ext}` | 扩展名（不含点） | `mp4` |
| `{date}` | 当天日期，默认 `YYYYMMDD` | `20261105` |
| `{index}` | 序号，支持 `{index:3}` 补零到 3 位 | `001` |
| `{drama}` | 剧名（按任务配置的「剧名」字段或本地目录名推断） | `我的剧` |
| `{season}` / `{episode}` | 季 / 集（从文件名 `S01E02`、`第01集` 等常见格式解析；解析失败留空并告警） | `01` / `02` |

- 示例模板：`{name}.{ext}`、`{date}_{name}.{ext}`、`{drama}_S{season}E{episode}.{ext}`。
- 规则页提供**实时预览**：输入示例文件名，展示「原名 → 新名」及清洗结果；非法字符、空名、超长名给出明确提示。
- 一期变量支持 `{name}`、`{ext}`、`{date}`、`{index}`；`{drama}`、`{season}`、`{episode}` 与解析规则建议一期同步实现（成本低），剧集命名复杂场景后置。

### 6.3 冲突策略（执行参数，执行管理页选择）

| 策略 | 行为 |
|------|------|
| **覆盖** | 先上传新文件（`create_file` 的 `duplicate=2` 覆盖同名文件），成功后按预检记录旧 `fileID` 幂等删除兜底；失败则保留原文件 |
| **跳过** | 目标目录已存在同名文件 → 不上传，记录「已存在，跳过」 |
| **追加后缀** | 新文件名追加 `_1`、`_2`… 直到目标目录无同名（如 `123.mp4 → 123_1.mp4`），以 `duplicate=1` 上传，新旧都保留 |

- 判定依据：阶段 5 的远端文件名集合（大小写敏感/不敏感以 123 云盘实际行为为准，接入时实测）。
- 所有策略均写入文件记录：`status` + `replaced_file_id`（覆盖时），便于历史追溯与回收站找回。

### 6.4 执行参数

| 参数 | 位置 | 默认 |
|------|------|------|
| 冲突策略 | 执行管理页（每次执行可选） | 跳过 |
| 并发数 | 任务配置「默认运行参数」+ 执行时可调 | 2 |
| 分片大小 | 任务配置「默认运行参数」 | 由 API 返回的 `sliceSize` 为准，可用配置覆盖 |
| 失败重试次数 | 任务配置「默认运行参数」 | 3 |
| 试运行（dry-run） | 执行管理页 | 关闭 |

- 执行参数在开始执行时固化到 `upload_execution`，保证历史可复现。

## 7. 后端 / 前端结构

```text
backend/app/business/uploader/
├── schema.py            # Pydantic：配置 / 规则 / 任务 / 执行 / 历史
├── pan123_client.py     # 123 云盘 API 封装：token、列目录、create_file、分片、删除、限流重试
├── rename_engine.py     # 命名模板渲染 + 变量解析 + 非法字符清洗
├── scanner.py           # 本地扫描 + 视频过滤 + MD5 计算
├── execution_engine.py  # 六阶段流水线编排、并发与取消
├── execution_logger.py  # 文件日志 + WS 推送（对齐 openlist）
└── task_status_manager.py
backend/app/api/uploader.py    # /api/upload/* 路由（main.py include_router，prefix="/api/upload"）
```

- 前端配套：`frontend/src/api/uploader.ts`、`frontend/src/types/uploader.ts`、`frontend/src/views/upload/*`。
- 接口统一 `success_response` 包装（`code=200`、分页 `total`），异常用现有 `BadRequestException` / `NotFoundException`。
- WebSocket：`/api/upload/ws/{execution_id}`，帧格式沿用 `log` / `progress` / `status` 三类。

## 8. 测试与验证约束（硬性）

1. **只允许使用 123 云盘的 `/test` 目录**（或 `/test` 下的子目录）——所有联调、手工验证、集成测试、示例数据、`remote_dir` 默认值均以 `/test` 为准；禁止使用根目录、`/test` 之外的任何目录。
2. 单元测试 mock `pan123_client`（`httpx.MockTransport`），覆盖：token 刷新、重命名变量与清洗、清单生成、三种冲突策略、分片/秒传分支、取消；不发起真实网络请求。
3. 真实联调：使用小文件（< 1 MB）上传到 `/test`，验证后清理；凭据使用测试应用，**任何真实 `clientSecret` 不得提交仓库或写入日志**。
4. 前端：`npm run type-check` + `npm run build` 必过；后端在 `backend/tests/` 补用例并实际运行全部通过（tests 目录不提交，沿用现有约定）。
5. 测试脚本 / 文档中的默认远端目录固定写 `/test`，避免误操作。

## 9. API 约定

| 方法 | 路径 | 说明 |
|------|------|------|
| GET / PUT | `/api/upload/config` | 读取（脱敏）/ 保存 123 云盘凭据 |
| POST | `/api/upload/config/test-connection` | 凭据连通性测试 |
| GET / POST / PUT / DELETE | `/api/upload/rules`、`/rules/{id}` | 命名规则 CRUD（含 `enabled` 启停） |
| POST | `/api/upload/rules/preview` | 模板预览（示例文件名 → 新名） |
| GET / POST / PUT / DELETE | `/api/upload/tasks`、`/tasks/{id}` | 上传任务 CRUD / 批量删除 |
| POST | `/api/upload/executions`、`/executions/batch` | 创建执行（单任务 / 多任务） |
| POST | `/api/upload/executions/start`、`/cancel` | 启动 / 取消（创建后可先连 WS 再启动，对齐调度模块时序） |
| GET | `/api/upload/executions`、`/executions/{id}` | 执行列表 / 详情 |
| GET | `/api/upload/history`、`/history/task/{taskId}` | 历史汇总 / 按任务历史 |
| GET | `/api/upload/executions/{id}/records`、`/logs`、`/log-download` | 文件记录分页、日志读取、日志下载 |
| WS | `/api/upload/ws/{execution_id}` | 实时日志 / 进度 / 状态 |

## 10. 页面设计要点（样式对齐任务调度）

- **任务配置**：顶部「默认运行参数」卡（并发、分片、重试、默认冲突策略）+ 编辑抽屉；工具栏搜索 / 新建 / 批量删除；表格列：任务名（主行）+ 本地目录/云端目录（副行）、最近执行、操作；空态 CTA。
- **重命名规则**：列表（名称、模板、示例、启用状态、操作）；新建/编辑弹窗含模板输入、变量说明表、实时预览；删除确认写明影响。
- **执行管理**：三卡片一行（选择任务 / 执行参数 / 已选任务）+ 正在执行表（状态圆点、计数右对齐、取消）；`dry-run` 开关生成清单预览。
- **实时日志**：进度摘要（文件总数 / 成功 / 跳过 / 失败 / 字节数）+ 终端日志区（级别着色、行号、自动滚动）+ 底部工具条（级别过滤、搜索、清屏、下载）。
- **任务历史**：执行列表 → 详情页（文件粒度表格：本地文件、远端文件名、大小、状态、原因、云端 fileId）+ 日志抽屉 / 下载。
- 全部沿用现有令牌与组件规范（`variables.scss`、`StatusDot`、空态、危险操作确认文案），不新增硬编码色值。

## 11. 实施阶段

1. **阶段一：凭据与 API 封装**——`upload_platform_config` 表、全局配置「123 云盘」卡、`pan123_client`（token / 列目录 / create_file / 分片 / 删除）+ mock 单测；在 `/test` 目录手工验证凭据与列目录。
2. **阶段二：任务与规则**——`upload_task` / `upload_rename_rule` 表与接口、任务配置页、重命名规则页（含预览）、`rename_engine` + `scanner` 单测。
3. **阶段三：执行流水线**——清单 / 重复检查 / 上传 / 删除兜底 / 取消；执行管理页（三卡片 + 执行参数 + 正在执行）；WS 实时日志；在 `/test` 做端到端验证（三种冲突策略各覆盖一次）。
4. **阶段四：历史与收尾**——文件粒度历史、日志回放/下载、失败重跑；手册 / README / rules 文档同步；`bump_version.py minor`（4.2.0 → 4.3.0）+ CHANGELOG 条目；打包验证（`build.ps1 -SkipFrontend` 或完整构建）。

每个阶段独立 `feat:` commit，逐项 `git add`，不 push；版本在阶段四统一递增一次。

## 12. 待确认 / 开放问题

| # | 问题 | 当前建议 |
|---|------|----------|
| 1 | 覆盖策略的云端实现 | 用 `create_file` 的 `duplicate=2`（服务端覆盖）+ 上传完成后按旧 `fileID` 幂等删除兜底；实施前在 `/test` 实测确认语义 |
| 2 | 目标云端目录不存在时 | 一期不自动建目录，提示先手工创建；二期可加「自动创建目录」 |
| 3 | `{drama}` / `{season}` / `{episode}` 变量 | 建议一期实现常见命名（`SxxExx`、`第xx集`）；复杂命名后置 |
| 4 | 上传后是否删除本地源文件 | 一期不做（默认保留），后续作为任务级选项 |
| 5 | 重名大小写判定 | 以 123 云盘实测为准，文档后续补充结论 |

## 13. 文档与交付要求

- 本计划文档单独提交（`docs:`，纯文档不递增版本）。
- 实施完成后同步：`README.md`（特性概览 + 文档导航）、`manual/用户手册.md`（新增上传管理章节）、`docs/rules/backend.md` / `frontend.md`（新增目录与页面）、`CHANGELOG.md`（4.3.0，MINOR）。
- 测试约定见 §8；`/test` 目录约束必须写入手册的联调说明。
