# 自动化任务模块（模块 C）设计与实现计划

> 状态：**待第二轮评审**（已按[第一轮评审意见](automation-module-plan-review.md)修订 P0 六项、P1 十二项、P2 十三项；本文只描述设计，评审通过后再实施代码）
>
> 关联文档：[上传管理模块计划](upload-module-plan.md) · [第一轮评审意见](automation-module-plan-review.md) · [前端规范](../rules/frontend.md) · [后端规范](../rules/backend.md)

## 1. 背景与定位

自动化任务模块（下称「模块 C」）用于把「上传到 123 云盘 → 等待 OpenList 可见 → 生成 STRM」串成全自动链路，解决目前必须人工先跑上传、等 OpenList 刷新、再手动执行任务调度的问题。

三个业务模块**完全平级、架构层级一致**：

| 模块 | 职责 | 路由前缀 |
|------|------|----------|
| 模块 A：任务调度 | OpenList → STRM 生成 | `/schedule/*`、数据 `open_list_*` |
| 模块 B：上传管理 | 本地 → 123 云盘上传 | `/upload/*`、数据 `upload_*` |
| 模块 C：自动化任务 | 编排 A/B，持续循环执行 | `/automation/*`、数据 `automation_*` |

设计约束：

- 模块 C **不产生业务产物**，不复制 A/B 的文件记录、不聚合 A/B 的历史。
- 模块 C 只是「调度触发方」：B 任务和 A 任务实例全部走各自模块原有的 service / 执行引擎 / 历史表。
- 模块 C 自身有独立的任务配置、执行状态、实时日志与任务历史（只记录「一轮链路」的编排结果）。

### 1.1 成功指标

| 指标 | 口径 | 目标 |
|------|------|------|
| 无人值守稳定性 | 连续运行不出现「僵尸阻塞 / 永久停摆」 | ≥ 7 天 |
| 链路成功率 | 新增文件 → STRM 生成端到端成功（排除用户配置错误） | ≥ 99% |
| 失败补偿 | A 失败后下一轮自动重新触发 A 直到成功 | 100%（致命错误除外） |
| 静默轮成本 | 无本地变更轮不创建 B 执行、不写 run、不落日志文件 | 100% |
| 可观测性 | 每次 run 有终态、日志、失败原因；任务异常终止有主动通知 | 100% |

### 1.2 范围外（不做）

- 不处理「同名文件内容更新/覆盖」：自动化只上传云端不存在的新文件；需要覆盖请在 B 模块手动执行。
- 不聚合 A/B 历史，不复制文件明细。
- 不做多机/分布式调度（单进程本地应用）。
- 不改 A 的 STRM 生成逻辑；不改 B 的上传算法（仅前置修复见 §9）。
- 不做复杂重试编排（瞬时故障终止后人工继续；连续失败自动暂停为后续增强）。

## 2. 固定执行链路（可恢复状态机）

一次「自动化运行（run）」= 一轮完整链路：

```text
每轮（检测周期开始）
  F = 本地视频文件指纹（路径 + 大小 + mtime_ns，范围与 B 扫描一致：视频格式、跳过隐藏/系统文件）
  F == task.scan_fingerprint（上次完整成功的指纹）且非手动 → 跳过（不建 run，仅 WS 一行）
   ↓ 有变更或手动启动
建 run（phase=waiting_idle，round_no = 本任务上一轮 + 1）
  获取绑定 B/A 任务的 FIFO 锁（等待超过 idle_wait_timeout → run fail）
  创建并启动 B（conflict_policy=skip）
  phase=waiting_upload → 等 B 终态
B 无进展（success+skipped==0）或致命错误 → run fail（不提交指纹，下一轮重试）
   ↓ 有进展（允许部分文件失败 → partial）
新文件 = 本次 B 执行 status='success' 的文件相对路径集合
   ↓ 新文件非空？
   是 → OpenList 递归校验（仅这些文件，按相对路径）→ 缺失/超时 → run fail（不提交指纹）
   否 → 跳过校验（变更已在云端或 B 全部跳过）
   ↓ phase=waiting_openlist_task
启动 A（openlist_mode）→ 等终态（stage_timeout 兜底）
   ↓
A 成功 → 提交指纹 F → run success（本轮 B 有失败文件则 status=partial）
A 失败/取消 → run fail，不提交指纹（下一轮自动补偿）
```

关键规则：

