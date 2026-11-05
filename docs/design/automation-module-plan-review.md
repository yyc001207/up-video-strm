# 自动化任务模块设计计划 · 评审意见（第一轮）

> 状态：**待处理**（本文只记录评审意见与修订建议；**未修改** [automation-module-plan.md](automation-module-plan.md) 原文，**未改动**任何代码）
>
> 评审对象：[automation-module-plan.md](automation-module-plan.md)（基线 commit `54ae18b`，版本 4.11.0）
>
> 评审日期：2026-11-06
>
> 评审方式：逐节对照计划与现有代码，结论均给出 `文件:行号`；按「链路能否跑通 / 能否长期无人值守 / 是否可验收」三条线检查。
>
> 关联文档：[上传管理模块计划](upload-module-plan.md) · [后端规范](../rules/backend.md) · [前端规范](../rules/frontend.md)

## 1. 总体结论

| 维度 | 评价 | 说明 |
|------|------|------|
| 方向与架构 | 可行 | 「只编排、不复制产物」的定位正确，A/B 已有创建/启动/状态/取消/日志能力可复用 |
| 链路完整性 | **不成立** | A 阶段失败后无法自动或手动补偿（P0-1）；首次文件已存在时自动化永远不会触发 A |
| 长期运行 | **不成立** | 僵尸 `running` 记录会永久阻塞（P0-2）；单文件失败即终止（P0-5）；无执行超时 |
| 并发正确性 | **不足** | 串行化是 check-then-act（P0-3）；A 的取消键是 `task_id`，会误杀同任务其它执行 |
| 目录模型 | **不匹配** | 默认校验目录取 A 的 `process_path` + 单层列表，而 A 是递归处理（P0-4） |
| 可验收性 | 不足 | 无成功指标、无异常处理清单、无 GWT 验收标准；测试计划缺前端与并发/重启用例 |

**结论：不建议按现文档直接进入实施。** 建议先修订 P0-1 ~ P0-6 涉及的方案表述（只改文档），完成第二轮评审后再排期；P1 可在实施前定稿，P2 可随实现处理。

## 2. P0：阻断实施的问题（6 项）

### P0-1 失败后不可恢复：指纹提交过早 + 新文件只来自单次 B 执行

**问题描述**：计划在 B 成功后立即提交变更指纹，而「进入 A 阶段」的输入只有本次 B 执行新增成功的文件。A 一旦失败、OpenList 校验超时或进程中途重启，这批文件永远无法再次进入 A。

**证据**：

- 计划 §2（L38）「提交本轮变更指纹（仅 B 成功后写入）」；L41「清单为空 → `skipped`」，不进入 OpenList 校验与 A。
- 计划 §3.1（L76）「清除变更指纹（使下一轮强制上传）」；§3.2（L81）手动启动跳过指纹。
- 代码：`backend/app/business/uploader/execution_engine.py:279` 冲突策略 `skip` 时把云端已存在文件记为 `skipped`；`:381` 任一文件失败即返回 `fail`。只有 `status='success'` 的记录会被当作新上传文件（计划 L55）。

**后果（按发生顺序）**：

1. A 失败 → 指纹已提交 → 下一轮「无本地变更」跳过 → A 不会重跑。
2. 手动启动虽跳过指纹，但 B 仍会把所有已存在文件标记为 `skipped` → `new_file_count=0` → `skipped` → **依然不进入 A**。
3. 清除指纹同理。用户只能绕过自动化，去模块 A 手动执行一次，或再放一个新视频进去让 B 至少产生 1 个 `success`；这对无人值守场景是致命的。
4. 首次配置时如果文件早已在云端（例如先手动上传过），第一轮就是 `skipped`，自动化永远不会触发 A（只能去模块 A 手动执行）。
5. 计划给出的「强制一轮」和「清除指纹」两个兜底手段，实际都无法达成「补偿」目标。

**建议改法**：

- 指纹语义改为「上一次**完整成功**（B 无致命错误且 A 成功）的指纹」，**只在 A 成功后提交**；任一步失败不提交，下一轮自动补偿。
- 把「本轮是否有变更」与「本次 B 是否新增」解耦：`new_file_count == 0` 但指纹与上次成功指纹不同 → 跳过 OpenList 校验、**仍然执行 A**（说明变更文件已在云端，或上次已上传但 A 未完成）。
- 手动启动：无新增时也执行 A，日志写明「无新增上传，继续生成 STRM」；否则「手动强制一轮」没有意义。
- `reset-fingerprint` 文案改为「重新扫描并补齐 STRM」，不要写「强制上传」。

