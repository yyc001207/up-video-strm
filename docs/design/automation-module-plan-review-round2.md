# 自动化任务模块设计计划 · 第二轮评审意见

> 状态：**待处理**（本文只记录评审意见；**未修改** [automation-module-plan.md](automation-module-plan.md) 原文，**未改动**任何代码）
>
> 评审对象：[automation-module-plan.md](automation-module-plan.md)（commit `101ec9c`，版本 4.11.0）
>
> 第一轮评审：[automation-module-plan-review.md](automation-module-plan-review.md)（commit `bf048d5` / `21755c2`）
>
> 评审日期：2026-11-06
>
> 评审方法：先逐项核对第一轮 P0/P1/P2 的闭环度，再审查本轮新增/残留问题；结论均给出计划行号与代码位置。

## 1. 总体结论

| 维度 | 结果 | 说明 |
|------|------|------|
| 第一轮 P0 闭环 | **2/6 完全闭环，4/6 部分闭环** | P0-2（僵尸 running）、P0-6（停止语义）已闭环；P0-1/P0-3/P0-4/P0-5 仍有残留 |
| 第一轮 P1 闭环 | **5/12 完全闭环，7/12 部分闭环** | 已闭环：指纹范围、顶栏胶囊、日志目录、运行中只读、重复绑定；其余仍有边界缺口 |
| 本轮新增阻断 | **5 项** | 补偿与终止矛盾、补偿路径绕过可见性校验、空目录误致命、手动竞态、相对路径无数据源 |
| 文档完整度 | 显著提升 | 成功指标、范围外、异常清单、非功能、回滚、术语表已补齐 |
| 可实施性 | **暂不具备** | 5 项阻断未解前，实施会再次返工 |

**结论：修订方向正确、质量明显提升，但仍有 5 项阻断，不建议直接进入实施。** 建议做一次针对性修订（5 项 P0 + §7 列出的 P1 项），不必第三次全文重写；修订后再做一轮只核对 P0 闭环的短评审。

## 2. 第一轮问题闭环核对

> 计划头部写「已按第一轮评审意见修订 P0 六项、P1 十二项、P2 十三项」；但「已修订」不等于「已闭环」。逐项核对如下，状态以计划正文的实际表述为准，不以修订摘要为准。

### 2.1 P0（6 项）

| 编号 | 第一轮问题 | 本轮修订 | 状态 | 残留说明 |
|------|------------|----------|------|----------|
| P0-1 | 失败后不可恢复 | 指纹改为 A 成功后提交；无新增也执行 A；reset 文案修正 | **部分闭环** | 与「致命即终止」冲突，A 失败后任务已停，没有「下一轮」可补偿（R2-P0-1） |
| P0-2 | 僵尸 running 阻塞 | 启动清理三表 + A/B 活跃注册表 + A `started_time` 移到启动 | **已闭环** | §5 写「A/B 另有 stopping」不准确，A/B 状态枚举没有 stopping（P2） |
| P0-3 | 串行化竞态 / 取消误杀 | 唯一绑定 + FIFO 锁 + A 取消键改 `execution_id` | **部分闭环** | 唯一绑定后 C 与 C 不再竞争；FIFO 锁对「手动启动」不可见，仍存在竞态（R2-P0-4） |
| P0-4 | 校验目录不匹配 | `check_dir` 必填 + 检测按钮 + 递归相对路径 | **部分闭环** | 相对路径无数据来源；`OPENLIST_REMOTE_PREFIX` 未定义（R2-P0-5、P1-7） |
| P0-5 | 单文件失败即终止 | 失败分级 + `partial` 继续 | **部分闭环** | 空目录被误判为致命；partial 失败文件不会自动重试（R2-P0-3、P1-4） |
| P0-6 | 停止语义 | `stopping` 中间态 + 只取消自有执行 + 可打断等待 | **已闭环** | 轮次间隔属于 run 还是任务运行时仍未定义（P1-6） |

### 2.2 P1（12 项）

