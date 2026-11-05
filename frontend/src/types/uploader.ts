/** 上传管理（123 云盘）相关类型。 */

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

/** 重命名规则：`{season}`/`{episode}`/`{ext}` 模板。 */
export interface UploadRenameRule {
  id: number
  name: string
  template: string
  created_time: string | null
  updated_time: string | null
}

export interface UploadRenameRuleCreate {
  name: string
  template: string
}

export type UploadRenameRuleUpdate = Partial<UploadRenameRuleCreate>

/** 重命名预览请求/结果。 */
export interface UploadRenamePreviewRequest {
  filename: string
  season: number
  start_episode: number
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