### P0-2 用 A/B 的 `status='running'` 判断空闲不可靠（僵尸记录永久阻塞）

**问题描述**：规则 7 用「绑定任务是否存在 `status='running'` 的执行」判断空闲，但系统里存在大量「永远 running」的记录，且没有任何启动清理。

**证据**：

- `backend/app/business/openlist/service.py:806`：A 的 `create_execution` 在**创建时**就写 `started_time`，`status` 默认 `running`；`start_execution`（876-936）没有「已启动」校验。
- `backend/app/business/uploader/service.py:526-552`：B 创建即 `status='running'`、`started_time=None`；`:588` 只阻止二次启动，不清理未启动记录。
- `backend/app/main.py:22-24`：lifespan 只做 `init_db()`；全库没有「重启把 running 置 fail」的逻辑。`run.py` 关停宽限 2s，运行中的 A/B 必然被杀。
- 计划 §2 规则 7（L59、L130、L194）以 `status='running'` 为唯一判据。

**后果**：

- 任一次「运行中关闭应用」「创建执行后没点启动」「启动请求失败」都会留下 running 记录；下一轮空闲检查等到 `wait_timeout_seconds`（默认 600s）超时 → 本轮失败 → 自动化终止。**每次重启都会复现**。
- 用户在 A/B 执行管理里看到永远「运行中」的僵尸记录，也没有入口清理；顶栏「运行中 N」同样会被污染。

**建议改法**：

- 增加**统一启动清理**（作为 C 的前置改动写进 §9）：应用启动时把三张执行表（`open_list_execution`、`upload_execution`、`automation_run`）的 `status='running'` 全部置 `fail`，`error_message='进程重启中断'`。单进程本地应用这样做是安全且必要的。
- 空闲判定不要只看 DB：A/B 引擎维护进程内「活跃执行」注册表（`execution_id → task_id`），C 优先查注册表；DB 只作兜底，并加「`finished_time IS NULL` 且 `started_time` 在合理窗口内」的陈旧判定。
- A 的 `started_time` 应在 `start_execution` 时写，而不是创建时；否则无法区分「已创建未启动」。

### P0-3 绑定任务串行化是 check-then-act，没有互斥；A 的取消键会误杀

**问题描述**：规则 7 要求「确认绑定任务没有正在执行中的实例，有则等待」，但「检查」与「创建并启动」之间没有锁；同时 A 的取消键是 `task_id`，同一任务的所有执行共享一个取消标记。

**证据**：

- 计划 L59、L130、L194 描述串行化，`registry.py`（计划 §5）只规划了 `{task_id: asyncio.Task}`，没有锁。
- `backend/app/business/openlist/service.py:938-949`：任务执行（`task_id != 0`）取消键为 `str(task_id)`，不是 `execution_id`。
- A/B 的 `create_execution` 前后没有任何按任务的互斥保护。

**后果**：

- 两个自动化任务绑定同一 A 任务并同时启动 → 都查到空闲 → 同时创建并启动 A → 两个 A 并发跑同一任务，写入同一输出目录。
- 任一自动化执行「停止」→ `cancel(str(task_id))` → 把另一个自动化甚至用户手动发起的 A 执行一起取消。
- 计划 §10 声称「运行期串行化」可以解决重复绑定，但按现有实现方式无法保证。

**建议改法**：

- `registry.py` 增加按 `(kind, id)` 的 `asyncio.Lock`（FIFO），在锁内完成「检查空闲 + 创建执行 + 启动」整段，不要在中间 `await` 后基于旧判断继续。
- 把 A 的取消键从 `task_id` 改为 `execution_id`（`start_execution` 传 `cancel_key=str(execution.id)`）。这同时修掉「取消一个执行会杀掉同任务所有执行」的历史问题，必须写进 §9 联动改动。
- 若短期不改 A 的取消键，C 的「停止」必须校验 `trigger_ref`，只取消本轮自己创建的执行，并在 §3.2 写明这一限制。

### P0-4 OpenList 校验目录默认值与校验方式不匹配 A 的递归模型

