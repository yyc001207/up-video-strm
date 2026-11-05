# 自动化任务模块（模块 C）设计与实现计划

> 状态：**待评审**（本文档只描述设计，评审通过后再实施代码）
>
> 关联文档：[上传管理模块计划](upload-module-plan.md) · [前端规范](../rules/frontend.md) · [后端规范](../rules/backend.md)

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

## 2. 固定执行链路

一次「自动化运行（run）」= 一轮完整链路：

```
本轮开始：轻量变更探测（仅 stat：路径 / 大小 / 修改时间，与上一轮指纹比对）
   ↓ 有变更？
   否 ──→ 本轮跳过（不创建 B 执行、不记 run），等待下一轮
   ↓ 是
触发 B 上传执行（冲突策略固定「跳过」）
   ↓ 等待 B 执行终态（轮询）
B 成功？──否──→ 本轮失败 → 自动化任务异常终止
   ↓ 是
提交本轮变更指纹（仅 B 成功后写入）
收集「本次 B 执行新上传成功的文件」清单
   ↓
清单为空？──是──→ run.status = skipped（本轮无新增上传）→ 等待下一轮
   ↓ 否
OpenList 可见性校验（轮询，本次新上传文件必须全部可查询到）
   ↓ 超时/失败 ──→ 本轮失败 → 自动化任务异常终止
   ↓ 全部可见
触发 A 生成执行（等待终态）
   ↓
A 成功 → 本轮成功 → 记录 run → 进入下一轮
```

关键规则：

1. **轮次开始前必须做轻量变更探测**：只 `stat` 本地目录（路径、大小、修改时间），生成指纹并与上一轮指纹比对；无变化则本轮跳过（**不创建 B 执行、不记 run**），日志记「无本地变更，跳过本轮」。指纹只在 B 执行成功后提交（失败保持旧指纹，下一轮重试）。
2. **手动启动总是强制执行一轮**（跳过指纹判定），用于用户主动「立即上传/生成」或清理指纹后的补偿操作。
3. **校验范围只限本次 B 执行新上传的文件**：从 `upload_file_record` 中按 `execution_id` + `status='success'` 取 `remote_name` 集合，不查历史、不比对全目录。
4. **必须全部文件可见**才触发 A：任一文件在等待窗口内未出现 → 视为异常。
5. 自动化任务启动后**持续运行**，只有两种终止方式：用户手动停止、发生异常错误。
6. 模块 B/A 的失败、取消、超时都算「异常错误」，终止整个自动化任务（历史 run 记为失败，并记录原因）。
7. **绑定任务运行期串行化**：同一 A/B 任务允许被多个自动化任务绑定，但启动前必须确认该 A/B 任务没有正在执行中的实例（自动或手动触发）；若有则等待其结束（等待上限沿用 `wait_timeout_seconds`，超时算异常并终止本轮）。

## 3. 子模块功能

### 3.1 任务配置（`/automation/tasks`）

- 列表：名称搜索、分页、批量删除（沿用列表页 `list-page` 骨架）。
- 新建/编辑抽屉：
  - 任务名称；
  - 绑定**一个**模块 B 上传任务、**一个**模块 A 调度任务（下拉，仅可选未删除的任务；**同一 A/B 任务允许被多个自动化任务绑定**，运行期按 §2 规则 7 串行化）；
  - 模块 B 执行参数：并发数、重试次数（**冲突策略固定为「跳过」，不提供配置**）；
  - 模块 A 执行参数：增量更新、强制重新生成、仅更新 STRM；
  - OpenList 等待：轮询间隔（默认 15s）、超时（默认 600s）；
  - OpenList 校验目录：默认取所选 A 任务的「处理路径」，可手工覆盖（应对 123 云盘路径与 OpenList 挂载路径不一致）；
  - 循环间隔：上一轮结束后等待 N 秒再开始下一轮（默认 60s，0 表示立即；界面建议最小 10s）。
- 保存校验：B/A 任务必须存在且未被删除；A 任务所属服务器必须启用；保存不校验「唯一绑定」，重复绑定是允许的（运行期串行化按上方规则处理）。
- **不提供「试运行」参数**：自动化链路要求真实上传，`dry_run` 不在该模块开放（B 模块自身仍保留试运行能力）。
- 变更探测指纹随任务保存（`scan_fingerprint` / `scan_time`），任务配置页提供「清除变更指纹」操作（使下一轮强制上传）。

