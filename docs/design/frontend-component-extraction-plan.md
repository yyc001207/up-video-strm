# docs/design/frontend-component-extraction-plan.md — Vue 3 前端页面审查与组件抽取方案

> **已撤回（2026-11-07）**：本文的组件抽取方案经评审存在「为组件化而组件化、混入交互变更、缺少删除标准、复用性判断错误」等问题，由 [frontend-abstraction-plan-v2.md](frontend-abstraction-plan-v2.md) 取代。本文仅保留为评审记录，**不应作为实施依据**。

> **状态：❌ 严重不合格（2026-11-07 复核判定，代码已回退至实施前）。** 本文件仅保留作复盘材料，**不再作为实施依据**。
>
> **判定原因（逐条）**：
> 1. **为组件化而组件化**：把「组件数量」当成成绩，拆分粒度远超实际复用需求。大量组件只是给 Element Plus 套一层壳并原样转发 props / slots——例如 `EntityFormDrawer` 仅转发 `el-drawer` 的 `modelValue / size / title / saving`，`ConfigSectionCard` 仅转发 `el-card`，`ExecPanel` 仅转发容器样式；这是**中间商组件**，没有减少概念，只是增加了一层需要同时阅读的契约。
> 2. **抽象没有消除重复**：方案声称「四组结构性重复」，但落地后页面里的业务编排、筛选状态、轮询语义仍需各自保留，真正消除的主要是 CSS 与骨架；同时新增了 `components/execution/`、`components/log/`、`components/history/`、`composables/` 多套目录与 20+ 文件、props 契约、插槽协议，阅读路径变长。
> 3. **低估风险、以「纯重构」掩盖交互变更**：D3（历史统一抽屉）、D4（弹窗统一抽屉）、D5（状态组件合并）实际改变了用户操作习惯与视觉，却与 D6–D10 纯逻辑收敛混在同一优先级表里，缺少逐项用户确认。
> 4. **缺少删除标准与验收口径**：「行数下降」不是结构改善的证据；方案没有规定「什么情况下应当删掉一个组件」「抽象失败的判定条件」，导致过度抽象无法在过程中被否决。
> 5. **可复用性判断错误**：真正值得复用的只有纯函数与少量无 DOM 逻辑（格式化、日期边界、分页、选择、轮询），这些在方案中被排在 P0 且体量很小；P1–P3 的大组件抽取属于风险最高、收益最低的部分。
>
> **处置**：代码已回退至本方案实施前版本（v4.19.2，提交 `810538a`）。后续如需收敛复用逻辑，只允许对「已重复出现 ≥3 次、且抽成纯函数 / 组合式函数后调用方明显更简单」的部分做小步抽取，禁止壳组件、转发型组件与布局壳抽象。

> **原状态（历史记录，已作废）：方案，未改代码。** 本文只做结构分析与抽取设计，落地时按第 6 节分批实施。
> **基线**：v4.19.2（`8d70366`），`frontend/src` 实读：16 个页面 + 3 个模块内组件 + 13 个通用组件，合计 13650 行（含样式）。
> **目标**：以降重复、定边界、可组合为主，不以"组件数量"为成绩。
> **方法**：逐页职责 → 重复逻辑分类 → 组合式函数 / 组件设计 → 优先级与迁移建议。
> **关联**：[ui-next-plan.md](ui-next-plan.md)（设计依据）、[ui-next-fix-plan.md](ui-next-fix-plan.md)（落地问题修复）。

---

## 0. 结论摘要

1. **四组结构性重复**：执行工作台（3 页 3210 行）、运行详情（3 页 1970 行）、运行记录（3 页 1628 行）、任务配置（4 页 1988 行）。它们共用类名与布局，却各写一遍。
2. **五类横切逻辑**：客户端分页（5 处）、筛选状态（6 处）、轮询（15 个 `setInterval`）、确认弹窗（18 处）、打开日志目录（14 处）。
3. **一处概念双轨**：状态展示同时存在 `StatusDot`（7 个页面）与 `StatusPill`（2 个页面），视觉与语义都在分叉。
4. **建议抽取**：9 个组合式函数（含 2 个轻量 action 封装）+ 13 个组件 + 2 个工具模块。先抽 headless 与纯展示层（低风险），再抽布局壳，最后统一交互模型。
5. **不建议抽**：Today 的页面编排、模块专属表单字段、`DirTreePanel` / `RemoteDirPanel`（已封装且只服务单模块）。

---

## 1. 现状盘点

### 1.1 规模分布

