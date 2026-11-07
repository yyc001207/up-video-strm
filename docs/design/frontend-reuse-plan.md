# 前端复用重构方案（纯逻辑优先）

> 状态：P0–P1 已实施（v4.19.5）；P2–P3 待实施
> 基线：v4.19.3（`43975d9`）
> 替代：已删除的 `frontend-component-extraction-plan.md`（该方案被判定不合格，原因见 §1，本方案不沿用其任何组件设计）

## 0. 结论

1. **只抽两类东西**：纯函数（无 Vue、无 DOM、无 store/api 依赖）与 headless 组合式函数（只封装状态机语义，不接管请求与文案）。
2. **组件默认不抽**。只有「承载非平凡决策 + 至少 3 处使用 + 使用方净减少代码」三个条件同时满足才允许抽；同构转发第三方组件 props 的一律否决。
3. **本方案不改任何交互**：详情页切换、弹窗/抽屉形态、状态组件样式全部保持现状；交互变更另立提案、单独评审。
4. **成功标准是「重复实现归零」，不是行数下降**：同一逻辑出现第二份实现即视为回归。
5. 复用价值集中在 `utils/` 与 `composables/`，预计净减少约 400–500 行页面代码；不新增任何 UI 组件、不新增目录层级。

## 1. 上一版为什么不合格（复盘）

| 问题 | 具体表现 | 本方案的修正 |
| --- | --- | --- |
| 为组件化而组件化 | `EntityFormDrawer` 只转发 `el-drawer` 的 `modelValue/size/title/saving`；`ConfigSectionCard` 只转发 `el-card`；`ExecPanel` 只转发容器样式 | 禁止同构转发；组件必须自带决策（§2.3） |
| 抽象没消除重复 | 三个执行页的业务编排、筛选状态、轮询语义仍各自一份；抽掉的只有 CSS 与骨架，却新增 4 套目录、20+ 文件、大量 props/slots 协议 | 只抽纯逻辑；页面编排保持页面所有（§2.2 / §8） |
| 以「纯重构」掩盖交互变更 | D3（整页详情→抽屉）、D4（弹窗→抽屉）、D5（状态组件合并）改变了操作习惯，却与纯逻辑收敛混在同一优先级 | 本方案不含交互变更；如确需变更，单独列出并等确认（§8） |
| 缺删除标准与验收口径 | 用「行数下降」当结构改善证据；没规定抽象失败如何否决 | 定义否决条款与 grep 级验收（§2.4 / §6） |
| 可复用性判断错误 | 真正值得复用的只有格式化、日期边界、分页、选择、轮询这类纯函数与无 DOM 逻辑；大组件抽取风险最高、收益最低 | 本方案审批只有纯函数与少量 composable（§3 / §4） |

## 2. 判据（批准后写入 `docs/rules/frontend.md`）

### 2.1 纯函数（鼓励抽）

- 不 import Vue / DOM / router / store / api；输入输出都是纯数据。
- 同一逻辑出现第 2 份实现即可合并；合并后原实现必须删除。
- 必须有单元测试（固定输入、边界值、时区/空值）。
- 位置：`frontend/src/utils/<domain>.ts`。

### 2.2 组合式函数（谨慎抽）

- 只封装「状态机语义」：启动/停止、跳过、去重、清理；不封装业务请求、路由跳转、提示文案。
- 参数 ≤ 3 个，返回值 ≤ 8 个；不 import store；不接收组件实例。
- 页面仍负责：取数、错误处理、文案、业务校验。
- 必须先在一页试点，diff 证明页面变短且行为等价后再推广。

### 2.3 组件（默认不抽）

必须**同时**满足：

1. 至少 3 处使用，且语义一致（不是「长得像」）；
2. 内部承载非平凡决策：状态→视觉映射、格式化→文本、空态→行动、交互→事件；
3. 删除该组件后，每个使用点至少多写 10 行；
4. props ≤ 5、slots ≤ 2；
5. 不得只是把某个第三方组件的 props 原样透传（`v-bind="$attrs"` + 同名 props 直接否决）。

已存在且满足上述条件的组件维持现状：`StatusDot`（状态→颜色/动效）、`EmptyState`（标题/说明/行动）、`LogViewer`（日志渲染与滚动策略）、`BulkBar`（批量条语义）。

