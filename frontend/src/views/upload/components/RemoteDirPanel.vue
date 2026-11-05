<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ArrowLeft, FolderOpened, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import { uploaderApi } from '@/api/uploader'
import type { UploadRemoteDirItem } from '@/types/uploader'

const emit = defineEmits<{
  (e: 'select', path: string): void
}>()

const loading = ref(false)
const parentId = ref(0)
const currentPath = ref('/')
const history = ref<Array<{ parentId: number; path: string }>>([])
const items = ref<UploadRemoteDirItem[]>([])

function joinPath(prefix: string, name: string): string {
  return prefix === '/' ? `/${name}` : `${prefix}/${name}`
}

async function load(targetParentId = 0, targetPath = '/'): Promise<void> {
  loading.value = true
  try {
    const res = await uploaderApi.listRemoteDirs({ parent_id: targetParentId, path: targetPath })
    parentId.value = res.data.parent_id
    currentPath.value = targetPath
    items.value = res.data.items
  } finally {
    loading.value = false
  }
}

function enterDir(item: UploadRemoteDirItem): void {
  history.value.push({ parentId: parentId.value, path: currentPath.value })
  void load(item.file_id, joinPath(currentPath.value, item.file_name))
}

function goUp(): void {
  const previous = history.value.pop()
  if (previous) {
    void load(previous.parentId, previous.path)
  } else {
    void load(0, '/')
  }
}

function selectCurrent(): void {
  if (currentPath.value === '/') {
    ElMessage.warning('请选择 /test 下的子目录或 /test 本身')
    return
  }
  emit('select', currentPath.value)
}

onMounted(() => void load(0, '/'))
</script>

<template>
  <div class="remote-dir">
    <div class="remote-dir__toolbar">
      <el-button :icon="ArrowLeft" :disabled="loading" @click="goUp">上级</el-button>
      <el-button :icon="Refresh" :disabled="loading" @click="load(0, '/')">根目录</el-button>
      <span class="remote-dir__path">{{ currentPath }}</span>
    </div>

    <div v-loading="loading" class="remote-dir__list">
      <button
        v-for="item in items"
        :key="item.file_id"
        class="remote-dir__item"
        type="button"
        @click="enterDir(item)"
      >
        <el-icon :size="16"><FolderOpened /></el-icon>
        <span>{{ item.file_name }}</span>
      </button>
      <el-empty v-if="!loading && items.length === 0" description="该目录下没有子目录" :image-size="64" />
    </div>

    <div class="remote-dir__footer">
      <span class="remote-dir__hint">测试与联调请仅使用 123 云盘 /test 目录</span>
      <el-button type="primary" :disabled="currentPath === '/'" @click="selectCurrent">
        选为上传目录
      </el-button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.remote-dir {
  display: flex;
  flex-direction: column;
  gap: var(--up-strm-space-3);

  &__toolbar {
    display: flex;
    align-items: center;
    gap: var(--up-strm-space-2);
  }

  &__path {
    flex: 1;
    overflow: hidden;
    color: var(--el-text-color-secondary);
    font-family: ui-monospace, 'SFMono-Regular', Consolas, monospace;
    font-size: var(--up-strm-font-size-xs);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__list {
    display: flex;
    flex-direction: column;
    gap: var(--up-strm-space-1);
    min-height: 220px;
    max-height: 320px;
    padding: var(--up-strm-space-1);
    overflow-y: auto;
    border: 1px solid var(--el-border-color-lighter);
    border-radius: var(--up-strm-radius-sm);
  }

  &__item {
    display: flex;
    align-items: center;
    gap: var(--up-strm-space-2);
    height: 34px;
    padding: 0 var(--up-strm-space-2);
    border: none;
    border-radius: var(--up-strm-radius-sm);
    background: transparent;
    color: var(--el-text-color-regular);
    font-size: var(--up-strm-font-size-sm);
    text-align: left;
    cursor: pointer;

    &:hover {
      background: var(--el-fill-color-light);
      color: var(--el-color-primary);
    }
  }

  &__footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--up-strm-space-2);
  }

  &__hint {
    color: var(--el-text-color-placeholder);
    font-size: var(--up-strm-font-size-xs);
  }
}
</style>
