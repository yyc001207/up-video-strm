/**
 * 展示格式化纯函数。
 *
 * 约定（见 `docs/design/frontend-reuse-plan.md` §2.1）：
 * - 不 import Vue / DOM / router / store / api；
 * - 同一逻辑只允许一处实现，页面直接 import，不再保留同名本地函数。
 */

export interface TriggerLike {
  trigger_source?: string | null
  trigger_name?: string | null
}

/** 谁启动的：automation → `自动化 · 名称`，其余 → `手动`。 */
export function triggerText(row: TriggerLike): string {
  if (row.trigger_source !== 'automation') return '手动'
  return row.trigger_name ? `自动化 · ${row.trigger_name}` : '自动化'
}

/** 成功/总数：total 为 0 或缺失 → `—`。 */
export function countText(success: number, total: number): string {
  return total > 0 ? `${success}/${total}` : '—'
}

/** 时长：65 → `1 分 5 秒`；空/负数/NaN → `—`。 */
export function durationText(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  if (!Number.isFinite(seconds) || seconds < 0) return '—'
  const total = Math.floor(seconds)
  if (total < 60) return `${total} 秒`
  return `${Math.floor(total / 60)} 分 ${total % 60} 秒`
}

/** 计时器：65 → `01:05`；超过 1 小时 → `1:01:05`。 */
export function clockText(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '—'
  const total = Math.floor(seconds)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const rest = total % 60
  const mm = String(minutes).padStart(2, '0')
  const ss = String(rest).padStart(2, '0')
  return hours > 0 ? `${hours}:${mm}:${ss}` : `${mm}:${ss}`
}
