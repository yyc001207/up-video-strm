<script setup lang="ts">
/**
 * 云盘上传 · 开始执行（/upload/execution）。
 *
 * 与STRM 生成开始执行保持同一套结构与样式：三张卡片一行工作区
 * （左「选择任务」、中「执行参数」、右「已选任务」），下方「正在执行」表 5s 轮询。
 *
 * 执行时序：本页只调用 batchCreateExecutions 落库，随后带参跳转运行详情页，
 * 由运行详情页在 WebSocket 连接成功后再逐个启动（排队串行），确保完整记录日志。
 * 差异点：上传模块的执行参数为「同名冲突 / 并发上传 / 失败重试 / 试运行」。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Close, Refresh, RefreshLeft, Search, Select, VideoPlay } from '@element-plus/icons-vue'

import StatusDot from '@/components/StatusDot.vue'
import { uploaderApi } from '@/api/uploader'
import { formatDateTime } from '@/utils/date'
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

const ROUTE_REALTIME = '/upload/realtime'
const POLL_INTERVAL_MS = 5000

const router = useRouter()

const loading = ref(false)
const runningLoading = ref(false)
const executing = ref(false)
const cancellingId = ref<number | null>(null)

const tasks = ref<UploadTask[]>([])
const running = ref<UploadExecution[]>([])
const selectedIds = ref<number[]>([])
const keyword = ref('')
const conflictPolicy = ref<UploadConflictPolicy>('skip')
const concurrency = ref(2)
const retryTimes = ref(3)
const dryRun = ref(false)

const filteredTasks = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return tasks.value
  return tasks.value.filter(task => {
    return (
      task.name.toLowerCase().includes(kw) ||
      (task.local_dir || '').toLowerCase().includes(kw) ||
      (task.remote_dir || '').toLowerCase().includes(kw)
    )
  })
})
const selectedTasks = computed(() => tasks.value.filter(task => selectedIds.value.includes(task.id)))
const canStart = computed(() => selectedIds.value.length > 0)
const allSelected = computed(
  () => filteredTasks.value.length > 0 && filteredTasks.value.every(task => isSelected(task.id))
)
const conflictHint = computed(
  () => CONFLICT_OPTIONS.find(option => option.value === conflictPolicy.value)?.hint ?? ''
)

let pollTimer: ReturnType<typeof setInterval> | null = null
/** 组件是否已卸载：异步首屏加载完成时避免在卸载后继续启动轮询。 */
let disposed = false

function isSelected(taskId: number): boolean {
  return selectedIds.value.includes(taskId)
}

function toggleTask(taskId: number): void {
  if (executing.value) return
  selectedIds.value = isSelected(taskId)
    ? selectedIds.value.filter(id => id !== taskId)
    : [...selectedIds.value, taskId]
}

function removeSelected(taskId: number): void {
  selectedIds.value = selectedIds.value.filter(id => id !== taskId)
}

function clearSelection(): void {
  selectedIds.value = []
}

/** 全选 / 取消全选（卡片底部右侧按钮），仅作用于当前筛选结果。 */
function toggleSelectAll(): void {
  if (executing.value) return
  if (allSelected.value) {
    const visibleIds = new Set(filteredTasks.value.map(task => task.id))
    selectedIds.value = selectedIds.value.filter(id => !visibleIds.has(id))
    return
  }
  const merged = new Set(selectedIds.value)
  for (const task of filteredTasks.value) merged.add(task.id)
  selectedIds.value = [...merged]
}

/** 进度文本：0/0 显示「—」降噪，等宽数字对齐。 */
function progressText(row: UploadExecution): string {
  return row.file_total > 0 ? `${row.file_success}/${row.file_total}` : '—'
}

/** 谁启动的：自动追更触发时展示任务名，其余为手动。 */
function triggerText(row: UploadExecution): string {
  if (row.trigger_source !== 'automation') return '手动'
  return row.trigger_name ? `自动化 · ${row.trigger_name}` : '自动化'
}

function taskMeta(task: UploadTask): string {
  const season = `S${String(task.season).padStart(2, '0')}`
  return `${task.remote_dir || '（未设置云端目录）'} · ${season} 起第 ${task.start_episode} 集`
}

async function loadTasks(): Promise<void> {
  const res = await uploaderApi.listTasks()
  tasks.value = res.data
}

async function loadRunning(silent = false): Promise<void> {
  if (!silent) runningLoading.value = true
  try {
    // silent 同时透传到 axios 请求：轮询失败不再弹窗，交给全局错误治理
    const res = await uploaderApi.listExecutions(
      { status: 'running', page: 1, pageSize: 50 },
      { silent }
    )
    running.value = res.data.list
  } finally {
    if (!silent) runningLoading.value = false
  }
}