| 分类 | 页面数 | 行数 | 占比 |
|------|--------|------|------|
| 执行工作台（3） | 3 | 3210 | 24% |
| 运行详情（3） | 3 | 1970 | 14% |
| 运行记录（3） | 3 | 1628 | 12% |
| 任务配置（4，含命名规则） | 4 | 1988 | 15% |
| 连接与格式 + 设置 | 2 | 1033 | 7% |
| 今天 | 1 | 472 | 3% |
| 模块内子组件（目录树 / 云端目录 / 生成设置） | 3 | 920 | 7% |
| 通用组件（13） | — | 2429 | 18% |

> 三个业务模块的 13 个页面合计 8796 行，占全部前端代码的 **64%**；它们又是同构的，是重复的主战场。

### 1.2 页面职责矩阵

| 页面 | 行数 | 职责 | 主要结构 | 与谁重复 |
|------|------|------|----------|----------|
| `Today.vue` | 472 | 聚合三模块状态：概览句、3 张流水线卡、待处理、最近活动 | `today__overview` + 卡片组 + 两个区块 | FlowCard 已抽；数据聚合一页专属 |
| `schedule/TaskManage.vue` | 635 | 调度任务 CRUD、按目录快速添加 | toolbar + `el-table` + 分页 + 快速添加抽屉 + 编辑弹窗 | 与 upload / automation 任务页同骨架 |
| `schedule/Execution.vue` | 996 | 选任务、选模式、启动、查看/取消运行中 | `exec-page` → 3 面板 + 运行表 | **D1** 执行工作台 |
| `schedule/RealtimeLog.vue` | 830 | 单执行的 WS 日志、视频/字幕进度 | 任务条 + 6 项进度 + 日志工具条 + `LogViewer` | **D2** 运行详情 |
| `schedule/TaskHistory.vue` | 502 | 每任务最近执行、详情页、日志抽屉 | `viewMode: list/detail` + 表格 + 抽屉 | **D3** 运行记录 |
| `upload/TaskConfig.vue` | 432 | 上传任务 CRUD、云端目录、命名规则选择 | toolbar + 表格 + 抽屉 + `RemoteDirPanel` | **D4** 配置列表 |
| `upload/RenameRules.vue` | 425 | 命名规则 CRUD、模板预览 | toolbar + 表格 + 弹窗 | 与任务页同骨架 |
| `upload/Execution.vue` | 917 | 选任务、冲突策略/并发/重试/试运行、启动 | 3 面板 + 运行表 | **D1** |
| `upload/RealtimeLog.vue` | 553 | 批量排队 WS 日志、7 项统计 | 根类名 `upload-realtime`（与另两页不同）+ 进度 + 日志条 | **D2** |
| `upload/TaskHistory.vue` | 616 | 任务汇总 → 详情 → 文件明细/日志，重跑 | `viewMode` + 表格 + 2 个抽屉 | **D3** |
| `automation/TaskConfig.vue` | 496 | 自动化任务 CRUD、绑定校验、目录检测 | toolbar + 表格 + 抽屉 | **D4** |
| `automation/Execution.vue` | 1297 | 批量启停、5 项时间参数、待校验、批量停止 | 3 面板 + 批量栏 + 运行表 | **D1**（最复杂） |
| `automation/RealtimeLog.vue` | 587 | 按任务订阅 WS、轮次/待校验统计 | 任务条 + 7 项 + 日志条 | **D2** |
| `automation/TaskHistory.vue` | 510 | 轮次记录、详情抽屉、失败重试 | toolbar + 表格 + 2 个抽屉 | **D3**（抽屉模型） |
| `config/GlobalConfig.vue` | 766 | 服务器、格式、云盘、生成设置 | 3 张分区卡 + 弹窗/抽屉 | 卡片头重复 |
| `Settings/index.vue` | 267 | 窗口、托盘、自启、数据目录、版本 | `settings__row` 列表 | 行结构重复 |

### 1.3 重复逻辑分类