1. **指纹语义 = 上次完整成功**：仅当「B 有进展且 A 成功」时提交；任一步失败不提交，下一轮自动补偿。`
2. **手动启动强制一轮**（跳过指纹判定）；**本轮无新增上传时仍执行 A**（保证 A 失败可补偿、首次配置时云端已有文件也能生成 STRM）。
3. **校验范围只限本次 B 执行新上传的文件**：从 `upload_file_record` 按 `execution_id` + `status='success'` 取相对路径集合；新文件为空时跳过校验直接 A。
4. **必须全部文件可见**才触发 A：任一文件在等待窗口内未出现 → 本轮失败（记录缺失清单）。
5. **失败分级**：
   - 致命（终止本轮并停任务）：任务/目录不存在、凭据失效、云端目录不可读、B 完全无进展（`success+skipped==0`）、校验目录不可访问。
   - 可继续（partial）：部分文件失败但 `success+skipped>0`；OpenList 只校验成功文件，继续 A；run 最终记为 `partial`，失败文件在 run 详情列出。
6. **持续运行**：只有两种终止方式——用户手动停止、致命错误；瞬时故障（网络抖动等）也按致命处理并**主动通知**，用户修复后手动继续（连续失败自动暂停为后续增强）。
7. **绑定唯一 + 运行期串行化**：同一 A/B 任务**只能被一个自动化任务绑定**（数据库部分唯一索引 + 应用层校验，冲突返回 400 并提示占用任务名）；运行期仍按 `(kind, id)` 的 **FIFO 锁**在「检查空闲 + 创建执行 + 启动」内互斥，防止 check-then-act 及与手动执行的竞争，C 的停止只取消本轮自己创建的执行。
8. **无变更轮**：不建 run、不落日志文件，仅在实时日志页推一行「无本地变更，跳过本轮」（回放不可见）。
9. **停止语义**：只取消 `trigger_ref == automation_run:{本轮 id}` 的 B/A 执行；等待空闲/OpenList 等待/轮次间隔阶段可立即打断；先进入 `stopping`，等 B/A 终态（或 `stage_timeout`）后 run 记 `cancelled`，补日志结束行与 WS 终帧。

## 3. 子模块功能

### 3.1 任务配置（`/automation/tasks`）

- 列表：名称搜索、分页（10/20/50，默认 20）、批量删除（沿用列表页 `list-page` 骨架）。
- 新建/编辑抽屉：
  - 任务名称；
  - 绑定**一个**模块 B 上传任务、**一个**模块 A 调度任务（下拉，仅可选未删除的任务）；**同一 A/B 任务只能被一个自动化任务绑定**，保存时校验，冲突返回 400 并提示占用任务名；
  - 模块 B 执行参数：并发数（1-8，默认 2）、重试次数（0-10，默认 3）；冲突策略固定 `skip`，不提供配置；
  - 模块 A 执行参数：`openlist_mode` 单选（`incremental` 增量 / `full` 全量 / `strm_only` 仅 STRM），替代原三个布尔；
  - **OpenList 校验目录 `check_dir`（必填）**：B 的云端目录在 OpenList 中的对应路径；默认按 `openlist_remote_prefix`（可选映射，见 §6）推导，提供「检测目录映射」按钮；
  - 超时：`wait_interval_seconds`（5-120，默认 15）、`openlist_wait_timeout`（60-3600，默认 600）、`idle_wait_timeout`（60-3600，默认 600）、`stage_timeout`（60-7200，默认 3600）；
  - 循环间隔：`interval_seconds`（0-3600，默认 60，0=立即；界面建议最小 10s）；
  - 变更指纹只读展示（`scan_time`）＋「重新扫描并补齐 STRM」按钮（`reset-fingerprint`），文案不写「强制上传」。
- 保存校验：B/A 任务必须存在且未删除；同一 A/B 任务未被其它自动化任务绑定（编辑时排除自身）；A 任务所属服务器必须启用；`check_dir` 非空；调用 OpenList 检测 `check_dir` 可访问（不可达时警告但允许保存，运行期启动前再校验一次）。
- **不提供试运行参数**：自动化链路要求真实上传；B 模块自身保留试运行能力。
- **运行中限制编辑**：任务运行中，编辑抽屉只读（绑定/参数/`check_dir`/指纹均不可改）；停止后可改。

### 3.2 执行管理（`/automation/execution`）

- 顶部卡片式操作区：选择自动化任务（多选）→ 配置本次启动参数（仅并发数/重试次数与 A 模式可临时覆盖）→ 启动；多选启动走 `POST /tasks/batch-start`，逐项返回结果（已运行中、绑定任务排队等以行内提示，不影响其它任务启动）。
- **手动启动总是强制执行一轮**（跳过指纹；无新增上传也执行 A）。
- 运行中列表：任务名、绑定关系、状态（运行中/停止中/已停止/错误）、当前轮次、当前阶段（等待空闲/等待 B/校验 OpenList/等待 A/轮次间隔）、排队位次（FIFO）、开始时间、操作（详情/实时日志/停止）。
- 停止 = 只取消本轮自有 B/A 执行 + 打断等待 + 写 `cancelled` 终态；正在「等待空闲」时只退出等待，不取消任何执行。
- 失败任务行提供「重新启动」（重新执行一次 `start`，跳过指纹）。

### 3.3 实时日志（`/automation/realtime`）

- 页面骨架沿用上传管理实时日志：说明文案 → 运行选择工具条（无运行中任务时显示「无运行中任务」）→ 进度摘要卡 → 日志工具条（级别/关键字/打开日志文件夹）→ LogViewer。
- 日志内容为**全链路**：自动化阶段日志（北京时间、级别）+ 内嵌 A/B 状态简报：
  - 模块 B：执行 ID、状态、上传成功/跳过/失败数；
  - 模块 A：执行 ID、状态、视频/字幕进度；
  - 自动化本身：第 N 轮、当前阶段、OpenList 已等待秒数、新增文件数、排队位次。
- 日志只写文件并经 WebSocket 实时推送：每次 run 一个 `automation_logs/automation_run_{run_id}.log`；run 表存 `log_path`。
- 无变更跳过轮不落日志文件，仅推 WS 一行「无本地变更，跳过本轮」。
- 终止通知：任务异常终止/停止时推送 `status` 终帧（含 `error_code`）；桌面版额外弹托盘气泡，网页版顶栏显示红点（见 §8）。

### 3.4 任务历史（`/automation/history`）

- **只展示模块 C 自身的运行历史**（`automation_run`），不聚合 A/B 记录。
- 列表：任务名称/时间范围/状态（运行中/成功/部分完成/失败/已取消）三项筛选 + 分页；行内展示轮次、状态、新增文件数、OpenList 校验耗时、B/A 执行 ID、开始/结束时间、失败原因（`error_code` + message）。
- 详情：本轮各阶段日志时间线、缺失文件清单、跳转对应 B/A 任务历史（携带 `task_id` + `execution_id` 高亮对应行；复用现有详情接口，不新增过滤 API）。
- 保留策略：run 保留 **最近 90 天**（每任务最多 1000 条）；日志文件保留 90 天（最多 200 个/任务）。清理在任务启动时与进程启动时执行。

## 4. 数据模型

### 4.1 新增表

**`automation_task`**

| 列 | 类型 | 说明 |
|----|------|------|
| id | int PK | |
| name | varchar(128) | 任务名称 |
| upload_task_id | int FK upload_task | 绑定的模块 B 任务（`is_deleted=0` 部分唯一索引） |
| openlist_task_id | int FK open_list_task | 绑定的模块 A 任务（`is_deleted=0` 部分唯一索引） |
| upload_concurrency | int | 默认 2（范围 1-8） |
| upload_retry_times | int | 默认 3（范围 0-10） |
| openlist_mode | varchar(16) | `incremental` / `full` / `strm_only`，默认 incremental |
| check_dir | varchar(512) | OpenList 校验目录（必填，映射 B 的 remote_dir） |
| wait_interval_seconds | int | 默认 15（5-120） |
| openlist_wait_timeout | int | 默认 600（60-3600） |
| idle_wait_timeout | int | 默认 600（60-3600） |
| stage_timeout | int | 默认 3600（60-7200）：等待 B/A 终态上限 |
| interval_seconds | int | 轮次间隔，默认 60（0-3600） |
| scan_fingerprint | varchar(64) NULL | 上次**完整成功**指纹（视频文件路径/大小/mtime_ns 聚合哈希） |
| scan_time | datetime NULL | 指纹提交时间（北京时间） |
| is_deleted | bool | 逻辑删除，默认 false（删除后保留 run） |
| created_time / updated_time | datetime | 北京时间 |

**`automation_run`**（一轮链路的执行历史）

| 列 | 类型 | 说明 |
|----|------|------|
| id | int PK | |
| task_id | int FK automation_task | |
| task_name | varchar(128) | 冗余快照 |
| round_no | int | 第几轮（= 建 run 的轮次，本任务递增；无变更跳过不占号） |
| status | enum | running / success / partial / fail / cancelled / stopping |
| phase | varchar(32) | waiting_idle / waiting_upload / waiting_openlist_check / waiting_openlist_task / interval |
| upload_execution_id | int NULL | 本轮 B 执行 ID（含触发来源校验用） |
| openlist_execution_id | int NULL | 本轮 A 执行 ID |
| new_file_count | int | 本轮 B 新上传成功文件数（为 0 时 UI 显示「已同步」） |
| checked_file_count | int | 已确认可见文件数 |
| skipped_file_count | int | 本轮 B 上报的跳过文件数 |
| wait_seconds | int | OpenList 校验等待耗时 |
| idle_wait_seconds | int | 等待绑定任务空闲耗时 |
| missed_files | text NULL | 超时缺失文件（按相对路径，JSON 数组） |
| error_code | varchar(32) NULL | 失败分类（见 §10 异常清单） |
| error_message | varchar(512) NULL | 失败原因 |
| log_path | varchar(1024) NULL | 本次 run 日志文件 |
| started_time / finished_time / created_time | datetime | 北京时间 |

索引：`(task_id, started_time)`、`(status)`。

### 4.2 存量表新增「触发来源」标识

`open_list_execution`、`upload_execution` 各新增三列：

| 列 | 类型 | 说明 |
|----|------|------|
| trigger_source | varchar(16) NOT NULL default 'manual' | `manual` / `automation`，加索引 |
| trigger_ref | varchar(64) NULL | 自动化触发时记录 `automation_run:{id}`，手动为空 |
| trigger_name | varchar(128) NULL | 自动化任务名称快照，用于展示「由自动化任务『X』触发」 |

- 旧数据默认 `manual`；通过 `_ensure_openlist_trigger_columns()` / `_ensure_upload_trigger_columns()` 增量 ALTER（PRAGMA table_info 判断）迁移，不重建表。
- A/B 的创建/批量创建/启动 service 增加可选 `trigger_source`/`trigger_ref`/`trigger_name` 参数，默认 `manual`，对现有前端调用零影响。
- **A 的 `started_time` 改为在 `start_execution` 写入**（当前创建即写，无法区分「已创建未启动」，见 §9 前置改动）。
- 模块 A/B 前端「任务历史」与「执行管理」增加「来源」列：手动显示「手动」，自动显示「由自动化任务『X』触发」；历史页按「最近一次执行」的来源展示，并支持按来源筛选。
- 历史语义不变：A/B 历史仍只属于 A/B，C 的 run 只存 ID 引用，不做外键耦合。

## 5. 后端实现方案

新增 `backend/app/business/automation/`：

| 文件 | 职责 |
|------|------|
| `schema.py` | 任务/运行/启动参数 Pydantic 模型 |
| `service.py` | 任务 CRUD（软删、绑定唯一校验）、run 查询与保留清理、启动/停止/批量启动入口、check_dir 检测 |
| `registry.py` | 运行实例表 `{task_id: asyncio.Task}`、按 `(kind,id)` 的 FIFO 锁、停止事件 `asyncio.Event` |
| `execution_engine.py` | 可恢复状态机：指纹判定 → FIFO 锁 → B → 校验 → A → 记录 run → 下一轮；`stopping` 收尾 |
| `change_detector.py` | 视频文件 stat 指纹（范围复用 B 的扩展名与跳过规则）、比对与提交 |
| `adapters.py` | 封装 A/B 的执行创建、启动、状态、取消、活跃检查，避免 C 直接依赖 A/B 表结构 |
| `execution_logger.py` | 每 run Logger + 日志队列泵（复用上传模块 LogPump 模式），写文件 + WS 广播 |

模型：`backend/app/core/models/automation/{task.py, run.py}`，并在 `app/core/models/__init__.py` 导出。

复用点：

- B：`uploader.service.create_execution`（`conflict_policy="skip"`）+ `start_execution`；取消键 `str(execution_id)`。
- A：`openlist.service.create_execution` + `start_execution`；**取消键改为 `str(execution_id)`**（§9 前置改动，替代当前的任务执行 `task_id` 键）。
- OpenList：`OpenListAPI.list_files(path, refresh=..., per_page=...)` + 递归遍历子目录。
- WebSocket：`ws_manager.broadcast(key, frame)`，key 使用 `automation:{task_id}`（字符串键，需扩展 manager 类型，见 §9）。
- 桌面：`POST /api/desktop/open-log-dir` 扩展 `kind=automation`。

轮询与超时：

- 空闲检查：先查 A/B **进程内活跃执行注册表**（§9），再查 DB 兜底（`status='running'` 且 `started_time` 在 `stage_timeout` 窗口内）；陈旧 running 视为不存在。
- B/A 终态：每 2s 查询 DB `status`（经 adapters 封装），超过 `stage_timeout` → 致命失败。
- OpenList 可见性：见 §6。

进程生命周期：

- 运行实例只在当前进程内有效；应用退出 → 自动化任务停止。
- **启动时统一清理**：`main.py` lifespan 在 `init_db()` 后，把 `open_list_execution` / `upload_execution` / `automation_run` 中 `status='running'`（A/B 另有 `stopping`）置 `fail`，`error_message='进程重启中断'`（§9 前置改动）；不自动恢复运行，UI 提示用户手动重启任务。
- 同一自动化任务只允许一个运行实例；重复启动返回 400。
- 保留清理：进程启动时与任务启动时，按 §3.4 保留策略删除过期 run 与日志文件。

## 6. OpenList 更新延迟等待机制

- **校验目录**：`automation_task.check_dir` 必填，语义为「B 的 `remote_dir` 在 OpenList 挂载下的路径」；不默认取 A 的 `process_path`（A 通常配置父目录并递归处理，直接列父目录会看不到文件）。可选全局映射 `OPENLIST_REMOTE_PREFIX`（如 `/media`）用于推导默认值，仍以显式 `check_dir` 为准。
- **目录映射检测**：任务配置页「检测目录映射」按钮调用 `POST /tasks/{id}/check-dir`（或新建前用 `GET /bind-options` 返回的候选）：用 OpenList 实际 `list_files` 验证 `check_dir` 存在且可列出，并抽样展示 B `remote_dir` 下文件在 OpenList 的对应位置；保存时执行一次检测（不可达则警告+允许保存，运行前必检）。
- **递归校验**：从 `check_dir` 递归遍历（深度上限 5、目录数上限 500），按「相对 `check_dir` 的路径」比对本次新文件；B 上传为平铺文件时等价于单层，但保留递归以兼容多级结构。
- **等待策略**：轮询 `list_files`，直到本次新增文件全部出现。首次 `refresh=True`，其后 `refresh=False` + 指数退避（15s → 30s → 60s 封顶）+ 随机抖动（±20%）；同一进程内多个自动化同时轮询时串行化，避免 OpenList 限流。
- **超时**：达到 `openlist_wait_timeout` → 本轮失败、终止任务；`missed_files` 写入缺失的相对路径清单，任务历史可查。
- **冲突策略固定「跳过」**：自动化只上传云端不存在的新文件；「同名文件内容更新」不属于自动化链路，如需覆盖请在 B 模块手动执行。

## 7. API 设计（`/api/automation`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/tasks` | 任务列表（keyword/page/page_size） |
| GET | `/tasks/{id}` | 任务详情（编辑抽屉回填） |
| POST | `/tasks` | 新建 |
| PUT | `/tasks/{id}` | 编辑（运行中禁止修改绑定/参数/check_dir） |
| DELETE | `/tasks/{id}` | 软删除（运行中禁止删除） |
| POST | `/tasks/batch-delete` | 批量软删除 |
| GET | `/bind-options?task_id=` | 可选 B/A 任务、A 处理路径、B remote_dir 及推导的 check_dir（新建时可不传 task_id） |
| POST | `/tasks/{id}/check-dir` | 检测校验目录映射（body 可临时传 check_dir） |
| POST | `/tasks/{id}/start` | 启动（body 可覆盖并发/重试/A 模式；总是强制一轮） |
| POST | `/tasks/batch-start` | 批量启动（`ids` + 可选参数覆盖，逐项返回结果） |
| POST | `/tasks/{id}/stop` | 停止并取消本轮自有 B/A 执行；返回 `stopping` |
| POST | `/tasks/{id}/reset-fingerprint` | 重新扫描并补齐 STRM（清指纹，下一轮强制执行） |
| GET | `/active` | 运行中的自动化任务：`task_id/run_id/log_path/phase/queue_pos/started_time` |
| GET | `/runs` | 运行历史（task_id/status/start/end/page） |
| GET | `/runs/{id}` | 运行详情（含缺失文件、error_code、log_path） |
| GET | `/runs/{id}/logs` | 读取日志文件（分页/尾部） |
| WS | `/ws/{task_id}` | 实时日志与状态帧（log/progress/status） |