### 2.4 否决与删除

- 评审只要发现「同构转发 / 只有布局 / 只有一个使用点」→ 撤回该批，不留「以后可能有用」的文件。
- 抽出的文件必须让原实现被删除；后续再出现同逻辑的第二份实现 → 评审阻断。
- 单批规模：≤ 3 个新文件、≤ 15 个调用点；超出就拆批，避免一次改太多无法回归。

## 3. 现状盘点与决策（v4.19.3 实测）

| 重复点 | 证据 | 份数 | 决策 |
| --- | --- | --- | --- |
| `triggerText`（谁启动的） | `views/schedule/Execution.vue:164`、`views/schedule/TaskHistory.vue:64`、`views/upload/Execution.vue:120`、`views/upload/TaskHistory.vue:97` | 4 | 抽到 `utils/format.ts` |
| `countText`（成功/总数） | `views/schedule/Execution.vue:159`、`views/schedule/TaskHistory.vue:59`、`views/upload/TaskHistory.vue:83` | 3 | 抽到 `utils/format.ts` |
| `durationText` / `formatDuration` | `views/schedule/RealtimeLog.vue:195`、`views/schedule/TaskHistory.vue:50`、`views/upload/TaskHistory.vue:74` | 3 | 抽到 `utils/format.ts` |
| `PHASE_LABELS`（自动追更阶段） | `views/automation/Execution.vue:56`、`views/automation/RealtimeLog.vue:44`、`views/automation/TaskHistory.vue:38` | 3 | 抽到 `utils/status.ts` |
| `CONNECTION_META`（WS 连接态文案） | `views/automation/RealtimeLog.vue:37`、`views/schedule/RealtimeLog.vue:78`、`views/upload/RealtimeLog.vue:44` | 3 | 抽到 `utils/status.ts` |
| 执行进度比例 | `stores/running.ts` 私有 `ratio()`；`views/Today.vue:69-70`、`views/Today.vue:87-89` 各算一遍；`views/upload/Execution.vue:116` 自己拼计数 | 3 | 抽到 `utils/execution.ts`，store 与页面共用 |
| 日期范围边界（北京时间 00:00:00 / 23:59:59） | `views/schedule/TaskHistory.vue:76-82`、`views/upload/TaskHistory.vue:115-117` | 2 | `utils/date.ts` 增 `toBeijingDayRange()` |
| 轮询 `setInterval` | 9 处：`components/TopBar.vue:19`、`App.vue:83`、三个 `Execution.vue`、三个 `RealtimeLog.vue`、`views/config/GlobalConfig.vue:349` | 9 | `composables/usePolling.ts`，先 2 处试点 |
| 危险操作确认 `ElMessageBox.confirm` | 10 个文件共 18 处 | 18 | `composables/useConfirmAction.ts`（只统一按钮文案与 danger 样式） |
| `openLogDir` 调用与 catch | 7 个文件共 20 处引用 | 20 | `composables/useLogDir.ts`（统一 catch 文案，不封装 desktop API） |
| 客户端分页 | `views/schedule/TaskManage.vue`、`views/schedule/TaskHistory.vue`、`views/upload/TaskConfig.vue`、`views/upload/RenameRules.vue`、`views/upload/TaskHistory.vue` | 5 | `composables/useClientPagination.ts` |
| 表格选择 + 全选语义 | 三个任务页、三处「正在执行」表 | 6 | `composables/useSelection.ts`（只存 id 集合与全选规则） |
| 字节格式化 | `views/upload/TaskHistory.vue:463` | 1 | 不抽（未到 2 处） |
| `error_code` 文案 | 各历史页直接展示原值 | — | 不抽（后端错误码仍会扩展，前端映射会过期） |
| 复制文本（含降级） | `components/LogViewer.vue` | 1 | 不抽，观察是否出现第二处 |
| `localStorage` 读写 | `AppSidebar.vue`、`App.vue`、`stores/theme.ts` | 8 处引用 | 可选：`utils/storage.ts` 统一前缀，P3 再评估 |

> 复现命令见附录 A；引用数会随代码变化，实施每一批前重新跑一遍。

## 4. 目标产物与契约

### 4.1 `frontend/src/utils/format.ts`

