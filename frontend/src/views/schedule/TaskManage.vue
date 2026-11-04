<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, FolderAdd, Plus, Search } from '@element-plus/icons-vue'

import { openlistApi } from '@/api/openlist'
import { useOpenlistStore } from '@/stores/openlist'
import type { OpenListTask } from '@/types/openlist'
import DirTreePanel from './components/DirTreePanel.vue'

const store = useOpenlistStore()

const list = ref<OpenListTask[]>([])
const loading = ref(false)
const saving = ref(false)
const keyword = ref('')
const selectedIds = ref<number[]>([])

const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  name: '',
  output_dir: '',
  process_path: '',
  pause_count: null as number | null,
  pause_time: '' as string
})

/** 空状态文案：有搜索条件时区分「无匹配」与「无数据」。 */
const emptyDescription = computed(() =>
  keyword.value.trim() ? '没有匹配的任务配置' : '暂无任务配置'
)

async function load() {
  loading.value = true
  try {
    // 任务与全局配置并行加载：配置用于取服务器信息与前缀
    const [tasksRes] = await Promise.all([
      openlistApi.listTasks(keyword.value || undefined),
      store.fetchConfig()
    ])
    list.value = tasksRes.data.list
  } finally {
    loading.value = false
  }
}

async function handleSearch() {
  await load()
}

function handleSelectionChange(rows: OpenListTask[]) {
  selectedIds.value = rows.map(row => row.id)
}

function openCreate() {
  editingId.value = null
  form.name = ''
  form.output_dir = ''
  form.process_path = ''
  form.pause_count = null
  form.pause_time = ''
  dialogVisible.value = true
}

function openEdit(row: OpenListTask) {
  editingId.value = row.id
  form.name = row.name
  form.output_dir = row.output_dir
  form.process_path = row.process_path
  form.pause_count = row.pause_count
  form.pause_time = row.pause_time ?? ''
  dialogVisible.value = true
}

