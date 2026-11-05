<script setup lang="ts">
/**
 * 自动化任务 · 执行管理：
 * - 列出全部自动化任务与运行态（3s 轮询），支持逐项/批量启动与停止；
 * - 启动可覆盖本次运行的并发、重试与生成模式（不写回任务配置）；
 * - 运行中的任务展示阶段、轮次与下一轮时间，并可重置指纹、清空待校验文件。
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, VideoPlay, VideoPause, Delete, Timer, ArrowRight } from '@element-plus/icons-vue'

import { automationApi, automationRunApi } from '@/api/automation'
import type {
  AutomationActiveTask,
  AutomationOpenListMode,
  AutomationStartPayload,
  AutomationTask
} from '@/types/automation'

const router = useRouter()

const tasks = ref<AutomationTask[]>([])
const active = ref<AutomationActiveTask[]>([])
const loading = ref(false)
const selectedIds = ref<number[]>([])
const starting = ref(false)

const startDialogVisible = ref(false)
const startTargets = ref<number[]>([])
const startForm = reactive<AutomationStartPayload>({
  upload_concurrency: undefined,
  upload_retry_times: undefined,
  openlist_mode: undefined
})

let timer: ReturnType<typeof setInterval> | null = null

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

const MODE_OPTIONS: { value: AutomationOpenListMode; label: string }[] = [
  { value: 'incremental', label: '增量生成' },
  { value: 'full', label: '全量生成' },
  { value: 'strm_only', label: '仅生成 STRM' }
]

const activeMap = computed(() => new Map(active.value.map(item => [item.task_id, item])))
const runningCount = computed(() => active.value.length)

function phaseText(task: AutomationTask): string {
  const state = activeMap.value.get(task.id)
  if (state?.phase) return PHASE_LABELS[state.phase] ?? state.phase
  return task.is_running ? '运行中' : '未运行'
}

function nextRoundText(task: AutomationTask): string {
  const state = activeMap.value.get(task.id)
  return state?.next_round_at ?? '—'
}

async function load(silent = false): Promise<void> {
  if (!silent) loading.value = true
  try {
    const [taskRes, activeRes] = await Promise.all([
      automationApi.listTasks({ page: 1, page_size: 100 }),
      automationRunApi.active()
    ])
    tasks.value = taskRes.data ?? []
    active.value = activeRes.data ?? []
  } finally {
    loading.value = false
  }
}

function openStartDialog(ids: number[]): void {
  if (!ids.length) {
    ElMessage.warning('请先选择要启动的任务')
    return
  }
  const running = ids.filter(id => {
    const task = tasks.value.find(item => item.id === id)
    return task?.is_running
  })
  if (running.length) {
    ElMessage.warning(`任务 ${running.join('、')} 正在运行，请先停止`)
    return
  }
  startTargets.value = ids
  startForm.upload_concurrency = undefined
  startForm.upload_retry_times = undefined
  startForm.openlist_mode = undefined
  startDialogVisible.value = true
}

async function confirmStart(): Promise<void> {
  const ids = startTargets.value
  if (!ids.length) return
  starting.value = true
  try {
    const payload: AutomationStartPayload = {}
    if (startForm.upload_concurrency) payload.upload_concurrency = startForm.upload_concurrency
    if (startForm.upload_retry_times !== undefined) payload.upload_retry_times = startForm.upload_retry_times
    if (startForm.openlist_mode) payload.openlist_mode = startForm.openlist_mode
    if (ids.length === 1) {
      await automationRunApi.start(ids[0], payload)
      ElMessage.success('已启动')
    } else {
      const res = await automationRunApi.batchStart(ids, payload)
      const failed = (res.data ?? []).filter(item => !item.ok)
      if (failed.length) {
        ElMessage.warning(`已启动 ${ids.length - failed.length} 个，失败 ${failed.length} 个`)
      } else {
        ElMessage.success(`已启动 ${ids.length} 个任务`)
      }
    }
    startDialogVisible.value = false
    await load(true)
  } finally {
    starting.value = false
  }
}

async function stopTask(task: AutomationTask): Promise<void> {
  await ElMessageBox.confirm(`确定停止自动化任务「${task.name}」？`, '停止运行', { type: 'warning' })
  await automationRunApi.stop(task.id)
  ElMessage.success('已请求停止')
  await load(true)
}

async function resetFingerprint(task: AutomationTask): Promise<void> {
  await automationRunApi.resetFingerprint(task.id)
  ElMessage.success('已重置扫描指纹，下一轮将重新检测变化')
  await load(true)
}

async function clearPending(task: AutomationTask): Promise<void> {
  if (!task.pending_file_count) {
    ElMessage.info('当前没有待校验文件')
    return
  }
  await ElMessageBox.confirm(
    `确定清空「${task.name}」的 ${task.pending_file_count} 个待校验文件？`,
    '清空待校验',
    { type: 'warning' }
  )
  await automationRunApi.clearPending(task.id)
  ElMessage.success('已清空待校验文件')
  await load(true)
}

function openLogs(task: AutomationTask): void {
  router.push({ path: '/automation/realtime', query: { task_id: String(task.id) } })
}

function onSelectionChange(rows: AutomationTask[]): void {
  selectedIds.value = rows.map(row => row.id)
}

onMounted(async () => {
  await load()
  timer = setInterval(() => void load(true), 3000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="page page--fill list-page automation-execution">
    <div class="toolbar">
      <div class="toolbar__left">
        <el-button type="primary" :icon="VideoPlay" @click="openStartDialog(selectedIds)">
          批量启动
        </el-button>
        <el-button :icon="Refresh" :loading="loading" @click="load()">刷新</el-button>
        <span class="toolbar__summary">运行中 {{ runningCount }} 个</span>
      </div>
      <div class="toolbar__right">
        <el-button :icon="ArrowRight" @click="router.push('/automation/realtime')">实时日志</el-button>
      </div>
    </div>

    <el-card class="list-card" shadow="never">
      <el-table
        v-loading="loading"
        class="list-card__table"
        :data="tasks"
        row-key="id"
        empty-text="暂无自动化任务，请先在「任务配置」中创建"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="44" :selectable="(row: AutomationTask) => !row.is_running" />
        <el-table-column label="任务名称" min-width="160">
          <template #default="{ row }">
            <div class="cell-main">{{ row.name }}</div>
            <div class="cell-sub">{{ row.upload_task_name }} → {{ row.openlist_task_name }}</div>
          </template>
        </el-table-column>
        <el-table-column label="校验目录" min-width="150" prop="check_dir" show-overflow-tooltip />
        <el-table-column label="运行状态" width="150">
          <template #default="{ row }">
            <el-tag :type="row.is_running ? 'success' : 'info'" size="small" effect="plain">
              {{ phaseText(row) }}
            </el-tag>
            <div v-if="row.is_running" class="cell-sub">下一轮：{{ nextRoundText(row) }}</div>
          </template>
        </el-table-column>
        <el-table-column label="待校验" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.pending_file_count" type="warning" size="small">
              {{ row.pending_file_count }}
            </el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="轮次" width="90" align="center">
          <template #default="{ row }">
            第 {{ row.last_round_no }} 轮
            <div v-if="row.consecutive_failures" class="cell-sub">连续失败 {{ row.consecutive_failures }}</div>
          </template>
        </el-table-column>
        <el-table-column label="最近扫描" width="160">
          <template #default="{ row }">{{ row.scan_time ?? '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="290" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="!row.is_running"
              link
              type="primary"
              :icon="VideoPlay"
              @click="openStartDialog([row.id])"
            >
              启动
            </el-button>
            <el-button v-else link type="warning" :icon="VideoPause" @click="stopTask(row)">停止</el-button>
            <el-button link :icon="Timer" @click="resetFingerprint(row)">重置指纹</el-button>
            <el-button link :icon="Delete" :disabled="!row.pending_file_count" @click="clearPending(row)">
              清空待校验
            </el-button>
            <el-button link @click="openLogs(row)">日志</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="startDialogVisible" title="启动自动化任务" width="460px">
      <div class="form-tip">
        启动后立即执行一轮（跳过指纹检查），以下参数仅本次运行生效，不写回任务配置。
      </div>
      <el-form label-width="120px" class="start-form">
        <el-form-item label="上传并发">
          <el-input-number v-model="startForm.upload_concurrency" :min="1" :max="8" placeholder="使用任务配置" />
        </el-form-item>
        <el-form-item label="失败重试">
          <el-input-number v-model="startForm.upload_retry_times" :min="0" :max="10" placeholder="使用任务配置" />
        </el-form-item>
        <el-form-item label="生成模式">
          <el-select v-model="startForm.openlist_mode" clearable placeholder="使用任务配置" style="width: 100%">
            <el-option v-for="item in MODE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="startDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="starting" @click="confirmStart">
          启动 {{ startTargets.length > 1 ? `${startTargets.length} 个任务` : '' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar__summary {
  margin-left: 12px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.start-form {
  margin-top: 16px;
}
</style>
