# 待定事项

> 本文档记录「已形成结论但尚未批准实施」的改动计划、待确认的取舍，以及被搁置的方案。
>
> - 状态说明：**待确认** = 已有建议方案，等用户批准；**已批准** = 已进入实施批次；**已否决** = 不再实施，保留原因备查。
> - 每项批准或否决后，更新 `状态` 与日期；实施完成并在 CHANGELOG 记录后，可整项删除或折叠进历史附录。
> - 基线：v4.19.3（`f725e46`）；相关方案见 [frontend-reuse-plan.md](frontend-reuse-plan.md)。

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
