<script setup lang="ts">
/**
 * 实时日志（/schedule/realtime）
 *
 * 三段式布局：顶部进度摘要（状态 / 连接状态 / 视频与字幕进度 / 耗时）、
 * 日志工具条（级别过滤 / 关键字 / 清屏 / 下载）、可复用日志终端（LogViewer）。
 *
 * 启动时序（与旧实现保持一致）：路由 query 传入 `execs` 与 `server`；
 * launch=true 的执行先建立 WebSocket（可先看到启动前的日志），连接建立后再调用
 * store.startExecution({ execution_id, task_id }) 真正启动任务；
 * launch=false 的执行只连接查看已运行的日志，不触发启动。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Delete, Download, Refresh, Search } from '@element-plus/icons-vue'

import StatusDot from '@/components/StatusDot.vue'
import LogViewer from '@/components/LogViewer.vue'
import { connectWs, disconnectWs, type WsState } from '@/utils/ws'
import { beijingMillis } from '@/utils/date'
import { openlistApi } from '@/api/openlist'
import type {
  ExecutionStatus,
  OpenListExecution,
  WsFrame,
  WsLogFrame,
  WsProgressFrame,
  WsStatusFrame
} from '@/types/openlist'
import { useOpenlistStore } from '@/stores/openlist'

/** 单条日志（与 LogViewer 的 LogLine 契约一致）。 */
interface LogLine {
  seq: number
  level: string
  ts?: string
  message: string
}

/** 路由 query 中的执行项（由「执行管理」页跳转时传入）。 */
interface QueryExecution {
  executionId: number
  taskId: number | null
  taskName: string
  launch: boolean
}

/** 已解析出的连接目标（taskId 已在必要时回退到运行记录）。 */
interface OpenTarget {
  executionId: number
  taskId: number
  taskName: string
  launch: boolean
  running: OpenListExecution | undefined
}

/** 等待 WebSocket 建立后再启动的启动参数。 */
interface PendingLaunch {
  executionId: number
  taskId: number
}

type ProgressSnapshot = WsProgressFrame['data']

type FilterLevel = 'all' | 'info' | 'warn' | 'error'

/** 本地日志上限（与 LogViewer 默认值保持一致）。 */
const MAX_LOG_LINES = 3000

/**
 * 已启动执行的持久化 key：刷新页面时避免对同一批执行重复调用 start（后端无防重）。
 * 使用 sessionStorage，仅当前标签页有效。
 */
const LAUNCHED_STORAGE_KEY = 'up-strm:launched-executions'

const CONNECTION_META: Record<WsState, { label: string; tone: 'info' | 'success' | 'danger' }> = {
  connecting: { label: '连接中', tone: 'info' },
  connected: { label: '已连接', tone: 'success' },
  disconnected: { label: '未连接', tone: 'danger' }
}

const route = useRoute()
const store = useOpenlistStore()

const socket = ref<WebSocket | null>(null)
const connectionState = ref<WsState>('disconnected')
const selectedExecutionId = ref<number | null>(null)
const selectedExecutionName = ref('')
/** 已真正启动过的执行，避免切换 / 刷新 / 重连时重复启动（后端创建记录即为 running，无法据此判断）。 */
const launchedIds = ref<number[]>(loadLaunchedIds())
const pendingLaunch = ref<PendingLaunch | null>(null)
const launching = ref(false)
const batchExecutions = ref<QueryExecution[]>([])

const logLines = ref<LogLine[]>([])
const nextSeq = ref(1)
const autoScroll = ref(true)
const levelFilter = ref<FilterLevel>('all')
const keyword = ref('')
const downloading = ref(false)

const progress = ref<ProgressSnapshot>({
  totalVideos: 0,
  successVideos: 0,
  totalSubtitles: 0,
  successSubtitles: 0
})
const finalStatus = ref<ExecutionStatus | null>(null)
const startedAt = ref<number | null>(null)
const finishedAt = ref<number | null>(null)
const now = ref(Date.now())

let timer: ReturnType<typeof setInterval> | null = null
/** 组件已卸载标记：避免异步初始化在卸载后仍建立连接 / 改写状态。 */
let disposed = false