**问题描述**：校验目录默认取 A 任务的 `process_path`，且只用 `list_files` 列一层；A 的生成器是逐目录递归处理的。

**证据**：

- 计划 §6（L207）默认 `OpenListTask.process_path`；L208 `list_files` 单层。
- `backend/app/business/openlist/strm_generator.py:238-280`：`_scan_and_process` 对每个子目录递归调用，`:245` 每个目录只列当前层。

**后果**：

- 常见配置：A 任务处理路径是媒体库根（如 `/media`），B 上传到 `/media/剧名`。校验时列 `/media` 只看到子目录、看不到文件 → 全部判定「缺失」→ 等满 600s → 本轮失败 → 自动化终止，且每轮如此。
- 即使文件都在同一层，`remote_name` 只有文件名；不同子目录的同名文件无法区分。

**建议改法**：

- 校验目录默认值改为「B 的 `remote_dir` 在 OpenList 的挂载路径」（新增映射配置，或绑定 A 任务时要求显式填写并给出示例）；A 的 `process_path` 只作参考展示，不作为默认值。
- 校验改为递归遍历（复用 A 的目录递归方式），按「相对 B 上传目录的路径」比对，而不是 basename。
- 任务配置页增加「检测目录映射」按钮：抽样展示 B 云端目录与 OpenList 目录的对应关系；保存时若校验目录不存在直接报错，不要等到运行期超时。
- 首次轮询 `refresh=True`，后续改为 `refresh=False` + 指数退避（见 P1-3）。

### P0-5 B 的「失败」是文件级的，单文件失败即终止整个自动化

**问题描述**：C 的规则是「B 失败 → 异常终止」，但 B 的 `fail` 含义是「任一文件扫描/重命名/上传失败」，不是「流水线无法运行」。

**证据**：

- `backend/app/business/uploader/execution_engine.py:203`（重命名失败计 `failed`）、`:265`（目标目录读取失败全部计 `failed`）、`:363`（单文件上传失败计 `failed`）、`:381`（`failed > 0` → 返回 `fail`）。
- 计划 §2（L36-37）与决策 #2（L294）：B 失败即终止整个自动化任务。

**后果**：

- 一个无法解析集数的文件、一个被占用的文件、一次重试耗尽，都会让自动化永久停止；重启后仍会在同一文件失败（指纹未提交，会再次重试到它）。
- 千集级媒体库中这是「必然发生」的事件，不是异常。

**建议改法**：

- 在计划中明确**失败分级**：
  - **致命（终止本轮并停任务）**：任务/目录不存在、凭据失效、云端目录不可读、B 完全无进展（`success + skipped == 0`）。
  - **可继续（partial）**：部分文件失败但存在成功/跳过；OpenList 只校验成功文件；本轮 `run.status=partial`，继续 A 阶段。
- C 可按 `file_success + file_skipped > 0` 判定「有进展」；更稳妥的做法是 B 的 `execution_to_dict` 暴露 `has_progress` 或 `pipeline_status`，避免 C 猜测。
- 指纹提交规则同步调整（见 P0-1）：partial 时建议仍推进指纹，失败文件在 run 详情列出，由用户修复后再触发，避免无限重试。若希望失败文件自动重试，则必须记录文件级失败集合并在下一轮强制 B（单值指纹无法表达「部分成功」）；这是 v1 需要明确的取舍点。

### P0-6 「停止」语义未定义：可能取消别人的执行，且没有终态收尾

**问题描述**：计划只写了「停止 = 取消当前进行中的 B/A 执行 + 立即结束循环」，没有定义停止时的执行所有权、终态、日志收尾与等待阶段的中断方式。

**证据**：

- 计划 §3.2（L83）。
- A/B 取消实现不一致：B 立即写 `cancelled`（`backend/app/business/uploader/service.py:602-613`），A 只置取消标记、等生成器自己退出（`backend/app/business/openlist/service.py:938-949`）。

**后果**：

- 若当前没有本自动化创建的执行（如正在「等待绑定任务空闲」），按字面会去取消「当前执行」，可能取消用户手动执行或其他自动化的执行。
- A 的停止是异步的：UI 显示「已停止」时 A 可能还在写 STRM；run 状态、日志结束行、WS 结束帧都没有定义。
- 停止发生在轮次间隔或 OpenList 等待时，需要能打断 `asyncio.sleep`，否则最长仍等 600s。

