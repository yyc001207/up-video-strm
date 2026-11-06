/** 云盘上传（123 云盘）相关类型。 */

/** 123 云盘开放平台凭据与 Token 状态。 */
export interface UploadPlatformConfig {
  client_id: string
  /** 是否已保存 Client Secret（只回显脱敏值，不返回明文）。 */
  has_secret: boolean
  /** 脱敏后的密钥，如 `****3456`。 */
  secret_masked: string
  token_status: 'none' | 'valid' | 'expired'
  token_expires_at: string | null
  updated_time: string | null
}

export interface UploadPlatformConfigUpdate {
  client_id?: string
  /** 留空表示保持原密钥不变。 */
  client_secret?: string
}

export interface UploadTestConnectionRequest {
  client_id?: string
  client_secret?: string
}

/** 命名规则：`{season}`/`{episode}`/`{ext}` 模板；可附带自定义集数提取正则。 */
export interface UploadRenameRule {
  id: number
  name: string
  template: string
  /** 自定义集数提取正则（第 1 个分组为集号）；为空表示使用默认解析。 */
  episode_pattern: string | null
  created_time: string | null
  updated_time: string | null
}

export interface UploadRenameRuleCreate {
  name: string
  template: string
  /** 留空使用默认集数解析。 */
  episode_pattern?: string | null
}

export type UploadRenameRuleUpdate = Partial<UploadRenameRuleCreate>

/** 重命名预览请求/结果。 */
export interface UploadRenamePreviewRequest {
  filename: string
  season: number
  start_episode: number
  /** 留空时使用规则或默认集数解析。 */
  episode_pattern?: string | null
}

export interface UploadRenamePreviewResponse {
  matched: boolean
  reason?: string
  output_name?: string
  episode?: number
}

/** 上传任务。 */
export interface UploadTask {
  id: number
  name: string
  local_dir: string
  /** 云端目录绝对路径，如 `/test`。 */
  remote_dir: string
  season: number
  start_episode: number
  rename_rule_id: number | null
  rename_rule_name: string | null
  created_time: string | null
  updated_time: string | null
}

export interface UploadTaskCreate {
  name: string
  local_dir: string
  remote_dir: string
  season: number
  start_episode: number
  rename_rule_id?: number | null
}

export type UploadTaskUpdate = Partial<UploadTaskCreate>

/** 123 云盘目录项。 */
export interface UploadRemoteDirItem {
  file_id: number
  file_name: string
  is_dir: boolean
}

export interface UploadRemoteDirList {
  parent_id: number
  path: string
  items: UploadRemoteDirItem[]
}

// ---------------------------------------------------------------------------
// 执行与文件明细
// ---------------------------------------------------------------------------

/** 上传执行状态。 */
export type UploadExecutionStatus = 'running' | 'success' | 'fail' | 'cancelled'

/** 同名冲突策略：跳过 / 覆盖 / 追加后缀。 */
export type UploadConflictPolicy = 'skip' | 'overwrite' | 'suffix'

/** 上传执行记录（创建时固化任务参数，后续编辑任务不影响历史）。 */
export interface UploadExecution {
  id: number
  task_id: number
  task_name: string
  local_dir: string
  remote_dir: string
  season: number
  start_episode: number
  rename_rule_id: number | null
  template: string
  episode_pattern: string | null
  conflict_policy: UploadConflictPolicy
  concurrency: number
  retry_times: number
  dry_run: boolean
  status: UploadExecutionStatus
  file_total: number
  file_success: number
  file_skipped: number
  file_failed: number
  bytes_uploaded: number
  duration_seconds: number | null
  log_path: string | null
  started_time: string | null
  finished_time: string | null
  created_time: string | null
  error_code?: string | null
  error_message?: string | null
  /** 触发来源：manual 手动 / automation 自动追更触发 */
  trigger_source?: string | null
  trigger_ref?: string | null
  trigger_name?: string | null
}

/** 执行参数（批量创建时多任务共享）。 */
export interface UploadExecutionParams {
  conflict_policy: UploadConflictPolicy
  concurrency: number
  retry_times: number
  dry_run: boolean
}

export interface UploadExecutionCreate extends UploadExecutionParams {
  task_id: number
}

export interface UploadExecutionBatchCreate extends UploadExecutionParams {
  task_ids: number[]
}

/** 单个文件的处理明细。 */
export interface UploadFileRecord {
  id: number
  execution_id: number
  local_path: string
  remote_name: string
  size: number
  md5: string
  status: 'pending' | 'uploading' | 'success' | 'skipped' | 'failed'
  phase: string
  reason: string | null
  remote_file_id: number | null
  replaced_file_id: number | null
  created_time: string | null
  updated_time: string | null
}

/** 运行详情帧（与后端 WS 推送保持一致）。 */
export interface UploadWsLogFrame {
  type: 'log'
  level: string
  message: string
  ts?: string | null
}

export interface UploadWsProgressData {
  total: number
  success: number
  skipped: number
  failed: number
  bytesUploaded: number
  current?: string
}

export interface UploadWsProgressFrame {
  type: 'progress'
  data: UploadWsProgressData
}

export interface UploadWsStatusFrame {
  type: 'status'
  status: UploadExecutionStatus
  total?: number
  success?: number
  skipped?: number
  failed?: number
  bytes_uploaded?: number
}

export type UploadWsFrame = UploadWsLogFrame | UploadWsProgressFrame | UploadWsStatusFrame

/** 历史汇总：每个任务的最近一次执行与累计执行次数。 */
export interface UploadHistorySummaryItem {
  task_id: number
  task_name: string
  local_dir: string
  remote_dir: string
  season: number
  start_episode: number
  total_executions: number
  last_execution: UploadExecution | null
}



