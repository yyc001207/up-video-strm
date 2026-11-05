/** 上传管理接口封装：123 云盘凭据配置与连通性测试。 */

import request from './index'
import type { Res } from '@/types/openlist'
import type {
  UploadPlatformConfig,
  UploadPlatformConfigUpdate,
  UploadTestConnectionRequest
} from '@/types/uploader'

export const uploaderApi = {
  getConfig: () => request.get<unknown, Res<UploadPlatformConfig>>('/upload/config'),
  updateConfig: (data: UploadPlatformConfigUpdate) =>
    request.put<unknown, Res<UploadPlatformConfig>>('/upload/config', data),
  testConnection: (data: UploadTestConnectionRequest, config?: { silent?: boolean }) =>
    request.post<unknown, Res<{ message: string }>>('/upload/config/test-connection', data, config)
}