说明：**不提供** `/runs/{id}/report`（本期不做）；**不新增** `execution_id` 过滤 API（C 历史跳转 B/A 历史时携带 `task_id` + `execution_id`，前端加载后高亮对应行，详情数据走现有 `get_execution_detail`）。

## 8. 前端设计

```text
frontend/src/views/automation/
├── TaskConfig.vue          任务配置（列表 + 编辑抽屉 + 检测目录映射）
├── Execution.vue           执行管理（批量启动卡片 + 运行中列表）
├── RealtimeLog.vue         实时日志（全链路）
├── TaskHistory.vue         任务历史（仅模块 C）
└── components/
    └── AutomationStage.vue 阶段与排队位次展示
```

- 路由：`/automation` → `/automation/tasks`；`/automation/tasks|execution|realtime|history`；侧栏顺序「全局配置 / 任务调度 / 上传管理 / 自动化任务」。
- 新增 `frontend/src/api/automation.ts`、`frontend/src/types/automation.ts`。
- 实时日志：复用上传管理 RealtimeLog 骨架与 `.toolbar` 原语；级别选项与任务调度一致（全部级别/信息/警告/错误）；WS 使用 `utils/ws.ts` 新增的 `connectAutomationWs`，module 联合类型扩展 `automation`。
- 顶栏运行指示：**不把自动化计入现有「运行中」胶囊总数**（自动化是常驻循环，否则胶囊永远显示运行中）；改为独立指示器「自动化 N」，点击进 `/automation/realtime`；侧栏「实时日志」徽标同样使用 `automation-running`。现有胶囊/分流逻辑保持不变。
- 列表页统一：`.list-page` 骨架、分页 `10/20/50`（默认 20）、卡片内滚动、北京时间 `YYYY-MM-DD HH:mm:ss`、按钮风格沿用既有规范。
- 终止通知：顶栏红点 + 任务历史异常标记；桌面版额外弹托盘气泡（由后端在 run 终止时调用 pystray 通知）。
- `api/desktop.ts` 的 `openLogDir` 类型扩展 `automation`。