async function load(): Promise<void> {
  loading.value = true
  try {
    await Promise.all([loadTasks(), loadRunning()])
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

async function execute(): Promise<void> {
  if (selectedIds.value.length === 0) {
    ElMessage.warning('请先在左侧勾选要执行的任务')
    return
  }
  if (executing.value) return
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
    await router.push({
      path: ROUTE_REALTIME,
      query: { execs: JSON.stringify(targets) }
    })
  } catch {
    /* 拦截器已提示 */
  } finally {
    executing.value = false
  }
}

async function cancelExecution(row: UploadExecution): Promise<void> {
  if (cancellingId.value !== null) return
  try {
    await ElMessageBox.confirm(
      `确认取消任务「${row.task_name}」的当前上传执行？已上传的文件会保留。`,
      '取消执行',
      { type: 'warning', confirmButtonText: '取消执行', cancelButtonText: '继续执行' }
    )
  } catch {
    return
  }
  cancellingId.value = row.id
  try {
    await uploaderApi.cancelExecution(row.id)
    ElMessage.success('已请求取消')
    await loadRunning()
  } catch {
    /* 拦截器已提示 */
  } finally {
    cancellingId.value = null
  }
}

function openRealtime(row: UploadExecution): void {
  const targets: RealtimeTarget[] = [
    { executionId: row.id, taskId: row.task_id, taskName: row.task_name }
  ]
  void router.push({ path: ROUTE_REALTIME, query: { execs: JSON.stringify(targets) } })
}

function goTasks(): void {
  void router.push('/upload/tasks')
}

onMounted(async () => {
  await load()
  if (disposed) return
  pollTimer = setInterval(() => {
    void loadRunning(true)
  }, POLL_INTERVAL_MS)
})

onBeforeUnmount(() => {
  disposed = true
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
              <p class="exec-panel__sub">展示全部上传任务，可搜索任务名称或目录</p>
            </div>
            <span class="exec-panel__count">已选 {{ selectedIds.length }}</span>
          </header>

          <div class="exec-panel__body">
            <div class="task-filters">
              <el-input
                v-model="keyword"
                class="task-filters__search"
                placeholder="搜索任务名称 / 目录"
                clearable
                :prefix-icon="Search"
              />
            </div>

            <el-empty
              v-if="tasks.length === 0"
              class="exec-panel__empty"
              description="还没有上传任务，先到「任务」创建"
              :image-size="72"
            >
              <el-button type="primary" plain @click="goTasks">前往任务</el-button>
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
                :class="{ 'is-selected': isSelected(task.id) }"
                role="checkbox"
                :aria-checked="isSelected(task.id)"
                :aria-label="task.name"
                tabindex="0"
                @click="toggleTask(task.id)"
                @keydown.enter.prevent="toggleTask(task.id)"
                @keydown.space.prevent="toggleTask(task.id)"
              >
                <span class="task-row__check" @click.stop>
                  <el-checkbox
                    :model-value="isSelected(task.id)"
                    @change="toggleTask(task.id)"
                  />
                </span>
                <span class="task-row__info">
                  <span class="task-row__name">{{ task.name }}</span>
                  <span class="task-row__path" :title="taskMeta(task)">{{ taskMeta(task) }}</span>
                </span>
              </div>
            </div>

            <div v-if="tasks.length > 0" class="exec-panel__footer">
              <span class="exec-panel__footer-hint">
                可选 {{ filteredTasks.length }} 个 · 已选 {{ selectedIds.length }} 个
              </span>
              <el-button
                link
                type="primary"
                :icon="Select"
                :disabled="filteredTasks.length === 0 || executing"
                @click="toggleSelectAll"
              >
                {{ allSelected ? '取消全选' : '全选' }}
              </el-button>
            </div>
          </div>
        </section>

        <!-- 中栏：执行参数 -->
        <aside class="exec-panel exec-panel--params">
          <header class="exec-panel__head">
            <div class="exec-panel__heading">
              <h2 class="exec-panel__title">执行参数</h2>
              <p class="exec-panel__sub">参数将应用到本次选中的全部任务</p>
            </div>
          </header>

          <div class="exec-panel__body">
            <div class="param-block">
              <span class="param-block__label">同名冲突</span>
              <el-select v-model="conflictPolicy" :disabled="executing" style="width: 100%">
                <el-option
                  v-for="option in CONFLICT_OPTIONS"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
              <p class="param-block__hint">{{ conflictHint }}</p>
            </div>

            <div class="param-block">
              <span class="param-block__label">并发上传</span>
              <el-input-number
                v-model="concurrency"
                :min="1"
                :max="8"
                :disabled="executing"
                controls-position="right"
                style="width: 100%"
              />
              <p class="param-block__hint">同时上传的文件数，过大可能触发云端限流。</p>
            </div>

            <div class="param-block">
              <span class="param-block__label">失败重试</span>
              <el-input-number
                v-model="retryTimes"
                :min="0"
                :max="10"
                :disabled="executing"
                controls-position="right"
                style="width: 100%"
              />
              <p class="param-block__hint">单个文件上传失败后的重试次数。</p>
            </div>

            <div class="param-block">
              <span class="param-block__label">试运行</span>
              <div class="switch-row">
                <el-switch v-model="dryRun" :disabled="executing" />
                <span class="switch-row__hint">只生成上传清单，不实际上传</span>
              </div>
            </div>

            <p class="param-note">
              执行记录创建后会跳转到运行详情页，日志连接成功后才开始逐个执行，确保完整记录本次执行日志。
            </p>
          </div>
        </aside>

        <!-- 右栏：已选任务 -->
        <section class="exec-panel exec-panel--selected">
          <header class="exec-panel__head">
            <div class="exec-panel__heading">
              <h2 class="exec-panel__title">已选任务</h2>
              <p class="exec-panel__sub">确认选中项后执行，参数应用到全部任务</p>
            </div>
            <span class="exec-panel__count">{{ selectedIds.length }}</span>
          </header>

          <div class="exec-panel__body">
            <el-empty
              v-if="selectedTasks.length === 0"
              class="exec-panel__empty"
              description="在左侧勾选要上传的任务"
              :image-size="64"
            />
            <div v-else class="selected-list">
              <div v-for="task in selectedTasks" :key="task.id" class="selected-row">
                <span class="selected-row__info">
                  <span class="selected-row__name">{{ task.name }}</span>
                  <span class="selected-row__path" :title="taskMeta(task)">{{ taskMeta(task) }}</span>
                </span>
                <el-button
                  link
                  :icon="Close"
                  :disabled="executing"
                  aria-label="移除该任务"
                  @click="removeSelected(task.id)"
                />
              </div>
            </div>

            <div class="selected-summary">
              已选 <strong class="selected-summary__num">{{ selectedIds.length }}</strong> 个任务
            </div>
            <div class="selected-actions">
              <el-button
                :icon="RefreshLeft"
                :disabled="selectedIds.length === 0 || executing"
                @click="clearSelection"
              >
                清空选择
              </el-button>
              <el-button
                type="primary"
                :icon="VideoPlay"
                :loading="executing"
                :disabled="!canStart"
                @click="execute"
              >
                执行任务
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
            <span class="exec-running__count">{{ running.length }}</span>
          </div>
          <el-button link :icon="Refresh" :loading="runningLoading" @click="loadRunning()">
            刷新
          </el-button>
        </header>
        <el-table
          v-loading="runningLoading"
          :data="running"
          row-key="id"
          :max-height="320"
          class="exec-running__table"
          empty-text="暂无正在执行的上传任务"
        >
          <el-table-column prop="task_name" label="任务" min-width="180" show-overflow-tooltip />
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <StatusDot :status="(row.status as UploadExecutionStatus)" />
            </template>
          </el-table-column>
          <el-table-column label="谁启动的" width="150" show-overflow-tooltip>
            <template #default="{ row }">
              <el-tag
                :type="row.trigger_source === 'automation' ? 'warning' : 'info'"
                size="small"
                effect="plain"
              >
                {{ triggerText(row) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="进度" width="110" align="right">
            <template #default="{ row }">
              <span class="exec-running__num" :class="{ 'is-muted': !row.file_total }">
                {{ progressText(row) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="开始时间" width="172">
            <template #default="{ row }">{{ formatDateTime(row.started_time) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="160" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openRealtime(row)">查看日志</el-button>
              <el-button
                link
                type="danger"
                :loading="cancellingId === row.id"
                @click="cancelExecution(row)"
              >
                取消
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

// 面板通用骨架（与STRM 生成开始执行保持一致）
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
    gap: var(--up-strm-space-2);

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

  .switch-row {
    display: flex;
    align-items: center;
    gap: var(--up-strm-space-2);

    &__hint {
      color: var(--el-text-color-secondary);
      font-size: var(--up-strm-font-size-xs);
      line-height: 1.5;
    }
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

    &.is-muted {
      color: var(--el-text-color-placeholder);
    }
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