function emptyProgress(): ProgressSnapshot {
  return { totalVideos: 0, successVideos: 0, totalSubtitles: 0, successSubtitles: 0 }
}

function toNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function loadLaunchedIds(): number[] {
  try {
    const raw = sessionStorage.getItem(LAUNCHED_STORAGE_KEY)
    if (raw === null) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    const ids: number[] = []
    for (const value of parsed) {
      const id = toNumber(value)
      if (id !== null) ids.push(id)
    }
    return ids
  } catch {
    return []
  }
}

function persistLaunchedIds(): void {
  try {
    sessionStorage.setItem(LAUNCHED_STORAGE_KEY, JSON.stringify(launchedIds.value))
  } catch {
    /* 存储不可用时忽略，只影响刷新后的去重 */
  }
}

/** 解析路由 query 中的 execs（容错数字 / 字符串形式的 id）。 */
function parseExecutions(raw: unknown): QueryExecution[] {
  if (typeof raw !== 'string' || raw.trim() === '') return []
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    const list: QueryExecution[] = []
    for (const item of parsed) {
      if (item === null || typeof item !== 'object') continue
      const record = item as Record<string, unknown>
      const executionId = toNumber(record.executionId)
      if (executionId === null) continue
      list.push({
        executionId,
        taskId: toNumber(record.taskId),
        taskName: typeof record.taskName === 'string' ? record.taskName : '',
        launch: record.launch === true
      })
    }
    return list
  } catch {
    return []
  }
}

function parseTime(value: string | null | undefined): number | null {
  if (!value) return null
  return beijingMillis(value)
}

/** 后端日志 ts 为 'YYYY-MM-DD HH:MM:SS'，终端内只展示时间部分。 */
function formatLogTime(value: string | null | undefined): string | undefined {
  if (value === null || value === undefined) return undefined
  const match = /(\d{2}:\d{2}:\d{2})/.exec(value)
  return match === null ? undefined : match[1]
}

function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const rest = seconds % 60
  const mm = String(minutes).padStart(2, '0')
  const ss = String(rest).padStart(2, '0')
  return hours > 0 ? `${hours}:${mm}:${ss}` : `${mm}:${ss}`
}

function percentOf(success: number, total: number): number {
  if (total <= 0) return 0
  return Math.min(100, Math.round((success / total) * 100))
}

function countText(success: number, total: number): string {
  return total > 0 ? `${success}/${total}` : '—'
}

const executionOptions = computed<{ id: number; name: string }[]>(() => {
  const options: { id: number; name: string }[] = []
  const known = new Set<number>()
  for (const item of batchExecutions.value) {
    options.push({ id: item.executionId, name: item.taskName || `执行 #${item.executionId}` })
    known.add(item.executionId)
  }
  for (const execution of store.runningExecutions) {
    if (known.has(execution.id)) continue
    options.push({ id: execution.id, name: execution.task_name || `执行 #${execution.id}` })
    known.add(execution.id)
  }
  const selected = selectedExecutionId.value
  if (selected !== null && !known.has(selected)) {
    options.push({ id: selected, name: selectedExecutionName.value || `执行 #${selected}` })
  }
  return options
})

const connectionMeta = computed(() => CONNECTION_META[connectionState.value])

const currentStatus = computed<ExecutionStatus>(() => finalStatus.value ?? 'running')

const showStatus = computed(
  () => selectedExecutionId.value !== null && (finalStatus.value !== null || connectionState.value !== 'disconnected')
)

const canReconnect = computed(
  () => selectedExecutionId.value !== null && connectionState.value === 'disconnected' && finalStatus.value === null
)

const videoPercent = computed(() => percentOf(progress.value.successVideos, progress.value.totalVideos))
const subtitlePercent = computed(() => percentOf(progress.value.successSubtitles, progress.value.totalSubtitles))

const barStatus = computed<'' | 'success' | 'exception'>(() => {
  if (finalStatus.value === 'success') return 'success'
  if (finalStatus.value === 'fail') return 'exception'
  return ''
})

