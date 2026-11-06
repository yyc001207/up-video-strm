<script lang="ts">
/**
 * 单条日志（复用组件的对外契约）。
 * 过滤逻辑（级别 / 关键字）由调用方完成，本组件只负责渲染与滚动交互。
 */
export interface LogLine {
  /** 行号：过滤后仍保留原始行号，便于定位。 */
  seq: number
  /** 级别：info / warn / error / progress，也允许其他字符串（按 info 处理）。 */
  level: string
  /** 时间戳文本，格式由调用方决定；缺省时不渲染时间列。 */
  ts?: string
  message: string
}
</script>

<script setup lang="ts">
/**
 * 可复用日志终端（Next UI C11 LogTerminal）：深色终端底 + 等宽字体 + 级别着色。
 *
 * - lines 已按调用方需要过滤，seq 保持原始行号；
 * - 行数超过 maxLines 时只渲染末尾部分，避免长时间执行后 DOM 膨胀；
 * - autoScroll 为受控 prop，用户上滚时通过 update:autoScroll 通知调用方暂停，
 *   暂停期间新日志在右下角累计为「N 条新日志」胶囊；
 * - 右键可复制单行或全部日志。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    /** 日志行（调用方负责过滤，组件只负责渲染）。 */
    lines: readonly LogLine[]
    /** 是否自动跟随最新日志，可配合 v-model:auto-scroll 使用。 */
    autoScroll?: boolean
    /** 最多渲染的行数（超出时仅渲染末尾部分）。 */
    maxLines?: number
    /** 空状态文案。 */
    emptyText?: string
  }>(),
  {
    autoScroll: true,
    maxLines: 3000,
    emptyText: '暂无日志'
  }
)

const emit = defineEmits<{
  (e: 'update:autoScroll', value: boolean): void
}>()

/** 距底部小于该值视为「在底部」，避免像素抖动造成误判。 */
const BOTTOM_THRESHOLD = 24

const LEVEL_CLASSES: Record<string, string> = {
  info: 'info',
  warn: 'warn',
  error: 'error',
  progress: 'progress'
}

const LEVEL_LABELS: Record<string, string> = {
  info: 'INFO',
  warn: 'WARN',
  error: 'ERR',
  progress: 'STEP'
}

const viewportRef = ref<HTMLElement | null>(null)

const visibleLines = computed<readonly LogLine[]>(() => {
  const total = props.lines.length
  if (total <= props.maxLines) return props.lines
  return props.lines.slice(total - props.maxLines)
})

/** 因超出 maxLines 而未渲染的行数。 */
const hiddenCount = computed(() => props.lines.length - visibleLines.value.length)

/** 暂停跟随后新到达、用户尚未看到的行数。 */
const unseenCount = ref(0)

/** 右键菜单：位置 + 目标行（null 表示在空白处右键，仅提供「复制全部」）。 */
const menuVisible = ref(false)
const menuX = ref(0)
const menuY = ref(0)
const menuLine = ref<LogLine | null>(null)

function levelClass(level: string): string {
  return LEVEL_CLASSES[level] ?? 'info'
}

function levelLabel(level: string): string {
  return LEVEL_LABELS[level] ?? level.toUpperCase()
}

function scrollToBottom(): void {
  void nextTick(() => {
    const el = viewportRef.value
    if (!el) return
    el.scrollTop = el.scrollHeight
  })
  unseenCount.value = 0
}

function setAutoScroll(value: boolean): void {
  emit('update:autoScroll', value)
  if (value) scrollToBottom()
  else unseenCount.value = 0
}

/** 用户滚动：上滚暂停跟随；手动滚回底部时恢复跟随。 */
function handleScroll(): void {
  const el = viewportRef.value
  if (!el) return
  const bottom = el.scrollHeight - el.scrollTop - el.clientHeight <= BOTTOM_THRESHOLD
  if (!bottom && props.autoScroll) {
    emit('update:autoScroll', false)
  } else if (bottom && !props.autoScroll) {
    emit('update:autoScroll', true)
  }
  menuVisible.value = false
}

/** el-switch 的 change 参数为 boolean | string | number，这里统一收敛为布尔值。 */
function handleSwitchChange(value: string | number | boolean): void {
  setAutoScroll(value === true)
}

