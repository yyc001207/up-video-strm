import { describe, expect, it } from 'vitest'

import { percentOf, scheduleProgress, uploadProgress } from '@/utils/execution'

describe('percentOf', () => {
  it('正常计算并四舍五入为整数', () => {
    expect(percentOf(1, 3)).toBe(33)
    expect(percentOf(2, 3)).toBe(67)
    expect(percentOf(5, 5)).toBe(100)
  })

  it('缺分母或分母为 0 时返回 null', () => {
    expect(percentOf(1, 0)).toBeNull()
    expect(percentOf(1, null)).toBeNull()
    expect(percentOf(1, undefined)).toBeNull()
    expect(percentOf(1, Number.NaN)).toBeNull()
  })

  it('夹在 0–100 之间，避免异常数据画出越界进度', () => {
    expect(percentOf(-1, 10)).toBe(0)
    expect(percentOf(12, 10)).toBe(100)
  })
})

describe('scheduleProgress', () => {
  it('按视频成功数/总数计算', () => {
    expect(scheduleProgress({ video_success_count: 3, video_total_count: 4 })).toBe(75)
    expect(scheduleProgress({ video_success_count: 0, video_total_count: 0 })).toBeNull()
  })
})

describe('uploadProgress', () => {
  it('成功 + 跳过都算已完成', () => {
    expect(uploadProgress({ file_success: 2, file_skipped: 1, file_total: 4 })).toBe(75)
    expect(uploadProgress({ file_success: 0, file_skipped: 0, file_total: 0 })).toBeNull()
  })
})
