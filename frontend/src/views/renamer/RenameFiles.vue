<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Document, Film, FolderOpened, Refresh, Search, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { renamerApi } from '@/api/renamer'
import { useLogDir } from '@/composables/useLogDir'
import type {
  RenameConflictMode,
  RenameEntryPayload,
  RenameFileItem,
  RenameFileResult,
  RenameLogEntry,
  RenameResultStatus,
  RenameScanResult,
  RenameSeason,
  RenameShow
} from '@/types/renamer'

type SplitFormat = 'season' | 's' | 'cn'

interface SplitConfig {
  counts: string
  format: SplitFormat
  move: boolean
}

interface SplitAssignment {
  counts: number[]
  format: SplitFormat
  move: boolean
}

interface PlanRow {
  key: string
  file: RenameFileItem
  target: string
  edited: boolean
  tags: Array<{ text: string; type: '' | 'success' | 'info' | 'warning' | 'danger' }>
}

interface DesktopBridge {
  api?: {
    pick_directory?: (startDir?: string) => Promise<string | null>
  }
}

const rootPath = ref('')
const scanning = ref(false)
const scan = ref<RenameScanResult | null>(null)

const keepLang = ref(true)
const autoNumber = ref(false)
const conflictMode = ref<RenameConflictMode>('skip')

const selected = reactive<Record<string, boolean>>({})
const edited = reactive<Record<string, string>>({})
const renumberSeasons = reactive<Record<string, boolean>>({})
const splitCfg = reactive<Record<string, SplitConfig>>({})
const appliedSplit = reactive<Record<string, SplitAssignment>>({})

const executing = ref(false)
const progressVisible = ref(false)
const progress = reactive({ done: 0, total: 0, renamed: 0, skipped: 0, failed: 0 })
const abortRequested = ref(false)

const results = ref<RenameFileResult[]>([])
const resultVisible = ref(false)
const rescanning = ref(false)

const logVisible = ref(false)
const logsLoading = ref(false)
const logs = ref<RenameLogEntry[]>([])
const { open: openLogFolder } = useLogDir('rename')

const chunkSize = 20

// ---------------------------------------------------------------- 工具函数

function pad2(value: number): string {
  return String(value).padStart(2, '0')
}

function fileKey(item: RenameFileItem): string {
  return `${item.folder}\u0000${item.name}`
}

function seasonKey(show: RenameShow, season: RenameSeason): string {
  return `${show.path}\u0000${season.folder_name ?? ''}`
}

function splitCfgFor(key: string): SplitConfig {
  if (!splitCfg[key]) {
    splitCfg[key] = { counts: '', format: 'season', move: false }
  }
  return splitCfg[key]
}

function formatSeasonFolder(season: number, format: SplitFormat): string {
  if (format === 's') return `S${pad2(season)}`
  if (format === 'cn') return `第${season}季`
  return `Season ${pad2(season)}`
}

function buildTarget(show: RenameShow, season: RenameSeason, item: RenameFileItem, index: number): string {
  const lang = keepLang.value && item.lang_tag ? `.${item.lang_tag}` : ''
  const split = appliedSplit[seasonKey(show, season)]
  if (split) {
    let offset = 0
    for (let i = 0; i < split.counts.length; i += 1) {
      const count = split.counts[i]
      if (index < offset + count) {
        const episode = index - offset + 1
        return `S${pad2(i + 1)}E${pad2(episode)}${lang}${item.ext}`
      }
      offset += count
    }
  }
  let episode: number | null = item.episode
  if (renumberSeasons[seasonKey(show, season)]) {
    episode = item.renumber
  } else if (episode === null) {
    episode = item.auto_number ?? 1
  }
  return `S${pad2(season.season)}E${pad2(episode ?? 1)}${lang}${item.ext}`
}

