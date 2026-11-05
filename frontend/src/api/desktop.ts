/** 桌面版设置接口：开机自启 / 托盘偏好 / 数据目录。 */

import request from './index'
import type { ApiRes, DesktopInfo } from '@/types/desktop'

export const desktopApi = {
  getInfo(): Promise<ApiRes<DesktopInfo>> {
    return request.get('/desktop/info')
  },
  setAutostart(enabled: boolean): Promise<ApiRes<DesktopInfo>> {
    return request.post('/desktop/autostart', { enabled })
  },
  savePreferences(data: { start_minimized?: boolean; close_to_tray?: boolean }): Promise<ApiRes<DesktopInfo>> {
    return request.post('/desktop/preferences', data)
  },
  openDataDir(): Promise<ApiRes<{ path: string }>> {
    return request.post('/desktop/open-data-dir')
  },
  /** 在资源管理器中打开日志保存目录（kind：openlist 任务调度 / upload 上传管理）。 */
  openLogDir(kind: 'openlist' | 'upload'): Promise<ApiRes<{ path: string }>> {
    return request.post('/desktop/open-log-dir', { kind })
  },
  /** Win11 默认折叠托盘图标，调用后写入「始终显示」注册表项。 */
  fixTray(): Promise<ApiRes<{ promoted: boolean }>> {
    return request.post('/desktop/fix-tray')
  },
  /** 打开系统任务栏设置（手动开启托盘图标显示）。 */
  openTaskbarSettings(): Promise<ApiRes<{ opened: boolean }>> {
    return request.post('/desktop/open-taskbar-settings')
  }
}