### 3.2 执行管理（`/automation/execution`）

- 顶部卡片式操作区：选择自动化任务（多选）→ 配置本次启动的 B/A 执行参数（默认取任务配置，仅并发数/重试次数与 A 的三项参数可临时覆盖）→ 启动。多选启动走 `POST /tasks/batch-start`，逐项返回结果（已运行中、绑定任务正被占用等情况以行内提示，不影响其它任务启动）。
- **手动启动总是强制执行一轮**（跳过变更指纹判定，见 §2 规则 2）。
- 运行中列表：任务名、绑定关系、状态（运行中/已停止/错误）、当前轮次、当前阶段（等待 B / 校验 OpenList / 等待 A / 轮次间隔）、开始时间、操作（详情/实时日志/停止）。
- 停止 = 取消当前进行中的 B/A 执行（复用各自 cancel 接口）+ 立即结束循环（含正在轮次间隔等待的情况）。

### 3.3 实时日志（`/automation/realtime`）

- 页面骨架沿用上传管理实时日志：说明文案 → 运行选择工具条（无运行中任务时显示「无运行中任务」）→ 进度摘要卡 → 日志工具条（级别/关键字/打开日志文件夹）→ LogViewer。
- 日志内容为**全链路**：自动化阶段日志（含时间戳、级别）+ 内嵌 A/B 状态简报：
  - 模块 B：执行 ID、状态、上传成功/跳过/失败数；
  - 模块 A：执行 ID、状态、视频/字幕进度；
  - 自动化本身：第 N 轮、当前阶段、已等待 OpenList 秒数、本轮新增文件数。
- 日志只写文件并经 WebSocket 实时推送，与 A/B 一致：每次 run 一个文件 `automation_logs/automation_run_{run_id}.log`。
- 无变更跳过轮（不建 run）不落日志文件，避免每 60s 产生小文件；仅在实时日志页展示一行「无本地变更，跳过本轮」。

### 3.4 任务历史（`/automation/history`）

- **只展示模块 C 自身的运行历史**（`automation_run`），不聚合 A/B 记录。
- 列表：任务名称/时间范围/状态（运行中/成功/失败/已取消/跳过 skipped）三项筛选 + 分页；行内展示轮次、状态、新增文件数、OpenList 校验耗时、B/A 执行 ID、开始/结束时间、失败原因。
- 详情：本轮各阶段日志时间线、缺失文件名清单、跳转对应 B/A 任务历史（需支持按执行 ID 过滤，见 §9 联动改动）。

## 4. 数据模型

### 4.1 新增表

**`automation_task`**（自动化任务）

| 列 | 类型 | 说明 |
|----|------|------|
| id | int PK | |
| name | varchar(128) | 任务名称 |
| upload_task_id | int FK upload_task | 绑定的模块 B 任务（**允许重复绑定**，运行期串行化） |
| openlist_task_id | int FK open_list_task | 绑定的模块 A 任务（**允许重复绑定**，运行期串行化） |
| upload_concurrency | int | 默认 2（冲突策略固定 skip，不落库） |
| upload_retry_times | int | 默认 3 |
| openlist_is_incremental | bool | 默认 true |
| openlist_is_force | bool | 默认 false |
| openlist_strm_only | bool | 默认 false |
| check_dir_override | varchar(512) NULL | OpenList 校验目录覆盖；空则取 A 任务 process_path |
| wait_interval_seconds | int | 默认 15 |
| wait_timeout_seconds | int | 默认 600（同时作为「等待绑定任务空闲」的超时上限） |
| interval_seconds | int | 轮次间隔，默认 60，0=立即 |
| scan_fingerprint | varchar(64) NULL | 本地目录变更指纹（路径/大小/修改时间聚合哈希），仅 B 成功后更新；手动启动忽略 |
| scan_time | datetime NULL | 指纹提交时间（北京时间） |
| is_enabled | bool | 默认 true（保留字段，v1 不参与执行判断） |
| created_time / updated_time | datetime | 北京时间 |

绑定关系：

