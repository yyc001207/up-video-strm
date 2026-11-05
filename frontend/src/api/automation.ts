/** 自动化任务接口封装（模块 C：任务配置 CRUD / 绑定选项 / 校验目录检测）。 */

import request from './index'
import type { Res } from '@/types/openlist'
import type {
  AutomationBindOptions,
  AutomationCheckDirResult,
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
