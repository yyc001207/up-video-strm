# docs/design/ui-next-fix-plan.md — 新版 UI 落地问题修复方案

> **背景**：v4.19.0（`5f2e077`）已按 [ui-next-plan.md](ui-next-plan.md) 落地暖调媒体界面。本轮基于**代码实读**，整理 8 个落地问题与全站样式复查结论。
> **状态**：修复方案，**未改代码**。每条给出「现象 → 根因（文件:行）→ 改法 → 验收」，可直接照做。
> **范围**：`frontend/src`（不涉及后端接口；与 [ui-next-plan.md 第 1.5 节](ui-next-plan.md)的接口约束一致）。
> **基线**：v4.19.0，前端 Vue 3.5 + Element Plus 2.14 + Sass。

---

## 0. 摘要

| # | 问题 | 严重度 | 一句话根因 | 改动面 |
|---|------|--------|-----------|--------|
| 1 | 深色模式菜单选中项看不清 | **P0** | 暗色只覆盖了 `--up-primary-600`，没覆盖 `--up-primary-50`，浅底配浅字 1.41:1 | 令牌 + 8 处引用 |
| 2 | 任务"卡片"其实是列表，要求只留列表并给按钮加图标 | P1 | 视图切换属过度设计；行样式仍是卡片外框 | 3 个任务页 + `TaskItem` |
| 3 | 「继续上次页面」多余 | P1 | 幽灵按钮 + 三段 localStorage 记忆 | `AppSidebar` |
| 4 | 菜单展开无动画 | P2 | `v-if` 直接挂载，箭头不旋转 | `AppSidebar` |
| 5 | 页面标题重复占空间 | P1 | 顶栏已有面包屑，`App.vue` 又全局渲染 28px 标题 + 简述 | `App.vue` + `Today.vue` + `TopBar` |
| 6 | 其他潜在样式问题 | P0–P2 | 令牌缺失、对比度、对齐、命中区等 12 项 | 见第 6 节 |
| 7 | 执行参数卡底部文字压边框 | **P0** | 面板固定高 + body 不滚动 + 说明文字贴底 | 3 个执行页 |
| 8 | 折叠/展开按钮一上一下 | P1 | 收起在顶部、展开在底部，同一操作两个位置 | `AppSidebar` |

**建议实施顺序**：1 → 7 → 6 中的 P0 → 8 → 2 → 5 → 3 → 4 → 6 中 P1/P2。前两项是"看不清/被裁切"，优先修。

---

## 1. 深色模式菜单选中项对比度（P0）

### 现象

深色模式下，左侧导航当前选中项几乎看不见：底色接近白、文字是浅紫，两者几乎同亮度。同类问题也出现在运行胶囊、运行中状态胶囊、选中任务行等位置。

### 根因（实测）

`AppSidebar.vue:373-377`：

```scss
&.is-active {
  background: var(--up-primary-50);   // 亮色 #f4f0ff，暗色未覆盖 → 仍是近白
  color: var(--up-primary-600);       // 暗色被覆盖为 #d3c6ff
  font-weight: 600;
}
```

`variables.scss:105-139` 的 `html.dark` 只覆盖了 `--up-primary-500/600`（120-122 行），**没有覆盖 50/100/200 阶**。于是暗色下：

| 组合 | 当前值 | 实测对比度 |
|------|--------|-----------|
| 选中文字 / 选中底 | `#d3c6ff` / `#f4f0ff` | **1.41:1**（不可读） |
| 目标：`#d3c6ff` / `#241b3d` | — | **10.23:1** |

### 修复

**A. 补齐暗色浅色阶**（`styles/variables.scss` 的 `html.dark` 块内）：

```scss
--up-primary-50: #241b3d;   // 选中底 / 轻提示底
--up-primary-100: #2a2140;  // 悬停底 / 徽标底
--up-primary-200: #3a2d5c;  // 浅描边
```