const elapsedText = computed(() => {
  const start = startedAt.value
  if (start === null) return '—'
  const end = finishedAt.value ?? now.value
  const seconds = Math.max(0, Math.floor((end - start) / 1000))
  return formatDuration(seconds)
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
  if (selectedExecutionId.value === null) return '请从「执行管理」页启动任务，或在顶部选择执行记录'
  if (finalStatus.value !== null) return '该执行已结束，可前往「任务历史」查看完整日志'
  if (connectionState.value === 'connected') return '等待日志输出…'
  return '暂无日志'
})

function findRunningExecution(executionId: number): OpenListExecution | undefined {
  return store.runningExecutions.find(item => item.id === executionId)
}

function findBatchItem(executionId: number): QueryExecution | undefined {
  return batchExecutions.value.find(item => item.executionId === executionId)
}

function buildTarget(
  executionId: number,
  taskId: number | null,
  taskName: string,
  launch: boolean
): OpenTarget {
  const running = findRunningExecution(executionId)
  const effectiveTaskId = taskId !== null && taskId > 0 ? taskId : running?.task_id ?? 0
  const name = taskName.trim() !== '' ? taskName : running?.task_name ?? ''
  return {
    executionId,
    taskId: effectiveTaskId,
    taskName: name !== '' ? name : `执行 #${executionId}`,
    launch,
    running
  }
}

/** launch=true 且本次页面尚未启动过该执行时才需要启动。 */
function needLaunch(target: OpenTarget): boolean {
  return target.launch && !launchedIds.value.includes(target.executionId)
}

function markLaunched(executionId: number): void {
  if (launchedIds.value.includes(executionId)) return
  launchedIds.value.push(executionId)
  persistLaunchedIds()
}

function removeBatchItem(executionId: number): void {
  batchExecutions.value = batchExecutions.value.filter(item => item.executionId !== executionId)
}

function disconnectSocket(): void {
  if (socket.value !== null) {
    disconnectWs(socket.value)
    socket.value = null
  }
}

function appendLog(frame: WsLogFrame): void {
  logLines.value.push({
    seq: nextSeq.value,
    level: frame.level,
    ts: formatLogTime(frame.ts),
    message: frame.message
  })
  nextSeq.value += 1
  if (logLines.value.length > MAX_LOG_LINES) {
    logLines.value.splice(0, logLines.value.length - MAX_LOG_LINES)
  }
}

function handleFrame(frame: WsFrame): void {
  if (frame.type === 'log') {
    appendLog(frame)
    return
  }
  if (frame.type === 'progress') {
    progress.value = { ...frame.data }
    return
  }
  handleStatusFrame(frame)
}

function handleStatusFrame(frame: WsStatusFrame): void {
  progress.value = {
    totalVideos: frame.video_total_count,
    successVideos: frame.video_success_count,
    totalSubtitles: frame.subtitle_total_count,
    successSubtitles: frame.subtitle_success_count
  }
  if (frame.status === 'running') return

  finalStatus.value = frame.status
  finishedAt.value = Date.now()
  pendingLaunch.value = null
  disconnectSocket()
  connectionState.value = 'disconnected'
  const executionId = selectedExecutionId.value
  if (executionId !== null) removeBatchItem(executionId)
  void store.fetchRunning().catch(() => {
    /* 请求拦截器已提示 */
  })
  ElMessage.info(
    frame.status === 'success' ? '任务执行完成，可前往「任务历史」查看日志' : '任务执行已结束，可前往「任务历史」查看日志'
  )
}

async function launchIfPending(): Promise<void> {
  const pending = pendingLaunch.value
  if (pending === null || launching.value) return
  launching.value = true
  try {
    await store.startExecution({
      execution_id: pending.executionId,
      task_id: pending.taskId
    })
    markLaunched(pending.executionId)
    pendingLaunch.value = null
    const running = findRunningExecution(pending.executionId)
    startedAt.value = parseTime(running?.started_time ?? null) ?? Date.now()
    if (finalStatus.value === null) ElMessage.success('任务已开始执行')
  } catch {
    ElMessage.error('任务启动失败，请检查配置后重试')
  } finally {
    launching.value = false
  }
}

function handleSocketOpen(): void {
  connectionState.value = 'connected'
  void launchIfPending()
}

function handleSocketClose(): void {
  socket.value = null
  connectionState.value = 'disconnected'
  if (finalStatus.value === null && selectedExecutionId.value !== null) {
    ElMessage.warning('实时日志连接已断开，可点击「重新连接」')
  }
}