- **允许同一 A/B 任务被多个自动化任务绑定**：不建唯一索引，保存时也不做重复校验。
- 运行期保证互斥：启动（或每轮开始）前检查绑定的 A/B 任务是否已有运行中执行（含手动触发），有则等待其结束（等待上限 `wait_timeout_seconds`，超时算异常并终止本轮）；同一自动化任务本身也只允许一个运行实例。
- 删除模块 A/B 任务前仍按原逻辑校验业务引用；被自动化任务绑定的 A/B 任务视为引用中，不允许直接删除。v1 采用「删除自动化任务不影响 A/B 任务」的只读引用语义，不改 A/B 删除逻辑；删除自动化任务时保留其历史 run。

**`automation_run`**（一轮链路运行记录 = 模块 C 的「执行历史」）

| 列 | 类型 | 说明 |
|----|------|------|
| id | int PK | |
| task_id | int FK automation_task | |
| task_name | varchar(128) | 冗余快照 |
| round_no | int | 第几轮 |
| status | enum | running / success / fail / cancelled / skipped（B 成功但本轮无新增上传） |
| phase | varchar(16) | waiting_upload / waiting_openlist_check / waiting_openlist_task / interval / done（done 为瞬时态，落库前即被终态覆盖） |
| upload_execution_id | int NULL | 本轮 B 执行 ID |
| openlist_execution_id | int NULL | 本轮 A 执行 ID |
| new_file_count | int | 本轮 B 新上传成功文件数 |
| checked_file_count | int | 已确认可见文件数 |
| wait_seconds | int | OpenList 等待耗时 |
| missed_files | JSON/text NULL | 超时缺失文件 |
| error_message | varchar(512) NULL | 失败原因 |
| started_time / finished_time / created_time | datetime | 北京时间 |

### 4.2 存量表新增「触发来源」标识

`open_list_execution`、`upload_execution` 各新增三列：

| 列 | 类型 | 说明 |
|----|------|------|
| trigger_source | varchar(16) NOT NULL default 'manual' | `manual` / `automation` |
| trigger_ref | varchar(64) NULL | 自动化触发时记录 `automation_run:{id}`，手动为空 |
| trigger_name | varchar(128) NULL | 自动化任务名称快照，用于 A/B 历史展示「由自动化任务『X』触发」 |

- 旧数据默认 `manual`；通过 `_ensure_openlist_trigger_columns()` / `_ensure_upload_trigger_columns()` 增量 ALTER（PRAGMA table_info 判断）迁移，不重建表。
- A/B 的创建/批量创建/启动 service 增加可选 `trigger_source`/`trigger_ref`/`trigger_name` 参数，默认 `manual`，对现有前端调用零影响。
- 模块 A/B 前端「任务历史」与「执行管理」增加「来源」列：手动显示「手动」，自动显示「由自动化任务『X』触发」（名称取 `trigger_name`），支持按来源筛选；自动化触发时在各自执行日志首行写入「由自动化任务「X」第 N 轮触发」。
- A/B 历史查询接口（`list_executions` 等）新增可选 `execution_id` 过滤参数，供自动化历史详情跳转对应执行记录（见 §9）。
- 历史表语义不变：A/B 历史仍只属于 A/B，模块 C 的 run 只存 ID 引用，不做外键耦合。

## 5. 后端实现方案

新增 `backend/app/business/automation/`：

| 文件 | 职责 |
|------|------|
| `schema.py` | 任务/运行/启动参数 Pydantic 模型 |
| `service.py` | 任务 CRUD（允许 A/B 任务重复绑定）、run 查询、启动/停止入口（启动前校验绑定任务空闲、防重复启动、批量启动） |
| `execution_engine.py` | 链路状态机：变更探测 → 创建并启动 B 执行 → 轮询 → 收集新文件 → OpenList 校验 → 启动 A 执行 → 轮询 → 记录 run → 下一轮 |
| `change_detector.py` | 轻量变更探测：stat 本地目录生成指纹、与 `scan_fingerprint` 比对、B 成功后提交指纹（手动启动跳过） |
| `execution_logger.py` | 每任务 Logger + 日志队列泵（复用上传模块 LogPump 模式），写文件 + WS 广播 |
| `registry.py` | `{task_id: asyncio.Task}` 运行实例表 + `TaskStatusManager` 取消键（`automation:{task_id}`） |

模型：`backend/app/core/models/automation/{task.py,run.py}`，并在 `app/core/models/__init__.py` 导出。

