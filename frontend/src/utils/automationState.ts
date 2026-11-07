/**
 * 自动追更运行详情页的状态推导（纯函数，唯一来源）。
 *
 * 后端状态分三层：任务循环态（长期，`/active`）、轮次态（单轮，WS 帧 / 运行记录）、
 * WS 连接态。本文件只负责把三层合成为「任务 / 本轮 / 连接」三个独立信号与空态文案，
 * 不在组件里散落 if-else，也方便单测覆盖所有组合。
 */
import type { AutomationRunStatus, AutomationRuntimeState } from '@/types/automation'
import type { WsState } from '@/utils/ws'
import type { StatusTone } from '@/utils/status'
import { AUTOMATION_RUN_STATUS_LABELS, CONNECTION_META, PHASE_LABELS } from '@/utils/status'

export interface RunDetailRound {
  status: AutomationRunStatus | null
  phase: string | null
  roundNo: number
  pending: number
  checked: number
  missed: number
}

export interface RunDetailInput {
  selected: boolean
  runtime: AutomationRuntimeState | null
  connection: WsState
  reconnecting?: boolean
  round: RunDetailRound
}

export interface RunDetailView {
  /** 任务层：运行中 · 当前阶段 / 已停止 / 未选择。 */
  taskLabel: string
  taskTone: StatusTone
  /** 本轮层：第 N 轮 · 状态。 */
  roundLabel: string
  roundTone: StatusTone
  phaseLabel: string
  /** 有下一轮计划时间时给出「下一轮 HH:mm:ss」。 */
  nextRoundText: string | null
  /** 连接层：已连接 / 重连中 / 未连接 / 连接中。 */
  connectionLabel: string
  connectionTone: StatusTone
  /** 日志空态文案：由任务态 + 轮次态推导，不再由「连接断开」推导。 */
  emptyText: string
  taskRunning: boolean
  /** 仅当任务确实在运行、或连接断开但任务有运行态时才提示重连。 */
  canReconnect: boolean
}

const TERMINAL_LABELS: Record<AutomationRunStatus, string> = AUTOMATION_RUN_STATUS_LABELS

function phaseText(phase: string | null | undefined): string {
  if (!phase) return '—'
  return PHASE_LABELS[phase] ?? phase
}

/** 从后端时间字符串（`YYYY-MM-DD HH:MM:SS`）里取时钟部分。 */
export function clockOf(value: string | null | undefined): string | null {
  if (!value) return null
  const match = /(\d{2}:\d{2}:\d{2})/.exec(value)
  return match === null ? null : match[1]
}

function roundTone(status: AutomationRunStatus | null): StatusTone {
  if (status === 'success') return 'success'
  if (status === 'partial') return 'warning'
  if (status === 'fail' || status === 'cancelled') return 'danger'
  return 'info'
}

function emptyTextFor(input: RunDetailInput, phase: string | null, taskRunning: boolean): string {
  if (!input.selected) return '请选择要查看的自动追更'
  if (!taskRunning) {
    if (input.round.status !== null) return '任务当前未运行；可点击「查看最近一轮」或前往「运行记录」查看日志'
    return '任务当前未运行，还没有可显示的日志'
  }
  if (input.connection === 'connecting') return '正在连接运行详情…'
  if (phase === 'idle') return '目录里暂时没有完整视频，任务仍在循环等待，无需手动重试'
  if (phase === 'interval') return '本轮已结束，等待下一轮自动开始…'
  if (phase === 'backoff') return '本轮失败，正在退避重试，下一页日志会记录重试原因'
  if (phase === 'waiting_idle') return '正在等待 STRM 生成 / 云盘上传空闲…'
  if (phase === 'waiting_upload' || phase === 'waiting_openlist_check' || phase === 'waiting_openlist_task') {
    return `当前阶段：${phaseText(phase)}，等待新的日志…`
  }
  return '任务运行中，等待输出日志…'
}

export function deriveRunDetailView(input: RunDetailInput): RunDetailView {
  const { runtime, round, connection } = input
  const taskRunning = runtime !== null
  const phase = round.phase ?? runtime?.phase ?? null
  const roundNo = round.roundNo > 0 ? round.roundNo : (runtime?.round_no ?? 0)
  const nextClock = clockOf(runtime?.next_round_at)
  // 空态由「任务层」阶段解释（轮次结束后 round.phase 为 done，不能代表任务当前在做什么）。
  const emptyPhase = runtime ? (runtime.phase ?? round.phase) : round.phase

  const taskLabel = !input.selected
    ? '未选择任务'
    : taskRunning
      ? `运行中 · ${phaseText(runtime?.phase)}`
      : '已停止'
  const taskTone: StatusTone = !input.selected ? 'info' : taskRunning ? (runtime?.phase === 'backoff' ? 'warning' : 'success') : 'info'

  const roundLabel = round.status !== null
    ? `第 ${roundNo > 0 ? roundNo : '—'} 轮 · ${TERMINAL_LABELS[round.status]}`
    : roundNo > 0
      ? `第 ${roundNo} 轮 · 进行中`
      : '尚无运行记录'

  const connectionLabel = input.reconnecting
    ? '重连中'
    : input.selected && connection === 'disconnected' && !taskRunning
      ? '已断开'
      : CONNECTION_META[connection].label
  const connectionTone: StatusTone = input.reconnecting
    ? 'warning'
    : input.selected && connection === 'disconnected' && !taskRunning
      ? 'info'
      : CONNECTION_META[connection].tone

  return {
    taskLabel,
    taskTone,
    roundLabel,
    roundTone: roundTone(round.status),
    phaseLabel: phaseText(phase),
    nextRoundText: nextClock === null ? null : `下一轮 ${nextClock}`,
    connectionLabel,
    connectionTone,
    emptyText: emptyTextFor(input, emptyPhase, taskRunning),
    taskRunning,
    canReconnect: input.selected && (taskRunning || connection === 'disconnected')
  }
}
