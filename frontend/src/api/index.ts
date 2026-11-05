/** axios 实例：统一响应处理（本地部署，无登录态处理）。 */

import axios from 'axios'
import type { AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'

declare module 'axios' {
  interface AxiosRequestConfig {
    /** 静默失败：为 true 时不弹全局错误消息（用于后台轮询探测等场景）。 */
    silent?: boolean
  }
}

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 30000
})

/** 同一错误文案去重窗口：并发失败/轮询失败只弹一条，避免 toast 轰炸。 */
const ERROR_DEDUPE_MS = 3000
let lastError: { message: string; at: number } | null = null

function showError(message: string): void {
  const now = Date.now()
  if (lastError && lastError.message === message && now - lastError.at < ERROR_DEDUPE_MS) {
    return
  }
  lastError = { message, at: now }
  ElMessage.error(message)
}

request.interceptors.response.use(
  (response: AxiosResponse) => {
    const res = response.data as { code: number; msg?: string }
    const silent = response.config.silent === true
    if (res.code === 200) {
      // 业务层已统一拆包，此处按原 AxiosResponse 类型透传（类型仅用于让拦截器签名成立）
      return response.data as unknown as AxiosResponse
    }
    if (res.code === 429) {
      if (!silent) showError('请求过于频繁，请稍后再试')
      return Promise.reject(res)
    }
    if (!silent) showError(res.msg || '请求失败')
    return Promise.reject(res)
  },
  error => {
    if (error?.config?.silent !== true) showError('网络异常，请稍后重试')
    return Promise.reject(error)
  }
)

export default request
