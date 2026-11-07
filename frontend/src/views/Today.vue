<script setup lang="ts">
/**
 * 今天：一屏看清「生成 → 上传 → 追更」三件事。
 * 数据全部来自现有只读接口（5 个并行请求），任一块失败只降级该块，不编造内容。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight } from '@element-plus/icons-vue'

import EmptyState from '@/components/EmptyState.vue'
import FlowCard from '@/components/FlowCard.vue'
import StatusPill from '@/components/StatusPill.vue'

import { openlistApi } from '@/api/openlist'
import { uploaderApi } from '@/api/uploader'
import { automationApi, automationRunApi } from '@/api/automation'
import type { OpenListExecution, OpenListTask } from '@/types/openlist'
import type { UploadExecution } from '@/types/uploader'
import type { AutomationActiveTask, AutomationTask } from '@/types/automation'
import { formatDateTime } from '@/utils/date'
import { scheduleProgress, uploadProgress } from '@/utils/execution'
import { useRunningStore } from '@/stores/running'

const router = useRouter()
const running = useRunningStore()

const loading = ref(true)
const scheduleTasks = ref<OpenListTask[]>([])
const scheduleExecs = ref<OpenListExecution[]>([])
const uploadExecs = ref<UploadExecution[]>([])
const automationTasks = ref<AutomationTask[]>([])
const automationActive = ref<AutomationActiveTask[]>([])

const todayText = computed(() => formatDateTime(new Date().toISOString()).slice(0, 10))

const lastSchedule = computed(() => scheduleExecs.value[0] ?? null)
const lastUpload = computed(() => uploadExecs.value[0] ?? null)
const pendingTotal = computed(() =>
  automationTasks.value.reduce((sum, task) => sum + (task.pending_file_count ?? 0), 0)
)

const scheduleRunning = computed(() => running.scheduleCount)
const uploadRunning = computed(() => running.uploadCount)
const automationRunning = computed(() => automationActive.value.length)

const overview = computed(() => {
  const parts: string[] = []
  if (scheduleRunning.value + uploadRunning.value + automationRunning.value > 0) {
    parts.push(`${scheduleRunning.value + uploadRunning.value + automationRunning.value} 个任务正在执行`)
  } else {
    parts.push('当前没有正在执行的链路')
  }
  if (pendingTotal.value > 0) parts.push(`${pendingTotal.value} 个文件等待云端校验`)
  return parts.join('，') + '。'
})

const scheduleCard = computed(() => ({
  headline: scheduleRunning.value > 0 ? `${scheduleRunning.value} 个任务正在生成` : '生成链路空闲',
  summary: lastSchedule.value
    ? `上次 ${formatDateTime(lastSchedule.value.started_time ?? lastSchedule.value.created_time)} · ${lastSchedule.value.video_success_count}/${lastSchedule.value.video_total_count} 个视频`
    : '还没有运行记录，可以先建一个任务试试。',
  tone: (scheduleRunning.value > 0
    ? 'running'
    : lastSchedule.value?.status === 'fail'
      ? 'fail'
      : lastSchedule.value
        ? 'success'
        : 'neutral') as 'running' | 'success' | 'fail' | 'warning' | 'neutral',
  progress: lastSchedule.value ? scheduleProgress(lastSchedule.value) : null
}))

const uploadCard = computed(() => ({
  headline: uploadRunning.value > 0 ? `${uploadRunning.value} 个任务正在上传` : '上传链路空闲',
  summary: lastUpload.value
    ? `上次 ${formatDateTime(lastUpload.value.started_time ?? lastUpload.value.created_time)} · 成功 ${lastUpload.value.file_success} / 共 ${lastUpload.value.file_total} 个文件`
    : '还没有上传记录，先把要追的剧集放进来。',
  tone: (uploadRunning.value > 0
    ? 'running'
    : lastUpload.value?.status === 'fail'
      ? 'fail'
      : lastUpload.value
        ? 'success'
        : 'neutral') as 'running' | 'success' | 'fail' | 'warning' | 'neutral',
  progress: lastUpload.value ? uploadProgress(lastUpload.value) : null
}))

const automationCard = computed(() => ({
  headline:
    pendingTotal.value > 0
      ? `${pendingTotal.value} 个文件等待追更`
      : automationTasks.value.length > 0
        ? `已配置 ${automationTasks.value.length} 个追更任务`
        : '还没有自动追更任务',
  summary:
    pendingTotal.value > 0
      ? '下一轮会自动跳过上传，直接校验云端可见性。'
      : '把「生成」和「上传」串起来后，追更会自己按轮次跑。',
  tone: (pendingTotal.value > 0
    ? 'warning'
    : automationRunning.value > 0
      ? 'running'
      : 'neutral') as 'running' | 'success' | 'fail' | 'warning' | 'neutral',
  progress: null
}))

interface AttentionItem {
  key: string
  title: string
  reason: string
  path: string
}

const attention = computed<AttentionItem[]>(() => {
  const items: AttentionItem[] = []
  for (const task of scheduleTasks.value) {
    if (task.last_execution?.status === 'fail') {
      items.push({
        key: `schedule-${task.id}`,
        title: task.name,
        reason: task.last_execution.error_message || '上次生成失败，去运行记录看原因',
        path: '/schedule/history'
      })
    }
  }
  if (lastUpload.value?.status === 'fail') {
    items.push({
      key: `upload-${lastUpload.value.id}`,
      title: lastUpload.value.task_name,
      reason: lastUpload.value.error_message || '上次上传失败，去运行记录看原因',
      path: '/upload/history'
    })
  }
  for (const task of automationTasks.value) {
    if (task.pending_file_count > 0) {
      items.push({
        key: `automation-${task.id}`,
        title: task.name,
        reason: `${task.pending_file_count} 个文件等待云端校验`,
        path: '/automation/tasks'
      })
    } else if (task.consecutive_failures >= 3) {
      items.push({
        key: `automation-fail-${task.id}`,
        title: task.name,
        reason: `连续失败 ${task.consecutive_failures} 次，已暂停自动执行`,
        path: '/automation/history'
      })
    }
  }
  return items.slice(0, 3)
})

interface ActivityItem {
  key: string
  moduleLabel: string
  name: string
  status: 'running' | 'success' | 'fail' | 'cancelled'
  time: string | null
  path: string
}

const activity = computed<ActivityItem[]>(() => {
  const merged: ActivityItem[] = [
    ...scheduleExecs.value.map(exec => ({
      key: `schedule-${exec.id}`,
      moduleLabel: 'STRM 生成',
      name: exec.task_name,
      status: exec.status,
      time: exec.started_time ?? exec.created_time,
      path: '/schedule/realtime'
    })),
    ...uploadExecs.value.map(exec => ({
      key: `upload-${exec.id}`,
      moduleLabel: '云盘上传',
      name: exec.task_name,
      status: exec.status,
      time: exec.started_time ?? exec.created_time,
      path: '/upload/realtime'
    }))
  ]
  return merged
    .filter(item => item.time)
    .sort((a, b) => (b.time ?? '').localeCompare(a.time ?? ''))
    .slice(0, 5)
})

const isEmpty = computed(
  () =>
    !loading.value &&
    scheduleTasks.value.length === 0 &&
    scheduleExecs.value.length === 0 &&
    uploadExecs.value.length === 0 &&
    automationTasks.value.length === 0
)

async function load(): Promise<void> {
  loading.value = true
  const results = await Promise.allSettled([
    openlistApi.listTasks(),
    openlistApi.listExecutions({ page: 1, pageSize: 20 }, { silent: true }),
    uploaderApi.listExecutions({ page: 1, pageSize: 20 }, { silent: true }),
    automationApi.listTasks({ page: 1, page_size: 20 }),
    automationRunApi.active()
  ])
  const [tasksResult, scheduleResult, uploadResult, automationResult, activeResult] = results
  if (tasksResult.status === 'fulfilled') scheduleTasks.value = tasksResult.value.data.list
  if (scheduleResult.status === 'fulfilled') scheduleExecs.value = scheduleResult.value.data.list
  if (uploadResult.status === 'fulfilled') uploadExecs.value = uploadResult.value.data.list
  if (automationResult.status === 'fulfilled') automationTasks.value = automationResult.value.data
  if (activeResult.status === 'fulfilled') automationActive.value = activeResult.value.data
  loading.value = false
}

function go(path: string): void {
  router.push(path)
}

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="today">
    <div class="today__body">
      <section class="today__overview">
        <p class="today__date">{{ todayText }}</p>
        <p class="today__greeting">{{ overview }}</p>
        <div class="today__cards">
          <FlowCard
            module-label="STRM 生成"
            :headline="scheduleCard.headline"
            :summary="scheduleCard.summary"
            action-text="去看生成任务"
            :progress="scheduleCard.progress"
            :tone="scheduleCard.tone"
            @action="go('/schedule/tasks')"
          />
          <FlowCard
            module-label="云盘上传"
            :headline="uploadCard.headline"
            :summary="uploadCard.summary"
            action-text="去看上传任务"
            :progress="uploadCard.progress"
            :tone="uploadCard.tone"
            @action="go('/upload/tasks')"
          />
          <FlowCard
            module-label="自动追更"
            :headline="automationCard.headline"
            :summary="automationCard.summary"
            action-text="去看追更配置"
            :progress="automationCard.progress"
            :tone="automationCard.tone"
            @action="go('/automation/tasks')"
          />
        </div>
      </section>

      <EmptyState
        v-if="isEmpty"
        title="先从连接开始"
        description="三步就能跑起来：连接 OpenList 与云盘 → 新建一个任务 → 点击开始执行。这里会变成你的每日总览。"
        action-text="去连接与格式"
        @action="go('/config')"
      />

      <div v-else class="today__grid">
        <section class="today__block">
          <header class="today__block-head">
            <h2 class="today__block-title">需要你处理</h2>
            <span class="today__block-sub">最多 3 条</span>
          </header>
          <EmptyState
            v-if="attention.length === 0"
            compact
            title="没有需要处理的事"
            description="最近一次执行都正常，去泡杯茶吧。"
          />
          <ul v-else class="today__list">
            <li v-for="item in attention" :key="item.key" class="today__attention">
              <div class="today__attention-main">
                <span class="today__attention-title">{{ item.title }}</span>
                <span class="today__attention-reason">{{ item.reason }}</span>
              </div>
              <el-button link type="primary" @click="go(item.path)">
                去处理
                <el-icon :size="14"><ArrowRight /></el-icon>
              </el-button>
            </li>
          </ul>
        </section>

        <section class="today__block">
          <header class="today__block-head">
            <h2 class="today__block-title">最近活动</h2>
            <span class="today__block-sub">最近 5 条</span>
          </header>
          <EmptyState
            v-if="activity.length === 0"
            compact
            title="还没有运行记录"
            description="点任意模块的「开始执行」后，这里会出现最近的活动。"
          />
          <ul v-else class="today__list">
            <li v-for="item in activity" :key="item.key" class="today__activity">
              <StatusPill :status="item.status" :breathe="false" />
              <div class="today__activity-main">
                <span class="today__activity-name">{{ item.name }}</span>
                <span class="today__activity-meta">{{ item.moduleLabel }} · {{ formatDateTime(item.time) }}</span>
              </div>
              <el-button link type="primary" @click="go(item.path)">看详情</el-button>
            </li>
          </ul>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.today {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}

.today__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--up-strm-space-6);
  padding: var(--up-strm-space-6) var(--up-strm-page-pad) var(--up-strm-space-8);
  max-width: var(--up-strm-content-max);
  width: 100%;
}

.today__overview {
  display: flex;
  flex-direction: column;
  gap: var(--up-strm-space-5);
}

.today__date {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: var(--up-strm-font-size-xs);
}

.today__greeting {
  margin: 0;
  color: var(--el-text-color-regular);
  font-size: var(--up-strm-fs-15);
  line-height: 24px;
}

.today__cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--up-strm-space-4);
}

.today__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.1fr);
  gap: var(--up-strm-space-4);
  align-items: start;
}

.today__block {
  display: flex;
  flex-direction: column;
  gap: var(--up-strm-space-2);
  padding: var(--up-strm-space-5);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--up-strm-radius-lg);
  background: var(--el-bg-color);
}

.today__block-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--up-strm-space-2);
}

.today__block-title {
  margin: 0;
  color: var(--el-text-color-primary);
  font-size: var(--up-strm-fs-15);
  font-weight: 600;
}

.today__block-sub {
  color: var(--el-text-color-secondary);
  font-size: var(--up-strm-font-size-xs);
}

.today__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.today__attention,
.today__activity {
  display: flex;
  align-items: center;
  gap: var(--up-strm-space-3);
  padding: var(--up-strm-space-2) var(--up-strm-space-1);
  border-radius: var(--up-strm-radius-sm);
}

.today__attention:hover,
.today__activity:hover {
  background: var(--el-fill-color-light);
}

.today__attention-main,
.today__activity-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.today__attention-title,
.today__activity-name {
  overflow: hidden;
  color: var(--el-text-color-primary);
  font-size: var(--up-strm-font-size-sm);
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.today__attention-reason,
.today__activity-meta {
  overflow: hidden;
  color: var(--el-text-color-secondary);
  font-size: var(--up-strm-font-size-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 1279px) {
  .today__body {
    padding: var(--up-strm-space-5) var(--up-strm-space-5) var(--up-strm-space-6);
  }

  .today__cards {
    grid-template-columns: 1fr;
  }

  .today__grid {
    grid-template-columns: 1fr;
  }
}
</style>
