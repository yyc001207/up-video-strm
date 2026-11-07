<script setup lang="ts">
/**
 * 自动追更 · 运行详情（/automation/realtime）。
 *
 * 布局与「STRM 生成 · 运行详情」保持一致：顶部进度摘要（轮次 / 待校验 / 已校验 /
 * 缺失 / 状态 / 用时 / 当前任务）、日志工具条（级别过滤 / 关键字 / 行数 / 返回开始执行）、
 * 可复用日志终端（LogViewer）。
 *
 * 数据来源：按任务维度订阅 WS（automation:{task_id}），帧类型 log / progress / status，
 * 异常终止另有 alert 帧（网页通知）；连接建立后后端回放最近帧。
 * 任务未运行时自动回放最近一轮的日志文件，避免空白页。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElNotification } from 'element-plus'
import { Delete, FolderOpened, Refresh, Search } from '@element-plus/icons-vue'

import { automationApi, automationRunApi } from '@/api/automation'
import { desktopApi } from '@/api/desktop'
import StatusDot from '@/components/StatusDot.vue'
import LogViewer from '@/components/LogViewer.vue'
import { connectAutomationWs, disconnectWs, type WsState } from '@/utils/ws'
import { beijingMillis } from '@/utils/date'
import { AUTOMATION_RUN_STATUS_LABELS, CONNECTION_META, PHASE_LABELS } from '@/utils/status'
import type { AutomationTask, AutomationWsFrame } from '@/types/automation'

interface LogLine {
  seq: number
  level: string
  ts?: string
  message: string
}

type FilterLevel = 'all' | 'info' | 'warn' | 'error'
type AutomationStatus = 'running' | 'success' | 'partial' | 'fail' | 'cancelled'

const MAX_LOG_LINES = 3000

const route = useRoute()
const router = useRouter()

const tasks = ref<AutomationTask[]>([])
const taskId = ref<number | null>(null)
const socket = ref<WebSocket | null>(null)
const connectionState = ref<WsState>('disconnected')
const logLines = ref<LogLine[]>([])
const nextSeq = ref(1)
const autoScroll = ref(true)
const levelFilter = ref<FilterLevel>('all')
const keyword = ref('')
const opening = ref(false)

const roundNo = ref(0)
const phase = ref('')
const pendingCount = ref(0)
const checkedCount = ref(0)
const missedCount = ref(0)
const finalStatus = ref<AutomationStatus | null>(null)
const startedAt = ref<number | null>(null)
const now = ref(Date.now())

let timer: ReturnType<typeof setInterval> | null = null
let disposed = false

const currentTask = computed(() => tasks.value.find(item => item.id === taskId.value) ?? null)
const connectionMeta = computed(() => CONNECTION_META[connectionState.value])
/** 未连接（无运行中任务可订阅）时：清空日志、禁用筛选控件，并展示「无运行中任务」。 */
const notConnected = computed(() => connectionState.value === 'disconnected')

const currentStatus = computed<AutomationStatus>(() => finalStatus.value ?? 'running')
/** StatusDot 只接受 A/B 的四种终态；自动化「部分成功」按失败着色展示。 */
const statusDotStatus = computed(() => (currentStatus.value === 'partial' ? 'fail' : currentStatus.value))
const statusText = computed(() => {
  if (taskId.value === null) return '—'
  if (finalStatus.value !== null) return AUTOMATION_RUN_STATUS_LABELS[finalStatus.value]
  if (currentTask.value?.is_running || connectionState.value === 'connected') return '运行中'
  return '未运行'
})
const showStatus = computed(
  () => taskId.value !== null && (finalStatus.value !== null || currentTask.value?.is_running === true || connectionState.value === 'connected')
)

const phaseText = computed(() => (phase.value === '' ? '—' : PHASE_LABELS[phase.value] ?? phase.value))

