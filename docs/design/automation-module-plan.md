# 自动化任务模块（模块 C）设计与实现计划

> 状态：**待第三轮短评审**（已按[第二轮评审意见](automation-module-plan-review-round2.md)对 5 项阻断 P0 与 P1/P2 项做针对性修订；本文只描述设计，评审通过后再实施代码）
>
> 关联文档：[上传管理模块计划](upload-module-plan.md) · [第一轮评审意见](automation-module-plan-review.md) · [第二轮评审意见](automation-module-plan-review-round2.md) · [前端规范](../rules/frontend.md) · [后端规范](../rules/backend.md)

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

### 1.1 成功指标（可测量，均来自 `automation_run` 与日志）

| 指标 | 口径 | 目标 |
|------|------|------|
| 无人值守稳定性 | 连续运行天数内无「致命停摆」（fatal 终止）且无僵尸 running | **≥ 14 天** |
| 补偿成功率 | A/OpenList/网络类轮次失败后 **3 轮内** 成功（清空 pending）的比例 | ≥ 95% |
| 链路成功率 | 本地新增文件 → STRM 生成端到端成功（排除用户配置错误） | ≥ 99% |
| 静默轮成本 | 无本地变更轮不创建 B 执行、不写 run、不落日志文件 | 100% |
| 可观测性 | 每次 run 有终态、日志、失败原因；任务异常终止有主动通知 | 100% |

统计方式：补偿成功率 = `run(status=success 且上一轮为 fail) / run(status=fail)`（同任务、3 轮窗口）；致命停摆 = `status=fail 且 error_code 属配置类` 的任务终止次数。

### 1.2 范围外（不做）

- 不处理「同名文件内容更新/覆盖」：自动化只上传云端不存在的新文件；需要覆盖请在 B 模块手动执行。
- 不聚合 A/B 历史，不复制文件明细。
- 不做多机/分布式调度（单进程本地应用）。
- 不改 A 的 STRM 生成逻辑；不改 B 的上传算法（仅前置修复见 §9）。
- 不恢复进程重启前的运行（重启后不自动续航，见 §2 规则）。

## 2. 固定执行链路（可恢复状态机）

一次「自动化运行（run）」= 一轮完整链路；轮次间隔（interval）属于任务运行时状态，**不属于 run**。

```text
每轮（任务运行循环开始）
  if task.pending_files 非空:                 # 补偿 / 续校验路径
       跳过指纹判定，直接进入「建 run → OpenList 校验 pending」
  else:
       F = 本地视频指纹（路径+大小+mtime_ns；范围与 B 扫描一致：视频格式、跳过隐藏/系统文件）
       if 本地无视频: 提交空集指纹；WS「本轮无视频文件，跳过」；等 interval → 下一轮
       if F == task.scan_fingerprint: WS「无本地变更，跳过本轮」；等 interval → 下一轮
       建 run（round_no = last_round_no + 1）
  等待绑定 A/B 空闲（共享启动闸门 is_task_active；超时 idle_wait_timeout → 轮次失败）
  若 pending 为空：创建并启动 B（conflict_policy=skip）；否则跳过 B（直接校验 pending）
  phase=waiting_upload → B 终态：
       file_total==0 且 failed==0 → run success（empty，new_file_count=0）+ 提交指纹 + 不执行 A → 结束
       success+skipped>0 → new_files = 本次 status='success' 的 remote_name 集合
                          pending = pending ∪ new_files
       success+skipped==0 且 failed>0 → 轮次失败（需 error_code 区分扫描错误→致命）
  phase=waiting_openlist_check（pending 为空时跳过）：OpenList 精确校验 pending
       全部可见 → phase=waiting_openlist_task → 启动 A（openlist_mode）
       超时 / API 5xx → 轮次失败（pending 保留；退避后下一轮重新校验 → 补偿）
  A 终态：
       成功 → 清空 pending + 提交指纹 → run success（B 有失败文件时 status=partial）
       失败/取消 → 轮次失败（pending 保留；退避后下一轮重新校验并重跑 A）
  轮次失败 → consecutive_failures++，等退避后下一轮；连续 3 次 → 终止任务（致命，通知）
  A/B 配置类错误（任务/目录不存在、凭据失效、check_dir 不可访问）→ 立即终止（致命，不重试）
```

关键规则：

1. **指纹语义 = 上次完整成功**：仅当「pending 清空且 A 成功」时提交；空轮提交空集指纹（避免每轮重复扫描空目录）。
2. **手动启动强制一轮**（跳过指纹判定）；**本轮无新增上传时仍执行 A**（保证 A 失败可补偿、首次配置时云端已有文件也能生成 STRM）。
3. **pending 决定了可见性校验**：本轮/历史轮 B 成功上传的文件进入 `automation_task.pending_files`（JSON），只有「OpenList 全部可见 + A 成功」后才清空。因此补偿路径（A 失败、OpenList 超时、校验阶段进程重启）都会重新校验，不会因「本轮新文件为 0」而跳过校验。
4. **绑定唯一 + 共享启动闸门**：同一 A/B 任务只能被一个自动化任务绑定（部分唯一索引 + 应用层校验）；A/B 的 `start_execution` 增加**共享按任务启动闸门**（任务已有活跃执行 → 400「任务正在执行」），手动与自动化都受同一约束，自动化侧用 `idle_wait_timeout` 等待空闲并浮出提示。
5. **失败分级**：见 §10.1 矩阵——**轮次失败**（A/OpenList/网络/B 全失败/空闲超时）退避后继续，连续 3 次才终止；**配置错误**立即终止。
6. **持续运行**：只有用户停止、连续 3 次轮次失败、配置类致命错误三种终止方式；终止窗口内主动通知，用户修复后可手动启动（跳过指纹）。
7. **停止语义**：只取消本轮 `trigger_ref == automation_run:{id}` 的 B/A 执行；等待空闲/OpenList 等待阶段可立即打断；先进入 `phase=stopping`，等 B/A 终态（或 `stage_timeout`）后 run 记 `cancelled`，补日志结束行与 WS 终帧。
8. **无变更轮**：不建 run、不落日志文件，仅实时日志页一行「无本地变更，跳过本轮」（回放不可见）。
9. **轮次间隔中停止**：只停循环，不产生 run 终态；`/active` 返回 `phase=interval` 与 `next_round_at`。

