import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { usePolling } from '@/composables/usePolling'

describe('usePolling', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('按间隔调用任务', async () => {
    const task = vi.fn()
    const poll = usePolling(task, { interval: 1000, visibleOnly: false })
    poll.start()

    await vi.advanceTimersByTimeAsync(1000)
    expect(task).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(2000)
    expect(task).toHaveBeenCalledTimes(3)

    poll.stop()
  })

  it('start 幂等：重复调用只保留一条定时器', async () => {
    const task = vi.fn()
    const poll = usePolling(task, { interval: 1000, visibleOnly: false })
    poll.start()
    poll.start()
    poll.start()

    await vi.advanceTimersByTimeAsync(1000)
    expect(task).toHaveBeenCalledTimes(1)

    poll.stop()
  })

  it('上一轮未完成时跳过本轮', async () => {
    let resolveFirst: (() => void) | null = null
    const task = vi.fn(() => {
      if (task.mock.calls.length === 1) {
        return new Promise<void>(resolve => {
          resolveFirst = resolve
        })
      }
      return undefined
    })
    const poll = usePolling(task, { interval: 1000, visibleOnly: false })
    poll.start()

    await vi.advanceTimersByTimeAsync(1000)
    expect(task).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(1000)
    expect(task).toHaveBeenCalledTimes(1)

    resolveFirst?.()
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(1000)
    expect(task).toHaveBeenCalledTimes(2)

    poll.stop()
  })

  it('immediate 启动时立即执行一次', async () => {
    const task = vi.fn()
    const poll = usePolling(task, { interval: 1000, immediate: true, visibleOnly: false })
    poll.start()

    await vi.advanceTimersByTimeAsync(0)
    expect(task).toHaveBeenCalledTimes(1)

    poll.stop()
  })

  it('stop 后不再触发', async () => {
    const task = vi.fn()
    const poll = usePolling(task, { interval: 1000, visibleOnly: false })
    poll.start()
    await vi.advanceTimersByTimeAsync(1000)
    poll.stop()
    await vi.advanceTimersByTimeAsync(3000)
    expect(task).toHaveBeenCalledTimes(1)
  })

  it('任务抛错不会中断后续轮询', async () => {
    const task = vi.fn(() => {
      throw new Error('boom')
    })
    const poll = usePolling(task, { interval: 1000, visibleOnly: false })
    poll.start()

    await vi.advanceTimersByTimeAsync(1000)
    await vi.advanceTimersByTimeAsync(1000)
    expect(task).toHaveBeenCalledTimes(2)

    poll.stop()
  })
})
