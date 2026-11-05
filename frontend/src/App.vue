<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watchEffect } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Calendar,
  Clock,
  Document,
  EditPen,
  Expand,
  Fold,
  Monitor,
  MagicStick,
  Setting,
  Upload,
  VideoPlay
} from '@element-plus/icons-vue'
import type { Component } from 'vue'

import ThemeToggle from '@/components/ThemeToggle.vue'
import { RUNNING_POLL_MS, useRunningStore } from '@/stores/running'

interface NavPage {
  path: string
  label: string
  icon: Component
  badge?: 'running' | 'upload-running'
}

interface NavGroup {
  /** 分组标题；单页模块可省略，直接平铺页面项。 */
  title?: string
  pages: NavPage[]
}

interface NavModule {
  id: string
  label: string
  icon: Component
  /** 模块路由命名空间前缀，用于判定当前所属模块。 */
  basePath: string
  groups: NavGroup[]
}

/**
 * 模块 → 页面两级导航清单（数据驱动）：
 * 新增平级模块只需在 modules 中追加一项，壳层代码无需改动。
 */
const modules: NavModule[] = [
  {
    id: 'config',
    label: '全局配置',
    icon: Setting,
    basePath: '/config',
    groups: [
      {
        // 单页模块：不显示分组标题，直接平铺页面项
        pages: [{ path: '/config', label: '全局配置', icon: Setting }]
      }
    ]
  },
  {
    id: 'schedule',
    label: '任务调度',
    icon: Calendar,
    basePath: '/schedule',
    groups: [
      {
        title: '配置',
        pages: [{ path: '/schedule/tasks', label: '任务配置', icon: Document }]
      },
      {
        title: '运行',
        pages: [
          { path: '/schedule/execution', label: '执行管理', icon: VideoPlay },
          { path: '/schedule/realtime', label: '实时日志', icon: Monitor, badge: 'running' }
        ]
      },
      {
        title: '记录',
        pages: [{ path: '/schedule/history', label: '任务历史', icon: Clock }]
      }
    ]
  },
  {
    id: 'upload',
    label: '上传管理',
    icon: Upload,
    basePath: '/upload',
    groups: [
      {
        title: '配置',
        pages: [
          { path: '/upload/tasks', label: '任务配置', icon: Document },
          { path: '/upload/rename', label: '重命名规则', icon: EditPen }
        ]
      },
      {
        title: '运行',
        pages: [
          { path: '/upload/execution', label: '执行管理', icon: VideoPlay },
          { path: '/upload/realtime', label: '实时日志', icon: Monitor, badge: 'upload-running' }
        ]
      },
      {
        title: '记录',
        pages: [{ path: '/upload/history', label: '任务历史', icon: Clock }]
      }
    ]
  },
  {
    id: 'automation',
    label: '自动化任务',
    icon: MagicStick,
    basePath: '/automation',
    groups: [
      {
        title: '配置',
        pages: [{ path: '/automation/tasks', label: '任务配置', icon: Document }]
      }
    ]
  }
]

const COLLAPSE_KEY = 'up-video-strm-sidebar-collapsed'

const route = useRoute()
const router = useRouter()
const runningStore = useRunningStore()

const collapsed = ref(readCollapsed())
const offlineDismissed = ref(false)
let pollTimer: ReturnType<typeof setInterval> | null = null

const currentModule = computed(
  () => modules.find(module => route.path.startsWith(module.basePath)) ?? null
)
const flatPages = computed(() => currentModule.value?.groups.flatMap(group => group.pages) ?? [])
/** 顶栏标题：「模块 · 页面」；单页模块同名只显示一次，无模块归属时退回页面标题。 */
const pageTitle = computed(() => {
  const moduleLabel = currentModule.value?.label
  const title = route.meta.title as string | undefined
  if (moduleLabel && title && title !== moduleLabel) return `${moduleLabel} · ${title}`
  return title ?? moduleLabel ?? 'up-video-strm 控制台'
})
const pageDescription = computed(() => (route.meta.description as string | undefined) ?? '')