```ts
export interface TriggerLike {
  trigger_source?: string | null
  trigger_name?: string | null
}

/** 谁启动的：automation → `自动化 · 名称`，其余 → `手动`。 */
export function triggerText(row: TriggerLike): string

/** 成功/总数：total 为 0 或缺失 → `—`。 */
export function countText(success: number, total: number): string

/** 时长：65 → `1 分 5 秒`；空/负数/NaN → `—`。 */
export function durationText(seconds: number | null | undefined): string

/** 计时器：65 → `01:05`，超过 1 小时 → `1:01:05`。 */
export function clockText(seconds: number): string
```

替换点：§3 表中对应页面；替换后删除页面内本地实现，不保留同名包装。

### 4.2 `frontend/src/utils/status.ts`

```ts
import type { WsState } from '@/utils/ws'
import type { AutomationRunStatus } from '@/types/automation'

export type StatusTone = 'success' | 'warning' | 'danger' | 'info'

/** 自动追更轮次阶段文案（唯一一份）。 */
export const PHASE_LABELS: Record<string, string>

/** WS 连接状态文案与色调（唯一一份）。 */
export const CONNECTION_META: Record<WsState, { label: string; tone: StatusTone }>

/** 自动追更轮次状态文案与标签色。 */
export const AUTOMATION_RUN_STATUS_LABELS: Record<AutomationRunStatus, string>
export const AUTOMATION_RUN_TAG_TYPES: Record<AutomationRunStatus, StatusTone>

/** STRM/上传执行状态（两者取值相同，文案不同处由调用方传 module）。 */
export const EXECUTION_STATUS_LABELS: Record<'running' | 'success' | 'fail' | 'cancelled', string>
export const EXECUTION_TAG_TYPES: Record<'running' | 'success' | 'fail' | 'cancelled', StatusTone>
```

说明：三个页面里与「筛选选项」绑定的 `STATUS_OPTIONS` 只在各自页面用一次，**保留在页面**，本方案不合并。

> **P0 实施调整（v4.19.4）**：按 §2.1「同一逻辑出现第 2 份实现才合并」复测后，`EXECUTION_STATUS_LABELS` / `EXECUTION_TAG_TYPES` / `AUTOMATION_RUN_TAG_TYPES` 实际各只有 1 份副本，未落库（仍留在页面）；`AUTOMATION_RUN_STATUS_LABELS` 有 2 份，已抽取。自动化「运行记录」页的阶段用词与「开始执行 / 运行详情」不同，为保持文案逐字不变，`utils/status.ts` 同时提供 `PHASE_LABELS` 与 `PHASE_LABELS_HISTORY`。

### 4.3 `frontend/src/utils/execution.ts`

```ts
/** 0–100 的整数百分比；分母缺失/为 0 → null。 */
export function percentOf(part: number, total: number | null | undefined): number | null

/** STRM 执行进度：video_success_count / video_total_count。 */
export function scheduleProgress(exec: { video_success_count: number; video_total_count: number }): number | null

/** 上传执行进度：(file_success + file_skipped) / file_total。 */
export function uploadProgress(exec: {
  file_success: number
  file_skipped: number
  file_total: number
}): number | null
```

接入：`stores/running.ts` 删除私有 `ratio()` 改用 `percentOf`；`views/Today.vue` 改用 `scheduleProgress/uploadProgress`；`views/upload/Execution.vue` 的 `fileCountText` 改用 `countText`。

### 4.4 `frontend/src/utils/date.ts`（追加）

```ts
/** 时间范围 → 北京时间当日边界毫秒：开始日 00:00:00、结束日 23:59:59。 */
export function toBeijingDayRange(
  range: readonly [string, string] | null | undefined
): { startMs: number; endMs: number } | null
```

接入：`schedule/TaskHistory.vue`、`upload/TaskHistory.vue`；`automation/TaskHistory.vue` 直接传 `YYYY-MM-DD` 字符串，不改。

### 4.5 `frontend/src/composables/usePolling.ts`

```ts
export interface UsePollingOptions {
  interval?: number // 默认 5000
  immediate?: boolean // 默认 false
  visibleOnly?: boolean // 默认 true：document.hidden 时跳过
}

/** 返回 start/stop/tick；同一时刻只有一条定时器；上一轮未完时跳过本轮；组件卸载自动 stop。 */
export function usePolling(
  task: () => void | Promise<void>,
  options?: UsePollingOptions
): { start: () => void; stop: () => void; tick: () => Promise<void> }
```

