/**
 * 状态映射常量（唯一来源）。
 *
 * 只放「状态 → 文案/色调」这类纯数据；筛选选项（`STATUS_OPTIONS`）与页面专属文案
 * 仍保留在各自页面，避免把业务差异抹平。
 */
import type { AutomationRunStatus } from '@/types/automation'
import type { WsState } from '@/utils/ws'

/** 标签/状态色调，与 Element Plus 的 `el-tag` type 对齐。 */
export type StatusTone = 'success' | 'warning' | 'danger' | 'info'

/** 自动追更阶段文案：开始执行页 / 运行详情页共用。 */
export const PHASE_LABELS: Record<string, string> = {
  starting: '准备中',
  waiting_idle: '等待 A/B 空闲',
  waiting_upload: '上传中',
  waiting_openlist_check: '校验 OpenList 可见性',
  waiting_openlist_task: 'STRM 调度中',
  interval: '等待下一轮',
  backoff: '失败退避中',
  idle: '空闲等待',
  stopped: '已停止',
  done: '已结束'
}

/**
 * 自动追更阶段文案（运行记录页）：历史页用词与实时页不同，保持原文，不做统一改写。
 */
export const PHASE_LABELS_HISTORY: Record<string, string> = {
  starting: '启动中',
  waiting_idle: '等待空闲',
  waiting_upload: '等待上传完成',
  waiting_openlist_check: '等待 OpenList 可见',
  waiting_openlist_task: '等待 STRM 完成',
  interval: '轮次间隔',
  backoff: '失败退避',
  idle: '空闲等待',
  stopped: '已停止',
  done: '本轮完成'
}

/** WebSocket 连接状态文案与色调（三个运行详情页共用）。 */
export const CONNECTION_META: Record<WsState, { label: string; tone: StatusTone }> = {
  connecting: { label: '连接中', tone: 'info' },
  connected: { label: '已连接', tone: 'success' },
  disconnected: { label: '未连接', tone: 'danger' }
}

/** 自动追更轮次状态文案（运行记录与运行详情共用）。 */
export const AUTOMATION_RUN_STATUS_LABELS: Record<AutomationRunStatus, string> = {
  running: '运行中',
  success: '成功',
  partial: '部分成功',
  fail: '失败',
  cancelled: '已取消'
}
