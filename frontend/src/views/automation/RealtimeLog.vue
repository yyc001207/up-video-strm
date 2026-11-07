<script setup lang="ts">
/**
 * 自动追更 · 运行详情（/automation/realtime）。
 *
 * 状态分三层，页面并列展示、互不冒充（推导见 `@/utils/automationState`）：
 * - 任务层：`GET /api/automation/active`（5s 轮询）→ 任务是否在跑、当前阶段、下一轮时间；
 * - 本轮层：WS live 帧 + 终态后 `GET /runs/{run_id}` → 轮次状态、计数、失败原因；
 * - 连接层：WS 连接状态 + 自动重连 → 只表达连接本身。
 *
 * 后端回放的历史帧带 `replay: true`，本页直接丢弃，避免把上一轮的终态当成本轮结束；
 * 最近一轮日志通过「查看最近一轮」按钮显式加载。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElNotification } from 'element-plus'
import { Clock, Delete, FolderOpened, Refresh, Search } from '@element-plus/icons-vue'

import { automationApi, automationRunApi } from '@/api/automation'
import LogViewer from '@/components/LogViewer.vue'
import { useLogDir } from '@/composables/useLogDir'
import { usePolling } from '@/composables/usePolling'
import { connectAutomationWs, disconnectWs, type WsState } from '@/utils/ws'
import { beijingMillis } from '@/utils/date'
import { clockText } from '@/utils/format'
import { deriveRunDetailView } from '@/utils/automationState'
import type { AutomationRunStatus, AutomationRuntimeState, AutomationTask, AutomationWsFrame } from '@/types/automation'

interface LogLine {
  seq: number
  level: string
  ts?: string
  message: string
}

type FilterLevel = 'all' | 'info' | 'warn' | 'error'

const MAX_LOG_LINES = 3000
const RUNTIME_POLL_MS = 5000
const RECONNECT_DELAYS = [1000, 3000, 5000, 5000, 5000]
const MAX_RECONNECT_ATTEMPTS = RECONNECT_DELAYS.length

const route = useRoute()
const router = useRouter()

const tasks = ref<AutomationTask[]>([])
const taskId = ref<number | null>(null)
const socket = ref<WebSocket | null>(null)
const connectionState = ref<WsState>('disconnected')
const reconnecting = ref(false)
const logLines = ref<LogLine[]>([])
const nextSeq = ref(1)
const autoScroll = ref(true)
const levelFilter = ref<FilterLevel>('all')
const keyword = ref('')
const loadingLatest = ref(false)

/** 任务层：运行态快照。 */
const runtime = ref<AutomationRuntimeState | null>(null)
/** 本轮层：当前/最近一轮。 */
const roundNo = ref(0)
const roundPhase = ref('')
const roundStatus = ref<AutomationRunStatus | null>(null)
const pendingCount = ref(0)
const checkedCount = ref(0)
const missedCount = ref(0)
const errorMessage = ref<string | null>(null)
const startedAt = ref<number | null>(null)
const now = ref(Date.now())

let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let reconnectAttempts = 0
let lastEndedRunId: number | null = null
let disposed = false

const currentTask = computed(() => tasks.value.find(item => item.id === taskId.value) ?? null)

const view = computed(() =>
  deriveRunDetailView({
    selected: taskId.value !== null,
    runtime: runtime.value,
    connection: connectionState.value,
    reconnecting: reconnecting.value,
    round: {
      status: roundStatus.value,
      phase: roundPhase.value === '' ? null : roundPhase.value,
      roundNo: roundNo.value,
      pending: pendingCount.value,
      checked: checkedCount.value,
      missed: missedCount.value
    }
  })
)

const elapsedText = computed(() => {
  const start = startedAt.value
  if (start === null) return '—'
  return clockText(Math.max(0, Math.floor((now.value - start) / 1000)))
})

const filteredLines = computed<LogLine[]>(() => {
  const level = levelFilter.value
  const needle = keyword.value.trim().toLowerCase()
  return logLines.value.filter(line => {
    if (level !== 'all') {
      // progress 级别的日志在过滤时归入 info，避免被「信息」过滤漏掉。
      const effective = line.level === 'progress' ? 'info' : line.level
      if (effective !== level) return false
    }
    if (needle !== '' && !line.message.toLowerCase().includes(needle)) return false
    return true
  })
})

