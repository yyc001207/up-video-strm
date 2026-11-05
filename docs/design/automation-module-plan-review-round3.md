# 自动化任务模块设计计划 · 第三轮（最后一轮）短评审

> 状态：**有条件通过**（本文只记录评审意见；**未修改** [automation-module-plan.md](automation-module-plan.md) 原文，**未改动**任何代码）
>
> 评审对象：[automation-module-plan.md](automation-module-plan.md)（commit `6a5e976`，版本 4.11.0，521 行）
>
> 前两轮：[第一轮](automation-module-plan-review.md)（`bf048d5` / `21755c2`）· [第二轮](automation-module-plan-review-round2.md)（`d18cdec` / `63030f6`）
>
> 评审日期：2026-11-06
>
> 本轮范围：只核对第二轮 5 项 P0 是否闭环，以及修订是否引入新的阻断；不再全文重审。

## 1. 结论

| 项目 | 结果 |
|------|------|
| 第二轮 5 项 P0 | **5/5 设计闭环**（P0-2/P0-4 带实施条件） |
| 本轮残余阻断 | **1 项 P0**：pending 没有清除/忽略出口 |
| 本轮残余重要项 | **6 项 P1**：pending 轮指纹、A 目录执行闸门、TASK_BUSY、失败计数复位、stage_timeout 收尾、OpenList 刷新策略 |
| 是否可进入实施 | **补完 1 项 P0 + 6 项 P1 的书面口径后可开工**，不需要第四轮评审 |
| P2 | 7 项，可作为实施备注 |

**结论：设计已经达到可实施水平，5 项 P0 的修订方向都正确；但 `pending_files` 目前只有「写入」和「A 成功后清空」，没有人工清除/忽略入口，一旦某个文件永久不可见，任务会陷入「3 次失败→终止→手动重启→仍失败」的死循环。这是最后一个必须补的阻断项。**

## 2. 第二轮 5 项 P0 闭环核对

| 第二轮 P0 | 本轮修订 | 结论 |
|-----------|----------|------|
| R2-P0-1 补偿 vs 终止 | §2 L71-72、§10.1 L347-364：轮次失败（A/OpenList/网络/B 全失败/空闲超时）退避重试 3 次，配置错误立即终止；指标改为 3 轮补偿成功率 ≥95% | **已闭环**。失败分级、连续计数、指标口径一致 |
| R2-P0-2 补偿绕过可见性校验 | §2 L51/L79、§4.1 L151：`pending_files` 持久化；pending 非空时优先校验；OpenList 可见 + A 成功后才清空 | **已闭环**（需补 P0-1 清除出口 + P1-1 指纹口径） |
| R2-P0-3 空目录误致命 | §2 L55/L61、§10.1 L350：本地无视频不建 run/空轮；`file_total=0 && failed=0` 不算失败 | **已闭环**（P2-1 语义仍可再明确） |
| R2-P0-4 手动竞态 | §2 L80、§9 ⓿-3：A/B `start_execution` 共享启动闸门，入队前注册，400 拒绝 | **已闭环**（需补 P1-2 目录执行、P1-3 TASK_BUSY） |
| R2-P0-5 相对路径无数据源 | §3.1 L97、§6 L247-251：`check_dir` 精确映射、按 `remote_name` 比对、去递归 | **已闭环**。与 B 的平铺上传模型一致 |

补充确认：第一轮的 P0-2（僵尸 running）、P0-6（停止语义）仍保持闭环；本轮修订没有回退它们。

## 3. 残余 P0（1 项，必须补）

### P0-1 `pending_files` 没有清除/忽略出口，会形成永久死循环

**证据**：

- §3.1 L101：pending 只读展示 + 「查看待校验文件」，没有清除操作。
- §2 L69：pending 只在「A 成功」后清空。
- §2 L59：pending 非空时跳过 B，直接校验 pending。
- §10.1 L358：连续 3 次轮次失败 → 终止任务；**pending 保留**。
- §7 L273：`reset-fingerprint` 只清指纹，不清 pending。

