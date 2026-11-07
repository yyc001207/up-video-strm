import { describe, expect, it } from 'vitest'

import { beijingMillis, toBeijingDayRange } from '@/utils/date'

describe('toBeijingDayRange', () => {
  it('空范围返回 null', () => {
    expect(toBeijingDayRange(null)).toBeNull()
    expect(toBeijingDayRange(undefined)).toBeNull()
  })

  it('开始日取 00:00:00、结束日取 23:59:59（北京时间）', () => {
    const range = toBeijingDayRange(['2026-03-01', '2026-03-31'])
    expect(range).not.toBeNull()
    expect(range?.startMs).toBe(beijingMillis('2026-03-01 00:00:00'))
    expect(range?.endMs).toBe(beijingMillis('2026-03-31 23:59:59'))
  })

  it('跨年范围仍是升序', () => {
    const range = toBeijingDayRange(['2025-12-31', '2026-01-01'])
    expect(range?.startMs).not.toBeNull()
    expect(range?.endMs).not.toBeNull()
    expect((range?.startMs ?? 0) < (range?.endMs ?? 0)).toBe(true)
  })

  it('同一天的范围仍覆盖 00:00:00 ~ 23:59:59', () => {
    const range = toBeijingDayRange(['2026-11-07', '2026-11-07'])
    expect(range?.endMs).toBeGreaterThan(range?.startMs ?? 0)
  })
})