**建议改法**：

- 停止只取消 `trigger_ref == automation_run:{本轮 id}` 的 B/A 执行；等待空闲阶段只退出等待，不取消任何执行。
- 增加 `stopping` 中间态：先请求取消，等 B/A 进入终态（或超时）后 run 记 `cancelled`，再结束循环。
- 引擎任务用 `asyncio.Event` 做停止信号 + `Task.cancel()` 兜底；`finally` 中必须写 run 终态与日志结束行，避免留下 running。
- WS 在停止时补一帧 `status=cancelled`，前端据此断开。

## 3. P1：实施前应定稿的重要问题（12 项）

| # | 问题 | 证据 | 建议 |
|---|------|------|------|
| P1-1 | 无 B/A 执行超时；`wait_timeout_seconds` 同时承担「OpenList 等待」「等待绑定任务空闲」两种语义 | 计划 L120、L194；A 全局信号量默认 1（`openlist/execution_engine.py:26`）、B 默认 2（`uploader/execution_engine.py:38`），长任务排队很常见 | 拆成 `openlist_wait_timeout`、`idle_wait_timeout`、`stage_timeout` 三个配置；新增「排队中」阶段；`interval_seconds` / `wait_interval_seconds` 加取值范围 |
| P1-2 | 变更探测范围与 B 的实际扫描范围不一致 | `uploader/scanner.py` 只收「视频格式」扩展名并跳过隐藏/系统文件；计划 L193 只 stat 全部文件 | 指纹必须复用 `scanner.normalize_extensions` 与跳过规则；否则字幕/封面变化会产生「有变更但无上传」的空轮 |
| P1-3 | OpenList 轮询每 15s 以 `refresh=True` 全量拉取 | 计划 L196、L208；`openlist_api.list_files` 无本地缓存 | 首次 `refresh=True`，后续 `False`；指数退避 + 随机抖动；多个自动化同时轮询时串行化；大目录评估 `per_page=0` 的响应体量 |
| P1-4 | 历史与日志无限增长，且会污染 A/B 历史 | 计划 L283 把保留策略写为「可加」；每轮都会在 A/B 表各留一条执行记录 | 明确 run 与日志的保留条数/天数并实现清理；A/B 历史默认过滤 `trigger_source=automation` 或折叠展示，提供「仅看手动」开关 |
| P1-5 | 顶栏胶囊语义被改变，点击分流回归 | `frontend/src/stores/running.ts:22`（`total = schedule + upload`）、`App.vue:143-148,187-193`；计划 L250-251 | 自动化是常驻循环，加入 `total` 后胶囊永远显示「运行中」且点击永远进自动化。建议独立指示器「自动化 N」，或胶囊内分组、点击按「真有执行的模块」优先 |
| P1-6 | 数据模型存在错误与冗余 | `phase varchar(16)`（L142）装不下 `waiting_openlist_check`（22 字符）；`is_enabled`（L124）是死字段；`openlist_is_incremental` 实际无效（`openlist/service.py:876-936` 未把 `is_incremental` 传给生成器）；三个布尔可组合出非法状态；`conflict_policy` 说「不落库」但 `upload_execution` 该列存在且非空 | `phase` 改 ≥32；删 `is_enabled`；A 参数改单一 `openlist_mode`（incremental / full / strm_only）；run 增加 `log_path`、`error_code`、`skipped_file_count`、`idle_wait_seconds`；`automation_run` 加 `(task_id, started_time)`、`(status)` 索引 |
| P1-7 | 删除语义自相矛盾 | 计划 L131 一边说「不改 A/B 删除逻辑」，一边要求「被绑定的 A/B 任务不允许删除」；B 是物理删除（`uploader/service.py:413-419`），A 是软删（`openlist/service.py:750-754`）；`automation_task` 无 `is_deleted` | 二选一：A/B 删除前检查 `automation_task` 引用并返回任务名（各改一处），或允许删除但运行时报错并停止。C 表加 `is_deleted`，删除后保留 run |
| P1-8 | API 缺口与冗余 | 无 `GET /tasks/{id}`；`GET /tasks/{id}/bind-options` 在「新建」时没有 id 可传；实时日志需要 task → 当前 run/log 的映射；`execution_id` 过滤与现有 `get_execution_detail` 重复（L165）；`/runs/{id}/report` 未定方案先列入（L232） | 增 `GET /tasks/{id}`、`GET /bind-options?task_id=`；`/active` 返回 `run_id` 与 `log_path`；删除 `execution_id` 过滤需求（直接调 detail 接口）；report 移出本期 |
| P1-9 | 日志目录/配置/打开文件夹未闭环 | `core/settings.py:40-48` 只有 openlist/upload 两个目录；`api/desktop.py:118-133` 的 `kind` 只有 `openlist|upload`；前端 `api/desktop.ts` 类型同样 | 新增 `AUTOMATION_LOG_DIR`、`.env.example` 条目、数据目录创建、日志保留策略；扩展 `kind` 与前端联合类型；`automation_run` 存 `log_path` |
| P1-10 | 运行中编辑/改绑未定义 | 计划 §3.1/§4.1 未提；指纹属于任务，绑定 B 的目录变化会改变指纹含义 | 运行中禁止修改绑定与指纹相关字段（或保存后自动清指纹并提示）；编辑抽屉在 running 时只读 |
| P1-11 | 重复绑定的公平性与饥饿 | 决策 #5（L297）允许重复绑定；两个自动化会互相等待到 600s 超时 | 使用 FIFO 锁；`idle_wait_timeout` 独立且可更长；日志展示「排队第 N 位」；或复核「允许重复绑定」是否确有必要 |
| P1-12 | 瞬时故障导致永久停摆 | 决策 #2（L294）：网络抖动、OpenList 5xx、123 凭据过期都会终止整个任务 | 建议「连续失败 N 次后暂停，保留手动继续」；至少提供一键继续入口与明确失败原因分类 |