**触发场景**：某个文件已上传到 123 云盘，但因路径映射错误、云端删除、重命名冲突或 OpenList 永久不索引，在 `check_dir` 中永远不可见。流程会：

```text
pending 非空 → 下一轮跳过 B → 校验 pending → 超时 → 轮次失败
→ 连续 3 次 → 任务终止（pending 保留）
→ 用户手动重启 → pending 仍非空 → 再次校验 → 再次超时 → 再次终止
```

用户没有 API/UI 可以清掉这个文件，只能删掉自动化任务重建或改数据库；这恰好违背「无人值守可恢复」的目标。

**建议改法**：

- 新增 `POST /tasks/{id}/pending/clear`（body 可选 `remote_names`，空表示全部），UI 在「查看待校验文件」抽屉里提供「忽略选中 / 全部清除」，二次确认写明「这些文件将不再等待 OpenList 校验，也不会自动重试」。
- 清除后写一条系统日志与 WS 事件；若 pending 因此为空，下一轮按指纹正常走 B/A。
- 可选增强：同一文件连续 N 次（建议 3 次）校验失败时自动移出 pending 并通知，避免完全依赖人工；但 v1 至少要有手动出口。
- 同步更新 §3.1、§7、§11、§12.1（新增决策「pending 可清除」）。

## 4. 残余 P1（6 项，实施前写成明确口径）

| 编号 | 问题 | 证据 | 建议 |
|------|------|------|------|
| P1-1 | pending 轮没有定义指纹计算（伪代码只在 else 分支算 F），但 A 成功后要「提交指纹」——提交哪一版未定义 | §2 L51-52（pending 非空跳过指纹判定）；L54（F 只在 else 分支计算）；L69（A 成功提交指纹）；L77（指纹 = 上次完整成功） | 每轮开始**始终计算 F**（stat 很便宜），pending 只影响「是否跳过本轮」；A 成功后提交当前 F。或在写 pending 时保存 `pending_fingerprint`，成功时提交它。不要依赖已丢失的 F |
| P1-2 | A 的目录执行（`task_id=0`）会被共享闸门误伤 | §2 L80、§9 ⓿-3 用 `is_task_active(task_id)`；A 的目录执行 `task_id=0`（`openlist/service.py:846`/`876`） | 闸门只对 `task_id > 0` 生效；目录执行按 `execution_id` 或跳过闸门，避免所有目录执行互相排斥 |
| P1-3 | `TASK_BUSY`（启动闸门 400）在 C 侧没有处理口径 | §10.1 L364 有 `TASK_BUSY` 枚举，但矩阵 L347-362 没有对应行；§5 L238 只说空闲检查 | C 调 `start_execution` 收到 400 时应回到「等待空闲」并重试到 `idle_wait_timeout`，而不是记 `INTERNAL_ERROR` 或直接累计失败；补矩阵行与测试 |
| P1-4 | `consecutive_failures` 在手动重启/重试失败文件时未复位 | §4.1 L155、§2 L71、§10.1 L358、§3.2 L113 | 手动 `start` / `retry-failed` 时把 `consecutive_failures` 置 0；否则第 3 次失败终止后重启，第一次新失败就变成第 4 次，立即再终止 |
| P1-5 | `stage_timeout` 的 30s grace 后执行可能仍在跑，形成「run 已失败 + 执行仍活跃」 | §5 L239；§10.1 L357；§9 ⓿-3 闸门 | 明确 grace 后策略：再请求取消 / 标记 orphan / 等引擎 `finally`；在活跃注册表未释放前，下一轮闸门会 400。补「超时不配合」测试 |
| P1-6 | OpenList 首次 `refresh=True`、其后 `False`，可能永远读旧缓存；bootstrap 无 pending 时 A 直接跑 | §6 L252；A 生成器 `list_files` 默认 `refresh=False`（`strm_generator.py:245`）；§2 L65（pending 为空跳过校验）、L78（无新增仍执行 A） | 每个退避步（15/30/60s）至少一次 `refresh=True`，或每 3 次轮询刷新一次；bootstrap/无 pending 时先对 `check_dir` 做一次 `refresh=True` 预热，再执行 A，避免 A 读到旧缓存 |

