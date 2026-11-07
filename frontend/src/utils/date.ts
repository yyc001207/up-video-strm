/**
 * 日期时间格式化工具。
 *
 * 项目全局约定：
 * - 所有时间一律按「北京时间（Asia/Shanghai）」解释与展示；
 * - 日期时间格式 `YYYY-MM-DD HH:mm:ss`，日期格式 `YYYY-MM-DD`。
 *
 * 后端返回的是北京时间墙钟字符串（无时区信息，如 `2026-11-05T18:43:59`），
 * 这里把不带时区的字符串按 Asia/Shanghai 解释；若字符串自带 Z 或 ±HH:mm 偏移，
 * 先解析为绝对时间再换算到北京时间，因此展示结果与浏览器本地时区无关。
 */
import dayjs from 'dayjs'
import timezone from 'dayjs/plugin/timezone'
import utc from 'dayjs/plugin/utc'

dayjs.extend(utc)
dayjs.extend(timezone)

export const BEIJING_TIMEZONE = 'Asia/Shanghai'

const DATE_TIME_FORMAT = 'YYYY-MM-DD HH:mm:ss'
const DATE_FORMAT = 'YYYY-MM-DD'

/** 字符串是否自带时区信息（Z 或 ±HH:mm）。 */
function hasOffset(value: string): boolean {
  return /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value.trim())
}

/**
 * 解析为北京时间 dayjs 实例：无时区信息按北京时间墙钟解释，有时区信息则换算。
 * 空值或非法值返回 null。
 */
export function parseBeijing(value: string | null | undefined): dayjs.Dayjs | null {
  if (!value) return null
  const text = String(value).trim()
  if (!text) return null
  const parsed = hasOffset(text) ? dayjs(text).tz(BEIJING_TIMEZONE) : dayjs.tz(text, BEIJING_TIMEZONE)
  return parsed.isValid() ? parsed : null
}

/** 统一日期时间展示：`YYYY-MM-DD HH:mm:ss`（北京时间），空值返回 `-`。 */
export function formatDateTime(value: string | null | undefined): string {
  const parsed = parseBeijing(value)
  return parsed ? parsed.format(DATE_TIME_FORMAT) : '-'
}

/** 统一日期展示：`YYYY-MM-DD`（北京时间），空值返回 `-`。 */
export function formatDate(value: string | null | undefined): string {
  const parsed = parseBeijing(value)
  return parsed ? parsed.format(DATE_FORMAT) : '-'
}

/** 北京时间毫秒时间戳（用于计算耗时），无法解析返回 null。 */
export function beijingMillis(value: string | null | undefined): number | null {
  const parsed = parseBeijing(value)
  return parsed ? parsed.valueOf() : null
}

export interface BeijingDayRangeMillis {
  startMs: number | null
  endMs: number | null
}

/**
 * 时间范围 → 北京时间当日边界毫秒：开始日 00:00:00、结束日 23:59:59。
 * 用于列表页的日期范围筛选，保证筛选含首尾两天。
 */
export function toBeijingDayRange(
  range: readonly [string, string] | null | undefined
): BeijingDayRangeMillis | null {
  if (!range) return null
  return {
    startMs: beijingMillis(`${range[0]} 00:00:00`),
    endMs: beijingMillis(`${range[1]} 23:59:59`)
  }
}