## 4. P2：细节与一致性问题

| # | 问题 | 证据/位置 | 建议 |
|---|------|-----------|------|
| P2-1 | 分页规格与项目规范不一致：计划写 20/50/100 | 计划 L252；`docs/rules/frontend.md:60` 与各列表页 `PAGE_SIZES = [10, 20, 50]` | 改为 10/20/50，默认 20 |
| P2-2 | 版本号写死 `4.12.0` | 计划 L313；当前 `backend/app/version.py` 为 4.11.0 | 写「实施时按 `bump_version.py minor` 递增」，不写死目标版本 |
| P2-3 | API 风格与现有模块不统一 | 现有开启/取消是 `POST /executions/start|cancel`（body 传 id）；计划用 `POST /tasks/{id}/start|stop` | 二选一并说明理由；同一模块内保持一致即可 |
| P2-4 | 「无变更跳过」的日志落点自相矛盾 | 计划 L53 说「日志记一行」；L93 说「不落日志文件」 | 明确为「只推 WS、不落文件」，并说明回放不可见 |
| P2-5 | `round_no` 定义缺失；`skipped` 有两种语义 | 计划 L140-141；无变更轮不建 run，导致轮次编号跳号 | 定义「轮次 = 建 run 的轮」或「检测周期」；`skipped` 仅表示「B 成功但无新增」 |
| P2-6 | A/B「任务历史」增加来源列语义不清 | 计划 L164；现有历史页是「每任务最近一次执行」汇总 | 明确来源列取「最近一次执行」的来源，或在执行记录层展示 |
| P2-7 | 三列触发来源无索引 | 计划 L158-160 | `trigger_source` 加索引；查询量小也可不加，但需说明 |
| P2-8 | 测试计划缺项 | 计划 L314 只写后端状态机与 API smoke | 补前端 `npm run type-check` / `npm run build`；补假时钟（避免真实 sleep）、并发抢占、重启残留、停止时机用例 |
| P2-9 | 文档同步范围未列全 | 计划 §12 只写「文档 + CHANGELOG」 | 明确 `README.md`、`manual/用户手册.md`、`docs/rules/backend.md`、`docs/rules/frontend.md`、`.env.example` |
| P2-10 | 缺少需求文档必备章节 | 全文 | 补「成功指标与口径」「范围外（不做）」「异常处理清单」「非功能需求」「数据保留策略」「回滚方案」「术语表」；建议加轻量 RTM |
| P2-11 | 工作区残留旧模块产物 | `backend/app/business/autoflow/__pycache__/`、`backend/app/api/__pycache__/autoflow.cpython-312.pyc`（无源码、未入库） | 实施前清理，避免与新模块混淆；`.gitignore` 补 `backend/upload_logs/`、`backend/automation_logs/` |
| P2-12 | `is_enabled` 与「不做不写」冲突 | 计划 L124 | 删除该字段，需要启停时再加 |
| P2-13 | 自动化终止后无主动通知 | 计划只在「进程重启」时要求 UI 提示；失败只落历史 | 托盘气泡 / 顶栏红点 / 系统通知至少一种；否则无人值守场景下用户可能数天不知道任务已停 |