const controlsDisabled = computed(() => taskId.value === null)

function resetLogs(): void {
  logLines.value = []
  nextSeq.value = 1
}

function appendLine(level: string, message: string, ts?: string): void {
  logLines.value.push({ seq: nextSeq.value, level, ts: formatLogTime(ts), message })
  nextSeq.value += 1
  if (logLines.value.length > MAX_LOG_LINES) {
    logLines.value.splice(0, logLines.value.length - MAX_LOG_LINES)
  }
}

/** 后端日志 ts 为 'YYYY-MM-DD HH:MM:SS'，终端内只展示时间部分。 */
function formatLogTime(value: string | undefined): string | undefined {
  if (value === undefined || value === '') return undefined
  const match = /(\d{2}:\d{2}:\d{2})/.exec(value)
  return match === null ? undefined : match[1]
}

function isTerminalStatus(value: string | undefined): value is AutomationRunStatus {
  return value === 'success' || value === 'partial' || value === 'fail' || value === 'cancelled'
}

function onFrame(frame: AutomationWsFrame): void {
  // 回放帧是上一轮的历史状态，丢弃，避免误判「本轮已结束」。
  if (frame.replay === true) return
  if (frame.type === 'log') {
    appendLine(frame.level || 'info', frame.message, frame.ts)
    return
  }
  if (frame.type === 'progress') {
    const data = frame.data ?? {}
    if (typeof data.pending === 'number') pendingCount.value = data.pending
    if (typeof data.checked === 'number') checkedCount.value = data.checked
    return
  }
  if (frame.type === 'status') {
    if (frame.phase) roundPhase.value = frame.phase
    if (typeof frame.round_no === 'number') roundNo.value = frame.round_no
    if (typeof frame.pending === 'number') pendingCount.value = frame.pending
    if (typeof frame.checked === 'number') checkedCount.value = frame.checked
    if (typeof frame.missed === 'number') missedCount.value = frame.missed
    if (isTerminalStatus(frame.status)) {
      handleRoundEnd(frame)
    }
    return
  }
  ElNotification({
    title: '自动追更异常终止',
    message: frame.message,
    type: 'error',
    duration: 0
  })
}

/** 单轮结束：记录终态明细，但不断开连接（任务可能仍在循环）。 */
function handleRoundEnd(frame: Extract<AutomationWsFrame, { type: 'status' }>): void {
  const status = frame.status as AutomationRunStatus
  roundStatus.value = status
  if (typeof frame.round_no === 'number') roundNo.value = frame.round_no
  if (typeof frame.missed === 'number') missedCount.value = frame.missed
  if (frame.error_message) errorMessage.value = frame.error_message
  const runId = frame.run_id ?? null
  if (runId !== null && lastEndedRunId !== runId) {
    lastEndedRunId = runId
    void loadRunDetail(runId)
    ElMessage.info(status === 'success' ? '本轮执行完成，等待下一轮' : '本轮执行结束，正在等待下一轮或退避重试')
  }
  // 任务循环仍在继续：刷新快照以拿到下一轮时间/新阶段，连接保持不变。
  void refreshRuntime()
}

async function loadRunDetail(runId: number): Promise<void> {
  try {
    const res = await automationRunApi.getRun(runId)
    const detail = res.data
    if (detail === undefined || detail === null) return
    if (typeof detail.round_no === 'number') roundNo.value = detail.round_no
    if (isTerminalStatus(detail.status)) roundStatus.value = detail.status
    if (typeof detail.pending_file_count === 'number') pendingCount.value = detail.pending_file_count
    if (typeof detail.checked_file_count === 'number') checkedCount.value = detail.checked_file_count
    if (Array.isArray(detail.missed_files)) missedCount.value = detail.missed_files.length
    errorMessage.value = detail.error_message ?? null
  } catch {
    /* 拦截器已提示；保留 WS 帧里的字段 */
  }
}

async function refreshRuntime(): Promise<void> {
  if (taskId.value === null) return
  try {
    const res = await automationRunApi.active()
    const state = (res.data ?? []).find(item => item.task_id === taskId.value) ?? null
    runtime.value = state
    if (state?.started_time) startedAt.value = beijingMillis(state.started_time)
  } catch {
    /* 轮询失败不打断页面；保持当前快照 */
  }
}