// 页面标题同步到浏览器标签页（桌面端即窗口标题）。
watchEffect(() => {
  const title = pageTitle.value
  document.title = title === 'up-video-strm 控制台' ? title : `${title} - up-video-strm`
})

/** 顶栏状态胶囊三态：连接失败（30s 内失败）优先于运行中，其余为空闲。 */
type CapsuleState = 'error' | 'busy' | 'idle'
const capsuleState = computed<CapsuleState>(() => {
  if (runningStore.isConnectFailed()) return 'error'
  return runningStore.total > 0 ? 'busy' : 'idle'
})
const capsuleText = computed(() => {
  if (capsuleState.value === 'error') return '连接失败'
  if (capsuleState.value === 'busy') return `运行中 ${runningStore.total}`
  return '空闲'
})
const showOfflineAlert = computed(() => runningStore.offline && !offlineDismissed.value)

/** 导航徽标值：任务调度与上传管理分别取各自模块的运行数。 */
function badgeCount(badge: NavPage['badge']): number {
  if (badge === 'running') return runningStore.scheduleCount
  if (badge === 'upload-running') return runningStore.uploadCount
  return 0
}

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === '1'
  } catch {
    return false
  }
}

function toggleCollapsed() {
  collapsed.value = !collapsed.value
  try {
    localStorage.setItem(COLLAPSE_KEY, collapsed.value ? '1' : '0')
  } catch {
    // 忽略隐私模式等场景下的写入失败
  }
}

function goModule(module: NavModule) {
  router.push(module.groups[0]?.pages[0]?.path ?? '/')
}

function isActive(path: string): boolean {
  return route.path === path
}

/** 按运行来源分流：调度优先，其次上传；都空闲时维持跳任务调度实时日志。 */
function goRealtime() {
  if (runningStore.scheduleCount > 0) {
    router.push('/schedule/realtime')
  } else if (runningStore.uploadCount > 0) {
    router.push('/upload/realtime')
  } else {
    router.push('/schedule/realtime')
  }
}

async function refreshRunning() {
  try {
    await runningStore.fetchCounts()
    offlineDismissed.value = false
  } catch {
    // fetchCounts 内部已记录离线状态，这里不再重复提示
  }
}

