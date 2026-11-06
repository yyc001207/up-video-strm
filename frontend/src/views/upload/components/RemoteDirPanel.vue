<script setup lang="ts">
/**
 * 123 云盘目录选择面板（逐级导航，按需请求）。
 *
 * 交互：
 * - 打开时只请求一次根目录列表；
 * - 点击目录行进入下级（每次进入只请求一次接口，不做任何递归预加载）；
 * - 面包屑 / 「返回上级」可回到任意上级目录；
 * - 顶部搜索框对当前目录已加载的文件夹做实时模糊过滤，切换目录时自动清空关键字；
 * - 底部醒目展示「当前目录」，点「选择此目录」即选定当前所在目录。
 */
import { computed, onMounted, ref } from 'vue'
import { Back, FolderOpened, Refresh, Search } from '@element-plus/icons-vue'

import { uploaderApi } from '@/api/uploader'

export interface RemoteDirEntry {
  id: number
  name: string
  path: string
}

const emit = defineEmits<{
  (e: 'select', path: string): void
}>()

interface TrailItem {
  id: number
  name: string
  path: string
}

const trail = ref<TrailItem[]>([{ id: 0, name: '根目录', path: '/' }])
const items = ref<RemoteDirEntry[]>([])
const loading = ref(false)
/** 当前目录的模糊搜索关键字（只过滤已加载的文件夹，不触发额外请求）。 */
const keyword = ref('')

const current = computed<TrailItem>(() => trail.value[trail.value.length - 1])
const canGoUp = computed(() => trail.value.length > 1)
const filteredItems = computed(() => {
  const needle = keyword.value.trim().toLowerCase()
  if (needle === '') return items.value
  return items.value.filter(item => item.name.toLowerCase().includes(needle))
})
const emptyDescription = computed(() =>
  keyword.value.trim() === '' ? '该目录下没有子目录' : `没有匹配「${keyword.value.trim()}」的文件夹`
)

function joinPath(parentPath: string, name: string): string {
  return parentPath === '/' ? `/${name}` : `${parentPath}/${name}`
}