function splitMoveTarget(show: RenameShow, season: RenameSeason, index: number): string | undefined {
  const split = appliedSplit[seasonKey(show, season)]
  if (!split || !split.move) return undefined
  let offset = 0
  for (let i = 0; i < split.counts.length; i += 1) {
    const count = split.counts[i]
    if (index < offset + count) {
      return `${show.path}/${formatSeasonFolder(i + 1, split.format)}`
    }
    offset += count
  }
  return undefined
}

function splitLabel(show: RenameShow, season: RenameSeason, index: number): string | null {
  const split = appliedSplit[seasonKey(show, season)]
  if (!split) return null
  let offset = 0
  for (let i = 0; i < split.counts.length; i += 1) {
    const count = split.counts[i]
    if (index < offset + count) {
      return `第 ${i + 1} 季 · E${index - offset + 1}`
    }
    offset += count
  }
  return null
}

function defaultChecked(item: RenameFileItem): boolean {
  if (item.half) return false
  if (item.episode !== null) return item.status !== 'noop'
  return autoNumber.value && item.auto_number !== null
}

// ---------------------------------------------------------------- 选择与编辑

function resetSelection(): void {
  for (const key of Object.keys(selected)) delete selected[key]
  const current = scan.value
  if (!current) return
  for (const show of current.shows) {
    for (const season of show.seasons) {
      for (const item of season.files) {
        selected[fileKey(item)] = defaultChecked(item)
      }
    }
  }
}

function clearEdits(): void {
  for (const key of Object.keys(edited)) delete edited[key]
}

function onOptionChanged(): void {
  clearEdits()
  resetSelection()
}

watch([keepLang, autoNumber], onOptionChanged)

function isChecked(item: RenameFileItem): boolean {
  return selected[fileKey(item)] === true
}

function toggleChecked(item: RenameFileItem): void {
  selected[fileKey(item)] = !isChecked(item)
}

function seasonCheckedCount(_show: RenameShow, season: RenameSeason): number {
  return season.files.filter(item => isChecked(item)).length
}

function seasonAllChecked(_show: RenameShow, season: RenameSeason): boolean {
  return season.files.length > 0 && seasonCheckedCount(_show, season) === season.files.length
}

function seasonIndeterminate(_show: RenameShow, season: RenameSeason): boolean {
  const count = seasonCheckedCount(_show, season)
  return count > 0 && count < season.files.length
}

function onSeasonCheckChange(show: RenameShow, season: RenameSeason, value: unknown): void {
  toggleSeason(show, season, Boolean(value))
}

function onRenumberChange(show: RenameShow, season: RenameSeason, value: unknown): void {
  toggleRenumber(show, season, Boolean(value))
}

function onTargetInput(key: string, value: unknown): void {
  setTarget(key, String(value ?? ''))
}

function toggleSeason(_show: RenameShow, season: RenameSeason, value: boolean): void {
  for (const item of season.files) selected[fileKey(item)] = value
}

// ---------------------------------------------------------------- 拆分季

function appliedSplitFor(show: RenameShow, season: RenameSeason): SplitAssignment | undefined {
  return appliedSplit[seasonKey(show, season)]
}

function applySplit(show: RenameShow, season: RenameSeason): void {
  const cfg = splitCfgFor(seasonKey(show, season))
  const parts = cfg.counts
    .split(/[,，\s]+/)
    .map(part => part.trim())
    .filter(Boolean)
    .map(part => Number(part))
  if (!parts.length || parts.some(part => !Number.isInteger(part) || part <= 0)) {
    ElMessage.warning('请输入合法的每季集数，例如 3,2,1')
    return
  }
  const total = parts.reduce((sum, part) => sum + part, 0)
  if (total !== season.files.length) {
    ElMessage.warning(`每季集数合计（${total}）需等于该文件夹文件数（${season.files.length}）`)
    return
  }
  appliedSplit[seasonKey(show, season)] = { counts: parts, format: cfg.format, move: cfg.move }
  clearEdits()
  ElMessage.success(`已按 ${parts.length} 季拆分预览`)
}

function clearSplit(show: RenameShow, season: RenameSeason): void {
  delete appliedSplit[seasonKey(show, season)]
  clearEdits()
}

