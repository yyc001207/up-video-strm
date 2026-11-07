/** 全局运行状态：聚合「STRM 生成」「云盘上传」「自动追更」三个模块的运行中执行。 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { openlistApi } from '@/api/openlist'
import { uploaderApi } from '@/api/uploader'
import { automationRunApi } from '@/api/automation'
import type { OpenListExecution } from '@/types/openlist'
import type { UploadExecution } from '@/types/uploader'
import type { AutomationActiveTask } from '@/types/automation'
import { percentOf, scheduleProgress, uploadProgress } from '@/utils/execution'

/** 顶栏轮询间隔（壳层统一轮询；页面可见时才执行，避免后台无意义请求）。 */
export const RUNNING_POLL_MS = 30000
/** 最近一次失败后视为「连接失败」的窗口。 */
export const OFFLINE_WINDOW_MS = 30000
/** 顶栏运行胶囊最多取多少条运行中执行来算加权进度；超过则只显示数量。 */
export const PROGRESS_SAMPLE_LIMIT = 5

export interface RunningModuleItem {
  module: 'schedule' | 'upload' | 'automation'
  moduleLabel: string
  id: number
  taskId: number
  name: string
  /** 0–100；null 表示该项没有可用分母。 */
  progress: number | null
  /** 跳转到的运行详情路径（带执行 id）。 */
  detailPath: string
  stop: () => Promise<unknown>
}

export const useRunningStore = defineStore('running', () => {
  const scheduleCount = ref(0)
  const uploadCount = ref(0)
  const automationCount = ref(0)
  const scheduleItems = ref<OpenListExecution[]>([])
  const uploadItems = ref<UploadExecution[]>([])
  const automationItems = ref<AutomationActiveTask[]>([])
  /** 最近一次轮询失败时间（毫秒时间戳），成功轮询后清空。 */
  const lastErrorAt = ref<number | null>(null)
  /** 最近一次轮询是否全部失败（后端不可达）。 */
  const offline = ref(false)
  /** 最近一次成功轮询时间（毫秒时间戳）。 */
  const lastUpdatedAt = ref<number | null>(null)

  const total = computed(() => scheduleCount.value + uploadCount.value + automationCount.value)

  /** 运行中条目（用于顶栏抽屉）；各模块合并后最多 5 条。 */
  const items = computed<RunningModuleItem[]>(() => {
    const merged: RunningModuleItem[] = [
      ...scheduleItems.value.map(item => ({
        module: 'schedule' as const,
        moduleLabel: 'STRM 生成',
        id: item.id,
        taskId: item.task_id,
        name: item.task_name,
        progress: scheduleProgress(item),
        detailPath: `/schedule/realtime?execs=${item.id}`,
        stop: () => openlistApi.cancelExecution(item.id)
      })),
      ...uploadItems.value.map(item => ({
        module: 'upload' as const,
        moduleLabel: '云盘上传',
        id: item.id,
        taskId: item.task_id,
        name: item.task_name,
        progress: uploadProgress(item),
        detailPath: `/upload/realtime?execs=${item.id}`,
        stop: () => uploaderApi.cancelExecution(item.id)
      })),
      ...automationItems.value.map(item => ({
        module: 'automation' as const,
        moduleLabel: '自动追更',
        id: item.run_id ?? 0,
        taskId: item.task_id,
        name: item.task_name ?? '',
        progress: null,
        detailPath: `/automation/realtime?task_id=${item.task_id}`,
        stop: () => automationRunApi.stop(item.task_id)
      }))
    ]
    return merged.slice(0, PROGRESS_SAMPLE_LIMIT)
  })

  /**
   * 加权进度：运行数不超过采样上限、且每个条目都有分母时才给百分比，
   * 样本不全就只显示数量（不猜）。
   */
  const progress = computed<number | null>(() => {
    if (total.value === 0 || total.value > PROGRESS_SAMPLE_LIMIT) return null
    if (items.value.length !== total.value) return null
    let done = 0
    let all = 0
    for (const item of items.value) {
      if (item.progress === null) return null
      const denominator = item.module === 'schedule' ? scheduleTotal(item) : undefined
      if (denominator === undefined) return null
      done += (item.progress / 100) * denominator
      all += denominator
    }
    if (all <= 0) return null
    return percentOf(done, all)
  })

  function scheduleTotal(item: RunningModuleItem): number | undefined {
    const source = scheduleItems.value.find(execution => execution.id === item.id)
    return source?.video_total_count
  }

  function isConnectFailed(now = Date.now()): boolean {
    return lastErrorAt.value !== null && now - lastErrorAt.value < OFFLINE_WINDOW_MS
  }

  async function fetchCounts(): Promise<void> {
    const results = await Promise.allSettled([
      openlistApi.listExecutions(
        { status: 'running', page: 1, pageSize: PROGRESS_SAMPLE_LIMIT },
        { silent: true }
      ),
      uploaderApi.listExecutions(
        { status: 'running', page: 1, pageSize: PROGRESS_SAMPLE_LIMIT },
        { silent: true }
      ),
      automationRunApi.active()
    ])
    const [scheduleResult, uploadResult, automationResult] = results
    if (scheduleResult.status === 'fulfilled') {
      scheduleItems.value = scheduleResult.value.data.list
      scheduleCount.value = scheduleResult.value.total ?? scheduleResult.value.data.list.length
    }
    if (uploadResult.status === 'fulfilled') {
      uploadItems.value = uploadResult.value.data.list
      uploadCount.value = uploadResult.value.total ?? uploadResult.value.data.list.length
    }
    if (automationResult.status === 'fulfilled') {
      automationItems.value = automationResult.value.data
      automationCount.value = automationResult.value.data.length
    }
    const failed = results.every(result => result.status === 'rejected')
    if (failed) {
      lastErrorAt.value = Date.now()
      offline.value = true
      scheduleItems.value = []
      uploadItems.value = []
      automationItems.value = []
    } else {
      lastErrorAt.value = null
      offline.value = false
      lastUpdatedAt.value = Date.now()
    }
  }

  return {
    scheduleCount,
    uploadCount,
    automationCount,
    scheduleItems,
    uploadItems,
    automationItems,
    items,
    progress,
    total,
    lastErrorAt,
    lastUpdatedAt,
    offline,
    isConnectFailed,
    fetchCounts
  }
})
