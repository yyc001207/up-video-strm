<script setup lang="ts">
/**
 * 左侧导航：232px 单列，模块手风琴（同一时刻只展开一个），可折叠为 72px。
 * 组内只记忆中当前模块（不记忆具体页面）；「开始执行」显示运行中数量徽标。
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowDown,
  Cpu,
  Film,
  Setting,
  MagicStick,
  Odometer,
  Connection,
  Expand,
  Fold
} from '@element-plus/icons-vue'

import { useRunningStore } from '@/stores/running'

const props = defineProps<{ collapsed: boolean }>()
const emit = defineEmits<{ toggle: [] }>()

const route = useRoute()
const router = useRouter()
const running = useRunningStore()

interface NavPage {
  path: string
  label: string
  /** 运行中数量来源：非空时在右侧显示徽标。 */
  badge?: 'schedule' | 'upload' | 'automation'
}

interface NavGroup {
  id: string
  label: string
  icon: unknown
  pages: NavPage[]
}

const GROUPS: NavGroup[] = [
  {
    id: 'schedule',
    label: 'STRM 生成',
    icon: Film,
    pages: [
      { path: '/schedule/tasks', label: '任务' },
      { path: '/schedule/execution', label: '开始执行', badge: 'schedule' },
      { path: '/schedule/realtime', label: '运行详情' },
      { path: '/schedule/history', label: '运行记录' }
    ]
  },
  {
    id: 'upload',
    label: '云盘上传',
    icon: Cpu,
    pages: [
      { path: '/upload/tasks', label: '任务' },
      { path: '/upload/rename', label: '命名规则' },
      { path: '/upload/execution', label: '开始执行', badge: 'upload' },
      { path: '/upload/realtime', label: '运行详情' },
      { path: '/upload/history', label: '运行记录' }
    ]
  },
  {
    id: 'automation',
    label: '自动追更',
    icon: MagicStick,
    pages: [
      { path: '/automation/tasks', label: '任务' },
      { path: '/automation/execution', label: '开始执行', badge: 'automation' },
      { path: '/automation/realtime', label: '运行详情' },
      { path: '/automation/history', label: '运行记录' }
    ]
  }
]

const FOOTER: NavPage[] = [
  { path: '/config', label: '连接与格式' },
  { path: '/settings', label: '设置' }
]

const OPEN_GROUP_KEY = 'up-video-strm-nav-open-group'

function readStorage(key: string, fallback = ''): string {
  try {
    return localStorage.getItem(key) ?? fallback
  } catch {
    return fallback
  }
}

function writeStorage(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* 忽略隐私模式下的写入失败 */
  }
}

/** path → 所属模块。 */
const moduleOfPath = computed(() => {
  for (const group of GROUPS) {
    const page = group.pages.find(item => route.path.startsWith(item.path))
    if (page) return group.id
  }
  return ''
})

const openGroup = ref(readStorage(OPEN_GROUP_KEY) || 'schedule')

watch(
  () => route.path,
  () => {
    const module = moduleOfPath.value
    if (!module) return
    openGroup.value = module
    writeStorage(OPEN_GROUP_KEY, module)
  },
  { immediate: true }
)

const isToday = computed(() => route.path === '/')

function groupActive(groupId: string): boolean {
  return moduleOfPath.value === groupId
}

function pageActive(path: string): boolean {
  return route.path === path
}

function toggleGroup(group: NavGroup): void {
  if (props.collapsed) {
    emit('toggle')
    openGroup.value = group.id
    return
  }
  openGroup.value = openGroup.value === group.id ? '' : group.id
  writeStorage(OPEN_GROUP_KEY, openGroup.value)
}

function go(path: string): void {
  if (route.path !== path) router.push(path)
}

function badgeValue(kind?: NavPage['badge']): number {
  if (kind === 'schedule') return running.scheduleCount
  if (kind === 'upload') return running.uploadCount
  if (kind === 'automation') return running.automationCount
  return 0
}
</script>