**B. 统一"tint 底 + 600 文字"的配对**，不要在 tint 底上用 `--el-text-color-primary`（暗色下是浅字）。逐处核对：

| 位置 | 文件:行 | 现状 | 处理 |
|------|---------|------|------|
| 导航选中项 | `AppSidebar.vue:374-375` | primary-50 底 + primary-600 字 | 令牌修复后自动达标（10.23:1） |
| 导航徽标 | `AppSidebar.vue:422-423` | primary-100 底 + **primary-700 字**（暗色未覆盖 700，仍是 `#4a32ac`） | 文字改 `--up-primary-600`（9.56:1） |
| 运行胶囊 | `TopBar.vue:151-152` | primary-50 底 + primary-600 字 | 令牌修复后达标 |
| 运行中状态胶囊 | `StatusPill.vue:76-78` | 同上 | 同上 |
| 选中任务行 | `TaskItem.vue:114-116` | primary-50 底 + `--el-text-color-primary`（暗色浅字） | 令牌修复后达标；另见第 2 节改列表样式 |
| 批量条 | `BulkBar.vue:41-43` | primary-200 描边 + primary-50 底 | 令牌修复后达标 |
| 命令面板选中项 | `CommandPalette.vue:243` | primary-50 底 | 令牌修复后达标 |
| 文本选中 | `global.scss:167-168` | primary-100 底 + `--up-ink-900`（暗色为 `#f5f0ed` 浅色） | 修复后 11:1；否则暗色下选中文字直接消失 |

### 验收

- 暗色下选中项、徽标、胶囊、选中行、`::selection` 全部 ≥4.5:1（推荐 ≥7:1）。
- 亮色无回归：选中项仍为 `#5a3fd1` on `#f4f0ff`（5.97:1）。
- 明暗各截 4 张：导航、顶栏胶囊、状态胶囊、任务选中行。

---

## 2. 任务列表：移除卡片模式、只保留列表、操作按钮加图标（P1）

### 现象与判断

三个任务页都有「卡片 / 表格」分段切换。所谓"卡片"其实是带边框、圆角、阴影、悬停上浮的**行**，结构上就是列表；再提供一个表格视图属于过度设计。

**决定**：只保留**一种列表视图**——沿用现有行的信息结构（头像块 + 两行文字 + 状态胶囊），但去掉卡片式外框，改为用分隔线组织的列表；删除「表格」视图与切换控件；操作按钮补图标。

### 涉及文件

| 文件 | 现状 |
|------|------|
| `views/schedule/TaskManage.vue` | 50-56 定义 `VIEW_OPTIONS/viewMode`；392 分段控件；401 `v-if="viewMode === 'card'"`；427-455 `el-table` |
| `views/upload/TaskConfig.vue` | 33-38 同上；276 分段控件；284 分支 |
| `views/automation/TaskConfig.vue` | 265-270 同上；16 分段控件；24 分支 |
| `components/TaskItem.vue` | 88-122 卡片外观：`border` + `radius-lg` + `shadow` + `hover translateY(-1px)` |

### 修改方案

**A. 删除切换与表格视图**（三处同样处理）

- 删 `VIEW_OPTIONS`、`viewMode`、`VIEW_KEY`、`watch(viewMode)`、`el-segmented`；
- 删 `el-table` 及 `@selection-change`、`handleSelectionChange`（若仅表格使用）；
- 模板只保留 `TaskItem` 列表 + `EmptyState`；
- 同步清理 `localStorage` 旧键 `up-video-strm-task-view`（一次性 `removeItem`，避免遗留脏数据）。

**B. `TaskItem` 改为列表行**（`components/TaskItem.vue`）

```scss
.task-item {
  min-height: 64px;               // 80 → 64
  padding: 10px 12px;
  border: none;                    // 去掉卡片外框
  border-bottom: 1px solid var(--el-border-color-lighter);
  border-radius: 0;
  background: transparent;
  box-shadow: none;

  &:last-child { border-bottom: none; }
  &:hover { background: var(--el-fill-color-light); transform: none; }  // 去掉上浮
}
```

