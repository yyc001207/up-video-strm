<script setup lang="ts">
/**
 * 上传管理 · 执行管理：
 * 一行三卡片（选择任务 / 执行参数 / 已选任务），下方为正在执行列表。
 * 点击「执行任务」先批量创建执行记录，再跳转实时日志页由 WS 连接成功后逐个启动。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Close, Refresh, VideoPlay } from '@element-plus/icons-vue'
import dayjs from 'dayjs'

import StatusDot from '@/components/StatusDot.vue'
import { uploaderApi } from '@/api/uploader'
import type {
  UploadConflictPolicy,
  UploadExecution,
  UploadExecutionStatus,
  UploadTask
} from '@/types/uploader'

interface RealtimeTarget {
  executionId: number
  taskId: number
  taskName: string
}

const CONFLICT_OPTIONS: { value: UploadConflictPolicy; label: string; hint: string }[] = [
  { value: 'skip', label: '跳过（推荐）', hint: '云端已存在同名文件时保留原文件，不覆盖' },
  { value: 'overwrite', label: '覆盖', hint: '先上传新文件，成功后再删除云端旧文件' },
  { value: 'suffix', label: '追加后缀', hint: '同名时自动改为 xxx_1.mp4、xxx_2.mp4' }
]

const router = useRouter()

const loading = ref(false)
const executing = ref(false)
const tasks = ref<UploadTask[]>([])
const running = ref<UploadExecution[]>([])
const selectedIds = ref<number[]>([])
const conflictPolicy = ref<UploadConflictPolicy>('skip')
const concurrency = ref(2)
const retryTimes = ref(3)
const dryRun = ref(false)

const selectedTasks = computed(() => tasks.value.filter(task => selectedIds.value.includes(task.id)))
const conflictHint = computed(
  () => CONFLICT_OPTIONS.find(option => option.value === conflictPolicy.value)?.hint ?? ''
)

let pollTimer: ReturnType<typeof setInterval> | null = null

function formatTime(value: string | null): string {
  return value ? dayjs(value).format('MM-DD HH:mm:ss') : '—'
}

function progressText(row: UploadExecution): string {
  return `${row.file_success}/${row.file_total}`
}

async function loadTasks(): Promise<void> {
  const res = await uploaderApi.listTasks()
  tasks.value = res.data
}

async function loadRunning(): Promise<void> {
  const res = await uploaderApi.listExecutions({ status: 'running', page: 1, pageSize: 50 })
  running.value = res.data.list
}

async function load(): Promise<void> {
  loading.value = true
  try {
    await Promise.all([loadTasks(), loadRunning()])
  } finally {
    loading.value = false
  }
}

function isSelected(taskId: number): boolean {
  return selectedIds.value.includes(taskId)
}

function toggleTask(taskId: number): void {
  selectedIds.value = isSelected(taskId)
    ? selectedIds.value.filter(id => id !== taskId)
    : [...selectedIds.value, taskId]
}

function removeSelected(taskId: number): void {
  selectedIds.value = selectedIds.value.filter(id => id !== taskId)
}

function clearSelected(): void {
  selectedIds.value = []
}

async function execute(): Promise<void> {
  if (selectedIds.value.length === 0) {
    ElMessage.warning('请先在左侧勾选要执行的任务')
    return
  }
  executing.value = true
  try {
    const res = await uploaderApi.batchCreateExecutions({
      task_ids: selectedIds.value,
      conflict_policy: conflictPolicy.value,
      concurrency: concurrency.value,
      retry_times: retryTimes.value,
      dry_run: dryRun.value
    })
    if (dryRun.value) {
      ElMessage.success(`已为 ${res.data.length} 个任务生成上传清单（试运行，不上传）`)
      selectedIds.value = []
      await load()
      return
    }
    const targets: RealtimeTarget[] = res.data.map(item => ({
      executionId: item.id,
      taskId: item.task_id,
      taskName: item.task_name
    }))
    await router.push({ path: '/upload/realtime', query: { execs: JSON.stringify(targets) } })
  } finally {
    executing.value = false
  }
}

async function cancelExecution(row: UploadExecution): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认取消执行「${row.task_name}」？`, '提示', {
      type: 'warning',
      confirmButtonText: '取消执行',
      cancelButtonText: '返回'
    })
  } catch {
    return
  }
  await uploaderApi.cancelExecution(row.id)
  ElMessage.success('已取消')
  await loadRunning()
}

function openRealtime(row: UploadExecution): void {
  const targets: RealtimeTarget[] = [
    { executionId: row.id, taskId: row.task_id, taskName: row.task_name }
  ]
  void router.push({ path: '/upload/realtime', query: { execs: JSON.stringify(targets) } })
}

onMounted(() => {
  void load()
  pollTimer = setInterval(() => void loadRunning(), 5000)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div class="page upload-execution">
    <div class="upload-execution__cards" v-loading="loading">
      <!-- 选择任务 -->
      <el-card shadow="never" class="exec-card">
        <template #header>
          <div class="exec-card__header">
            <span class="exec-card__title">选择任务</span>
            <span class="exec-card__hint">已选 {{ selectedIds.length }} 个</span>
          </div>
        </template>
        <div v-if="tasks.length > 0" class="task-list">
          <div
            v-for="task in tasks"
            :key="task.id"
            class="task-row"
            :class="{ 'task-row--active': isSelected(task.id) }"
            @click="toggleTask(task.id)"
          >
            <el-checkbox
              :model-value="isSelected(task.id)"
              @click.stop
              @change="toggleTask(task.id)"
            />
            <div class="task-row__body">
              <div class="task-row__name">{{ task.name }}</div>
              <div class="task-row__meta">
                {{ task.remote_dir }} · S{{ String(task.season).padStart(2, '0') }} 起第
                {{ task.start_episode }} 集
              </div>
            </div>
          </div>
        </div>
        <el-empty
          v-else
          description="还没有上传任务，先到「任务配置」创建"
          :image-size="72"
        >
          <el-button @click="router.push('/upload/tasks')">去创建</el-button>
        </el-empty>
      </el-card>

      <!-- 执行参数 -->
      <el-card shadow="never" class="exec-card">
        <template #header>
          <div class="exec-card__header">
            <span class="exec-card__title">执行参数</span>
          </div>
        </template>
        <el-form label-position="top" class="exec-form">
          <el-form-item label="同名冲突">
            <el-select v-model="conflictPolicy" style="width: 100%">
              <el-option
                v-for="option in CONFLICT_OPTIONS"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
            <div class="form-tip">{{ conflictHint }}</div>
          </el-form-item>
          <el-row :gutter="12">
            <el-col :span="12">
              <el-form-item label="并发上传">
                <el-input-number
                  v-model="concurrency"
                  :min="1"
                  :max="8"
                  controls-position="right"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="失败重试">
                <el-input-number
                  v-model="retryTimes"
                  :min="0"
                  :max="10"
                  controls-position="right"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="试运行">
            <div class="switch-row">
              <el-switch v-model="dryRun" />
              <span class="switch-row__hint">只生成上传清单，不实际上传</span>
            </div>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 已选任务 -->
      <el-card shadow="never" class="exec-card">
        <template #header>
          <div class="exec-card__header">
            <span class="exec-card__title">已选任务</span>
            <el-button v-if="selectedIds.length > 0" link type="primary" @click="clearSelected">
              清空
            </el-button>
          </div>
        </template>
        <div v-if="selectedTasks.length > 0" class="selected-list">
          <div v-for="task in selectedTasks" :key="task.id" class="selected-row">
            <div class="selected-row__body">
              <div class="selected-row__name">{{ task.name }}</div>
              <div class="selected-row__meta">{{ task.local_dir }} → {{ task.remote_dir }}</div>
            </div>
            <el-button
              link
              type="danger"
              :icon="Close"
              aria-label="移除"
              @click="removeSelected(task.id)"
            />
          </div>
        </div>
        <el-empty v-else description="在左侧勾选要执行的任务" :image-size="64" />
        <div class="selected-footer">
          <span class="selected-footer__summary">共 {{ selectedTasks.length }} 个任务</span>
          <el-button
            type="primary"
            :icon="VideoPlay"
            :loading="executing"
            :disabled="selectedTasks.length === 0"
            @click="execute"
          >
            执行任务
          </el-button>
        </div>
      </el-card>
    </div>

    <!-- 正在执行 -->
    <el-card shadow="never" class="running-card">
      <template #header>
        <div class="exec-card__header">
          <span class="exec-card__title">正在执行</span>
          <el-button link :icon="Refresh" @click="loadRunning">刷新</el-button>
        </div>
      </template>
      <el-table :data="running" row-key="id" style="width: 100%">
        <el-table-column label="任务名称" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.task_name }}</template>
        </el-table-column>
        <el-table-column label="开始时间" width="150">
          <template #default="{ row }">{{ formatTime(row.started_time) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <StatusDot :status="(row.status as UploadExecutionStatus)" />
          </template>
        </el-table-column>
        <el-table-column label="进度" width="110" align="right">
          <template #default="{ row }">
            <span class="num">{{ progressText(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="170" align="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openRealtime(row)">查看日志</el-button>
            <el-button link type="danger" @click="cancelExecution(row)">取消</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="当前没有正在执行的上传" :image-size="64" />
        </template>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped lang="scss">
.upload-execution {
  display: flex;
  flex-direction: column;
  gap: var(--up-strm-space-4, 16px);

  &__cards {
    display: grid;
    grid-template-columns: minmax(0, 1.5fr) minmax(240px, 0.85fr) minmax(260px, 0.95fr);
    gap: var(--up-strm-space-4, 16px);
    align-items: stretch;
  }
}

.exec-card {
  display: flex;
  flex-direction: column;
  height: clamp(380px, 52vh, 560px);
  margin: 0;

  :deep(.el-card__body) {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  &__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--up-strm-space-2, 8px);
  }

  &__title {
    font-size: var(--up-strm-font-size-md, 14px);
    font-weight: 600;
    color: var(--el-text-color-primary);
  }

  &__hint {
    font-size: var(--up-strm-font-size-xs, 12px);
    color: var(--el-text-color-secondary);
  }
}

.task-list,
.selected-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.task-row {
  display: flex;
  align-items: flex-start;
  gap: var(--up-strm-space-2, 8px);
  padding: var(--up-strm-space-2, 8px) var(--up-strm-space-3, 12px);
  border-radius: var(--up-strm-radius-sm, 6px);
  cursor: pointer;
  transition: background-color 0.15s ease;

  &:hover {
    background: var(--el-fill-color-light);
  }

  &--active {
    background: var(--el-color-primary-light-9);
  }

  &__body {
    min-width: 0;
    flex: 1;
  }

  &__name {
    font-size: var(--up-strm-font-size-sm, 13px);
    color: var(--el-text-color-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__meta {
    margin-top: 2px;
    font-size: var(--up-strm-font-size-xs, 12px);
    color: var(--el-text-color-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.exec-form {
  :deep(.el-form-item) {
    margin-bottom: var(--up-strm-space-3, 12px);
  }
}

.form-tip {
  margin-top: 4px;
  font-size: var(--up-strm-font-size-xs, 12px);
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

.switch-row {
  display: flex;
  align-items: center;
  gap: var(--up-strm-space-2, 8px);

  &__hint {
    font-size: var(--up-strm-font-size-xs, 12px);
    color: var(--el-text-color-secondary);
  }
}

.selected-row {
  display: flex;
  align-items: center;
  gap: var(--up-strm-space-2, 8px);
  padding: var(--up-strm-space-2, 8px) var(--up-strm-space-3, 12px);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--up-strm-radius-sm, 6px);
  margin-bottom: var(--up-strm-space-2, 8px);

  &__body {
    min-width: 0;
    flex: 1;
  }

  &__name {
    font-size: var(--up-strm-font-size-sm, 13px);
    color: var(--el-text-color-primary);
  }

  &__meta {
    margin-top: 2px;
    font-size: var(--up-strm-font-size-xs, 12px);
    color: var(--el-text-color-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.selected-footer {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--up-strm-space-2, 8px);
  padding-top: var(--up-strm-space-3, 12px);
  border-top: 1px solid var(--el-border-color-lighter);

  &__summary {
    font-size: var(--up-strm-font-size-xs, 12px);
    color: var(--el-text-color-secondary);
  }
}

.running-card {
  margin: 0;

  :deep(.el-table) {
    font-variant-numeric: tabular-nums;
  }
}

.num {
  font-variant-numeric: tabular-nums;
  color: var(--el-text-color-regular);
}

@media (max-width: 1200px) {
  .upload-execution__cards {
    grid-template-columns: minmax(0, 1fr) minmax(220px, 0.8fr) minmax(240px, 0.9fr);
  }
}

@media (max-width: 1100px) {
  .upload-execution__cards {
    grid-template-columns: 1fr;
  }

  .exec-card {
    height: auto;
    min-height: 320px;

    :deep(.el-card__body) {
      max-height: 60vh;
    }
  }
}
</style>