## 9. 模块 A/B 的联动与前置改动（实施前必须完成）

> 以下改动超出「C 只编排」的本意，但缺一不可；第一轮评审 P0-2/P0-3/P0-4/P1-7/P1-9 依赖这些前置项。

**⓿-1 启动清理残留 running（P0-2）**
`backend/app/main.py` lifespan：`init_db()` 之后把 `open_list_execution`、`upload_execution`、`automation_run` 的 `status='running'`（以及 `stopping`）置 `fail`，`error_message='进程重启中断'`；同时清空 A/B 进程内活跃注册表。单进程本地应用下这样做是安全且必要的。

**⓿-2 A 取消键改为 `execution_id`（P0-3）**
`openlist/service.py:start_execution` 为 A 执行传 `cancel_key=str(execution.id)`（原任务执行使用 `str(task_id)`，会误杀同任务其它执行）；`execution_engine.run_generation` 的取消检查同步使用该键。这是 A 模块的行为修复，需补回归用例。

**⓿-3 A/B 进程内活跃执行注册表（P0-2）**
A/B 执行引擎模块维护 `ACTIVE_EXECUTIONS: dict[int, int]`（`execution_id → task_id`，运行开始注册、`finally` 注销）并提供 `is_task_active(task_id)` / `is_execution_active(execution_id)`；C 的空闲检查优先查注册表，DB 只作兜底与陈旧判定。