async function loadTasks(silent = false): Promise<void> {
  try {
    const res = await automationApi.listTasks({ page: 1, page_size: 100 })
    tasks.value = res.data ?? []
    if (taskId.value !== null && !tasks.value.some(item => item.id === taskId.value)) {
      taskId.value = null
    }
  } catch {
    if (!silent) ElMessage.error('加载自动追更任务失败')
  }
}

function clearReconnectTimer(): void {
  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

function disconnectSocket(): void {
  clearReconnectTimer()
  reconnecting.value = false
  if (socket.value !== null) {
    disconnectWs(socket.value)
    socket.value = null
  }
  connectionState.value = 'disconnected'
}

/** 连接断开时：任务仍在运行则按 1s/3s/5s 自动重连（最多 5 次）。 */
function scheduleReconnect(): void {
  if (disposed || taskId.value === null || runtime.value === null) return
  if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    reconnecting.value = false
    ElMessage.warning('运行详情连接已断开，可点击「重连」重试')
    return
  }
  const delay = RECONNECT_DELAYS[reconnectAttempts]
  reconnectAttempts += 1
  reconnecting.value = true
  clearReconnectTimer()
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    if (disposed || taskId.value === null) return
    void refreshRuntime().then(() => {
      if (runtime.value !== null) subscribe()
    })
  }, delay)
}

function subscribe(): void {
  if (taskId.value === null) return
  clearReconnectTimer()
  if (socket.value !== null) {
    disconnectWs(socket.value)
    socket.value = null
  }
  connectionState.value = 'connecting'
  socket.value = connectAutomationWs(taskId.value, {
    onMessage: onFrame,
    onOpen: () => {
      connectionState.value = 'connected'
      reconnecting.value = false
      reconnectAttempts = 0
    },
    onClose: () => {
      socket.value = null
      connectionState.value = 'disconnected'
      if (disposed) return
      scheduleReconnect()
    },
    onError: () => {
      connectionState.value = 'disconnected'
    }
  })
}

function resetRoundState(): void {
  runtime.value = null
  roundNo.value = 0
  roundPhase.value = ''
  roundStatus.value = null
  pendingCount.value = 0
  checkedCount.value = 0
  missedCount.value = 0
  errorMessage.value = null
  startedAt.value = null
  lastEndedRunId = null
  reconnectAttempts = 0
  resetLogs()
}

/** 选择任务后：先取运行快照，任务在运行则订阅 WS；否则保持空态并允许查看最近一轮。 */
async function openTask(): Promise<void> {
  if (disposed) return
  await Promise.all([refreshRuntime(), loadTasks(true)])
  if (disposed) return
  if (runtime.value !== null || currentTask.value?.is_running === true) {
    subscribe()
    return
  }
  disconnectSocket()
}

/** 显式加载最近一轮日志（替代旧的自动回放）。 */
async function loadLatestRound(): Promise<void> {
  if (taskId.value === null || loadingLatest.value) return
  loadingLatest.value = true
  try {
    const res = await automationRunApi.listRuns({ task_id: taskId.value, page: 1, page_size: 1 })
    const latest = (res.data ?? [])[0]
    if (latest === undefined) {
      ElMessage.info('还没有运行记录')
      return
    }
    const logs = await automationRunApi.runLogs(latest.id, 0, 2000)
    resetLogs()
    appendLine('info', `—— 第 ${latest.round_no} 轮历史日志（${latest.status}）——`)
    for (const line of logs.data.lines) {
      appendLine(line.level, line.message)
    }
    if (isTerminalStatus(latest.status)) roundStatus.value = latest.status
    roundNo.value = latest.round_no
    errorMessage.value = latest.error_message ?? null
    ElMessage.success(`已加载第 ${latest.round_no} 轮日志`)
  } catch {
    /* 拦截器已提示 */
  } finally {
    loadingLatest.value = false
  }
}

function handleReconnect(): void {
  if (taskId.value === null) return
  clearReconnectTimer()
  reconnectAttempts = 0
  void refreshRuntime().then(() => {
    if (runtime.value !== null) {
      subscribe()
    } else {
      ElMessage.info('任务当前未运行，可点击「查看最近一轮」或前往「运行记录」')
    }
  })
}