function handleSocketError(): void {
  // 具体提示由 onClose 统一给出，这里只更新连接状态，避免重复弹出。
  connectionState.value = 'disconnected'
}

/** 先断开旧连接、重置视图状态，再建立新的 WebSocket；launch=true 时在 onOpen 后启动任务。 */
function startConnection(target: OpenTarget, launch: boolean): void {
  if (disposed) return
  disconnectSocket()
  selectedExecutionId.value = target.executionId
  selectedExecutionName.value = target.taskName
  logLines.value = []
  nextSeq.value = 1
  finalStatus.value = null
  progress.value = emptyProgress()
  finishedAt.value = null
  startedAt.value = parseTime(target.running?.started_time ?? null) ?? (launch ? null : Date.now())
  pendingLaunch.value = launch
    ? { executionId: target.executionId, taskId: target.taskId }
    : null
  autoScroll.value = true
  connectionState.value = 'connecting'
  socket.value = connectWs(target.executionId, {
    onMessage: handleFrame,
    onOpen: handleSocketOpen,
    onClose: handleSocketClose,
    onError: handleSocketError
  })
}

/** 展示已结束执行（初始进入或重连时发现已结束）的最终状态，避免一直停留在「连接中」。 */
async function showFinishedDetail(executionId: number, resetLogs: boolean): Promise<void> {
  removeBatchItem(executionId)
  disconnectSocket()
  connectionState.value = 'disconnected'
  pendingLaunch.value = null
  selectedExecutionId.value = executionId
  if (selectedExecutionName.value === '') selectedExecutionName.value = `执行 #${executionId}`
  if (resetLogs) {
    logLines.value = []
    nextSeq.value = 1
    progress.value = emptyProgress()
    finalStatus.value = null
    startedAt.value = null
    finishedAt.value = null
  }
  try {
    const res = await openlistApi.getExecutionDetail(executionId)
    if (disposed) return
    const execution = res.data.execution
    selectedExecutionName.value = execution.task_name || selectedExecutionName.value
    finalStatus.value = execution.status
    progress.value = {
      totalVideos: execution.video_total_count,
      successVideos: execution.video_success_count,
      totalSubtitles: execution.subtitle_total_count,
      successSubtitles: execution.subtitle_success_count
    }
    startedAt.value = parseTime(execution.started_time) ?? startedAt.value
    finishedAt.value = parseTime(execution.finished_time) ?? Date.now()
  } catch {
    /* 请求拦截器已提示，保留当前可见状态 */
  }
  ElMessage.info('该执行已结束，可前往「任务历史」查看日志')
}

/** 初始进入页面：可启动或仍在运行的执行直接连接；已结束的执行展示最终状态。 */
async function openInitial(target: OpenTarget): Promise<void> {
  const launch = needLaunch(target)
  if (launch || target.running !== undefined) {
    startConnection(target, launch)
    return
  }
  await showFinishedDetail(target.executionId, true)
}

async function handleExecutionChange(executionId: number): Promise<void> {
  if (executionId === selectedExecutionId.value) return
  try {
    await store.fetchRunning()
  } catch {
    return
  }
  const batchItem = findBatchItem(executionId)
  const fallbackName = executionOptions.value.find(option => option.id === executionId)?.name ?? `执行 #${executionId}`
  const target = buildTarget(
    executionId,
    batchItem?.taskId ?? null,
    batchItem?.taskName || fallbackName,
    batchItem?.launch ?? false
  )
  const launch = needLaunch(target)
  if (!launch && target.running === undefined) {
    ElMessage.info('该执行已结束，可前往「任务历史」查看日志')
    removeBatchItem(executionId)
    return
  }
  if (launch && target.taskId <= 0) {
    ElMessage.error('缺少任务信息，无法启动执行')
    removeBatchItem(executionId)
    return
  }
  startConnection(target, launch)
}

