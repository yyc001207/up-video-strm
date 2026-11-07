/**
 * 定时轮询组合式函数（唯一允许调用 `setInterval` 的地方）。
 *
 * 约定（见 `docs/design/frontend-reuse-plan.md` §4.5）：
 * - 同一时刻只保留一条定时器；
 * - 上一轮任务未完成时跳过本轮，避免慢请求叠加；
 * - `visibleOnly`（默认 true）时页面隐藏期间跳过；
 * - 在组件 setup 中调用时，卸载自动停止。
 *
 * 页面仍负责取数、错误处理与文案。
 */
import { getCurrentInstance, onBeforeUnmount } from 'vue'

export interface UsePollingOptions {
  /** 轮询间隔（毫秒），默认 5000。 */
  interval?: number
  /** 启动时立即执行一次，默认 false。 */
  immediate?: boolean
  /** `document.hidden` 时跳过本轮，默认 true。 */
  visibleOnly?: boolean
}

export interface UsePollingHandle {
  start: () => void
  stop: () => void
  /** 立即手动触发一次（同样受「上一轮未完成」保护）。 */
  tick: () => Promise<void>
}

export function usePolling(
  task: () => void | Promise<void>,
  options: UsePollingOptions = {}
): UsePollingHandle {
  const { interval = 5000, immediate = false, visibleOnly = true } = options
  let timer: ReturnType<typeof setInterval> | null = null
  let inFlight = false
  let disposed = false

  async function tick(): Promise<void> {
    if (disposed || inFlight) return
    if (visibleOnly && typeof document !== 'undefined' && document.hidden) return
    inFlight = true
    try {
      await task()
    } catch {
      /* 轮询失败由页面或请求拦截器处理，不在此中断定时器 */
    } finally {
      inFlight = false
    }
  }

  function start(): void {
    if (disposed || timer !== null) return
    timer = setInterval(() => {
      void tick()
    }, interval)
    if (immediate) void tick()
  }

  function stop(): void {
    if (timer === null) return
    clearInterval(timer)
    timer = null
  }

  if (getCurrentInstance()) {
    onBeforeUnmount(() => {
      disposed = true
      stop()
    })
  }

  return { start, stop, tick }
}