复用点（不重复实现）：

- B：`uploader.service.create_execution` + `start_execution`，或直接复用执行引擎 `run_upload` 的启动方式；取消用 `TaskStatusManager` 现有键 `str(execution_id)`；创建时固定 `conflict_policy="skip"`。
- A：`openlist.service.create_execution` + `start_execution`；**任务执行的取消键是 `str(task_id)`，只有目录执行（task_id=0）才用 `execution_id`**（以 `openlist/service.py:cancel_execution` 现有实现为准）。
- OpenList 校验：`OpenListAPI.list_files(path, refresh=True, per_page=0)`（A 模块已有客户端与重试）。
- WebSocket：`ws_manager.broadcast(task_key, frame)`，帧格式沿用 log/progress/status。
- 打开日志文件夹：扩展 `POST /api/desktop/open-log-dir` 的 `kind=automation`。

轮询实现：

- 变更探测：每轮开始同步 stat 扫描本地目录（只取路径 / 大小 / `mtime_ns`，排序后哈希，不读文件内容、不算 MD5）；与 `scan_fingerprint` 相同 → 本轮跳过（不建 B 执行、不记 run，日志一行）；B 成功后提交新指纹。手动启动忽略指纹。
- 绑定任务空闲检查：启动时与每轮创建 B 执行前，查询绑定的 A/B 任务是否存在 `status='running'` 的执行（含手动触发），有则进入「等待绑定任务空闲」阶段并轮询；等待超过 `wait_timeout_seconds` → 本轮失败并终止任务。
- B/A 执行状态：在 `automation` 模块内每 2s 查询 DB 的 `status` 字段（不依赖 WS）。
- OpenList 可见性：按 `wait_interval_seconds` 调 `list_files`，比对 `remote_name` 集合；记录每次缺失数量。
- B 成功但 `new_file_count == 0` → 本轮记 `status=skipped`，不进入 OpenList 校验与 A，直接进入下一轮。

进程生命周期：

- 运行实例只在当前进程内有效；应用退出 → 自动化任务停止。
- 启动时把上次未结束的 `automation_run(status=running)` 标记为 `fail`（「进程重启中断」），**不自动恢复**运行（避免无预期行为，UI 需提示）。
- 同一自动化任务只允许一个运行实例；重复启动返回 400。

## 6. OpenList 更新延迟等待机制

- 校验目录：默认 `OpenListTask.process_path`，可由 `check_dir_override` 覆盖。
- 等待策略：轮询 `list_files`（`per_page=0`、`refresh=True`），直到「本次新增文件名」全部出现。
- 超时：达到 `wait_timeout_seconds` 后终止本轮并终止自动化任务；`automation_run.missed_files` 写入缺失清单，任务历史可查。
- 不做「等待固定秒数后一次校验」：避免文件多、网盘慢时误判；轮询 + 全量比对更稳。
- 冲突策略固定为「跳过」：自动化只上传云端不存在的新文件，因此「同名文件内容更新」不属于自动化链路；如需覆盖，请在 B 模块手动执行覆盖策略。

## 7. API 设计（`/api/automation`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/tasks` | 任务列表（keyword/page/page_size） |
| POST | `/tasks` | 新建 |
| PUT | `/tasks/{id}` | 编辑 |
| DELETE | `/tasks/{id}` | 删除（运行中禁止删除） |
| POST | `/tasks/batch-delete` | 批量删除 |
| GET | `/tasks/{id}/bind-options` | 可选 B/A 任务与 A 任务处理路径（供前端展示校验目录） |
| POST | `/tasks/{id}/start` | 启动（body 可覆盖 B/A 执行参数；总是强制执行一轮） |
| POST | `/tasks/batch-start` | 批量启动（body: `ids` + 可选参数覆盖，逐项返回结果） |
| POST | `/tasks/{id}/stop` | 停止并取消当前 B/A 执行（轮次间隔中则直接结束循环） |
| POST | `/tasks/{id}/reset-fingerprint` | 清除变更指纹（下一轮强制执行） |
| GET | `/active` | 当前运行中的自动化任务及阶段（供执行管理/顶栏徽标） |
| GET | `/runs` | 运行历史（task_id/status/start/end/page） |
| GET | `/runs/{id}` | 运行详情（含缺失文件清单） |
| GET | `/runs/{id}/logs` | 读取日志文件（分页/尾部） |
| WS | `/ws/{task_id}` | 实时日志与状态帧 |
| GET | `/runs/{id}/report` | 下载本轮运行报告（可选，后续版本） |