async function handleReconnect(): Promise<void> {
  const executionId = selectedExecutionId.value
  if (executionId === null) return
  try {
    await store.fetchRunning()
  } catch {
    return
  }
  const batchItem = findBatchItem(executionId)
  const target = buildTarget(
    executionId,
    batchItem?.taskId ?? null,
    selectedExecutionName.value,
    batchItem?.launch ?? false
  )
  const launch = needLaunch(target)
  if (!launch && target.running === undefined) {
    // 断线期间执行已结束：保留已有日志，补充最终状态。
    await showFinishedDetail(executionId, false)
    return
  }
  startConnection(target, launch)
}

function handleClear(): void {
  logLines.value = []
  nextSeq.value = 1
}

async function handleDownload(): Promise<void> {
  const executionId = selectedExecutionId.value
  if (executionId === null || downloading.value) return
  downloading.value = true
  try {
    await openlistApi.downloadLog(executionId)
  } catch {
    ElMessage.error('日志下载失败，请稍后重试')
  } finally {
    downloading.value = false
  }
}

async function init(): Promise<void> {
  try {
    await store.fetchRunning()
  } catch {
    return
  }
  if (disposed) return
  const items = parseExecutions(route.query.execs)
  if (items.length > 0) {
    batchExecutions.value = items
    const first: QueryExecution | undefined = items[0]
    if (first === undefined) return
    const running = findRunningExecution(first.executionId)
    const target = buildTarget(
      first.executionId,
      first.taskId,
      first.taskName || running?.task_name || '',
      first.launch
    )
    await openInitial(target)
    return
  }
  // 直接刷新 / 手动打开页面：展示第一条运行中的执行（只查看日志，不启动）。
  const firstRunning: OpenListExecution | undefined = store.runningExecutions[0]
  if (firstRunning === undefined) return
  const target = buildTarget(firstRunning.id, firstRunning.task_id, firstRunning.task_name, false)
  await openInitial(target)
}

onMounted(() => {
  timer = setInterval(() => {
    now.value = Date.now()
  }, 1000)
  void init().catch(() => {
    /* 请求拦截器已提示 */
  })
})

onBeforeUnmount(() => {
  disposed = true
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
  disconnectSocket()
})
</script>

<template>
  <div class="page page--fill realtime-page">
    <section class="realtime-page__summary">
      <div class="realtime-page__summary-head">
        <div class="realtime-page__identity">
          <div class="realtime-page__identity-row">
            <StatusDot v-if="showStatus" :status="currentStatus" />
            <el-select
              class="realtime-page__selector"
              :model-value="selectedExecutionId"
              placeholder="选择执行记录"
              :disabled="executionOptions.length === 0"
              @change="handleExecutionChange"
            >
              <el-option
                v-for="option in executionOptions"
                :key="option.id"
                :value="option.id"
                :label="option.name"
              />
            </el-select>
            <el-tag :type="connectionMeta.tone" size="small" effect="light">
              {{ connectionMeta.label }}
            </el-tag>
            <el-button
              v-if="canReconnect"
              link
              type="primary"
              size="small"
              :icon="Refresh"
              @click="handleReconnect"
            >
              重新连接
            </el-button>
          </div>
          <p v-if="selectedExecutionId === null" class="realtime-page__hint">
            从「执行管理」启动任务后将自动打开此页，也可以在上方选择正在运行的执行记录。
          </p>
        </div>
        <div class="realtime-page__elapsed">
          <span class="realtime-page__elapsed-label">耗时</span>
          <span class="realtime-page__elapsed-value">{{ elapsedText }}</span>
        </div>
      </div>

      <div class="realtime-page__progress">
        <div class="realtime-page__progress-item">
          <div class="realtime-page__progress-head">
            <span>视频</span>
            <span class="realtime-page__progress-count">{{ countText(progress.successVideos, progress.totalVideos) }}</span>
          </div>
          <el-progress :percentage="videoPercent" :stroke-width="8" :show-text="false" :status="barStatus" />
        </div>
        <div class="realtime-page__progress-item">
          <div class="realtime-page__progress-head">
            <span>字幕</span>
            <span class="realtime-page__progress-count">{{ countText(progress.successSubtitles, progress.totalSubtitles) }}</span>
          </div>
          <el-progress :percentage="subtitlePercent" :stroke-width="8" :show-text="false" :status="barStatus" />
        </div>
      </div>
    </section>

    <div class="realtime-page__toolbar">
      <div class="realtime-page__filters">
        <el-select v-model="levelFilter" class="realtime-page__level-filter" size="small" aria-label="日志级别过滤">
          <el-option label="全部级别" value="all" />
          <el-option label="信息" value="info" />
          <el-option label="警告" value="warn" />
          <el-option label="错误" value="error" />
        </el-select>
        <el-input
          v-model="keyword"
          class="realtime-page__keyword"
          size="small"
          placeholder="搜索日志关键字"
          clearable
          :prefix-icon="Search"
        />
      </div>
      <div class="realtime-page__toolbar-right">
        <span class="realtime-page__line-count">{{ filteredLines.length }} / {{ logLines.length }} 行</span>
        <el-button size="small" :icon="Delete" :disabled="logLines.length === 0" @click="handleClear">清屏</el-button>
        <el-button
          size="small"
          type="primary"
          :icon="Download"
          :loading="downloading"
          :disabled="selectedExecutionId === null"
          @click="handleDownload"
        >
          下载日志
        </el-button>
      </div>
    </div>

    <LogViewer
      v-model:auto-scroll="autoScroll"
      class="realtime-page__viewer"
      :lines="filteredLines"
      :max-lines="MAX_LOG_LINES"
      :empty-text="emptyText"
    />
  </div>