列表容器（三页的 `.task-list`）补：`border: 1px solid var(--el-border-color-lighter); border-radius: var(--up-strm-radius-lg); background: var(--el-bg-color); overflow: hidden;`——圆角与描边由容器承担，行内不再各画一圈。

**C. 操作按钮加图标**（`TaskItem` 的 `#actions` 插槽，三页同改）

```vue
<el-button link type="primary" :icon="EditPen" @click="openEdit(row)">编辑</el-button>
<el-button link type="primary" :icon="CopyDocument" @click="handleCopy(row)">复制</el-button>
<el-button link type="danger" :icon="Delete" @click="handleDelete(row)">删除</el-button>
```

- 图标 14px，与文字间距 4px；`el-button` 的 `link` 样式已带图标位。
- 删除按钮保持 `danger`；不要改成纯图标（任务名是危险操作对象，需要文字）。
- 批量删除按钮已有 `Delete` 图标，无需改。

### 验收

- 三个任务页均无 `el-segmented`、无 `el-table`、无 `viewMode`；
- 列表首屏（1440×900）至少 9 行完整可见；
- 每行操作都有图标 + 文字；点击行仍能打开编辑；
- 批量选中、批量删除、空态、分页不回归。

---

## 3. 移除「继续上次页面」（P1）

### 现象

展开某个模块时，如果当前页不属于该模块，组内会多出一行「继续上次页面」，点它跳回上次访问的页面。这个入口既不可预期，也和"点页面进页面"的常规导航重复。

### 根因位置

`AppSidebar.vue`：

- 229-237：幽灵按钮本身；
- 82-83：`LAST_PAGE_KEY`、`OPEN_GROUP_KEY`；
- 111-119：`lastPageByModule` 初始化；
- 121-136：路由变化时写入上次页面；
- 158-160：`groupTarget()` 只为该按钮服务。

### 修改方案

1. 删除 229-237 的 `nav-item--ghost` 按钮；
2. 删除 `lastPageByModule`、`LAST_PAGE_KEY`、`groupTarget`，以及 `watch` 里 128-133 的写存储逻辑；
3. **保留** `OPEN_GROUP_KEY`（记住展开的是哪个模块）——这是导航展开状态，不是"上次页面"；
4. 模块标题点击只做展开/收起，不再承担跳转；
5. 不做数据迁移：旧键 `up-video-strm-nav-last-page` 在首次启动时 `removeItem` 即可。

> 注意：不要误删 `router/index.ts` 里 `/schedule`、`/upload`、`/automation` 的模块级重定向，那是路由兜底，与本功能无关。

### 验收

- 任意模块展开后只显示该模块的页面项，无多余行；
- 刷新、切换模块、折叠再展开，均不出现「继续上次页面」；
- `localStorage` 中不再写入 `up-video-strm-nav-last-page`。

---

## 4. 菜单切换 / 展开动画（P2）

### 现象

点模块标题，子项瞬间出现/消失；箭头只在展开时显示，且不旋转，看不出"可折叠"。

### 修复

**A. 高度过渡**（`AppSidebar.vue` 215 行附近）

`v-if` 直接卸载无法过渡，二选一：

- 方案一（推荐，零 JS）：外层用 `grid-template-rows: 0fr → 1fr`

```vue
<div class="nav-group__wrap" :class="{ 'is-open': openGroup === group.id }">
  <div class="nav-group__body">…</div>
</div>
```

```scss
.nav-group__wrap {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows var(--up-strm-dur-base) var(--up-strm-ease);
  &.is-open { grid-template-rows: 1fr; }
}
.nav-group__body { min-height: 0; overflow: hidden; }
```

- 方案二：`<Transition>` + JS 钩子读 `scrollHeight` 设 `height`，结束后置 `auto`。适合需要精确控制 `opacity` 的场景。

