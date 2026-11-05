/** 自动化任务（模块 C）类型定义：任务配置、绑定选项与目录检测。 */

export type AutomationOpenListMode = 'incremental' | 'full' | 'strm_only'

/** 自动化任务（列表 / 详情）。时间字段由后端按北京时间格式化为字符串。 */
export interface AutomationTask {
  id: number
  name: string
  upload_task_id: number
  upload_task_name: string
  openlist_task_id: number
  openlist_task_name: string
  check_dir: string
  upload_concurrency: number
  upload_retry_times: number
  openlist_mode: AutomationOpenListMode
  wait_interval_seconds: number
  openlist_wait_timeout: number
  idle_wait_timeout: number
  stage_timeout: number
  interval_seconds: number
  pending_file_count: number
  last_round_no: number
  consecutive_failures: number
  scan_time: string | null
  is_running: boolean
  created_time: string | null
  updated_time: string | null
}

/** 新建 / 编辑提交字段。 */
export interface AutomationTaskPayload {
  name: string
  upload_task_id: number
  openlist_task_id: number
  check_dir: string
  upload_concurrency: number
  upload_retry_times: number
  openlist_mode: AutomationOpenListMode
  wait_interval_seconds: number
  openlist_wait_timeout: number
  idle_wait_timeout: number
  stage_timeout: number
  interval_seconds: number
}

/** 保存结果附带提示（如校验目录当前不可访问）。 */
export interface AutomationTaskSaveResult extends AutomationTask {
  warnings?: string[]
}

export interface AutomationUploadTaskOption {
  id: number
  name: string
  remote_dir: string
  derived_check_dir: string
  bound_by: string | null
}

export interface AutomationOpenListTaskOption {
  id: number
  name: string
  process_path: string
  output_dir: string
  bound_by: string | null
}

export interface AutomationBindOptions {
  openlist_remote_prefix: string
  upload_tasks: AutomationUploadTaskOption[]
  openlist_tasks: AutomationOpenListTaskOption[]
}

export interface AutomationCheckDirResult {
  check_dir: string
  expected_check_dir: string
  consistent: boolean
  reachable: boolean
  file_count: number
  files: string[]
  error: string | null
  message: string
}
