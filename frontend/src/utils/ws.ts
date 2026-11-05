/** WebSocket 封装：连接/断开执行实时日志流（本地部署，无鉴权）。 */

import type { WsFrame } from '@/types/openlist'
import type { UploadWsFrame } from '@/types/uploader'
import type { AutomationWsFrame } from '@/types/automation'

export type WsHandler = (frame: WsFrame) => void
export type UploadWsHandler = (frame: UploadWsFrame) => void
export type AutomationWsHandler = (frame: AutomationWsFrame) => void

export interface WsOptions {
  onMessage: WsHandler
  onOpen?: () => void
  onClose?: () => void
  onError?: () => void
}

export interface UploadWsOptions {
  onMessage: UploadWsHandler
  onOpen?: () => void
  onClose?: () => void
  onError?: () => void
}

export interface AutomationWsOptions {
  onMessage: AutomationWsHandler
  onOpen?: () => void
  onClose?: () => void
  onError?: () => void
}

export type WsState = 'connecting' | 'connected' | 'disconnected'

/** 拼出 WS 地址；模块决定后端路由前缀（openlist / upload / automation）。 */
export function buildWsUrl(
  targetId: number,
  module: 'openlist' | 'upload' | 'automation' = 'openlist'
): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const base = import.meta.env.VITE_API_BASE_URL ?? '/api'
  return `${proto}://${location.host}${base}/${module}/ws/${targetId}`
}

function openSocket<T>(url: string, options: {
  onMessage: (frame: T) => void
  onOpen?: () => void
  onClose?: () => void
  onError?: () => void
}): WebSocket {
  const ws = new WebSocket(url)
  ws.onopen = () => options.onOpen?.()
  ws.onmessage = event => {
    try {
      const frame = JSON.parse(event.data as string) as T
      options.onMessage(frame)
    } catch {
      /* 忽略无法解析的帧 */
    }
  }
  ws.onclose = () => options.onClose?.()
  ws.onerror = () => options.onError?.()
  return ws
}

export function connectWs(executionId: number, options: WsOptions): WebSocket {
  return openSocket<WsFrame>(buildWsUrl(executionId), options)
}

/** 上传管理模块的实时日志连接（不同路由前缀）。 */
export function connectUploadWs(executionId: number, options: UploadWsOptions): WebSocket {
  return openSocket<UploadWsFrame>(buildWsUrl(executionId, 'upload'), options)
}

/** 自动化任务模块的实时日志连接（按任务维度，非执行维度）。 */
export function connectAutomationWs(taskId: number, options: AutomationWsOptions): WebSocket {
  return openSocket<AutomationWsFrame>(buildWsUrl(taskId, 'automation'), options)
}

export function disconnectWs(ws: WebSocket | null): void {
  if (ws) {
    ws.onclose = null
    ws.onerror = null
    ws.onmessage = null
    ws.close()
  }
}

export function wsState(ws: WebSocket | null): WsState {
  if (!ws) return 'disconnected'
  if (ws.readyState === WebSocket.OPEN) return 'connected'
  if (ws.readyState === WebSocket.CONNECTING) return 'connecting'
  return 'disconnected'
}
