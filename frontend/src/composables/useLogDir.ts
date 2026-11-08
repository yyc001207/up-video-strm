/**
 * 打开日志文件夹（唯一允许调用 `desktopApi.openLogDir` 的地方）。
 *
 * 只统一入口与失败兜底：失败提示由 axios 拦截器展示（后端返回
 * 「仅 Windows 本地环境支持打开日志文件夹」），页面不再各写 try/catch。
 * 带重入保护，避免连点重复请求。
 */
import { ref } from 'vue'

import { desktopApi } from '@/api/desktop'

export type LogDirKind = 'openlist' | 'upload' | 'automation' | 'rename'

export function useLogDir(kind: LogDirKind): { open: () => Promise<void> } {
  const opening = ref(false)

  async function open(): Promise<void> {
    if (opening.value) return
    opening.value = true
    try {
      await desktopApi.openLogDir(kind)
    } catch {
      /* 错误提示由请求拦截器统一处理 */
    } finally {
      opening.value = false
    }
  }

  return { open }
}