## 3. 子模块功能

### 3.1 任务配置（`/automation/tasks`）

- 列表：名称搜索、分页（10/20/50，默认 20）、批量删除（沿用列表页 `list-page` 骨架）。
- 新建/编辑抽屉：
  - 任务名称（**唯一**，与已有未删除任务重名 → 400）；
  - 绑定**一个**模块 B 上传任务、**一个**模块 A 调度任务（下拉，仅可选未删除且未被其它自动化任务绑定的任务；保存冲突 400 并提示占用任务名）；
  - 模块 B 执行参数：并发数（1-8，默认 2）、重试次数（0-10，默认 3）；冲突策略固定 `skip`；
  - 模块 A 执行参数：`openlist_mode` 单选（`incremental` 增量 / `full` 全量 / `strm_only` 仅 STRM），映射为 A 现有参数 `(is_force, strm_only)`（不承诺 `is_incremental` 透传）；
  - **OpenList 校验目录 `check_dir`（必填）** = B `remote_dir` 在 OpenList 中的**精确映射**（含全局 `openlist_remote_prefix` 时按前缀+后缀校验；不解析子目录、不递归）；
  - 超时：`wait_interval_seconds`（5-120，默认 15，作为退避基数）、`openlist_wait_timeout`（60-3600，默认 600）、`idle_wait_timeout`（60-3600，默认 600）、`stage_timeout`（60-7200，默认 3600）；
  - 循环间隔：`interval_seconds`（10-3600，默认 60；0 不支持，API/UI 双重最小 10）；
  - 指纹只读展示（`scan_time`）＋「重新扫描并补齐 STRM」按钮（`reset-fingerprint`）；
  - pending 只读展示（当前待校验文件数）＋「查看待校验文件」。
- 保存校验：B/A 任务存在且未删除、A 所属服务器启用、`check_dir` 非空且与 B `remote_dir` 映射一致（`openlist_remote_prefix + remote_dir == check_dir`，空前缀时直接相等）、名称唯一、绑定唯一；保存时调用 OpenList 检测 `check_dir` 可访问（不可达警告但允许保存）。
- **不提供试运行参数**；B 模块自身保留。
- **运行中限制编辑**：运行中编辑抽屉只读；停止后可改。

### 3.2 执行管理（`/automation/execution`）

- 顶部卡片式操作区：选择自动化任务（多选）→ 配置本次启动参数（并发数/重试次数/A 模式可临时覆盖）→ 启动；多选启动走 `POST /tasks/batch-start`，逐项返回结果（已在运行、绑定任务被手动执行占用等以行内提示，不影响其它任务启动）。
- **手动启动总是强制执行一轮**（跳过指纹；无新增上传也执行 A）。
- 运行中列表：任务名、绑定关系、状态（运行中/成功/部分完成/失败/已取消）、当前轮次、当前阶段（等待空闲/等待 B/校验 OpenList/等待 A/轮次间隔/停止中）、开始时间、操作（详情/实时日志/停止）。
- 停止 = 只取消本轮自有 B/A 执行 + 打断等待 + 写 `cancelled` 终态；「等待空闲」时只退出等待。
- **重试失败文件**：run 为 `partial` 时提供按钮——启动一次强制轮（跳过指纹），B 按 skip 策略重试失败项、已成功项跳过。
- 失败/终止任务行提供「重新启动」（跳过指纹）。

### 3.3 实时日志（`/automation/realtime`）

- 页面骨架沿用上传管理实时日志：说明文案 → 运行选择工具条（无运行中任务显示「无运行中任务」）→ 进度摘要卡（第 N 轮、阶段、OpenList 已等待秒数、待校验文件数、新增文件数、B/A 状态简报）→ 日志工具条（级别/关键字/打开日志文件夹）→ LogViewer。
- 日志内容为全链路：自动化阶段日志 + 内嵌 B/A 简报（执行 ID、状态、成功/跳过/失败数、A 视频/字幕进度）。
- 日志只写文件并经 WebSocket 推送：每次 run 一个 `automation_logs/automation_run_{run_id}.log`；run 表存 `log_path`；日志被保留清理后接口返回「日志已清理」，UI 占位。
- 无变更跳过轮不落日志文件，仅推 WS 一行。
- 终止通知：异常终止/连续失败终止 → 桌面版托盘气泡（模块级可注入通知器，线程安全）+ 网页版顶栏未读红点；用户主动停止不弹错误气泡。

### 3.4 任务历史（`/automation/history`）

- 只展示模块 C 自身运行历史（`automation_run`），不聚合 A/B。
- 列表：任务名称/时间范围/状态筛选 + 分页；行内：轮次、状态、阶段（含停止中）、新增文件数、待校验数、OpenList 等待耗时、B/A 执行 ID、开始/结束时间、错误码与原因（`error_message` 截断 500 字 + 省略号，完整原因在日志）。
- 详情：阶段时间线、缺失文件清单（最多展示 200 条，超出写日志）、跳转对应 B/A 任务历史（携带 `task_id` + `execution_id` 高亮对应行，复用现有详情接口）。
- 保留策略：run 保留最近 90 天且每任务最多 1000 条；日志保留 90 天且最多 200 个/任务；清理在进程启动、任务启动、每日定时任务三处执行。

## 4. 数据模型

### 4.1 新增表

**`automation_task`**