**B. 箭头常显 + 旋转**

```vue
<span class="nav-group__chevron" :class="{ 'is-open': openGroup === group.id }">⌄</span>
```

```scss
.nav-group__chevron {
  margin-left: auto;
  transition: transform var(--up-strm-dur-fast) var(--up-strm-ease);
  &.is-open { transform: rotate(180deg); }
}
```

- 折叠态（72px）不显示箭头；
- 只旋转不换字符，避免两个图标字重不一致。

**C. 减弱动效**：全局 `prefers-reduced-motion` 已把 transition 压到 0.01ms（`global.scss:136`），无需额外处理。

### 验收

- 展开/收起有 220ms 高度过渡，无内容截断、无跳动；
- 箭头随状态旋转 180°；
- 从一个模块切到另一个模块时，前一个收起、后一个展开，动画不叠加错位。

---

## 5. 去掉页面标题，简述移到面包屑下方（P1）

### 现象

顶栏已有「模块 / 页面」面包屑，内容区又渲染一个 28px 标题 + 一行简述，同一信息出现两次，且占掉约 86px 首屏高度。

### 现状结构（关键：不是每页各写一次）

- `TopBar.vue:51-55`：渲染「模块 / 页面」面包屑；
- **`App.vue:108-112` 在 `router-view` 之前全局渲染了一次 `PageHeader`**，`title / description` 取自 `route.meta`（`isToday` 时跳过）；
- `Today.vue:233` 又单独渲染一次 `PageHeader title="今天" :description="todayText"`；
- 全项目只有这 **2 处**调用；且 `PageHeader` 没有接收 `actions` 插槽（App.vue 未传），目前是**纯标题块**；
- 高度构成：上内边距 24 + 标题 36 + 间距 6 + 简述 20 ≈ 86px。

### 修改方案

**A. 顶栏改两行（48 → 60px）**

```
┌──────────────────────────────────────────────────────────┐
│ STRM 生成 / 任务                                          │  13/600
│ 维护任务：处理路径、输出目录与默认参数                     │  12/次要
│                                    [运行胶囊] [已连接] [搜索] [主题] │
└──────────────────────────────────────────────────────────┘
```

- 简述直接取 `route.meta.description`（16 条路由已全部配置），不需要页面再传；
- 行高：面包屑 18 + 简述 18 + 间距 4 + 上下内边距 10 = 60；
- 简述单行省略；无 description 时（理论上不存在）不渲染第二行，顶栏回落 48px。

**B. 直接删除 `PageHeader`，而不是改成操作条**

- 页面级操作本来就在各页工具栏（`el-button` 组）里，`PageHeader` 从未承载过操作；
- 删除 `App.vue:108-112` 与 `Today.vue:233` 两处调用，删除 `components/PageHeader.vue`；
- `Today` 的那句概览由已有的 `.today__greeting` 承担，与 `description` 内容重复，删掉正好去重；
- `App.vue` 的 `pageTitle` / `pageDescription` 计算属性仅服务于该组件，一并删除；`document.title` 改用 `route.meta.title`。

**C. 15 个业务页面无需改动**

- 业务页面没有任何 `<PageHeader>` 调用，删除全局那一次即可；
- 删除后检查内容区顶部间距：`.page` 已有 32px 上内边距（`global.scss:47`），若视觉上"顶栏—内容"过松，把列表页上内边距收到 24，正文页保持 32；
- 若将来确需"页面级主行动固定在顶部"，再单独引入操作条，本期不做。

### 空间收益与验收

| 项 | 改前 | 改后 |
|----|------|------|
| 顶栏 | 48 | 60（有简述）/ 48（无） |
| 页面标题区 | ~86 | 0 |
| 净变化 | — | 首屏多出约 74px，且不再有重复标题 |

