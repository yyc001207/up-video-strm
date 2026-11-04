/** 桌面版设置相关类型（与后端 /api/desktop 字段保持一致）。 */

export interface ApiRes<T> {
  code: number
  msg: string
  data: T
}

export interface DesktopInfo {
  /** 是否为打包后的桌面版（Docker/源码调试为 false） */
  is_desktop: boolean
  version: string
  autostart_supported: boolean
  autostart: boolean
  start_minimized: boolean
  close_to_tray: boolean
  data_dir: string
  log_file: string
  exe_path: string
}