**⓿-4 A 的 `started_time` 改在 `start_execution` 写入（P0-2）**
创建执行时不再写 `started_time`，避免「已创建未启动」被误判为运行中。

**⓿-5 A/B 删除前检查自动化引用（P1-7）**
`automation_task.is_deleted` 软删除；A/B 删除（B 物理删除、A 软删除）前检查是否存在未删除的 `automation_task` 引用，有则 400 返回占用任务名（提示先删除自动化任务）。

**⓿-6 `AUTOMATION_LOG_DIR` 配置与 open-log-dir 扩展（P1-9）**
`core/settings.py` 新增 `automation_log_dir`（默认 `./automation_logs`，冻结态在数据目录下）、`.env.example` 条目、启动时创建目录；`api/desktop.py` 的 `kind` 增加 `automation`；前端 `desktopApi.openLogDir` 类型同步。

**⓿-7 WebSocket 支持字符串键（P2/§6.5）**
`websocket/manager.py` 的连接键类型从 `Dict[int, ...]` 扩展为 `Dict[str, ...]`（或键序列化为字符串），`utils/ws.ts` 的 module 联合类型增加 `automation`，避免与整数 execution_id 冲突。

**⓿-8 A/B 触发来源三列迁移与来源展示（§4.2）**
三列增量迁移 + service 透传 + A/B 历史/执行管理来源列与筛选 + trigger_source 索引；`trigger_name` 用于「由自动化任务『X』触发」。