| 编号 | 重复模式 | 证据 | 影响 | 处置 |
|------|----------|------|------|------|
| **D1** | 执行工作台三套 | 996 / 917 / 1297 行；样式各 412 / 400 / 439 行；`.exec-panel`、`.task-row`、`.selected-list` 类名与规则几乎一致 | 改一处布局要改三次；上次 285px 中栏问题就是这么来的 | 抽 `ExecutionWorkbench` + 3 个面板 + 选择逻辑 |
| **D2** | 运行详情三套 | 830 / 553 / 587；`CONNECTION_META`、`autoScroll`、`levelFilter`、`keyword`、`canReconnect` 三份；上传页根类名不同 | 连接状态、过滤行为会漂移；样式重复 ~345 行 | 抽 `LogMonitorLayout` + `LogFilterBar` + `useLogStream` |
| **D3** | 运行记录三套，交互模型还不一致 | 调度/上传用 `viewMode: list/detail` 页内切换；自动化用 `detailVisible` 抽屉 | 用户在三页学到三种"看详情"的方式 | **先统一模型**（建议都用抽屉），再抽 `DetailDrawer` |
| **D4** | 配置列表四套 + 表单容器不一致 | 调度 4 个 `el-dialog` + 2 个 `el-drawer`；上传 2+2；自动化 2 抽屉；命名规则 2 弹窗 | 同一"新建/编辑"动作在不同页用不同容器 | 统一 `EntityFormDrawer`，容器先统一为抽屉 |
| **D5** | 状态展示双轨 | `StatusDot` 用于 7 个页面；`StatusPill` 用于 Today / ActivityDrawer；状态色与文案各维护一份 | 同一种"成功/失败"两种长相 | 合并为 `StatusBadge`（`variant: dot｜pill`） |
| **D6** | 格式化函数复制 | `triggerText` ×4、`countText` ×3、`durationText` ×2、`formatDuration` ×1 | 0/0 显示 `—`、耗时格式等规则容易改漏 | `utils/format.ts` |
| **D7** | 客户端分页 | 5 个页面各写 `page/pageSize/pagedList/slice` | 分页大小、回第 1 页时机不一致 | `useClientPagination` |
| **D8** | 轮询与清理 | 15 处 `setInterval`，各自写 `onBeforeUnmount` / `disposed` 标志 | 卸载后仍写状态、页面隐藏仍请求 | `usePolling` |
| **D9** | 确认弹窗 | 18 处 `ElMessageBox.confirm`，文案与按钮词各写 | 危险操作口径不统一 | `useConfirmAction` |
| **D10** | 日志目录与日期范围 | `openLogDir` 14 处（各带一份 catch）；`00:00:00/23:59:59` 转换 6 处 | 提示文案分叉、时区处理易错 | `useLogDir` + `toBeijingDayRange` |

### 1.4 已有的好资产（不要重造）

| 资产 | 现有接口 | 结论 |
|------|----------|------|
| `LogViewer` | `lines` / `autoScroll` / `maxLines` / `emptyText`，**只渲染不筛选** | 边界清晰，保留；不要往里塞过滤逻辑 |
| `EmptyState` | `title` / `description` / `actionText` / `compact` | 保留 |
| `BulkBar` | `count` / `noun` + 默认插槽 | 保留 |
| `utils/ws.ts` | `connectWs` / `connectUploadWs` / `connectAutomationWs` / `disconnectWs` | 保留；薄封装成 composable 即可 |
| `utils/date.ts` | `formatDateTime` / `formatDate` / `beijingMillis` | 保留，补 `toBeijingDayRange` |
| `stores/running.ts` | 三模块运行数聚合、离线判定 | 保留；不要在页面里重复轮询 |

---

## 2. 抽取原则与边界

### 2.1 四项原则的落地判据

| 原则 | 判据（做到才算） | 反例 |
|------|------------------|------|
| **单一职责** | 一句话能说清"它只做什么"；超过两个变化原因就拆 | `TaskPickerPanel` 同时管搜索、全选、执行启动 |
| **通用性** | 只依赖入参与事件，不 import store / api；换一个模块仍能用 | 组件内部 `useOpenlistStore()` 取任务 |
| **封装** | 内部状态（开合、分页、定时器）不外泄；外部只看到语义事件 | 把 `selectedIds` 的 ref 直接传给子组件改 |
| **组合** | 页面只做编排；能力由小组件/组合式函数拼出来 | 一个 500 行"万能页面组件" |

### 2.2 分层规则

```
views/            只编排：取数、组合组件、处理路由；不写布局细节
components/<域>/  展示或容器：可接收数据、发语义事件；容器型才可依赖 store/api
composables/      无 DOM、无组件 import；只处理状态与副作用
utils/            纯函数：无 ref、无请求
```

**三条 props 规则**

1. **受控**：`v-model` 只用于 `keyword` / `page` / `visible` 这类可直接回写的值；复杂对象用 props + 事件。
2. **语义事件**：发 `toggle` / `start` / `cancel`，不发 `set-selected-ids`。
3. **不传 store**：展示组件只收数据；store 留在页面或容器组件。

### 2.3 目录建议

```
frontend/src/
├── composables/          # 新增
│   ├── useSelection.ts
│   ├── useClientPagination.ts
│   ├── useFilterState.ts
│   ├── usePolling.ts
│   ├── useEntityForm.ts
│   ├── useExecutionLaunch.ts
│   └── useLogStream.ts
├── components/
│   ├── execution/        # ExecPanel / Workbench / Picker / Selected / Running / ParamBlock
│   ├── log/              # LogMonitorLayout / LogFilterBar / LogDrawer
│   ├── history/          # HistoryToolbar / DetailDrawer
│   ├── config/           # ConfigSectionCard / SettingRow
│   └── StatusBadge.vue
└── utils/
    ├── format.ts         # countText / durationText / triggerText
    └── date.ts           # 追加 toBeijingDayRange
```

