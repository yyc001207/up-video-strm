<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowLeft, FolderOpened, Refresh, Search, View } from '@element-plus/icons-vue'

import { desktopApi } from '@/api/desktop'
import { openlistApi } from '@/api/openlist'
import StatusDot from '@/components/StatusDot.vue'
import { useOpenlistStore } from '@/stores/openlist'
import type { HistorySummaryItem, OpenListExecution, OpenListLog } from '@/types/openlist'
import { beijingMillis, formatDateTime } from '@/utils/date'

const store = useOpenlistStore()

const list = ref<HistorySummaryItem[]>([])
const loading = ref(false)

/** 视图切换：列表 ↔ 详情（详情作为页面展示，不再使用抽屉）。 */
const viewMode = ref<'list' | 'detail'>('list')
const detailTaskId = ref<number | null>(null)
const detailTaskName = ref('')
const executions = ref<OpenListExecution[]>([])
const detailLoading = ref(false)
const detailPage = ref(1)
const detailTotal = ref(0)
const PAGE_SIZE = 20

// —— 列表筛选与客户端分页（详情页仍走后端分页）——
type StatusFilter = '' | 'success' | 'fail' | 'cancelled' | 'unexecuted'

const STATUS_OPTIONS: { label: string; value: StatusFilter }[] = [
  { label: '全部状态', value: '' },
  { label: '成功', value: 'success' },
  { label: '失败', value: 'fail' },
  { label: '已取消', value: 'cancelled' },
  { label: '未执行', value: 'unexecuted' }
]

const keyword = ref('')
const dateRange = ref<[string, string] | null>(null)
const statusFilter = ref<StatusFilter>('')
const PAGE_SIZES = [10, 20, 50]
const page = ref(1)
const pageSize = ref(PAGE_SIZE)

const logVisible = ref(false)
const logLoading = ref(false)
const logs = ref<OpenListLog[]>([])
const logExecution = ref<OpenListExecution | null>(null)

