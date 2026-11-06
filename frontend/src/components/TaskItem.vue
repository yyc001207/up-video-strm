<script setup lang="ts">
/**
 * 任务卡片列表行（Next UI C5）。
 *
 * - 两行文字 + 左右内边距，总高约 80；整行可点（Enter 也可）；
 * - 勾选框默认隐藏，悬停或已选中时出现；
 * - 右侧操作区由调用方通过 actions 插槽注入（通常是「⋯」菜单或按钮组）。
 */
import AvatarTile from './AvatarTile.vue'
import StatusPill, { type PillStatus } from './StatusPill.vue'

withDefaults(
  defineProps<{
    /** 任务名（同时用于头像首字与哈希取色）。 */
    name: string
    /** 副行左侧：处理路径 / 目录等。 */
    path?: string
    /** 副行追加信息，如「128 集 · 上次 4m12s」。 */
    meta?: string
    /** 右侧状态胶囊；不传则不显示。 */
    status?: PillStatus
    /** 「待处理 N」的数量。 */
    statusCount?: number
    /** 是否选中。 */
    selected?: boolean
    /** 是否显示勾选框（默认显示，但只在悬停/选中时可见）。 */
    selectable?: boolean
    /** 是否允许整行点击触发 activate。 */
    clickable?: boolean
  }>(),
  {
    path: '',
    meta: '',
    status: undefined,
    statusCount: undefined,
    selected: false,
    selectable: true,
    clickable: true
  }
)

const emit = defineEmits<{
  (e: 'toggle'): void
  (e: 'activate'): void
}>()

function handleActivate(): void {
  emit('activate')
}
</script>

<template>
  <div
    class="task-item"
    :class="{ 'is-selected': selected, 'is-clickable': clickable }"
    :tabindex="clickable ? 0 : -1"
    role="listitem"
    @click="clickable && handleActivate()"
    @keydown.enter="clickable && handleActivate()"
  >
    <el-checkbox
      v-if="selectable"
      class="task-item__check"
      :model-value="selected"
      aria-label="选择任务"
      @click.stop
      @change="emit('toggle')"
    />
    <AvatarTile :name="name" :size="40" />
    <div class="task-item__main">
      <div class="task-item__title-line">
        <span class="task-item__name" :title="name">{{ name }}</span>
        <StatusPill v-if="status" :status="status" :count="statusCount" />
      </div>
      <div class="task-item__meta">
        <span v-if="path" class="task-item__path" :title="path">{{ path }}</span>
        <span v-if="path && meta" class="task-item__sep">·</span>
        <span v-if="meta">{{ meta }}</span>
      </div>
    </div>
    <div v-if="$slots.actions" class="task-item__actions" @click.stop>
      <slot name="actions" />
    </div>
  </div>
</template>

<style scoped lang="scss">
.task-item {
  display: flex;
  align-items: center;
  gap: var(--up-strm-space-3);
  min-height: 80px;
  padding: 12px var(--up-strm-space-4);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--up-strm-radius-lg);
  background: var(--el-bg-color);
  transition:
    background-color var(--up-strm-dur-fast) var(--up-strm-ease),
    border-color var(--up-strm-dur-fast) var(--up-strm-ease),
    box-shadow var(--up-strm-dur-fast) var(--up-strm-ease),
    transform var(--up-strm-dur-fast) var(--up-strm-ease);

  &:hover {
    background: var(--up-ink-100);
    box-shadow: var(--up-strm-shadow-sm);
    transform: translateY(-1px);

    .task-item__check {
      opacity: 1;
      pointer-events: auto;
    }
  }

  &.is-selected {
    border-color: var(--up-primary-300);
    background: var(--up-primary-50);

    .task-item__check {
      opacity: 1;
      pointer-events: auto;
    }
  }

  &.is-clickable {
    cursor: pointer;
  }

  &:focus-visible {
    outline: 2px solid var(--up-primary-500);
    outline-offset: 2px;
  }

  &__check {
    flex: none;
    display: inline-flex;
    align-items: center;
    height: 24px;
    margin-right: calc(-1 * var(--up-strm-space-1));
    opacity: 0;
    pointer-events: none;
    transition: opacity var(--up-strm-dur-fast) var(--up-strm-ease);
  }

  &__main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  &__title-line {
    display: flex;
    align-items: center;
    gap: var(--up-strm-space-2);
    min-width: 0;
  }

  &__name {
    min-width: 0;
    overflow: hidden;
    color: var(--el-text-color-primary);
    font-size: var(--up-strm-fs-15);
    font-weight: 600;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__meta {
    display: flex;
    align-items: center;
    gap: var(--up-strm-space-1);
    min-width: 0;
    color: var(--el-text-color-secondary);
    font-size: var(--up-strm-font-size-xs);
    line-height: 18px;
  }

  &__path {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__sep {
    flex: none;
    color: var(--el-text-color-placeholder);
  }

  &__actions {
    flex: none;
    display: flex;
    align-items: center;
    gap: var(--up-strm-space-1);
    opacity: 0.55;
    transition: opacity var(--up-strm-dur-fast) var(--up-strm-ease);
  }

  &:hover &__actions,
  &:focus-within &__actions {
    opacity: 1;
  }
}
</style>