---

## 3. 组合式函数设计（headless）

### 3.1 `useSelection`

**职责边界**：管理"选中了哪些 id"，以及全选/取消全选、锁定判断；不持有任务数据、不渲染、不发请求。

```ts
function useSelection<T>(options: {
  items: () => T[]                 // 当前可见/可选的集合（通常是筛选结果）
  getId: (item: T) => number
  isLocked?: (item: T) => boolean  // 执行中不可选
}): {
  selectedIds: Ref<number[]>
  selectedItems: ComputedRef<T[]>
  selectableItems: ComputedRef<T[]>
  allSelected: ComputedRef<boolean>
  count: ComputedRef<number>
  isSelected: (id: number) => boolean
  toggle: (id: number) => void
  remove: (id: number) => void
  clear: () => void
  toggleAll: () => void
}
```

- **可复用点**：三个执行页；以后批量选择类页面都能用。
- **内部封装**：全选只作用于 `selectableItems`；切换筛选不清空已选（这是既定行为，写进测试）。
- **不做什么**：不改 `items`、不排序、不负责"已选摘要"的文案。

### 3.2 `useClientPagination`

**职责边界**：把全量数组切成当前页；页码越界时自动回收；筛选变化时回到第 1 页由调用方显式 `reset()`。

```ts
function useClientPagination<T>(
  source: MaybeRef<T[]>,
  options?: { pageSize?: number; sizes?: number[] }
): {
  page: Ref<number>
  pageSize: Ref<number>
  sizes: number[]
  pagedItems: ComputedRef<T[]>
  total: ComputedRef<number>
  reset: () => void          // 回第 1 页
  onSizeChange: () => void   // 改每页条数后回第 1 页
}
```

- **可复用点**：TaskManage、RenameRules、调度/上传/自动化运行记录（5 处）。
- **内部封装**：`watch(total)` 时把 `page` 钳制到有效范围，避免删到空页。
- **不做什么**：不处理服务端分页（automation 运行记录走服务端，保持现状）。

### 3.3 `useFilterState`

**职责边界**：只保存筛选状态与重置，不计算过滤结果（客户端/服务端两种模式差异大）。

```ts
function useFilterState<S extends string = string>(options?: {
  statuses?: readonly S[]
}): {
  keyword: Ref<string>
  status: Ref<S | ''>
  dateRange: Ref<[string, string] | null>
  hasFilter: ComputedRef<boolean>
  reset: () => void
}
```

配套纯函数：

```ts
// utils/format.ts
function matchKeyword(keyword: string, fields: Array<string | null | undefined>): boolean
function countText(success: number, total: number): string   // 0/0 → '—'
function durationText(seconds: number | null): string        // 4m12s / 1h04m
function triggerText(row: { trigger_source?: string | null; trigger_name?: string | null }): string

// utils/date.ts
function toBeijingDayRange(range: [string, string] | null): { start?: string; end?: string }
```

- **可复用点**：6 个列表页的 keyword/status/dateRange；4 处 `triggerText` 等。
- **不做什么**：不替页面决定"服务端传 `start_time` 还是客户端按自然日过滤"。

### 3.4 `usePolling`

**职责边界**：按固定间隔执行任务；组件卸载自动停；页面隐藏时跳过（可选）。

```ts
function usePolling(
  task: () => void | Promise<void>,
  options: { interval: number; immediate?: boolean; visibleOnly?: boolean }
): { start: () => void; stop: () => void; running: Ref<boolean> }
```

- **可复用点**：执行页运行表（5s）、壳层运行数（30s）、Today 的轻量刷新。
- **内部封装**：`onBeforeUnmount` 清理；重入保护（上一次没结束就跳过本次）。
- **不做什么**：不做指数退避（接口层已有 3s 去重，退避放后续单独议题）。

### 3.5 `useEntityForm`

**职责边界**：抽屉的开合、编辑态 id、保存 loading、提交编排；表单字段与校验由页面提供。

```ts
function useEntityForm<TForm extends object>(options: {
  empty: () => TForm
  load?: (id: number) => Promise<Partial<TForm>>
  submit: (form: TForm, id: number | null) => Promise<void>
  validate?: () => Promise<boolean>
}): {
  visible: Ref<boolean>
  saving: Ref<boolean>
  editingId: Ref<number | null>
  isEdit: ComputedRef<boolean>
  form: TForm
  openCreate: () => void
  openEdit: (id: number) => Promise<void>
  close: () => void
  save: () => Promise<void>
}
```

- **可复用点**：调度/上传/自动化任务、命名规则（4 处），后续 GlobalConfig 的编辑弹窗。
- **不做什么**：不生成表单字段、不写校验规则（领域知识留在页面）。

### 3.6 `useExecutionLaunch`

