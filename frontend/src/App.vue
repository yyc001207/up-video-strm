<script setup lang="ts">
/**
 * 应用壳层：232px 手风琴侧栏 + 48px 顶栏 + 内容区。
 * 全局每 30s 轮询运行状态（页面隐藏时跳过）；离线时内容区顶部出现一条细横幅。
 */
import { computed, onBeforeUnmount, onMounted, ref, watchEffect } from 'vue'
import { useRoute } from 'vue-router'

import AppSidebar from '@/components/AppSidebar.vue'
import PageHeader from '@/components/PageHeader.vue'
import TopBar from '@/components/TopBar.vue'
import { RUNNING_POLL_MS, useRunningStore } from '@/stores/running'

const COLLAPSE_KEY = 'up-video-strm-sidebar-collapsed'

const route = useRoute()
const runningStore = useRunningStore()

const collapsed = ref(readCollapsed())
const offlineDismissed = ref(false)
let pollTimer: ReturnType<typeof setInterval> | null = null

const isToday = computed(() => route.path === '/')
const pageTitle = computed(() => (route.meta.title as string | undefined) ?? '')
const pageDescription = computed(() => (route.meta.description as string | undefined) ?? '')
const showOfflineAlert = computed(() => runningStore.offline && !offlineDismissed.value)

watchEffect(() => {
  const title = pageTitle.value
  document.title = title ? `${title} - up-video-strm` : 'up-video-strm 控制台'
})

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === '1'
  } catch {
    return false
  }
}

function toggleCollapsed(): void {
  collapsed.value = !collapsed.value
  try {
    localStorage.setItem(COLLAPSE_KEY, collapsed.value ? '1' : '0')
  } catch {
    /* 忽略隐私模式下的写入失败 */
  }
}

async function refreshRunning(): Promise<void> {
  try {
    await runningStore.fetchCounts()
    offlineDismissed.value = false
  } catch {
    /* fetchCounts 内部已记录离线状态 */
  }
}

onMounted(() => {
  void refreshRunning()
  pollTimer = setInterval(() => {
    if (document.hidden) return
    void refreshRunning()
  }, RUNNING_POLL_MS)
})

onBeforeUnmount(() => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
})
</script>

<template>
  <div class="app-shell" :class="{ 'is-collapsed': collapsed }">
    <AppSidebar :collapsed="collapsed" @toggle="toggleCollapsed" />

    <div class="app-main">
      <TopBar />

      <div v-if="showOfflineAlert" class="app-offline" role="status">
        <span class="app-offline__dot" />
        <span class="app-offline__text">后端连接中断，正在自动重试；页面上的数据可能不是最新。</span>
        <button class="app-offline__close" type="button" @click="offlineDismissed = true">
          知道了
        </button>
      </div>

      <main class="app-content">
        <PageHeader
          v-if="!isToday && pageTitle"
          :title="pageTitle"
          :description="pageDescription"
        />
        <router-view />
      </main>
    </div>
  </div>
</template>

<style scoped lang="scss">
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--el-bg-color-page);
}

.app-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  height: 100vh;
}

.app-content {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.app-offline {
  display: flex;
  flex: none;
  align-items: center;
  gap: 8px;
  height: 32px;
  padding: 0 var(--up-strm-space-6);
  border-bottom: 1px solid var(--up-warning-bg);
  background: var(--up-warning-bg);
  color: var(--up-warning-text);
  font-size: var(--up-strm-font-size-xs);
}

.app-offline__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--up-warning-mark);
}

.app-offline__text {
  flex: 1;
}

.app-offline__close {
  border: none;
  background: transparent;
  color: inherit;
  font-size: inherit;
  font-weight: 600;
  cursor: pointer;
}

@media (max-width: 1279px) {
  .app-offline {
    padding: 0 var(--up-strm-space-5);
  }
}
</style>
