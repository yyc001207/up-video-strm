<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, FolderOpened, Refresh, RefreshRight, Search, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { desktopApi } from '@/api/desktop'
import { uploaderApi } from '@/api/uploader'
import StatusDot from '@/components/StatusDot.vue'
import type { UploadConflictPolicy, UploadExecution, UploadFileRecord, UploadHistorySummaryItem } from '@/types/uploader'
import { beijingMillis, formatDateTime } from '@/utils/date'

const router = useRouter()

const CONFLICT_LABELS: Record<UploadConflictPolicy, string> = {
  skip: '跳过',
  overwrite: '覆盖',
  suffix: '追加后缀',
}

const RECORD_STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  uploading: '上传中',
  success: '成功',
  skipped: '跳过',
  failed: '失败',
}

const list = ref<UploadHistorySummaryItem[]>([])
const loading = ref(false)

/** 列表筛选状态：未执行对应 last_execution 为空。 */
type HistoryStatusFilter = 'all' | 'success' | 'fail' | 'cancelled' | 'none'

const STATUS_FILTER_OPTIONS: { label: string; value: HistoryStatusFilter }[] = [
  { label: '全部状态', value: 'all' },
  { label: '成功', value: 'success' },
  { label: '失败', value: 'fail' },
  { label: '已取消', value: 'cancelled' },
  { label: '未执行', value: 'none' },
]

// 列表筛选与客户端分页（详情页仍走后端分页）
const keyword = ref('')
const statusFilter = ref<HistoryStatusFilter>('all')
const dateRange = ref<[string, string] | null>(null)
const page = ref(1)
const pageSize = ref(20)
const PAGE_SIZES = [10, 20, 50]

/** 视图切换：列表 ↔ 详情（同任务调度历史，详情作为页面而非抽屉）。 */
const viewMode = ref<'list' | 'detail'>('list')
const detailTaskId = ref<number | null>(null)
const detailTaskName = ref('')
const executions = ref<UploadExecution[]>([])
const detailLoading = ref(false)
const detailPage = ref(1)
const detailTotal = ref(0)
const PAGE_SIZE = 20
const RECORD_PAGE_SIZE = 20

const recordsVisible = ref(false)
const recordsLoading = ref(false)
const records = ref<UploadFileRecord[]>([])
const recordsTotal = ref(0)
const recordsPage = ref(1)
const recordsExecutionId = ref<number | null>(null)

const logVisible = ref(false)
const logLoading = ref(false)
const logs = ref<{ id: number; log_level: string; content: string; created_time: string | null }[]>([])
const logExecution = ref<UploadExecution | null>(null)