**职责边界**：把"执行记录 → 路由入参"的约定收在一处，保证"先连日志再启动"的时序不被各页写错。

```ts
function useExecutionLaunch(route: string): {
  launch: (
    executions: Array<{ id: number; task_id: number; task_name: string }>,
    options?: { launch?: boolean }
  ) => Promise<void>
}
```

- **可复用点**：三个执行页的「执行任务」「查看日志」。
- **内部封装**：拼 `LaunchNavItem[]`、`JSON.stringify`、`router.push({ path, query: { execs } })`。
- **不做什么**：不创建执行记录（那是页面/store 的事）。

### 3.7 `useLogStream`

**职责边界**：连接状态与生命周期的薄封装；帧解析留给页面（三模块帧结构不同）。

```ts
function useLogStream(options: {
  connect: () => void
  disconnect: () => void
}): {
  state: Ref<'connecting' | 'connected' | 'disconnected'>
  reconnect: () => void
  dispose: () => void
}
```

- **可复用点**：三个运行详情页。
- **不做什么**：不合并帧、不做日志过滤、不管排队（上传的队列逻辑留在页面）。

### 3.8 `useConfirmAction` / `useLogDir`

```ts
function useConfirmAction(): {
  confirmDanger: (options: {
    title: string
    message: string
    confirmText: string
    cancelText?: string
  }) => Promise<boolean>
}

function useLogDir(kind: 'openlist' | 'upload' | 'automation'): {
  open: () => Promise<void>   // 统一 catch + 提示「仅 Windows 本地环境支持」
}
```

- **可复用点**：18 处确认、14 处日志目录。
- **不做什么**：不替页面决定危险级别（L1/L2/L3 仍由页面判断）。

---

## 4. 组件设计

> 每个组件都按「职责边界 / 可复用点 / 接口 / 内部封装 / 不做什么」描述。组件个数控制在 13 个以内，避免碎片化。

### 4.1 `ExecPanel`（面板壳）

- **职责**：只负责"卡片头 + 可滚动主体 + 可选 footer"的布局与描边。
- **可复用点**：三个执行页 × 3 栏 = 9 处；运行详情页的进度卡也可复用。
- **Props**：`title: string`、`subtitle?: string`、`count?: number`、`bodyClass?: string`
- **Events**：无
- **Slots**：`default`（主体）、`head-extra`（右上角计数/开关）、`footer`（底栏）
- **内部封装**：`overflow: hidden` + 主体 `overflow-y: auto` + `padding-bottom` 兜底（修复"底部文字压边框"的根因）。
- **不做什么**：不接收业务数据、不判断状态。

### 4.2 `ExecutionWorkbench`（三栏布局）

- **职责**：只负责 `选择任务 / 执行参数 / 已选任务 / 运行中` 四块的位置、列宽、间距、响应式。
- **可复用点**：三个执行页。
- **Props**：`runningCollapsed?: boolean`（可选，默认 false）
- **Events**：`update:runningCollapsed`
- **Slots**：`tasks`、`params`、`selected`、`running`
- **内部封装**：`grid-template-columns: minmax(0,1.6fr) minmax(300px,.9fr) minmax(280px,1fr)`、`height: clamp(380px,52vh,560px)`、<1100 堆叠。
- **不做什么**：不知道"任务""模式""冲突策略"是什么。

### 4.3 `TaskPickerPanel`

- **职责**：搜索 + 可选列表 + 全选/取消全选 + 可选/已选计数。
- **可复用点**：三个执行页；后续任何"多选对象"场景。
- **Props**（泛型组件，Vue 3.3+ `generic`）：

```ts
interface Props<T extends { id: number }> {
  items: T[]
  selectedIds: number[]
  keyword: string
  title?: string
  subtitle?: string
  placeholder?: string
  loading?: boolean
  isLocked?: (item: T) => boolean
  countLabel?: (item: T) => string
  emptyText?: string
}
```

- **Events**：`update:keyword`、`toggle(id)`、`toggle-all`、`activate(item)`
- **Slots**：`item`（`{ item, selected, locked }`）、`empty`
- **内部封装**：搜索框、行结构、锁定态、全选只作用于当前筛选结果。
- **不做什么**：不发请求、不持有选择结果（`selectedIds` 由父级传入）。

### 4.4 `SelectedTasksPanel`

- **职责**：展示已选清单、单项移除、清空、主行动按钮与摘要。
- **可复用点**：三个执行页。
- **Props**：`items: Array<{ id: number; name: string; meta?: string }>`、`summary?: string`、`canStart: boolean`、`loading?: boolean`、`startText?: string`
- **Events**：`remove(id)`、`clear`、`start`
- **Slots**：`item-extra`
- **内部封装**：清单滚动区（超过 6 条内部滚动）、空态、footer 固定。
- **不做什么**：不校验"是否在执行中"（通过 `canStart` 传入）。

