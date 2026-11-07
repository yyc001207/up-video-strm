import { describe, expect, it } from 'vitest'

import {
  AUTOMATION_RUN_STATUS_LABELS,
  CONNECTION_META,
  PHASE_LABELS,
  PHASE_LABELS_HISTORY
} from '@/utils/status'

describe('PHASE_LABELS', () => {
  it('覆盖全部自动追更阶段', () => {
    const phases = [
      'starting',
      'waiting_idle',
      'waiting_upload',
      'waiting_openlist_check',
      'waiting_openlist_task',
      'interval',
      'backoff',
      'idle',
      'stopped',
      'done'
    ]
    for (const phase of phases) {
      expect(PHASE_LABELS[phase]).toBeTruthy()
      expect(PHASE_LABELS_HISTORY[phase]).toBeTruthy()
    }
  })

  it('运行记录页保留自己的历史用词，不与实时页统一改写', () => {
    expect(PHASE_LABELS.waiting_upload).toBe('上传中')
    expect(PHASE_LABELS_HISTORY.waiting_upload).toBe('等待上传完成')
    expect(PHASE_LABELS.done).toBe('已结束')
    expect(PHASE_LABELS_HISTORY.done).toBe('本轮完成')
  })
})

describe('CONNECTION_META', () => {
  it('三种连接状态都有文案与色调', () => {
    expect(CONNECTION_META.connecting).toEqual({ label: '连接中', tone: 'info' })
    expect(CONNECTION_META.connected).toEqual({ label: '已连接', tone: 'success' })
    expect(CONNECTION_META.disconnected).toEqual({ label: '未连接', tone: 'danger' })
  })
})

describe('AUTOMATION_RUN_STATUS_LABELS', () => {
  it('五种轮次状态文案与页面原文本一致', () => {
    expect(AUTOMATION_RUN_STATUS_LABELS).toEqual({
      running: '运行中',
      success: '成功',
      partial: '部分成功',
      fail: '失败',
      cancelled: '已取消'
    })
  })
})