| 编号 | 第一轮问题 | 状态 | 残留说明 |
|------|------------|------|----------|
| P1-1 | 超时三拆 | 部分 | `stage_timeout` 超时后是否取消 B/A、是否等待终态未定义 |
| P1-2 | 指纹范围对齐 B | 已 | — |
| P1-3 | OpenList 退避 | 部分 | 退避基数与 `wait_interval_seconds` 关系未定义；串行轮询的公平性未说明 |
| P1-4 | 历史与日志保留 | 部分 | 清理只在任务/进程启动时执行，24/7 任务永不触发；run 1000 条与日志 200 个不一致 |
| P1-5 | 顶栏胶囊语义 | 已 | 独立指示器方案正确 |
| P1-6 | 数据模型修正 | 部分 | `is_incremental` 无法「实际生效」；唯一索引措辞与实现细节不清 |
| P1-7 | 删除语义 | 部分 | 批量删除、服务器删除未覆盖；B 为物理删除 |
| P1-8 | API 缺口 | 部分 | 新建任务无 id 时无法调用 `check-dir`；`bind-options` 未排除已绑定任务 |
| P1-9 | 日志目录闭环 | 已 | — |
| P1-10 | 运行中只读 | 已 | — |
| P1-11 | 重复绑定 | 已（按用户决策改唯一绑定） | FIFO 锁的「防手动竞争」目的不成立（R2-P0-4） |
| P1-12 | 瞬时故障停摆 | 部分 | 已明确「人工继续」，但正文仍承诺「下一轮自动补偿」，两者冲突（R2-P0-1） |

### 2.3 P2

分页、版本号、无变更日志口径、`round_no`/`skipped`、来源列口径、索引、测试与文档范围、必备章节、pycache、`is_enabled` 等 **大部分已闭环**。仍未闭环：API 风格（`POST /tasks/{id}/start` vs 现有 `/executions/start`）、`stopping` 未进历史筛选、§10.1 表格语法错误、A/B `stopping` 措辞、`error_message` 截断、`trigger_source` 索引迁移语句、回滚未覆盖 A 前置改动。详见 §5。

## 3. 本轮阻断问题（5 项）

### R2-P0-1 「自动补偿」与「致命即终止」互相矛盾

**问题**：计划一边承诺「A 失败/OpenList 超时 → 不提交指纹，下一轮自动补偿」，一边把 A 失败、OpenList 超时、B 无进展都定义为「致命 → 终止整个自动化任务」。任务已停，不存在「下一轮」。

**证据**：

- 计划 §2 L65-66：A 成功提交指纹；A 失败/取消 → 「下一轮自动补偿」。
- 计划 §2 L56：B 无进展 → run fail（「下一轮重试」）。
- 计划 §2 规则 6 L78：只有用户停止、致命错误两种终止；瞬时故障也按致命处理，用户修复后手动继续。
- 计划 §10.1 L331：A 失败/取消 → 致命 `A_FAILED`，终止任务。
- 计划 §1.1 L31：失败补偿目标 **100%**（致命错误除外），与上述终止规则冲突。

**后果**：

- A 失败一次，任务终止；指纹未提交但没有任何轮次会再执行，正文承诺的「自动补偿」不会发生。
- OpenList 超时同理：任务终止，`missed_files` 只是记录，不会重试。
- 指标把「致命错误」排除后，A 失败恰好被排除在外，等于没有衡量补偿；指标与正文承诺不一致。

**建议改法**：

- 把失败分为**轮次失败**与**任务终止**两级：轮次失败不终止循环，按退避重试，连续 N 次（建议 3 次）后才终止并通知；配置类错误（任务/目录不存在、凭据失效、check_dir 不可访问）才立即终止。
- A 失败、OpenList 超时、网络/5xx 归为轮次失败；B 全部文件失败归为轮次失败；B 配置错误归为致命。
- 在 `automation_task` 或运行时状态增加 `consecutive_failures`，成功后清零。
- 指标改为「A 失败后 3 轮内自动补偿成功率 ≥ 95%」，并给出统计口径。

### R2-P0-2 补偿路径会绕过 OpenList 可见性校验（缺少 pending 状态）

**问题**：本轮流程把「本次 B 新增文件为空」直接解释为「变更已在云端」，跳过 OpenList 校验并执行 A。这个推断在 **A 失败补偿** 场景成立（上一轮已经校验过可见性），但在 **OpenList 超时 / 校验阶段进程重启** 场景不成立：文件已上传但尚未确认可见，下一轮 B 全部跳过、新文件为空，流程会跳过校验直接跑 A，A 可能看不到文件却返回成功，随后提交指纹，文件永久失去 STRM。