function toggleRenumber(show: RenameShow, season: RenameSeason, value: boolean): void {
  if (value) delete appliedSplit[seasonKey(show, season)]
  renumberSeasons[seasonKey(show, season)] = value
  clearEdits()
}

// ---------------------------------------------------------------- 扫描

async function pickFolder(): Promise<void> {
  const bridge = (window as unknown as { pywebview?: DesktopBridge }).pywebview
  if (!bridge?.api?.pick_directory) {
    ElMessage.warning('目录快速选择仅在桌面版可用，请手动输入文件夹路径')
    return
  }
  const picked = await bridge.api.pick_directory(rootPath.value.trim() || undefined)
  if (picked) {
    rootPath.value = picked
    void runScan()
  }
}

async function runScan(): Promise<void> {
  const path = rootPath.value.trim()
  if (!path) {
    ElMessage.warning('请输入文件夹路径')
    return
  }
  scanning.value = true
  try {
    const res = await renamerApi.scan(path)
    scan.value = res.data
    for (const key of Object.keys(renumberSeasons)) delete renumberSeasons[key]
    for (const key of Object.keys(appliedSplit)) delete appliedSplit[key]
    for (const key of Object.keys(splitCfg)) delete splitCfg[key]
    clearEdits()
    resetSelection()
  } finally {
    scanning.value = false
  }
}

/** 重命名完成后静默重扫，刷新磁盘上的最新文件名。 */
async function rescanSilently(): Promise<void> {
  if (!scan.value) return
  rescanning.value = true
  try {
    const res = await renamerApi.scan(scan.value.root)
    scan.value = res.data
    for (const key of Object.keys(renumberSeasons)) delete renumberSeasons[key]
    for (const key of Object.keys(appliedSplit)) delete appliedSplit[key]
    clearEdits()
    resetSelection()
  } catch {
    /* 失败提示由请求拦截器统一处理 */
  } finally {
    rescanning.value = false
  }
}

// ---------------------------------------------------------------- 预览行

const allRows = computed<Array<{ show: RenameShow; season: RenameSeason; index: number; row: PlanRow }>>(() => {
  const current = scan.value
  if (!current) return []
  const result: Array<{ show: RenameShow; season: RenameSeason; index: number; row: PlanRow }> = []
  for (const show of current.shows) {
    for (const season of show.seasons) {
      season.files.forEach((file, index) => {
        const key = fileKey(file)
        const target = edited[key] ?? buildTarget(show, season, file, index)
        result.push({ show, season, index, row: { key, file, target, edited: edited[key] !== undefined, tags: [] } })
      })
    }
  }
  return result
})

const checkedRows = computed(() => allRows.value.filter(entry => selected[entry.row.key] === true))

const checkedCount = computed(() => checkedRows.value.length)
const totalCount = computed(() => allRows.value.length)

/** 选中行中「目标文件夹 + 目标名」重复的键集合（用于提示与执行前校验）。 */
const duplicateKeys = computed<Set<string>>(() => {
  const seen = new Map<string, number>()
  for (const entry of checkedRows.value) {
    const folder = splitMoveTarget(entry.show, entry.season, entry.index) ?? entry.row.file.folder
    const key = `${folder}\u0000${entry.row.target.toLowerCase()}`
    seen.set(key, (seen.get(key) ?? 0) + 1)
  }
  return new Set(Array.from(seen.entries()).filter(([, count]) => count > 1).map(([key]) => key))
})

