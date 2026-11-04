<script setup lang="ts">
/**
 * 任务调度 · 执行管理（/schedule/execution）。
 *
 * 双栏工作区：左「选择任务」（服务器 + 搜索 + 复选列表），右「执行参数」（分段模式 + 高级选项）；
 * 底部常驻操作条展示已选任务 / 视频数并提供清空与执行；「正在执行」表 5s 轮询。
 *
 * 执行时序保持不变：本页只调用 batchCreateExecution 落库，随后带参跳转实时日志页，
 * 由实时日志页在 WebSocket 连接成功后再调用 startExecution（避免漏日志）。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, RefreshLeft, Search, VideoPlay } from '@element-plus/icons-vue'

import StatusDot from '@/components/StatusDot.vue'
import { useOpenlistStore } from '@/stores/openlist'
import type { OpenListExecution, OpenListTask } from '@/types/openlist'
import { formatDateTime } from '@/utils/date'

/** 执行模式：用互斥分段控件表达，映射到后端三个布尔开关（替代旧版三个开关 + 隐含联动）。 */
type ExecutionMode = 'incremental' | 'full' | 'strm-only'

interface ModeFlags {
  is_incremental: boolean
  is_force: boolean
  strm_only: boolean
}

/** 跳转实时日志页的单个执行入参（与实时日志页约定一致）。 */
interface LaunchNavItem {
  executionId: number
  taskId: number
  taskName: string
  launch: boolean
}

const MODE_OPTIONS: Array<{ label: string; value: ExecutionMode }> = [
  { label: '增量更新', value: 'incremental' },
  { label: '全量重生成', value: 'full' },
  { label: '仅更新 strm', value: 'strm-only' }
]

const MODE_FLAGS: Record<ExecutionMode, ModeFlags> = {
  incremental: { is_incremental: true, is_force: false, strm_only: false },
  full: { is_incremental: false, is_force: true, strm_only: false },
  'strm-only': { is_incremental: true, is_force: false, strm_only: true }
}

const MODE_HINT: Record<ExecutionMode, string> = {
  incremental: '跳过已存在的 STRM 与字幕，只处理新增内容，耗时最短。',
  full: '忽略已有产物，重新生成全部 STRM 与字幕，耗时最长。',
  'strm-only': '只更新 STRM 文件，不重新下载已存在的字幕。'
}

const ROUTE_REALTIME = '/schedule/realtime'
const POLL_INTERVAL_MS = 5000

const router = useRouter()
const store = useOpenlistStore()

const loading = ref(false)
const runningLoading = ref(false)
const starting = ref(false)
const cancellingId = ref<number | null>(null)

const selectedServerId = ref<number | null>(null)
const selectedTaskIds = ref<number[]>([])
const keyword = ref('')
const execMode = ref<ExecutionMode>('incremental')
const stripSeries = ref(false)
const advancedPanels = ref<string[]>([])

const activeServers = computed(() => store.servers.filter(server => server.is_active))
/** 任务强关联服务器：只展示所选服务器的任务配置。 */
const taskOptions = computed(() => store.tasks.filter(task => task.server_id === selectedServerId.value))
const filteredTasks = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return taskOptions.value
  return taskOptions.value.filter(task => {
    return (
      task.name.toLowerCase().includes(kw) ||
      (task.process_path || '').toLowerCase().includes(kw) ||
      (task.output_dir || '').toLowerCase().includes(kw)
    )
  })
})
const selectedTasks = computed(() =>
  taskOptions.value.filter(task => selectedTaskIds.value.includes(task.id))
)
/** 已选任务的视频总数：按各任务最近一次执行的视频数估算。 */
const totalVideos = computed(() =>
  selectedTasks.value.reduce((sum, task) => sum + (task.last_execution?.video_total_count ?? 0), 0)
)
const canStart = computed(
  () => selectedServerId.value != null && selectedTaskIds.value.length > 0
)