function durationText(sec: number | null): string {
  if (sec == null) return '—'
  if (sec < 60) return `${sec} 秒`
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m} 分 ${s} 秒`
}

/** 计数文本：总数为 0 时显示「—」，避免 0/0 噪声。 */
function countText(success: number, total: number): string {
  return total > 0 ? `${success}/${total}` : '—'
}

/** 谁启动的：自动追更触发时展示任务名，其余为手动。 */
function triggerText(row: OpenListExecution): string {
  if (row.trigger_source !== 'automation') return '手动'
  return row.trigger_name ? `自动化 · ${row.trigger_name}` : '自动化'
}

/** 该任务最近一次执行的时间戳：优先完成时间，其次开始/创建时间。 */
function executionMillis(item: HistorySummaryItem): number | null {
  const exec = item.execution
  if (!exec) return null
  return beijingMillis(exec.finished_time ?? exec.started_time ?? exec.created_time)
}

/** 时间范围边界（北京时间）：开始日 00:00:00 ~ 结束日 23:59:59。 */
const rangeBounds = computed(() => {
  const range = dateRange.value
  if (!range) return null
  return {
    start: beijingMillis(`${range[0]} 00:00:00`),
    end: beijingMillis(`${range[1]} 23:59:59`)
  }
})

const filteredList = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  const bounds = rangeBounds.value
  return list.value.filter(item => {
    if (kw && !item.task_name.toLowerCase().includes(kw)) return false
    if (statusFilter.value === 'unexecuted') {
      if (item.execution) return false
    } else if (statusFilter.value && item.execution?.status !== statusFilter.value) {
      return false
    }
    if (bounds) {
      const millis = executionMillis(item)
      if (millis == null) return false
      if (bounds.start != null && millis < bounds.start) return false
      if (bounds.end != null && millis > bounds.end) return false
    }
    return true
  })
})

const pagedList = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filteredList.value.slice(start, start + pageSize.value)
})

const hasFilter = computed(() => Boolean(keyword.value.trim() || dateRange.value || statusFilter.value))

const emptyDescription = computed(() =>
  hasFilter.value ? '没有匹配的运行记录' : '暂无运行记录（执行任务后才会生成记录）'
)

// 筛选条件变化后回到第一页，避免停留在越界页
watch([keyword, dateRange, statusFilter], () => {
  page.value = 1
})

function handlePageSizeChange() {
  page.value = 1
}

async function load() {
  loading.value = true
  try {
    // 单服务器模式：后端只返回唯一服务器下的历史，无需传服务器参数
    const res = await openlistApi.historySummary()
    list.value = res.data.list
    // 数据变化后回到第一页，避免停留在越界页
    page.value = 1
  } finally {
    loading.value = false
  }
}

/** 进入详情页面。 */
async function openDetail(item: HistorySummaryItem) {
  detailTaskId.value = item.task_id
  detailTaskName.value = item.task_name
  detailPage.value = 1
  viewMode.value = 'detail'
  await loadDetail()
}

/** 返回列表页面。 */
function backToList() {
  viewMode.value = 'list'
}

async function loadDetail() {
  if (detailTaskId.value == null) return
  detailLoading.value = true
  try {
    const res = await openlistApi.historyByTask(detailTaskId.value, detailPage.value, PAGE_SIZE)
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

async function openLogs(row: OpenListExecution) {
  logExecution.value = row
  logVisible.value = true
  logLoading.value = true
  logs.value = []
  try {
    const res = await openlistApi.listExecutionLogs(row.id, 1, 500)
    logs.value = res.data.list
  } finally {
    logLoading.value = false
  }
}

function openLogDir() {
  desktopApi.openLogDir('openlist').catch(() => {
    /* 拦截器提示 */
  })
}

onMounted(async () => {
  await Promise.all([load(), store.fetchConfig()])
})

defineExpose({ reload: load })
</script>

<template>
  <div class="page task-history" :class="viewMode === 'list' ? 'page--fill list-page' : ''">
    <!-- 列表页面 -->
    <template v-if="viewMode === 'list'">
      <p class="page-hint">
        按任务汇总最近一次执行与累计执行次数，点击任务名进入执行记录，可查看执行日志、打开日志文件夹；需要重跑请到「开始执行」重新选择任务执行。列表支持按任务名称、执行时间范围与执行状态筛选。
      </p>

      <div class="toolbar">
        <div class="toolbar__left">
          <el-input
            v-model="keyword"
            class="toolbar__keyword"
            placeholder="搜索任务名称"
            clearable
            :prefix-icon="Search"
          />
          <el-date-picker
            v-model="dateRange"
            class="toolbar__date"
            type="daterange"
            value-format="YYYY-MM-DD"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            range-separator="至"
            unlink-panels
          />
          <el-select v-model="statusFilter" class="toolbar__status">
            <el-option v-for="opt in STATUS_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </div>

        <div class="toolbar__right">
          <el-button :icon="FolderOpened" @click="openLogDir()">日志文件夹</el-button>
          <el-button :icon="Refresh" @click="load">刷新</el-button>
        </div>
      </div>

      <el-card shadow="never" class="list-card">
        <div class="list-card__table">
          <el-table v-loading="loading" :data="pagedList" row-key="task_id" class="task-history__table">
            <el-table-column label="任务" min-width="260">
              <template #default="{ row }">
                <div class="cell-primary">
                  <el-link type="primary" :underline="false" @click="openDetail(row)">{{ row.task_name }}</el-link>
                </div>
                <div class="cell-secondary" :title="row.process_path">{{ row.process_path || '—' }}</div>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <StatusDot v-if="row.execution" :status="row.execution.status" />
                <span v-else class="muted">—</span>
              </template>
            </el-table-column>
            <el-table-column label="视频" width="96" align="right">
              <template #default="{ row }">
                <span class="num">
                  {{ row.execution ? countText(row.execution.video_success_count, row.execution.video_total_count) : '—' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="字幕" width="96" align="right">
              <template #default="{ row }">
                <span class="num">
                  {{ row.execution ? countText(row.execution.subtitle_success_count, row.execution.subtitle_total_count) : '—' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="耗时" width="110">
              <template #default="{ row }">
                {{ row.execution ? durationText(row.execution.duration_seconds) : '—' }}
              </template>
            </el-table-column>
            <el-table-column label="执行时间" width="170">
              <template #default="{ row }">
                {{ row.execution ? formatDateTime(row.execution.started_time) : '—' }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" :disabled="!row.execution" @click="openDetail(row)">详情</el-button>
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
            @size-change="handlePageSizeChange"
          />
        </div>
      </el-card>
    </template>

    <!-- 详情页面 -->
    <template v-else>
      <div class="detail-header">
        <el-button :icon="ArrowLeft" @click="backToList">返回</el-button>
        <div class="detail-header__title">
          <span class="detail-header__name">{{ detailTaskName }}</span>
          <span class="detail-header__meta">执行历史</span>
        </div>
      </div>

      <el-card v-loading="detailLoading" shadow="never" class="task-history__card">
        <el-table :data="executions" row-key="id" class="task-history__table">
          <el-table-column label="编号" prop="id" width="80" />
          <el-table-column label="处理路径" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">{{ row.process_path || '—' }}</template>
          </el-table-column>
          <el-table-column label="输出目录" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">{{ row.output_dir || '—' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <StatusDot :status="row.status" />
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
          <el-table-column label="视频" width="96" align="right">
            <template #default="{ row }">
              <span class="num">{{ countText(row.video_success_count, row.video_total_count) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="字幕" width="96" align="right">
            <template #default="{ row }">
              <span class="num">{{ countText(row.subtitle_success_count, row.subtitle_total_count) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="耗时" width="110">
            <template #default="{ row }">{{ durationText(row.duration_seconds) }}</template>
          </el-table-column>
          <el-table-column label="执行时间" width="170">
            <template #default="{ row }">{{ formatDateTime(row.started_time) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" :icon="View" @click="openLogs(row)">日志</el-button>
              <el-button link type="primary" :icon="FolderOpened" @click="openLogDir()">日志文件夹</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="pagination">
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

    <!-- 执行日志查看（保留抽屉，长文本展示更合适） -->
    <el-drawer v-model="logVisible" :title="`执行日志 #${logExecution?.id ?? ''}`" size="640px" destroy-on-close>
      <div v-loading="logLoading" class="task-history__log">
        <pre v-if="logs.length" class="task-history__log-pre">{{ logs.map(l => `[${formatDateTime(l.created_time)}] [${l.log_level.toUpperCase()}] ${l.content}`).join('\n') }}</pre>
        <el-empty v-else description="暂无日志" />
      </div>
    </el-drawer>
  </div>
</template>

<style scoped lang="scss">
.task-history {
  display: flex;
  flex-direction: column;
  gap: var(--up-strm-space-4, 16px);

  &__card {
    flex-shrink: 0;
  }

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

// 工具栏布局见 styles/global.scss 的 .toolbar 原语

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
}

.toolbar__status {
  width: 140px;
}

@media (max-width: 720px) {
  .toolbar__keyword,
  .toolbar__date,
  .toolbar__status {
    width: 100%;
  }
}

.detail-header {
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
