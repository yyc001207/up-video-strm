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
 * 可复用日志终端：等宽字体 + 级别着色 + 行号 + 自动滚动（上滚暂停，回到底部恢复）。
 *
 * - lines 已按调用方需要过滤，seq 保持原始行号；
 * - 行数超过 maxLines 时只渲染末尾部分，避免长时间执行后 DOM 膨胀；
 * - autoScroll 为受控 prop，用户上滚时通过 update:autoScroll 通知调用方暂停。
 */
import { computed, nextTick, onMounted, ref, watch } from 'vue'

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

const viewportRef = ref<HTMLElement | null>(null)

const visibleLines = computed<readonly LogLine[]>(() => {
  const total = props.lines.length
  if (total <= props.maxLines) return props.lines
  return props.lines.slice(total - props.maxLines)
})

/** 因超出 maxLines 而未渲染的行数。 */
const hiddenCount = computed(() => props.lines.length - visibleLines.value.length)

function levelClass(level: string): string {
  return LEVEL_CLASSES[level] ?? 'info'
}

function levelLabel(level: string): string {
  return level.toUpperCase()
}

function scrollToBottom(): void {
  void nextTick(() => {
    const el = viewportRef.value
    if (!el) return
    el.scrollTop = el.scrollHeight
  })
}

function setAutoScroll(value: boolean): void {
  emit('update:autoScroll', value)
  if (value) scrollToBottom()
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
}

/** el-switch 的 change 参数为 boolean | string | number，这里统一收敛为布尔值。 */
function handleSwitchChange(value: string | number | boolean): void {
  setAutoScroll(value === true)
}

function handleBackToBottom(): void {
  setAutoScroll(true)
}

watch(
  () => visibleLines.value.length,
  () => {
    if (props.autoScroll) scrollToBottom()
  }
)

watch(
  () => props.autoScroll,
  value => {
    if (value) scrollToBottom()
  }
)

onMounted(() => {
  if (props.autoScroll) scrollToBottom()
})
</script>

<template>
  <div class="log-viewer">
    <div class="log-viewer__bar">
      <span class="log-viewer__stat">
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

    <div
      ref="viewportRef"
      class="log-viewer__viewport"
      role="log"
      aria-live="polite"
      aria-label="实时日志输出"
      tabindex="0"
      @scroll.passive="handleScroll"
    >
      <template v-if="visibleLines.length > 0">
        <div
          v-for="line in visibleLines"
          :key="line.seq"
          class="log-viewer__line"
          :class="`log-viewer__line--${levelClass(line.level)}`"
        >
          <span class="log-viewer__seq">{{ line.seq }}</span>
          <span v-if="line.ts" class="log-viewer__ts">{{ line.ts }}</span>
          <span class="log-viewer__level">{{ levelLabel(line.level) }}</span>
          <span class="log-viewer__message">{{ line.message }}</span>
        </div>
      </template>
      <div v-else class="log-viewer__empty">
        <el-empty :description="emptyText" :image-size="72" />
      </div>
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
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--up-strm-radius-md, 8px);

  &__bar {
    flex: none;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--up-strm-space-3, 12px);
    padding: var(--up-strm-space-1, 4px) var(--up-strm-space-3, 12px);
    background: var(--el-fill-color-light);
    border-bottom: 1px solid var(--el-border-color-lighter);
    font-size: var(--up-strm-font-size-xs, 12px);
    color: var(--el-text-color-secondary);
  }

  &__stat-hint {
    margin-left: var(--up-strm-space-1, 4px);
    color: var(--el-text-color-placeholder);
  }

  &__actions {
    display: flex;
    align-items: center;
    gap: var(--up-strm-space-2, 8px);
  }

  &__auto-label {
    font-size: var(--up-strm-font-size-xs, 12px);
  }

  &__viewport {
    flex: 1;
    min-height: 0;
    overflow-x: hidden;
    overflow-y: auto;
    padding: var(--up-strm-space-2, 8px) 0;
    background: var(--el-fill-color-light);
    font-family: 'JetBrains Mono', 'Cascadia Code', Consolas, 'Courier New', monospace;
    font-size: var(--up-strm-font-size-xs, 12px);
    line-height: 1.65;
  }

  &__line {
    display: flex;
    align-items: flex-start;
    gap: var(--up-strm-space-2, 8px);
    padding: 0 var(--up-strm-space-3, 12px);
  }

  &__line--warn {
    background: color-mix(in srgb, var(--el-color-warning) 8%, transparent);

    .log-viewer__level,
    .log-viewer__message {
      color: var(--el-color-warning);
    }
  }

  &__line--error {
    background: color-mix(in srgb, var(--el-color-danger) 10%, transparent);

    .log-viewer__level,
    .log-viewer__message {
      color: var(--el-color-danger);
    }
  }

  &__line--progress {
    .log-viewer__level,
    .log-viewer__message {
      color: var(--el-color-primary);
    }
  }

  &__seq {
    flex: none;
    min-width: 3.5ch;
    text-align: right;
    color: var(--el-text-color-placeholder);
    font-variant-numeric: tabular-nums;
    user-select: none;
  }

  &__ts {
    flex: none;
    color: var(--el-text-color-placeholder);
  }

  &__level {
    flex: none;
    width: 8ch;
    font-weight: 600;
    letter-spacing: 0.02em;
    color: var(--el-text-color-secondary);
  }

  &__message {
    flex: 1;
    min-width: 0;
    white-space: pre-wrap;
    word-break: break-word;
    color: var(--el-text-color-regular);
  }

  &__empty {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 160px;
    height: 100%;
  }
}
</style>