**⓿-9 清理历史残留（P2-11）**
删除未入库的 `backend/app/business/autoflow/__pycache__/`、`backend/app/api/__pycache__/autoflow*.pyc`；`.gitignore` 补 `backend/upload_logs/`、`backend/automation_logs/`。

**⓿ 失败分级与 A 模式参数映射**
C 调用 A 时：`openlist_mode=incremental` → `is_incremental=True,is_force=False,strm_only=False`；`full` → `is_force=True`；`strm_only` → `strm_only=True`；A 侧需确认 `is_incremental` 实际生效（P1-6 提到现有 `start_execution` 未透传，需同步修复并补测试）。

**A/B 其它行为不变**：WebSocket、进度、重跑逻辑保持原样（取消键与 started_time 除外）。

## 10. 异常处理清单、非功能需求与回滚

### 10.1 异常处理清单

| 场景 | 判定 | run 结果 | 处理 |
|------|------|----------|------|
| B 任务/本地目录不存在 | 致命 | fail（`B_TASK_INVALID`） | 终止任务，通知 || B 凭据/123 云盘不可达 | 致命 | fail（`B_CLOUD_ERROR`） | 终止任务，通知 |
| B 部分文件失败 | 可继续 | partial | 继续 A，失败文件列在 run 详情 |
| B 完全无进展（success+skipped=0） | 致命 | fail（`B_NO_PROGRESS`） | 终止任务，不提交指纹 |
| OpenList 校验目录不可访问 | 致命 | fail（`CHECK_DIR_INVALID`） | 终止任务，提示改 check_dir |
| OpenList 等待超时 | 致命 | fail（`OPENLIST_TIMEOUT`） | 记录 missed_files，终止，不提交指纹 |
| A 执行失败/取消 | 致命 | fail（`A_FAILED`） | 不提交指纹，下一轮自动补偿（但任务已停，需手动继续） |
| 进程重启 | — | 残留 running/stopping → fail | 启动清理；不自动恢复 |
| 用户停止 | — | cancelled | 取消本轮自有执行，写结束日志 |
| 无本地变更 | 跳过 | 不建 run | 仅 WS 一行，不落日志 |

### 10.2 非功能需求

- 单进程运行；轮询开销：每轮 stat（不含 MD5）、B/A 终态 2s 查询、OpenList 退避轮询。
- 并发：A 全局信号量默认 1、B 默认 2，长任务会排队；C 用 FIFO 锁 + `idle_wait_timeout` 体现排队位次。
- 日志：每 run 一个文件，保留 90 天/200 个；run 保留 90 天/1000 条。
- 时间：全系统北京时间 `YYYY-MM-DD HH:mm:ss`。
- 安全：123/OpenList 凭据不落日志；自动化日志不含 token。

### 10.3 回滚方案

- 功能级关闭：移除前端「自动化任务」模块入口与路由、停止挂载 `/api/automation` 路由即可；不迁移、不删除 A/B 三列（默认 `manual`，无副作用）。
- 数据级：`automation_task`/`automation_run` 保留（软删），A/B 触发来源列为可空/默认值，可直接忽略。
- 若需彻底移除：删除两张 C 表与 `automation_logs` 目录；A/B 三列可保留（无读取方）。

### 10.4 术语表

| 术语 | 含义 |
|------|------|
| run | 一轮完整链路（C 的执行历史记录） |
| round_no | 建 run 的轮次编号（无变更跳过不占号） |
| phase | run 内部阶段：waiting_idle / waiting_upload / waiting_openlist_check / waiting_openlist_task / interval |
| 指纹 | 视频文件（路径+大小+mtime_ns）聚合哈希，用于判断本地是否有变更 |
| 上次完整成功 | B 有进展且 A 成功的那一轮；指纹只在此时提交 |
| check_dir | B 的云端目录在 OpenList 中的对应路径（必填） |
| idle_wait | 等待绑定 A/B 任务空闲的时间 |
| trigger_source | A/B 执行记录的来源（manual / automation） |

