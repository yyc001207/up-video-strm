<script setup lang="ts">
/**
 * 云盘上传 · 运行详情：
 * - 通过 WS 连接当前执行，连接成功后由本页调用「启动执行」（避免启动后漏掉开头日志）；
 * - 支持批量排队：一个执行结束后自动连下一个；
 * - 日志只写文件并由 WS 实时推送，本页可切换到任意执行回放最近日志。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Delete, FolderOpened, Refresh, Search } from '@element-plus/icons-vue'

import { desktopApi } from '@/api/desktop'
import LogViewer from '@/components/LogViewer.vue'
import StatusDot from '@/components/StatusDot.vue'
import { uploaderApi } from '@/api/uploader'
import { beijingMillis, parseBeijing } from '@/utils/date'
import { connectUploadWs, disconnectWs, type WsState } from '@/utils/ws'
import type {
  UploadExecution,
  UploadExecutionStatus,
  UploadWsFrame,
  UploadWsLogFrame,
  UploadWsProgressData,
  UploadWsStatusFrame
} from '@/types/uploader'

interface LogLine {
  seq: number
  level: string
  ts?: string
  message: string
}

interface RealtimeTarget {
  executionId: number
  taskId: number
  taskName: string
}

type FilterLevel = 'all' | 'info' | 'warn' | 'error'

const MAX_LOG_LINES = 3000
const CONNECTION_META: Record<WsState, { label: string; tone: 'info' | 'success' | 'danger' }> = {
  connecting: { label: '连接中', tone: 'info' },
  connected: { label: '已连接', tone: 'success' },
  disconnected: { label: '未连接', tone: 'danger' }
}

const route = useRoute()
const router = useRouter()

const socket = ref<WebSocket | null>(null)
const connectionState = ref<WsState>('disconnected')
const targets = ref<RealtimeTarget[]>([])
const selectedExecutionId = ref<number | null>(null)
const launching = ref(false)
const logLines = ref<LogLine[]>([])
const nextSeq = ref(1)
const autoScroll = ref(true)
const levelFilter = ref<FilterLevel>('all')
const keyword = ref('')
const opening = ref(false)
const progress = ref<UploadWsProgressData>({
  total: 0,
  success: 0,
  skipped: 0,
  failed: 0,
  bytesUploaded: 0,
  current: ''
})
const finalStatus = ref<UploadExecutionStatus | null>(null)
const startedAt = ref<number | null>(null)
const finishedAt = ref<number | null>(null)
const now = ref(Date.now())
const finishedIds = ref<number[]>([])

let clockTimer: ReturnType<typeof setInterval> | null = null

const selectedTarget = computed(
  () => targets.value.find(item => item.executionId === selectedExecutionId.value) ?? null
)

/** 是否有可查看的执行记录（无执行时不展示「运行中」状态）。 */
const hasTargets = computed(() => targets.value.length > 0)

const connectionMeta = computed(() => CONNECTION_META[connectionState.value])

const currentStatus = computed<UploadExecutionStatus>(
  () => finalStatus.value ?? 'running'
)

const executionOptions = computed(() =>
  targets.value.map((item, index) => ({
    id: item.executionId,
    label: `${index + 1}. ${item.taskName}`
  }))
)

const elapsedText = computed(() => {
  if (!startedAt.value) return '—'
  const end = finishedAt.value ?? now.value
  const seconds = Math.max(0, Math.floor((end - startedAt.value) / 1000))
  const minutes = Math.floor(seconds / 60)
  return `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
})

const bytesText = computed(() => {
  const bytes = progress.value.bytesUploaded
  if (bytes <= 0) return '—'
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`
})

const filteredLines = computed<LogLine[]>(() => {
  const text = keyword.value.trim().toLowerCase()
  return logLines.value.filter(line => {
    if (levelFilter.value !== 'all' && line.level !== levelFilter.value) return false
    if (text && !line.message.toLowerCase().includes(text)) return false
    return true
  })
})

const canReconnect = computed(
  () => connectionState.value === 'disconnected' && currentStatus.value === 'running'
)

const emptyText = computed(() => {
  if (!hasTargets.value) return '当前没有执行中的上传，请到开始执行发起执行'
  if (selectedExecutionId.value === null) return '请选择左侧执行记录'
  if (connectionState.value === 'connecting') return '正在连接运行详情…'
  if (currentStatus.value !== 'running') return '执行已结束，日志已回放完毕'
  return '等待执行开始输出日志…'
})

function toNumber(value: unknown): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function formatLogTime(value: string | null | undefined): string | undefined {
  if (!value) return undefined
  return parseBeijing(value)?.format('HH:mm:ss') ?? undefined
}