## 5. P2（实施备注）

| # | 问题 | 位置 | 建议 |
|---|------|------|------|
| P2-1 | 空轮语义有「不建 run」和「run success(empty)」两种写法 | §2 L55 vs L61；§10.1 L350 | 二选一：本地无视频 → 不建 run；B 执行后 0 文件 → run success + `new_file_count=0`，历史显示「本轮无文件」 |
| P2-2 | `automation_run.phase` 仍含 `interval`，但 §2 L47 说 interval 不属于 run | §4.1 L173 vs §2 L47/L85 | 从 run.phase 删除 `interval`，只放在 `/active` 的任务运行时状态；或注明该值仅用于 `/active` |
| P2-3 | RK-10 写「DB 与指纹一起事务提交」，实际 pending 在 B 后写、指纹在 A 成功后写 | §14 L516 | 改为「pending 在 B 成功后持久化；指纹在 A 成功后提交；两者不要求同一事务」 |
| P2-4 | `retry-failed` 的校验条件未定义 | §7 L274；§3.2 L112 | 只允许 `status=partial`、任务未运行、pending 为空；调用时重置 `consecutive_failures`；否则返回 400 |
| P2-5 | 错误矩阵缺 `B_CLOUD_ERROR`、`TASK_BUSY` 行；`A_CANCELLED` 外部取消仍重试 3 次 | §10.1 L347-364 | 补两行；明确外部取消 A 是「轮次失败」还是「停止任务」，并在 UI 提示 |
| P2-6 | OpenList 校验未明确只匹配文件 | §6 L251 | 只匹配 `is_dir=False` 的条目；`content=None` 视为空目录；同名目录不应当作文件命中 |
| P2-7 | 手动启动在 pending 非空时不会跑 B，「强制一轮」语义不完整 | §2 L78、L109、L59 | 文案改为「优先处理待校验文件」；或允许手动启动选择「先清 pending 再跑 B」 |

## 6. Go / No-Go

**Go（有条件）**：补完以下内容即可进入实施，不需要第四轮评审：

1. **P0-1**：pending 清除/忽略 API + UI + 审计日志。
2. **P1-1**：pending 轮的指纹计算与提交口径。
3. **P1-2/P1-3**：A 目录执行不误伤、`TASK_BUSY` 回到等待。
4. **P1-4/P1-5**：手动启动复位失败计数、stage_timeout 后活跃执行的处理。
5. **P1-6**：OpenList 周期刷新 + bootstrap 预热。

P2 可写进实施任务说明，不阻塞开工。

## 7. 代码事实核对（本轮新增引用）

| 事实 | 代码位置 |
|------|----------|
| B 空目录返回 success、计数全 0 | `backend/app/business/uploader/execution_engine.py:240` |
| A 目录执行 `task_id=0` | `backend/app/business/openlist/service.py:846`、`:876-936` |
| A 生成器 `list_files` 默认不刷新 | `backend/app/business/openlist/strm_generator.py:245` |
| A/B `start_execution` 当前没有按任务闸门 | `backend/app/business/openlist/service.py:876-936`；`backend/app/business/uploader/service.py:578-600` |
| A/B 执行表当前无 `error_code`/`error_message`（前置改动新增） | `backend/app/core/models/openlist/execution.py`；`backend/app/core/models/uploader/execution.py` |

---

本方案为产品设计参考，具体实施请结合公司合规与法务要求确认。