### 4.5 `RunningExecutionsTable`

- **职责**：运行中/最近执行的表格：状态、计数、耗时、触发来源、操作。
- **可复用点**：三个执行页；运行记录页可复用同一套单元格渲染。
- **Props**：`rows: ExecutionRow[]`、`loading?: boolean`、`showTrigger?: boolean`（默认 true）、`emptyText?: string`
- **Events**：`view(row)`、`cancel(row)`
- **Slots**：`actions-extra`
- **内部封装**：`countText` / `durationText` / `triggerText`（来自 utils）、状态徽标、`is-running` 行样式。
- **不做什么**：不轮询、不确认取消（确认由页面调 `useConfirmAction`）。

### 4.6 `ParamBlock`

- **职责**：一个参数项 = label + 控件 + 说明文字。
- **可复用点**：三个执行页共 3 + 4 + 8 项；连接与格式页也可用。
- **Props**：`label: string`、`hint?: string`、`required?: boolean`
- **Slots**：`default`（控件）
- **内部封装**：label 14/600、间距 8、hint 12/次要、行高 1.6。
- **不做什么**：不接管 `v-model`（控件自己绑定）。

### 4.7 `StatusBadge`（合并 StatusDot / StatusPill）

- **职责**：全站唯一的状态展示：点状（表格内）或胶囊状（详情/卡片）。
- **可复用点**：现有 9 个页面 + 后续所有状态位。
- **Props**：`status: PillStatus`、`variant?: 'dot' | 'pill'`（默认 dot）、`count?: number`、`breathe?: boolean`
- **Events**：无
- **内部封装**：状态 → 文案/颜色/是否呼吸的映射表；颜色只用语义令牌。
- **迁移**：先保留 `StatusDot` 作为 `variant="dot"` 的别名导出，页面逐个替换后删除旧文件。

### 4.8 `LogMonitorLayout`（运行详情骨架）

- **职责**：任务选择条 + 进度摘要 + 内容区的位置与滚动；不解析日志。
- **可复用点**：三个运行详情页。
- **Props**：`tasks: Array<{ id: number; label: string }>`、`currentId: number | null`、`connection: 'connecting' | 'connected' | 'disconnected'`、`statusText: string`、`elapsedText?: string`、`stats: Array<{ label: string; value: string; tone?: 'default' | 'success' | 'danger' }>`
- **Events**：`update:currentId`、`reconnect`、`clear`、`open-log-dir`
- **Slots**：`progress-extra`（自动化特有的轮次/待校验）、`default`（日志区）
- **内部封装**：任务条、进度卡、统计项排布、连接状态文案。
- **不做什么**：不建 WS、不存日志行。

### 4.9 `LogFilterBar`

- **职责**：级别筛选、关键字搜索、跟随滚动、行数限制、匹配计数。
- **可复用点**：三个运行详情页。
- **Props**：`level: FilterLevel`、`keyword: string`、`follow: boolean`、`lineLimit: number`、`levels: Array<{ value: FilterLevel; label: string; count: number }>`
- **Events**：`update:level`、`update:keyword`、`update:follow`、`update:lineLimit`
- **内部封装**：工具条布局、级别切换、清空、快捷键 `/` 聚焦。
- **不做什么**：不执行过滤（`LogViewer` 的上游由页面算）。

### 4.10 `LogDrawer`

- **职责**：历史页的日志抽屉：按 id 拉取日志 → 渲染 `LogViewer` → 打开日志目录。
- **可复用点**：三个运行记录页；后续失败详情也可复用。
- **Props**：`modelValue: boolean`、`title?: string`、`size?: string`（默认 640px）、`loader: (id: number) => Promise<LogLine[]>`、`executionId?: number | null`、`logDirKind: 'openlist' | 'upload' | 'automation'`
- **Events**：`update:modelValue`
- **内部封装**：加载态、空态、错误态、`LogViewer`、底部"日志文件夹"。
- **不做什么**：不重连、不实时跟随（历史日志是静态的）。

### 4.11 `EntityFormDrawer`

- **职责**：抽屉壳 + footer 保存/取消 + 保存中状态；字段与校验由页面放入插槽。
- **可复用点**：4 个配置页 + GlobalConfig 的编辑弹窗。
- **Props**：`modelValue: boolean`、`title: string`、`width?: string`（默认 480）、`saving?: boolean`、`submitText?: string`
- **Events**：`update:modelValue`、`submit`、`closed`
- **Slots**：`default`（表单）、`footer-extra`
- **内部封装**：`el-drawer` 圆角、内边距、footer 高度、`Esc` 行为。
- **不做什么**：不管表单数据（配合 `useEntityForm` 使用）。

### 4.12 `ConfigSectionCard`