<template>
  <aside class="app-sidebar" :class="{ 'is-collapsed': collapsed }">
    <div class="app-sidebar__brand">
      <span class="app-sidebar__logo" aria-hidden="true">uv</span>
      <span v-if="!collapsed" class="app-sidebar__title">up-video-strm</span>
      <button
        class="app-sidebar__collapse"
        type="button"
        :title="collapsed ? '展开导航' : '收起导航'"
        :aria-label="collapsed ? '展开导航' : '收起导航'"
        @click="emit('toggle')"
      >
        <el-icon :size="16"><Expand v-if="collapsed" /><Fold v-else /></el-icon>
      </button>
    </div>

    <nav class="app-sidebar__nav" aria-label="主导航">
      <button
        class="nav-item nav-item--today"
        type="button"
        :class="{ 'is-active': isToday }"
        :title="collapsed ? '今天' : undefined"
        @click="go('/')"
      >
        <el-icon :size="20"><Odometer /></el-icon>
        <span v-if="!collapsed" class="nav-item__label">今天</span>
      </button>

      <template v-for="group in GROUPS" :key="group.id">
        <button
          class="nav-group__head"
          type="button"
          :class="{ 'is-active': groupActive(group.id) }"
          :title="collapsed ? group.label : undefined"
          @click="toggleGroup(group)"
        >
          <el-icon :size="20"><component :is="group.icon" /></el-icon>
          <span v-if="!collapsed" class="nav-group__label">{{ group.label }}</span>
          <el-icon
            v-if="!collapsed"
            class="nav-group__chevron"
            :class="{ 'is-open': openGroup === group.id }"
            :size="14"
          >
            <ArrowDown />
          </el-icon>
        </button>
        <div
          v-if="!collapsed"
          class="nav-group__wrap"
          :class="{ 'is-open': openGroup === group.id }"
        >
          <div class="nav-group__body">
            <button
              v-for="page in group.pages"
              :key="page.path"
              class="nav-item"
              type="button"
              :class="{ 'is-active': pageActive(page.path) }"
              @click="go(page.path)"
            >
              <span class="nav-item__label">{{ page.label }}</span>
              <span v-if="badgeValue(page.badge) > 0" class="nav-item__badge">
                {{ badgeValue(page.badge) }}
              </span>
            </button>
          </div>
        </div>
      </template>
    </nav>

    <div class="app-sidebar__footer">
      <button
        v-for="item in FOOTER"
        :key="item.path"
        class="nav-item"
        type="button"
        :class="{ 'is-active': pageActive(item.path) }"
        :title="collapsed ? item.label : undefined"
        @click="go(item.path)"
      >
        <el-icon :size="20">
          <Connection v-if="item.path === '/config'" />
          <Setting v-else />
        </el-icon>
        <span v-if="!collapsed" class="nav-item__label">{{ item.label }}</span>
      </button>
    </div>
  </aside>
</template>

<style scoped lang="scss">
.app-sidebar {
  display: flex;
  flex: none;
  flex-direction: column;
  width: var(--up-strm-sidebar-width);
  height: 100%;
  padding: var(--up-strm-space-3) var(--up-strm-space-2);
  border-right: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
  transition: width var(--up-strm-dur-base) var(--up-strm-ease);

  &.is-collapsed {
    width: var(--up-strm-sidebar-collapsed);
    align-items: center;
    padding-inline: 4px;
  }
}

.app-sidebar__brand {
  display: flex;
  flex: none;
  align-items: center;
  gap: 8px;
  height: 40px;
  padding: 0 6px;
}

.app-sidebar__logo {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: var(--up-primary-500);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: -0.5px;
}

.app-sidebar__title {
  flex: 1;
  overflow: hidden;
  color: var(--el-text-color-primary);
  font-size: var(--up-strm-font-size-sm);
  font-weight: 500;
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
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
  min-height: 0;
  margin-top: var(--up-strm-space-4);
  overflow-y: auto;
}

.nav-item,
.nav-group__head {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  height: 36px;
  padding: 0 10px;
  border: none;
  border-radius: var(--up-strm-radius-md);
  background: transparent;
  color: var(--el-text-color-regular);
  font-size: var(--up-strm-font-size-sm);
  font-weight: 400;
  cursor: pointer;
  transition:
    background var(--up-strm-dur-fast) var(--up-strm-ease),
    color var(--up-strm-dur-fast) var(--up-strm-ease);

  &:hover {
    background: var(--el-fill-color-light);
    color: var(--el-text-color-primary);
  }

  &.is-active {
    background: var(--up-primary-50);
    color: var(--up-primary-600);
  }
}

.nav-item--today {
  margin-bottom: 6px;
}

.nav-group__head {
  margin-top: 2px;
}

.nav-group__label {
  flex: 1;
  text-align: left;
}

.nav-group__chevron {
  flex: none;
  color: var(--el-text-color-secondary);
  transition: transform var(--up-strm-dur-fast) var(--up-strm-ease);

  &.is-open {
    transform: rotate(0deg);
  }

  &:not(.is-open) {
    transform: rotate(-90deg);
  }
}

.nav-group__wrap {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows var(--up-strm-dur-base) var(--up-strm-ease);

  &.is-open {
    grid-template-rows: 1fr;
  }
}

.nav-group__body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-height: 0;
  padding: 2px 0 6px 20px;
  overflow: hidden;
}

.nav-item__label {
  flex: 1;
  overflow: hidden;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nav-item__badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: var(--up-primary-100);
  color: var(--up-primary-600);
  font-size: 11px;
  font-weight: 500;
}

.app-sidebar__footer {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-top: var(--up-strm-space-3);
  border-top: 1px solid var(--el-border-color-lighter);
}

.is-collapsed {
  .nav-item,
  .nav-group__head {
    justify-content: center;
    padding: 0;
  }

  .app-sidebar__brand {
    flex-direction: row;
    justify-content: center;
    gap: 4px;
    height: 40px;
    padding: 0;
  }
}
</style>