let pollTimer: ReturnType<typeof setInterval> | null = null
/** 组件是否已卸载：异步首屏加载完成时避免在卸载后继续启动轮询。 */
let disposed = false

function isSelected(taskId: number): boolean {
  return selectedTaskIds.value.includes(taskId)
}

/** 任务是否锁定：执行中不可重复选择；提交过程中锁定全部选择。 */
function isLocked(taskId: number): boolean {
  return starting.value || store.runningTaskIds.has(taskId)
}

function toggleTask(task: OpenListTask): void {
  if (isLocked(task.id)) return
  const index = selectedTaskIds.value.indexOf(task.id)
  if (index >= 0) {
    selectedTaskIds.value.splice(index, 1)
  } else {
    selectedTaskIds.value.push(task.id)
  }
}

function clearSelection(): void {
  selectedTaskIds.value = []
}

/**
 * 行级键盘操作：仅当焦点在行本身时响应，避免行内 checkbox 聚焦时回车/空格被行重复处理
 * （checkbox 自身的空格行为由浏览器原生触发 change）。
 */
function handleRowKeydown(event: KeyboardEvent, task: OpenListTask): void {
  if (event.target !== event.currentTarget) return
  event.preventDefault()
  toggleTask(task)
}

function handleServerChange(): void {
  // 任务强关联服务器，切换服务器后旧选择不再有效
  selectedTaskIds.value = []
  keyword.value = ''
}

/** 首屏/刷新后校正服务器选择，避免配置变化后指向已删除服务器。 */
function ensureServer(): void {
  const exists = activeServers.value.some(server => server.id === selectedServerId.value)
  if (!exists) {
    selectedServerId.value = activeServers.value[0]?.id ?? null
    selectedTaskIds.value = []
  }
}

/** 计数文本：0/0 显示「—」降噪，等宽数字对齐。 */
function countText(success: number, total: number): string {
  return total > 0 ? `${success}/${total}` : '—'
}

function lastExecutionText(task: OpenListTask): string {
  const last = task.last_execution
  if (!last) return '尚无执行记录'
  return `最近 ${last.video_total_count} 个视频`
}

async function refreshRunning(silent = false): Promise<void> {
  if (!silent) runningLoading.value = true
  try {
    await store.fetchRunning()
  } catch {
    /* 拦截器已提示 */
  } finally {
    if (!silent) runningLoading.value = false
  }
}

