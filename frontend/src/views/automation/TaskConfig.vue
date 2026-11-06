<template>
  <div class="page page--fill list-page automation-tasks">
    <div class="toolbar">
      <div class="toolbar__left">
        <el-input
          v-model="keyword"
          class="toolbar__keyword"
          clearable
          :prefix-icon="Search"
          placeholder="搜索任务名称 / 校验目录"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
      </div>
      <div class="toolbar__right">
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
        <el-button
          type="danger"
          plain
          :icon="Delete"
          :disabled="selectedIds.length === 0"
          @click="handleBatchDelete"
        >
          批量删除
        </el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate">新建任务</el-button>
      </div>
    </div>

    <el-card shadow="never" class="list-card">
      <div class="list-card__table">
        <el-table
          ref="tableRef"
          v-loading="loading"
          :data="tasks"
          row-key="id"
          style="width: 100%"
          @selection-change="handleSelectionChange"
        >
          <el-table-column type="selection" width="48" />
          <el-table-column label="任务名称" min-width="180">
            <template #default="{ row }">
              <div class="cell-main">{{ row.name }}</div>
              <div class="cell-sub">{{ row.check_dir }}</div>
            </template>
          </el-table-column>
          <el-table-column label="上传任务（B）" min-width="150">
            <template #default="{ row }">{{ row.upload_task_name || `#${row.upload_task_id}` }}</template>
          </el-table-column>
          <el-table-column label="STRM 任务（A）" min-width="150">
            <template #default="{ row }">{{ row.openlist_task_name || `#${row.openlist_task_id}` }}</template>
          </el-table-column>
          <el-table-column label="运行参数" min-width="150">
            <template #default="{ row }">
              <div class="cell-main">并发 {{ row.upload_concurrency }} · 重试 {{ row.upload_retry_times }}</div>
              <div class="cell-sub">{{ modeLabel(row.openlist_mode) }} · 间隔 {{ row.interval_seconds }}s</div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="row.is_running ? 'success' : 'info'" effect="light" round>
                {{ row.is_running ? '运行中' : '空闲' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="最近扫描" min-width="180">
            <template #default="{ row }">
              <div class="cell-main">{{ row.scan_time || '尚未扫描' }}</div>
              <div class="cell-sub">
                第 {{ row.last_round_no }} 轮 · 待处理 {{ row.pending_file_count }} 个文件
              </div>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" align="right">
            <template #default="{ row }">
              <el-button link type="primary" :icon="Edit" @click="openEdit(row)">编辑</el-button>
              <el-button link type="danger" :icon="Delete" @click="handleDelete(row)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty :description="emptyDescription">
              <el-button v-if="!keyword.trim()" type="primary" :icon="Plus" @click="openCreate">
                创建第一个自动化任务
              </el-button>
            </el-empty>
          </template>
        </el-table>
      </div>
      <div class="list-card__pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          background
          @current-change="load"
          @size-change="handleSearch"
        />
      </div>
    </el-card>

    <el-drawer v-model="drawerVisible" :title="drawerTitle" size="560px">
      <el-form ref="formRef" :model="form" :rules="formRules" label-position="top">
        <el-form-item label="任务名称" prop="name">
          <el-input v-model="form.name" placeholder="例如：某剧 自动上传 + 生成" maxlength="128" />
        </el-form-item>

        <el-form-item label="上传任务（B）" prop="upload_task_id">
          <el-select
            v-model="form.upload_task_id"
            filterable
            placeholder="选择已配置的上传任务"
            style="width: 100%"
            @change="handleUploadTaskChange"
          >
            <el-option
              v-for="option in uploadOptions"
              :key="option.id"
              :label="option.name"
              :value="option.id"
              :disabled="!!option.bound_by"
            >
              <div class="option-row">
                <span>{{ option.name }}</span>
                <span class="option-row__hint">
                  {{ option.bound_by ? `已绑定：${option.bound_by}` : option.remote_dir || '未设置云端目录' }}
                </span>
              </div>
            </el-option>
          </el-select>
        </el-form-item>

        <el-form-item label="STRM 任务（A）" prop="openlist_task_id">
          <el-select
            v-model="form.openlist_task_id"
            filterable
            placeholder="选择已配置的 STRM 任务"
            style="width: 100%"
          >
            <el-option
              v-for="option in openlistOptions"
              :key="option.id"
              :label="option.name"
              :value="option.id"
              :disabled="!!option.bound_by"
            >
              <div class="option-row">
                <span>{{ option.name }}</span>
                <span class="option-row__hint">
                  {{ option.bound_by ? `已绑定：${option.bound_by}` : option.process_path || '未设置处理路径' }}
                </span>
              </div>
            </el-option>
          </el-select>
        </el-form-item>

        <el-form-item label="校验目录" prop="check_dir">
          <div class="check-dir-row">
            <el-input v-model="form.check_dir" placeholder="通常由上传任务云端目录推导" />
            <el-button :loading="checking" @click="handleCheckDir">检测</el-button>
          </div>
          <div v-if="expectedCheckDir" class="form-tip">
            期望目录：{{ expectedCheckDir }}
            <template v-if="remotePrefix">（含远程前缀 {{ remotePrefix }}）</template>
          </div>
          <div v-if="checkResult" class="check-result" :class="checkResultClass">
            <el-tag :type="checkResult.consistent ? 'success' : 'warning'" effect="light">
              {{ checkResult.consistent ? '映射一致' : '映射不一致' }}
            </el-tag>
            <el-tag :type="checkResult.reachable ? 'success' : 'info'" effect="light">
              {{ checkResult.reachable ? `可访问 ${checkResult.file_count} 个文件` : '暂时不可访问' }}
            </el-tag>
            <div class="form-tip">{{ checkResult.message }}</div>
            <div v-if="checkResult.files.length" class="check-files">
              {{ checkResult.files.join('、') }}
            </div>
          </div>
        </el-form-item>

        <el-divider content-position="left">上传参数</el-divider>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="上传并发数" prop="upload_concurrency">
              <el-input-number v-model="form.upload_concurrency" :min="1" :max="8" controls-position="right" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="失败重试次数" prop="upload_retry_times">
              <el-input-number v-model="form.upload_retry_times" :min="0" :max="10" controls-position="right" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">STRM 生成参数</el-divider>
        <el-form-item label="生成模式" prop="openlist_mode">
          <el-select v-model="form.openlist_mode" style="width: 100%">
            <el-option label="增量（仅新增/变更文件）" value="incremental" />
            <el-option label="全量重新生成" value="full" />
            <el-option label="仅生成 STRM" value="strm_only" />
          </el-select>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="可见性轮询间隔（秒）" prop="wait_interval_seconds">
              <el-input-number
                v-model="form.wait_interval_seconds"
                :min="5"
                :max="120"
                controls-position="right"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="可见性等待超时（秒）" prop="openlist_wait_timeout">
              <el-input-number
                v-model="form.openlist_wait_timeout"
                :min="60"
                :max="3600"
                controls-position="right"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="空闲等待超时（秒）" prop="idle_wait_timeout">
              <el-input-number
                v-model="form.idle_wait_timeout"
                :min="60"
                :max="3600"
                controls-position="right"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="阶段超时（秒）" prop="stage_timeout">
              <el-input-number v-model="form.stage_timeout" :min="60" :max="7200" controls-position="right" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="轮次间隔（秒）" prop="interval_seconds">
          <el-input-number v-model="form.interval_seconds" :min="10" :max="3600" controls-position="right" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="drawer-footer">
          <el-button @click="drawerVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Delete, Edit, Plus, Refresh, Search } from '@element-plus/icons-vue'
import {
  ElMessage,
  ElMessageBox,
  type FormInstance,
  type FormRules
} from 'element-plus'

import { automationApi } from '@/api/automation'
import type {
  AutomationCheckDirResult,
  AutomationOpenListMode,
  AutomationOpenListTaskOption,
  AutomationTask,
  AutomationTaskPayload,
  AutomationUploadTaskOption
} from '@/types/automation'

const loading = ref(false)
const tasks = ref<AutomationTask[]>([])
const total = ref(0)
const keyword = ref('')
const page = ref(1)
const pageSize = ref(20)
const selectedIds = ref<number[]>([])

const drawerVisible = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()

const uploadOptions = ref<AutomationUploadTaskOption[]>([])
const openlistOptions = ref<AutomationOpenListTaskOption[]>([])
const remotePrefix = ref('')

const checking = ref(false)
const checkResult = ref<AutomationCheckDirResult | null>(null)

const emptyDescription = computed(() =>
  keyword.value.trim() ? '没有匹配的自动化任务' : '暂无自动化任务，创建后将串联「上传」与「STRM 生成」'
)
const drawerTitle = computed(() => (editingId.value ? '编辑自动化任务' : '新建自动化任务'))
const expectedCheckDir = computed(() => {
  const option = uploadOptions.value.find(item => item.id === form.upload_task_id)
  return option?.derived_check_dir ?? ''
})
const checkResultClass = computed(() => (checkResult.value?.consistent ? 'is-ok' : 'is-warn'))

function createDefaultForm(): AutomationTaskPayload {
  return {
    name: '',
    upload_task_id: 0,
    openlist_task_id: 0,
    check_dir: '',
    upload_concurrency: 2,
    upload_retry_times: 3,
    openlist_mode: 'incremental',
    wait_interval_seconds: 15,
    openlist_wait_timeout: 600,
    idle_wait_timeout: 600,
    stage_timeout: 3600,
    interval_seconds: 60
  }
}

const form = reactive<AutomationTaskPayload>(createDefaultForm())

const formRules: FormRules = {
  name: [{ required: true, message: '请输入任务名称', trigger: 'blur' }],
  upload_task_id: [{ required: true, message: '请选择上传任务', trigger: 'change' }],
  openlist_task_id: [{ required: true, message: '请选择 STRM 任务', trigger: 'change' }],
  check_dir: [{ required: true, message: '请填写校验目录', trigger: 'blur' }]
}

function modeLabel(mode: AutomationOpenListMode): string {
  return mode === 'full' ? '全量生成' : mode === 'strm_only' ? '仅生成 STRM' : '增量生成'
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const res = await automationApi.listTasks({
      keyword: keyword.value.trim() || undefined,
      page: page.value,
      page_size: pageSize.value
    })
    tasks.value = res.data ?? []
    total.value = res.total ?? tasks.value.length
    if (tasks.value.some(task => task.is_running)) {
      scheduleRefresh()
    }
  } finally {
    loading.value = false
  }
}

function handleSearch(): void {
  page.value = 1
  load()
}

let refreshTimer: ReturnType<typeof setTimeout> | null = null

function scheduleRefresh(): void {
  if (refreshTimer) return
  refreshTimer = setTimeout(() => {
    refreshTimer = null
    load()
  }, 5000)
}

async function loadOptions(includeTaskId?: number): Promise<void> {
  const res = await automationApi.bindOptions(includeTaskId)
  uploadOptions.value = res.data.upload_tasks
  openlistOptions.value = res.data.openlist_tasks
  remotePrefix.value = res.data.openlist_remote_prefix
}

function resetForm(): void {
  Object.assign(form, createDefaultForm())
  checkResult.value = null
}

async function openCreate(): Promise<void> {
  editingId.value = null
  resetForm()
  await loadOptions()
  drawerVisible.value = true
  formRef.value?.clearValidate()
}

async function openEdit(task: AutomationTask): Promise<void> {
  editingId.value = task.id
  resetForm()
  Object.assign(form, {
    name: task.name,
    upload_task_id: task.upload_task_id,
    openlist_task_id: task.openlist_task_id,
    check_dir: task.check_dir,
    upload_concurrency: task.upload_concurrency,
    upload_retry_times: task.upload_retry_times,
    openlist_mode: task.openlist_mode,
    wait_interval_seconds: task.wait_interval_seconds,
    openlist_wait_timeout: task.openlist_wait_timeout,
    idle_wait_timeout: task.idle_wait_timeout,
    stage_timeout: task.stage_timeout,
    interval_seconds: task.interval_seconds
  } satisfies AutomationTaskPayload)
  await loadOptions(task.id)
  drawerVisible.value = true
  formRef.value?.clearValidate()
}

function handleUploadTaskChange(): void {
  const option = uploadOptions.value.find(item => item.id === form.upload_task_id)
  if (option?.derived_check_dir) {
    form.check_dir = option.derived_check_dir
  }
  checkResult.value = null
}

async function handleCheckDir(): Promise<void> {
  if (!form.upload_task_id) {
    ElMessage.warning('请先选择上传任务')
    return
  }
  checking.value = true
  try {
    const res = await automationApi.checkDir({
      upload_task_id: form.upload_task_id,
      check_dir: form.check_dir,
      task_id: editingId.value ?? undefined
    })
    checkResult.value = res.data
    if (res.data.check_dir) {
      form.check_dir = res.data.check_dir
    }
  } finally {
    checking.value = false
  }
}

async function handleSave(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    const payload: AutomationTaskPayload = { ...form, name: form.name.trim() }
    const res = editingId.value
      ? await automationApi.updateTask(editingId.value, payload)
      : await automationApi.createTask(payload)
    ;(res.data.warnings ?? []).forEach(warning => ElMessage.warning(warning))
    ElMessage.success(editingId.value ? '任务已更新' : '任务已创建')
    drawerVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function handleDelete(task: AutomationTask): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除自动化任务「${task.name}」？`, '删除确认', {
      type: 'warning'
    })
  } catch {
    return
  }
  await automationApi.deleteTask(task.id)
  ElMessage.success('已删除')
  await load()
}

function handleSelectionChange(rows: AutomationTask[]): void {
  selectedIds.value = rows.map(row => row.id)
}

async function handleBatchDelete(): Promise<void> {
  if (selectedIds.value.length === 0) return
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selectedIds.value.length} 个自动化任务？`, '批量删除', {
      type: 'warning'
    })
  } catch {
    return
  }
  await automationApi.batchDeleteTasks(selectedIds.value)
  ElMessage.success('已删除')
  selectedIds.value = []
  await load()
}

onMounted(load)

onBeforeUnmount(() => {
  if (refreshTimer) {
    clearTimeout(refreshTimer)
    refreshTimer = null
  }
})
</script>

<style scoped lang="scss">
// 与列表页一致：页面级纵向间距由页面自身承担（.page--fill 基础样式不含 gap）。
.automation-tasks {
  gap: var(--up-strm-space-4);
}

.check-dir-row {
  display: flex;
  gap: 8px;
  width: 100%;

  .el-input {
    flex: 1;
  }
}

.check-result {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}

.check-files {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  word-break: break-all;
}

.option-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  width: 100%;
}

.option-row__hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