**证据**：

- 计划 §2 L59-61：「新文件非空？否 → 跳过校验（变更已在云端或 B 全部跳过）」。
- 计划 §2 L60：OpenList 缺失/超时 → run fail（不提交指纹）；但未定义下一轮如何继续校验。
- 计划 §4.1 L170：`missed_files` 只是记录，未作为下一轮的待校验集合使用。
- 代码：`upload_file_record` 只有 `local_path` / `remote_name`（`models/uploader/file_record.py:26-27`）；B 的 skip 策略把已存在文件记为 `skipped`（`uploader/execution_engine.py:279`），因此下一轮 `status='success'` 集合为空。

**后果**：

- OpenList 超时一次后，无论任务是否因致命而停止，用户手动重启后的下一轮仍会跳过可见性校验；若按 R2-P0-1 改为「轮次失败继续」，则会自动暴露该问题。A 可能在没有新文件可见时“成功”，指纹被提交，文件永远不生成 STRM。
- 进程在「校验阶段」重启也会触发同样问题。
- 这是修复 R2-P0-1 后必然暴露、且当前手动恢复也会踩中的路径，两者必须一起修。

**建议改法**：

- 引入持久化的「待完成文件集合」`pending_files`（JSON，存 `automation_task` 或独立表）：B 识别到新文件时写入；**只有 OpenList 全部可见且 A 成功后**才清空。
- 每轮开始：若 `pending_files` 非空，无论本次 B 是否有新增，都先对这些文件做可见性校验；校验通过再执行 A；A 成功后才清空。
- 这样同时覆盖 A 失败补偿（pending 仍在 → 重新校验 → A）与 OpenList 超时补偿，不再依赖 `new_file_count` 推断可见性。
- 首次配置且云端已有文件时（B 全部 skip、pending 为空），建议至少对 `check_dir` 做一次 `refresh=True` 的预热与目录可访问校验，再执行 A；A 的生成器默认 `refresh=False`（`strm_generator.py:245`），否则可能读到 OpenList 旧缓存。
- 若不引入 pending，至少要用上一轮 `missed_files` + `last_failed_stage` 判断「上一轮是否卡在校验阶段」，并在该状态下强制重新校验；但不如 pending 集合稳妥。

### R2-P0-3 空目录 / 无视频被误判为 `B_NO_PROGRESS` 致命

**问题**：B 对空目录返回 `success` 且 `file_total=0`、`success=0`、`skipped=0`；C 的规则把「`success+skipped==0`」一律判为致命 `B_NO_PROGRESS`，会在「先建自动化、后放文件」这种常见配置顺序下第一轮就终止任务。

**证据**：

- `uploader/execution_engine.py:240`：`if not plan_items: return "fail" if progress["failed"] > 0 else "success"` —— 空目录返回 `success`，计数全 0。
- 计划 §2 L56：「B 无进展（success+skipped==0）或致命错误 → run fail」。
- 计划 §10.1 L328：`B_NO_PROGRESS` 判为致命，终止任务。

**后果**：

- 新建自动化任务时本地目录还没放视频 → 第一轮即终止，用户以为功能坏了。
- 目录被临时清空/移动 → 任务终止，而不是等待。
- 与「持续运行、只有用户停止或致命错误才停」的定位冲突。

**建议改法**：

- 区分三种情况：
  - `file_total == 0 && file_failed == 0` → **空轮**（`empty` / `skipped`），不终止，下一轮继续；
  - `file_total == 0 && file_failed > 0`（扫描错误）→ 致命或按配置错误处理；
  - `file_total > 0 && success + skipped == 0`（全部失败）→ 轮次失败，连续 N 次后终止。
- 空轮是否提交指纹需明确：若因文件被删除导致指纹变化，建议提交（避免每 60s 重复扫描空目录）；若首次为空，也可提交空集指纹。
- 增加 `empty` 运行状态或在 UI 显示「本轮无文件」，不要记为失败。

### R2-P0-4 FIFO 锁无法防止与手动执行的竞态