- 面包屑与简述左边缘对齐内容区（见第 6.4 条，同用 32px 内边距）；
- 全站 16 条路由检查：不再出现 28px 大标题；主行动仍在首屏；`document.title` 仍为「页面 - up-video-strm」。

---

## 6. 全站样式复查（P0–P2）

> 复查方式：逐文件读样式段 + 颜色令牌引用统计 + 对比度计算。以下只列**确认存在问题**的项；`focus-visible`、减弱动效、表格数字对齐等已合规，不再重复。

### 6.1 汇总

| # | 严重度 | 问题 | 位置 |
|---|--------|------|------|
| 6.1 | **P0** | 暗色浅色阶缺失，导致 8 处浅底浅字 | 见第 1 节 |
| 6.2 | **P0** | 头像块白字对比度不足：6 色中 4 色 <3:1 | `AvatarTile.vue:55-81` |
| 6.3 | **P0** | `--up-accent-400` 未定义，logo 渐变失效且违反"不用渐变" | `AppSidebar.vue:307` |
| 6.4 | P1 | 顶栏内边距 24，内容区 32，左边缘差 8px | `TopBar.vue:109` vs `variables.scss:53` |
| 6.5 | P1 | 导航选中态 `font-weight: 600`，中文会变粗跳宽 | `AppSidebar.vue:376` |
| 6.6 | P1 | 折叠按钮 24×24，低于 32 命中区 | `AppSidebar.vue:327-328` |
| 6.7 | P1 | 顶栏 `backdrop-filter` + 88% 透明，属玻璃拟态且滚动重绘 | `TopBar.vue:111-112` |
| 6.8 | P1 | 勾选框 `opacity:0` + `pointer-events:none`，键盘聚焦时仍不可见 | `TaskItem.vue:133-142` |
| 6.9 | P2 | `Ctrl K` 提示 10px，低于 11px 元信息下限 | `TopBar.vue:232` |
| 6.10 | P2 | 壳层用 `100vh` 而非 `100%`，窗口缩放时可能溢出 | `App.vue:122,132` |
| 6.11 | P2 | 日志终端硬编码整套暗色 hex（20+ 处），未走令牌 | `LogViewer.vue:284-396` |
| 6.12 | P2 | 行操作按钮无图标（随第 2 节一并修） | 三个任务页 |

### 6.2 头像块白字（P0）

`AvatarTile.vue` 用 6 个固定底色 + `color:#fff`，实测：

| 底色 | 白字对比度 | 结论 |
|------|-----------|------|
| `#6b4ee6` | 5.44 | 通过 |
| `#3f74d9` | 4.46 | 临界（<4.5） |
| `#d95c9a` | 3.53 | 不通过 |
| `#2aa8a8` | 2.89 | 不通过 |
| `#d98a00` | 2.77 | 不通过 |
| `#ff8a5b` | 2.32 | 不通过 |

**改法**：底色整体加深一档，白字全部 ≥4.9：

```
#6b4ee6 → 保留（5.44）
#3f74d9 → #2f5bb7（6.36）
#d95c9a → #9d2b6b（7.02）
#2aa8a8 → #0f766e（5.47）
#d98a00 → #a16207（4.92）
#ff8a5b → #c2410c（5.18）
```

同时把 6 个色值提为令牌（`--up-avatar-1..6`），深色模式如需再调只改一处。

### 6.3 logo 渐变失效（P0）

```scss
// AppSidebar.vue:307
background: linear-gradient(135deg, var(--up-primary-500), var(--up-accent-400));
```

`--up-accent-400` 全项目未定义（`variables.scss` 只有 `--up-accent-mark/text/bg`）。`var()` 解析失败会让整条 `background` 声明失效，logo 实际是**透明底 + 白字**，在浅色主题下几乎不可见。

**改法**：不用渐变（设计规范也禁止），改实色：

```scss
background: var(--up-primary-500);
```

### 6.4 顶栏与内容左边距不一致（P1）