function handleBackToBottom(): void {
  setAutoScroll(true)
}

/** 复制文本：优先 Clipboard API，失败时降级为临时 textarea。 */
async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
    return
  } catch {
    /* 降级 */
  }
  const area = document.createElement('textarea')
  area.value = text
  area.style.position = 'fixed'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.select()
  document.execCommand('copy')
  document.body.removeChild(area)
}

function lineText(line: LogLine): string {
  return `${line.ts ? `${line.ts} ` : ''}[${levelLabel(line.level)}] ${line.message}`
}

function openMenu(event: MouseEvent, line: LogLine | null): void {
  event.preventDefault()
  menuLine.value = line
  menuX.value = Math.min(event.clientX, window.innerWidth - 180)
  menuY.value = Math.min(event.clientY, window.innerHeight - 100)
  menuVisible.value = true
}

async function copyRow(): Promise<void> {
  const line = menuLine.value
  menuVisible.value = false
  if (line) await copyText(lineText(line))
}

async function copyAll(): Promise<void> {
  menuVisible.value = false
  await copyText(props.lines.map(lineText).join('\n'))
}

function closeMenu(): void {
  menuVisible.value = false
}

watch(
  () => visibleLines.value.length,
  (next, prev) => {
    if (props.autoScroll) {
      unseenCount.value = 0
      scrollToBottom()
      return
    }
    const added = Math.max(0, next - (prev ?? 0))
    if (added > 0) unseenCount.value += added
  }
)

watch(
  () => props.autoScroll,
  value => {
    if (value) scrollToBottom()
  }
)

onMounted(() => {
  document.addEventListener('click', closeMenu)
  if (props.autoScroll) scrollToBottom()
})

onBeforeUnmount(() => {
  document.removeEventListener('click', closeMenu)
})
</script>