function fileTags(show: RenameShow, season: RenameSeason, item: RenameFileItem, index: number): PlanRow['tags'] {
  const tags: PlanRow['tags'] = []
  if (item.half) tags.push({ text: '特殊集数 .5：需手动输入目标名', type: 'danger' })
  if (item.episode === null) {
    tags.push({
      text: item.auto_number === null ? '无法识别集数' : `无法识别 · 自动编号 E${pad2(item.auto_number)}`,
      type: 'danger'
    })
  }
  if (item.lang_tag) tags.push({ text: item.lang_tag, type: 'success' })
  const split = splitLabel(show, season, index)
  if (split) tags.push({ text: `分季 ${split}`, type: '' })
  if (renumberSeasons[seasonKey(show, season)]) tags.push({ text: `从头编号 E${pad2(item.renumber)}`, type: '' })
  if (item.status === 'noop') tags.push({ text: '已是目标名称', type: 'info' })
  if (item.status === 'caseonly') tags.push({ text: '仅大小写调整', type: 'info' })
  if (item.status === 'duplicate' || item.status === 'chain' || item.status === 'exists') {
    tags.push({ text: `目标已存在${item.conflict_with ? `（${item.conflict_with}）` : ''}`, type: 'warning' })
  }
  if (edited[fileKey(item)] !== undefined) tags.push({ text: '已修改', type: 'warning' })
  const folder = splitMoveTarget(show, season, index) ?? item.folder
  const target = edited[fileKey(item)] ?? buildTarget(show, season, item, index)
  if (duplicateKeys.value.has(`${folder}\u0000${target.toLowerCase()}`)) {
    tags.push({ text: '目标重名', type: 'warning' })
  }
  return tags
}

function seasonRows(show: RenameShow, season: RenameSeason): PlanRow[] {
  return season.files.map((file, index) => {
    const key = fileKey(file)
    return {
      key,
      file,
      target: edited[key] ?? buildTarget(show, season, file, index),
      edited: edited[key] !== undefined,
      tags: fileTags(show, season, file, index)
    }
  })
}

function setTarget(key: string, value: string): void {
  edited[key] = value
}

function resetTarget(key: string): void {
  delete edited[key]
}

// ---------------------------------------------------------------- 执行

function validate(): string | null {
  const rows = checkedRows.value
  if (!rows.length) return '请先勾选需要重命名的文件'
  for (const entry of rows) {
    if (entry.row.file.half && edited[entry.row.key] === undefined) {
      return `「${entry.row.file.name}」是 .5 特殊集，请先手动输入目标文件名`
    }
    if (!entry.row.target.trim()) {
      return `「${entry.row.file.name}」的目标文件名为空`
    }
  }
  if (duplicateKeys.value.size > 0) {
    return '存在目标重名的文件，请调整目标名或冲突处理方式'
  }
  return null
}

async function execute(): Promise<void> {
  const message = validate()
  if (message) {
    ElMessage.warning(message)
    return
  }
  if (conflictMode.value === 'overwrite') {
    try {
      await ElMessageBox.confirm(
        '目标文件已存在时将直接覆盖（删除原目标文件），该操作不可撤销，是否继续？',
        '覆盖确认',
        { type: 'warning', confirmButtonText: '继续重命名', cancelButtonText: '取消' }
      )
    } catch {
      return
    }
  }
  const rows = checkedRows.value
  const entries: RenameEntryPayload[] = rows.map(entry => {
    const payload: RenameEntryPayload = {
      folder: entry.row.file.folder,
      name: entry.row.file.name,
      new_name: entry.row.target
    }
    const targetFolder = splitMoveTarget(entry.show, entry.season, entry.index)
    if (targetFolder) payload.target_folder = targetFolder
    return payload
  })

  progress.done = 0
  progress.total = entries.length
  progress.renamed = 0
  progress.skipped = 0
  progress.failed = 0
  results.value = []
  abortRequested.value = false
  executing.value = true
  progressVisible.value = true
  try {
    for (let start = 0; start < entries.length; start += chunkSize) {
      if (abortRequested.value) break
      const chunk = entries.slice(start, start + chunkSize)
      const res = await renamerApi.rename({
        root: scan.value?.root ?? rootPath.value.trim(),
        entries: chunk,
        conflict_mode: conflictMode.value,
        keep_lang: keepLang.value
      })
      results.value.push(...res.data.results)
      for (const item of res.data.results) {
        if (item.status === 'renamed') progress.renamed += 1
        else if (item.status === 'skipped') progress.skipped += 1
        else progress.failed += 1
      }
      progress.done += chunk.length
    }
    resultVisible.value = true
  } finally {
    executing.value = false
    progressVisible.value = false
  }
  const renamed = progress.renamed
  if (renamed > 0) {
    await rescanSilently()
    ElMessage.success(`已重命名 ${renamed} 个文件`)
  }
  void loadLogs()
}

