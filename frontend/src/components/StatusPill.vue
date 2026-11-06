<script setup lang="ts">
/** 状态胶囊：柔和底 + 同色描边 + 文字，高 24、圆角 999。 */
import { computed } from 'vue'

export type PillStatus =
  | 'running'
  | 'queued'
  | 'success'
  | 'fail'
  | 'cancelled'
  | 'never'
  | 'pending'

const props = withDefaults(
  defineProps<{
    status: PillStatus
    /** 「待处理 N」中的数量；为 0 时只显示「待处理」以外的固定文案会被忽略。 */
    count?: number
    /** 运行中/排队中的圆点是否呼吸（默认开启）。 */
    breathe?: boolean
  }>(),
  { count: undefined, breathe: true }
)

const LABELS: Record<PillStatus, string> = {
  running: '运行中',
  queued: '排队中',
  success: '成功',
  fail: '失败',
  cancelled: '已取消',
  never: '还没跑过',
  pending: '待处理'
}

const label = computed(() => {
  if (props.status === 'pending' && typeof props.count === 'number') {
    return `${LABELS.pending} ${props.count}`
  }
  return LABELS[props.status]
})
</script>

<template>
  <span class="status-pill" :class="[`status-pill--${status}`, { 'is-breathing': breathe && status === 'running' }]">
    <span class="status-pill__dot" />
    <span class="status-pill__label">{{ label }}</span>
  </span>
</template>

<style scoped lang="scss">
.status-pill {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 6px;
  height: 24px;
  padding: 0 10px;
  border: 1px solid var(--up-ink-200);
  border-radius: var(--up-strm-radius-pill);
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  font-size: var(--up-strm-font-size-xs);
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;

  &__dot {
    flex: none;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--up-ink-400);
  }

  &--running {
    border-color: color-mix(in srgb, var(--up-primary-500) 30%, transparent);
    background: var(--up-primary-50);
    color: var(--up-primary-600);

    .status-pill__dot {
      background: var(--up-primary-500);
    }
  }

  &--queued .status-pill__dot {
    border: 1.5px solid var(--up-ink-400);
    background: transparent;
  }

  &--success {
    border-color: color-mix(in srgb, var(--up-success-mark) 28%, transparent);
    background: var(--up-success-bg);
    color: var(--up-success-text);

    .status-pill__dot {
      background: var(--up-success-mark);
    }
  }

  &--fail {
    border-color: color-mix(in srgb, var(--up-danger-mark) 28%, transparent);
    background: var(--up-danger-bg);
    color: var(--up-danger-text);

    .status-pill__dot {
      background: var(--up-danger-mark);
    }
  }

  &--pending {
    border-color: color-mix(in srgb, var(--up-warning-mark) 30%, transparent);
    background: var(--up-warning-bg);
    color: var(--up-warning-text);

    .status-pill__dot {
      background: var(--up-warning-mark);
    }
  }

  &--cancelled,
  &--never {
    color: var(--el-text-color-secondary);
  }

  &.is-breathing .status-pill__dot {
    animation: pill-breathe 2s ease-in-out infinite;
  }
}

@keyframes pill-breathe {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.45;
    transform: scale(0.82);
  }
}

@media (prefers-reduced-motion: reduce) {
  .status-pill.is-breathing .status-pill__dot {
    animation: none;
  }
}
</style>
