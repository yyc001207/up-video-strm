/** WebSocket 封装：连接/断开执行实时日志流（本地部署，无鉴权）。 */

import type { WsFrame } from '@/types/openlist'
import type { UploadWsFrame } from '@/types/uploader'

export type WsHandler = (frame: WsFrame) => void
export type UploadWsHandler = (frame: UploadWsFrame) => void

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

export type WsState = 'connecting' | 'connected' | 'disconnected'

/** 拼出 WS 地址；模块决定后端路由前缀（openlist / upload）。 */
export function buildWsUrl(executionId: number, module: 'openlist' | 'upload' = 'openlist'): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const base = import.meta.env.VITE_API_BASE_URL ?? '/api'
  return `${proto}://${location.host}${base}/${module}/ws/${executionId}`
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