function parseTargets(raw: unknown): RealtimeTarget[] {
  if (typeof raw !== 'string' || !raw) return []
  try {
    const parsed = JSON.parse(raw) as RealtimeTarget[]
    return parsed
      .map(item => ({
        executionId: Number(item.executionId),
        taskId: Number(item.taskId),
        taskName: String(item.taskName ?? `执行 #${item.executionId}`)
      }))
      .filter(item => Number.isInteger(item.executionId) && Number.isInteger(item.taskId))
  } catch {
    return []
  }
}

function resetLogs(): void {
  logLines.value = []
  nextSeq.value = 1
  progress.value = { total: 0, success: 0, skipped: 0, failed: 0, bytesUploaded: 0, current: '' }
  finalStatus.value = null
  startedAt.value = null
  finishedAt.value = null
}

function appendLog(frame: UploadWsLogFrame): void {
  const line: LogLine = {
    seq: nextSeq.value++,
    level: frame.level || 'info',
    ts: formatLogTime(frame.ts),
    message: frame.message
  }
  logLines.value.push(line)
  if (logLines.value.length > MAX_LOG_LINES) {
    logLines.value.splice(0, logLines.value.length - MAX_LOG_LINES)
  }
}

function disconnectSocket(): void {
  disconnectWs(socket.value)
  socket.value = null
  connectionState.value = 'disconnected'
}

async function maybeStart(target: RealtimeTarget): Promise<void> {
  if (finalStatus.value) return
  const detail = await uploaderApi.getExecutionDetail(target.executionId)
  const execution = detail.data.execution
  if (execution.started_time) {
    startedAt.value = startedAt.value ?? beijingMillis(execution.started_time)
  }
  // 连接时执行已结束（例如刷新页面回放日志）：直接显示最终状态，避免页面停留在「运行中」。
  if (execution.status !== 'running') {
    finalStatus.value = execution.status
    finishedAt.value = finishedAt.value ?? Date.now()
    disconnectSocket()
    return
  }
  if (execution.started_time) return
  launching.value = true
  try {
    await uploaderApi.startExecution(target.executionId, target.taskId)
    startedAt.value = Date.now()
    ElMessage.success(`已开始执行：${target.taskName}`)
  } finally {
    launching.value = false
  }
}

async function handleFinishedFrame(frame: UploadWsStatusFrame): Promise<void> {
  finalStatus.value = frame.status
  finishedAt.value = Date.now()
  disconnectSocket()
  if (!finishedIds.value.includes(selectedExecutionId.value ?? -1)) {
    finishedIds.value.push(selectedExecutionId.value ?? -1)
  }
  if (frame.success !== undefined) {
    progress.value = {
      ...progress.value,
      success: toNumber(frame.success),
      skipped: toNumber(frame.skipped ?? progress.value.skipped),
      failed: toNumber(frame.failed ?? progress.value.failed)
    }
  }
  const next = targets.value.find(
    item => !finishedIds.value.includes(item.executionId)
  )
  if (next) {
    await connectTarget(next)
  }
}

function handleFrame(frame: UploadWsFrame): void {
  if (frame.type === 'log') {
    appendLog(frame)
    return
  }
  if (frame.type === 'progress') {
    progress.value = {
      total: toNumber(frame.data?.total),
      success: toNumber(frame.data?.success),
      skipped: toNumber(frame.data?.skipped),
      failed: toNumber(frame.data?.failed),
      bytesUploaded: toNumber(frame.data?.bytesUploaded),
      current: String(frame.data?.current ?? '')
    }
    return
  }
  if (frame.type === 'status') {
    void handleFinishedFrame(frame)
  }
}

async function connectTarget(target: RealtimeTarget): Promise<void> {
  disconnectSocket()
  selectedExecutionId.value = target.executionId
  resetLogs()
  connectionState.value = 'connecting'
  socket.value = connectUploadWs(target.executionId, {
    onOpen: () => {
      connectionState.value = 'connected'
      void maybeStart(target).catch(error => {
        ElMessage.warning((error as Error).message || '启动执行失败')
      })
    },
    onMessage: handleFrame,
    onClose: () => {
      connectionState.value = 'disconnected'
    },
    onError: () => {
      connectionState.value = 'disconnected'
    }
  })
}

function handleExecutionChange(executionId: number): void {
  const target = targets.value.find(item => item.executionId === executionId)
  if (target) void connectTarget(target)
}

async function handleReconnect(): Promise<void> {
  if (selectedTarget.value) await connectTarget(selectedTarget.value)
}

function handleClear(): void {
  logLines.value = []
  nextSeq.value = 1
}

async function handleOpenLogDir(): Promise<void> {
  if (opening.value) return
  opening.value = true
  try {
    await desktopApi.openLogDir('upload')
    ElMessage.success('已打开日志文件夹')
  } catch {
    /* 拦截器已提示（非桌面环境时会提示不支持） */
  } finally {
    opening.value = false
  }
}