## 5. 计划中准确、应保留的部分

| 内容 | 说明 |
|------|------|
| 三模块平级、`/automation/*` + `automation_*` 命名 | 与现有模块化导航和表命名约定一致 |
| 「不产生业务产物、不复制 A/B 历史」的边界 | 方向正确，避免数据双写 |
| 新文件来源 = `upload_file_record` 的 `execution_id + status='success'` | 数据来源准确，能精确圈定本次上传 |
| A 的取消键为 `str(task_id)` 的判断 | 与 `openlist/service.py:938-949` 一致（但这正是 P0-3 要改的点） |
| 触发来源三列的增量迁移方式 | 与 `core/database.py` 的 `_ensure_*_columns` 模式一致，不重建表 |
| 侧栏顺序、日志级别文案、列表页骨架、MINOR 版本级别 | 与现有规范一致 |
| 决策记录（m06952 / m06954） | 可追溯，便于后续变更管理 |

## 6. 建议的修订清单（按计划章节）

### 6.1 §2 固定执行链路：改为可恢复的状态机

```text
每轮（检测周期开始）
  F = 本地视频文件 stat 指纹（路径 + 大小 + mtime_ns，范围与 B 扫描一致）
  F == task.scan_fingerprint（上次完整成功的指纹）且非手动 → 跳过（不建 run，仅 WS 一行）
  ↓ 有变更或手动
建 run（phase=waiting_idle）
  获取绑定 B/A 任务的 FIFO 锁（等待超时 → run fail，按失败策略处理）
  创建并启动 B（conflict_policy=skip）
  ↓ 等 B 终态
B 无进展（success+skipped=0）或致命错误 → run fail，不提交指纹
  ↓ 有进展（允许部分文件失败）
新文件 = 本次 status='success' 的相对路径集合
  ↓ 新文件非空？
  是 → OpenList 递归校验（仅这些文件）→ 缺失/超时 → run fail，不提交指纹
  否 → 跳过校验（变更已在云端，或 B 全部跳过）
  ↓
启动 A（incremental）→ 等终态
  ↓
A 成功 → 提交指纹 F → run success（新文件=0 时记 skipped/已同步）
A 失败/取消 → run fail，不提交指纹（下一轮自动补偿）
```

配套规则修订：

| 计划位置 | 现表述 | 建议改为 |
|----------|--------|----------|
| L53 规则 1 | 指纹在 B 成功后提交 | 指纹在 **A 成功后**提交；定义「上次完整成功」 |
| L54 规则 2 | 手动启动跳过指纹 | 手动启动跳过指纹；**无新增时仍执行 A** |
| L55 规则 3 | 校验范围限本次新文件 | 保留；补充「新文件为 0 但指纹变化时进入 A」 |
| L59 规则 7 | 检查绑定任务无运行实例，有则等待 | 改为「按 (kind,id) 的 FIFO 锁 + 所有权校验」；A 取消键改 `execution_id` |
| L36-37 | B 失败即终止 | 增加致命/可继续（partial）分级 |
| L83 停止 | 取消当前 B/A + 结束循环 | 只取消本轮自有执行；增加 `stopping` 态与终态收尾 |

### 6.2 §4 数据模型：建议调整