- **职责**：连接与格式页的分区卡：标题 + 说明 + 右上状态/操作 + 内容。
- **可复用点**：OpenList / 格式 / 123 云盘 / 生成设置 4 处。
- **Props**：`title: string`、`description?: string`
- **Slots**：`status`、`actions`、`default`
- **内部封装**：卡片头布局、分隔线、段落间距 32。
- **不做什么**：不判断在线/离线（`status` 插槽传入）。

### 4.13 `SettingRow`

- **职责**：设置页一行：标题 + 说明 + 右侧控件。
- **可复用点**：设置页 6–8 行。
- **Props**：`label: string`、`description?: string`
- **Slots**：`default`（控件）
- **内部封装**：64px 行高、分隔线、窄屏换行。

---

## 5. 组合方式示例

抽取后，一个执行页从"900 行什么都写"变成"200 行编排"：

```vue
<ExecutionWorkbench>
  <template #tasks>
    <TaskPickerPanel
      v-model:keyword="keyword"
      :items="store.tasks"
      :selected-ids="selection.selectedIds.value"
      :is-locked="isLocked"
      :count-label="t => `最近 ${t.last_execution?.video_total_count ?? 0} 个视频`"
      @toggle="selection.toggle"
      @toggle-all="selection.toggleAll"
    />
  </template>

  <template #params>
    <ExecPanel title="执行参数" subtitle="参数将应用到本次选中的全部任务">
      <ParamBlock label="模式" hint="增量只处理新增内容">
        <el-segmented v-model="execMode" :options="MODE_OPTIONS" />
      </ParamBlock>
      <ParamBlock label="并发" hint="过大可能触发限流">
        <el-input-number v-model="concurrency" :min="1" :max="8" />
      </ParamBlock>
    </ExecPanel>
  </template>

  <template #selected>
    <SelectedTasksPanel
      :items="selection.selectedItems.value"
      :summary="`已选 ${selection.count.value} 个 · ${totalVideos} 个视频`"
      :can-start="selection.count.value > 0 && !starting"
      :loading="starting"
      @remove="selection.remove"
      @clear="selection.clear"
      @start="handleStart"
    />
  </template>

  <template #running>
    <RunningExecutionsTable :rows="runningRows" :loading="runningLoading" @view="handleViewLog" @cancel="handleCancel" />
  </template>
</ExecutionWorkbench>
```

脚本侧：

```ts
const selection = useSelection({ items: () => store.tasks, getId: t => t.id, isLocked: t => store.runningTaskIds.has(t.id) })
const { page, pageSize, pagedItems, reset } = useClientPagination(list)
const { keyword, status, dateRange, hasFilter, reset: resetFilter } = useFilterState()
const { start, stop } = usePolling(() => refreshRunning(true), { interval: 5000, visibleOnly: true })
const launch = useExecutionLaunch('/schedule/realtime')
```

页面剩下的只有：取数、参数映射（模式 → 三个布尔）、提交、路由跳转。

---

## 6. 优先级与落地建议

### 6.1 分批

| 批次 | 内容 | 收益 | 风险 | 验证 |
|------|------|------|------|------|
| **P0**（1–2 天） | `utils/format.ts`、`toBeijingDayRange`、`useClientPagination`、`useSelection`、`StatusBadge`、`ParamBlock` | 立刻消除 5 类复制；改动面小、可逐页替换 | 低 | type-check + 逐页对照 |
| **P1**（3–5 天） | `ExecPanel`、`ExecutionWorkbench`、`TaskPickerPanel`、`SelectedTasksPanel`、`RunningExecutionsTable`；先迁移**自动追更**（最复杂，能暴露接口不足） | 执行页 3210 行 → 约 3×250 + 共享约 900 | 中：面板差异靠 slot 表达 | 三模块功能对照表 |
| **P2**（2–3 天） | `LogMonitorLayout`、`LogFilterBar`、`LogDrawer`、`usePolling`、`useLogStream` | 日志页 1970 行 → 约 3×200 + 共享约 500；连接行为统一 | 中：统计项不同，用 `stats` 数组 | 三种执行各跑一次 |
| **P3**（3–5 天） | 统一运行记录交互（都用抽屉）→ `HistoryToolbar` + `DetailDrawer`；`EntityFormDrawer`；`ConfigSectionCard` + `SettingRow` | 历史页 1628 行 → 约 3×220 + 共享约 400；"新建/编辑"容器统一 | 中：交互模型变化需产品确认 | 逐页走查 + 截图 |

> 行数为估算目标，不是承诺；以"重复样式消失、改一处生效"为验收，而不是死抠行数。

### 6.2 迁移顺序

