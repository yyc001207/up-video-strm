/** 本地改名：扫描结果与重命名结果类型。 */

export type RenameFileKind = 'video' | 'sub'
export type RenameFileStatus = 'ok' | 'noop' | 'caseonly' | 'chain' | 'exists' | 'duplicate'

export interface RenameFileItem {
  name: string
  folder: string
  season: number
  ext: string
  kind: RenameFileKind
  episode: number | null
  auto_number: number | null
  lang_tag: string | null
  half: boolean
  renumber: number
  new_name: string
  status: RenameFileStatus
  conflict_with: string | null
}

export interface RenameSeason {
  season: number
  folder_name: string | null
  folder_path: string
  files: RenameFileItem[]
  warnings: string[]
}

export interface RenameShow {
  name: string
  path: string
  level: number
  seasons: RenameSeason[]
  warnings: string[]
}

export interface RenameStats {
  shows: number
  seasons: number
  files: number
  unrecognized: number
  conflicts: number
  noop: number
  half_episodes: number
}

export interface RenameScanResult {
  root: string
  root_name: string
  shows: RenameShow[]
  warnings: string[]
  stats: RenameStats
}

export type RenameConflictMode = 'skip' | 'overwrite' | 'autonum'

export interface RenameEntryPayload {
  folder: string
  name: string
  new_name?: string
  target_folder?: string
}

export type RenameResultStatus = 'renamed' | 'skipped' | 'failed'

export interface RenameFileResult {
  name: string
  new_name: string
  status: RenameResultStatus
  reason?: string
  note?: string
}

export interface RenameLogEntry {
  ts: string
  level: string
  message: string
  detail?: Record<string, unknown> | null
}