<template>
  <div class="log-viewer">
    <div class="log-viewer__bar">
      <span class="log-viewer__stat">
        <span class="log-viewer__dot" aria-hidden="true" />
        {{ lines.length }} 行
        <span v-if="hiddenCount > 0" class="log-viewer__stat-hint">（仅渲染最近 {{ maxLines }} 行）</span>
      </span>
      <div class="log-viewer__actions">
        <el-button v-if="!autoScroll" link type="primary" size="small" @click="handleBackToBottom">
          回到底部
        </el-button>
        <span class="log-viewer__auto-label">自动滚动</span>
        <el-switch :model-value="autoScroll" size="small" @change="handleSwitchChange" />
      </div>
    </div>

    <div class="log-viewer__body">
      <div
        ref="viewportRef"
        class="log-viewer__viewport"
        role="log"
        aria-live="polite"
        aria-label="运行日志输出"
        tabindex="0"
        @scroll.passive="handleScroll"
        @contextmenu="openMenu($event, null)"
      >
        <template v-if="visibleLines.length > 0">
          <div
            v-for="line in visibleLines"
            :key="line.seq"
            class="log-viewer__line"
            :class="`log-viewer__line--${levelClass(line.level)}`"
            @contextmenu.stop="openMenu($event, line)"
          >
            <span v-if="line.ts" class="log-viewer__ts">{{ line.ts }}</span>
            <span class="log-viewer__level">{{ levelLabel(line.level) }}</span>
            <span class="log-viewer__message">{{ line.message }}</span>
          </div>
        </template>
        <div v-else class="log-viewer__empty">
          <el-empty :description="emptyText" :image-size="72" />
        </div>
      </div>

      <button
        v-if="unseenCount > 0"
        type="button"
        class="log-viewer__jump"
        @click="handleBackToBottom"
      >
        {{ unseenCount }} 条新日志 ↓
      </button>
    </div>

    <div
      v-if="menuVisible"
      class="log-viewer__menu"
      :style="{ left: `${menuX}px`, top: `${menuY}px` }"
      @click.stop
    >
      <button v-if="menuLine" type="button" class="log-viewer__menu-item" @click="copyRow">复制这一行</button>
      <button type="button" class="log-viewer__menu-item" @click="copyAll">复制全部日志</button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.log-viewer {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  overflow: hidden;
  // 终端固定深色底，不随浅/深色主题反转
  background: #16131a;
  border: 1px solid #302a3a;
  border-radius: var(--up-strm-radius-lg);
  box-shadow: var(--up-strm-shadow-sm);

  &__bar {
    flex: none;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--up-strm-space-3);
    padding: var(--up-strm-space-2) var(--up-strm-space-4);
    background: #1e1a24;
    border-bottom: 1px solid #302a3a;
    color: #c9c0d6;
    font-size: var(--up-strm-font-size-xs);
  }

  &__stat {
    display: inline-flex;
    align-items: center;
    gap: var(--up-strm-space-2);
    font-variant-numeric: tabular-nums;
  }

  &__dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #ff8a5b;
    box-shadow: 0 0 0 3px color-mix(in srgb, #ff8a5b 24%, transparent);
  }

  &__stat-hint {
    color: #7c7386;
  }

  &__actions {
    display: flex;
    align-items: center;
    gap: var(--up-strm-space-2);
  }

  &__auto-label {
    font-size: var(--up-strm-font-size-xs);
    color: #a79fa4;
  }

  &__body {
    position: relative;
    flex: 1;
    min-height: 0;
  }

  &__viewport {
    height: 100%;
    overflow-x: auto;
    overflow-y: auto;
    padding: var(--up-strm-space-4);
    font-family: var(--up-strm-font-mono);
    font-size: 12.5px;
    line-height: 20px;
    color: #e8e1dc;

    &::-webkit-scrollbar {
      width: 8px;
      height: 8px;
    }

    &::-webkit-scrollbar-thumb {
      border-radius: var(--up-strm-radius-pill);
      background: #453c52;
    }
  }

  &__line {
    display: flex;
    align-items: flex-start;
    gap: var(--up-strm-space-3);
    white-space: nowrap;

    &:hover {
      background: color-mix(in srgb, #302a3a 40%, transparent);
    }
  }

  &__line--warn {
    .log-viewer__level,
    .log-viewer__message {
      color: #ffc46b;
    }
  }

  &__line--error {
    background: color-mix(in srgb, #ff9b9b 12%, transparent);

    .log-viewer__level,
    .log-viewer__message {
      color: #ff9b9b;
    }
  }

  &__line--progress {
    .log-viewer__level,
    .log-viewer__message {
      color: #ffa57c;
    }
  }

  &__ts {
    flex: none;
    width: 62px;
    color: #7c7386;
    font-variant-numeric: tabular-nums;
    user-select: none;
  }

  &__level {
    flex: none;
    width: 44px;
    font-weight: 600;
    letter-spacing: 0.02em;
    color: #a79fa4;
  }

  &__message {
    flex: none;
    color: #e8e1dc;
  }

  &__empty {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 160px;
    height: 100%;
    color: #c9c0d6;
  }

  &__jump {
    position: absolute;
    right: var(--up-strm-space-4);
    bottom: var(--up-strm-space-4);
    padding: 4px 12px;
    border: none;
    border-radius: var(--up-strm-radius-pill);
    background: #6b4ee6;
    color: #fff;
    cursor: pointer;
    font-family: var(--up-strm-font-ui);
    font-size: var(--up-strm-font-size-xs);
    box-shadow: var(--up-strm-shadow-md);

    &:hover {
      background: #7c62f0;
    }
  }

  &__menu {
    position: fixed;
    z-index: 3000;
    display: flex;
    flex-direction: column;
    min-width: 160px;
    padding: var(--up-strm-space-1);
    border: 1px solid #302a3a;
    border-radius: var(--up-strm-radius-md);
    background: var(--el-bg-color-overlay);
    box-shadow: var(--up-strm-shadow-lg);
  }

  &__menu-item {
    padding: 6px 10px;
    border: none;
    border-radius: var(--up-strm-radius-sm);
    background: transparent;
    color: var(--el-text-color-regular);
    cursor: pointer;
    font-family: var(--up-strm-font-ui);
    font-size: var(--up-strm-font-size-sm);
    text-align: left;

    &:hover {
      background: var(--up-primary-50);
      color: var(--up-primary-700);
    }
  }
}
</style>
