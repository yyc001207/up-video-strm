<script setup lang="ts">
/**
 * 自动追更 · 开始执行（/automation/execution）。
 *
 * 结构与「STRM 生成 · 开始执行」保持一致：三张卡片一行工作区
 * （左「选择任务」、中「执行参数」、右「已选任务」），下方「正在执行」表 5s 轮询。
 *
 * 与STRM 生成的差异仅在业务语义：本页执行的是自动追更的一轮链路，
 * 执行参数为 5 项时间参数（写入所选任务并持续生效）；
 * 启动成功后自动跳转到该任务的运行详情页，便于立即观察链路日志。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type TableInstance } from 'element-plus'
import {
  Close,
  Delete,
  Refresh,
  RefreshLeft,
  Search,
  Select,
  Timer,
  VideoPause,
  VideoPlay
} from '@element-plus/icons-vue'

import { automationApi, automationRunApi } from '@/api/automation'
import type {
  AutomationActiveTask,
  AutomationStartPayload,
  AutomationTask
} from '@/types/automation'

const ROUTE_REALTIME = '/automation/realtime'
const ROUTE_TASKS = '/automation/tasks'
const POLL_INTERVAL_MS = 5000

/** 执行参数缺省值（与后端 AutomationTask 默认值一致）。 */
const DEFAULT_RUN_PARAMS = {
  wait_interval_seconds: 15,
  openlist_wait_timeout: 600,
  idle_wait_timeout: 600,
  stage_timeout: 3600,
  interval_seconds: 60
}

/** 执行参数与任务字段的映射，选中任务时同步展示任务当前配置。 */
const RUN_PARAM_FIELDS = [
  'wait_interval_seconds',
  'openlist_wait_timeout',
  'idle_wait_timeout',
  'stage_timeout',
  'interval_seconds'
] as const

const PHASE_LABELS: Record<string, string> = {
  starting: '准备中',
  waiting_idle: '等待 A/B 空闲',
  waiting_upload: '上传中',
  waiting_openlist_check: '校验 OpenList 可见性',
  waiting_openlist_task: 'STRM 调度中',
  interval: '等待下一轮',
  backoff: '失败退避中',
  idle: '空闲等待',
  stopped: '已停止',
  done: '已结束'
}

const router = useRouter()

const loading = ref(false)
const activeLoading = ref(false)
const starting = ref(false)
const stoppingId = ref<number | null>(null)
const activeTableRef = ref<TableInstance>()
const activeSelectedIds = ref<number[]>([])
const batchStopping = ref(false)
const maintaining = ref(false)

const tasks = ref<AutomationTask[]>([])
const active = ref<AutomationActiveTask[]>([])
const allActiveSelected = computed(
  () => active.value.length > 0 && activeSelectedIds.value.length === active.value.length
)
const selectedTaskIds = ref<number[]>([])
const keyword = ref('')
/** 执行参数：默认取后端默认值；选中任务后同步为该任务当前配置，可修改（写回任务并持续生效）。 */
const waitIntervalSeconds = ref<number | undefined>(DEFAULT_RUN_PARAMS.wait_interval_seconds)
const openlistWaitTimeout = ref<number | undefined>(DEFAULT_RUN_PARAMS.openlist_wait_timeout)
const idleWaitTimeout = ref<number | undefined>(DEFAULT_RUN_PARAMS.idle_wait_timeout)
const stageTimeout = ref<number | undefined>(DEFAULT_RUN_PARAMS.stage_timeout)
const intervalSeconds = ref<number | undefined>(DEFAULT_RUN_PARAMS.interval_seconds)
/** 多选任务且各任务参数不一致时置空并提示，留空表示不修改该任务的对应参数。 */
const mixedRunParams = ref(false)

let pollTimer: ReturnType<typeof setInterval> | null = null
/** 轮次结束时刷新一次任务行（待校验 / 运行状态），避免额外轮询任务列表。 */
const ROUND_END_PHASES = new Set(['interval', 'backoff', 'idle', 'stopped', 'done'])
let lastPhases = new Map<number, string>()

const activeMap = computed(() => new Map(active.value.map(item => [item.task_id, item])))

/** 单服务器 / 自动追更列表不分页：直接在前端按关键字筛选。 */
const filteredTasks = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return tasks.value
  return tasks.value.filter(task => {
    return (
      task.name.toLowerCase().includes(kw) ||
      (task.check_dir || '').toLowerCase().includes(kw) ||
      (task.upload_task_name || '').toLowerCase().includes(kw) ||
      (task.openlist_task_name || '').toLowerCase().includes(kw)
    )
  })
})

