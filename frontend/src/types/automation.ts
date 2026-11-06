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

/** 新建 / 编辑提交字段（选择框未选中时为 null，避免回显 0）。 */
export interface AutomationTaskPayload {
  name: string
  upload_task_id: number | null
  openlist_task_id: number | null
  check_dir: string
  upload_concurrency: number
  upload_retry_times: number
  openlist_mode: AutomationOpenListMode
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

// ---------- 执行管理 / 运行历史 / 实时日志（阶段③） ----------

export type AutomationRunStatus = 'running' | 'success' | 'partial' | 'fail' | 'cancelled'

/** 自动化任务一轮运行记录。 */
export interface AutomationRun {
  id: number
  task_id: number
  task_name: string
  round_no: number
  status: AutomationRunStatus
  phase: string
  upload_execution_id: number | null
  openlist_execution_id: number | null
  new_file_count: number
  pending_file_count: number
  checked_file_count: number
  skipped_file_count: number
  wait_seconds: number
  idle_wait_seconds: number
  missed_files: string[]
  error_code: string | null
  error_message: string | null
  log_path: string | null
  started_time: string | null
  finished_time: string | null
  created_time: string | null
  upload: AutomationExecutionBrief | null
  openlist: AutomationExecutionBrief | null
}

/** 运行记录关联的 A/B 执行摘要。 */
export interface AutomationExecutionBrief {
  id: number
  status: string
  error_code: string | null
  error_message: string | null
  started_time: string | null
  finished_time: string | null
  log_path: string | null
  file_total?: number
  file_success?: number
  file_skipped?: number
  file_failed?: number
}

/** 运行中的自动化任务（进程内运行态快照）。 */
export interface AutomationActiveTask {
  task_id: number
  task_name: string | null
  phase: string | null
  run_id: number | null
  round_no: number | null
  next_round_at: string | null
  log_path: string | null
  started_time: string | null
}

/** 执行管理页的执行参数：写入所选任务配置并持续生效，留空沿用任务当前值。 */
export interface AutomationStartPayload {
  wait_interval_seconds?: number
  openlist_wait_timeout?: number
  idle_wait_timeout?: number
  stage_timeout?: number
  interval_seconds?: number
}

export interface AutomationBatchStartItem {
  task_id: number
  ok: boolean
  message: string
}

export interface AutomationRunLogLine {
  index: number
  level: string
  message: string
}

export interface AutomationRunLogResult {
  total: number
  lines: AutomationRunLogLine[]
}

/** 自动化任务 WS 帧：日志 / 进度 / 状态 / 异常通知。 */
export type AutomationWsFrame =
  | { type: 'log'; level: string; message: string; ts: string }
  | { type: 'progress'; data: Record<string, unknown> }
  | {
      type: 'status'
      status?: string
      run_id?: number
      round_no?: number
      phase?: string
      pending?: number
      checked?: number
      missed?: number
    }
  | { type: 'alert'; status?: string; message: string; task_id?: number }
