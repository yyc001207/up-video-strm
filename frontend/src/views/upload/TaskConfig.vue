<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Delete, Edit, FolderOpened, Plus, Refresh, Search } from '@element-plus/icons-vue'
import {
  ElMessage,
  type FormInstance,
  type FormRules,
  type TableInstance
} from 'element-plus'

import { uploaderApi } from '@/api/uploader'
import BulkBar from '@/components/BulkBar.vue'
import EmptyState from '@/components/EmptyState.vue'
import { useConfirmAction } from '@/composables/useConfirmAction'
import type { UploadRenameRule, UploadTask, UploadTaskCreate } from '@/types/uploader'

import RemoteDirPanel from './components/RemoteDirPanel.vue'

const loading = ref(false)
const tasks = ref<UploadTask[]>([])
const rules = ref<UploadRenameRule[]>([])

// 列表筛选 / 选择 / 分页（客户端处理）
const keyword = ref('')
const selectedIds = ref<number[]>([])
const page = ref(1)
const pageSize = ref(20)

const tableRef = ref<TableInstance>()
const { confirmDanger } = useConfirmAction()

function handleSelectionChange(rows: UploadTask[]): void {
  selectedIds.value = rows.map(row => row.id)
}

const drawerVisible = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = reactive<UploadTaskCreate>({
  name: '',
  local_dir: '',
  remote_dir: '',
  season: 1,
  start_episode: 1,
  rename_rule_id: null
})

interface DesktopBridge {
  api?: {
    pick_directory?: (startDir?: string) => Promise<string | null>
  }
}

/** 桌面版通过 pywebview 打开系统目录选择框；网页版退化为手动输入。 */
async function pickLocalDir(): Promise<void> {
  const bridge = (window as unknown as { pywebview?: DesktopBridge }).pywebview
  if (!bridge?.api?.pick_directory) {
    ElMessage.warning('目录快速选择仅在桌面版可用，请手动输入本地目录')
    return
  }
  const picked = await bridge.api.pick_directory(form.local_dir.trim() || undefined)
  if (picked) {
    form.local_dir = picked
  }
}

const rulesOptions = computed(() => rules.value.map(rule => ({ label: rule.name, value: rule.id })))

const formRules: FormRules = {
  name: [{ required: true, message: '请输入任务名称', trigger: 'blur' }],
  local_dir: [{ required: true, message: '请输入本地目录', trigger: 'blur' }],
  remote_dir: [{ required: true, message: '请选择云端目录', trigger: 'change' }],
  season: [{ required: true, message: '请输入输出季数', trigger: 'change' }],
  start_episode: [{ required: true, message: '请输入源起始集号', trigger: 'change' }]
}

const remoteDialogVisible = ref(false)

const drawerTitle = computed(() => (editingId.value === null ? '新建上传任务' : '编辑上传任务'))

/** 名称关键字过滤（不区分大小写的包含匹配）。 */
const filteredTasks = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) {
    return tasks.value
  }
  return tasks.value.filter(task => task.name.toLowerCase().includes(kw))
})

const pagedTasks = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filteredTasks.value.slice(start, start + pageSize.value)
})

const emptyDescription = computed(() =>
  keyword.value.trim() ? '没有匹配的上传任务' : '还没有上传任务，先创建一个吧'
)

// 搜索条件或每页条数变化时回到第一页
watch([keyword, pageSize], () => {
  page.value = 1
})

// 数据量变化（删除/刷新）时把页码收敛到最后一页
watch(filteredTasks, value => {
  const maxPage = Math.max(1, Math.ceil(value.length / pageSize.value))
  if (page.value > maxPage) {
    page.value = maxPage
  }
})

function resetSelection(): void {
  selectedIds.value = []
  tableRef.value?.clearSelection()
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const [taskRes, ruleRes] = await Promise.all([
      uploaderApi.listTasks(),
      uploaderApi.listRenameRules()
    ])
    tasks.value = taskRes.data
    rules.value = ruleRes.data
  } finally {
    loading.value = false
  }
}

