/** 上传管理接口封装：123 云盘凭据、重命名规则、上传任务、执行与实时日志。 */

import axios from 'axios'
import { ElMessage } from 'element-plus'

import request from './index'
import type { Res } from '@/types/openlist'
import type {
  UploadConflictPolicy,
  UploadExecution,
  UploadExecutionStatus,
  UploadFileRecord,
  UploadHistorySummaryItem,
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
  clearConfig: () => request.delete<unknown, Res<UploadPlatformConfig>>('/upload/config'),
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
    request.get<unknown, Res<UploadRemoteDirList>>('/upload/remote/dirs', { params }),

  createExecution: (data: {
    task_id: number
    conflict_policy: UploadConflictPolicy
    concurrency: number
    retry_times: number
    dry_run: boolean
  }) => request.post<unknown, Res<UploadExecution>>('/upload/executions', data),
  batchCreateExecutions: (data: {
    task_ids: number[]
    conflict_policy: UploadConflictPolicy
    concurrency: number
    retry_times: number
    dry_run: boolean
  }) => request.post<unknown, Res<UploadExecution[]>>('/upload/executions/batch', data),
  startExecution: (executionId: number, taskId: number) =>
    request.post<unknown, Res<UploadExecution>>('/upload/executions/start', {
      execution_id: executionId,
      task_id: taskId
    }),
  cancelExecution: (executionId: number) =>
    request.post<unknown, Res<{ cancelled: boolean; status: UploadExecutionStatus }>>(
      '/upload/executions/cancel',
      { execution_id: executionId }
    ),
  listExecutions: (params: { task_id?: number; status?: UploadExecutionStatus; page: number; pageSize: number }) =>
    request.get<unknown, Res<{ list: UploadExecution[] }>>('/upload/executions', { params }),
  getExecutionDetail: (executionId: number) =>
    request.get<unknown, Res<{ execution: UploadExecution; records: UploadFileRecord[] }>>(
      `/upload/executions/${executionId}`
    ),
  listFileRecords: (executionId: number, page: number, pageSize: number) =>
    request.get<unknown, Res<{ list: UploadFileRecord[] }>>(`/upload/executions/${executionId}/records`, {
      params: { page, pageSize }
    }),
  listExecutionLogs: (executionId: number, page: number, pageSize: number) =>
    request.get<unknown, Res<{ list: { id: number; log_level: string; content: string; created_time: string | null }[] }>>(
      `/upload/executions/${executionId}/logs`,
      { params: { page, pageSize } }
    ),

  historySummary: () => request.get<unknown, Res<UploadHistorySummaryItem[]>>('/upload/history'),
  historyByTask: (taskId: number, page: number, pageSize: number) =>
    request.get<unknown, Res<{ list: UploadExecution[] }>>(`/upload/history/task/${taskId}`, {
      params: { page, pageSize }
    }),
  /** 以原执行的固化参数重新创建一条执行记录（不启动）。 */
  retryExecution: (executionId: number) =>
    request.post<unknown, Res<UploadExecution>>(`/upload/executions/${executionId}/retry`),

  /** 下载执行日志文件（blob，本地部署无鉴权）。 */
  async downloadLog(executionId: number): Promise<void> {
    const response = await axios.get(`/upload/executions/${executionId}/log-download`, {
      baseURL: import.meta.env.VITE_API_BASE_URL,
      responseType: 'blob',
      timeout: 60000
    })
    const blob = response.data as Blob
    const disposition = response.headers['content-disposition'] || ''
    let filename = `upload_execution_${executionId}.log`
    const filenameMatch = disposition.match(/filename\*=UTF-8''([^;]+)/)
    if (filenameMatch?.[1]) {
      try {
        filename = decodeURIComponent(filenameMatch[1])
      } catch {
        /* 忽略解码失败，使用默认文件名 */
      }
    }
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('日志下载成功')
  }
}