**问题**：改为唯一绑定后，两个自动化任务不会再共享 A/B 任务，C 与 C 的竞争已消失；计划保留 FIFO 锁并声称「防止 check-then-act 及与手动执行的竞争」，但**手动启动 A/B 不会获取 C 的锁**，锁对手动路径完全不可见。

**证据**：

- 计划 §2 规则 7 L79、§5 L220：FIFO 锁 + 空闲检查。
- 计划 §14 RK-05 L447：把「自动化与手动并发」风险降到 8，理由包含 FIFO 锁。
- `openlist/service.py:876-936`、`uploader/service.py:578-600`：`start_execution` 没有按任务的互斥/活跃检查，任何调用方都可直接启动。

**后果**：

- C 检查空闲 → 用户手动点启动 → C 创建并启动，两次执行并发；A 同时写同一输出目录，B 可能重复上传（skip 策略能挡一部分）。
- FIFO 锁只保护 C 内部；唯一绑定后 C 内部已无共享任务，锁的实际作用接近于零，风险表的高估会误导排期。

**建议改法**：

- 在 A/B 的 `start_execution` 增加**共享的按任务启动闸门**：`is_task_active(task_id)` 为真则返回 400「任务正在执行」，并在同一事件循环 tick 内完成「检查 + 注册」，引擎 `finally` 注销。注册应发生在**入队前**（拿到信号量之前），保证排队中的执行也算活跃。这样手动与自动化都受同一约束，C 的 FIFO 锁退化为 UX 排队。
- 若不做共享闸门，则必须在计划中明确「C 与手动仍可能并发」，并下调 RK-05 的缓解描述；不能同时声称锁能防手动竞争。
- 增加对应回归用例（手动与自动化同时启动只允许一个）。

### R2-P0-5 相对路径校验无数据来源；`check_dir` 语义过度设计

**问题**：计划要求「按相对 `check_dir` 的路径」比对本次新文件，但 B 的上传记录只有 `local_path` 和 `remote_name`，没有云端相对路径；B 的上传是平铺到 `remote_dir` 的（不保留本地子目录结构），因此「相对路径」在现有数据里无法可靠推导。

**证据**：

- `models/uploader/file_record.py:26-27`：只有 `local_path`、`remote_name`；无 `remote_rel_path`。
- `uploader/execution_engine.py`：所有文件上传到 `execution.remote_dir` 解析出的同一个 `parent_file_id`，不创建子目录。
- 计划 §2 L58/L60、§6 L235：使用「相对路径」并递归遍历。

**后果**：

- 如果 `check_dir` 等于 B `remote_dir` 的 OpenList 映射，直接比对 `remote_name` 即可，递归是多余的；
- 如果 `check_dir` 是父目录，现有数据无法知道文件在云端的子路径，递归比对无法实现，只能靠 `local_path` 猜测（B 已重命名、平铺，猜不准）。
- 深度 5/500 的递归在大目录下还会增加 OpenList 请求量。

**建议改法**：

- 明确 `check_dir` = **B `remote_dir` 在 OpenList 的精确映射**，比对 `check_dir + "/" + remote_name`；去掉递归，或仅在 B 未来支持子目录时再加。
- 若确实要支持多级结构，需在 `upload_file_record` 增加 `remote_rel_path`（B 侧写入），而不是在 C 侧推导。
- 保存时校验 `check_dir` 与 B `remote_dir` 的映射关系（前缀 + 后缀），避免用户填成父目录。

## 4. 本轮重要问题（P1）

