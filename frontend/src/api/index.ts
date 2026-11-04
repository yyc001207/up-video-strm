/** axios 实例：统一响应处理（本地部署，无登录态处理）。 */

import axios from 'axios'
import type { AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 30000
})

request.interceptors.response.use(
  (response: AxiosResponse) => {
    const res = response.data as { code: number; msg?: string }
    if (res.code === 200) {
      // 业务层已统一拆包，此处按原 AxiosResponse 类型透传（类型仅用于让拦截器签名成立）
      return response.data as unknown as AxiosResponse
    }
    if (res.code === 429) {
      ElMessage.warning('请求过于频繁，请稍后再试')
      return Promise.reject(res)
    }
    ElMessage.error(res.msg || '请求失败')
    return Promise.reject(res)
  },
  error => {
    ElMessage.error('网络异常，请稍后重试')
    return Promise.reject(error)
  }
)

export default request