const selectedTasks = computed(() =>
  tasks.value.filter(task => selectedTaskIds.value.includes(task.id))
)
const canStart = computed(
  () => selectedTaskIds.value.length > 0 && !starting.value
)
/** 已选任务的待校验文件总数（仅展示，便于决定是否优先补偿）。 */
const pendingTotal = computed(() =>
  selectedTasks.value.reduce((sum, task) => sum + (task.pending_file_count ?? 0), 0)
)

/** 全选仅作用于当前筛选结果里可选的任务：运行中的任务不可重复选择。 */
const selectableTasks = computed(() => filteredTasks.value.filter(task => !isLocked(task.id)))
const allSelectableSelected = computed(
  () =>
    selectableTasks.value.length > 0 &&
    selectableTasks.value.every(task => selectedTaskIds.value.includes(task.id))
)

function phaseText(taskId: number): string {
  const state = activeMap.value.get(taskId)
  if (state?.phase) return PHASE_LABELS[state.phase] ?? state.phase
  return '运行中'
}

function nextRoundText(taskId: number): string {
  return activeMap.value.get(taskId)?.next_round_at ?? '—'
}

function taskName(taskId: number): string {
  return activeMap.value.get(taskId)?.task_name || tasks.value.find(item => item.id === taskId)?.name || `任务 #${taskId}`
}

function isRunning(task: AutomationTask): boolean {
  return activeMap.value.has(task.id) || task.is_running
}

function isSelected(taskId: number): boolean {
  return selectedTaskIds.value.includes(taskId)
}

/** 任务是否锁定：执行中不可重复选择；提交过程中锁定全部选择。 */
function isLocked(taskId: number): boolean {
  const task = tasks.value.find(item => item.id === taskId)
  return starting.value || (task !== undefined && isRunning(task))
}

function toggleTask(task: AutomationTask): void {
  if (isLocked(task.id)) return
  const index = selectedTaskIds.value.indexOf(task.id)
  if (index >= 0) {
    selectedTaskIds.value.splice(index, 1)
  } else {
    selectedTaskIds.value.push(task.id)
  }
}

function handleRowKeydown(event: KeyboardEvent, task: AutomationTask): void {
  if (event.target !== event.currentTarget) return
  event.preventDefault()
  toggleTask(task)
}

function toggleSelectAll(): void {
  if (starting.value) return
  if (allSelectableSelected.value) {
    const selectableIds = new Set(selectableTasks.value.map(task => task.id))
    selectedTaskIds.value = selectedTaskIds.value.filter(id => !selectableIds.has(id))
    return
  }
  const merged = new Set(selectedTaskIds.value)
  for (const task of selectableTasks.value) merged.add(task.id)
  selectedTaskIds.value = [...merged]
}

function clearSelection(): void {
  selectedTaskIds.value = []
}

function removeSelected(taskId: number): void {
  selectedTaskIds.value = selectedTaskIds.value.filter(id => id !== taskId)
}

function buildPayload(): AutomationStartPayload {
  const payload: AutomationStartPayload = {}
  if (waitIntervalSeconds.value !== undefined) payload.wait_interval_seconds = waitIntervalSeconds.value
  if (openlistWaitTimeout.value !== undefined) payload.openlist_wait_timeout = openlistWaitTimeout.value
  if (idleWaitTimeout.value !== undefined) payload.idle_wait_timeout = idleWaitTimeout.value
  if (stageTimeout.value !== undefined) payload.stage_timeout = stageTimeout.value
  if (intervalSeconds.value !== undefined) payload.interval_seconds = intervalSeconds.value
  return payload
}

/** 选中任务变化时同步执行参数：单选取该任务当前值；多选取共同值，取值不一致则置空（不修改）。 */
function syncRunParams(): void {
  const list = selectedTasks.value
  if (list.length === 0) {
    waitIntervalSeconds.value = DEFAULT_RUN_PARAMS.wait_interval_seconds
    openlistWaitTimeout.value = DEFAULT_RUN_PARAMS.openlist_wait_timeout
    idleWaitTimeout.value = DEFAULT_RUN_PARAMS.idle_wait_timeout
    stageTimeout.value = DEFAULT_RUN_PARAMS.stage_timeout
    intervalSeconds.value = DEFAULT_RUN_PARAMS.interval_seconds
    mixedRunParams.value = false
    return
  }
  const common = (field: (typeof RUN_PARAM_FIELDS)[number]): number | undefined => {
    const first = list[0]?.[field]
    return list.every(task => task[field] === first) ? first : undefined
  }
  waitIntervalSeconds.value = common('wait_interval_seconds')
  openlistWaitTimeout.value = common('openlist_wait_timeout')
  idleWaitTimeout.value = common('idle_wait_timeout')
  stageTimeout.value = common('stage_timeout')
  intervalSeconds.value = common('interval_seconds')
  mixedRunParams.value = RUN_PARAM_FIELDS.some(field => common(field) === undefined)
}

