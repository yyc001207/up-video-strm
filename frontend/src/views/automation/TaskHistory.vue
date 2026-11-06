<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { FolderOpened, Refresh, RefreshRight, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { desktopApi } from '@/api/desktop'
import { automationApi, automationRunApi } from '@/api/automation'
import type { AutomationExecutionBrief, AutomationRun, AutomationRunStatus, AutomationTask } from '@/types/automation'

const router = useRouter()

const STATUS_OPTIONS: { label: string; value: AutomationRunStatus | 'all' }[] = [
  { label: '全部状态', value: 'all' },
  { label: '运行中', value: 'running' },
  { label: '成功', value: 'success' },
  { label: '部分成功', value: 'partial' },
  { label: '失败', value: 'fail' },
  { label: '已取消', value: 'cancelled' },
]

const STATUS_LABELS: Record<AutomationRunStatus, string> = {
  running: '运行中',
  success: '成功',
  partial: '部分成功',
  fail: '失败',
  cancelled: '已取消',
}

const STATUS_TAG_TYPES: Record<AutomationRunStatus, 'success' | 'warning' | 'danger' | 'info'> = {
  running: 'warning',
  success: 'success',
  partial: 'warning',
  fail: 'danger',
  cancelled: 'info',
}

const PHASE_LABELS: Record<string, string> = {
  starting: '启动中',
  waiting_idle: '等待空闲',
  waiting_upload: '等待上传完成',
  waiting_openlist_check: '等待 OpenList 可见',
  waiting_openlist_task: '等待 STRM 完成',
  interval: '轮次间隔',
  backoff: '失败退避',
  idle: '空闲等待',
  stopped: '已停止',
  done: '本轮完成',
}

const tasks = ref<AutomationTask[]>([])
const list = ref<AutomationRun[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const PAGE_SIZES = [10, 20, 50]
const taskFilter = ref<number | null>(null)
const statusFilter = ref<AutomationRunStatus | 'all'>('all')
/** 时间范围筛选（按运行开始时间，API 以北京时间日期解释起止日）。 */
const dateRange = ref<[string, string] | null>(null)

const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<AutomationRun | null>(null)

const logVisible = ref(false)
const logLoading = ref(false)
const logLines = ref<{ index: number; level: string; message: string }[]>([])
const logRun = ref<AutomationRun | null>(null)

function statusText(status: string): string {
  return STATUS_LABELS[status as AutomationRunStatus] ?? status
}

function phaseText(phase: string): string {
  return PHASE_LABELS[phase] ?? phase
}

function statusTagType(status: string): 'success' | 'warning' | 'danger' | 'info' {
  return STATUS_TAG_TYPES[status as AutomationRunStatus] ?? 'info'
}

/** 执行摘要：成功/跳过/失败 展示文本。 */
function briefText(brief: AutomationExecutionBrief | null): string {
  if (!brief) return '—'
  return `#${brief.id} · ${statusText(brief.status)}`
}

const emptyDescription = computed(() => {
  if (taskFilter.value !== null || statusFilter.value !== 'all' || dateRange.value !== null) return '没有匹配的运行记录'
  return '暂无运行记录（启动自动追更后才会生成记录）'
})

async function loadTasks() {
  const res = await automationApi.listTasks({ page: 1, page_size: 100 })
  tasks.value = res.data
}

async function load() {
  loading.value = true
  try {
    const range = dateRange.value
    const res = await automationRunApi.listRuns({
      task_id: taskFilter.value ?? undefined,
      status: statusFilter.value === 'all' ? undefined : statusFilter.value,
      start_time: range?.[0],
      end_time: range?.[1],
      page: page.value,
      page_size: pageSize.value,
    })
    list.value = res.data
    total.value = res.total ?? 0
  } finally {
    loading.value = false
  }
}

function handleFilterChange() {
  page.value = 1
  load()
}

function handlePageChange() {
  load()
}

function handleSizeChange() {
  page.value = 1
  load()
}

async function openDetail(row: AutomationRun) {
  detail.value = row
  detailVisible.value = true
  detailLoading.value = true
  try {
    const res = await automationRunApi.getRun(row.id)
    detail.value = res.data
  } finally {
    detailLoading.value = false
  }
}

async function openLogs(row: AutomationRun) {
  logRun.value = row
  logVisible.value = true
  logLoading.value = true
  logLines.value = []
  try {
    const res = await automationRunApi.runLogs(row.id, 0, 1000)
    logLines.value = res.data.lines
  } finally {
    logLoading.value = false
  }
}

function openRealtime(row: AutomationRun) {
  router.push({ path: '/automation/realtime', query: { task_id: String(row.task_id) } })
}

function openLogDir() {
  desktopApi.openLogDir('automation').catch(() => {
    /* 拦截器提示 */
  })
}

/** 把失败运行的缺失文件写回待校验，下一轮优先补偿（不自动启动）。 */
async function handleRetryFailed(row: AutomationRun) {
  const missedCount = row.missed_files.length
  try {
    await ElMessageBox.confirm(
      missedCount > 0
        ? `将把 ${missedCount} 个缺失文件写回任务的待校验列表，下一轮优先补偿，是否继续？`
        : '将把任务当前待校验列表保留并触发下一轮补偿，是否继续？',
      '重试失败文件',
      { type: 'warning', confirmButtonText: '写回待校验', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  const res = await automationRunApi.retryFailed(row.id)
  ElMessage.success(`已写回待校验，当前待校验 ${res.data.pending_file_count} 个文件`)
  await load()
}

onMounted(async () => {
  await loadTasks()
  await load()
})

defineExpose({ reload: load })
</script>

<template>
  <div class="page page--fill list-page automation-history">
    <p class="page-hint">
      按轮次记录自动追更的执行结果：可查看阶段、新增/待校验/已校验文件数、缺失文件与错误信息，支持回放该轮日志、打开日志文件夹以及把缺失文件写回待校验。
    </p>

    <div class="toolbar">
      <div class="toolbar__left">
        <el-select v-model="taskFilter" class="toolbar__task" clearable filterable placeholder="全部任务" @change="handleFilterChange">
          <el-option v-for="task in tasks" :key="task.id" :label="task.name" :value="task.id" />
        </el-select>
        <el-select v-model="statusFilter" class="toolbar__status" @change="handleFilterChange">
          <el-option v-for="option in STATUS_OPTIONS" :key="option.value" :label="option.label" :value="option.value" />
        </el-select>
        <el-date-picker
          v-model="dateRange"
          class="toolbar__date"
          type="daterange"
          value-format="YYYY-MM-DD"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          unlink-panels
          @change="handleFilterChange"
        />
      </div>
      <div class="toolbar__right">
        <el-button :icon="FolderOpened" @click="openLogDir">日志文件夹</el-button>
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
      </div>
    </div>

    <el-card shadow="never" class="list-card">
      <div class="list-card__table">
        <el-table v-loading="loading" :data="list" row-key="id" class="automation-history__table">
          <el-table-column label="任务 / 轮次" min-width="220">
            <template #default="{ row }">
              <div class="cell-primary">{{ row.task_name }}</div>
              <div class="cell-secondary">第 {{ row.round_no }} 轮 · 编号 #{{ row.id }}</div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" size="small" effect="light">
                {{ statusText(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="阶段" width="150">
            <template #default="{ row }">{{ phaseText(row.phase) }}</template>
          </el-table-column>
          <el-table-column label="新增 / 待校验" width="120" align="right">
            <template #default="{ row }">
              <span class="num">{{ row.new_file_count }}</span>
              <span class="muted"> / </span>
              <span class="num">{{ row.pending_file_count }}</span>
            </template>
          </el-table-column>
          <el-table-column label="已校验 / 跳过" width="120" align="right">
            <template #default="{ row }">
              <span class="num">{{ row.checked_file_count }}</span>
              <span class="muted"> / </span>
              <span class="num">{{ row.skipped_file_count }}</span>
            </template>
          </el-table-column>
          <el-table-column label="缺失文件" width="96" align="right">
            <template #default="{ row }">
              <span class="num">{{ row.missed_files.length || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="A / B 执行" width="200">
            <template #default="{ row }">
              <div class="cell-secondary">上传：{{ briefText(row.upload) }}</div>
              <div class="cell-secondary">STRM：{{ briefText(row.openlist) }}</div>
            </template>
          </el-table-column>
          <el-table-column label="开始时间" width="170">
            <template #default="{ row }">{{ row.started_time ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="结束时间" width="170">
            <template #default="{ row }">{{ row.finished_time ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="操作" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" :icon="View" @click="openDetail(row)">详情</el-button>
              <el-button
                v-if="row.status === 'fail' || row.status === 'partial' || row.missed_files.length"
                link
                type="primary"
                :icon="RefreshRight"
                @click="handleRetryFailed(row)"
              >
                重试失败
              </el-button>
            </template>
          </el-table-column>

          <template #empty>
            <el-empty :description="emptyDescription" :image-size="80" />
          </template>
        </el-table>
      </div>

      <div class="list-card__pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="PAGE_SIZES"
          layout="total, sizes, prev, pager, next"
          background
          @current-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>

    <!-- 运行详情 -->
    <el-drawer v-model="detailVisible" :title="`运行详情 #${detail?.id ?? ''}`" size="640px" destroy-on-close>
      <div v-loading="detailLoading" class="automation-history__detail">
        <template v-if="detail">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="任务">{{ detail.task_name }}</el-descriptions-item>
            <el-descriptions-item label="轮次">第 {{ detail.round_no }} 轮</el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="statusTagType(detail.status)" size="small" effect="light">
                {{ statusText(detail.status) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="阶段">{{ phaseText(detail.phase) }}</el-descriptions-item>
            <el-descriptions-item label="新增文件">{{ detail.new_file_count }}</el-descriptions-item>
            <el-descriptions-item label="待校验文件">{{ detail.pending_file_count }}</el-descriptions-item>
            <el-descriptions-item label="已校验文件">{{ detail.checked_file_count }}</el-descriptions-item>
            <el-descriptions-item label="跳过文件">{{ detail.skipped_file_count }}</el-descriptions-item>
            <el-descriptions-item label="等待可见（秒）">{{ detail.wait_seconds }}</el-descriptions-item>
            <el-descriptions-item label="空闲等待（秒）">{{ detail.idle_wait_seconds }}</el-descriptions-item>
            <el-descriptions-item label="错误码">{{ detail.error_code ?? '—' }}</el-descriptions-item>
            <el-descriptions-item label="开始时间">{{ detail.started_time ?? '—' }}</el-descriptions-item>
            <el-descriptions-item label="结束时间">{{ detail.finished_time ?? '—' }}</el-descriptions-item>
            <el-descriptions-item label="日志文件" :span="2">
              <span class="automation-history__path">{{ detail.log_path ?? '—' }}</span>
            </el-descriptions-item>
            <el-descriptions-item v-if="detail.error_message" label="错误信息" :span="2">
              {{ detail.error_message }}
            </el-descriptions-item>
          </el-descriptions>

          <div v-if="detail.missed_files.length" class="automation-history__section">
            <div class="automation-history__section-title">缺失文件（{{ detail.missed_files.length }}）</div>
            <div class="automation-history__tags">
              <el-tag v-for="name in detail.missed_files" :key="name" size="small" type="warning" effect="plain">
                {{ name }}
              </el-tag>
            </div>
          </div>

          <div class="automation-history__section">
            <div class="automation-history__section-title">关联执行</div>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="上传执行">
                <template v-if="detail.upload">
                  {{ briefText(detail.upload) }}
                  <span v-if="detail.upload.error_code" class="muted"> · {{ detail.upload.error_code }}</span>
                  <span class="muted"> · {{ detail.upload.started_time ?? '—' }} → {{ detail.upload.finished_time ?? '—' }}</span>
                </template>
                <span v-else class="muted">—</span>
              </el-descriptions-item>
              <el-descriptions-item label="STRM 执行">
                <template v-if="detail.openlist">
                  {{ briefText(detail.openlist) }}
                  <span v-if="detail.openlist.error_code" class="muted"> · {{ detail.openlist.error_code }}</span>
                  <span class="muted"> · {{ detail.openlist.started_time ?? '—' }} → {{ detail.openlist.finished_time ?? '—' }}</span>
                </template>
                <span v-else class="muted">—</span>
              </el-descriptions-item>
            </el-descriptions>
          </div>

          <div class="automation-history__actions">
            <el-button :icon="View" @click="openLogs(detail)">查看日志</el-button>
            <el-button :icon="View" @click="openRealtime(detail)">打开运行详情</el-button>
            <el-button
              v-if="detail.status === 'fail' || detail.status === 'partial' || detail.missed_files.length"
              type="primary"
              :icon="RefreshRight"
              @click="handleRetryFailed(detail)"
            >
              重试失败文件
            </el-button>
          </div>
        </template>
      </div>
    </el-drawer>

    <!-- 该轮日志文件回放 -->
    <el-drawer v-model="logVisible" :title="`运行日志 #${logRun?.id ?? ''}`" size="720px" destroy-on-close>
      <div v-loading="logLoading" class="automation-history__log">
        <pre v-if="logLines.length" class="automation-history__log-pre">{{
          logLines.map(line => `[${line.level.toUpperCase()}] ${line.message}`).join('\n')
        }}</pre>
        <el-empty v-else description="该轮暂无日志文件" />
      </div>
    </el-drawer>
  </div>
</template>

<style scoped lang="scss">
.automation-history {
  gap: var(--up-strm-space-4, 16px);

  &__table {
    width: 100%;
  }

  &__detail {
    display: flex;
    flex-direction: column;
    gap: var(--up-strm-space-4, 16px);
  }

  &__section {
    display: flex;
    flex-direction: column;
    gap: var(--up-strm-space-2, 8px);
  }

  &__section-title {
    font-size: var(--up-strm-font-size-sm, 13px);
    font-weight: 600;
    color: var(--el-text-color-primary);
  }

  &__tags {
    display: flex;
    flex-wrap: wrap;
    gap: var(--up-strm-space-2, 8px);
  }

  &__path {
    word-break: break-all;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: var(--up-strm-font-size-xs, 12px);
  }

  &__actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--up-strm-space-2, 8px);
  }

  &__log {
    height: 100%;
    overflow: auto;
    background: var(--el-fill-color-light);
    border-radius: var(--up-strm-radius-sm, 6px);
    padding: var(--up-strm-space-3, 12px);
  }

  &__log-pre {
    margin: 0;
    white-space: pre-wrap;
    word-break: break-all;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: var(--up-strm-font-size-xs, 12px);
    line-height: 1.6;
    color: var(--el-text-color-regular);
  }
}

.toolbar {
  flex: none;
}

.page-hint {
  flex: none;
  margin: 0;
  font-size: var(--up-strm-font-size-sm, 13px);
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

.toolbar__task {
  width: 220px;
}

.toolbar__status {
  width: 140px;
}

.toolbar__date {
  width: 280px;
}

.cell-primary {
  font-size: var(--up-strm-font-size-base, 14px);
  color: var(--el-text-color-primary);
  line-height: 1.4;
}

.cell-secondary {
  font-size: var(--up-strm-font-size-xs, 12px);
  color: var(--el-text-color-secondary);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.num {
  font-variant-numeric: tabular-nums;
}

.muted {
  color: var(--el-text-color-secondary);
}
</style>