const elapsedText = computed(() => {
  const start = startedAt.value
  if (start === null) return '—'
  const seconds = Math.max(0, Math.floor(((finalStatus.value !== null ? now.value : now.value) - start) / 1000))
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const rest = seconds % 60
  const mm = String(minutes).padStart(2, '0')
  const ss = String(rest).padStart(2, '0')
  return hours > 0 ? `${hours}:${mm}:${ss}` : `${mm}:${ss}`
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

const emptyText = computed(() => {
  if (taskId.value === null) return '请选择要查看的自动追更'
  if (connectionState.value === 'connecting') return '正在连接运行详情…'
  if (finalStatus.value !== null) return '本轮已结束，可前往「运行记录」查看完整日志'
  if (currentTask.value?.is_running) return '等待任务输出日志…'
  return '任务当前未运行，可前往「运行记录」查看最近一轮日志'
})

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

function onFrame(frame: AutomationWsFrame): void {
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
    if (frame.phase) phase.value = frame.phase
    if (typeof frame.round_no === 'number') roundNo.value = frame.round_no
    if (typeof frame.pending === 'number') pendingCount.value = frame.pending
    if (typeof frame.checked === 'number') checkedCount.value = frame.checked
    if (typeof frame.missed === 'number') missedCount.value = frame.missed
    if (isTerminalStatus(frame.status)) handleRoundEnd(frame.status)
    return
  }
  ElNotification({
    title: '自动追更异常终止',
    message: frame.message,
    type: 'error',
    duration: 0
  })
}

function isTerminalStatus(value: string | undefined): value is AutomationStatus {
  return value === 'success' || value === 'partial' || value === 'fail' || value === 'cancelled'
}

function handleRoundEnd(status: AutomationStatus): void {
  finalStatus.value = status
  disconnect()
  void loadTasks(true)
  ElMessage.info(
    status === 'success' ? '本轮执行完成，可前往「运行记录」查看日志' : '本轮执行已结束，可前往「运行记录」查看日志'
  )
}

function disconnect(): void {
  if (socket.value !== null) {
    disconnectWs(socket.value)
    socket.value = null
  }
  connectionState.value = 'disconnected'
}

function connect(): void {
  disconnect()
  if (taskId.value === null) return
  finalStatus.value = null
  connectionState.value = 'connecting'
  socket.value = connectAutomationWs(taskId.value, {
    onMessage: onFrame,
    onOpen: () => {
      connectionState.value = 'connected'
    },
    onClose: () => {
      socket.value = null
      connectionState.value = 'disconnected'
      if (finalStatus.value === null && taskId.value !== null) {
        ElMessage.warning('运行详情连接已断开，可点击「重新连接」')
      }
    },
    onError: () => {
      connectionState.value = 'disconnected'
    }
  })
}

async function loadTasks(silent = false): Promise<void> {
  try {
    const res = await automationApi.listTasks({ page: 1, page_size: 100 })
    tasks.value = res.data ?? []
    if (taskId.value !== null && !tasks.value.some(item => item.id === taskId.value)) {
      taskId.value = null
    }
  } catch {
    if (!silent) throw new Error('load tasks failed')
  }
}

/** 连接前刷新一次运行状态：运行中则订阅 WS，否则回放最近一轮日志。 */
async function openTask(id: number): Promise<void> {
  resetLogs()
  roundNo.value = 0
  phase.value = ''
  pendingCount.value = 0
  checkedCount.value = 0
  missedCount.value = 0
  finalStatus.value = null
  startedAt.value = null
  if (disposed) return

  try {
    const res = await automationRunApi.active()
    const state = (res.data ?? []).find(item => item.task_id === id)
    if (state?.started_time) startedAt.value = beijingMillis(state.started_time)
    if (state) {
      if (state.phase) phase.value = state.phase
      if (typeof state.round_no === 'number') roundNo.value = state.round_no
    }
  } catch {
    /* 拦截器已提示，保持无运行状态 */
  }

  const task = tasks.value.find(item => item.id === id)
  if (task?.is_running) {
    connect()
    return
  }
  // 任务未运行：不订阅 WS、不回放历史日志；页面保持「无运行中任务」空态，历史日志请到运行记录查看。
}

/** 重连：运行中重新订阅 WS；未运行时刷新任务状态并提示「无运行中任务」。 */
function handleReconnect(): void {
  if (taskId.value === null) return
  const task = tasks.value.find(item => item.id === taskId.value)
  if (task?.is_running) {
    connect()
    return
  }
  ElMessage.info('当前没有运行中的任务，历史日志请到「运行记录」查看')
  void loadTasks(true)
}

function handleClear(): void {
  resetLogs()
}

async function handleOpenLogDir(): Promise<void> {
  if (opening.value) return
  opening.value = true
  try {
    await desktopApi.openLogDir('automation')
    ElMessage.success('已打开日志文件夹')
  } catch {
    /* 拦截器已提示 */
  } finally {
    opening.value = false
  }
}

function handleBackToExecution(): void {
  void router.push('/automation/execution')
}

watch(taskId, id => {
  disconnect()
  if (id !== null) void openTask(id)
})

/** 断线（含任务不存在/本轮结束）后立即清空日志区域，避免残留上一任务的日志。 */
watch(connectionState, state => {
  if (state === 'disconnected') resetLogs()
})

onMounted(async () => {
  timer = setInterval(() => {
    now.value = Date.now()
  }, 1000)

  try {
    await loadTasks()
  } catch {
    return
  }
  if (disposed) return
  const queryTaskId = Number(route.query.task_id)
  if (Number.isInteger(queryTaskId) && queryTaskId > 0 && tasks.value.some(item => item.id === queryTaskId)) {
    taskId.value = queryTaskId
  } else {
    taskId.value = tasks.value.find(item => item.is_running)?.id ?? tasks.value[0]?.id ?? null
  }
})

onBeforeUnmount(() => {
  disposed = true
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
  disconnect()
})
</script>

<template>
  <div class="page realtime-page">
    <p class="realtime-page__desc">
      本页实时显示所选自动追更每一轮链路的日志与阶段；启动任务后会自动跳转到本页。可通过日志级别与关键字过滤日志；本轮结束后可前往「运行记录」查看完整记录。
    </p>

    <div class="realtime-toolbar">
      <div class="realtime-toolbar__left">
        <el-select
          v-model="taskId"
          class="realtime-toolbar__selector"
          placeholder="选择自动追更"
          filterable
          :disabled="tasks.length === 0 || notConnected"
        >
          <el-option
            v-for="task in tasks"
            :key="task.id"
            :label="`${task.name}${task.is_running ? '（运行中）' : ''}`"
            :value="task.id"
          />
        </el-select>
        <el-tag :type="connectionMeta.tone" size="small" disable-transitions>
          {{ connectionMeta.label }}
        </el-tag>
        <StatusDot v-if="!notConnected && showStatus" :status="statusDotStatus" />
        <el-tag v-else type="info" size="small" disable-transitions>无运行中任务</el-tag>
      </div>
      <div class="realtime-toolbar__right">
        <el-button :icon="Refresh" @click="handleReconnect">重连</el-button>
        <el-button :icon="Delete" :disabled="notConnected" @click="handleClear">清空</el-button>
        <el-button :icon="FolderOpened" :loading="opening" @click="handleOpenLogDir">
          打开日志文件夹
        </el-button>
      </div>
    </div>

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
        <span class="progress-card__value progress-card__value--text">{{ phaseText }}</span>
      </div>
      <div class="progress-card__item">
        <span class="progress-card__label">执行状态</span>
        <span class="progress-card__value progress-card__value--text">{{ statusText }}</span>
      </div>
      <div class="progress-card__item progress-card__item--wide">
        <span class="progress-card__label">用时 / 当前任务</span>
        <span class="progress-card__value progress-card__value--mono">
          {{ elapsedText }} · {{ currentTask?.name || '—' }}
        </span>
      </div>
    </div>

    <div class="log-toolbar">
      <div class="log-toolbar__left">
        <el-select v-model="levelFilter" size="small" class="log-toolbar__level" :disabled="notConnected">
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
          :disabled="notConnected"
        />
        <span class="log-toolbar__count">{{ filteredLines.length }} 行</span>
      </div>
      <div class="log-toolbar__right">
        <el-button v-if="taskId !== null" size="small" @click="handleBackToExecution">
          返回开始执行
        </el-button>
      </div>
    </div>

    <div class="log-area">
      <LogViewer
        v-model:auto-scroll="autoScroll"
        :lines="filteredLines"
        :max-lines="MAX_LOG_LINES"
        :empty-text="emptyText"
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