`TopBar` 用 `var(--up-strm-space-6)` = 24px，页面用 `--up-strm-page-pad` = 32px。面包屑与下方卡片左边缘差 8px，放大截图可见"标题比内容更靠左"。

**改法**：`TopBar` 横向内边距统一为 `var(--up-strm-page-pad)`；≤1279 的媒体查询同步为 24（与页面一致）。

### 6.5 导航选中态改字重（P1）

`AppSidebar.vue:376` 的 `font-weight: 600` 会让微软雅黑直接变 Bold，选中项文字变宽 1–2px，切换时横向跳动；这违反既定规则（"选中不改字重，用底色 + 颜色表达"）。

**改法**：删除该行；选中态只保留底色 + 文字颜色。

### 6.6 折叠按钮命中区（P1，与第 8 节合并）

当前 24×24。改为 32×32（图标仍 16–18），并保证折叠态顶部能容纳（见第 8 节的宽度分配）。

### 6.7 顶栏玻璃拟态（P1）

```scss
background: color-mix(in srgb, var(--el-bg-color) 88%, transparent);
backdrop-filter: saturate(160%) blur(10px);
```

WebView2 在滚动时会持续重绘模糊层；且半透明顶栏与"暖调实色表面"的语言不一致。

**改法**：`background: var(--el-bg-color);`，去掉 `backdrop-filter`；如需滚动阴影，用 1px 底边 + 轻阴影。

### 6.8 隐藏勾选框的可达性（P1）

`TaskItem.vue:133-142` 用 `opacity:0` + `pointer-events:none` 隐藏勾选框，但元素仍在 tab 序列里：键盘 Tab 会聚焦一个看不见的控件。

**改法**：

```scss
&__check { opacity: 0; }
.task-item:hover &__check,
.task-item:focus-within &__check,
.task-item.is-selected &__check { opacity: 1; pointer-events: auto; }
```

去掉 `pointer-events:none`（或只在非悬停时保留，但 `focus-within` 要能点）。

### 6.9–6.12 低优先项

- **10px 提示**：`Ctrl K` 快捷键提示改 11px；或整体改用 `kbd` 风格但字号不低于 11。
- **100vh**：`App.vue` 的 `.app-shell` / `.app-main` 改 `height: 100%`，与外层 `#app` 的百分比高度链一致；避免窗口出现横向滚动条时底部被裁。
- **日志终端硬编码**：`LogViewer.vue` 内 20 余处 hex 建议抽成 `--up-log-bg / --up-log-text / --up-log-muted / --up-log-error …` 四到六个令牌。若要保留"深色终端"视觉，也要把色值放到令牌层并注明"终端在两种主题下恒暗"，避免后续改主题时漏改。
- **行操作图标**：见第 2 节 C。

### 6.13 复查中确认"没问题"的项（避免重复劳动）

- `:focus-visible` 已统一 2px 紫色 + 2px offset，暗色切 300 阶（`global.scss:126-133`）；
- `prefers-reduced-motion` 已全局降级（136 行起）；
- 表格数字列右对齐、`tabular-nums` 已落地；
- 批量条为文档流内元素，不是浮层（`BulkBar` 无 `position`）。

---

## 7. 执行参数卡片底部文字与边框重叠（P0）

### 现象

「云盘上传 / 开始执行」「STRM 生成 / 开始执行」「自动追更 / 开始执行」三页的执行参数卡，最下方说明文字紧贴甚至压住卡片下边框；窗口越矮越明显，自动追更（参数最多）最严重。

### 根因（三处同构）

以 `views/upload/Execution.vue` 为例：

| 位置 | 代码 | 后果 |
|------|------|------|
| 534 | `.exec-workspace { height: clamp(380px, 52vh, 560px) }` | 面板高度被锁死 |
| 544 | `.exec-panel { overflow: hidden }` | 超出部分直接裁掉 |
| 590-597 | `&__body { flex:1; padding:16px }`，**无 `overflow-y`** | 内容超高时既不滚动也不撑开 |
| 719-726 | `.param-note { margin: auto 0 0; padding-top:12px; border-top:1px }` | 被 `margin-top:auto` 顶到 body 底边，正好贴住卡片边框 |