试点：`App.vue`（运行数 30s，保持「页面隐藏跳过」）与 `views/schedule/Execution.vue`（正在执行 5s，保持旧实现「隐藏时仍刷新」即 `visibleOnly: false`）先改；验证无重叠请求后再推广到其余 7 处。

### 4.6 `frontend/src/composables/useConfirmAction.ts`

```ts
export interface ConfirmDangerOptions {
  title: string
  message: string
  confirmText?: string // 默认「确定」
  cancelText?: string // 默认「取消」
}

/** 统一 type=warning + danger 主按钮；返回是否确认。 */
export function useConfirmAction(): {
  confirmDanger: (options: ConfirmDangerOptions) => Promise<boolean>
}
```

只替换 `ElMessageBox.confirm(...)` 的调用形态，**标题与正文文案一律由页面传入并保持原文**。

### 4.7 `frontend/src/composables/useLogDir.ts`

```ts
export type LogDirKind = 'openlist' | 'upload' | 'automation'

/** 打开日志文件夹；带重入保护，失败提示沿用后端文案（拦截器展示）。 */
export function useLogDir(kind: LogDirKind): { open: () => Promise<void> }
```

只统一 catch 与提示，`desktopApi.openLogDir` 仍在函数内调用；页面不再各写 try/catch。

### 4.8 `frontend/src/composables/useClientPagination.ts`

```ts
/** source 为已过滤列表；pageSize 默认 20；筛选项变化由页面调用 reset()。 */
export function useClientPagination<T>(
  source: Ref<T[]>,
  options?: { pageSize?: number; sizes?: number[] }
): {
  page: Ref<number>
  pageSize: Ref<number>
  sizes: number[]
  total: ComputedRef<number>
  pagedItems: ComputedRef<T[]>
  reset: () => void
}
```

接入 §3 的 5 处客户端分页；服务端分页页面（自动化任务/运行记录）不改。

### 4.9 `frontend/src/composables/useSelection.ts`

```ts
/** 只维护 id 集合与全选规则；与 el-table 的 selection-change 由页面用 set() 同步。 */
export function useSelection<T>(options: {
  items: () => T[]
  getId: (item: T) => number
  isLocked?: (item: T) => boolean
}): {
  selectedIds: Ref<number[]>
  count: ComputedRef<number>
  allSelected: ComputedRef<boolean>
  toggle: (item: T) => void
  toggleAll: () => void
  set: (ids: number[]) => void
  clear: () => void
}
```

页面仍负责：请求数据、全选后的批量操作、确认弹窗、清空 `el-table` 视觉选择（`tableRef.value?.clearSelection()`）。

### 4.10 可选（不随本方案强制）

- `composables/useEntityForm.ts`：6 个表单重复 `visible/saving/editingId/form/openCreate/openEdit/save`。风险是「表单壳」再次变成中间商，因此只在试点页删除 ≥40 行且校验规则仍留在页面时才保留。
- `utils/storage.ts`：统一 `up-video-strm-*` 前缀与 JSON 读写，8 处引用，放 P3 评估。

## 5. 批次与顺序

| 批次 | 内容 | 验证 | 交付物 |
| --- | --- | --- | --- |
| P0 | `utils/format.ts`、`utils/status.ts`、`utils/execution.ts`、`utils/date.ts` 追加；删除对应页面本地实现 | 新增 vitest（node 环境）纯函数单测；`vue-tsc`；`npm run build` | 4 个 utils 文件 + 测试 + 页面替换 |
| P1 | `usePolling`、`useConfirmAction`、`useLogDir` 各在 1 个页面试点 | 试点页手工回归（不重复发请求、切后台暂停、确认弹窗文案不变、日志目录失败提示） | 3 个 composable + 3 个试点页 |
| P2 | 铺开剩余调用点：轮询 9 处、确认 18 处、日志目录 20 处；`useClientPagination` 5 处、`useSelection` 6 处 | `vue-tsc`、`npm run build`、逐页回归清单 | 页面 diff |
| P3 | 评估 `useEntityForm`、`utils/storage` 是否达到 §2 判据；未达标则明确否决并记录 | 达标才实施 | 结论记录 |