## 11. 测试与验收

### 11.1 自动化测试

- 后端单测（mock A/B adapters 与 OpenList API，假时钟替换 sleep，不发真实请求）：
  - 状态机主链路：新文件 → 校验 → A 成功 → success + 指纹提交；A 失败 → 不提交指纹；下一轮无新增仍执行 A（补偿）；首次配置云端已有文件 → skipped 校验但执行 A。
  - 变更探测：无变更不建 run；检测范围与 B 的扩展名/跳过规则一致；手动启动忽略指纹。
  - 失败分级：B 无进展 → fail；B 部分失败 → partial 继续 A；OpenList 超时 → fail 不提交指纹；check_dir 无效 → fail。
  - 绑定唯一：第二个自动化任务保存绑定同一 A/B 任务 → 400 并提示占用任务名（编辑自身不误报）；并发/串行化：自动化启动时若绑定任务已有手动运行中执行 → 等待空闲/超时失败；FIFO 锁保证检查+创建+启动不可被 check-then-act；停止仅取消自己创建的执行。
  - 停止时机：等待空闲/OpenList 等待/轮次间隔三种时机停止都能立即结束，run=cancelled 且有结束日志与 WS 终帧。
  - 重启：启动清理把残留 running/stopping 置 fail。
  - 来源：创建 A/B 执行带 trigger_source/ref/name；trigger_source 索引存在。
  - 保留清理：过期 run 与日志被删除。
- 前端：`npm run type-check`、`npm run build`；分页/筛选/高亮交互手工冒烟。
- API smoke：路由注册与权限（本地单用户无需鉴权）。

### 11.2 验收标准（GWT）

- [ ] 本地新增 1 个云端不存在的视频 → B 上传 1 个、OpenList 校验通过、A 成功、run=success、指纹更新。
- [ ] A 执行失败 → 下一轮**无新增文件**也能再次触发 A，直到成功（自动补偿）。
- [ ] 首次配置且文件早已在云端 → B 全部 skip，仍执行 A 并生成 STRM。
- [ ] 进程在 B 或 A 阶段重启 → 残留 running 全部标 fail；自动化不自动恢复；手动启动可继续。
- [ ] 同一 A 任务已绑定一个自动化任务 → 再保存第二个绑定同一 A 任务被拒绝（400 提示占用任务名）；自动化启动与手动执行并发 → 不出现重复创建，按空闲等待/超时处理。
- [ ] A 的 `process_path` 为父目录、B 上传到子目录 → 校验能按相对路径正确找到文件。
- [ ] 单个文件无法解析集数 → 本轮 partial，其余文件继续进入 A，自动化不终止。
- [ ] 本地无任何变更 → 不建 run，仅实时日志一行「无本地变更，跳过本轮」。
- [ ] 停止发生在「等待绑定任务空闲」「OpenList 等待」「轮次间隔」三种时机 → 都能立即结束，run 记 cancelled 且有结束日志。
- [ ] A/B 历史能按「手动 / 自动化任务 X」区分；自动化 run 详情能跳转到对应 A/B 执行记录并高亮。

## 12. 已确认决策与评审修订记录

### 12.1 已确认决策

| # | 决策 | 结论 |
|---|------|------|
| 1 | 循环节奏 | 上一轮结束后等待 60 秒（`interval_seconds` 默认 60，可配，0=立即） |
| 2 | 失败处理 | **分级**：致命错误立即终止整个自动化任务；文件级失败为 partial 继续（第一轮评审 P0-5 修订） |
| 3 | 重启恢复 | 不自动恢复；启动清理残留 running 为 fail（「进程重启中断」），用户手动启动 |
| 4 | 批量启动 | 执行管理多选批量启动：`POST /tasks/batch-start`，逐项返回结果 |
| 5 | 绑定关系 | **同一 A/B 任务只能被一个自动化任务绑定**（`is_deleted=0` 部分唯一索引 + 应用层校验，冲突 400 提示占用任务名）；运行期 FIFO 锁仍保留，防止 check-then-act 及与手动执行竞争（用户确认，不采用评审的「允许多绑定+串行化」） |
| 6 | 模块顺序 | 自动化任务在侧栏「上传管理」之后：全局配置 / 任务调度 / 上传管理 / 自动化任务 |
| 7 | 轮次变更探测 | 每轮先 stat 指纹比对；无变化跳过（不建 B 执行/不记 run）；指纹 = 上次完整成功；手动启动忽略指纹 |
| 8 | 冲突策略 | 固定「跳过」，不提供覆盖/追加后缀与试运行参数 |
| 9 | 校验目录 | `check_dir` 必填，默认按 B `remote_dir` 的 OpenList 映射推导，提供「检测目录映射」按钮（评审 D-4 采纳 B+C） |
| 10 | 来源展示 | A/B 历史/执行管理来源列展示「由自动化任务『X』触发」（`trigger_name` 快照） |
| 11 | 保留策略 | run 保留 90 天/每任务 1000 条；日志 90 天/200 个；A/B 历史默认提示自动化来源可筛选（评审 D-5 采纳 B） |
| 12 | 手动启动语义 | 跳过指纹强制一轮；无新增上传时仍执行 A（评审 D-3 采纳 B） |
| 13 | 提示：原「skipped 状态」 | P0-1 修订后「无新增但执行 A」，不再保留独立 skipped 终态：`new_file_count=0` 在 UI 显示「已同步」，run 终态为 success/partial（见 §10.1） |