async function handleSave() {
  if (!form.name.trim() || !form.output_dir.trim() || !form.process_path.trim()) {
    ElMessage.warning('请填写任务名称、输出目录与处理路径')
    return
  }
  saving.value = true
  try {
    // 限流字段：留空表示使用全局配置（不提交 / 置 null）
    const payload = {
      name: form.name.trim(),
      output_dir: form.output_dir.trim(),
      process_path: form.process_path.trim(),
      ...(form.pause_count != null ? { pause_count: form.pause_count } : {}),
      ...(form.pause_time.trim() ? { pause_time: form.pause_time.trim() } : {})
    }
    if (editingId.value != null) {
      await openlistApi.updateTask(editingId.value, payload)
    } else {
      // 单服务器模式：后端自动绑定唯一服务器，前端不再传 server_id
      await openlistApi.createTask(payload)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await Promise.all([load(), store.fetchTasks()])
  } catch {
    /* 拦截器提示 */
  } finally {
    saving.value = false
  }
}

async function handleDelete(row: OpenListTask) {
  try {
    await ElMessageBox.confirm(`删除任务「${row.name}」？该操作不可恢复。`, '删除任务', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  await openlistApi.deleteTask(row.id)
  ElMessage.success('已删除')
  await Promise.all([load(), store.fetchTasks()])
}

async function handleBatchDelete() {
  const count = selectedIds.value.length
  if (count === 0) {
    ElMessage.warning('请先选择要删除的任务')
    return
  }
  try {
    await ElMessageBox.confirm(`删除选中的 ${count} 个任务？该操作不可恢复。`, '批量删除任务', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  try {
    await openlistApi.batchDeleteTasks(selectedIds.value)
    ElMessage.success(`已删除 ${count} 个任务`)
    selectedIds.value = []
    await Promise.all([load(), store.fetchTasks()])
  } catch {
    /* 拦截器提示 */
  }
}

async function handleCopy(row: OpenListTask) {
  // 复制：仅带入用户可编辑参数（排除 id 等系统自动生成字段），不立即新建
  editingId.value = null
  form.name = `${row.name} - 复制`
  form.output_dir = row.output_dir
  form.process_path = row.process_path
  form.pause_count = row.pause_count
  form.pause_time = row.pause_time ?? ''
  dialogVisible.value = true
}

// ---------- 快速添加（按目录批量生成任务配置） ----------

const quickDialogVisible = ref(false)
const quickParentDir = ref('')
const quickSelected = ref<string[]>([])
const quickCreating = ref(false)
const quickPauseCount = ref<number | null>(null)
const quickPauseTime = ref('')
// 快速新增父级目录子对话框
const quickParentDialogVisible = ref(false)
const quickParentSaving = ref(false)
const quickNewDirs = ref('')

// 单服务器模式：父级目录直接取全局唯一服务器的配置
const quickParentOptions = computed(() => store.server?.parent_dirs ?? [])

/** 任务名称：季文件夹（Season 01 / S01 / Season 1 等）→「上级文件夹名S季号」，其余取目录名。 */
function buildTaskName(path: string): string {
  const parts = path.split('/').filter(Boolean)
  const base = parts[parts.length - 1] ?? ''
  // 匹配季文件夹：Season 01 / season2 / S01 / s3（不区分大小写），季号原样保留
  const seasonMatch = /^(?:season\s*|s)(\d+)$/i.exec(base)
  if (seasonMatch) {
    const parent = parts[parts.length - 2]
    if (parent) return `${parent}S${seasonMatch[1]}`
  }
  return base
}

/** 输出目录推导：全局「输出目录前缀」+（可选父级目录 + ）相对父级目录的路径。
 * 带父级目录：以父级目录开头（如 /emby/电视剧）；不带：以一级子目录开头（如 /电视剧）。
 * 前缀空则以 / 开头（收敛到 output/ 下）。
 */
function deriveQuickOutputDir(parentDir: string, path: string, withParent: boolean): string {
  const parentStripped = parentDir.replace(/^\/+/, '').replace(/\/+$/, '')
  let rel = path
  if (parentStripped && path.startsWith(parentStripped)) {
    rel = path.slice(parentStripped.length).replace(/^\/+/, '')
  }
  if (!rel) rel = path
  const relClean = rel.replace(/^\/+/, '')
  const base = withParent && parentStripped ? `${parentStripped}/${relClean}` : relClean
  const prefix = (store.config?.output_dir_prefix ?? '').trim().replace(/\/+$/, '')
  return prefix ? `${prefix}/${base}` : `/${base}`
}

/** 勾选目录 → 将创建的任务配置预览（可包含父级目录本身）。 */
const quickIncludeParent = ref(false)
/** 输出目录是否带父级目录（默认不带，以一级子目录开头）。 */
const quickWithParent = ref(false)
const quickPreview = computed(() => {
  const items = quickSelected.value.map(path => ({
    path,
    name: buildTaskName(path),
    process_path: `/${path.replace(/^\/+/, '')}`,
    output_dir: deriveQuickOutputDir(quickParentDir.value, path, quickWithParent.value)
  }))
  // 勾选「包含父级目录」时，把父级目录本身也作为一条任务配置（置顶）
  // 输出目录默认留空，用单个斜杠 / 表示（父级作为根，输出收敛到 output/ 下）
  if (quickIncludeParent.value && quickParentDir.value) {
    const parentPath = quickParentDir.value
    if (!items.some(i => i.path === parentPath)) {
      items.unshift({
        path: parentPath,
        name: buildTaskName(parentPath),
        process_path: `/${parentPath.replace(/^\/+/, '')}`,
        output_dir: '/'
      })
    }
  }
  return items
})

function openQuickAdd() {
  quickDialogVisible.value = true
  quickSelected.value = []
  quickIncludeParent.value = false
  quickWithParent.value = false
  quickPauseCount.value = null
  quickPauseTime.value = ''
  quickParentDir.value = quickParentOptions.value[0] ?? ''
}

// 切换父级目录：清空已选目录
watch(quickParentDir, () => {
  quickSelected.value = []
})

/** 预览中删除一条：更新数据源（树勾选由 DirTreePanel 的 watch(selected) 自动同步）。 */
function removeQuickPreview(path: string) {
  // 删除的是"父级目录本身"那条 → 取消「包含父级目录」
  if (quickIncludeParent.value && path === quickParentDir.value) {
    quickIncludeParent.value = false
    return
  }
  quickSelected.value = quickSelected.value.filter(p => p !== path)
}

/** 批量创建任务配置：勾选几个目录就创建几条。 */
async function handleQuickAdd() {
  if (quickPreview.value.length === 0) {
    ElMessage.warning('请先在目录树中勾选目录')
    return
  }
  quickCreating.value = true
  try {
    const payloads = quickPreview.value.map(item => {
      const payload = {
        name: item.name,
        process_path: item.process_path,
        output_dir: item.output_dir,
        // 限流字段：留空表示使用全局配置（不提交）
        ...(quickPauseCount.value != null ? { pause_count: quickPauseCount.value } : {}),
        ...(quickPauseTime.value.trim() ? { pause_time: quickPauseTime.value.trim() } : {})
      }
      return payload
    })
    await Promise.all(payloads.map(p => openlistApi.createTask(p)))
    ElMessage.success(`已添加 ${payloads.length} 条任务配置`)
    quickDialogVisible.value = false
    quickSelected.value = []
    await Promise.all([load(), store.fetchTasks()])
  } catch {
    /* 拦截器提示 */
  } finally {
    quickCreating.value = false
  }
}

// ---------- 快速新增父级目录 ----------

function openQuickAddParentDir() {
  quickNewDirs.value = ''
  quickParentDialogVisible.value = true
}

/** 解析父级目录输入（每行一个，去空白去重）。 */
function parseParentDirs(text: string): string[] {
  const dirs: string[] = []
  for (const line of text.split('\n')) {
    const path = line.trim()
    if (path && !dirs.includes(path)) dirs.push(path)
  }
  return dirs
}

/** 快速新增父级目录：追加到唯一服务器，校验通过后自动选中新增的第一个。 */
async function handleQuickAddParentDir() {
  const serverId = store.server?.id
  if (serverId == null) {
    ElMessage.warning('请先在全局配置中新增服务器')
    return
  }
  const newDirs = parseParentDirs(quickNewDirs.value)
  if (newDirs.length === 0) {
    ElMessage.warning('请输入父级目录')
    return
  }
  quickParentSaving.value = true
  try {
    await openlistApi.addServerParentDirs(serverId, newDirs)
    await store.fetchConfig()
    quickParentDir.value = newDirs[0]
    quickParentDialogVisible.value = false
    quickNewDirs.value = ''
    ElMessage.success(`已新增 ${newDirs.length} 个父级目录`)
  } catch {
    /* 拦截器提示 */
  } finally {
    quickParentSaving.value = false
  }
}

onMounted(async () => {
  await load()
})

defineExpose({ reload: load })
</script>

<template>
  <div class="page task-manage">
    <!-- 工具栏：左侧搜索/筛选，右侧动作（主次分明） -->
    <div class="toolbar">
      <div class="toolbar__left">
        <el-input
          v-model="keyword"
          placeholder="搜索任务名称"
          clearable
          class="toolbar__keyword"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
      </div>

      <div class="toolbar__right">
        <el-button
          type="danger"
          plain
          :icon="Delete"
          :disabled="selectedIds.length === 0"
          @click="handleBatchDelete"
        >
          批量删除{{ selectedIds.length > 0 ? `（${selectedIds.length}）` : '' }}
        </el-button>
        <el-button :icon="FolderAdd" @click="openQuickAdd">快速添加</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate">新建任务</el-button>
      </div>
    </div>

    <el-card shadow="never" class="task-manage__card">
      <el-table
        v-loading="loading"
        :data="list"
        row-key="id"
        class="task-manage__table"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="48" />
        <el-table-column label="编号" prop="id" width="76" />
        <el-table-column label="任务" min-width="260">
          <template #default="{ row }">
            <div class="cell-primary">{{ row.name }}</div>
            <div class="cell-secondary" :title="row.process_path">{{ row.process_path || '—' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="输出目录" prop="output_dir" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="primary" @click="handleCopy(row)">复制</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>

        <template #empty>
          <el-empty :description="emptyDescription" :image-size="80">
            <el-button type="primary" :icon="Plus" @click="openCreate">新建任务</el-button>
          </el-empty>
        </template>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId != null ? '编辑任务' : '新建任务'"
      width="520px"
      destroy-on-close
    >
      <el-form label-width="96px">
        <el-form-item label="任务名称">
          <el-input v-model="form.name" placeholder="如：TV 剧集" maxlength="128" />
        </el-form-item>
        <el-form-item label="处理路径">
          <el-input v-model="form.process_path" placeholder="如：/电视剧" maxlength="512" />
        </el-form-item>
        <el-form-item label="输出目录">
          <el-input v-model="form.output_dir" placeholder="如：/tv" maxlength="512" />
        </el-form-item>
        <el-form-item label="限流间隔">
          <el-input-number v-model="form.pause_count" :min="1" :max="100000" placeholder="用全局" class="pause-count" />
          <div class="remark">留空则使用全局配置；每隔 N 个文件暂停一次</div>
        </el-form-item>
        <el-form-item label="限流暂停">
          <el-input v-model="form.pause_time" placeholder="用全局，如 0,3,5" maxlength="512" />
          <div class="remark">秒，逗号分隔；随机暂停其中一项；填 0 表示不限流</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 快速添加：按目录批量生成任务配置（抽屉，便于上下滚动） -->
    <el-drawer
      v-model="quickDialogVisible"
      title="快速添加任务配置（按目录）"
      size="800px"
      destroy-on-close
    >
      <el-form label-width="96px">
        <el-form-item label="父级目录">
          <div class="parent-row">
            <el-select v-model="quickParentDir" placeholder="请选择父级目录" class="quick-select">
              <el-option v-for="dir in quickParentOptions" :key="dir" :label="dir" :value="dir" />
            </el-select>
            <el-button :icon="Plus" plain @click="openQuickAddParentDir">新增</el-button>
          </div>
          <span v-if="!store.server" class="remark">请先在「全局配置」新增服务器</span>
          <span v-else-if="!quickParentOptions.length" class="remark">
            当前服务器未配置父级目录，可点击「新增」快速添加
          </span>
        </el-form-item>
        <el-form-item label="选择目录">
          <DirTreePanel v-model="quickSelected" :server-id="store.server?.id ?? null" :parent-dir="quickParentDir" />
          <div class="include-parent">
            <el-checkbox v-model="quickIncludeParent" :disabled="!quickParentDir">
              同时把父级目录「{{ quickParentDir || '—' }}」本身作为一条任务配置
            </el-checkbox>
          </div>
          <div class="include-parent">
            <el-checkbox v-model="quickWithParent" :disabled="!quickParentDir">
              输出目录带父级目录（选中以父级目录开头，如 /emby/电视剧；不选以一级子目录开头，如 /电视剧）
            </el-checkbox>
          </div>
          <div class="remark">勾选目录后点击下方「添加任务配置」，每个目录生成一条任务配置</div>
        </el-form-item>
        <el-form-item label="限流间隔">
          <el-input-number v-model="quickPauseCount" :min="1" :max="100000" placeholder="用全局" class="pause-count" />
          <div class="remark">留空则使用全局配置；每隔 N 个文件暂停一次</div>
        </el-form-item>
        <el-form-item label="限流暂停">
          <el-input v-model="quickPauseTime" placeholder="用全局，如 0,3,5" maxlength="512" />
          <div class="remark">秒，逗号分隔；随机暂停其中一项；填 0 表示不限流</div>
        </el-form-item>
        <el-form-item v-if="quickPreview.length" label="添加预览">
          <el-table :data="quickPreview" size="small" max-height="220" class="quick-table">
            <el-table-column label="任务名称" prop="name" min-width="110" show-overflow-tooltip />
            <el-table-column label="处理路径" prop="process_path" min-width="150" show-overflow-tooltip />
            <el-table-column label="输出目录" prop="output_dir" min-width="150" show-overflow-tooltip />
            <el-table-column label="操作" width="70" fixed="right">
              <template #default="{ row }">
                <el-button link type="danger" @click="removeQuickPreview(row.path)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="drawer-footer">
          <el-button @click="quickDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="quickCreating" :disabled="quickPreview.length === 0" @click="handleQuickAdd">
            添加 {{ quickPreview.length }} 条任务配置
          </el-button>
        </div>
      </template>
    </el-drawer>

    <!-- 快速新增父级目录 -->
    <el-dialog v-model="quickParentDialogVisible" title="快速新增父级目录" width="480px" destroy-on-close>
      <el-form label-width="96px">
        <el-form-item label="父级目录">
          <el-input
            v-model="quickNewDirs"
            type="textarea"
            :rows="4"
            placeholder="每行一个目录，自动补全 / 前缀，如：&#10;emby/动漫&#10;音乐"
          />
          <div class="remark">保存时自动校验格式、存在性与读写权限，校验通过后自动缓存一级子目录并选中</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="quickParentDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="quickParentSaving" @click="handleQuickAddParentDir">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
.task-manage {
  display: flex;
  flex-direction: column;
  gap: var(--up-strm-space-4, 16px);

  &__card {
    flex-shrink: 0;
  }

  &__table {
    width: 100%;
  }
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--up-strm-space-3, 12px);

  &__left,
  &__right {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--up-strm-space-2, 8px);
  }

  &__keyword {
    width: 220px;
  }
}

.cell-primary {
  font-size: var(--up-strm-font-size-base, 14px);
  color: var(--el-text-color-primary);
  line-height: 1.4;
}

.cell-secondary {
  font-size: var(--up-strm-font-size-xs, 12px);
  color: var(--el-text-color-secondary);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quick-select {
  width: 100%;
}

.pause-count {
  width: 200px;
}

.parent-row {
  display: flex;
  align-items: center;
  gap: var(--up-strm-space-2, 8px);
  width: 100%;
}

.include-parent {
  margin: var(--up-strm-space-1, 4px) 0;
}

.quick-table {
  width: 100%;
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--up-strm-space-3, 12px);
}

.remark {
  font-size: var(--up-strm-font-size-sm, 13px);
  color: var(--el-text-color-secondary);
  line-height: 1.5;
  margin-top: 2px;
}
</style>
