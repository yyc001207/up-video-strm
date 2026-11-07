import { describe, expect, it } from 'vitest'

import { clockText, countText, durationText, triggerText } from '@/utils/format'

describe('triggerText', () => {
  it('自动追更触发时展示任务名', () => {
    expect(triggerText({ trigger_source: 'automation', trigger_name: '追更 · 某剧' })).toBe(
      '自动化 · 追更 · 某剧'
    )
  })

  it('自动追更但缺任务名时只展示「自动化」', () => {
    expect(triggerText({ trigger_source: 'automation', trigger_name: null })).toBe('自动化')
    expect(triggerText({ trigger_source: 'automation' })).toBe('自动化')
  })

  it('手动触发与空值都展示「手动」', () => {
    expect(triggerText({ trigger_source: 'manual', trigger_name: 'x' })).toBe('手动')
    expect(triggerText({})).toBe('手动')
  })
})

describe('countText', () => {
  it('正常计数显示 success/total', () => {
    expect(countText(3, 10)).toBe('3/10')
    expect(countText(0, 10)).toBe('0/10')
  })

  it('总数为 0 时显示破折号，避免 0/0 噪声', () => {
    expect(countText(0, 0)).toBe('—')
  })
})

describe('durationText', () => {
  it('空值、负数、NaN 显示破折号', () => {
    expect(durationText(null)).toBe('—')
    expect(durationText(undefined)).toBe('—')
    expect(durationText(-1)).toBe('—')
    expect(durationText(Number.NaN)).toBe('—')
  })

  it('不足 1 分钟按秒展示', () => {
    expect(durationText(0)).toBe('0 秒')
    expect(durationText(59)).toBe('59 秒')
  })

  it('超过 1 分钟按分秒展示', () => {
    expect(durationText(60)).toBe('1 分 0 秒')
    expect(durationText(65)).toBe('1 分 5 秒')
    expect(durationText(3725)).toBe('62 分 5 秒')
  })
})

describe('clockText', () => {
  it('1 小时内为 mm:ss', () => {
    expect(clockText(5)).toBe('00:05')
    expect(clockText(65)).toBe('01:05')
    expect(clockText(3599)).toBe('59:59')
  })

  it('超过 1 小时带小时段', () => {
    expect(clockText(3600)).toBe('1:00:00')
    expect(clockText(3665)).toBe('1:01:05')
  })

  it('非法输入显示破折号', () => {
    expect(clockText(-1)).toBe('—')
    expect(clockText(Number.NaN)).toBe('—')
  })
})