| 列 | 类型 | 说明 |
|----|------|------|
| id | int PK | |
| name | varchar(128) | 任务名称，未删除任务内唯一 |
| upload_task_id | int FK upload_task | 绑定的模块 B 任务 |
| openlist_task_id | int FK open_list_task | 绑定的模块 A 任务 |
| upload_concurrency | int | 默认 2（1-8） |
| upload_retry_times | int | 默认 3（0-10） |
| openlist_mode | varchar(16) | `incremental` / `full` / `strm_only`，默认 incremental |
| check_dir | varchar(512) | OpenList 校验目录（B `remote_dir` 的精确映射，必填） |
| wait_interval_seconds | int | 默认 15（5-120），退避基数 |
| openlist_wait_timeout | int | 默认 600（60-3600） |
| idle_wait_timeout | int | 默认 600（60-3600） |
| stage_timeout | int | 默认 3600（60-7200） |
| interval_seconds | int | 轮次间隔，默认 60（10-3600） |
| pending_files | text NULL | 待完成文件（JSON 数组，`remote_name` 列表；B 成功后写入，OpenList 验证 + A 成功后清空） |
| scan_fingerprint | varchar(64) NULL | 上次完整成功指纹 |
| scan_time | datetime NULL | 指纹提交时间（北京时间） |
| last_round_no | int | 最近一轮轮次号（避免保留清理后 round_no 重置） |
| consecutive_failures | int | 连续轮次失败次数（成功清零；达 3 终止任务） |
| is_deleted | bool | 逻辑删除，默认 false |
| created_time / updated_time | datetime | 北京时间 |

索引/约束：

- 绑定唯一：`upload_task_id`、`openlist_task_id` 在 `automation_task.is_deleted = 0` 上建 **SQLite 部分唯一索引**（`sqlite_where`），并发创建捕获 `IntegrityError` → 400 提示占用任务名；批量/交换绑定整体校验。
- 名称唯一：`name` 在 `is_deleted = 0` 上部分唯一索引。

**`automation_run`**（一轮链路的执行历史；生命周期 = 建 run → A 终态 / 停止 / 致命；interval 不属于 run）

| 列 | 类型 | 说明 |
|----|------|------|
| id | int PK | |
| task_id | int FK automation_task | |
| task_name | varchar(128) | 冗余快照 |
| round_no | int | 第几轮（建 run 递增） |
| status | enum | running / success / partial / fail / cancelled |
| phase | varchar(32) | waiting_idle / waiting_upload / waiting_openlist_check / waiting_openlist_task / interval / stopping |
| upload_execution_id | int NULL | 本轮 B 执行 ID（补偿轮可为空） |
| openlist_execution_id | int NULL | 本轮 A 执行 ID |
| new_file_count | int | 本轮 B 新上传成功文件数（0 时 UI 显示「已同步」/「本轮无文件」） |
| pending_file_count | int | 本轮结束后仍待校验文件数（0 表示已清空） |
| checked_file_count | int | 已确认可见文件数 |
| skipped_file_count | int | 本轮 B 上报的跳过文件数 |
| wait_seconds | int | OpenList 校验等待耗时 |
| idle_wait_seconds | int | 等待绑定任务空闲耗时 |
| missed_files | text NULL | 超时缺失文件（JSON 数组，最多 200 条，超出写日志） |
| error_code | varchar(32) NULL | 失败分类（见 §10.1） |
| error_message | varchar(512) NULL | 失败原因（截断 500 字 + 省略号） |
| log_path | varchar(1024) NULL | 日志文件路径 |
| started_time / finished_time / created_time | datetime | 北京时间 |

索引：`(task_id, started_time)`、`(status)`、`(error_code)`。

### 4.2 存量表新增列

`open_list_execution`、`upload_execution` 各新增：

| 列 | 类型 | 说明 |
|----|------|------|
| trigger_source | varchar(16) NOT NULL default 'manual' | `manual` / `automation`；建索引 |
| trigger_ref | varchar(64) NULL | 自动化触发时记 `automation_run:{id}` |
| trigger_name | varchar(128) NULL | 自动化任务名称快照，展示「由自动化任务『X』触发」 |
| error_code | varchar(32) NULL | 执行失败分类（C 据此区分 `B_CLOUD_ERROR` / `B_NO_PROGRESS` / `B_SCAN_ERROR` 等） |
| error_message | varchar(512) NULL | 失败原因摘要（截断） |

迁移：`_ensure_openlist_trigger_columns()` / `_ensure_upload_trigger_columns()` 用 `PRAGMA table_info` 判断后 `ALTER TABLE ADD COLUMN`，并在同一函数内 `CREATE INDEX IF NOT EXISTS idx_*_trigger_source`（SQLite 无「ADD INDEX」，不走 Base.metadata 变更）。

其他：

- A 的 `started_time` 改为在 `start_execution` 写入；历史排序与实时用时使用 `coalesce(started_time, created_time)`，未启动记录不再影响排序。
- A/B 的 service 增加可选 `trigger_source/trigger_ref/trigger_name` 参数（默认 manual），现有调用零影响。
- A/B 前端「任务历史」「执行管理」增加来源列（历史按最近一次执行口径），支持按来源筛选。

## 5. 后端实现方案

新增 `backend/app/business/automation/`：

| 文件 | 职责 |
|------|------|
| `schema.py` | 任务/运行/启动参数/批量启动 Pydantic 模型 |
| `service.py` | 任务 CRUD（软删、名称与绑定唯一校验、批量绑定整体校验）、run 查询与保留清理、启动/停止/批量启动/重试失败文件入口、check_dir 检测 |
| `registry.py` | 运行实例表 `{task_id: asyncio.Task}`、按 `(kind,id)` 的 FIFO 锁（**不维护排队位次**；唯一绑定后仅用于 C 内部启动互斥）、停止事件 `asyncio.Event` |
| `execution_engine.py` | 可恢复状态机：pending 优先 → 指纹 → 启动闸门 → B → 精确校验 → A → 提交/清除 → 轮次失败退避；`stopping` 收尾 |
| `change_detector.py` | 视频文件 stat 指纹（范围复用 B 扩展名与跳过规则）、比对与提交 |
| `adapters.py` | 封装 A/B 的执行创建、启动、状态（含 error_code）、取消、活跃检查（is_task_active/is_execution_active） |
| `notifier.py` | 终止通知：桌面版经模块级托盘通知器（线程安全投递）、网页版仅写 WS status 帧（前端红点/未读存储由前端维护） |
| `execution_logger.py` | 每 run Logger + 日志队列泵（写文件 + WS 广播） |