watch(selectedTasks, syncRunParams)

/** 参数输入框占位文案：多选取值不一致时提示留空含义。 */
const paramPlaceholder = computed(() =>
  mixedRunParams.value ? '多任务取值不同，留空不修改' : '请填写'
)

async function loadTasks(silent = false): Promise<void> {
  if (!silent) loading.value = true
  try {
    const res = await automationApi.listTasks({ page: 1, page_size: 100 })
    tasks.value = res.data ?? []
    // 运行中的任务可能被删除：清理已不合法的选中项。
    const validIds = new Set(tasks.value.map(task => task.id))
    selectedTaskIds.value = selectedTaskIds.value.filter(id => validIds.has(id))
  } finally {
    if (!silent) loading.value = false
  }
}

async function loadActive(): Promise<void> {
  activeLoading.value = true
  try {
    const res = await automationRunApi.active()
    active.value = res.data ?? []
    lastPhases = new Map(active.value.map(item => [item.task_id, item.phase ?? '']))
    pruneActiveSelection()
    syncTimer()
  } finally {
    activeLoading.value = false
  }
}

/** 轮询后清理已不在运行列表中的选中项，避免批量停止命中已停止的任务。 */
function pruneActiveSelection(): void {
  const valid = new Set(active.value.map(item => item.task_id))
  activeSelectedIds.value = activeSelectedIds.value.filter(id => valid.has(id))
}

/** 轮次结束/任务停止时刷新一次任务行（待校验计数、运行状态），不额外轮询。 */
async function refreshAfterRoundEnd(next: AutomationActiveTask[], previousActive: AutomationActiveTask[]): Promise<void> {
  const finishedRound = next.some(item => {
    const previous = lastPhases.get(item.task_id)
    return previous !== undefined && !ROUND_END_PHASES.has(previous) && ROUND_END_PHASES.has(item.phase ?? '')
  })
  const stopped = previousActive.length > 0 && next.length === 0
  if (finishedRound || stopped) await loadTasks(true)
}

async function pollActive(): Promise<void> {
  try {
    const res = await automationRunApi.active()
    const previous = active.value
    const next = res.data ?? []
    active.value = next
    lastPhases = new Map(next.map(item => [item.task_id, item.phase ?? '']))
    pruneActiveSelection()
    await refreshAfterRoundEnd(next, previous)
  } catch {
    /* 拦截器已提示 */
  } finally {
    syncTimer()
  }
}