> **P0 已完成（v4.19.4）**：4 个 utils 文件与 24 个单测落地，页面/store 本地实现已删除并通过 §6 grep 断言。
>
> **P1 已完成（v4.19.5）**：`composables/usePolling.ts`、`useConfirmAction.ts`、`useLogDir.ts` 落地（新增 12 个单测，纯函数与组合式函数共 36 个）；试点接入 `App.vue`（运行数 30s）、`views/schedule/Execution.vue`（正在执行 5s）、`views/upload/TaskConfig.vue`（两个删除确认）、`views/schedule/TaskHistory.vue`（日志文件夹）；三个入口的旧实现（`setInterval` / `ElMessageBox.confirm` / `desktopApi.openLogDir` + 各写 catch）在试点页已删除，其余调用点留待 P2 铺开。

每批独立 commit；文档（`docs/rules/frontend.md` 判据与目录）随代码提交更新；每批交付前跑 `vue-tsc`、`npm run build`、`vitest`。

## 6. 验收（每批都必须全绿）

**代码级断言（grep）**

- `function triggerText|const triggerText` → 0 处；`countText`、`durationText` 定义仅在 `utils/format.ts`。
- `PHASE_LABELS:`、`CONNECTION_META:` 仅在 `utils/status.ts`。
- `setInterval(` 仅在 `composables/usePolling.ts`。
- `ElMessageBox.confirm(` 仅在 `composables/useConfirmAction.ts`。
- `openLogDir(` 仅在 `composables/useLogDir.ts`（`api/desktop.ts` 定义除外）。
- 客户端分页不再出现 `(page - 1) * pageSize` + `slice(` 的手写组合。

**行为级断言**

- 交互、文案、视觉与 v4.19.3 完全一致（唯一允许的差异是代码组织）。
- 轮询：页面隐藏时暂停；上一轮未完不叠加请求。
- 确认弹窗：标题、正文、按钮文案逐字一致。
- 日志目录：非 Windows 或接口失败时的提示文案一致。

**否决条款**

- 若某批需要新增组件、新增 props/slots 协议，或删除后的代码量没有减少 → 该批撤回。
- 若发现同一逻辑仍有第二份实现 → 该批不算完成。

## 7. 风险与对策

| 风险 | 对策 |
| --- | --- |
| 轮询迁移改变刷新节奏 | 先 2 处试点，保留原 `interval`/`immediate` 语义；对比网络面板请求间隔 |
| `useSelection` 与 `el-table` 视觉选择不同步 | composable 只存 id；清空由页面调用 `tableRef.value?.clearSelection()` |
| 确认弹窗漏掉 `await` 语义 | `vue-tsc` + 逐页手工点一次取消/确定 |
| 日期边界时区差异 | 单测固定北京时间样例（跨月末、跨年） |
| 纯函数合并时把页面差异抹平 | 差异参数显式化（如 module 文案由调用方传），不猜默认值 |

## 8. 明确不做（写进评审清单）

- 不抽布局壳：`ExecutionWorkbench`、`LogMonitorLayout`、`ExecPanel`、`ConfigSectionCard`、`SettingRow`。
- 不抽业务容器：`TaskPickerPanel`、`SelectedTasksPanel`、`RunningExecutionsTable`、`HistoryToolbar`、`EntityFormDrawer`。
- 不改交互：详情页/抽屉形态切换、状态组件合并、按钮位置调整等（如需要，另立方案并由用户确认）。
- 不动 `api/*`、`stores/*` 的接口与状态语义（`utils/execution.ts` 只抽纯计算）。
- 不为「以后可能复用」提前建文件。

## 附录 A：重复点复现命令

```powershell
cd frontend/src
$files = Get-ChildItem -Recurse -Include *.vue,*.ts | ForEach-Object { $_.FullName }

# 格式化函数
Select-String -Path $files -Pattern '^\s*(function|const) (triggerText|countText|durationText|formatDuration)'

# 状态/阶段映射
Select-String -Path $files -Pattern 'PHASE_LABELS\s*:|CONNECTION_META\s*:'

# 轮询与确认
Select-String -Path $files -Pattern 'setInterval\('
Select-String -Path $files -Pattern 'ElMessageBox\.confirm'

# 日志目录与分页
Select-String -Path $files -Pattern 'openLogDir'
Select-String -Path $files -Pattern 'pageSize.*slice|slice\(start'
```
