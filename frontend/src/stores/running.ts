/** 全局运行状态：聚合「任务调度」「上传管理」「自动化任务」三个模块的运行中执行数。 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { openlistApi } from '@/api/openlist'
import { uploaderApi } from '@/api/uploader'
import { automationRunApi } from '@/api/automation'

/** 顶栏轮询间隔（壳层统一轮询，页面内继续保留各自的轮询）。 */
export const RUNNING_POLL_MS = 10000
/** 最近一次失败后视为「连接失败」的窗口。 */
export const OFFLINE_WINDOW_MS = 30000

export const useRunningStore = defineStore('running', () => {
  const scheduleCount = ref(0)
  const uploadCount = ref(0)
  const automationCount = ref(0)
  /** 最近一次轮询失败时间（毫秒时间戳），成功轮询后清空。 */
  const lastErrorAt = ref<number | null>(null)
  /** 最近一次轮询是否全部失败（后端不可达）。 */
  const offline = ref(false)

  const total = computed(() => scheduleCount.value + uploadCount.value + automationCount.value)

  function isConnectFailed(now = Date.now()): boolean {
    return lastErrorAt.value !== null && now - lastErrorAt.value < OFFLINE_WINDOW_MS
  }

  async function fetchCounts(): Promise<void> {
    const results = await Promise.allSettled([
      openlistApi.listExecutions({ status: 'running', page: 1, pageSize: 1 }, { silent: true }),
      uploaderApi.listExecutions({ status: 'running', page: 1, pageSize: 1 }, { silent: true }),
      automationRunApi.active()
    ])
    const [scheduleResult, uploadResult, automationResult] = results
    if (scheduleResult.status === 'fulfilled') {
      scheduleCount.value = scheduleResult.value.total ?? scheduleResult.value.data.list.length
    }
    if (uploadResult.status === 'fulfilled') {
      uploadCount.value = uploadResult.value.total ?? uploadResult.value.data.list.length
    }
    if (automationResult.status === 'fulfilled') {
      automationCount.value = automationResult.value.data.length
    }
    const failed = results.every(result => result.status === 'rejected')
    if (failed) {
      lastErrorAt.value = Date.now()
      offline.value = true
    } else {
      lastErrorAt.value = null
      offline.value = false
    }
  }

  return {
    scheduleCount,
    uploadCount,
    automationCount,
    total,
    lastErrorAt,
    offline,
    isConnectFailed,
    fetchCounts
  }
})