| 编号 | 问题 | 证据 | 建议 |
|------|------|------|------|
| R2-P1-1 | `stage_timeout` 超时后的行为未定义 | 计划 L146、L221 | 明确：超时先请求取消 B/A，等一个 grace 期（如 30s），再记 fail；避免 run 已失败但 B/A 仍在跑 |
| R2-P1-2 | B 的错误原因不可得，`B_CLOUD_ERROR` 与 `B_NO_PROGRESS` 无法区分 | `upload_execution`、`open_list_execution` 均无 `error_message` / `error_code`（模型字段列表可证）；`_finish_execution` 只写状态与计数 | 给 A/B 执行表增加 `error_code`/`error_message`（或让 adapters 返回 B 的错误摘要）；C 才能做失败分级与错误码映射 |
| R2-P1-3 | `is_incremental` 无法「实际生效」 | `strm_generator.execute(force, strm_only, cleanup)` 没有 `is_incremental` 参数（L404）；`start_execution` 只传 `is_force`/`strm_only`（`openlist/service.py:927`） | 不要承诺透传；`openlist_mode` 只映射 `(is_force, strm_only)`，`is_incremental` 仅保留为历史展示或删除 |
| R2-P1-4 | partial 的失败文件不会自动重试 | 计划 L65：A 成功后照常提交指纹；失败文件只列在详情 | 明确策略：v1 建议提交指纹 + 提供「重试失败文件」按钮（重新跑一次 B，成功项 skip、失败项重试）；或维护文件级失败集合并设重试上限 |
| R2-P1-5 | 保留清理只在任务/进程启动时执行 | 计划 L125、L229 | 24/7 任务永不触发清理；增加每日定时清理（lifespan 后台任务）或每轮轻量检查；同时对齐 run 1000 条与日志 200 个的保留口径 |
| R2-P1-6 | run 生命周期与 `phase=interval` / `stopping` 矛盾 | 计划 L65（A 成功即 run success）、L162（phase 含 interval）、L161（status 含 stopping）、L106（间隔中停止） | 明确：interval 属于任务运行时状态，不属于已结束的 run；`stopping` 建议放 phase 而非 status；间隔中停止只停循环，不需要 run 终态 |
| R2-P1-7 | `OPENLIST_REMOTE_PREFIX` 没有存储/接口定义；新建任务无法调 `check-dir` | 计划 L93、L233；`open_list_config` 无此字段（`models/openlist/config.py`） | 明确存 `open_list_config` 还是环境变量；`POST /check-dir` 支持不传 task_id（body 带 B task_id + check_dir）；`bind-options` 排除已绑定任务并返回 `bound_by` |
| R2-P1-8 | A `started_time` 迁移影响历史排序与实时日志用时 | `openlist/service.py:966` 按 `started_time.desc()` 排序；`TaskHistory.vue:67` 用 `finished/started/created`；`RealtimeLog.vue:385` 用 `started_time` 算用时 | 迁移后未启动记录 `started_time=NULL`，排序落底、实时页回退 `Date.now()`；补 UI 处理与回归用例，或保留 `created_time` 作为排序兜底 |
| R2-P1-9 | 唯一绑定索引的实现细节与并发异常未定义 | 计划 L137-138；`upload_task` 无 `is_deleted`（`models/uploader/task.py`） | 明确部分唯一索引建在 `automation_task.is_deleted=0`（SQLite `sqlite_where`），不是 `upload_task.is_deleted`；并发创建捕获 `IntegrityError` → 400 并提示占用任务名；批量/交换绑定需整体校验 |
| R2-P1-10 | A/B 删除引用检查不完整 | 计划 L300-301；`delete_server` 只软删服务器与目录（`openlist/service.py:521-534`）；批量删除未提 | 覆盖单删/批删/服务器删除；服务器删除时若仍有自动化任务引用其 A 任务，至少警告或阻止；B 物理删除前必须检查 |
| R2-P1-11 | 终止通知的实现可行性未验证 | `desktop.py:295` 的 `tray_icon` 是函数局部变量；`:344` 才调用 `notify` | 需要把托盘图标提升为模块级/可注入的通知器，并处理 asyncio 线程与 pystray 线程的调用；用户主动停止不应弹「错误」气泡；网页版红点的未读状态需定义存储 |
| R2-P1-12 | `queue_pos` 与 `asyncio.Lock` 不匹配 | 计划 L105、L202、L256 | `asyncio.Lock` 不暴露等待者；要显示位次需自己维护 FIFO 等待队列（`asyncio.Condition` + deque），否则删掉 `queue_pos` 字段 |
| R2-P1-13 | 退避基数与 `wait_interval_seconds` 冲突 | 计划 L94（5-120 可配）、L236（15→30→60 固定） | 以 `wait_interval_seconds` 为基数做退避（如 base、2×base、4×base，封顶 60），再加 ±20% 抖动；否则用户配 30/120 不生效 |
| R2-P1-14 | 成功指标不可测量；错误码表不完整且表格语法错误 | 计划 L27-33、L324-334；L326 两行被误合并 | 明确指标统计 SQL/接口；补 `IDLE_TIMEOUT`、`STAGE_TIMEOUT`、`CHECK_DIR_UNREACHABLE`、`OPENLIST_API_ERROR`、`A_CANCELLED`、`PROCESS_RESTART`、`INTERNAL_ERROR`；修复 L326 表格 |