`schedule/Execution.vue:657-664`、`806-813` 与 `automation/Execution.vue:931-938`、`1092` 完全同构；自动追更有 5 个时间参数，最容易触发。

> 结论：不是"文字多写了 4px"，而是**固定高度 + 不滚动 + 贴底布局**三者叠加。只调 `padding` 治标不治本。

### 修复方案

**A. 参数面板内容可滚动（推荐）**

```scss
.exec-panel--params {
  .exec-panel__body {
    overflow-y: auto;
    padding-bottom: var(--up-strm-space-5); // 20px，保证末行与边框有呼吸
  }

  .param-note {
    margin: var(--up-strm-space-3) 0 0;     // 不用 auto：滚动容器里 auto 会挤底
    padding-top: var(--up-strm-space-3);
    border-top: 1px solid var(--el-border-color-lighter);
  }
}
```

滚动条样式沿用全局 8px；`padding-right: 4px` 避免滚动条压字。

**B. 说明文字常驻（可选，更稳）**

把 `.param-note` 移出 `body`，作为面板 footer：

```vue
<div class="exec-panel__body">…参数…</div>
<p class="param-note">执行记录创建后…</p>
```

```scss
.param-note {
  flex: none;
  margin: 0;
  padding: 12px 16px 16px;
  border-top: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
}
```

这样参数区自己滚，说明永远可见、永不压边框。代价是面板可用高度少约 60px。

**C. 不要做的事**

- 不要靠给 `.exec-workspace` 加高度解决：1366×768 下会更糟；
- 不要在 `.param-note` 上加负 margin 或 `position: absolute`：会重现上一轮的遮挡问题；
- 三个页面必须用同一套改法，否则又会漂移。

### 验收

- 1440×900、1280×720、1024×680 三档，分别检查三个执行页：
  - 参数卡滚到底，最后一行文字与卡片下边框间距 ≥16px；
  - 无文字被裁切、无横向滚动条；
  - 「自动追更」5 个时间参数 + 说明全部可达；
- 参数区滚动不影响左侧任务列表与右侧已选列表的滚动。

---

## 8. 折叠 / 展开按钮统一到菜单栏顶部（P1）

### 现象

- 展开态：收起按钮在**顶部**品牌行右侧（`AppSidebar.vue:179-188`）；
- 折叠态：展开按钮在**底部**（`AppSidebar.vue:257-266`）。

同一个操作（收起/展开导航）在两个位置、两种图标字符（`«` / `»`），用户需要重新找入口；折叠后按钮还从顶部"跳"到底部。

### 修复方案

**A. 顶部唯一入口**

删除 footer 里的 `app-sidebar__expand`，品牌行内保留唯一 toggle，两种状态都在同一位置（顶部右侧）：

| 状态 | 品牌行内容 | 尺寸分配（72px 折叠态） |
|------|-----------|------------------------|
| 展开（232） | logo 28 + 名称 + toggle 32（右对齐） | — |
| 折叠（72） | logo 28 + toggle 32 | 左右内边距 4 + logo 28 + gap 4 + 按钮 32 + 右内边距 4 = 72 |

> 72px 折叠态下，`logo(28) + gap(4) + 按钮(32) + 左右 padding(4×2) = 72`，刚好放下；若按钮保持 24×24 更宽松，但命中区不足（见 6.6），建议 32×32 并把左右 padding 收到 4。

**B. 图标与语义**

- 用 Element Plus `Fold` / `Expand`（16px），不要用 `«` `»` 字符（字重与对齐随字体变化）；
- 按钮加 `aria-expanded`、`aria-label="收起导航" / "展开导航"`；
- 鼠标悬停显示 tooltip（折叠态尤其需要）。

**C. 与动画的配合**