</template>

<style scoped lang="scss">
.realtime-page {
  gap: var(--up-strm-space-3, 12px);
  min-height: 0;

  &__summary {
    flex: none;
    display: flex;
    flex-direction: column;
    gap: var(--up-strm-space-3, 12px);
    padding: var(--up-strm-space-3, 12px) var(--up-strm-space-4, 16px);
    background: var(--el-bg-color);
    border: 1px solid var(--el-border-color-lighter);
    border-radius: var(--up-strm-radius-md, 8px);
  }

  &__summary-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--up-strm-space-4, 16px);
  }

  &__identity {
    display: flex;
    flex-direction: column;
    gap: var(--up-strm-space-1, 4px);
    min-width: 0;
  }

  &__identity-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--up-strm-space-2, 8px);
  }

  &__selector {
    width: 260px;
    max-width: 100%;
  }

  &__hint {
    margin: 0;
    font-size: var(--up-strm-font-size-xs, 12px);
    color: var(--el-text-color-secondary);
  }

  &__elapsed {
    flex: none;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 2px;
  }

  &__elapsed-label {
    font-size: var(--up-strm-font-size-xs, 12px);
    color: var(--el-text-color-secondary);
  }

  &__elapsed-value {
    font-size: var(--up-strm-font-size-lg, 16px);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--el-text-color-primary);
  }

  &__progress {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--up-strm-space-4, 16px);
  }

  &__progress-item {
    display: flex;
    flex-direction: column;
    gap: var(--up-strm-space-1, 4px);
    min-width: 0;
  }

  &__progress-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--up-strm-space-2, 8px);
    font-size: var(--up-strm-font-size-sm, 13px);
    color: var(--el-text-color-regular);
  }

  &__progress-count {
    font-size: var(--up-strm-font-size-xs, 12px);
    font-variant-numeric: tabular-nums;
    color: var(--el-text-color-secondary);
  }

  &__viewer {
    flex: 1;
    min-height: 0;
  }

  &__toolbar {
    flex: none;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: var(--up-strm-space-2, 8px);
    padding-bottom: var(--up-strm-space-1, 4px);
    border-bottom: 1px solid var(--el-border-color-lighter);
  }

  &__filters {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--up-strm-space-2, 8px);
  }

  &__level-filter {
    width: 128px;
  }

  &__keyword {
    width: 240px;
    max-width: 100%;
  }

  &__toolbar-right {
    display: flex;
    align-items: center;
    gap: var(--up-strm-space-2, 8px);
  }

  &__line-count {
    font-size: var(--up-strm-font-size-xs, 12px);
    font-variant-numeric: tabular-nums;
    color: var(--el-text-color-secondary);
  }
}

@media (max-width: 768px) {
  .realtime-page {
    &__progress {
      grid-template-columns: minmax(0, 1fr);
    }

    &__selector {
      width: 100%;
    }

    &__keyword {
      width: 100%;
    }
  }
}
</style>