## 5. P2 细节与一致性问题

| # | 问题 | 位置 | 建议 |
|---|------|------|------|
| P2-1 | API 风格仍与现有模块不一致 | 计划 L252-255；现有 `POST /executions/start`、`/executions/cancel` | 统一为动作式或 REST 式，并在计划中说明取舍 |
| P2-2 | `stopping` 未进入历史筛选 | 计划 L161 vs L123 | 要么加入「停止中」，要么改为 `phase=stopping` |
| P2-3 | 「A/B 另有 stopping」与代码不符 | 计划 L227 | A/B 状态枚举只有 running/success/fail/cancelled；改为「C 的 run 另有 stopping」 |
| P2-4 | 文档语法/笔误 | 计划 L71 尾部多余反引号；L326 两行合并 | 修正 Markdown |
| P2-5 | `round_no` 在保留清理后可能重置 | 计划 L160、L125 | 在任务上存 `last_round_no`，或接受重置并注明 |
| P2-6 | 日志被保留清理后详情 404 | 计划 L259 | `GET /runs/{id}/logs` 返回明确的「日志已清理」，UI 占位 |
| P2-7 | 任务名重复导致 `trigger_name` 歧义 | 计划 L136 | 增加名称唯一校验，或允许重复但在来源展示中带 ID |
| P2-8 | `error_message` 512 可能截断 | 计划 L172 | 截断加省略号，完整原因写日志 |
| P2-9 | `trigger_source` 索引无迁移语句 | 计划 L184；`database.py` 只有 ALTER，无 `CREATE INDEX` | 在 `_ensure_*` 中补 `CREATE INDEX IF NOT EXISTS` |
| P2-10 | 回滚未覆盖 A 的前置改动 | 计划 L344-348 | 说明 A 取消键/started_time/活跃注册表在回滚后保留且向后兼容，或给出回退步骤 |
| P2-11 | `upload_task` 无 `is_deleted`，措辞易误读 | 计划 L137 | 明确索引建在 `automation_task.is_deleted` |
| P2-12 | `missed_files` 可能很大且无上限 | 计划 L170 | 限制存储/展示条数，超出写日志 |
| P2-13 | `interval_seconds=0` 未强制最小 10s | 计划 L95 | API/UI 双重限制，避免连续空转 |
| P2-14 | `check_dir` 递归深度 5/500 与精确映射矛盾 | 计划 L235 | 若精确映射则去掉递归；若保留递归，说明深度依据 |
| P2-15 | 测试缺关键场景 | 计划 L367-376 | 补：空目录、B 预扫描失败 vs 空目录（依赖 error_code）、stage_timeout 取消、手动并发、唯一索引竞态、保留清理时钟、间隔中停止、A started_time 迁移 |
| P2-16 | 成功指标「无人值守 ≥7 天」偏低且无采集方式 | 计划 L29 | 建议 ≥30 天或「无致命停摆 ≥14 天」，并说明从 run 表统计 |
| P2-17 | `check_dir` 保存与启动的校验行为不一致 | 计划 L97：「不可达时警告但允许保存，运行期启动前再校验一次」 | 明确启动时是 400 拒绝（推荐，不建 run）还是先建 run 再 fail；避免用户看到一条无意义的失败记录 |
| P2-18 | WS 键类型迁移有破坏 A/B 日志的风险 | 计划 L306-307；`websocket/manager.py:17`；A/B 的 `connect`/`broadcast` 仍以 int 调用 | 仅改类型注解不会改变运行时键；建议键类型放宽为 int / str，或在路由边界统一转 str，并回归 A/B 实时日志 |

## 6. 本轮做得好的部分

