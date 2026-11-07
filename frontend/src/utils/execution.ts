/**
 * 执行进度纯计算。
 *
 * 三个模块的分母规则不同，因此按模块提供函数，而不是让调用方各自拼公式；
 * 返回值统一为 0–100 的整数百分比，缺分母时为 null（页面显示「—」）。
 */

/** 0–100 的整数百分比；分母缺失/为 0/非法 → null。 */
export function percentOf(part: number, total: number | null | undefined): number | null {
  if (total === null || total === undefined) return null
  if (!Number.isFinite(total) || total <= 0) return null
  if (!Number.isFinite(part)) return null
  return Math.min(100, Math.max(0, Math.round((part / total) * 100)))
}

/** STRM 生成执行进度：视频成功数 / 视频总数。 */
export function scheduleProgress(exec: {
  video_success_count: number
  video_total_count: number
}): number | null {
  return percentOf(exec.video_success_count, exec.video_total_count)
}

/** 云盘上传执行进度：（成功 + 跳过）/ 文件总数。 */
export function uploadProgress(exec: {
  file_success: number
  file_skipped: number
  file_total: number
}): number | null {
  return percentOf(exec.file_success + exec.file_skipped, exec.file_total)
}
