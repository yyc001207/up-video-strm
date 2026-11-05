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
