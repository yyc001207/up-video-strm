<script setup lang="ts">
/**
 * 自动化任务 · 实时日志：
 * - 按任务维度订阅 WS（automation:{task_id}），帧类型沿用 A/B：log / progress / status，
 *   异常终止另有 alert 帧（触发网页红点与托盘通知）；
 * - 连接建立后后端回放最近 200 帧，避免刚打开页面看不到开头；
 * - 可切换到任意任务，也可加载该任务最近一轮的日志文件回放。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElNotification } from 'element-plus'
import { Connection, Refresh, Search } from '@element-plus/icons-vue'

import { automationApi, automationRunApi } from '@/api/automation'
import LogViewer from '@/components/LogViewer.vue'
import { connectAutomationWs, disconnectWs, type WsState } from '@/utils/ws'
import type { AutomationTask, AutomationWsFrame } from '@/types/automation'

interface LogLine {
  seq: number
  level: string
  ts?: string
  message: string
}

const MAX_LOG_LINES = 3000
const CONNECTION_META: Record<WsState, { label: string; tone: 'info' | 'success' | 'danger' }> = {
  connecting: { label: '连接中', tone: 'info' },
  connected: { label: '已连接', tone: 'success' },
  disconnected: { label: '未连接', tone: 'danger' }
}

const route = useRoute()

const tasks = ref<AutomationTask[]>([])
const taskId = ref<number | null>(null)
const socket = ref<WebSocket | null>(null)
const connectionState = ref<WsState>('disconnected')
const logLines = ref<LogLine[]>([])
const nextSeq = ref(1)
const autoScroll = ref(true)
const levelFilter = ref<'all' | 'info' | 'warn' | 'error'>('all')
const keyword = ref('')
const phase = ref('—')
const roundNo = ref(0)
const pendingCount = ref(0)
const lastRunId = ref<number | null>(null)
const loadingRun = ref(false)

const currentTask = computed(() => tasks.value.find(item => item.id === taskId.value) ?? null)
const connectionMeta = computed(() => CONNECTION_META[connectionState.value])

const filteredLines = computed<LogLine[]>(() => {
  const text = keyword.value.trim().toLowerCase()
  return logLines.value.filter(line => {
    if (levelFilter.value !== 'all' && line.level !== levelFilter.value) return false
    if (text && !line.message.toLowerCase().includes(text)) return false
    return true
  })
})

const emptyText = computed(() => {
  if (!taskId.value) return '请选择要查看的自动化任务'
  if (connectionState.value === 'connecting') return '正在连接实时日志…'
  if (!currentTask.value?.is_running) return '任务当前未运行，可加载最近一轮日志回放'
  return '等待任务输出日志…'
})

function resetLogs(): void {
  logLines.value = []
  nextSeq.value = 1
}

function appendLine(level: string, message: string, ts?: string): void {
  logLines.value.push({ seq: nextSeq.value++, level, ts, message })
  if (logLines.value.length > MAX_LOG_LINES) {
    logLines.value.splice(0, logLines.value.length - MAX_LOG_LINES)
  }
}

function onFrame(frame: AutomationWsFrame): void {
  if (frame.type === 'log') {
    appendLine(frame.level || 'info', frame.message, frame.ts)
    return
  }
  if (frame.type === 'progress') {
    const data = frame.data ?? {}
    if (typeof data.pending === 'number') pendingCount.value = data.pending
    return
  }
  if (frame.type === 'status') {
    if (frame.phase) phase.value = frame.phase
    if (frame.round_no) roundNo.value = frame.round_no
    return
  }
  if (frame.type === 'alert') {
    ElNotification({
      title: '自动化任务异常终止',
      message: frame.message,
      type: 'error',
      duration: 0
    })
  }
}

function disconnect(): void {
  disconnectWs(socket.value)
  socket.value = null
  connectionState.value = 'disconnected'
}

function connect(): void {
  disconnect()
  if (!taskId.value) return
  connectionState.value = 'connecting'
  socket.value = connectAutomationWs(taskId.value, {
    onMessage: onFrame,
    onOpen: () => {
      connectionState.value = 'connected'
    },
    onClose: () => {
      connectionState.value = 'disconnected'
    },
    onError: () => {
      connectionState.value = 'disconnected'
    }
  })
}

async function loadTasks(): Promise<void> {
  const res = await automationApi.listTasks({ page: 1, page_size: 100 })
  tasks.value = res.data ?? []
  const queryTaskId = Number(route.query.task_id)
  if (!taskId.value) {
    taskId.value =
      (Number.isInteger(queryTaskId) && tasks.value.some(item => item.id === queryTaskId) ? queryTaskId : null) ??
      tasks.value.find(item => item.is_running)?.id ??
      tasks.value[0]?.id ??
      null
  }
}

async function loadLatestRunLogs(): Promise<void> {
  if (!taskId.value) return
  loadingRun.value = true
  try {
    const runs = await automationRunApi.listRuns({ task_id: taskId.value, page: 1, page_size: 5 })
    const run = (runs.data ?? []).find(item => item.id) ?? null
    lastRunId.value = run?.id ?? null
    if (!run) {
      resetLogs()
      appendLine('info', '该任务还没有运行记录')
      return
    }
    const logs = await automationRunApi.runLogs(run.id, 0, 2000)
    resetLogs()
    for (const line of logs.data?.lines ?? []) {
      appendLine(line.level, line.message)
    }
    phase.value = run.phase
    roundNo.value = run.round_no
    pendingCount.value = run.pending_file_count
  } finally {
    loadingRun.value = false
  }
}

watch(taskId, () => {
  resetLogs()
  phase.value = '—'
  roundNo.value = 0
  pendingCount.value = 0
  connect()
})

onMounted(async () => {
  await loadTasks()
  if (taskId.value) connect()
})

onBeforeUnmount(disconnect)
</script>

<template>
  <div class="page page--fill realtime-page automation-realtime">
    <div class="toolbar">
      <div class="toolbar__left">
        <el-select v-model="taskId" placeholder="选择自动化任务" style="width: 240px" filterable>
          <el-option
            v-for="task in tasks"
            :key="task.id"
            :label="`${task.name}${task.is_running ? '（运行中）' : ''}`"
            :value="task.id"
          />
        </el-select>
        <el-tag :type="connectionMeta.tone" size="small" effect="plain">{{ connectionMeta.label }}</el-tag>
        <el-tag v-if="currentTask" type="info" size="small" effect="plain">阶段：{{ phase }}</el-tag>
        <el-tag v-if="roundNo" type="info" size="small" effect="plain">第 {{ roundNo }} 轮</el-tag>
        <el-tag v-if="pendingCount" type="warning" size="small" effect="plain">
          待校验 {{ pendingCount }}
        </el-tag>
      </div>
      <div class="toolbar__right">
        <el-button :icon="Connection" @click="connect">重新连接</el-button>
        <el-button :icon="Refresh" :loading="loadingRun" @click="loadLatestRunLogs">加载最近一轮</el-button>
      </div>
    </div>

    <el-card class="log-card" shadow="never">
      <div class="log-toolbar">
        <el-radio-group v-model="levelFilter" size="small">
          <el-radio-button value="all">全部</el-radio-button>
          <el-radio-button value="info">信息</el-radio-button>
          <el-radio-button value="warn">警告</el-radio-button>
          <el-radio-button value="error">错误</el-radio-button>
        </el-radio-group>
        <el-input
          v-model="keyword"
          size="small"
          :prefix-icon="Search"
          placeholder="搜索日志内容"
          clearable
          style="width: 240px"
        />
        <el-checkbox v-model="autoScroll" size="small">自动滚动</el-checkbox>
        <el-button size="small" @click="resetLogs">清屏</el-button>
      </div>
      <LogViewer
        v-model:auto-scroll="autoScroll"
        class="log-viewer"
        :lines="filteredLines"
        :max-lines="MAX_LOG_LINES"
        :empty-text="emptyText"
      />
    </el-card>
  </div>
</template>

<style scoped>
.log-card {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.log-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.log-viewer {
  flex: 1;
  min-height: 0;
}
</style>