### 12.2 第一轮评审修订摘要

| 评审项 | 修订 |
|--------|------|
| P0-1 失败不可恢复 | 指纹改为 A 成功后提交；无新增也执行 A；reset 文案改「重新扫描并补齐 STRM」；手动启动强制一轮 |
| P0-2 僵尸 running | 启动统一清理三表 running/stopping；A/B 活跃注册表 + DB 陈旧判定；A `started_time` 移到 start_execution |
| P0-3 串行化竞态/取消误杀 | `(kind,id)` FIFO 锁内完成检查+创建+启动；A 取消键改 `execution_id`；C 停止只取消自有执行 |
| 绑定关系（评审 D-2） | 不采用评审的「允许多绑定+串行化」；按用户确认改为**唯一绑定**（部分唯一索引 + 应用层校验），FIFO 锁仅用于防竞态 |
| P0-4 校验目录不匹配 | `check_dir` 必填 + 映射检测按钮；递归相对路径校验；首次 refresh、后续退避 + 抖动 |
| P0-5 单文件失败即终止 | 失败分级：致命终止 / partial 继续；`partial` 状态；B 有进展判定 |
| P0-6 停止语义 | `stopping` 中间态；只取消自有执行；打断等待；finally 写终态/日志/WS |
| P1 | 超时三拆、指纹范围对齐 B、轮询退避、保留策略、顶栏独立指示器、数据模型修正（phase 32、去 is_enabled、openlist_mode）、删除语义、API 补缺、日志目录闭环、运行中只读、绑定唯一校验、失败通知 |
| P2 | 分页 10/20/50、版本不写死、API 风格、无变更日志只推 WS、round_no/skipped 定义、来源列口径、索引、测试与文档范围、必备章节、清理 pycache、终止通知 |

## 13. 实施阶段（第二轮评审通过后）

| 阶段 | 内容 | 前置关系 |
|------|------|----------|
| ⓿ 前置 | 启动清理残留 running；A 取消键改 `execution_id`；A `started_time` 迁移；A/B 活跃注册表；A/B 删除引用检查；`AUTOMATION_LOG_DIR`；WS 字符串键；A/B 三列迁移与来源展示；pycache 清理 | 必须先于 C 引擎 |
| ① | 数据模型（`automation_task`/`automation_run` 修正版）+ 索引 + 保留清理 | ⓿ 完成 |
| ② | C 任务 CRUD + `bind-options` + check_dir 检测 + `TaskConfig.vue` | ① 完成 |
| ③ | 引擎（可恢复状态机、FIFO 锁、阶段超时、partial、停止收尾、WS、通知）+ `Execution.vue` + `RealtimeLog.vue` | ② 完成 |
| ④ | `TaskHistory.vue` + 导航/运行指示 + 文档同步 + 测试补齐 + CHANGELOG | ③ 完成 |

- 版本：实施时按 `bump_version.py minor` 递增一次（不写死目标版本号）。
- 文档同步范围：`README.md`、`manual/用户手册.md`、`docs/rules/backend.md`、`docs/rules/frontend.md`、`.env.example`、`CHANGELOG.md`。

## 14. 风险登记册

| 编号 | 风险 | 概率 | 影响 | 等级 | 应对 |
|------|------|------|------|------|------|
| RK-01 | A 失败后无法补偿 | 1（已修） | 5 | 5 低 | P0-1：指纹 A 成功后提交 + 无新增也执行 A |
| RK-02 | 重启残留 running 阻塞 | 1（已修） | 5 | 5 低 | P0-2：启动清理 + 活跃注册表 |
| RK-03 | 校验目录/递归不匹配 | 2 | 5 | 10 中 | P0-4：check_dir 必填 + 检测按钮 + 递归相对路径 |
| RK-04 | 单文件失败导致永久停摆 | 1（已修） | 4 | 4 低 | P0-5：失败分级 + partial |
| RK-05 | 同一 A/B 任务被自动化与手动执行并发启动 | 2 | 4 | 8 中 | 绑定唯一（部分唯一索引 + 400 校验）+ P0-3 FIFO 锁 + 空闲等待 + A/B 信号量排队 |
| RK-06 | OpenList 轮询限流/拖慢 | 3 | 3 | 9 中 | 退避 + 抖动 + 串行化轮询 |
| RK-07 | 历史/日志增长淹没数据 | 2 | 3 | 6 中 | 保留策略 + A/B 来源筛选 |
| RK-08 | 用户误以为会同步文件更新 | 4 | 3 | 12 中 | 文档与界面写明「只处理新增」 |
| RK-09 | 瞬时故障导致任务停摆未被发现 | 3 | 4 | 12 中 | 终止通知（托盘气泡/顶栏红点）+ 失败原因分类 + 一键重新启动 |

---

本方案为产品设计参考，具体实施请结合公司合规与法务要求确认。
