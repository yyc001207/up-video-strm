<script setup lang="ts">
/**
 * 命令面板（Next UI P5）：Ctrl/Cmd + K 打开，输入即搜索页面，回车跳转。
 * 只在前端做页面级导航，不请求任何接口；别名同时匹配旧名称，便于老用户过渡。
 */
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

interface PaletteItem {
  path: string
  label: string
  group: string
  /** 额外可匹配词：旧名称、模块别名。 */
  aliases: string
  description?: string
}

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: boolean): void }>()

const router = useRouter()

const ITEMS: PaletteItem[] = [
  { path: '/', label: '今天', group: '总览', aliases: 'today home 首页 今天' },
  { path: '/schedule/tasks', label: '任务', group: 'STRM 生成', aliases: '任务配置 任务调度 strm 媒体库' },
  { path: '/schedule/execution', label: '开始执行', group: 'STRM 生成', aliases: '执行管理 运行 生成 启动' },
  { path: '/schedule/realtime', label: '运行详情', group: 'STRM 生成', aliases: '实时日志 日志 进度' },
  { path: '/schedule/history', label: '运行记录', group: 'STRM 生成', aliases: '任务历史 历史 执行记录' },
  { path: '/upload/tasks', label: '任务', group: '云盘上传', aliases: '上传任务 上传管理 云盘' },
  { path: '/upload/rename', label: '命名规则', group: '云盘上传', aliases: '重命名规则 命名 剧集' },
  { path: '/upload/execution', label: '开始执行', group: '云盘上传', aliases: '上传执行 上传 开始' },
  { path: '/upload/realtime', label: '运行详情', group: '云盘上传', aliases: '上传日志 实时日志' },
  { path: '/upload/history', label: '运行记录', group: '云盘上传', aliases: '上传历史 任务历史' },
  { path: '/automation/tasks', label: '任务配置', group: '自动追更', aliases: '自动化任务 追更 自动' },
  { path: '/automation/execution', label: '开始执行', group: '自动追更', aliases: '自动化执行 追更执行' },
  { path: '/automation/realtime', label: '运行详情', group: '自动追更', aliases: '自动化日志 实时日志' },
  { path: '/automation/history', label: '运行记录', group: '自动追更', aliases: '自动化历史 任务历史' },
  { path: '/renamer', label: '批量改名', group: '本地改名', aliases: '重命名 rename 剧集 sxxexx 字幕 季 拆分' },
  { path: '/config', label: '连接与格式', group: '全局', aliases: '全局配置 config openlist 云盘 格式 生成设置' },
  { path: '/settings', label: '设置', group: '全局', aliases: 'settings 主题 外观 关于' }
]

const keyword = ref('')
const activeIndex = ref(0)
const inputRef = ref<HTMLInputElement | null>(null)
const listRef = ref<HTMLElement | null>(null)

const filtered = computed<PaletteItem[]>(() => {
  const needle = keyword.value.trim().toLowerCase()
  if (!needle) return ITEMS
  return ITEMS.filter(item =>
    `${item.label} ${item.group} ${item.aliases}`.toLowerCase().includes(needle)
  )
})

const grouped = computed(() => {
  const map = new Map<string, PaletteItem[]>()
  for (const item of filtered.value) {
    const list = map.get(item.group) ?? []
    list.push(item)
    map.set(item.group, list)
  }
  return [...map.entries()].map(([group, items]) => ({ group, items }))
})

watch(
  () => props.modelValue,
  async open => {
    if (open) {
      keyword.value = ''
      activeIndex.value = 0
      await nextTick()
      inputRef.value?.focus()
    }
  }
)

watch(keyword, () => {
  activeIndex.value = 0
})

function close(): void {
  emit('update:modelValue', false)
}

function go(item: PaletteItem): void {
  close()
  if (router.currentRoute.value.path !== item.path) void router.push(item.path)
}

function move(step: number): void {
  const total = filtered.value.length
  if (total === 0) return
  activeIndex.value = (activeIndex.value + step + total) % total
  void nextTick(() => {
    const el = listRef.value?.querySelector<HTMLElement>(`[data-index="${activeIndex.value}"]`)
    el?.scrollIntoView({ block: 'nearest' })
  })
}

