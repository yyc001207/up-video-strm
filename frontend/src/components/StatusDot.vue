<script setup lang="ts">
import { computed } from 'vue'

import type { ExecutionStatus } from '@/types/openlist'

const props = withDefaults(defineProps<{ status: ExecutionStatus; size?: number }>(), {
  size: 6
})

const LABELS: Record<ExecutionStatus, string> = {
  running: '运行中',
  success: '成功',
  fail: '失败',
  cancelled: '已取消'
}

const TONES: Record<ExecutionStatus, string> = {
  running: 'warning',
  success: 'success',
  fail: 'danger',
  cancelled: 'info'
}

const label = computed(() => LABELS[props.status])
const tone = computed(() => TONES[props.status])
</script>

<template>
  <span class="status-dot" :class="`status-dot--${tone}`">
    <span class="status-dot__dot" :style="{ width: `${size}px`, height: `${size}px` }" />
    <span class="status-dot__label">{{ label }}</span>
  </span>
</template>

<style scoped lang="scss">
.status-dot {
  display: inline-flex;
  align-items: center;
  gap: var(--up-strm-space-2);
  font-size: var(--up-strm-font-size-sm);
  line-height: 1.4;
  color: var(--el-text-color-regular);

  &__dot {
    flex: none;
    border-radius: 50%;
    background: var(--el-color-info);
  }

  &--warning .status-dot__dot {
    background: var(--el-color-warning);
  }

  &--success .status-dot__dot {
    background: var(--el-color-success);
  }

  &--danger .status-dot__dot {
    background: var(--el-color-danger);
  }
}
</style>
