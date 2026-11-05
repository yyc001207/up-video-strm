/** 上传管理接口封装：123 云盘凭据配置与连通性测试。 */

import request from './index'
import type { Res } from '@/types/openlist'
import type {
  UploadPlatformConfig,
  UploadPlatformConfigUpdate,
  UploadRemoteDirList,
  UploadRenamePreviewRequest,
  UploadRenamePreviewResponse,
  UploadRenameRule,
  UploadRenameRuleCreate,
  UploadRenameRuleUpdate,
  UploadTask,
  UploadTaskCreate,
  UploadTaskUpdate,
  UploadTestConnectionRequest
} from '@/types/uploader'

export const uploaderApi = {
  getConfig: () => request.get<unknown, Res<UploadPlatformConfig>>('/upload/config'),
  updateConfig: (data: UploadPlatformConfigUpdate) =>
    request.put<unknown, Res<UploadPlatformConfig>>('/upload/config', data),
  testConnection: (data: UploadTestConnectionRequest, config?: { silent?: boolean }) =>
    request.post<unknown, Res<{ message: string }>>('/upload/config/test-connection', data, config),

  listRenameRules: () => request.get<unknown, Res<UploadRenameRule[]>>('/upload/rules'),
  createRenameRule: (data: UploadRenameRuleCreate) =>
    request.post<unknown, Res<UploadRenameRule>>('/upload/rules', data),
  updateRenameRule: (id: number, data: UploadRenameRuleUpdate) =>
    request.put<unknown, Res<UploadRenameRule>>(`/upload/rules/${id}`, data),
  deleteRenameRule: (id: number) => request.delete<unknown, Res<null>>(`/upload/rules/${id}`),
  previewRename: (data: UploadRenamePreviewRequest) =>
    request.post<unknown, Res<UploadRenamePreviewResponse>>('/upload/rules/preview', data),

  listTasks: () => request.get<unknown, Res<UploadTask[]>>('/upload/tasks'),
  createTask: (data: UploadTaskCreate) => request.post<unknown, Res<UploadTask>>('/upload/tasks', data),
  updateTask: (id: number, data: UploadTaskUpdate) =>
    request.put<unknown, Res<UploadTask>>(`/upload/tasks/${id}`, data),
  deleteTask: (id: number) => request.delete<unknown, Res<null>>(`/upload/tasks/${id}`),

  listRemoteDirs: (params: { parent_id?: number; path?: string }) =>
    request.get<unknown, Res<UploadRemoteDirList>>('/upload/remote/dirs', { params })
}