| 内容 | 说明 |
|------|------|
| 启动清理 + 活跃注册表 + `started_time` 迁移 | 真正解决了僵尸 running 的根因，方案可落地 |
| 停止语义（只取消自有执行 + 可打断 + 终态收尾） | 第一轮 P0-6 闭环，边界考虑到位 |
| 顶栏独立「自动化 N」指示器 | 没有破坏现有胶囊语义，是正确的取舍 |
| 失败分级 + `partial` | 方向正确，只差空目录与失败重试两个边界 |
| 成功指标 / 范围外 / 异常清单 / 非功能 / 回滚 / 术语表 | 文档从「设计说明」提升为可评审的方案 |
| `check_dir` 必填 + 检测按钮 + 递归相对路径 | 抓住了第一轮 P0-4 的核心，只差数据来源定义 |
| 保留策略、`log_path`、`error_code`、`skipped_file_count` | 可观测性明显增强 |
| 分页 10/20/50、版本不写死、API 清理、文档同步范围 | 与项目规范对齐 |
| 决策记录与修订摘要 | 可追溯，便于第三轮核对 |

## 7. 建议的修订清单

| 计划位置 | 建议修改 | 优先级 |
|----------|----------|--------|
| §1.1 L31 + §2 L56/L66 + §10.1 L331 | 统一失败策略：区分「轮次失败（继续）」与「任务终止（致命）」；A/OpenList/网络归轮次失败，连续 3 次后终止；指标改为「3 轮内补偿成功率」 | P0 |
| §2 L59-61 + §4.1 | 增加持久化 `pending_files`（或 `last_failed_stage` + `missed_files` 重校验）：OpenList/A 失败后下一轮必须重新校验可见性，不能因新文件为 0 跳过 | P0 |
| §2 L56 + §10.1 L328 | 空目录/无视频 → `empty`/skip，不终止；`file_total>0 && success+skipped=0` 才按失败处理 | P0 |
| §2 L79 + §5 L220 + §14 RK-05 | 在 A/B `start_execution` 增加共享按任务启动闸门；或明确 FIFO 锁只防 C 内部并下调 RK-05 | P0 |
| §2 L58/L60 + §6 L235 | `check_dir` 定义为 B `remote_dir` 的精确映射，比对 `remote_name`；去掉递归，或给 `upload_file_record` 加 `remote_rel_path` | P0 |
| §4.1 L137-138 | 明确部分唯一索引建在 `automation_task.is_deleted=0`；补 `IntegrityError` → 400；批量/交换绑定校验 | P1 |
| §4.1 L161-162 + §3.2 L106 | run 生命周期：A 终态即结束；interval 归任务运行时；`stopping` 放 phase 或加入筛选；间隔中停止不产生 run | P1 |
| §4.1 + §5 L227 | 给 A/B 执行表加 `error_code`/`error_message`，C 才能区分 `B_CLOUD_ERROR`/`B_NO_PROGRESS` | P1 |
| §3.1 L93 + §6 L233 | 定义 `OPENLIST_REMOTE_PREFIX` 的存储（建议 `open_list_config` 新字段）与多挂载处理；`check-dir` 支持新建 | P1 |
| §3.4 L125 + §5 L229 | 增加每日定时清理；对齐 run 1000 条与日志 200 个的保留范围 | P1 |
| §4.2 L190 + 前端 | A `started_time` 迁移补 UI/排序/实时用时处理与回归用例 | P1 |
| §9 L300-301 | 删除引用检查覆盖批删与服务器删除；服务器删除时提示受影响的自动化任务 | P1 |
| §3.3 L118 + §8 L281 | 托盘通知改为模块级可注入通知器 + 线程安全调用；仅异常终止通知；网页红点定义未读存储 | P1 |
| §10.1 L326 | 修复表格并补全 `error_code` 枚举 | P1 |
| §11 | 补 P2-15 列出的测试场景 | P1 |
| §7 L252-255 | 统一 API 风格 | P2 |
| §14 RK-05/RK-09 | 按共享闸门与通知方案更新概率/影响 | P2 |

### 7.1 建议的失败策略矩阵（替换 §10.1 的现状）