// ---------------------------------------------------------------- 日志

async function loadLogs(): Promise<void> {
  logsLoading.value = true
  try {
    const res = await renamerApi.logs(200)
    logs.value = res.data.logs
  } finally {
    logsLoading.value = false
  }
}

function openLogs(): void {
  logVisible.value = true
  void loadLogs()
}

const resultSummary = computed(() => {
  const groups = { renamed: 0, skipped: 0, failed: 0 }
  for (const item of results.value) groups[item.status] += 1
  return groups
})

const problemResults = computed(() => results.value.filter(item => item.status !== 'renamed'))

function statusText(status: RenameResultStatus): string {
  if (status === 'renamed') return '已重命名'
  if (status === 'skipped') return '已跳过'
  return '失败'
}

function statusTagType(status: RenameResultStatus): '' | 'success' | 'info' | 'danger' {
  if (status === 'renamed') return 'success'
  if (status === 'skipped') return 'info'
  return 'danger'
}
</script>

<template>
  <div class="page renamer">
    <el-card shadow="never" class="renamer__card">
      <div class="card-header">
        <div class="card-header__left">
          <span class="card-title">选择文件夹</span>
          <span class="card-sub">支持一级结构（剧集文件夹内直接放视频）与二级结构（剧集文件夹 + 季文件夹）</span>
        </div>
        <div class="card-header__actions">
          <el-button text :icon="View" @click="openLogs">操作日志</el-button>
        </div>
      </div>
      <div class="path-row">
        <el-input
          v-model="rootPath"
          placeholder="输入本机文件夹完整路径，例如 D:\Media\某剧"
          clearable
          @keyup.enter="runScan"
        />
        <el-button :icon="FolderOpened" @click="pickFolder">浏览…</el-button>
        <el-button type="primary" :icon="Search" :loading="scanning" @click="runScan">扫描</el-button>
      </div>
      <div v-if="scan" class="summary">
        <div class="summary__chips">
          <el-tag effect="light" size="small" type="info">{{ scan.stats.shows }} 个剧集</el-tag>
          <el-tag effect="light" size="small" type="info">{{ scan.stats.seasons }} 个季</el-tag>
          <el-tag effect="light" size="small" type="info">{{ scan.stats.files }} 个文件</el-tag>
          <el-tag v-if="scan.stats.unrecognized" effect="light" size="small" type="danger">
            {{ scan.stats.unrecognized }} 个无法识别集数
          </el-tag>
          <el-tag v-if="scan.stats.conflicts" effect="light" size="small" type="warning">
            {{ scan.stats.conflicts }} 个目标冲突
          </el-tag>
          <el-tag v-if="scan.stats.noop" effect="light" size="small" type="success">
            {{ scan.stats.noop }} 个已符合命名
          </el-tag>
          <el-tag v-if="scan.stats.half_episodes" effect="light" size="small" type="danger">
            {{ scan.stats.half_episodes }} 个 .5 特殊集
          </el-tag>
        </div>
        <div class="summary__path nums">{{ scan.root }}</div>
        <ul v-if="scan.warnings.length" class="warning-list">
          <li v-for="(warning, index) in scan.warnings" :key="index">{{ warning }}</li>
        </ul>
      </div>
    </el-card>

    <el-card
      v-for="show in scan?.shows ?? []"
      :key="show.path"
      shadow="never"
      class="renamer__card show-card"
    >
      <div class="card-header">
        <div class="card-header__left">
          <span class="card-title">{{ show.name }}</span>
          <el-tag v-if="show.level === 2" size="small" effect="light" type="info">二级结构</el-tag>
          <el-tag v-else-if="show.level === 1" size="small" effect="light" type="success">一级结构</el-tag>
          <el-tag v-else size="small" effect="light" type="danger">无法识别结构</el-tag>
        </div>
        <div class="card-header__actions">
          <span class="muted nums">{{ show.path }}</span>
        </div>
      </div>
      <ul v-if="show.warnings.length" class="warning-list">
        <li v-for="(warning, index) in show.warnings" :key="index">{{ warning }}</li>
      </ul>

      <div v-for="season in show.seasons" :key="season.folder_path" class="season">
        <div class="season__head">
          <div class="season__title">
            <span class="season__label">S{{ String(season.season).padStart(2, '0') }}</span>
            <span class="muted nums">{{ season.folder_name ?? '根目录' }}</span>
            <span class="muted nums">{{ season.files.length }} 个文件</span>
          </div>
          <div class="season__actions">
            <el-checkbox
              v-if="season.files.length"
              :model-value="seasonAllChecked(show, season)"
              :indeterminate="seasonIndeterminate(show, season)"
              @change="onSeasonCheckChange(show, season, $event)"
            >
              全选
            </el-checkbox>
            <el-switch
              :model-value="renumberSeasons[seasonKey(show, season)] === true"
              active-text="从头开始"
              @change="onRenumberChange(show, season, $event)"
            />
          </div>
        </div>

        <ul v-if="season.warnings.length" class="warning-list">
          <li v-for="(warning, index) in season.warnings" :key="index">{{ warning }}</li>
        </ul>

        <div v-if="show.level === 1 && season.files.length > 1" class="split">
          <div class="split__row">
            <span class="split__title">按集数拆分季</span>
            <el-input
              v-model="splitCfgFor(seasonKey(show, season)).counts"
              size="small"
              class="split__counts"
              placeholder="每季集数，如 3,2,1（合计需等于文件数）"
            />
            <el-select v-model="splitCfgFor(seasonKey(show, season)).format" size="small" class="split__format">
              <el-option label="Season 01" value="season" />
              <el-option label="S01" value="s" />
              <el-option label="第1季" value="cn" />
            </el-select>
            <el-checkbox v-model="splitCfgFor(seasonKey(show, season)).move">移动文件</el-checkbox>
            <el-button size="small" @click="applySplit(show, season)">应用</el-button>
            <el-button v-if="appliedSplitFor(show, season)" size="small" text @click="clearSplit(show, season)">
              清除拆分
            </el-button>
          </div>
          <div v-if="appliedSplitFor(show, season)" class="split__hint">
            已拆分为 {{ appliedSplitFor(show, season)?.counts?.length }} 季，
            目标文件夹：{{ appliedSplitFor(show, season)?.format === 's' ? 'S01 / S02 …' : appliedSplitFor(show, season)?.format === 'cn' ? '第1季 / 第2季 …' : 'Season 01 / Season 02 …' }}
          </div>
        </div>

        <el-table v-if="season.files.length" :data="seasonRows(show, season)" row-key="key" size="small" class="rows">
          <el-table-column width="48" align="center">
            <template #default="{ row }">
              <el-checkbox :model-value="isChecked(row.file)" @change="toggleChecked(row.file)" />
            </template>
          </el-table-column>
          <el-table-column label="原文件名" min-width="260">
            <template #default="{ row }">
              <div class="file-cell">
                <el-icon class="file-cell__icon">
                  <Film v-if="row.file.kind === 'video'" />
                  <Document v-else />
                </el-icon>
                <span class="file-cell__name" :title="row.file.name">{{ row.file.name }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="目标文件名" min-width="260">
            <template #default="{ row }">
              <div class="target-cell">
                <el-input
                  :model-value="row.target"
                  size="small"
                  :class="{ 'target-cell__input--edited': row.edited }"
                  @update:model-value="onTargetInput(row.key, $event)"
                />
                <el-button v-if="row.edited" text size="small" :icon="Refresh" @click="resetTarget(row.key)" />
              </div>
            </template>
          </el-table-column>
          <el-table-column label="状态" min-width="240">
            <template #default="{ row }">
              <div class="tags">
                <el-tag
                  v-for="(tag, index) in fileTags(show, season, row.file, season.files.indexOf(row.file))"
                  :key="index"
                  :type="tag.type"
                  effect="light"
                  size="small"
                >
                  {{ tag.text }}
                </el-tag>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <el-card v-if="totalCount" shadow="never" class="renamer__card actions-card">
      <div class="actions">
        <div class="actions__left">
          <span class="nums">已勾选 {{ checkedCount }} / {{ totalCount }}</span>
          <el-select v-model="conflictMode" size="small" class="actions__mode">
            <el-option label="冲突时跳过" value="skip" />
            <el-option label="冲突时自动编号" value="autonum" />
            <el-option label="冲突时覆盖" value="overwrite" />
          </el-select>
          <el-checkbox v-model="keepLang">保留语言标记</el-checkbox>
          <el-checkbox v-model="autoNumber">无法识别集数时自动编号</el-checkbox>
        </div>
        <div class="actions__right">
          <el-button :icon="Refresh" :loading="rescanning" @click="rescanSilently">重新扫描</el-button>
          <el-button type="primary" :loading="executing" :disabled="!checkedCount" @click="execute">
            开始重命名
          </el-button>
        </div>
      </div>
    </el-card>

    <el-card v-if="scan && totalCount === 0" shadow="never" class="renamer__card">
      <div class="empty">
        未发现视频/字幕文件或季文件夹。请确认路径下是剧集文件夹（一级或二级结构）后重新扫描。
      </div>
    </el-card>

    <el-dialog
      v-model="progressVisible"
      title="正在重命名"
      width="460px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="false"
    >
      <el-progress
        :percentage="progress.total ? Math.round((progress.done / progress.total) * 100) : 0"
        :stroke-width="10"
      />
      <div class="progress-meta nums">
        已处理 {{ progress.done }} / {{ progress.total }} · 成功 {{ progress.renamed }} · 跳过 {{ progress.skipped }} · 失败 {{ progress.failed }}
      </div>
      <template #footer>
        <el-button :disabled="abortRequested" @click="abortRequested = true">停止后续批次</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="resultVisible" title="重命名结果" width="620px">
      <div class="result-summary nums">
        成功 {{ resultSummary.renamed }} · 跳过 {{ resultSummary.skipped }} · 失败 {{ resultSummary.failed }}
      </div>
      <el-table v-if="problemResults.length" :data="problemResults" size="small" max-height="320">
        <el-table-column prop="name" label="原文件名" min-width="200" show-overflow-tooltip />
        <el-table-column prop="new_name" label="目标文件名" min-width="200" show-overflow-tooltip />
        <el-table-column label="状态" width="96">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" effect="light" size="small">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="原因" min-width="200">
          <template #default="{ row }">{{ row.reason || row.note || '' }}</template>
        </el-table-column>
      </el-table>
      <div v-else class="result-summary result-summary--ok">全部文件已按目标名称重命名完成。</div>
      <template #footer>
        <el-button @click="resultVisible = false">关闭</el-button>
        <el-button type="primary" @click="resultVisible = false; rescanSilently()">重新扫描</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="logVisible" title="操作日志" size="520px">
      <div class="logs">
        <div class="logs__toolbar">
          <el-button size="small" :icon="FolderOpened" @click="openLogFolder">打开日志文件夹</el-button>
          <el-button size="small" :icon="Refresh" :loading="logsLoading" @click="loadLogs">刷新</el-button>
        </div>
        <el-empty v-if="!logs.length && !logsLoading" description="暂无操作日志" :image-size="80" />
        <div v-for="(entry, index) in logs" :key="index" class="log-item" :class="`log-item--${entry.level}`">
          <div class="log-item__head nums">
            <span>{{ entry.ts }}</span>
            <span class="log-item__level">{{ entry.level }}</span>
          </div>
          <div class="log-item__message">{{ entry.message }}</div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped lang="scss">
.renamer {
  display: flex;
  flex-direction: column;
  gap: var(--up-strm-space-4);

  &__card {
    margin: 0;
  }
}

.card-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--up-strm-space-2);
  margin-bottom: var(--up-strm-space-3);

  &__left {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--up-strm-space-2);
  }

  &__actions {
    display: flex;
    align-items: center;
    gap: var(--up-strm-space-2);
    margin-left: auto;
  }
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.card-sub,
.muted {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.path-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--up-strm-space-2);

  .el-input {
    flex: 1;
    min-width: 260px;
  }
}