async function init(): Promise<void> {
  const parsed = parseTargets(route.query.execs)
  if (parsed.length > 0) {
    targets.value = parsed
    await connectTarget(parsed[0])
    return
  }
  const res = await uploaderApi.listExecutions({ status: 'running', page: 1, pageSize: 50 })
  const running = res.data.list
  if (running.length === 0) return
  targets.value = running.map((item: UploadExecution) => ({
    executionId: item.id,
    taskId: item.task_id,
    taskName: item.task_name
  }))
  await connectTarget(targets.value[0])
}

onMounted(() => {
  void init().catch(error => ElMessage.error((error as Error).message || '运行详情初始化失败'))
  clockTimer = setInterval(() => {
    now.value = Date.now()
  }, 1000)
})

onBeforeUnmount(() => {
  if (clockTimer) clearInterval(clockTimer)
  disconnectSocket()
})
</script>

<template>
  <div class="page upload-realtime">
    <p class="upload-realtime__desc">
      本页实时显示所选上传执行的日志与 6 阶段进度；批量排队时按队列串行启动并自动切换。可通过日志级别与关键字过滤日志；当前没有运行中的上传时，请到「开始执行」发起执行。
    </p>

    <div class="realtime-toolbar">
      <div class="realtime-toolbar__left">
        <el-select
          :model-value="selectedExecutionId"
          placeholder="选择执行"
          style="width: 260px"
          :disabled="targets.length === 0"
          @change="handleExecutionChange"
        >
          <el-option
            v-for="option in executionOptions"
            :key="option.id"
            :label="option.label"
            :value="option.id"
          />
        </el-select>
        <el-tag :type="connectionMeta.tone" size="small" disable-transitions>
          {{ connectionMeta.label }}
        </el-tag>
        <el-tag v-if="launching" type="warning" size="small" disable-transitions>启动中</el-tag>
        <StatusDot v-if="hasTargets" :status="currentStatus" />
        <el-tag v-else type="info" size="small" disable-transitions>无运行中任务</el-tag>
      </div>
      <div class="realtime-toolbar__right">
        <el-button v-if="canReconnect" :icon="Refresh" @click="handleReconnect">重连</el-button>
        <el-button :icon="Delete" @click="handleClear">清空</el-button>
        <el-button :icon="FolderOpened" :loading="opening" @click="handleOpenLogDir">打开日志文件夹</el-button>
      </div>
    </div>

    <div class="progress-card">
      <div class="progress-card__item">
        <span class="progress-card__label">文件总数</span>
        <span class="progress-card__value">{{ progress.total }}</span>
      </div>
      <div class="progress-card__item">
        <span class="progress-card__label">成功</span>
        <span class="progress-card__value progress-card__value--success">{{ progress.success }}</span>
      </div>
      <div class="progress-card__item">
        <span class="progress-card__label">跳过</span>
        <span class="progress-card__value">{{ progress.skipped }}</span>
      </div>
      <div class="progress-card__item">
        <span class="progress-card__label">失败</span>
        <span class="progress-card__value progress-card__value--danger">{{ progress.failed }}</span>
      </div>
      <div class="progress-card__item">
        <span class="progress-card__label">已上传</span>
        <span class="progress-card__value">{{ bytesText }}</span>
      </div>
      <div class="progress-card__item">
        <span class="progress-card__label">用时</span>
        <span class="progress-card__value">{{ elapsedText }}</span>
      </div>
      <div class="progress-card__item progress-card__item--wide">
        <span class="progress-card__label">当前文件</span>
        <span class="progress-card__value progress-card__value--mono">
          {{ progress.current || '—' }}
        </span>
      </div>
    </div>

    <div class="log-toolbar">
      <div class="log-toolbar__left">
        <el-select v-model="levelFilter" size="small" style="width: 128px">
          <el-option label="全部级别" value="all" />
          <el-option label="信息" value="info" />
          <el-option label="警告" value="warn" />
          <el-option label="错误" value="error" />
        </el-select>
        <el-input
          v-model="keyword"
          size="small"
          placeholder="筛选关键字"
          clearable
          style="width: 220px"
          :prefix-icon="Search"
        />
        <span class="log-toolbar__count">{{ filteredLines.length }} 行</span>
      </div>
      <div class="log-toolbar__right">
        <el-button v-if="selectedExecutionId" size="small" @click="router.push('/upload/execution')">
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
.upload-realtime {
  display: flex;
  flex-direction: column;
  gap: var(--up-strm-space-3, 12px);
  min-height: 0;
  height: 100%;
}

.upload-realtime__desc {
  flex: none;
  margin: 0;
  font-size: var(--up-strm-font-size-xs, 12px);
  line-height: 1.6;
  color: var(--el-text-color-secondary);
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