onMounted(() => {
  void refreshRunning()
  pollTimer = setInterval(() => void refreshRunning(), RUNNING_POLL_MS)
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
    <aside class="app-sidebar">
      <div class="app-sidebar__brand">
        <span class="app-sidebar__logo">UV</span>
        <span v-if="!collapsed" class="app-sidebar__name">up-video-strm</span>
        <button
          class="app-sidebar__collapse"
          type="button"
          :aria-label="collapsed ? '展开侧栏' : '折叠侧栏'"
          @click="toggleCollapsed"
        >
          <el-icon :size="16"><component :is="collapsed ? Expand : Fold" /></el-icon>
        </button>
      </div>

      <nav class="app-sidebar__nav">
        <div class="nav-modules">
          <button
            v-for="module in modules"
            :key="module.id"
            class="nav-module"
            :class="{ 'nav-module--active': currentModule?.id === module.id }"
            type="button"
            :title="module.label"
            @click="goModule(module)"
          >
            <el-icon :size="18"><component :is="module.icon" /></el-icon>
            <span v-if="!collapsed" class="nav-module__label">{{ module.label }}</span>
          </button>
        </div>

        <template v-if="currentModule">
          <template v-if="!collapsed">
            <div v-for="group in currentModule.groups" :key="group.title ?? group.pages[0]?.path" class="nav-group">
              <div v-if="group.title" class="nav-group__title">{{ group.title }}</div>
              <router-link
                v-for="page in group.pages"
                :key="page.path"
                :to="page.path"
                class="nav-page"
                :class="{ 'nav-page--active': isActive(page.path) }"
              >
                <el-icon :size="16"><component :is="page.icon" /></el-icon>
                <span class="nav-page__label">{{ page.label }}</span>
                <span v-if="page.badge && badgeCount(page.badge) > 0" class="nav-page__badge">
                  {{ badgeCount(page.badge) }}
                </span>
              </router-link>
            </div>
          </template>
          <template v-else>
            <router-link
              v-for="page in flatPages"
              :key="page.path"
              :to="page.path"
              class="nav-page nav-page--icon"
              :class="{ 'nav-page--active': isActive(page.path) }"
              :title="page.label"
            >
              <el-icon :size="18"><component :is="page.icon" /></el-icon>
            </router-link>
          </template>
        </template>
      </nav>

      <div class="app-sidebar__footer">
        <router-link
          to="/settings"
          class="nav-page"
          :class="{ 'nav-page--active': isActive('/settings') }"
          :title="collapsed ? '设置' : undefined"
        >
          <el-icon :size="16"><Setting /></el-icon>
          <span v-if="!collapsed" class="nav-page__label">设置</span>
        </router-link>
        <div class="app-sidebar__theme">
          <ThemeToggle />
        </div>
      </div>
    </aside>

    <div class="app-main">
      <header class="app-topbar">
        <div class="app-topbar__heading">
          <h1 class="app-topbar__title">{{ pageTitle }}</h1>
          <p v-if="pageDescription" class="app-topbar__desc">{{ pageDescription }}</p>
        </div>
        <div class="app-topbar__actions">
          <button
            class="run-capsule"
            :class="`run-capsule--${capsuleState}`"
            type="button"
            :aria-label="`运行状态：${capsuleText}`"
            @click="goRealtime"
          >
            <span class="run-capsule__dot" />
            <span>{{ capsuleText }}</span>
          </button>
        </div>
      </header>

      <el-alert
        v-if="showOfflineAlert"
        class="app-offline"
        type="error"
        :closable="true"
        show-icon
        title="无法连接后端服务，正在自动重试…"
        @close="offlineDismissed = true"
      />

      <main class="app-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<style scoped lang="scss">
.app-shell {
  display: flex;
  height: 100%;
  overflow: hidden;
  background: var(--el-bg-color-page);
}

.app-sidebar {
  display: flex;
  flex: none;
  flex-direction: column;
  width: var(--up-strm-sidebar-width);
  height: 100%;
  border-right: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
  transition: width 0.2s ease;
}

.is-collapsed .app-sidebar {
  width: var(--up-strm-sidebar-collapsed-width);
}

.app-sidebar__brand {
  display: flex;
  align-items: center;
  gap: var(--up-strm-space-2);
  height: var(--up-strm-topbar-height);
  padding: 0 var(--up-strm-space-3);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.app-sidebar__logo {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: var(--up-strm-radius-sm);
  background: var(--el-color-primary);
  color: var(--el-color-white);
  font-size: var(--up-strm-font-size-xs);
  font-weight: 700;
  letter-spacing: 0.02em;
}

.app-sidebar__name {
  flex: 1;
  overflow: hidden;
  color: var(--el-text-color-primary);
  font-size: var(--up-strm-font-size-base);
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-sidebar__collapse {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  margin-left: auto;
  border: none;
  border-radius: var(--up-strm-radius-sm);
  background: transparent;
  color: var(--el-text-color-secondary);
  cursor: pointer;

  &:hover {
    background: var(--el-fill-color-light);
    color: var(--el-text-color-primary);
  }
}

.app-sidebar__nav {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: var(--up-strm-space-3) var(--up-strm-space-2);
}

.nav-modules {
  display: flex;
  flex-direction: column;
  gap: var(--up-strm-space-1);
  padding-bottom: var(--up-strm-space-2);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.nav-module {
  display: flex;
  align-items: center;
  gap: var(--up-strm-space-2);
  width: 100%;
  height: 36px;
  padding: 0 var(--up-strm-space-3);
  border: none;
  border-radius: var(--up-strm-radius-sm);
  background: transparent;
  color: var(--el-text-color-regular);
  font-size: var(--up-strm-font-size-base);
  text-align: left;
  cursor: pointer;

  &:hover {
    background: var(--el-fill-color-light);
    color: var(--el-text-color-primary);
  }

  &--active {
    color: var(--el-color-primary);
    font-weight: 600;
  }

  &__label {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.nav-group {
  margin-top: var(--up-strm-space-3);

  &__title {
    padding: 0 var(--up-strm-space-3) var(--up-strm-space-1);
    color: var(--el-text-color-secondary);
    font-size: var(--up-strm-font-size-xs);
    font-weight: 600;
    letter-spacing: 0.04em;
  }
}

.nav-page {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--up-strm-space-2);
  height: 36px;
  padding: 0 var(--up-strm-space-3);
  border-radius: var(--up-strm-radius-sm);
  color: var(--el-text-color-regular);
  font-size: var(--up-strm-font-size-base);

  &:hover {
    background: var(--el-fill-color-light);
    color: var(--el-text-color-primary);
  }

  // 选中态：主色文字 + 主色 12% 底 + 左侧 2px 主色指示条。
  // 刻意不改 font-weight：微软雅黑会把 600 映射为 Bold，导致选中项文字变宽跳位。
  &--active {
    background: color-mix(in srgb, var(--el-color-primary) 12%, transparent);
    color: var(--el-color-primary);

    &::before {
      content: '';
      position: absolute;
      top: 9px;
      bottom: 9px;
      left: 0;
      width: 2px;
      border-radius: 1px;
      background: var(--el-color-primary);
    }
  }

  &--icon {
    justify-content: center;
    padding: 0;
  }

  &__label {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 18px;
    height: 18px;
    padding: 0 5px;
    border-radius: 9px;
    background: var(--el-color-warning);
    color: var(--el-color-white);
    font-size: var(--up-strm-font-size-xs);
    font-weight: 600;
    line-height: 1;
  }
}

.app-sidebar__footer {
  display: flex;
  align-items: center;
  gap: var(--up-strm-space-2);
  padding: var(--up-strm-space-2);
  border-top: 1px solid var(--el-border-color-lighter);

  .nav-page {
    flex: 1;
    min-width: 0;
  }

  .app-sidebar__theme {
    flex: none;
  }
}

.is-collapsed .app-sidebar__footer {
  flex-direction: column;

  .app-sidebar__theme {
    display: none;
  }
}

.app-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  height: 100%;
}

.app-topbar {
  display: flex;
  flex: none;
  align-items: center;
  gap: var(--up-strm-space-4);
  height: var(--up-strm-topbar-height);
  padding: 0 var(--up-strm-space-6);
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
}

.app-topbar__heading {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  justify-content: center;
}

.app-topbar__title {
  margin: 0;
  overflow: hidden;
  color: var(--el-text-color-primary);
  font-size: var(--up-strm-font-size-xl);
  font-weight: 600;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-topbar__desc {
  margin: 0;
  overflow: hidden;
  color: var(--el-text-color-secondary);
  font-size: var(--up-strm-font-size-xs);
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-topbar__actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: var(--up-strm-space-3);
}

.run-capsule {
  display: inline-flex;
  align-items: center;
  gap: var(--up-strm-space-2);
  height: 32px;
  padding: 0 var(--up-strm-space-3);
  border: 1px solid var(--el-border-color);
  border-radius: 16px;
  background: var(--el-bg-color);
  color: var(--el-text-color-secondary);
  font-size: var(--up-strm-font-size-xs);
  cursor: pointer;

  &:hover {
    border-color: var(--el-color-primary);
    color: var(--el-color-primary);
  }

  &__dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--el-color-info);
  }

  &--busy {
    border-color: var(--el-color-warning-light-5);
    color: var(--el-text-color-primary);

    .run-capsule__dot {
      background: var(--el-color-warning);
    }
  }

  &--error {
    border-color: var(--el-color-danger-light-5);
    color: var(--el-color-danger);

    .run-capsule__dot {
      background: var(--el-color-danger);
    }
  }
}

.app-offline {
  margin: var(--up-strm-space-2) var(--up-strm-space-4) 0;
}

.app-content {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
</style>