模型：`backend/app/core/models/automation/{task.py, run.py}`，在 `app/core/models/__init__.py` 导出。

复用点与行为：

- B：`uploader.service.create_execution(conflict_policy="skip")` + `start_execution`；取消键 `str(execution_id)`；B 执行记录的 `error_code/error_message` 由 B 引擎在失败时写入。
- A：`openlist.service.create_execution` + `start_execution`；**取消键改为 `str(execution_id)`**（§9 ⓿-2）；`openlist_mode` 映射 `(is_force, strm_only)`：incremental→(False,False)、full→(True,False)、strm_only→(False,True)。
- 启动闸门：A/B `start_execution` 在**入队前**检查并注册活跃执行（`is_task_active(task_id)` 为真 → 400「任务正在执行」），引擎 `finally` 注销；排队中的执行也算活跃。
- OpenList：`OpenListAPI.list_files(check_dir, refresh=...)`；只比对 `remote_name`（平铺，不递归）。
- WebSocket：`ws_manager.broadcast(key, frame)`，key 归一化为字符串（`automation:{task_id}`），manager 键类型放宽为 `int | str`，路由边界统一转 str。
- 桌面：`POST /api/desktop/open-log-dir` 扩展 `kind=automation`。

轮询、超时与生命周期：

- 空闲检查：先查 A/B 活跃注册表，再查 DB 兜底（`status='running'` 且 `started_time` 在 `stage_timeout` 窗口内）；每 2s 轮询，超过 `idle_wait_timeout` → 轮次失败 `IDLE_TIMEOUT`。
- B/A 终态：每 2s 查询；超过 `stage_timeout` → 先请求取消（A/B 各自取消接口），给 30s grace 期等终态，再记轮次失败 `STAGE_TIMEOUT`。
- OpenList 可见性：见 §6。
- 进程生命周期：运行实例仅进程内有效；应用退出 → 自动化停止。**启动清理**：lifespan 在 `init_db()` 后把 `open_list_execution` / `upload_execution` / `automation_run` 中 `status='running'` 置 `fail`，`error_message='进程重启中断'`（`automation_run` 另记 `PROCESS_RESTART`），清空 A/B 活跃注册表；不自动恢复，UI 提示手动启动。
- 同一自动化任务只允许一个运行实例；重复启动 400。
- 保留清理：进程启动 + 任务启动 + **每日定时后台任务**（lifespan 内 asyncio 任务，每 24h）按 §3.4 策略清理。

## 6. OpenList 更新延迟等待机制

- **校验目录 = 精确映射**：`check_dir` 必须等于 B `remote_dir` 在 OpenList 中的路径（含全局 `openlist_remote_prefix` 时按「前缀 + 后缀」规范化校验；不解析多级子目录）。不做递归校验：B 的上传记录只有 `local_path`/`remote_name`，云端目录结构平铺到 `remote_dir`，无法可靠推导子路径。
- **保存校验**：保存时校验 `check_dir` 与 B `remote_dir` 的映射一致性；调用 OpenList 检测目录存在且可列（不可达时警告但允许保存）。
- **启动前校验**：任务启动时再次检测 `check_dir`；不可访问 → 400 拒绝启动（不建 run、不产生无意义失败记录）。
- **检测目录映射接口**：`POST /tasks/check-dir`（新建时不传 task_id，body 带 `upload_task_id` + `check_dir`）返回规范化结果、目录样例文件（最多 20 个）与映射是否一致。
- **可见性校验**：`list_files(check_dir)` 拉取该目录文件集合（按 `remote_name` 比对 pending 中全部文件）；全部出现即通过。B 为平铺上传，等价单层比对。
- **等待策略**：首次 `refresh=True`，其后 `refresh=False`；退避以 `wait_interval_seconds` 为基数（base → 2×base → 4×base，封顶 60s）+ ±20% 抖动；同一进程内多个自动化轮询串行化，避免 OpenList 限流。
- **超时**：达到 `openlist_wait_timeout` → 轮次失败 `OPENLIST_TIMEOUT`，pending 保留、`missed_files` 记录（最多 200 条），下一轮自动重新校验。
- **冲突策略固定「跳过」**；同一文件内容更新不属自动化范围。

## 7. API 设计（`/api/automation`）