/** 仅当存在运行中的任务且页面可见时轮询；否则完全停止轮询。 */
function syncTimer(): void {
  const need = active.value.length > 0 && typeof document !== 'undefined' && !document.hidden
  if (need && !pollTimer) {
    pollTimer = setInterval(() => void pollActive(), POLL_INTERVAL_MS)
  } else if (!need && pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function onVisibilityChange(): void {
  if (!document.hidden && active.value.length > 0) {
    void pollActive()
  } else {
    syncTimer()
  }
}

async function load(): Promise<void> {
  try {
    await Promise.all([loadTasks(), loadActive()])
  } catch {
    /* 拦截器已提示 */
  }
}

async function handleStart(): Promise<void> {
  if (selectedTaskIds.value.length === 0) {
    ElMessage.warning('请至少选择一个任务')
    return
  }
  if (starting.value) return

  // 轮询可能发现已选任务被其他入口启动：跳过执行中的任务，避免重复执行。
  const requestedIds = selectedTaskIds.value.filter(taskId => !isLocked(taskId))
  const skippedCount = selectedTaskIds.value.length - requestedIds.length
  if (requestedIds.length === 0) {
    ElMessage.warning('所选任务均处于运行中，请等待当前轮次结束')
    return
  }
  if (skippedCount > 0) {
    ElMessage.info(`已跳过 ${skippedCount} 个正在运行的任务`)
  }

  starting.value = true
  try {
    const payload = buildPayload()
    if (requestedIds.length === 1) {
      await automationRunApi.start(requestedIds[0], payload)
    } else {
      const res = await automationRunApi.batchStart(requestedIds, payload)
      const failed = (res.data ?? []).filter(item => !item.ok)
      if (failed.length) {
        ElMessage.warning(`已启动 ${requestedIds.length - failed.length} 个，失败 ${failed.length} 个`)
      }
    }
    // 启动成功后自动跳转到对应任务的运行详情，便于立即观察本轮链路日志。
    await router.push({ path: ROUTE_REALTIME, query: { task_id: String(requestedIds[0]) } })
  } catch {
    /* 拦截器已提示 */
  } finally {
    starting.value = false
  }
}

async function stopTask(taskId: number): Promise<void> {
  if (stoppingId.value !== null) return
  try {
    await ElMessageBox.confirm(`确认停止自动追更「${taskName(taskId)}」的当前轮次？`, '停止运行', {
      type: 'warning',
      confirmButtonText: '停止运行',
      cancelButtonText: '继续运行'
    })
  } catch {
    return
  }
  stoppingId.value = taskId
  try {
    await automationRunApi.stop(taskId)
    ElMessage.success('已请求停止')
    await load()
  } catch {
    /* 拦截器已提示 */
  } finally {
    stoppingId.value = null
  }
}

/** 「正在执行」表：选择变化 / 全选 / 取消全选。 */
function handleActiveSelectionChange(rows: AutomationActiveTask[]): void {
  activeSelectedIds.value = rows.map(row => row.task_id)
}

function selectAllActive(): void {
  for (const row of active.value) {
    activeTableRef.value?.toggleRowSelection(row, true)
  }
}

function clearActiveSelection(): void {
  activeTableRef.value?.clearSelection()
  activeSelectedIds.value = []
}

function onToggleAllActive(value: boolean | string | number): void {
  if (value === true) selectAllActive()
  else clearActiveSelection()
}

/** 批量停止：逐个调用停止接口，全部结束后刷新列表。 */
async function stopSelected(): Promise<void> {
  const ids = [...activeSelectedIds.value]
  if (ids.length === 0) {
    ElMessage.warning('请先选择要停止的任务')
    return
  }
  if (batchStopping.value) return
  try {
    await ElMessageBox.confirm(`确认停止选中的 ${ids.length} 个任务的当前轮次？`, '批量停止', {
      type: 'warning',
      confirmButtonText: '批量停止',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  batchStopping.value = true
  let stopped = 0
  let failed = 0
  for (const taskId of ids) {
    try {
      await automationRunApi.stop(taskId)
      stopped += 1
    } catch {
      failed += 1
    }
  }
  batchStopping.value = false
  if (failed === 0) {
    ElMessage.success(`已请求停止 ${stopped} 个任务`)
  } else {
    ElMessage.warning(`已停止 ${stopped} 个，失败 ${failed} 个`)
  }
  clearActiveSelection()
  await load()
}

/** 重置扫描指纹：下次轮询将重新检测本地目录变化。 */
async function handleResetFingerprint(): Promise<void> {
  if (selectedTaskIds.value.length === 0) {
    ElMessage.warning('请先选择任务')
    return
  }
  if (maintaining.value) return
  try {
    await ElMessageBox.confirm(
      `确认重置 ${selectedTaskIds.value.length} 个任务的扫描指纹？下一轮将重新检测本地目录变化。`,
      '重置指纹',
      { type: 'warning' }
    )
  } catch {
    return
  }
  maintaining.value = true
  try {
    for (const taskId of selectedTaskIds.value) {
      await automationRunApi.resetFingerprint(taskId)
    }
    ElMessage.success('已重置扫描指纹')
    await loadTasks(true)
  } catch {
    /* 拦截器已提示 */
  } finally {
    maintaining.value = false
  }
}

/** 清空待校验：清空选中任务的待校验文件列表。 */
async function handleClearPending(): Promise<void> {
  const targets = selectedTasks.value.filter(task => task.pending_file_count > 0)
  if (targets.length === 0) {
    ElMessage.info('所选任务当前没有待校验文件')
    return
  }
  if (maintaining.value) return
  const count = targets.reduce((sum, task) => sum + task.pending_file_count, 0)
  try {
    await ElMessageBox.confirm(
      `确认清空 ${targets.length} 个任务的 ${count} 个待校验文件？清空后不再校验这些文件。`,
      '清空待校验',
      { type: 'warning' }
    )
  } catch {
    return
  }
  maintaining.value = true
  try {
    for (const task of targets) {
      await automationRunApi.clearPending(task.id)
    }
    ElMessage.success('已清空待校验文件')
    await loadTasks(true)
  } catch {
    /* 拦截器已提示 */
  } finally {
    maintaining.value = false
  }
}

function goTaskConfig(): void {
  void router.push(ROUTE_TASKS)
}

function openTaskRealtime(taskId: number): void {
  void router.push({ path: ROUTE_REALTIME, query: { task_id: String(taskId) } })
}

onMounted(async () => {
  await load()
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
})
</script>

<template>
  <div class="page page--fill exec-page">
    <div class="exec-body">
      <div class="exec-workspace">
        <!-- 左栏：选择任务 -->
        <section v-loading="loading" class="exec-panel exec-panel--tasks">
          <header class="exec-panel__head">
            <div class="exec-panel__heading">
              <h2 class="exec-panel__title">选择任务</h2>
              <p class="exec-panel__sub">展示全部自动追更；运行中的任务不可重复选择</p>
            </div>
            <span class="exec-panel__count">已选 {{ selectedTaskIds.length }}</span>
          </header>

          <div class="exec-panel__body">
            <div class="task-filters">
              <el-input
                v-model="keyword"
                class="task-filters__search"
                placeholder="搜索任务名称 / 校验目录"
                clearable
                :prefix-icon="Search"
              />
            </div>

            <el-empty
              v-if="tasks.length === 0"
              class="exec-panel__empty"
              description="还没有自动追更任务"
              :image-size="72"
            >
              <el-button type="primary" plain @click="goTaskConfig">前往任务</el-button>
            </el-empty>
            <el-empty
              v-else-if="filteredTasks.length === 0"
              class="exec-panel__empty"
              description="没有匹配的任务"
              :image-size="72"
            />
            <div v-else class="task-list">
              <div
                v-for="task in filteredTasks"
                :key="task.id"
                class="task-row"
                :class="{
                  'is-selected': isSelected(task.id),
                  'is-running': isRunning(task)
                }"
                role="checkbox"
                :aria-checked="isSelected(task.id)"
                :aria-disabled="isLocked(task.id)"
                :aria-label="task.name"
                tabindex="0"
                @click="toggleTask(task)"
                @keydown.enter="handleRowKeydown($event, task)"
                @keydown.space="handleRowKeydown($event, task)"
              >
                <span class="task-row__check" @click.stop>
                  <el-checkbox
                    :model-value="isSelected(task.id)"
                    :disabled="isLocked(task.id)"
                    @change="toggleTask(task)"
                  />
                </span>
                <span class="task-row__info">
                  <span class="task-row__name">{{ task.name }}</span>
                  <span class="task-row__path" :title="task.check_dir">{{ task.check_dir }}</span>
                </span>
                <span class="task-row__meta">
                  <span class="task-row__count">待校验 {{ task.pending_file_count }}</span>
                  <el-tag v-if="isRunning(task)" type="success" size="small" effect="light">
                    {{ phaseText(task.id) }}
                  </el-tag>
                </span>
              </div>
            </div>

            <div v-if="tasks.length > 0" class="exec-panel__footer">
              <span class="exec-panel__footer-hint">
                可选 {{ selectableTasks.length }} 个 · 已选 {{ selectedTaskIds.length }} 个
              </span>
              <div class="exec-panel__footer-ops">
                <el-button
                  link
                  :icon="Timer"
                  :disabled="selectedTaskIds.length === 0 || maintaining"
                  @click="handleResetFingerprint"
                >
                  重置指纹
                </el-button>
                <el-button
                  link
                  :icon="Delete"
                  :disabled="selectedTaskIds.length === 0 || maintaining"
                  @click="handleClearPending"
                >
                  清空待校验
                </el-button>
                <el-button
                  link
                  type="primary"
                  :icon="Select"
                  :disabled="selectableTasks.length === 0 || starting"
                  @click="toggleSelectAll"
                >
                  {{ allSelectableSelected ? '取消全选' : '全选' }}
                </el-button>
              </div>
            </div>
          </div>
        </section>

        <!-- 中栏：执行参数 -->
        <aside class="exec-panel exec-panel--params">
          <header class="exec-panel__head">
            <div class="exec-panel__heading">
              <h2 class="exec-panel__title">执行参数</h2>
              <p class="exec-panel__sub">默认取所选任务的当前配置；修改后写回任务并持续生效</p>
            </div>
          </header>

          <div class="exec-panel__body">
            <div class="param-block">
              <span class="param-block__label">可见性轮询间隔（秒）</span>
              <el-input-number
                v-model="waitIntervalSeconds"
                :min="5"
                :max="120"
                :disabled="starting"
                :placeholder="paramPlaceholder"
                controls-position="right"
              />
            </div>

            <div class="param-block">
              <span class="param-block__label">可见性等待超时（秒）</span>
              <el-input-number
                v-model="openlistWaitTimeout"
                :min="60"
                :max="3600"
                :disabled="starting"
                :placeholder="paramPlaceholder"
                controls-position="right"
              />
            </div>

            <div class="param-block">
              <span class="param-block__label">空闲等待超时（秒）</span>
              <el-input-number
                v-model="idleWaitTimeout"
                :min="60"
                :max="3600"
                :disabled="starting"
                :placeholder="paramPlaceholder"
                controls-position="right"
              />
            </div>

            <div class="param-block">
              <span class="param-block__label">阶段超时（秒）</span>
              <el-input-number
                v-model="stageTimeout"
                :min="60"
                :max="7200"
                :disabled="starting"
                :placeholder="paramPlaceholder"
                controls-position="right"
              />
            </div>

            <div class="param-block">
              <span class="param-block__label">轮次间隔（秒）</span>
              <el-input-number
                v-model="intervalSeconds"
                :min="10"
                :max="3600"
                :disabled="starting"
                :placeholder="paramPlaceholder"
                controls-position="right"
              />
            </div>

            <p class="param-note">
              启动后立即执行一轮（跳过指纹检查）；进入运行详情页后随时可查看链路日志。
            </p>
          </div>
        </aside>

        <!-- 右栏：已选任务 -->
        <section class="exec-panel exec-panel--selected">
          <header class="exec-panel__head">
            <div class="exec-panel__heading">
              <h2 class="exec-panel__title">已选任务</h2>
              <p class="exec-panel__sub">确认选中项后启动，参数应用到全部任务</p>
            </div>
            <span class="exec-panel__count">{{ selectedTaskIds.length }}</span>
          </header>

          <div class="exec-panel__body">
            <el-empty
              v-if="selectedTasks.length === 0"
              class="exec-panel__empty"
              description="在左侧勾选要启动的自动追更"
              :image-size="64"
            />
            <div v-else class="selected-list">
              <div v-for="task in selectedTasks" :key="task.id" class="selected-row">
                <span class="selected-row__info">
                  <span class="selected-row__name">{{ task.name }}</span>
                  <span class="selected-row__path" :title="task.check_dir">{{ task.check_dir }}</span>
                </span>
                <el-button
                  link
                  :icon="Close"
                  :disabled="starting"
                  aria-label="移除该任务"
                  @click="removeSelected(task.id)"
                />
              </div>
            </div>

            <div class="selected-summary" title="待校验为空表示本次没有上次未校验成功的文件">
              已选 <strong class="selected-summary__num">{{ selectedTaskIds.length }}</strong> 个任务 ·
              待校验 <strong class="selected-summary__num">{{ pendingTotal }}</strong> 个文件
            </div>

            <div class="selected-actions">
              <el-button
                :icon="RefreshLeft"
                :disabled="selectedTaskIds.length === 0 || starting"
                @click="clearSelection"
              >
                清空选择
              </el-button>
              <el-button
                type="primary"
                :icon="VideoPlay"
                :loading="starting"
                :disabled="!canStart"
                @click="handleStart"
              >
                启动任务
              </el-button>
            </div>
          </div>
        </section>
      </div>

      <!-- 正在执行 -->
      <section class="exec-running">
        <header class="exec-running__head">
          <div class="exec-running__heading">
            <h2 class="exec-running__title">正在执行</h2>
            <span class="exec-running__count">{{ active.length }}</span>
          </div>
          <el-button link :icon="Refresh" :loading="activeLoading" @click="loadActive">刷新</el-button>
        </header>
        <div class="exec-running__batch">
          <el-checkbox
            :model-value="allActiveSelected"
            :indeterminate="activeSelectedIds.length > 0 && !allActiveSelected"
            :disabled="active.length === 0"
            @change="onToggleAllActive"
          >
            全选
          </el-checkbox>
          <span class="exec-running__batch-info">已选 {{ activeSelectedIds.length }} / {{ active.length }}</span>
          <el-button
            type="danger"
            plain
            size="small"
            :icon="VideoPause"
            :disabled="activeSelectedIds.length === 0 || batchStopping"
            :loading="batchStopping"
            @click="stopSelected"
          >
            批量停止
          </el-button>
        </div>
        <el-table
          ref="activeTableRef"
          v-loading="activeLoading"
          :data="active"
          row-key="task_id"
          :max-height="320"
          class="exec-running__table"
          empty-text="暂无正在运行的自动追更"
          @selection-change="handleActiveSelectionChange"
        >
          <el-table-column type="selection" width="48" :reserve-selection="true" />
          <el-table-column label="任务" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">{{ row.task_name || taskName(row.task_id) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="180">
            <template #default="{ row }">
              <el-tag type="success" size="small" effect="light">{{ phaseText(row.task_id) }}</el-tag>
              <div class="exec-running__sub">下一轮：{{ nextRoundText(row.task_id) }}</div>
            </template>
          </el-table-column>
          <el-table-column label="轮次" width="90" align="right">
            <template #default="{ row }">
              <span class="exec-running__num">{{ row.round_no ?? '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="开始时间" width="172">
            <template #default="{ row }">{{ row.started_time ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openTaskRealtime(row.task_id)">查看日志</el-button>
              <el-button
                link
                type="danger"
                :icon="VideoPause"
                :loading="stoppingId === row.task_id"
                @click="stopTask(row.task_id)"
              >
                停止
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>
    </div>
  </div>
</template>

<style scoped lang="scss">
.exec-body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--up-strm-space-4);
  min-height: 0;
  padding-bottom: var(--up-strm-space-4);
  overflow-y: auto;
}

.exec-workspace {
  display: grid;
  flex: none;
  grid-template-columns: minmax(0, 1.6fr) minmax(300px, 0.9fr) minmax(280px, 1fr);
  gap: var(--up-strm-space-4);
  align-items: stretch;
  height: auto;
  min-height: clamp(380px, 52vh, 560px);
}

// 面板通用骨架
.exec-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: var(--up-strm-radius-lg);
  box-shadow: var(--up-strm-shadow-sm);

  &__head {
    display: flex;
    flex: none;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--up-strm-space-3);
    padding: var(--up-strm-space-4);
    border-bottom: 1px solid var(--el-border-color-lighter);
  }

  &__heading {
    min-width: 0;
  }

  &__title {
    margin: 0;
    color: var(--el-text-color-primary);
    font-size: var(--up-strm-font-size-lg);
    font-weight: 600;
    line-height: 1.4;
  }

  &__sub {
    margin: var(--up-strm-space-1) 0 0;
    color: var(--el-text-color-secondary);
    font-size: var(--up-strm-font-size-xs);
    line-height: 1.5;
  }

  &__count {
    flex: none;
    padding: 0 var(--up-strm-space-2);
    border-radius: var(--up-strm-radius-lg);
    background: var(--el-color-primary-light-9);
    color: var(--el-color-primary);
    font-size: var(--up-strm-font-size-xs);
    font-variant-numeric: tabular-nums;
    line-height: 1.5;
  }

  &__body {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--up-strm-space-3);
    min-height: 0;
    padding: var(--up-strm-space-4);
  }

  &__empty {
    margin: auto 0;
  }

  &__footer {
    display: flex;
    flex: none;
    align-items: center;
    justify-content: space-between;
    gap: var(--up-strm-space-3);
    padding-top: var(--up-strm-space-3);
    border-top: 1px solid var(--el-border-color-lighter);
  }

  &__footer-hint {
    color: var(--el-text-color-secondary);
    font-size: var(--up-strm-font-size-xs);
    line-height: 1.5;
  }

  &__footer-ops {
    display: flex;
    flex: none;
    align-items: center;
    gap: var(--up-strm-space-1);
  }
}

// 任务搜索
.task-filters {
  display: flex;
  flex: none;
  gap: var(--up-strm-space-2);

  &__search {
    flex: 1;
    min-width: 160px;
  }
}

// 任务复选列表
.task-list {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--up-strm-space-2);
  min-height: 0;
  overflow-y: auto;
  padding-right: var(--up-strm-space-1);
}