- 宽度过渡已有（`transition: width 220ms`）；按钮位置固定，不参与动画；
- 折叠时名称淡出（`opacity` 160ms），避免文字被瞬间裁切；
- 展开时名称延迟 60ms 淡入，避免与宽度动画抢帧。

### 验收

- 展开/折叠两种状态，按钮中心坐标一致（距顶 12、距右 12，允许 ±1）；
- 折叠态能同时看到 logo 与按钮，不重叠、不溢出；
- 键盘 Tab 可达，`aria-expanded` 随状态变化；
- 连续切换 10 次无错位、无文字残影。

---

## 9. 文件级修改清单

| 文件 | 改动 | 关联 |
|------|------|------|
| `styles/variables.scss` | `html.dark` 补 primary-50/100/200；头像色板令牌（可选） | 1、6.2 |
| `components/AppSidebar.vue` | 删「继续上次页面」与 last-page 记忆；toggle 统一到顶部；箭头常显+旋转；展开动画；删 `font-weight:600`；logo 实色；徽标文字改 600 | 1、3、4、6.3、6.5、6.6、8 |
| `components/TopBar.vue` | 两行面包屑 + 简述；内边距统一 32；去 `backdrop-filter`；kbd 11px | 5、6.4、6.7、6.9 |
| `components/PageHeader.vue` | **删除文件**（全项目仅 2 处调用，均移除） | 5 |
| `views/Today.vue` | 删除 `PageHeader` 调用，保留概览句 | 5 |
| `components/TaskItem.vue` | 列表行样式（去边框/圆角/阴影/上浮，64px）；勾选框 `focus-within` 可见 | 2、6.8 |
| `views/schedule/TaskManage.vue` | 删视图切换与 el-table；操作按钮加图标 | 2 |
| `views/upload/TaskConfig.vue` | 同上 | 2 |
| `views/automation/TaskConfig.vue` | 同上 | 2 |
| `views/upload/Execution.vue` | 参数 body 可滚动 + note 间距 | 7 |
| `views/schedule/Execution.vue` | 同上 | 7 |
| `views/automation/Execution.vue` | 同上 | 7 |
| `components/AvatarTile.vue` | 6 色加深，白字 ≥4.9:1 | 6.2 |
| `App.vue` | 删除 `PageHeader` 与 `pageTitle/pageDescription`；`100vh` → `100%` | 5、6.10 |
| `components/LogViewer.vue` | （可选）hex 抽令牌 | 6.11 |

---

## 10. 回归与验收

### 10.1 视觉

- [ ] 暗色：导航选中、徽标、运行胶囊、状态胶囊、选中行、文本选中 全部 ≥4.5:1
- [ ] 明暗 × 1440 / 1280 / 1024 三档，任务页无横向滚动
- [ ] 页面不再出现 28px 重复标题；简述在面包屑下且左边缘与内容对齐
- [ ] 参数卡在三档窗口下，说明文字与边框间距 ≥16px
- [ ] 折叠/展开按钮同坐标；动画无跳动

### 10.2 功能

- [ ] 三个任务页：新建、编辑、复制、删除、批量删除、分页、搜索、空态
- [ ] 三个执行页：选任务、改参数、启动、跳转运行详情、参数滚动
- [ ] 导航：模块展开/收起、今天、连接与格式、设置
- [ ] 托盘「设置…」仍跳 `/settings`（`window.__upVideoStrmNavigate`）
- [ ] 命令面板 `Ctrl+K`、`/` 聚焦搜索、`Esc` 关闭

### 10.3 工程

- [ ] `npm run type-check` 通过
- [ ] `npm run build` 通过
- [ ] 无新增后端接口调用（与 ui-next-plan 第 1.5 节一致）
- [ ] 纯前端改动，按规范递增 PATCH 并补 `CHANGELOG.md`

---

**设计：UI Designer** · **日期：2026-11-07** · **状态：修复方案，未改代码**