## 8. 前端设计

```
frontend/src/views/automation/
├── TaskConfig.vue          任务配置（列表 + 编辑抽屉）
├── Execution.vue           执行管理（启动卡片 + 运行中列表）
├── RealtimeLog.vue         实时日志（全链路）
├── TaskHistory.vue         任务历史（仅模块 C）
└── components/
    └── AutomationStage.vue 阶段进度条（等待B→校验→等待A）
```

- 路由：`/automation` → `/automation/tasks`；`/automation/tasks|execution|realtime|history`。
- 侧栏：在「上传管理」之后新增「自动化任务」模块，最终顺序「全局配置 / 任务调度 / 上传管理 / 自动化任务」（已确认，不再评审）。
- 任务配置页：无冲突策略、无试运行字段；提供「清除变更指纹」按钮（调用 `reset-fingerprint`）。
- 执行管理页：支持多选批量启动（`batch-start`），逐项结果提示；运行中列表按 §3.2 字段展示。
- 运行状态聚合：`stores/running.ts` 增加 `automationCount` 与徽标 `automation-running`；顶栏胶囊总数 = 调度 + 上传 + 自动化；徽标点击分流：自动化 > 0 优先进入 `/automation/realtime`。
- 实时日志页：复用上传管理 RealtimeLog 的骨架与 `.toolbar` 原语；级别选择器文案与任务调度一致（全部级别/信息/警告/错误）。
- 列表页统一：`.list-page` 骨架、分页 20/50/100、卡片内滚动、北京时间 `YYYY-MM-DD HH:mm:ss`、按钮风格（primary/default/danger-plain）沿用既有规范。

## 9. 模块 A/B 的联动改动

- 数据库：两表加 `trigger_source` / `trigger_ref` / `trigger_name` 三列（见 §4.2）。
- service：create/batch/start 增加可选触发来源参数（含任务名称快照）；A/B 的 `list_executions` 增加可选 `execution_id` 过滤参数。
- 日志：自动化触发时在 B/A 执行日志首行写入「由自动化任务「X」第 N 轮触发」；不改动原有日志内容。
- 前端：两个「任务历史」与两个「执行管理」表格增加「来源」列（手动 / 由自动化任务『X』触发）与来源筛选；任务历史支持按 `execution_id` 过滤（供自动化 run 详情跳转）；不新增页面。
- 无其它行为变化：A/B 的 WebSocket、进度、取消、重跑逻辑保持原样。

## 10. 可行性结论

**可行，且与现有架构高度契合**，不需要引入新依赖：

- A/B 已经具备「创建执行 → 启动 → 状态查询 → 取消 → 历史记录 → 日志文件 + WS」的完整能力，模块 C 只做编排。
- OpenList 可见性校验可直接用现有 `OpenListAPI.list_files`（已带重试与 SSL 开关）。
- 「本次新上传文件」在 `upload_file_record` 中有精确来源（execution_id + status=success），不会与历史文件混淆。
- 主要不确定性是 OpenList 更新延迟，已用「可配置轮询 + 超时 + 缺失清单 + 异常终止」兜底。

风险与应对：

| 风险 | 应对 |
|------|------|
| OpenList 迟迟不刷新 | 可配置超时；超时终止并在历史中列出缺失文件；建议用户确认 123 云盘与 OpenList 挂载正常 |
| B 上传目录与 A 处理路径映射不一致 | `check_dir_override` 手工指定；保存时展示 A 任务处理路径供核对 |
| 自动化与手动操作冲突 | 启动/每轮前检测绑定 A/B 任务是否有运行中执行（含手动），有则等待其结束（超时算异常，见 §2 规则 7）；同一自动化任务单实例 |
| 同一 A/B 任务被多个自动化绑定 | 允许绑定但运行期串行化（等待绑定任务空闲）；顶栏/日志提示等待阶段 |
| 变更探测漏检（大小与修改时间未变的替换） | 指纹含路径 + 大小 + `mtime_ns`；提供「清除变更指纹」与手动启动强制一轮兜底；必要时在 B 模块手动重跑 |
| 每轮 stat 扫描开销 | 只做 stat（不读内容、不算 MD5），大目录可接受；如压力大可调大 `interval_seconds` |
| 长时间循环占资源 | 每轮复用 A/B 各自的并发信号量；轮次间隔可配置；单任务单实例 |
| 进程重启中断 | run 标记失败；不自动恢复，UI 明确提示 |
| 循环产生海量历史 | 无变更轮不记 run（只记一行日志）；每个 run 只记摘要（~1 行数字），不存文件级明细；历史分页/可加保留策略 |