.task-row {
  display: flex;
  flex: none;
  align-items: center;
  gap: var(--up-strm-space-3);
  padding: var(--up-strm-space-3);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--up-strm-radius-md);
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease;

  &:hover {
    background: var(--el-fill-color-light);
  }

  &.is-selected {
    background: var(--el-color-primary-light-9);
    border-color: var(--el-color-primary-light-5);
  }

  &.is-running {
    background: var(--el-fill-color-light);
    cursor: not-allowed;
  }

  &__check {
    display: flex;
    flex: none;
    align-items: center;
  }

  &__info {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--up-strm-space-1);
    min-width: 0;
  }

  &__name {
    overflow: hidden;
    color: var(--el-text-color-primary);
    font-size: var(--up-strm-font-size-base);
    font-weight: 500;
    line-height: 1.5;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__path {
    overflow: hidden;
    color: var(--el-text-color-secondary);
    font-size: var(--up-strm-font-size-xs);
    line-height: 1.5;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__meta {
    display: flex;
    flex: none;
    align-items: center;
    gap: var(--up-strm-space-2);
  }

  &__count {
    color: var(--el-text-color-secondary);
    font-size: var(--up-strm-font-size-xs);
    font-variant-numeric: tabular-nums;
    line-height: 1.5;
    white-space: nowrap;
  }
}

// 执行参数
.exec-panel--params {
  .exec-panel__body {
    padding-right: var(--up-strm-space-4);
    padding-bottom: var(--up-strm-space-4);
    overflow-y: auto;
  }

  .param-block {
    display: flex;
    flex: none;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--up-strm-space-2);

    :deep(.el-input-number) {
      width: 100%;
    }

    &__label {
      color: var(--el-text-color-regular);
      font-size: var(--up-strm-font-size-sm);
      font-weight: 600;
    }

    &__hint {
      margin: 0;
      color: var(--el-text-color-secondary);
      font-size: var(--up-strm-font-size-xs);
      line-height: 1.6;
    }
  }

  .param-note {
    margin: var(--up-strm-space-3) 0 0;
    padding: var(--up-strm-space-3) 0 0;
    border-top: 1px solid var(--el-border-color-lighter);
    color: var(--el-text-color-secondary);
    font-size: var(--up-strm-font-size-xs);
    line-height: 1.6;
  }
}