1. **先 headless**：`useSelection` / `useClientPagination` / `format` 先在**一个页面**接入，行为不变再推广。
2. **再壳后页**：先落 `ExecPanel`（纯样式），确认视觉零变化，再上 `Workbench`。
3. **按模块推进**：自动追更 → 云盘上传 → STRM 生成。自动化参数最多、批量操作最全，用它验证接口;调度最简单，最后迁，作为"是否过度抽象"的反向检验。
4. **一次一个模块，迁完即删旧样式**，不允许新旧两套长期并存。

### 6.3 量化目标

| 指标 | 现状 | 目标 |
|------|------|------|
| 三执行页总行数 | 3210 | ≤ 1700（含共享组件） |
| 三日志页总行数 | 1970 | ≤ 1100 |
| 三历史页总行数 | 1628 | ≤ 1100 |
| 重复样式（exec-panel 等） | 约 1250 行 ×1 份 | 1 份，约 300 行 |
| 状态展示实现 | 2 套 | 1 套 |
| 分页/轮询实现 | 5 / 15 处 | 1 / 1 套 |

### 6.4 风险与对策

| 风险 | 表现 | 对策 |
|------|------|------|
| 过度抽象 | 为 2 处相似写一个"万能组件"，props 越加越多 | 同一模式出现 **≥3 次**才抽；2 处先复制 |
| 泛型组件类型难写 | `TaskPickerPanel` 泛型 + slot 作用域类型报错 | 泛型只约束 `{ id: number }`；复杂渲染交给 `item` 插槽 |
| slot 爆炸 | 一个组件 5+ 插槽，调用方比原代码还长 | 每组件 ≤3 个插槽；多出来的用数据 props |
| 抹平模块差异 | 自动化 5 个时间参数被塞进通用参数卡 | 差异显式化为 props/插槽；`ParamBlock` 只做行，不做分组 |
| 双轨期 | 新组件与旧页面并存半年 | 每批次结束删旧实现；PR 里带删除行数 |
| 行为回归 | 全选范围、执行时序、排队逻辑被改 | 迁移前把这三条写成对照清单，逐条勾 |

### 6.5 验收清单

- [ ] 三个执行页使用同一套 `Workbench + Picker + Selected + Running`，页面内无 `.exec-panel` 样式定义
- [ ] 三个运行详情页使用同一套 `LogMonitorLayout + LogFilterBar`，连接状态文案一致
- [ ] 运行记录三页的"看详情"交互一致（统一为抽屉）
- [ ] 全站状态展示只剩 `StatusBadge`
- [ ] 分页、轮询、确认、日志目录各只有一套实现
- [ ] `npm run type-check`、`npm run build` 通过
- [ ] 无新增后端接口（沿用现有数据流）

---

## 7. 不抽取清单（明确边界）

| 对象 | 原因 |
|------|------|
| `Today.vue` 的页面编排 | 一屏聚合，结构一次性；抽成"万能 Dashboard"会引入大量配置 |
| `DirTreePanel` / `RemoteDirPanel` | 已封装，且分别只服务调度/上传；强行通用会牺牲目录语义 |
| `LogViewer` | 接口已合理（只渲染不筛选），保持 |
| 业务表单字段与校验规则 | 领域知识，属于页面；抽成"配置驱动表单"会把复杂度转移到 schema |
| `api/*` 层 | 已按模块拆分，无需再包一层 |
| 三个模块的接口调用与状态机 | 差异真实存在，抽象收益低于理解成本 |

---

## 附录 A：页面 → 组件映射

| 页面 | 将使用的组件/组合式函数 |
|------|--------------------------|
| 三个 Execution | `ExecutionWorkbench`、`TaskPickerPanel`、`SelectedTasksPanel`、`RunningExecutionsTable`、`ExecPanel`、`ParamBlock`、`useSelection`、`usePolling`、`useExecutionLaunch` |
| 三个 RealtimeLog | `LogMonitorLayout`、`LogFilterBar`、`LogViewer`、`useLogStream`、`usePolling` |
| 三个 TaskHistory | `HistoryToolbar`、`DetailDrawer`、`LogDrawer`、`StatusBadge`、`useClientPagination`、`useFilterState` |
| 四个 TaskConfig/Rules | `EntityFormDrawer`、`StatusBadge`、`useEntityForm`、`useClientPagination`、`useConfirmAction` |
| GlobalConfig | `ConfigSectionCard`、`EntityFormDrawer`、`useConfirmAction` |
| Settings | `SettingRow` |
| Today | `FlowCard`（已有）、`StatusBadge`、`usePolling` |

## 附录 B：术语

- **展示组件**：只收 props、发事件，不知道数据从哪来。
- **容器组件**：可以依赖 store/api，负责取数与编排。
- **headless**：只有状态与副作用，没有模板（组合式函数）。
- **受控**：值由父级传入，子级只发"想改"的事件。

---

**设计：UI Designer** · **日期：2026-11-07** · **状态：抽取方案，未改代码**