.summary {
  display: flex;
  flex-direction: column;
  gap: var(--up-strm-space-2);
  margin-top: var(--up-strm-space-3);

  &__chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--up-strm-space-2);
  }

  &__path {
    font-size: 12px;
    color: var(--el-text-color-secondary);
    word-break: break-all;
  }
}

.warning-list {
  margin: var(--up-strm-space-2) 0 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.show-card .season {
  margin-top: var(--up-strm-space-4);

  &__head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--up-strm-space-2);
    padding-bottom: var(--up-strm-space-2);
    border-bottom: 1px solid var(--el-border-color-lighter);
    margin-bottom: var(--up-strm-space-2);
  }

  &__title {
    display: flex;
    align-items: center;
    gap: var(--up-strm-space-2);
  }

  &__label {
    font-weight: 600;
    color: var(--el-text-color-primary);
  }

  &__actions {
    display: flex;
    align-items: center;
    gap: var(--up-strm-space-3);
  }
}

.split {
  display: flex;
  flex-direction: column;
  gap: var(--up-strm-space-2);
  padding: var(--up-strm-space-2) var(--up-strm-space-3);
  margin-bottom: var(--up-strm-space-2);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);

  &__row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--up-strm-space-2);
  }

  &__title {
    font-size: 12px;
    font-weight: 600;
    color: var(--el-text-color-regular);
  }

  &__counts {
    width: 260px;
  }

  &__format {
    width: 120px;
  }

  &__hint {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }
}