function handleClear(): void {
  resetLogs()
}

const { open: openLogDir } = useLogDir('automation')
const openingLogDir = ref(false)
async function handleOpenLogDir(): Promise<void> {
  openingLogDir.value = true
  try {
    await openLogDir()
  } finally {
    openingLogDir.value = false
  }
}

function handleBackToExecution(): void {
  void router.push('/automation/execution')
}

watch(taskId, id => {
  disconnectSocket()
  resetRoundState()
  if (id !== null) void openTask()
})

/** 任务停止后（快照变空）主动断开连接；轮次结束不在这里。 */
watch(runtime, value => {
  if (value === null && connectionState.value === 'connected') {
    disconnectSocket()
  }
})

const runtimePoll = usePolling(refreshRuntime, { interval: RUNTIME_POLL_MS, visibleOnly: true })
const clockPoll = usePolling(
  () => {
    now.value = Date.now()
  },
  { interval: 1000, visibleOnly: false }
)

onMounted(async () => {
  await loadTasks(true)
  if (disposed) return
  const queryTaskId = Number(route.query.task_id)
  const preferred =
    Number.isInteger(queryTaskId) && queryTaskId > 0 && tasks.value.some(item => item.id === queryTaskId)
      ? queryTaskId
      : (tasks.value.find(item => item.is_running)?.id ?? tasks.value[0]?.id ?? null)
  runtimePoll.start()
  clockPoll.start()
  taskId.value = preferred
})

onBeforeUnmount(() => {
  disposed = true
  runtimePoll.stop()
  clockPoll.stop()
  disconnectSocket()
})
</script>

<template>
  <div class="page realtime-page">
    <p class="realtime-page__desc">
      本页并列显示任务状态（运行中 / 已停止）、本轮状态与 WS 连接状态；三者互不冒充。任务循环运行期间页面保持连接并自动进入下一轮；需要历史日志时点击「查看最近一轮」。
    </p>

    <div class="realtime-toolbar">
      <div class="realtime-toolbar__left">
        <el-select
          v-model="taskId"
          class="realtime-toolbar__selector"
          placeholder="选择自动追更"
          filterable
          :disabled="tasks.length === 0"
        >
          <el-option
            v-for="task in tasks"
            :key="task.id"
            :label="`${task.name}${task.is_running ? '（运行中）' : ''}`"
            :value="task.id"
          />
        </el-select>
        <el-tag :type="view.taskTone" size="small" disable-transitions>{{ view.taskLabel }}</el-tag>
        <el-tag :type="view.roundTone" size="small" disable-transitions effect="plain">
          {{ view.roundLabel }}
        </el-tag>
        <el-tag :type="view.connectionTone" size="small" disable-transitions>{{ view.connectionLabel }}</el-tag>
      </div>
      <div class="realtime-toolbar__right">
        <el-button :icon="Refresh" :disabled="!view.canReconnect" @click="handleReconnect">重连</el-button>
        <el-button :icon="Clock" :loading="loadingLatest" :disabled="controlsDisabled" @click="loadLatestRound">
          查看最近一轮
        </el-button>
        <el-button :icon="Delete" :disabled="controlsDisabled" @click="handleClear">清空</el-button>
        <el-button :icon="FolderOpened" :loading="openingLogDir" @click="handleOpenLogDir">打开日志文件夹</el-button>
      </div>
    </div>

    <el-alert
      v-if="errorMessage"
      class="realtime-alert"
      type="error"
      :title="`本轮失败：${errorMessage}`"
      :closable="false"
      show-icon
    />

    <div class="progress-card">
      <div class="progress-card__item">
        <span class="progress-card__label">当前轮次</span>
        <span class="progress-card__value">{{ roundNo || '—' }}</span>
      </div>
      <div class="progress-card__item">
        <span class="progress-card__label">待校验</span>
        <span class="progress-card__value">{{ pendingCount }}</span>
      </div>
      <div class="progress-card__item">
        <span class="progress-card__label">已校验</span>
        <span class="progress-card__value progress-card__value--success">{{ checkedCount }}</span>
      </div>
      <div class="progress-card__item">
        <span class="progress-card__label">缺失文件</span>
        <span class="progress-card__value" :class="{ 'progress-card__value--danger': missedCount > 0 }">
          {{ missedCount }}
        </span>
      </div>
      <div class="progress-card__item">
        <span class="progress-card__label">当前阶段</span>
        <span class="progress-card__value progress-card__value--text">{{ view.phaseLabel }}</span>
      </div>
      <div class="progress-card__item">
        <span class="progress-card__label">本轮状态</span>
        <span class="progress-card__value progress-card__value--text">{{ view.roundLabel }}</span>
      </div>
      <div class="progress-card__item progress-card__item--wide">
        <span class="progress-card__label">用时 / 下一轮</span>
        <span class="progress-card__value progress-card__value--mono">
          {{ elapsedText }} · {{ view.nextRoundText || '—' }} · {{ currentTask?.name || '—' }}
        </span>
      </div>
    </div>

    <div class="log-toolbar">
      <div class="log-toolbar__left">
        <el-select v-model="levelFilter" size="small" class="log-toolbar__level" :disabled="controlsDisabled">
          <el-option label="全部级别" value="all" />
          <el-option label="信息" value="info" />
          <el-option label="警告" value="warn" />
          <el-option label="错误" value="error" />
        </el-select>
        <el-input
          v-model="keyword"
          class="log-toolbar__keyword"
          size="small"
          placeholder="筛选关键字"
          clearable
          :prefix-icon="Search"
          :disabled="controlsDisabled"
        />
        <span class="log-toolbar__count">{{ filteredLines.length }} 行</span>
      </div>
      <div class="log-toolbar__right">
        <el-button v-if="taskId !== null" size="small" @click="handleBackToExecution">返回开始执行</el-button>
      </div>
    </div>

    <div class="log-area">
      <LogViewer
        v-model:auto-scroll="autoScroll"
        :lines="filteredLines"
        :max-lines="MAX_LOG_LINES"
        :empty-text="view.emptyText"
      />
    </div>
  </div>
