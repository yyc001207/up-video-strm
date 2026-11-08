/** 本地改名接口封装（扫描、批量重命名与操作日志）。 */

import request from './index'
import type { Res } from '@/types/openlist'
import type {
  RenameConflictMode,
  RenameEntryPayload,
  RenameFileResult,
  RenameLogEntry,
  RenameScanResult
} from '@/types/renamer'

export const renamerApi = {
  scan: (path: string) => request.post<unknown, Res<RenameScanResult>>('/renamer/scan', { path }),
  rename: (data: {
    root: string
    entries: RenameEntryPayload[]
    conflict_mode: RenameConflictMode
    keep_lang: boolean
  }) => request.post<unknown, Res<{ results: RenameFileResult[] }>>('/renamer/rename', data),
  logs: (limit = 200) =>
    request.get<unknown, Res<{ logs: RenameLogEntry[] }>>('/renamer/logs', { params: { limit } })
}