| 场景 | 本轮结果 | 任务是否继续 | 指纹 | 通知/动作 |
|------|----------|--------------|------|-----------|
| A/B 任务或目录不存在、凭据失效、`check_dir` 不可访问 | fail（致命） | 停止 | 不提交 | 通知 + 修复后手动启动 |
| 本地无视频（`file_total=0`、`file_failed=0`） | empty / skip | 继续 | 提交（避免重复扫描空目录） | 不通知 |
| B 部分文件失败（`success+skipped>0`） | partial | 继续 A | 提交 + 失败文件列表 +「重试失败文件」入口 | 非致命通知 |
| B 全部文件失败（`file_total>0`、`success+skipped=0`） | fail（轮次） | 连续 3 次后停止 | 不提交 | 第 3 次通知 |
| OpenList 超时 / API 5xx | fail（轮次） | 继续 + 退避 | 不提交 | 第 3 次通知 |
| A 失败 / 取消（外部原因） | fail（轮次） | 继续 + 退避 | 不提交 | 第 3 次通知 |
| 连续 3 次轮次失败 | fail（致命） | 停止 | 不提交 | 通知 + 一键重新启动 |
| 用户停止 | cancelled | 停止 | 不提交 | 不通知（轻提示即可） |
| 进程重启 | fail（致命，启动清理） | 不恢复 | 保持 | 启动后提示 |

> 备注：区分「空目录」与「B 预扫描失败」依赖 R2-P1-2 的 `error_code`；若暂不加字段，C 无法仅凭计数区分两者，空目录修复会引入误判。

### 7.2 Run 生命周期建议

- run 从「建 run」到「A 终态 / 停止 / 致命」结束；**轮次间隔不属于 run**，属于任务运行时状态，`/active` 返回 `phase=interval` 与 `next_round_at`。
- `stopping` 作为 phase（`running + phase=stopping`）或短暂状态并在历史筛选中显示；不要既放进 status 又不放进筛选。
- 间隔中停止：只停循环，不需要给已结束的 run 写 `cancelled`；若希望留痕，可写一条 `task_stopped` 系统日志。

## 8. 结论与下一步

1. 本轮修订解决了第一轮最严重的两个根因（僵尸 running、停止语义），文档完整度也明显提升，值得肯定。
2. 但「补偿 vs 终止」是当前设计的核心矛盾；在它解决之前，P0-1/P0-2 的补偿路径无法成立。空目录误判、手动竞态、相对路径数据源同样会在真实环境暴露。
3. 建议按 §7 做一次**针对性修订**（5 项 P0 + §7 列出的 P1 项），然后做一轮只核对 P0 闭环的短评审；无需第三次全文重写。
4. 实施顺序仍按 ⓿ 前置 → ① 数据 → ② 配置 → ③ 引擎 → ④ 历史/文档；但 ⓿ 需新增两项：**A/B 执行表错误字段**、**A/B 共享按任务启动闸门**。

## 9. 附录：本文引用的代码事实

| 事实 | 代码位置 |
|------|----------|
| B 空目录返回 success、计数全 0 | `backend/app/business/uploader/execution_engine.py:240` |
| B 任一文件失败即返回 fail | `backend/app/business/uploader/execution_engine.py:381` |
| A/B `start_execution` 无按任务启动闸门 | `backend/app/business/openlist/service.py:876-936`；`backend/app/business/uploader/service.py:578-600` |
| A/B 执行表无 `error_message` / `error_code` | `backend/app/core/models/openlist/execution.py`；`backend/app/core/models/uploader/execution.py` |
| A 生成器只使用 `force` / `strm_only` | `backend/app/business/openlist/strm_generator.py:404` |
| A `is_incremental` 未传入生成器 | `backend/app/business/openlist/service.py:927` |
| 上传记录只有 `local_path` / `remote_name` | `backend/app/core/models/uploader/file_record.py:26-27` |
| `upload_task` 无 `is_deleted` | `backend/app/core/models/uploader/task.py` |
| `delete_server` 只软删服务器与目录 | `backend/app/business/openlist/service.py:521-534` |
| 托盘图标为函数局部变量 | `backend/app/desktop.py:295,344` |
| WS manager 键类型为 int | `backend/app/websocket/manager.py:17` |
| A 创建执行即写 `started_time` | `backend/app/business/openlist/service.py:806` |
| `init_db` 无 `CREATE INDEX` 迁移 | `backend/app/core/database.py:162-178` |
| A 历史排序/实时用时依赖 `started_time` | `frontend/src/views/schedule/TaskHistory.vue:67`；`RealtimeLog.vue:385` |

---

本方案为产品设计参考，具体实施请结合公司合规与法务要求确认。