function durationText(sec: number | null): string {
  if (sec == null) return '—'
  if (sec < 60) return `${sec} 秒`
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m} 分 ${s} 秒`
}

/** 计数文本：总数为 0 时显示「—」，避免 0/0 噪声。 */
function countText(value: number, total: number): string {
  return total > 0 ? `${value}/${total}` : '—'
}

function seasonText(season: number, startEpisode: number): string {
  return `S${String(season).padStart(2, '0')} · 起 ${startEpisode}`
}

/** 冲突策略显示文本（模板中 row 为 any，统一走这里收窄类型）。 */
function conflictText(policy: string): string {
  return CONFLICT_LABELS[policy as UploadConflictPolicy] ?? policy
}

/** 触发方式：自动化任务触发时展示任务名，其余为手动。 */
function triggerText(row: UploadExecution): string {
  if (row.trigger_source !== 'automation') return '手动'
  return row.trigger_name ? `自动化 · ${row.trigger_name}` : '自动化'
}

/** 取最近一次执行的时间（结束 → 开始 → 创建），按北京时间比较。 */
function executionTimestamp(item: UploadHistorySummaryItem): number | null {
  const exec = item.last_execution
  if (!exec) return null
  return beijingMillis(exec.finished_time ?? exec.started_time ?? exec.created_time)
}

const filteredList = computed(() => {
  const needle = keyword.value.trim().toLowerCase()
  const range = dateRange.value
  let startMs: number | null = null
  let endMs: number | null = null
  if (range !== null) {
    // 起止日期分别按北京时间 00:00:00 / 23:59:59 计算
    startMs = beijingMillis(`${range[0]} 00:00:00`)
    endMs = beijingMillis(`${range[1]} 23:59:59`)
  }
  return list.value.filter(item => {
    if (needle !== '' && !item.task_name.toLowerCase().includes(needle)) return false
    if (statusFilter.value !== 'all') {
      const status = item.last_execution?.status ?? 'none'
      if (status !== statusFilter.value) return false
    }
    if (startMs !== null && endMs !== null) {
      const timestamp = executionTimestamp(item)
      if (timestamp === null || timestamp < startMs || timestamp > endMs) return false
    }
    return true
  })
})

const pagedList = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filteredList.value.slice(start, start + pageSize.value)
})

const hasFilters = computed(() => keyword.value.trim() !== '' || statusFilter.value !== 'all' || dateRange.value !== null)

const emptyDescription = computed(() => (hasFilters.value ? '没有匹配的上传历史' : '暂无上传历史（执行上传任务后才会生成记录）'))

// 筛选条件或每页条数变化时回到第一页
watch([keyword, statusFilter, dateRange, pageSize], () => {
  page.value = 1
})

// 数据量变化（刷新 / 筛选）时把页码收敛到最后一页
watch(filteredList, value => {
  const maxPage = Math.max(1, Math.ceil(value.length / pageSize.value))
  if (page.value > maxPage) {
    page.value = maxPage
  }
})

async function load() {
  loading.value = true
  try {
    const res = await uploaderApi.historySummary()
    list.value = res.data
    page.value = 1
  } finally {
    loading.value = false
  }
}

/** 进入某任务的执行历史页面。 */
async function openDetail(item: UploadHistorySummaryItem) {
  detailTaskId.value = item.task_id
  detailTaskName.value = item.task_name
  detailPage.value = 1
  viewMode.value = 'detail'
  await loadDetail()
}

function backToList() {
  viewMode.value = 'list'
}

async function loadDetail() {
  if (detailTaskId.value == null) return
  detailLoading.value = true
  try {
    const res = await uploaderApi.historyByTask(detailTaskId.value, detailPage.value, PAGE_SIZE)
    executions.value = res.data.list
    // 后端分页响应在 data 之外附带 total 字段，Res 类型未声明，这里按实际响应读取
    detailTotal.value = (res as unknown as { total?: number }).total ?? 0
  } finally {
    detailLoading.value = false
  }
}

function handleDetailPageChange() {
  loadDetail()
}

async function openRecords(row: UploadExecution) {
  recordsExecutionId.value = row.id
  recordsPage.value = 1
  recordsVisible.value = true
  await loadRecords()
}

async function loadRecords() {
  if (recordsExecutionId.value == null) return
  recordsLoading.value = true
  try {
    const res = await uploaderApi.listFileRecords(recordsExecutionId.value, recordsPage.value, RECORD_PAGE_SIZE)
    records.value = res.data.list
    recordsTotal.value = (res as unknown as { total?: number }).total ?? 0
  } finally {
    recordsLoading.value = false
  }
}

function handleRecordsPageChange() {
  loadRecords()
}

async function openLogs(row: UploadExecution) {
  logExecution.value = row
  logVisible.value = true
  logLoading.value = true
  logs.value = []
  try {
    const res = await uploaderApi.listExecutionLogs(row.id, 1, 500)
    logs.value = res.data.list
  } finally {
    logLoading.value = false
  }
}

function openLogDir() {
  desktopApi.openLogDir('upload').catch(() => {
    /* 拦截器提示 */
  })
}

/** 以原执行的固化参数重跑：新建执行记录后跳转实时日志，由 WS 连接后启动。 */
async function handleRetry(row: UploadExecution) {
  try {
    await ElMessageBox.confirm(
      `将按原参数（冲突策略：${CONFLICT_LABELS[row.conflict_policy]}、并发 ${row.concurrency}、重试 ${row.retry_times} 次）重新创建并启动执行，是否继续？`,
      '重新执行',
      { type: 'warning', confirmButtonText: '重新执行', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  const res = await uploaderApi.retryExecution(row.id)
  const created = res.data
  ElMessage.success('已创建新的执行记录，正在跳转实时日志')
  await router.push({
    name: 'UploadRealtime',
    query: {
      execs: JSON.stringify([{ executionId: created.id, taskId: created.task_id, taskName: created.task_name }]),
    },
  })
}

onMounted(load)

defineExpose({ reload: load })
</script>

<template>
  <div class="page page--fill list-page upload-history">
    <!-- 列表页面：按任务汇总 -->
    <template v-if="viewMode === 'list'">
      <p class="page-hint">
        按任务汇总最近一次上传执行与累计执行次数，点击任务名进入执行记录，可查看文件明细、执行日志、打开日志文件夹或重跑；列表支持按任务名称、执行时间范围与执行状态筛选。
      </p>

      <div class="toolbar">
        <div class="toolbar__left">
          <el-input
            v-model="keyword"
            class="toolbar__keyword"
            clearable
            :prefix-icon="Search"
            placeholder="搜索任务名称"
            @keyup.enter="page = 1"
            @clear="page = 1"
          />
          <el-date-picker
            v-model="dateRange"
            class="toolbar__date"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            unlink-panels
          />
          <el-select v-model="statusFilter" class="toolbar__status" placeholder="任务状态">
            <el-option v-for="option in STATUS_FILTER_OPTIONS" :key="option.value" :label="option.label" :value="option.value" />
          </el-select>
        </div>
        <div class="toolbar__right">
          <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
        </div>
      </div>

      <el-card shadow="never" class="list-card">
        <div class="list-card__table">
          <el-table v-loading="loading" :data="pagedList" row-key="task_id" class="upload-history__table">
            <el-table-column label="任务" min-width="260">
              <template #default="{ row }">
                <div class="cell-primary">
                  <el-link type="primary" :underline="false" @click="openDetail(row)">{{ row.task_name }}</el-link>
                </div>
                <div class="cell-secondary" :title="`${row.local_dir || '—'} → 云端 ${row.remote_dir || '—'}`">
                  {{ row.local_dir || '—' }}
                </div>
              </template>
            </el-table-column>
            <el-table-column label="季数 / 起始集" width="130">
              <template #default="{ row }">{{ seasonText(row.season, row.start_episode) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <StatusDot v-if="row.last_execution" :status="row.last_execution.status" />
                <span v-else class="muted">—</span>
              </template>
            </el-table-column>
            <el-table-column label="文件" width="96" align="right">
              <template #default="{ row }">
                <span class="num">
                  {{ row.last_execution ? countText(row.last_execution.file_success, row.last_execution.file_total) : '—' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="耗时" width="110">
              <template #default="{ row }">
                {{ row.last_execution ? durationText(row.last_execution.duration_seconds) : '—' }}
              </template>
            </el-table-column>
            <el-table-column label="执行时间" width="170">
              <template #default="{ row }">
                {{ row.last_execution ? formatDateTime(row.last_execution.started_time) : '—' }}
              </template>
            </el-table-column>
            <el-table-column label="执行次数" width="96" align="right">
              <template #default="{ row }">
                <span class="num">{{ row.total_executions }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openDetail(row)">详情</el-button>
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
            :total="filteredList.length"
            :page-sizes="PAGE_SIZES"
            layout="total, sizes, prev, pager, next"
            background
          />
        </div>
      </el-card>
    </template>

    <!-- 详情页面：某任务的全部执行记录 -->
    <template v-else>
      <div class="detail-header">
        <el-button :icon="ArrowLeft" @click="backToList">返回</el-button>
        <div class="detail-header__title">
          <span class="detail-header__name">{{ detailTaskName }}</span>
          <span class="detail-header__meta">上传执行历史</span>
        </div>
      </div>

      <el-card v-loading="detailLoading" shadow="never" class="list-card">
        <div class="list-card__table">
          <el-table :data="executions" row-key="id" class="upload-history__table">
            <el-table-column label="编号" prop="id" width="80" />
            <el-table-column label="状态">
              <template #default="{ row }">
                <StatusDot :status="row.status" />
              </template>
            </el-table-column>
            <el-table-column label="触发方式" show-overflow-tooltip>
              <template #default="{ row }">
                <el-tag :type="row.trigger_source === 'automation' ? 'warning' : 'info'" size="small" effect="plain">
                  {{ triggerText(row) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="冲突策略">
              <template #default="{ row }">{{ conflictText(row.conflict_policy) }}</template>
            </el-table-column>
            <el-table-column label="文件数" align="right">
              <template #default="{ row }">
                <span class="num">{{ row.file_total }}</span>
              </template>
            </el-table-column>
            <el-table-column label="成功 / 跳过 / 失败" width="200" align="right">
              <template #default="{ row }">
                <span class="num">{{ countText(row.file_success, row.file_total) }}</span>
                <span class="muted"> · </span>
                <span class="num">{{ row.file_skipped }}</span>
                <span class="muted"> · </span>
                <span class="num">{{ row.file_failed }}</span>
              </template>
            </el-table-column>
            <el-table-column label="试运行">
              <template #default="{ row }">{{ row.dry_run ? '是' : '否' }}</template>
            </el-table-column>
            <el-table-column label="耗时">
              <template #default="{ row }">{{ durationText(row.duration_seconds) }}</template>
            </el-table-column>
            <el-table-column label="开始时间">
              <template #default="{ row }">{{ formatDateTime(row.started_time) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="400" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" :icon="View" @click="openRecords(row)">明细</el-button>
                <el-button link type="primary" :icon="View" @click="openLogs(row)">日志</el-button>
                <el-button link type="primary" :icon="FolderOpened" @click="openLogDir()">日志文件夹</el-button>
                <el-button link type="primary" :icon="RefreshRight" @click="handleRetry(row)">重跑</el-button>
              </template>
            </el-table-column>

            <template #empty>
              <el-empty description="该任务暂无执行记录" :image-size="80" />
            </template>
          </el-table>
        </div>

        <div class="list-card__pager">
          <el-pagination
            v-model:current-page="detailPage"
            :total="detailTotal"
            :page-size="PAGE_SIZE"
            layout="total, prev, pager, next"
            @current-change="handleDetailPageChange"
          />
        </div>
      </el-card>
    </template>

    <!-- 文件粒度明细 -->
    <el-drawer v-model="recordsVisible" :title="`文件明细 #${recordsExecutionId ?? ''}`" size="720px" destroy-on-close>
      <div v-loading="recordsLoading" class="upload-history__records">
        <el-table :data="records" row-key="id" class="upload-history__table">
          <el-table-column label="本地文件" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">{{ row.local_path }}</template>
          </el-table-column>
          <el-table-column label="远端名称" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">{{ row.remote_name }}</template>
          </el-table-column>
          <el-table-column label="大小" width="100" align="right">
            <template #default="{ row }">
              <span class="num">{{ (row.size / 1024 / 1024).toFixed(2) }} MB</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">{{ RECORD_STATUS_LABELS[row.status] ?? row.status }}</template>
          </el-table-column>
          <el-table-column label="原因" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">{{ row.reason || '—' }}</template>
          </el-table-column>
          <el-table-column label="云端 fileId" width="120">
            <template #default="{ row }">{{ row.remote_file_id ?? '—' }}</template>
          </el-table-column>

          <template #empty>
            <el-empty description="暂无文件明细" :image-size="80" />
          </template>
        </el-table>

        <div class="pagination">
          <el-pagination
            v-model:current-page="recordsPage"
            :total="recordsTotal"
            :page-size="RECORD_PAGE_SIZE"
            layout="total, prev, pager, next"
            @current-change="handleRecordsPageChange"
          />
        </div>
      </div>
    </el-drawer>

    <!-- 执行日志（文件回放） -->
    <el-drawer v-model="logVisible" :title="`执行日志 #${logExecution?.id ?? ''}`" size="640px" destroy-on-close>
      <div v-loading="logLoading" class="upload-history__log">
        <pre v-if="logs.length" class="upload-history__log-pre">{{
          logs.map(l => `[${formatDateTime(l.created_time)}] [${l.log_level.toUpperCase()}] ${l.content}`).join('\n')
        }}</pre>
        <el-empty v-else description="暂无日志" />
      </div>
    </el-drawer>
  </div>
