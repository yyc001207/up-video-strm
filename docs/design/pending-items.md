# 待定事项

> 本文档记录「已形成结论但尚未批准实施」的改动计划、待确认的取舍，以及被搁置的方案。
>
> - 状态说明：**待确认** = 已有建议方案，等用户批准；**已批准** = 已进入实施批次；**已否决** = 不再实施，保留原因备查。
> - 每项批准或否决后，更新 `状态` 与日期；实施完成并在 CHANGELOG 记录后，可整项删除或折叠进历史附录。
> - 基线：v4.19.6（`v4.19.5` tag 之后）；相关方案见 [frontend-reuse-plan.md](frontend-reuse-plan.md)。

## P-001 日志显示框与日志管线抽取

- **状态**：待确认（2026-11-07）
- **来源**：讨论「日志打印框适不适合抽出组件」（2026-11-07）
- **结论**：`LogViewer.vue` 已经是一个合格且应保留的组件；真正重复且值得抽的是环绕它的类型、过滤与追加逻辑。
- **保留 `LogViewer.vue` 的依据**（406 行，3 个运行详情页共用，props 4 个 + emit 1 个）：
  1. 终端渲染（固定深色样式、时间列/级别列、消息不换行横向滚动）；
  2. `maxLines` 只渲染最近 N 行，避免长时间运行后 DOM 膨胀；
  3. 跟随滚动为受控行为：用户上滚时暂停并浮出「N 条新日志 ↓」胶囊；
  4. 右键复制单行/全部、行级 `LEVEL_LABELS`。
  以上均属非平凡决策，且 3 个调用点各自净省 100 行以上，不是转发壳组件。
- **明确的「不抽」**（避免重复此前的过度抽取）：
  - 不把级别/关键字筛选移进 `LogViewer`（组件只渲染已过滤行；工具栏的「N 行」计数在组件外）；
  - 不抽「工具栏 + 日志区」外壳（三页控件存在差异：自动追更页未连接时禁用控件，A/B 页按钮不同；属于同构转发）；
  - `CONNECTION_META` / `PHASE_LABELS` 不在本项处理，归入 `utils/status.ts` 的独立批次。
- **实测重复点**（v4.19.3）：
  | 重复项 | 现有副本 |
  | --- | --- |
  | `LogLine` 接口 | `frontend/src/components/LogViewer.vue:6`、`frontend/src/views/automation/RealtimeLog.vue:26`、`frontend/src/views/schedule/RealtimeLog.vue:35`、`frontend/src/views/upload/RealtimeLog.vue:28` |
  | 级别 + 关键字过滤、`filteredLines` | `views/automation/RealtimeLog.vue:123`、`views/schedule/RealtimeLog.vue:255`、`views/upload/RealtimeLog.vue:121` |
  | 追加日志 + `MAX_LOG_LINES` 截断 | `views/automation/RealtimeLog.vue:151-155`、`views/schedule/RealtimeLog.vue:325-334`、`views/upload/RealtimeLog.vue:178-187` |
  | `autoScroll` ref 与清屏 | 三个 RealtimeLog 页各一份 |
- **建议抽出（不改任何交互与样式）**：
  1. `frontend/src/types/log.ts`：`LogLine { seq, level, ts?, message }` 作为唯一来源，`LogViewer` 与三个页面统一导入；
  2. `frontend/src/utils/log.ts`：`filterLogLines(lines, { level, keyword })` 纯函数（无 Vue/DOM/store），单测覆盖级别匹配、关键字大小写、空关键字；
  3. `frontend/src/composables/useLogLines.ts`：`useLogLines({ maxLines })` → `{ lines, append(line), clear() }`，接管追加与截断，页面删除 `push + splice` 副本。
- **待确认问题**：
  1. 是否批准上述 3 个文件的抽取；
  2. 实施批次：与 `frontend-reuse-plan.md` 的 P0（纯函数批次）同批提交，还是独立一个提交 + PATCH 版本；
  3. `autoScroll` 是否随 `useLogLines` 一起返回（会稍增 composable 表面积，但可再消 3 处 ref 与清屏逻辑）。
- **影响范围**：纯前端；3 个运行详情页与 1 个通用组件；无后端接口、无依赖变更；验收以「三页行为与 DOM 完全不变 + `npm test`/`vue-tsc`/`npm run build` 通过」为准。

## P-002 自动追更启动后运行详情误报「本轮执行已结束」

- **状态**：已实施（2026-11-08，v4.19.7）
- **来源**：用户实测「启动自动追更任务后跳转到运行详情，页面提示『本轮执行已结束』」（2026-11-07）
- **现象**：点击「启动」后立即跳到 `/automation/realtime?task_id=X`，页面短暂显示后提示「本轮执行已结束，可前往『运行记录』查看日志」，然后断开连接；任务本身仍在后台按轮次运行。
- **根因分析**：
  1. `frontend/src/views/automation/RealtimeLog.vue:176` 的 `handleRoundEnd()` 对任何 `status` 终态帧都视为「本轮结束」并 `disconnect()`；
  2. 后端 WS 连接建立时会回放该任务最近 200 帧（`execution_logger.recent_frames`），其中可能包含**上一轮**遗留的终态 `status` 帧 → 页面一连上就误判结束；
  3. 设计上「一轮结束即断开」，循环任务下一轮开始时页面不会自动续订，因此用户看不到后续轮次，只能手动点「重新连接」。
- **实施方案**（v4.19.7 已完成）：
  1. 回放帧统一标记 `replay: true`（`backend/app/api/automation.py` 的 `_replay_frames`），前端 `onFrame` 直接丢弃；
  2. 终态帧透传 `error_code / error_message / missed`（`execution_engine._finish_run`），页面无需再查库即可展示失败原因；
  3. 页面改为「任务 / 本轮 / 连接」三层状态并列（`frontend/src/utils/automationState.ts` + 单测），单轮终态后不断开，显示「下一轮 HH:mm:ss」并保持连接；任务停止才断开；断线且任务仍运行时自动重连（1s/3s/5s，最多 5 次）；
  4. 历史日志改为「查看最近一轮」显式加载，不再自动回放。
- **验收**：见 `docs/rules/frontend.md` 自动化四页与 `manual/用户手册.md` 3.13.3；`npm test` / `vue-tsc` / `npm run build` / 后端全量测试通过。

## 变更记录

- 2026-11-07：新建 P-002（自动追更启动后运行详情误报本轮结束）。
- 2026-11-08：P-002 已实施（v4.19.7），保留记录备查。