/** 只请求当前目录的直接子目录（一次一页展示，不递归）。 */
async function loadDir(target: TrailItem): Promise<void> {
  loading.value = true
  try {
    const res = await uploaderApi.listRemoteDirs({ parent_id: target.id, path: target.path })
    items.value = res.data.items
      .filter(item => item.is_dir)
      .map(item => ({ id: item.file_id, name: item.file_name, path: joinPath(target.path, item.file_name) }))
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

function enterDir(item: RemoteDirEntry): void {
  keyword.value = ''
  trail.value = [...trail.value, item]
  void loadDir(item)
}

function goUp(): void {
  if (!canGoUp.value) return
  jumpTo(trail.value.length - 2)
}

function jumpTo(index: number): void {
  if (index < 0 || index >= trail.value.length) return
  keyword.value = ''
  trail.value = trail.value.slice(0, index + 1)
  void loadDir(current.value)
}

function refresh(): void {
  void loadDir(current.value)
}

function confirmSelect(): void {
  emit('select', current.value.path)
}

onMounted(() => void loadDir(current.value))
</script>

<template>
  <div class="remote-dir">
    <div class="remote-dir__breadcrumb">
      <template v-for="(item, index) in trail" :key="item.path">
        <el-button
          link
          class="remote-dir__crumb"
          :class="{ 'is-current': index === trail.length - 1 }"
          @click="jumpTo(index)"
        >
          {{ item.name }}
        </el-button>
        <span v-if="index < trail.length - 1" class="remote-dir__sep">/</span>
      </template>
      <el-button :icon="Refresh" size="small" :loading="loading" class="remote-dir__refresh" @click="refresh">
        刷新
      </el-button>
    </div>

    <div class="remote-dir__search">
      <el-input
        v-model="keyword"
        :prefix-icon="Search"
        placeholder="搜索当前目录下的文件夹"
        clearable
        size="small"
      />
    </div>

    <div v-loading="loading" class="remote-dir__list">
      <div v-if="canGoUp" class="remote-dir__row remote-dir__row--up" @click="goUp">
        <el-icon :size="16"><Back /></el-icon>
        <span class="remote-dir__row-name">返回上级</span>
      </div>
      <div
        v-for="item in filteredItems"
        :key="item.id"
        class="remote-dir__row"
        @click="enterDir(item)"
      >
        <el-icon :size="16"><FolderOpened /></el-icon>
        <span class="remote-dir__row-name">{{ item.name }}</span>
        <span class="remote-dir__row-enter">进入 ›</span>
      </div>
      <el-empty
        v-if="!loading && filteredItems.length === 0"
        :description="emptyDescription"
        :image-size="60"
      />
    </div>

    <div class="remote-dir__footer">
      <div class="remote-dir__selected">
        <span class="remote-dir__selected-label">当前目录（将上传到此）</span>
        <strong class="remote-dir__selected-path">{{ current.path }}</strong>
      </div>
      <el-button type="primary" @click="confirmSelect">选择此目录</el-button>
    </div>

    <p class="remote-dir__tip">测试与联调请仅使用 123 云盘 /test 目录；目录不存在时请先在网盘手工创建。</p>
  </div>
</template>

<style scoped lang="scss">
.remote-dir {
  display: flex;
  flex-direction: column;
  gap: var(--up-strm-space-3, 12px);

  &__breadcrumb {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--up-strm-space-1, 4px);
    padding: var(--up-strm-space-2, 8px) var(--up-strm-space-3, 12px);
    background: var(--el-fill-color-light);
    border-radius: var(--up-strm-radius-sm, 6px);
  }

  &__crumb {
    padding: 0 var(--up-strm-space-1, 4px);
    font-size: var(--up-strm-font-size-sm, 13px);

    &.is-current {
      font-weight: 600;
    }
  }

  &__sep {
    color: var(--el-text-color-placeholder);
  }

  &__refresh {
    margin-left: auto;
  }

  &__list {
    min-height: 240px;
    max-height: 340px;
    overflow-y: auto;
    border: 1px solid var(--el-border-color-lighter);
    border-radius: var(--up-strm-radius-sm, 6px);
  }

  &__row {
    display: flex;
    align-items: center;
    gap: var(--up-strm-space-2, 8px);
    padding: var(--up-strm-space-2, 8px) var(--up-strm-space-3, 12px);
    cursor: pointer;
    transition: background-color 0.15s;

    & + & {
      border-top: 1px solid var(--el-border-color-lighter);
    }

    &:hover {
      background: var(--el-color-primary-light-9);
    }

    &--up {
      color: var(--el-text-color-secondary);
    }

    &-name {
      flex: 1;
      min-width: 0;
      overflow: hidden;
      font-size: var(--up-strm-font-size-sm, 13px);
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    &-enter {
      color: var(--el-text-color-placeholder);
      font-size: var(--up-strm-font-size-xs, 12px);
    }
  }

  &__footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--up-strm-space-3, 12px);
    padding: var(--up-strm-space-2, 8px) var(--up-strm-space-3, 12px);
    background: var(--el-fill-color-light);
    border-radius: var(--up-strm-radius-sm, 6px);
  }

  &__selected {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  &__selected-label {
    font-size: var(--up-strm-font-size-xs, 12px);
    color: var(--el-text-color-secondary);
  }

  &__selected-path {
    overflow: hidden;
    color: var(--el-color-primary);
    font-family: ui-monospace, 'SFMono-Regular', Consolas, monospace;
    font-size: var(--up-strm-font-size-md, 14px);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__tip {
    margin: 0;
    font-size: var(--up-strm-font-size-xs, 12px);
    color: var(--el-text-color-placeholder);
  }
}
</style>