| 表/字段 | 调整 |
|---------|------|
| `automation_task` | 增加 `is_deleted`；删除 `is_enabled`；A 参数改为单一 `openlist_mode`；`wait_timeout_seconds` 拆为 `openlist_wait_timeout` / `idle_wait_timeout` / `stage_timeout`；`scan_fingerprint` 语义注明「上次完整成功」 |
| `automation_run` | `phase` 改 `varchar(32)`，补 `waiting_idle`；`status` 增加 `partial`、`stopping`；增加 `log_path`、`error_code`、`skipped_file_count`、`idle_wait_seconds`；加 `(task_id, started_time)`、`(status)` 索引 |
| A/B 执行表 | 三列触发来源保留；`trigger_source` 加索引；`open_list_execution.started_time` 改在 `start_execution` 写入 |
| 删除语义 | 明确 `automation_task` 软删；run 保留；A/B 删除前检查引用（或明确允许悬空并给运行期提示） |

### 6.3 §5/§6 执行引擎与校验

- `registry.py` 增加三样东西：运行实例表、按 `(kind,id)` 的 FIFO 锁、取消事件（`asyncio.Event`）。
- 轮询 DB 的间隔保留 2s，但增加阶段超时与「排队中」判定；A/B 状态查询封装成适配函数，避免 C 直接依赖表结构。
- OpenList 校验：默认目录改为 B `remote_dir` 的映射；递归比对相对路径；首次 `refresh=True`，后续 `False` + 退避 + 抖动。
- 日志：`automation_logs/automation_run_{run_id}.log` 目录进 `settings`；run 表存 `log_path`；提供保留清理。

### 6.4 §7 API 调整

| 调整 | 说明 |
|------|------|
| 新增 `GET /tasks/{id}` | 编辑抽屉需要完整当前值 |
| `GET /bind-options` 改为可选 `task_id` | 新建时也能取可选 B/A 任务与 A 处理路径 |
| `GET /active` 返回 `run_id`、`log_path` | 实时日志页需要 task → 当前 run 的映射 |
| 移除 `GET /runs/{id}/report`（本期） | 未定方案的功能不列入 v1 |
| 移除 `execution_id` 过滤需求 | 已有 `get_execution_detail`，直接跳转详情即可 |
| `POST /tasks/{id}/stop` 返回 `stopping` | 与前端中间态一致 |

### 6.5 §8 前端调整

- 分页统一 10/20/50；`PAGE_SIZES` 复用现有常量。
- 顶栏胶囊：不要把 automation 直接加进 `total`；建议独立「自动化 N」指示器，或胶囊分组展示；点击优先级按「确有执行」的模块分流。
- `utils/ws.ts` 的 module 联合类型需扩展 `automation`，并新增 `connectAutomationWs`；WS key 用 `automation:{task_id}`，避免与现有整数 execution_id 冲突（`websocket/manager.py:17` 目前类型标注为 `Dict[int, ...]`）。
- `api/desktop.ts` 的 `openLogDir` 类型扩展 `automation`。
- 新增 `api/automation.ts`、`types/automation.ts`；任务配置页增加「检测目录映射」按钮。

### 6.6 §9 联动改动：补充三项必要改动

1. 启动时统一清理 A/B/C 的残留 `running`（见 P0-2）。
2. A 的取消键由 `task_id` 改为 `execution_id`（见 P0-3）。
3. A/B 删除前检查 `automation_task` 引用（见 P1-7）。

> 这三项都超出「C 只编排」的范围，但缺一不可；§9 目前写「无其它行为变化」，与实际情况不符。

## 7. 需要用户拍板的决策（建议在第二轮评审前确认）

| # | 决策 | 选项 | 建议 |
|---|------|------|------|
| D-1 | B 部分文件失败时的处理 | A. 仍按现决策终止；B. 分级为 partial 继续；C. 连续 N 次失败后暂停 | B（否则大库必然停摆），并保留 C 作为后续增强 |
| D-2 | 重复绑定是否保留 | A. 允许 + 串行；B. 改为唯一约束 | 若自动化是长期常驻，B 更简单可靠；若确需多对一，A 必须配 FIFO 锁与更长等待 |
| D-3 | 手动启动的语义 | A. 仅跳过指纹；B. 无新增也执行 A | B；否则「手动强制一轮」无法补偿 A 失败 |
| D-4 | 校验目录默认值 | A. A.process_path；B. B.remote_dir 的 OpenList 映射；C. 必填 + 检测按钮 | B + C（默认映射，保存前检测） |
| D-5 | 历史与日志保留 | A. 永久；B. 保留 N 天/条；C. 仅保留最近 N 轮 | B；A/B 历史默认过滤 automation |

## 8. 风险登记册（修订前）