API 风格沿用本项目既有**动作式**（与 `/executions/start`、`/executions/cancel` 一致），不改成纯 REST；原因：执行类操作语义是「动作」而非资源增删改，动作式与现有前端调用风格统一。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/tasks` | 任务列表（keyword/page/page_size） |
| GET | `/tasks/{id}` | 任务详情（编辑回填，含 pending 数与 scan_time） |
| POST | `/tasks` | 新建（名称/绑定唯一校验） |
| PUT | `/tasks/{id}` | 编辑（运行中禁止改绑定/参数/check_dir） |
| DELETE | `/tasks/{id}` | 软删除（运行中禁止） |
| POST | `/tasks/batch-delete` | 批量软删除 |
| POST | `/tasks/check-dir` | 检测目录映射（新建可用；body: upload_task_id + check_dir + 可选 task_id） |
| GET | `/bind-options` | 可选 B/A 任务（**排除已被其它自动化绑定的任务**；返回 bound_by）与推导的 check_dir |
| POST | `/tasks/{id}/start` | 启动（body 可覆盖并发/重试/A 模式；强制一轮） |
| POST | `/tasks/batch-start` | 批量启动（逐项结果） |
| POST | `/tasks/{id}/stop` | 停止（返回 `stopping` phase；无 run 时可立即返回） |
| POST | `/tasks/{id}/reset-fingerprint` | 重新扫描并补齐 STRM（清指纹，下一轮强制） |
| POST | `/runs/{id}/retry-failed` | 重试失败文件（partial run；跳过指纹强制一轮） |
| GET | `/active` | 运行中任务：`task_id/run_id/log_path/phase/next_round_at/started_time`（无 queue_pos） |
| GET | `/runs` | 运行历史（task_id/status/start/end/page） |
| GET | `/runs/{id}` | 运行详情（缺失文件、错误码、log_path） |
| GET | `/runs/{id}/logs` | 日志读取（文件已清理 → 返回 `log_cleaned` 标记） |
| WS | `/ws/{task_id}` | 实时日志/状态帧 |

不提供 `/runs/{id}/report`；不新增 `execution_id` 过滤 API（跳转 B/A 历史用 `task_id` + `execution_id` 高亮）。

## 8. 前端设计

```text
frontend/src/views/automation/
├── TaskConfig.vue          任务配置（列表 + 编辑抽屉 + 检测目录映射）
├── Execution.vue           执行管理（批量启动卡片 + 运行中列表）
├── RealtimeLog.vue         实时日志（全链路）
├── TaskHistory.vue         任务历史（仅模块 C）
└── components/
    └── AutomationPhaseTag.vue  阶段/状态展示