async function load(): Promise<void> {
  loading.value = true
  try {
    await Promise.all([store.fetchConfig(), store.fetchTasks(), refreshRunning()])
    ensureServer()
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

async function handleStart(): Promise<void> {
  if (selectedServerId.value == null) {
    ElMessage.warning('请先选择服务器')
    return
  }
  if (selectedTaskIds.value.length === 0) {
    ElMessage.warning('请至少选择一个任务')
    return
  }
  if (starting.value) return

  // 轮询可能发现已选任务被其他入口启动：跳过执行中的任务，避免重复执行
  const requestedIds = selectedTaskIds.value.filter(taskId => !store.runningTaskIds.has(taskId))
  const skippedCount = selectedTaskIds.value.length - requestedIds.length
  if (requestedIds.length === 0) {
    ElMessage.warning('所选任务均处于执行中，请等待当前执行结束')
    return
  }
  if (skippedCount > 0) {
    ElMessage.info(`已跳过 ${skippedCount} 个正在执行的任务`)
  }

  const serverId = selectedServerId.value
  const flags = MODE_FLAGS[execMode.value]
  starting.value = true
  try {
    // 仅创建执行记录（落库，不启动后台），启动由实时日志页在日志连接成功后触发
    const executions = await store.batchCreateExecution(
      serverId,
      requestedIds.map(taskId => ({
        task_id: taskId,
        ...flags,
        strip_series: stripSeries.value
      }))
    )
    if (executions.length === 0) {
      ElMessage.warning('未创建任何执行记录，请重试')
      return
    }
    const taskNameMap = new Map<number, string>(store.tasks.map(task => [task.id, task.name]))
    const items: LaunchNavItem[] = executions.map(execution => ({
      executionId: execution.id,
      taskId: execution.task_id,
      taskName: taskNameMap.get(execution.task_id) ?? execution.task_name ?? `任务 #${execution.task_id}`,
      launch: true
    }))
    await router.push({
      path: ROUTE_REALTIME,
      query: { execs: JSON.stringify(items), server: String(serverId) }
    })
  } catch {
    /* 拦截器已提示 */
  } finally {
    starting.value = false
  }
}

async function handleViewLog(execution: OpenListExecution): Promise<void> {
  // launch:false：只查看正在运行的执行日志，不重复启动
  const items: LaunchNavItem[] = [
    {
      executionId: execution.id,
      taskId: execution.task_id,
      taskName: execution.task_name,
      launch: false
    }
  ]
  const query: Record<string, string> = { execs: JSON.stringify(items) }
  if (execution.server_id != null) {
    query.server = String(execution.server_id)
  }
  await router.push({ path: ROUTE_REALTIME, query })
}

async function handleCancel(execution: OpenListExecution): Promise<void> {
  if (cancellingId.value !== null) return
  try {
    await ElMessageBox.confirm(
      `确认取消任务「${execution.task_name}」的当前执行？已生成的文件会保留。`,
      '取消执行',
      { type: 'warning', confirmButtonText: '取消执行', cancelButtonText: '继续执行' }
    )
  } catch {
    return
  }
  cancellingId.value = execution.id
  try {
    await store.cancelExecution(execution.id)
    ElMessage.success('已请求取消')
  } catch {
    /* 拦截器已提示 */
  } finally {
    cancellingId.value = null
  }
}

/** 运行中行加 amber 左边条（其余状态不加）。 */
function runningRowClassName({ row }: { row: OpenListExecution }): string {
  return row.status === 'running' ? 'is-running' : ''
}

function goConfig(): void {
  void router.push('/schedule/config')
}

function goTasks(): void {
  void router.push('/schedule/tasks')
}

onMounted(async () => {
  await load()
  if (disposed) return
  // 「正在执行」表 5s 轮询；静默刷新避免表格 loading 遮挡
  pollTimer = setInterval(() => {
    void refreshRunning(true)
  }, POLL_INTERVAL_MS)
})

onUnmounted(() => {
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
              <p class="exec-panel__sub">仅展示所选服务器下的任务；执行中的任务不可重复选择</p>
            </div>
            <span class="exec-panel__count">已选 {{ selectedTaskIds.length }}</span>
          </header>

          <div class="exec-panel__body">
            <template v-if="activeServers.length > 0">
              <div class="task-filters">
                <el-select
                  v-model="selectedServerId"
                  class="task-filters__server"
                  placeholder="选择服务器"
                  :disabled="starting"
                  @change="handleServerChange"
                >
                  <el-option
                    v-for="server in activeServers"
                    :key="server.id"
                    :label="server.name || server.server_url"
                    :value="server.id"
                  />
                </el-select>
                <el-input
                  v-model="keyword"
                  class="task-filters__search"
                  placeholder="搜索任务名称 / 路径"
                  clearable
                  :prefix-icon="Search"
                />
              </div>

              <el-empty
                v-if="taskOptions.length === 0"
                class="exec-panel__empty"
                description="该服务器下暂无任务配置"
                :image-size="72"
              >
                <el-button type="primary" plain @click="goTasks">前往任务配置</el-button>
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
                    'is-running': store.runningTaskIds.has(task.id)
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
                    <span class="task-row__path" :title="task.process_path">{{ task.process_path }}</span>
                  </span>
                  <span class="task-row__meta">
                    <span class="task-row__count">{{ lastExecutionText(task) }}</span>
                    <el-tag
                      v-if="store.runningTaskIds.has(task.id)"
                      type="warning"
                      size="small"
                      effect="light"
                    >
                      执行中
                    </el-tag>
                  </span>
                </div>
              </div>
            </template>
            <el-empty
              v-else
              class="exec-panel__empty"
              description="暂无可用服务器配置"
              :image-size="72"
            >
              <el-button type="primary" plain @click="goConfig">前往全局配置</el-button>
            </el-empty>
          </div>
        </section>

        <!-- 右栏：执行参数 -->
        <aside class="exec-panel exec-panel--params">
          <header class="exec-panel__head">
            <div class="exec-panel__heading">
              <h2 class="exec-panel__title">执行参数</h2>
              <p class="exec-panel__sub">参数将应用到本次选中的全部任务</p>
            </div>
          </header>

          <div class="exec-panel__body">
            <div class="param-block">
              <span class="param-block__label">执行模式</span>
              <el-segmented
                v-model="execMode"
                :options="MODE_OPTIONS"
                :disabled="starting"
                block
              />
              <p class="param-block__hint">{{ MODE_HINT[execMode] }}</p>
            </div>

            <el-collapse v-model="advancedPanels" class="param-advanced">
              <el-collapse-item name="advanced" title="高级选项">
                <div class="param-switch">
                  <div class="param-switch__text">
                    <span class="param-switch__label">系列层优化</span>
                    <p class="param-switch__hint">
                      默认关闭；开启后输出目录移除「电影」目录下的「系列」层级（如
                      动画电影/哆啦A梦系列/剧场版 → 动画电影/剧场版），strm 内链接仍保留原始完整路径
                    </p>
                  </div>
                  <el-switch v-model="stripSeries" :disabled="starting" />
                </div>
              </el-collapse-item>
            </el-collapse>

            <p class="param-note">
              执行记录创建后会跳转到实时日志页，日志连接成功后才开始执行，确保完整记录本次执行日志。
            </p>
          </div>
        </aside>
      </div>

      <!-- 正在执行 -->
      <section class="exec-running">
        <header class="exec-running__head">
          <div class="exec-running__heading">
            <h2 class="exec-running__title">正在执行</h2>
            <span class="exec-running__count">{{ store.runningExecutions.length }}</span>
          </div>
          <el-button link :icon="Refresh" :loading="runningLoading" @click="refreshRunning()">
            刷新
          </el-button>
        </header>
        <el-table
          v-loading="runningLoading"
          :data="store.runningExecutions"
          row-key="id"
          :row-class-name="runningRowClassName"
          :max-height="320"
          class="exec-running__table"
          empty-text="暂无正在执行的任务"
        >
          <el-table-column prop="task_name" label="任务" min-width="180" show-overflow-tooltip />
          <el-table-column label="服务器" width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.server_name || '—' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <StatusDot :status="row.status" />
            </template>
          </el-table-column>
          <el-table-column label="视频" width="96" align="right">
            <template #default="{ row }">
              <span
                class="exec-running__num"
                :class="{ 'is-muted': !row.video_total_count }"
              >{{ countText(row.video_success_count, row.video_total_count) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="字幕" width="96" align="right">
            <template #default="{ row }">
              <span
                class="exec-running__num"
                :class="{ 'is-muted': !row.subtitle_total_count }"
              >{{ countText(row.subtitle_success_count, row.subtitle_total_count) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="开始时间" width="172">
            <template #default="{ row }">{{ formatDateTime(row.started_time) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="160" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="handleViewLog(row)">查看日志</el-button>
              <el-button
                link
                type="danger"
                :loading="cancellingId === row.id"
                @click="handleCancel(row)"
              >
                取消
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>
    </div>

    <!-- 底部常驻操作条 -->
    <footer class="exec-footer">
      <div
        class="exec-footer__summary"
        title="视频数按各任务最近一次执行的视频总数估算"
      >
        <span class="exec-footer__text">
          已选 <strong class="exec-footer__num">{{ selectedTaskIds.length }}</strong> 个任务 ·
          共 <strong class="exec-footer__num">{{ totalVideos }}</strong> 个视频
        </span>
        <span v-if="selectedTaskIds.length === 0" class="exec-footer__hint">选择任务后可执行</span>
      </div>
      <div class="exec-footer__actions">
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
          执行任务
        </el-button>
      </div>
    </footer>
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
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: var(--up-strm-space-4);
  align-items: stretch;
  min-height: 420px;
}

// 面板通用骨架
.exec-panel {
  display: flex;
  flex-direction: column;
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
}

// 服务器 / 搜索
.task-filters {
  display: flex;
  flex: none;
  gap: var(--up-strm-space-2);

  &__server {
    flex: none;
    width: 210px;
  }

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
  max-height: min(46vh, 420px);
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

  .param-advanced {
    flex: none;
    border-top: 1px solid var(--el-border-color-lighter);
    border-bottom: none;

    :deep(.el-collapse-item__header) {
      color: var(--el-text-color-regular);
      font-size: var(--up-strm-font-size-sm);
      font-weight: 600;
      border-bottom-color: var(--el-border-color-lighter);
    }

    :deep(.el-collapse-item__wrap) {
      background: transparent;
      border-bottom: none;
    }

    :deep(.el-collapse-item__content) {
      padding-bottom: 0;
    }
  }

  .param-switch {
    display: flex;
    align-items: flex-start;
    gap: var(--up-strm-space-3);
    padding-top: var(--up-strm-space-2);

    &__text {
      flex: 1;
      min-width: 0;
    }

    &__label {
      display: block;
      color: var(--el-text-color-primary);
      font-size: var(--up-strm-font-size-sm);
      font-weight: 500;
      line-height: 1.5;
    }

    &__hint {
      margin: var(--up-strm-space-1) 0 0;
      color: var(--el-text-color-secondary);
      font-size: var(--up-strm-font-size-xs);
      line-height: 1.6;
    }

    :deep(.el-switch) {
      flex: none;
    }
  }

  .param-note {
    margin: auto 0 0;
    padding-top: var(--up-strm-space-3);
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

    :deep(.el-table__row.is-running td:first-child) {
      box-shadow: inset 3px 0 0 0 var(--el-color-warning);
    }
  }
}

// 底部常驻操作条：始终可见（P0-2）
.exec-footer {
  position: sticky;
  bottom: 0;
  z-index: 10;
  display: flex;
  flex: none;
  align-items: center;
  justify-content: space-between;
  gap: var(--up-strm-space-4);
  padding: var(--up-strm-space-3) var(--up-strm-space-4);
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: var(--up-strm-radius-lg);
  box-shadow: var(--up-strm-shadow-md);

  &__summary {
    display: flex;
    flex-direction: column;
    gap: var(--up-strm-space-1);
    min-width: 0;
  }

  &__text {
    color: var(--el-text-color-regular);
    font-size: var(--up-strm-font-size-base);
    line-height: 1.5;
  }

  &__num {
    color: var(--el-text-color-primary);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  &__hint {
    color: var(--el-text-color-secondary);
    font-size: var(--up-strm-font-size-xs);
    line-height: 1.5;
  }

  &__actions {
    display: flex;
    flex: none;
    align-items: center;
    gap: var(--up-strm-space-2);
  }
}

@media (max-width: 1100px) {
  .exec-workspace {
    grid-template-columns: minmax(0, 1fr);
    min-height: 0;
  }

  .task-list {
    max-height: min(40vh, 320px);
  }
}

@media (max-width: 720px) {
  .task-filters {
    flex-direction: column;
  }

  .task-filters__server {
    width: 100%;
  }

  .exec-footer {
    flex-direction: column;
    align-items: stretch;
  }

  .exec-footer__actions {
    justify-content: flex-end;
  }
}
</style>