| 编号 | 风险 | 概率 | 影响 | 等级 | 应对 |
|------|------|------|------|------|------|
| RK-01 | A 失败后链路无法恢复，需人工加文件才能补救 | 5 | 5 | 25 高 | P0-1：指纹改为 A 成功后提交 + 无新增也执行 A |
| RK-02 | 重启残留 running 阻塞空闲检查，任务反复超时终止 | 4 | 5 | 20 高 | P0-2：启动清理 + 活跃注册表 |
| RK-03 | 校验目录/递归模型不匹配，每轮超时 | 4 | 5 | 20 高 | P0-4：B 目录映射 + 递归校验 + 检测按钮 |
| RK-04 | 单文件解析/权限失败导致自动化永久停止 | 5 | 4 | 20 高 | P0-5：失败分级 + partial |
| RK-05 | 重复绑定并发启动同一 A/B 任务 | 3 | 4 | 12 中 | P0-3：FIFO 锁 + A 取消键改 execution_id |
| RK-06 | OpenList 轮询触发限流或拖慢应用 | 3 | 3 | 9 中 | P1-3：退避 + 抖动 + 缓存 |
| RK-07 | 每轮 A/B 执行记录与日志淹没历史 | 4 | 3 | 12 中 | P1-4：保留策略 + 默认过滤 |
| RK-08 | 用户误以为自动化会同步「文件内容更新」 | 4 | 3 | 12 中 | 文档与界面写明「只处理新增，不处理同名更新」 |

## 9. 建议的实施顺序（修订后）

| 阶段 | 内容 | 前置关系 |
|------|------|----------|
| ⓿ 前置 | 启动清理残留 running；A 取消键改 `execution_id`；A/B 删除引用检查；`AUTOMATION_LOG_DIR` 配置 | 必须先于 C 的引擎实现 |
| ① | 数据模型（修正后的 `automation_task` / `automation_run`）+ A/B 触发来源 + 来源展示 | ⓿ 完成 |
| ② | C 任务 CRUD + `bind-options` + 目录映射检测 + 配置页 | ① 完成 |
| ③ | 引擎（可恢复状态机、FIFO 锁、阶段超时、partial、停止收尾、WS）+ 执行管理页 | ② 完成 |
| ④ | 任务历史、导航/运行指示、文档同步、测试补齐、CHANGELOG | ③ 完成 |

版本：实施时按 `bump_version.py minor` 递增一次，不写死 4.12.0。

## 10. 建议补入计划的验收标准（GWT）

- [ ] 本地新增 1 个云端不存在的视频 → B 上传 1 个、OpenList 校验通过、A 成功、run=success、指纹更新。
- [ ] A 执行失败 → 下一轮**无新增文件**也能再次触发 A，直到成功（自动补偿）。
- [ ] 首次配置且文件早已在云端 → B 全部 skip，仍执行 A 并生成 STRM。
- [ ] 进程在 B 或 A 阶段重启 → 残留 running 全部标 fail；自动化不自动恢复；手动启动可继续。
- [ ] 同一 A 任务被两个自动化绑定 → 同时启动严格串行，无并发 A 执行；停止任一不影响另一个。
- [ ] A 的 `process_path` 为父目录、B 上传到子目录 → 校验能按相对路径正确找到文件。
- [ ] 单个文件无法解析集数 → 本轮 partial，其余文件继续进入 A，自动化不终止。
- [ ] 本地无任何变更 → 不建 run，仅实时日志一行「无本地变更，跳过本轮」。
- [ ] 停止发生在「等待绑定任务空闲」「OpenList 等待」「轮次间隔」三种时机 → 都能立即结束，run 记 cancelled 且有结束日志。
- [ ] A/B 历史能按「手动 / 自动化任务 X」区分；自动化 run 详情能跳转到对应 A/B 执行记录。

## 11. 结论

计划的方向、边界划分和复用思路是成立的，问题集中在**状态机的闭环与长期运行的健壮性**，而不是架构选型。P0-1 ~ P0-6 都属于「不改就会在真实环境跑不通」的问题，建议按本文 §6 修订计划后，再做一轮聚焦评审（只看 P0 是否闭环）。P1 建议在实施前定稿，P2 可随实现处理。

---

本方案为产品设计参考，具体实施请结合公司合规与法务要求确认。