.rows :deep(.el-table__cell) {
  vertical-align: middle;
}

.file-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;

  &__icon {
    color: var(--el-text-color-secondary);
    flex: none;
  }

  &__name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.target-cell {
  display: flex;
  align-items: center;
  gap: 4px;

  &__input--edited :deep(.el-input__wrapper) {
    box-shadow: 0 0 0 1px var(--el-color-warning) inset;
  }
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.actions-card :deep(.el-card__body) {
  padding-top: var(--up-strm-space-3);
  padding-bottom: var(--up-strm-space-3);
}

.actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--up-strm-space-3);

  &__left,
  &__right {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--up-strm-space-3);
  }

  &__mode {
    width: 150px;
  }
}

.empty {
  padding: var(--up-strm-space-6) 0;
  text-align: center;
  color: var(--el-text-color-secondary);
}

.progress-meta,
.result-summary {
  margin-top: var(--up-strm-space-3);
  font-size: 13px;
  color: var(--el-text-color-regular);

  &--ok {
    color: var(--el-color-success);
  }
}

.logs {
  display: flex;
  flex-direction: column;
  gap: var(--up-strm-space-3);

  &__toolbar {
    display: flex;
    gap: var(--up-strm-space-2);
  }
}

.log-item {
  padding: var(--up-strm-space-2) var(--up-strm-space-3);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
  border-left: 3px solid var(--el-border-color);

  &--warn {
    border-left-color: var(--el-color-warning);
  }

  &--error {
    border-left-color: var(--el-color-danger);
  }

  &__head {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  &__level {
    text-transform: uppercase;
  }

  &__message {
    margin-top: 2px;
    font-size: 13px;
    color: var(--el-text-color-primary);
  }
}
</style>