// 正在执行
.exec-running {
  display: flex;
  flex: none;
  flex-direction: column;
  overflow: hidden;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: var(--up-strm-radius-lg);
  box-shadow: var(--up-strm-shadow-sm);

  &__head {
    display: flex;
    flex: none;
    align-items: center;
    justify-content: space-between;
    gap: var(--up-strm-space-3);
    padding: var(--up-strm-space-3) var(--up-strm-space-4);
    border-bottom: 1px solid var(--el-border-color-lighter);
  }

  &__heading {
    display: flex;
    align-items: center;
    gap: var(--up-strm-space-2);
  }

  &__title {
    margin: 0;
    color: var(--el-text-color-primary);
    font-size: var(--up-strm-font-size-lg);
    font-weight: 600;
    line-height: 1.4;
  }

  &__count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 20px;
    height: 20px;
    padding: 0 var(--up-strm-space-1);
    border-radius: var(--up-strm-radius-sm);
    background: var(--el-color-warning-light-9);
    color: var(--el-color-warning);
    font-size: var(--up-strm-font-size-xs);
    font-variant-numeric: tabular-nums;
  }

  &__num {
    color: var(--el-text-color-primary);
    font-variant-numeric: tabular-nums;
  }

  &__batch {
    display: flex;
    flex: none;
    align-items: center;
    gap: var(--up-strm-space-3);
    padding: var(--up-strm-space-2) var(--up-strm-space-4);
    border-bottom: 1px solid var(--el-border-color-lighter);
    background: var(--el-fill-color-lighter);
  }

  &__batch-info {
    margin-right: auto;
    color: var(--el-text-color-secondary);
    font-size: var(--up-strm-font-size-xs);
    font-variant-numeric: tabular-nums;
  }

  &__sub {
    color: var(--el-text-color-secondary);
    font-size: var(--up-strm-font-size-xs);
    line-height: 1.5;
  }

  &__table {
    :deep(th.el-table__cell) {
      height: 40px;
      padding: 0 var(--up-strm-space-3);
      background: var(--el-fill-color-light);
      color: var(--el-text-color-secondary);
      font-size: var(--up-strm-font-size-xs);
      font-weight: 600;
    }

    :deep(td.el-table__cell) {
      height: 40px;
      padding: 0 var(--up-strm-space-3);
      color: var(--el-text-color-regular);
      font-size: var(--up-strm-font-size-base);
    }
  }
}

