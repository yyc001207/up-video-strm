<script setup lang="ts">
/** 顶栏 60px 吸顶：两行面包屑 + 运行胶囊 + 连接状态 + 主题切换。 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Search } from '@element-plus/icons-vue'

import ActivityDrawer from '@/components/ActivityDrawer.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
import { useRunningStore } from '@/stores/running'

const route = useRoute()
const running = useRunningStore()
const emit = defineEmits<{ (e: 'open-search'): void }>()
const drawerOpen = ref(false)
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  timer = setInterval(() => (now.value = Date.now()), 5000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})

const MODULE_LABEL: Record<string, string> = {
  schedule: 'STRM 生成',
  upload: '云盘上传',
  automation: '自动追更',
  config: '连接与格式',
  settings: '设置'
}

const moduleId = computed(() => route.path.split('/')[1] ?? '')
const moduleLabel = computed(() => MODULE_LABEL[moduleId.value] ?? '')
const pageLabel = computed(() => (route.meta.title as string | undefined) ?? '')
const pageDescription = computed(() => (route.meta.description as string | undefined) ?? '')

const offline = computed(() => running.isConnectFailed(now.value))
const updateText = computed(() => {
  if (!running.lastUpdatedAt) return ''
  const seconds = Math.max(0, Math.round((now.value - running.lastUpdatedAt) / 1000))
  return seconds < 60 ? `${seconds} 秒前更新` : `${Math.round(seconds / 60)} 分钟前更新`
})
const progressText = computed(() =>
  running.progress === null ? '' : ` · ${running.progress}%`
)
</script>

<template>
  <header class="top-bar">
    <div class="top-bar__crumbs">
      <span class="top-bar__page">{{ pageLabel }}</span>
      <span v-if="moduleLabel || pageDescription" class="top-bar__sub">
        <template v-if="moduleLabel">{{ moduleLabel }}</template>
        <template v-if="moduleLabel && pageDescription"> · </template>
        <template v-if="pageDescription">{{ pageDescription }}</template>
      </span>
    </div>

    <div class="top-bar__actions">
      <button
        class="run-capsule"
        type="button"
        :class="{ 'is-idle': running.total === 0 }"
        :title="running.total > 0 ? '查看正在执行的任务' : '没有正在执行的任务'"
        @click="drawerOpen = true"
      >
        <span class="run-capsule__dot" />
        <template v-if="running.total > 0">
          <span>{{ running.total }} 个在跑{{ progressText }}</span>
        </template>
        <template v-else>
          <span>空闲</span>
        </template>
        <span v-if="updateText" class="run-capsule__time">{{ updateText }}</span>
      </button>

      <span class="conn-status" :class="{ 'is-offline': offline }">
        <span class="conn-status__dot" />
        <span>{{ offline ? '离线' : '已连接' }}</span>
      </span>

      <button
        class="top-bar__search"
        type="button"
        title="搜索页面（Ctrl + K）"
        @click="emit('open-search')"
      >
        <el-icon :size="15"><Search /></el-icon>
        <span class="top-bar__search-hint">搜索</span>
        <kbd class="top-bar__search-kbd">Ctrl K</kbd>
      </button>

      <ThemeToggle />
    </div>

    <ActivityDrawer v-model="drawerOpen" />
  </header>
</template>

<style scoped lang="scss">
.top-bar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  flex: none;
  align-items: center;
  justify-content: space-between;
  gap: var(--up-strm-space-4);
  height: var(--up-strm-topbar-height);
  padding: 0 var(--up-strm-page-pad);
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
}

.top-bar__crumbs {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.top-bar__page {
  overflow: hidden;
  color: var(--el-text-color-primary);
  font-size: var(--up-strm-fs-15);
  font-weight: 600;
  line-height: 20px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.top-bar__sub {
  overflow: hidden;
  color: var(--el-text-color-secondary);
  font-size: var(--up-strm-font-size-xs);
  line-height: 16px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.top-bar__actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: var(--up-strm-space-2);
}

.run-capsule {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 12px;
  border: 1px solid color-mix(in srgb, var(--up-primary-500) 26%, transparent);
  border-radius: 999px;
  background: var(--up-primary-50);
  color: var(--up-primary-600);
  font-size: var(--up-strm-font-size-xs);
  font-weight: 600;
  cursor: pointer;

  &.is-idle {
    border-color: var(--el-border-color-lighter);
    background: transparent;
    color: var(--el-text-color-secondary);
  }

  &__dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentcolor;
    animation: capsule-breathe 2s ease-in-out infinite;
  }

  &.is-idle &__dot {
    animation: none;
    background: var(--el-text-color-placeholder);
  }

  &__time {
    color: var(--el-text-color-secondary);
    font-weight: 400;
  }
}

.conn-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--el-text-color-secondary);
  font-size: var(--up-strm-font-size-xs);
  white-space: nowrap;

  &__dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--up-success-mark);
  }

  &.is-offline {
    color: var(--up-danger-text);

    .conn-status__dot {
      background: var(--up-danger-mark);
    }
  }
}

.top-bar__search {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 8px 0 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 999px;
  background: transparent;
  color: var(--el-text-color-secondary);
  font-size: var(--up-strm-font-size-xs);
  cursor: pointer;

  &:hover {
    border-color: var(--up-primary-500);
    color: var(--up-primary-600);
  }
}

.top-bar__search-kbd {
  padding: 1px 5px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-placeholder);
  font-family: var(--up-strm-font-mono);
  font-size: 11px;
}

@keyframes capsule-breathe {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.4;
  }
}

@media (prefers-reduced-motion: reduce) {
  .run-capsule__dot {
    animation: none;
  }
}
</style>