function onInputKeydown(event: KeyboardEvent): void {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    move(1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    move(-1)
  } else if (event.key === 'Enter') {
    event.preventDefault()
    const item = filtered.value[activeIndex.value]
    if (item) go(item)
  } else if (event.key === 'Escape') {
    event.preventDefault()
    close()
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="palette">
      <div v-if="modelValue" class="palette-mask" @click.self="close">
        <div class="palette" role="dialog" aria-modal="true" aria-label="命令面板">
          <input
            ref="inputRef"
            v-model="keyword"
            class="palette__input"
            type="text"
            placeholder="搜索页面或功能…"
            autocomplete="off"
            spellcheck="false"
            @keydown="onInputKeydown"
          />

          <div ref="listRef" class="palette__list">
            <template v-if="filtered.length > 0">
              <div v-for="section in grouped" :key="section.group" class="palette__group">
                <div class="palette__group-title">{{ section.group }}</div>
                <button
                  v-for="item in section.items"
                  :key="item.path"
                  type="button"
                  class="palette__item"
                  :class="{ 'is-active': filtered.indexOf(item) === activeIndex }"
                  :data-index="filtered.indexOf(item)"
                  @click="go(item)"
                  @mousemove="activeIndex = filtered.indexOf(item)"
                >
                  <span class="palette__label">{{ item.label }}</span>
                  <span class="palette__path">{{ item.path }}</span>
                </button>
              </div>
            </template>
            <div v-else class="palette__empty">没有匹配的页面，换个关键词试试。</div>
          </div>

          <div class="palette__footer">
            <span><kbd>↑</kbd><kbd>↓</kbd> 选择</span>
            <span><kbd>Enter</kbd> 跳转</span>
            <span><kbd>Esc</kbd> 关闭</span>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped lang="scss">
.palette-mask {
  position: fixed;
  inset: 0;
  z-index: 4000;
  display: flex;
  justify-content: center;
  padding-top: 14vh;
  background: rgba(22, 19, 26, 0.42);
  backdrop-filter: blur(2px);
}

.palette {
  display: flex;
  flex-direction: column;
  width: min(560px, calc(100vw - 48px));
  max-height: 60vh;
  overflow: hidden;
  border: 1px solid var(--el-border-color-light);
  border-radius: var(--up-strm-radius-xl);
  background: var(--el-bg-color-overlay);
  box-shadow: var(--up-strm-shadow-lg);

  &__input {
    flex: none;
    height: 52px;
    padding: 0 var(--up-strm-space-5);
    border: none;
    border-bottom: 1px solid var(--el-border-color-lighter);
    background: transparent;
    color: var(--el-text-color-primary);
    font-family: var(--up-strm-font-ui);
    font-size: var(--up-strm-font-size-lg);
    outline: none;

    &::placeholder {
      color: var(--el-text-color-placeholder);
    }
  }

  &__list {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: var(--up-strm-space-2);
  }

  &__group + &__group {
    margin-top: var(--up-strm-space-2);
    padding-top: var(--up-strm-space-2);
    border-top: 1px solid var(--el-border-color-lighter);
  }

  &__group-title {
    padding: 6px 10px 4px;
    color: var(--el-text-color-secondary);
    font-size: var(--up-strm-font-size-xs);
  }

  &__item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--up-strm-space-4);
    width: 100%;
    padding: 9px 10px;
    border: none;
    border-radius: var(--up-strm-radius-sm);
    background: transparent;
    color: var(--el-text-color-regular);
    cursor: pointer;
    font-family: var(--up-strm-font-ui);
    font-size: var(--up-strm-font-size-sm);
    text-align: left;

    &.is-active {
      background: var(--up-primary-50);
      color: var(--up-primary-700);
    }
  }

  &__label {
    font-weight: 600;
  }

  &__path {
    color: var(--el-text-color-placeholder);
    font-family: var(--up-strm-font-mono);
    font-size: var(--up-strm-font-size-xs);
  }

  &__empty {
    padding: var(--up-strm-space-6);
    color: var(--el-text-color-secondary);
    font-size: var(--up-strm-font-size-sm);
    text-align: center;
  }

  &__footer {
    flex: none;
    display: flex;
    gap: var(--up-strm-space-5);
    padding: 10px var(--up-strm-space-5);
    border-top: 1px solid var(--el-border-color-lighter);
    color: var(--el-text-color-secondary);
    font-size: var(--up-strm-font-size-xs);

    kbd {
      margin-right: 2px;
      padding: 1px 5px;
      border: 1px solid var(--el-border-color);
      border-radius: 4px;
      background: var(--el-fill-color-light);
      font-family: var(--up-strm-font-mono);
      font-size: 11px;
    }
  }
}

.palette-enter-active,
.palette-leave-active {
  transition: opacity 160ms ease;
}

.palette-enter-from,
.palette-leave-to {
  opacity: 0;
}
</style>
