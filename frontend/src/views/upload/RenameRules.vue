<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Delete, Edit, Plus, Refresh, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'

import { uploaderApi } from '@/api/uploader'
import type {
  UploadRenamePreviewResponse,
  UploadRenameRule,
  UploadRenameRuleCreate
} from '@/types/uploader'

const loading = ref(false)
const rules = ref<UploadRenameRule[]>([])

const dialogVisible = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = reactive<UploadRenameRuleCreate>({
  name: '',
  template: 'S{season:02}E{episode:02}.{ext}'
})

const formRules: FormRules = {
  name: [{ required: true, message: '请输入规则名称', trigger: 'blur' }],
  template: [{ required: true, message: '请输入命名模板', trigger: 'blur' }]
}

const preview = reactive({
  filename: 'Show.S01E13.mp4',
  season: 2,
  start_episode: 13,
  result: null as UploadRenamePreviewResponse | null
})

async function load(): Promise<void> {
  loading.value = true
  try {
    const res = await uploaderApi.listRenameRules()
    rules.value = res.data
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  editingId.value = null
  form.name = ''
  form.template = 'S{season:02}E{episode:02}.{ext}'
  preview.result = null
  formRef.value?.clearValidate()
  dialogVisible.value = true
}

function openEdit(rule: UploadRenameRule): void {
  editingId.value = rule.id
  form.name = rule.name
  form.template = rule.template
  preview.result = null
  formRef.value?.clearValidate()
  dialogVisible.value = true
}

async function handleSave(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) {
    return
  }
  saving.value = true
  try {
    const payload: UploadRenameRuleCreate = { name: form.name.trim(), template: form.template.trim() }
    if (editingId.value === null) {
      await uploaderApi.createRenameRule(payload)
      ElMessage.success('重命名规则已创建')
    } else {
      await uploaderApi.updateRenameRule(editingId.value, payload)
      ElMessage.success('重命名规则已保存')
    }
    dialogVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function handleDelete(rule: UploadRenameRule): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `将删除重命名规则「${rule.name}」，使用该规则的任务需先改用其他规则。该操作不可恢复。`,
      '删除重命名规则',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  await uploaderApi.deleteRenameRule(rule.id)
  ElMessage.success('重命名规则已删除')
  await load()
}

async function handlePreview(): Promise<void> {
  const res = await uploaderApi.previewRename({
    filename: preview.filename.trim(),
    season: preview.season,
    start_episode: preview.start_episode
  })
  preview.result = res.data
}

onMounted(() => void load())
</script>

<template>
  <div class="page upload-rules">
    <div class="toolbar">
      <div class="toolbar__left">
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
        <span class="toolbar__hint">模板变量：{season} / {episode} / {ext}，支持 :02 补零</span>
      </div>
      <div class="toolbar__right">
        <el-button type="primary" :icon="Plus" @click="openCreate">新建规则</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="rules" row-key="id" style="width: 100%">
        <el-table-column label="规则名称" prop="name" min-width="160" />
        <el-table-column label="命名模板" min-width="240">
          <template #default="{ row }"><code class="template">{{ row.template }}</code></template>
        </el-table-column>
        <el-table-column label="更新时间" prop="updated_time" width="180" />
        <el-table-column label="操作" width="150" align="right">
          <template #default="{ row }">
            <el-button link type="primary" :icon="Edit" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" :icon="Delete" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="还没有重命名规则，先创建一个吧">
            <el-button type="primary" :icon="Plus" @click="openCreate">新建规则</el-button>
          </el-empty>
        </template>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId === null ? '新建重命名规则' : '编辑重命名规则'"
      width="560px"
    >
      <el-form ref="formRef" :model="form" :rules="formRules" label-position="top">
        <el-form-item label="规则名称" prop="name">
          <el-input v-model="form.name" placeholder="例如：默认 SxxExx" maxlength="64" />
        </el-form-item>
        <el-form-item label="命名模板" prop="template">
          <el-input v-model="form.template" placeholder="S{season:02}E{episode:02}.{ext}" />
        </el-form-item>
        <div class="form-tip">
          可用变量：{season}（输出季数）、{episode}（换算后的季内集号）、{ext}（扩展名）；必须同时包含
          episode 与 ext，最终输出需为 SxxExx.ext 形式。
        </div>
      </el-form>

      <div class="preview">
        <div class="preview__header">
          <span class="preview__title">预览</span>
          <el-button size="small" :icon="View" @click="handlePreview">预览</el-button>
        </div>
        <div class="preview__form">
          <el-input v-model="preview.filename" placeholder="原始文件名，如 Show.S01E13.mp4" />
          <el-input-number v-model="preview.season" :min="1" :max="99" controls-position="right" />
          <el-input-number v-model="preview.start_episode" :min="1" :max="9999" controls-position="right" />
        </div>
        <div v-if="preview.result" class="preview__result">
          <template v-if="preview.result.matched">
            <span class="preview__ok">{{ preview.result.output_name }}</span>
            <span class="preview__meta">（绝对集号 {{ preview.result.episode }}）</span>
          </template>
          <span v-else class="preview__fail">{{ preview.result.reason || '无法解析集数' }}</span>
        </div>
      </div>

      <template #footer>
        <div class="drawer-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
.upload-rules {
  gap: var(--up-strm-space-3);

  .toolbar__hint {
    margin-left: var(--up-strm-space-2);
    color: var(--el-text-color-placeholder);
    font-size: var(--up-strm-font-size-xs);
  }

  .template {
    padding: 1px 6px;
    border-radius: var(--up-strm-radius-sm);
    background: var(--el-fill-color-light);
    color: var(--el-text-color-regular);
    font-family: ui-monospace, 'SFMono-Regular', Consolas, monospace;
    font-size: var(--up-strm-font-size-xs);
  }

  .form-tip {
    margin-top: calc(-1 * var(--up-strm-space-1));
    color: var(--el-text-color-placeholder);
    font-size: var(--up-strm-font-size-xs);
    line-height: 1.5;
  }

  .preview {
    margin-top: var(--up-strm-space-2);
    padding: var(--up-strm-space-3);
    border: 1px dashed var(--el-border-color);
    border-radius: var(--up-strm-radius-sm);

    &__header {
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    &__title {
      color: var(--el-text-color-primary);
      font-size: var(--up-strm-font-size-sm);
      font-weight: 600;
    }

    &__form {
      display: flex;
      gap: var(--up-strm-space-2);
      margin-top: var(--up-strm-space-2);
    }

    &__result {
      margin-top: var(--up-strm-space-2);
      font-size: var(--up-strm-font-size-sm);
    }

    &__ok {
      color: var(--el-color-success);
      font-family: ui-monospace, 'SFMono-Regular', Consolas, monospace;
      font-weight: 600;
    }

    &__meta {
      color: var(--el-text-color-secondary);
    }

    &__fail {
      color: var(--el-color-warning);
    }
  }
}
</style>
