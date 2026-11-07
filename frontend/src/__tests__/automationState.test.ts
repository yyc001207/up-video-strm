import { describe, expect, it } from 'vitest'

import { clockOf, deriveRunDetailView, type RunDetailInput } from '@/utils/automationState'

function runtime(patch: Partial<NonNullable<RunDetailInput['runtime']>> = {}): RunDetailInput['runtime'] {
  return {
    task_id: 1,
    task_name: '自动追更 A',
    phase: 'running',
    run_id: 11,
    round_no: 3,
    next_round_at: null,
    log_path: null,
    started_time: '2026-11-08 10:00:00',
    ...patch
  }
}

function input(patch: Partial<RunDetailInput> = {}): RunDetailInput {
  return {
    selected: true,
    runtime: runtime(),
    connection: 'connected',
    round: { status: null, phase: null, roundNo: 0, pending: 0, checked: 0, missed: 0 },
    ...patch
  }
}

describe('deriveRunDetailView', () => {
  it('未选择任务时三个信号都保持中性', () => {
    const view = deriveRunDetailView(input({ selected: false, runtime: null, connection: 'disconnected' }))
    expect(view.taskLabel).toBe('未选择任务')
    expect(view.taskTone).toBe('info')
    expect(view.emptyText).toBe('请选择要查看的自动追更')
    expect(view.canReconnect).toBe(false)
  })

  it('任务空闲等待时显示运行中 + 空闲等待，且解释无日志原因', () => {
    const view = deriveRunDetailView(input({ runtime: runtime({ phase: 'idle' }) }))
    expect(view.taskLabel).toBe('运行中 · 空闲等待')
    expect(view.emptyText).toContain('暂时没有完整视频')
    expect(view.taskRunning).toBe(true)
    expect(view.connectionLabel).toBe('已连接')
  })

  it('本轮成功且任务仍运行时不断开，显示下一轮时间', () => {
    const view = deriveRunDetailView(
      input({
        runtime: runtime({ phase: 'interval', next_round_at: '2026-11-08 10:01:05' }),
        round: { status: 'success', phase: 'done', roundNo: 3, pending: 0, checked: 2, missed: 0 }
      })
    )
    expect(view.roundLabel).toBe('第 3 轮 · 成功')
    expect(view.roundTone).toBe('success')
    expect(view.nextRoundText).toBe('下一轮 10:01:05')
    expect(view.emptyText).toContain('等待下一轮')
    expect(view.canReconnect).toBe(true)
  })

  it('失败退避时任务出现警告态', () => {
    const view = deriveRunDetailView(
      input({
        runtime: runtime({ phase: 'backoff', next_round_at: '2026-11-08 10:02:00' }),
        round: { status: 'fail', phase: 'done', roundNo: 4, pending: 1, checked: 0, missed: 2 }
      })
    )
    expect(view.taskLabel).toBe('运行中 · 失败退避中')
    expect(view.taskTone).toBe('warning')
    expect(view.roundTone).toBe('danger')
    expect(view.nextRoundText).toBe('下一轮 10:02:00')
    expect(view.emptyText).toContain('退避重试')
  })

  it('部分成功按警告色展示', () => {
    const view = deriveRunDetailView(
      input({ round: { status: 'partial', phase: 'done', roundNo: 2, pending: 0, checked: 1, missed: 1 } })
    )
    expect(view.roundLabel).toBe('第 2 轮 · 部分成功')
    expect(view.roundTone).toBe('warning')
  })

  it('已取消按危险色展示', () => {
    const view = deriveRunDetailView(
      input({ round: { status: 'cancelled', phase: 'done', roundNo: 2, pending: 0, checked: 0, missed: 0 } })
    )
    expect(view.roundTone).toBe('danger')
  })

  it('任务停止时显示已停止，连接状态不冒充任务状态', () => {
    const view = deriveRunDetailView(
      input({
        runtime: null,
        connection: 'disconnected',
        round: { status: 'fail', phase: 'done', roundNo: 5, pending: 1, checked: 0, missed: 1 }
      })
    )
    expect(view.taskLabel).toBe('已停止')
    expect(view.taskTone).toBe('info')
    expect(view.connectionLabel).toBe('已断开')
    expect(view.connectionTone).toBe('info')
    expect(view.emptyText).toContain('任务当前未运行')
    expect(view.emptyText).toContain('查看最近一轮')
  })

  it('任务未运行且没有任何轮次时给出简洁空态', () => {
    const view = deriveRunDetailView(input({ runtime: null, connection: 'disconnected' }))
    expect(view.roundLabel).toBe('尚无运行记录')
    expect(view.emptyText).toBe('任务当前未运行，还没有可显示的日志')
  })

  it('运行中但 WS 正在连接时提示连接中', () => {
    const view = deriveRunDetailView(input({ connection: 'connecting' }))
    expect(view.emptyText).toBe('正在连接运行详情…')
    expect(view.connectionLabel).toBe('连接中')
  })

  it('自动重连期间连接标签为重连中（警告色）', () => {
    const view = deriveRunDetailView(input({ connection: 'disconnected', reconnecting: true }))
    expect(view.connectionLabel).toBe('重连中')
    expect(view.connectionTone).toBe('warning')
  })

  it('等待 A/B 阶段时给出阶段说明空态', () => {
    const waiting = deriveRunDetailView(input({ runtime: runtime({ phase: 'waiting_upload' }) }))
    expect(waiting.emptyText).toBe('当前阶段：上传中，等待新的日志…')
    const idle = deriveRunDetailView(input({ runtime: runtime({ phase: 'waiting_idle' }) }))
    expect(idle.emptyText).toContain('等待 STRM 生成 / 云盘上传空闲')
  })

  it('只有任务最新轮次号时显示进行中', () => {
    const view = deriveRunDetailView(input({ round: { status: null, phase: 'waiting_openlist_check', roundNo: 0, pending: 0, checked: 0, missed: 0 } }))
    expect(view.roundLabel).toBe('第 3 轮 · 进行中')
    expect(view.phaseLabel).toBe('校验 OpenList 可见性')
  })

  it('没有下一轮时间时不显示倒计时文案', () => {
    const view = deriveRunDetailView(input())
    expect(view.nextRoundText).toBeNull()
  })

  it('已连接且无运行态时不需要重连', () => {
    const view = deriveRunDetailView(input({ runtime: null, connection: 'connected' }))
    expect(view.canReconnect).toBe(false)
  })
})

describe('clockOf', () => {
  it('从后端时间字符串取出时钟部分', () => {
    expect(clockOf('2026-11-08 09:05:03')).toBe('09:05:03')
  })

  it('空值与无时间部分返回 null', () => {
    expect(clockOf(null)).toBeNull()
    expect(clockOf('')).toBeNull()
    expect(clockOf('tomorrow')).toBeNull()
  })
})