</template>

<style scoped lang="scss">
.realtime-page {
  display: flex;
  flex-direction: column;
  gap: var(--up-strm-space-3, 12px);
  min-height: 0;
  height: 100%;

  &__desc {
    flex: none;
    margin: 0;
    font-size: var(--up-strm-font-size-xs, 12px);
    line-height: 1.6;
    color: var(--el-text-color-secondary);
  }
}

.realtime-toolbar,
.log-toolbar {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--up-strm-space-2, 8px);
  flex-wrap: wrap;

  &__left,
  &__right {
    display: flex;
    align-items: center;
    gap: var(--up-strm-space-2, 8px);
    flex-wrap: wrap;
  }
}

.realtime-toolbar__selector {
  width: 260px;
  max-width: 100%;
}

.realtime-alert {
  flex: none;
}

.progress-card {
  flex: none;
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr)) minmax(0, 1.6fr);
  gap: var(--up-strm-space-2, 8px);
  padding: var(--up-strm-space-3, 12px) var(--up-strm-space-4, 16px);
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--up-strm-radius-md, 8px);

  &__item {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  &__label {
    font-size: var(--up-strm-font-size-xs, 12px);
    color: var(--el-text-color-secondary);
  }

  &__value {
    font-size: var(--up-strm-font-size-lg, 16px);
    font-weight: 600;
    color: var(--el-text-color-primary);
    font-variant-numeric: tabular-nums;

    &--success {
      color: var(--el-color-success);
    }

    &--danger {
      color: var(--el-color-danger);
    }

    &--text {
      overflow: hidden;
      font-size: var(--up-strm-font-size-sm, 13px);
      font-weight: 500;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    &--mono {
      font-family: 'JetBrains Mono', Consolas, monospace;
      font-size: var(--up-strm-font-size-xs, 12px);
      font-weight: 500;
      color: var(--el-text-color-regular);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }
}

.log-toolbar__level {
  width: 128px;
}

.log-toolbar__keyword {
  width: 220px;
  max-width: 100%;
}

.log-toolbar__count {
  font-size: var(--up-strm-font-size-xs, 12px);
  color: var(--el-text-color-secondary);
  font-variant-numeric: tabular-nums;
}

.log-area {
  flex: 1;
  min-height: 0;
}

@media (max-width: 1100px) {
  .progress-card {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .progress-card__item--wide {
    grid-column: span 3;
  }
}
</style>