function resetForm(): void {
  form.name = ''
  form.local_dir = ''
  form.remote_dir = ''
  form.season = 1
  form.start_episode = 1
  form.rename_rule_id = null
  formRef.value?.clearValidate()
}

function openCreate(): void {
  editingId.value = null
  resetForm()
  drawerVisible.value = true
}

function openEdit(task: UploadTask): void {
  editingId.value = task.id
  form.name = task.name
  form.local_dir = task.local_dir
  form.remote_dir = task.remote_dir
  form.season = task.season
  form.start_episode = task.start_episode
  form.rename_rule_id = task.rename_rule_id
  formRef.value?.clearValidate()
  drawerVisible.value = true
}

async function handleSave(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) {
    return
  }
  saving.value = true
  try {
    const payload: UploadTaskCreate = {
      name: form.name.trim(),
      local_dir: form.local_dir.trim(),
      remote_dir: form.remote_dir,
      season: form.season,
      start_episode: form.start_episode,
      rename_rule_id: form.rename_rule_id ?? null
    }
    if (editingId.value === null) {
      await uploaderApi.createTask(payload)
      ElMessage.success('上传任务已创建')
    } else {
      await uploaderApi.updateTask(editingId.value, payload)
      ElMessage.success('上传任务已保存')
    }
    drawerVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function handleDelete(task: UploadTask): Promise<void> {
  const confirmed = await confirmDanger({
    title: '删除上传任务',
    message: `将删除上传任务「${task.name}」及其配置（不影响云端已上传文件），该操作不可恢复。`,
    confirmText: '删除'
  })
  if (!confirmed) return
  await uploaderApi.deleteTask(task.id)
  ElMessage.success('上传任务已删除')
  await load()
}

/** 批量删除：确认后按选中的 id 一次提交，成功后清空选择并刷新。 */
async function handleBatchDelete(): Promise<void> {
  const ids = [...selectedIds.value]
  if (ids.length === 0) {
    return
  }
  const confirmed = await confirmDanger({
    title: '批量删除任务',
    message: `确定删除选中的 ${ids.length} 个任务？删除后不可恢复。`,
    confirmText: '删除'
  })
  if (!confirmed) return
  try {
    const res = await uploaderApi.batchDeleteTasks(ids)
    ElMessage.success(`已删除 ${res.data.deleted} 个任务`)
    resetSelection()
    await load()
  } catch {
    /* 错误信息由请求拦截器统一提示 */
  }
}

function handleRemoteSelect(path: string): void {
  form.remote_dir = path
  remoteDialogVisible.value = false
}

const remoteTip = computed(() => {
  if (!form.remote_dir) {
    return '尚未选择云端目录；测试与联调请使用 /test 目录'
  }
  return form.remote_dir === '/test' || form.remote_dir.startsWith('/test/')
    ? '将以 /test 目录进行联调'
    : '注意：测试与联调只应使用 /test 目录'
})

onMounted(() => void load())
</script>

<template>
  <div class="page page--fill list-page upload-tasks">
    <div class="toolbar">
      <div class="toolbar__left">
        <el-input
          v-model="keyword"
          class="toolbar__keyword"
          clearable
          :prefix-icon="Search"
          placeholder="搜索任务名称"
          @keyup.enter="page = 1"
          @clear="page = 1"
        />
      </div>
      <div class="toolbar__right">
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate">新建任务</el-button>
      </div>
    </div>

    <el-card shadow="never" class="list-card">
      <div class="list-card__table">
        <el-table
          ref="tableRef"
          v-loading="loading"
          :data="pagedTasks"
          row-key="id"
          @selection-change="handleSelectionChange"
        >
          <el-table-column type="selection" width="48" />
          <el-table-column label="任务" min-width="260">
            <template #default="{ row }">
              <div class="cell-primary">{{ row.name }}</div>
              <div class="cell-secondary" :title="row.local_dir">{{ row.local_dir }}</div>
            </template>
          </el-table-column>
          <el-table-column label="云端目录" prop="remote_dir" min-width="160" show-overflow-tooltip />
          <el-table-column label="季数" width="80" align="right">
            <template #default="{ row }">S{{ String(row.season).padStart(2, '0') }}</template>
          </el-table-column>
          <el-table-column label="起始集号" prop="start_episode" width="96" align="right" />
          <el-table-column label="命名规则" min-width="140">
            <template #default="{ row }">{{ row.rename_rule_name || '默认规则' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="190" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" :icon="Edit" @click="openEdit(row)">编辑</el-button>
              <el-button link type="danger" :icon="Delete" @click="handleDelete(row)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>
            <EmptyState :title="emptyDescription" compact @action="openCreate" />
          </template>
        </el-table>
      </div>
      <BulkBar v-if="selectedIds.length > 0" :count="selectedIds.length" class="task-bulk" @clear="resetSelection">
        <el-button type="danger" plain :icon="Delete" @click="handleBatchDelete">删除</el-button>
      </BulkBar>
      <div class="list-card__pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="filteredTasks.length"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          background
        />
      </div>
    </el-card>

    <el-drawer v-model="drawerVisible" :title="drawerTitle" size="520px">
      <el-form ref="formRef" :model="form" :rules="formRules" label-position="top">
        <el-form-item label="任务名称" prop="name">
          <el-input v-model="form.name" placeholder="例如：某剧 第二季" maxlength="64" />
        </el-form-item>
        <el-form-item label="本地目录" prop="local_dir">
          <div class="local-picker">
            <el-input v-model="form.local_dir" placeholder="例如：D:\\videos\\某剧" />
            <el-button :icon="FolderOpened" @click="pickLocalDir">浏览</el-button>
          </div>
        </el-form-item>
        <el-form-item label="云端目录" prop="remote_dir">
          <div class="remote-picker">
            <el-input v-model="form.remote_dir" readonly placeholder="点击「浏览」选择云端目录" />
            <el-button :icon="FolderOpened" @click="remoteDialogVisible = true">浏览</el-button>
          </div>
          <div v-if="remoteTip" class="form-tip">{{ remoteTip }}</div>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="输出季数" prop="season">
              <el-input-number v-model="form.season" :min="1" :max="99" controls-position="right" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="源起始集号" prop="start_episode">
              <el-input-number
                v-model="form.start_episode"
                :min="1"
                :max="9999"
                controls-position="right"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <div class="form-tip">
          集号换算：季内集号 = 解析出的绝对集号 − 源起始集号 + 1（如起始 13 时 S01E13 → S02E01）。
        </div>
        <el-form-item label="命名规则" prop="rename_rule_id">
          <el-select v-model="form.rename_rule_id" clearable placeholder="默认规则" style="width: 100%">
            <el-option
              v-for="option in rulesOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="drawer-footer">
          <el-button @click="drawerVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
        </div>
      </template>
    </el-drawer>

    <el-dialog v-model="remoteDialogVisible" title="选择云端目录" width="640px" append-to-body>
      <RemoteDirPanel @select="handleRemoteSelect" />
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
.upload-tasks {
  display: flex;
  flex-direction: column;
  gap: var(--up-strm-space-3);

  // 列表：行间以分隔线组织，外框由容器承担
  .task-list {
    display: flex;
    flex-direction: column;
    min-height: 120px;
    border: 1px solid var(--el-border-color-lighter);
    border-radius: var(--up-strm-radius-lg);
    background: var(--el-bg-color);
    overflow: hidden;
  }

  .task-bulk {
    margin-top: var(--up-strm-space-3);
  }

  // 工具栏布局见 styles/global.scss 的 .toolbar 原语
  .toolbar__keyword {
    width: 220px;
  }

  .cell-main {
    color: var(--el-text-color-primary);
    font-weight: 500;
  }

  .cell-sub {
    margin-top: 2px;
    overflow: hidden;
    color: var(--el-text-color-secondary);
    font-size: var(--up-strm-font-size-xs);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .local-picker,
  .remote-picker {
    display: flex;
    gap: var(--up-strm-space-2);
    width: 100%;
  }

  .form-tip {
    margin-top: var(--up-strm-space-1);
    color: var(--el-text-color-placeholder);
    font-size: var(--up-strm-font-size-xs);
    line-height: 1.5;
  }
}
</style>