</template>

<style scoped lang="scss">
.upload-history {
  gap: var(--up-strm-space-4, 16px);

  &__table {
    width: 100%;
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

// 工具栏布局见 styles/global.scss 的 .toolbar 原语，这里只约束筛选项宽度
.toolbar {
  flex: none;
}

// 列表页顶部功能说明（次要色，遵循页面 hint 风格）
.page-hint {
  flex: none;
  margin: 0;
  font-size: var(--up-strm-font-size-sm, 13px);
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

.toolbar__keyword {
  width: 200px;
}

.toolbar__date {
  width: 280px;
  max-width: 100%;
}

.toolbar__status {
  width: 140px;
}

.detail-header {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--up-strm-space-3, 12px);

  &__title {
    display: flex;
    align-items: baseline;
    gap: var(--up-strm-space-2, 8px);
    min-width: 0;
  }

  &__name {
    font-size: var(--up-strm-font-size-lg, 16px);
    font-weight: 600;
    color: var(--el-text-color-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__meta {
    font-size: var(--up-strm-font-size-sm, 13px);
    color: var(--el-text-color-secondary);
    flex-shrink: 0;
  }
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

.pagination {
  display: flex;
  justify-content: flex-end;
  padding-top: var(--up-strm-space-3, 12px);
}
</style>