// 已选任务卡片
.exec-panel--selected {
  .selected-list {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--up-strm-space-2);
    min-height: 0;
    overflow-y: auto;
    padding-right: var(--up-strm-space-1);
  }

  .selected-row {
    display: flex;
    flex: none;
    align-items: center;
    gap: var(--up-strm-space-2);
    padding: var(--up-strm-space-2) var(--up-strm-space-3);
    border: 1px solid var(--el-border-color-lighter);
    border-radius: var(--up-strm-radius-md);
    background: var(--el-fill-color-lighter);
  }

  .selected-row__info {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .selected-row__name {
    overflow: hidden;
    color: var(--el-text-color-primary);
    font-size: var(--up-strm-font-size-sm);
    font-weight: 500;
    line-height: 1.5;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .selected-row__path {
    overflow: hidden;
    color: var(--el-text-color-secondary);
    font-size: var(--up-strm-font-size-xs);
    line-height: 1.5;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .selected-summary {
    flex: none;
    padding-top: var(--up-strm-space-3);
    border-top: 1px solid var(--el-border-color-lighter);
    color: var(--el-text-color-regular);
    font-size: var(--up-strm-font-size-sm);
    line-height: 1.5;
  }

  .selected-summary__num {
    color: var(--el-text-color-primary);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  .selected-actions {
    display: flex;
    flex: none;
    justify-content: flex-end;
    gap: var(--up-strm-space-2);
  }
}

@media (max-width: 1280px) {
  .exec-workspace {
    grid-template-columns: minmax(0, 1fr);
    height: auto;
    min-height: 0;
  }

  .exec-panel {
    height: auto;
    min-height: 320px;
  }

  .task-list {
    max-height: min(40vh, 320px);
  }

  .exec-panel--selected .selected-list {
    max-height: 240px;
  }
}
</style>