```

- 路由：`/automation` → `/automation/tasks`；`/automation/tasks|execution|realtime|history`；侧栏顺序「全局配置 / 任务调度 / 上传管理 / 自动化任务」。
- 新增 `frontend/src/api/automation.ts`、`frontend/src/types/automation.ts`；`utils/ws.ts` module 联合类型加 `automation`。
- 实时日志复用上传管理骨架；级别选项与任务调度一致（全部级别/信息/警告/错误）。
- 顶栏运行指示：自动化常驻循环，**不计入现有运行胶囊**，用独立指示器「自动化 N」+ 侧栏徽标；点击进 `/automation/realtime`。
- 终止通知：顶栏未读红点（未读状态存 localStorage `up-video-strm-automation-unread`，进入实时日志/历史后清除）；桌面版托盘气泡由后端通知器触发。
- 列表页统一：`.list-page` 骨架、分页 10/20/50、卡片内滚动、北京时间 `YYYY-MM-DD HH:mm:ss`。
- `api/desktop.ts` 的 `openLogDir` 增加 `automation`；`schedule/TaskHistory.vue`、`RealtimeLog.vue` 的 A `started_time` 为空时改用 `created_time` 兜底（排序与用时展示）。

## 9. 模块 A/B 的联动与前置改动（实施前必须完成）

**⓿-1 启动清理残留 running**
lifespan `init_db()` 后把 `open_list_execution`、`upload_execution`、`automation_run` 的 `status='running'` 置 `fail`（error_message「进程重启中断」）；清空 A/B 活跃注册表。

**⓿-2 A 取消键改为 `execution_id`**
`openlist/service.py:start_execution` 传 `cancel_key=str(execution.id)`；引擎按该键检查取消；补回归用例。

**⓿-3 A/B 活跃执行注册表 + 共享启动闸门（R2-P0-4）**
A/B 引擎模块维护 `ACTIVE_EXECUTIONS: dict[int, int]`（执行开始**入队前**注册、`finally` 注销），暴露 `is_task_active(task_id)` / `is_execution_active(execution_id)`；`start_execution` 先检查，活跃则 400「任务正在执行」；手动与自动化同受约束。

**⓿-4 A `started_time` 迁移**
创建执行不写 `started_time`，`start_execution` 时写入；历史排序/列表用 `coalesce(started_time, created_time)`；实时日志用时缺失时用 `created_time`/当前时间兜底。

**⓿-5 A/B 执行错误字段（R2-P1-2）**
两张执行表新增 `error_code`/`error_message`，引擎失败时写入（截断 500）；adapters 读取用于失败分级。

**⓿-6 A/B 删除引用检查（R2-P1-10）**
覆盖单删/批删/服务器删除：存在未删除的 `automation_task` 引用时 400 提示占用任务名；服务器删除时若其 A 任务被自动化引用 → 阻止并说明；B 物理删除前必须检查。

**⓿-7 `AUTOMATION_LOG_DIR` 与 open-log-dir 扩展**
settings 新增 `automation_log_dir`（默认 `./automation_logs`）、`.env.example`、启动创建；`kind=automation`。

**⓿-8 WebSocket 键类型**
manager 键类型放宽 `int | str`，路由边界统一转 str；A/B 实时日志回归。

**⓿-9 A/B 触发来源三列 + 错误字段迁移 + 索引**
见 §4.2；`CREATE INDEX IF NOT EXISTS` 写进 `_ensure_*`。

**⓿-10 `OPENLIST_REMOTE_PREFIX`**
`open_list_config` 新增 `openlist_remote_prefix` varchar(256) default ''（A 全局配置页可编辑），仅用于 `check_dir` 推导与映射校验。

**⓿-11 托盘通知器重构（R2-P1-11）**
`desktop.py` 的托盘图标提升为模块级可注入通知器（线程安全投递 pystray notify）；仅异常终止通知，用户主动停止不弹错误气泡；网页版红点未读由前端维护。

**⓿-12 清理历史残留**
删除未入库的 `backend/app/business/autoflow/__pycache__/` 等；`.gitignore` 补 `backend/upload_logs/`、`backend/automation_logs/`。

**其它行为不变**：A/B 的 WebSocket、进度、重跑逻辑保持原样（取消键、started_time、启动闸门、错误字段除外）。

## 10. 异常处理清单、非功能需求与回滚

### 10.1 失败策略矩阵

| 场景 | 本轮结果 | 任务是否继续 | 指纹/pending | 通知/动作 |
|------|----------|--------------|--------------|-----------|
| A/B 任务或目录不存在、凭据失效、`check_dir` 不可访问 | fail（致命 `CONFIG_INVALID`/`CHECK_DIR_INVALID`） | 停止 | 不提交，pending 保留 | 通知 + 修复后手动启动 |
| 本地无视频（`file_total=0`、`failed=0`，pending 为空） | 不建 run（WS 一行）或 run success（empty） | 继续 | 提交空集指纹 | 不通知 |
| B 部分文件失败（`success+skipped>0`） | partial | 继续执行 A | 清空 pending + 提交指纹 + 失败文件列表 + 「重试失败文件」入口 | 非致命提示 |
| B 全部文件失败（`file_total>0`、`success+skipped=0`） | 轮次失败 `B_NO_PROGRESS` | 退避后继续，连续 3 次终止 | 不提交，pending 保留 | 第 3 次通知 |
| B 预扫描失败（`file_total=0`、`failed>0`） | 致命 `B_SCAN_ERROR` | 停止 | 不提交 | 通知 |
| OpenList 超时 / API 5xx | 轮次失败 `OPENLIST_TIMEOUT`/`OPENLIST_API_ERROR` | 退避后继续，3 次终止 | 不提交，pending 保留 | 第 3 次通知 |
| A 失败 / 取消（外部原因） | 轮次失败 `A_FAILED`/`A_CANCELLED` | 退避后继续，3 次终止 | 不提交，pending 保留 | 第 3 次通知 |
| 等待绑定任务空闲超时 | 轮次失败 `IDLE_TIMEOUT` | 退避后继续，3 次终止 | 不提交 | 第 3 次通知 |
| 等待 B/A 终态超时（已尝试取消 + 30s grace） | 轮次失败 `STAGE_TIMEOUT` | 退避后继续，3 次终止 | 不提交，pending 保留 | 第 3 次通知 |
| 连续 3 次轮次失败 | fail（终止） | 停止 | 不提交，pending 保留 | 通知 + 一键重新启动 |
| 用户停止 | cancelled | 停止 | 不提交 | 不通知（轻提示） |
| 进程重启 | 启动清理为 fail `PROCESS_RESTART` | 不恢复 | 保持 | 启动后提示 |
| 无本地变更 | 不建 run | 继续 | 保持 | 不通知 |
| 内部异常 | fail `INTERNAL_ERROR` | 停止 | 不提交 | 通知 |

错误码枚举：`CONFIG_INVALID`、`B_SCAN_ERROR`、`B_NO_PROGRESS`、`B_CLOUD_ERROR`、`CHECK_DIR_INVALID`、`OPENLIST_TIMEOUT`、`OPENLIST_API_ERROR`、`A_FAILED`、`A_CANCELLED`、`IDLE_TIMEOUT`、`STAGE_TIMEOUT`、`PROCESS_RESTART`、`INTERNAL_ERROR`、`BINDING_CONFLICT`（保存期）、`TASK_BUSY`（保存/启动期）。

### 10.2 非功能需求

- 单进程；轮询开销：每轮 stat（不算 MD5）、B/A 终态 2s、OpenList 按退避。
- 并发：A 全局信号量默认 1、B 默认 2；启动闸门 + FIFO 锁保证同一任务不并发。
- 日志：每 run 一个文件；保留 90 天/200 个；run 90 天/1000 条。
- 时间：全系统北京时间 `YYYY-MM-DD HH:mm:ss`。
- 安全：凭据不落日志。

### 10.3 回滚方案

- 功能级关闭：移除前端自动化入口/路由、停止挂载 `/api/automation` 路由。
- **A/B 前置改动（取消键、started_time、启动闸门、错误字段、触发来源列、remote_prefix）为向后兼容的修复/可空字段，回滚 C 时保留即可**：取消键与 started_time 属于缺陷修复；新增列为空值；启动闸门对既有调用只增加「同任务并发 400」保护。如确需撤销闸门，可单独移除检查而保留列。
- 数据级：两张 C 表软删保留；A/B 触发来源列与错误列可直接忽略；删除 `automation_logs` 目录。

### 10.4 术语表

| 术语 | 含义 |
|------|------|
| run | 一轮完整链路（C 的执行历史记录） |
| round_no | 建 run 的轮次编号（无变更跳过不占号；删除历史后由 `last_round_no` 续号） |
| phase | run 内部阶段（waiting_*/interval/stopping） |
| interval | 轮次间隔（任务运行时状态，不属于 run） |
| 指纹 | 视频文件（路径+大小+mtime_ns）聚合哈希 |
| 上次完整成功 | pending 清空且 A 成功的那一轮；指纹只在此时提交 |
| pending | 待完成文件集合（已上传但未经 OpenList 验证 + A 成功） |
| check_dir | B `remote_dir` 在 OpenList 的精确映射（必填） |
| 轮次失败 | 可恢复失败：退避后继续，连续 3 次终止 |
| 致命错误 | 配置/目录/凭据类错误：立即终止 |
| trigger_source | A/B 执行来源（manual / automation） |

## 11. 测试与验收

### 11.1 自动化测试

后端单测（mock adapters/OpenList/123，假时钟替换 sleep）：

- 状态机：新文件→校验→A 成功→success+pending 清空+指纹提交；A 失败→轮次失败（pending 保留）→下一轮无本地变更也重新校验并重跑 A（补偿）；连续 3 次→终止。
- 可见性：OpenList 超时后下一轮重新校验 pending（不因 new_file_count=0 跳过）；校验阶段进程重启后重启清理 + pending 仍触发校验。
- 空轮：本地无视频不建 run、提交空指纹；B 空目录返回 success 计数 0 → 不判失败；B 预扫描失败（failed>0 且 total=0）→ 致命。
- 失败分级：partial 提交指纹 + 重试失败文件接口；B 全失败 → 轮次失败；stage_timeout 先取消 + grace 后记失败；idle 超时。
- 启动闸门/并发：手动与自动化同时启动同一任务只允许一个（400）；唯一绑定 400；部分唯一索引并发创建 IntegrityError→400；批量/交换绑定校验。
- 停止时机：等待空闲、OpenList 等待、轮次间隔、A 执行中四种时机停止都正确收尾（interval 停止不产生 run 终态）。
- 保留清理：过期 run/日志被删；每日后台清理被触发；round_no 由 last_round_no 续号；日志清理后接口返回 `log_cleaned`。
- 迁移：A/B 新增三列 + 错误列 + 索引存在；A 未启动记录 started_time 为空且排序/用时兜底正常。
- WS：字符串键广播；A/B 实时日志回归。
- 通知：异常终止触发通知器、主动停止不触发（mock）。

前端：`npm run type-check`、`npm run build`；分页/筛选/高亮/重试失败文件手工冒烟。

### 11.2 验收标准（GWT）

- [ ] 本地新增 1 个云端不存在的视频 → B 上传、OpenList 校验通过、A 成功、pending 清空、指纹更新。
- [ ] A 失败 → 下一轮**无本地变更**也会重新校验 pending 并重跑 A（3 轮内补偿）；连续 3 次失败后终止并通知。
- [ ] OpenList 超时 → 下一轮自动重新校验同一批 pending 文件（不跳过校验）。
- [ ] 本地无视频 / 空目录 → 不终止、不产生失败 run；后续放入文件后正常触发。
- [ ] 首次配置且云端已有文件 → B 全部 skip、为 pending 为空时执行 A 生成 STRM。
- [ ] 进程在 B 或 A 阶段重启 → 残留 running 清理为 fail；手动启动后 pending 仍触发校验。
- [ ] 手动执行与自动化同时启动同一 A 任务 → 只允许一个（另一方 400/等待）。
- [ ] 同一 A 任务再被第二个自动化绑定 → 保存 400 提示占用任务名。
- [ ] `check_dir` 填成父目录或与 B `remote_dir` 不匹配 → 保存 400；启动前检测失败 → 400 不建 run。
- [ ] 停止发生在等待空闲/OpenList 等待/A 执行中/轮次间隔 → 正确收尾；interval 停止不产生 run 终态。
- [ ] partial run 点「重试失败文件」→ 已成功项跳过、失败项重试。
- [ ] A/B 历史能区分「手动 / 自动化任务 X」；自动化 run 详情可跳转 A/B 记录并高亮。

## 12. 已确认决策与评审修订记录

### 12.1 已确认决策

| # | 决策 | 结论 |
|---|------|------|
| 1 | 循环节奏 | 上一轮结束后等待 `interval_seconds`（默认 60，最小 10） |
| 2 | 失败处理 | **轮次失败**（A/OpenList/网络/B 全失败/空闲超时）退避重试，连续 3 次终止；**配置错误**立即终止（第二轮 R2-P0-1 修订） |
| 3 | 重启恢复 | 不自动恢复；启动清理残留 running 为 fail，用户手动启动 |
| 4 | 批量启动 | `POST /tasks/batch-start`，逐项返回结果 |
| 5 | 绑定关系 | **同一 A/B 任务只能被一个自动化任务绑定**（部分唯一索引 + 400 校验）；共享启动闸门防手动并发 |
| 6 | 模块顺序 | 全局配置 / 任务调度 / 上传管理 / 自动化任务 |
| 7 | 变更探测 | 每轮 stat 指纹；无变化跳过；指纹 = 上次完整成功；手动启动忽略指纹；空轮提交空指纹 |
| 8 | 冲突策略 | 固定「跳过」，无试运行参数 |
| 9 | 校验目录 | `check_dir` = B `remote_dir` 的精确映射（必填 + 映射校验 + 检测按钮），退避以 `wait_interval_seconds` 为基数 |
| 10 | 来源展示 | A/B 历史/执行管理来源列「由自动化任务『X』触发」，任务名唯一防歧义 |
| 11 | 保留策略 | run 90 天/1000 条；日志 90 天/200 个；启动 + 每日定时清理 |
| 12 | 手动启动语义 | 跳过指纹强制一轮；无新增上传仍执行 A |
| 13 | 原「skipped 状态」 | 不保留独立终态：`new_file_count=0` 显示「已同步/本轮无文件」；终态为 success/partial/fail/cancelled |
| 14 | pending 集合 | 引入持久化 `pending_files`（B 成功写入；OpenList 可见 + A 成功清空），补偿与超时路径必须重新校验（第二轮 R2-P0-2） |
| 15 | 启动闸门 | A/B `start_execution` 增加共享按任务活跃检查（入队前注册，400 拒绝），手动与自动化一致（第二轮 R2-P0-4） |
| 16 | 失败重试入口 | partial run 提供「重试失败文件」；连续失败终止后提供一键重新启动（第二轮 R2-P1-4） |

### 12.2 第一轮评审修订摘要

| 评审项 | 修订 |
|--------|------|
| P0-1 失败不可恢复 | 指纹 A 成功后提交；pending 机制保证补偿；无新增也执行 A；reset 文案修正 |
| P0-2 僵尸 running | 启动清理 + 活跃注册表 + started_time 迁移 |
| P0-3 串行化竞态/取消误杀 | 唯一绑定 + 共享启动闸门 + FIFO 锁 + A 取消键 execution_id |
| P0-4 校验目录不匹配 | `check_dir` 精确映射（去递归）+ 映射检测 + 启动前校验 |
| P0-5 单文件失败即终止 | 失败分级 + partial + 空轮处理 + 重试失败文件 |
| P0-6 停止语义 | phase=stopping + 只取消自有执行 + 可打断 + 终态收尾 |
| P1/P2 | 超时三拆、退避基数、保留定时、独立指示器、数据模型修正、删除语义、API 补缺、日志闭环、运行中只读、通知、分页、来源列、索引、文档 |

### 12.3 第二轮评审针对性修订

| 评审项 | 修订 |
|--------|------|
| R2-P0-1 补偿 vs 终止 | 失败分级改为「轮次失败（重试 3 次）」与「致命（配置类）」；指标改为 3 轮补偿成功率 ≥95% |
| R2-P0-2 补偿绕过校验 | 新增持久化 `pending_files`；每轮优先校验 pending；A 成功才清空并提交指纹 |
| R2-P0-3 空目录误判 | 空轮不建 run / 或不判失败；`file_total>0 && success+skipped=0` 才按轮次失败；预扫描错误依赖 error_code 判致命 |
| R2-P0-4 手动竞态 | A/B `start_execution` 共享启动闸门（入队前注册、400 拒绝）；FIFO 锁缩小为 C 内部；RK-05 重估 |
| R2-P0-5 相对路径无数据源 | `check_dir` 精确映射、按 `remote_name` 比对、去递归；保存/启动双重校验 |
| R2-P1-1 stage_timeout | 先取消 + 30s grace 再记失败 |
| R2-P1-2 错误原因 | A/B 执行表新增 error_code/error_message |
| R2-P1-3 is_incremental | 不承诺透传，`openlist_mode` 只映射 (is_force, strm_only) |
| R2-P1-6 run 生命周期 | interval 归任务运行时；stopping 为 phase；interval 停止不产生 run 终态 |
| R2-P1-7 remote_prefix | `open_list_config.openlist_remote_prefix` 字段；`check-dir` 支持新建 |
| R2-P1-8 started_time | `coalesce(started_time, created_time)` 排序/用时兜底 |
| R2-P1-9 唯一索引 | 建在 `automation_task.is_deleted=0`（sqlite_where）；IntegrityError→400 |
| R2-P1-10 删除检查 | 覆盖单删/批删/服务器删除 |
| R2-P1-11 通知 | 托盘通知器模块级可注入、线程安全；主动停止不通知 |
| R2-P1-12 queue_pos | 删除排队位次（asyncio.Lock 不暴露等待者），改展示 phase/next_round_at |
| R2-P1-13 退避基数 | 以 `wait_interval_seconds` 为基数（base/2×/4×，封顶 60）+ 抖动 |
| R2-P1-14 指标/错误码 | 指标可统计；错误码枚举补全；表格语法修正 |
| P2 | API 风格说明、stopping 进 phase、A/B 措辞、round_no 续号、日志清理 404、名称唯一、error_message 截断、索引迁移、回滚说明、missed 上限、interval 最小 10、测试补齐、WS 键回归 |

## 13. 实施阶段（第三轮短评审通过后）

| 阶段 | 内容 | 前置关系 |
|------|------|----------|
| ⓿ 前置 | 启动清理；A 取消键；started_time 迁移；活跃注册表 + 共享启动闸门；A/B 错误字段；删除引用检查；`AUTOMATION_LOG_DIR`；WS 字符串键；A/B 三列 + 索引迁移；`openlist_remote_prefix`；托盘通知器；pycache 清理 | 必须先于 C 引擎 |
| ① | 数据模型（含 pending_files/last_round_no/consecutive_failures）+ 索引 + 保留清理任务 | ⓿ 完成 |
| ② | C 任务 CRUD + bind-options + check-dir + `TaskConfig.vue` | ① 完成 |
| ③ | 引擎（pending 状态机、启动闸门、退避/重试、partial、停止收尾、WS、通知）+ `Execution.vue` + `RealtimeLog.vue` | ② 完成 |
| ④ | `TaskHistory.vue` + 导航/运行指示 + 文档同步 + 测试补齐 + CHANGELOG | ③ 完成 |

- 版本：实施时按 `bump_version.py minor` 递增一次（不写死目标版本号）。
- 文档同步范围：`README.md`、`manual/用户手册.md`、`docs/rules/backend.md`、`docs/rules/frontend.md`、`.env.example`、`CHANGELOG.md`。

## 14. 风险登记册

| 编号 | 风险 | 概率 | 影响 | 等级 | 应对 |
|------|------|------|------|------|------|
| RK-01 | A 失败后无法补偿 | 1 | 5 | 5 低 | pending + 轮次失败重试 + 指纹 A 成功后提交 |
| RK-02 | 重启残留 running 阻塞 | 1 | 5 | 5 低 | 启动清理 + 活跃注册表 + started_time 迁移 |
| RK-03 | 校验目录不匹配 | 2 | 5 | 10 中 | check_dir 精确映射 + 保存/启动双重校验 |
| RK-04 | 单文件失败导致永久停摆 | 1 | 4 | 4 低 | 失败分级 + partial + 重试失败文件 |
| RK-05 | 同一 A/B 任务被手动与自动化并发启动 | 2 | 4 | 8 中 | A/B 共享启动闸门（400）+ 应用层唯一绑定 |
| RK-06 | OpenList 轮询限流/拖慢 | 3 | 3 | 9 中 | 退避 + 抖动 + 串行化轮询 |
| RK-07 | 历史/日志增长淹没数据 | 2 | 3 | 6 中 | 保留策略 + 每日定时清理 |
| RK-08 | 用户误以为会同步文件更新 | 4 | 3 | 12 中 | 文档与界面写明「只处理新增」 |
| RK-09 | 瞬时故障导致任务停摆未被发现 | 3 | 4 | 12 中 | 3 次轮次失败终止 + 托盘/顶栏通知 + 一键重新启动 |
| RK-10 | pending 丢失导致文件永久无 STRM | 2 | 4 | 8 中 | pending 持久化在任务表；DB 与指纹一起事务提交 |
| RK-11 | 空目录/删除文件导致指纹反复变化 | 2 | 2 | 4 低 | 空轮提交空指纹，避免重复扫描 |

---

本方案为产品设计参考，具体实施请结合公司合规与法务要求确认。
