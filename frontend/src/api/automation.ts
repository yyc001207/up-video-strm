/** 自动追更接口封装（模块 C：任务 CRUD / 绑定选项 / 校验目录检测）。 */

import request from './index'
import type { Res } from '@/types/openlist'
import type {
  AutomationActiveTask,
  AutomationBatchStartItem,
  AutomationBindOptions,
  AutomationCheckDirResult,
  AutomationRun,
  AutomationRunLogResult,
  AutomationStartPayload,
  AutomationTask,
  AutomationTaskPayload,
  AutomationTaskSaveResult
} from '@/types/automation'

export const automationApi = {
  listTasks: (params: { keyword?: string; page?: number; page_size?: number }) =>
    request.get<unknown, Res<AutomationTask[]>>('/automation/tasks', { params }),
  getTask: (id: number) => request.get<unknown, Res<AutomationTask>>(`/automation/tasks/${id}`),
  createTask: (data: AutomationTaskPayload) =>
    request.post<unknown, Res<AutomationTaskSaveResult>>('/automation/tasks', data),
  updateTask: (id: number, data: Partial<AutomationTaskPayload>) =>
    request.put<unknown, Res<AutomationTaskSaveResult>>(`/automation/tasks/${id}`, data),
  deleteTask: (id: number) => request.delete<unknown, Res<null>>(`/automation/tasks/${id}`),
  batchDeleteTasks: (ids: number[]) =>
    request.post<unknown, Res<{ deleted: number }>>('/automation/tasks/batch-delete', { ids }),
  bindOptions: (includeTaskId?: number) =>
    request.get<unknown, Res<AutomationBindOptions>>('/automation/bind-options', {
      params: includeTaskId ? { include_task_id: includeTaskId } : undefined
    }),
  checkDir: (data: { upload_task_id: number; check_dir: string; task_id?: number }) =>
    request.post<unknown, Res<AutomationCheckDirResult>>('/automation/tasks/check-dir', data)
}

// ---------- 开始执行 / 运行历史（阶段③） ----------

export const automationRunApi = {
  start: (id: number, data?: AutomationStartPayload) =>
    request.post<unknown, Res<{ started: boolean; task_id: number }>>(`/automation/tasks/${id}/start`, data ?? {}),
  batchStart: (taskIds: number[], data?: AutomationStartPayload) =>
    request.post<unknown, Res<AutomationBatchStartItem[]>>('/automation/tasks/batch-start', {
      task_ids: taskIds,
      ...(data ?? {})
    }),
  stop: (id: number) => request.post<unknown, Res<{ stopping: boolean }>>(`/automation/tasks/${id}/stop`),
  active: () => request.get<unknown, Res<AutomationActiveTask[]>>('/automation/active'),
  resetFingerprint: (id: number) =>
    request.post<unknown, Res<AutomationTask>>(`/automation/tasks/${id}/reset-fingerprint`),
  clearPending: (id: number, remoteNames?: string[]) =>
    request.post<unknown, Res<AutomationTask>>(`/automation/tasks/${id}/pending/clear`, {
      remote_names: remoteNames
    }),
  listRuns: (params: {
    task_id?: number
    status?: string
    start_time?: string
    end_time?: string
    page?: number
    page_size?: number
  }) => request.get<unknown, Res<AutomationRun[]>>('/automation/runs', { params }),
  getRun: (id: number) => request.get<unknown, Res<AutomationRun>>(`/automation/runs/${id}`),
  runLogs: (id: number, offset = 0, limit = 200) =>
    request.get<unknown, Res<AutomationRunLogResult>>(`/automation/runs/${id}/logs`, {
      params: { offset, limit }
    }),
  retryFailed: (id: number) => request.post<unknown, Res<AutomationTask>>(`/automation/runs/${id}/retry-failed`)
}