## 11. 已确认需求与决策

**来自需求（m06952）**：三模块平级；固定链路 B→OpenList 校验→A；只校验本次新文件；全部文件可见才触发 A；四子模块；实时日志全链路；任务历史不跨模块聚合；A/B 历史新增触发来源标识。

**已确认决策（m06954 用户勾选）**：

| # | 决策 | 结论 |
|---|------|------|
| 1 | 循环节奏 | 上一轮 A 完成后等待 **60 秒**（`interval_seconds` 默认 60，可在任务配置中调整，0=立即） |
| 2 | 失败处理 | B 失败/取消、OpenList 校验超时、A 失败**任一发生即立即终止整个自动化任务**；历史 run 记录原因，需用户处理后手动重新启动 |
| 3 | 重启恢复 | 程序重启后**不自动恢复**运行中的自动化任务；启动时把未结束 run 标记为失败（「进程重启中断」），等待用户手动启动 |
| 4 | 批量启动 | 执行管理页支持多选批量启动：`POST /tasks/batch-start`，逐项返回结果（m07084 确认） |
| 5 | 绑定关系 | **同一 A/B 任务允许被多个自动化任务绑定**（不建唯一索引）；运行期串行化——启动/每轮前等待绑定任务当前执行结束（超时终止）；删除自动化任务不影响 A/B 任务（m07084 修订，替代原「一对一」约束） |
| 6 | 模块顺序 | 自动化任务排在侧栏「上传管理」之后：全局配置 / 任务调度 / 上传管理 / 自动化任务 |
| 7 | 轮次变更探测 | 每轮先做轻量 stat 指纹比对；无变化则跳过本轮（不建 B 执行、不记 run）；手动启动忽略指纹强制一轮（m07084 选择方案 B） |
| 8 | 冲突策略 | 自动化链路固定「跳过」策略，不提供覆盖/追加后缀与试运行参数（m07084 确认） |
| 9 | 空上传轮 | B 成功但无新增上传文件 → run.status = `skipped`，不进入 OpenList 校验与 A（m07084 确认） |
| 10 | 来源展示 | A/B 历史与执行管理的「来源」列显示「由自动化任务『X』触发」，存 `trigger_name` 任务名快照（m07084 确认） |

## 12. 实施阶段（评审通过后）

| 阶段 | 内容 | 产出 |
|------|------|------|
| ① | 数据模型（`automation_task` 含 `scan_fingerprint`/`scan_time`，`automation_run` 含 `skipped`；A/B 三列触发来源迁移）+ A/B service 透传（含 `execution_id` 过滤）+ A/B 前端来源列与提示 | 可看到手动/自动来源差异 |
| ② | 自动化任务配置 CRUD + `reset-fingerprint` + `TaskConfig.vue` | 能配置绑定、参数与指纹重置 |
| ③ | 执行引擎（变更探测 → B → 校验 → A 状态机、串行化等待、取消、异常、skipped、WS）+ `Execution.vue`（批量启动）+ `RealtimeLog.vue` | 可端到端自动跑一轮 |
| ④ | `TaskHistory.vue` + 导航/运行聚合徽标 + 文档 + CHANGELOG | 完整交付 |

- 版本：MINOR（新增模块，`4.11.0 → 4.12.0`，实施完成时递增并记录 CHANGELOG）。
- 测试：runner 状态机单测（mock A/B service 与 OpenList API，覆盖变更探测跳过、B 失败、无新增 → skipped、校验超时、A 失败、手动停止、绑定任务等待/超时）、触发来源透传单测、`batch-start` 逐项结果单测、API 路由 smoke；不真实调用 123 云盘与 OpenList（用 MockTransport）。
