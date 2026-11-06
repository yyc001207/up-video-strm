<script setup lang="ts">
/** 「今天」流水线卡：模块名 → 状态行 → 一句摘要 → 文字行动，右上角进度环。 */
import { ArrowRight } from '@element-plus/icons-vue'

import ProgressRing from '@/components/ProgressRing.vue'

withDefaults(
  defineProps<{
    moduleLabel: string
    headline: string
    summary: string
    actionText: string
    /** 0–100；null 表示没有可算的进度（不显示环）。 */
    progress?: number | null
    /** 用于状态色：running / success / fail / pending / never */
    tone?: 'running' | 'success' | 'fail' | 'warning' | 'neutral'
  }>(),
  { progress: null, tone: 'neutral' }
)

const emit = defineEmits<{ action: [] }>()
</script>

<template>
  <button class="flow-card" type="button" :class="`flow-card--${tone}`" @click="emit('action')">
    <div class="flow-card__top">
      <span class="flow-card__module">{{ moduleLabel }}</span>
      <ProgressRing v-if="progress !== null" :value="progress" :size="48" />
    </div>
    <span class="flow-card__headline">{{ headline }}</span>
    <span class="flow-card__summary">{{ summary }}</span>
    <span class="flow-card__action">
      {{ actionText }}
      <el-icon :size="14"><ArrowRight /></el-icon>
    </span>
  </button>
</template>

<style scoped lang="scss">
.flow-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  min-height: 176px;
  padding: var(--up-strm-space-5);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--up-strm-radius-lg);
  background: var(--el-bg-color);
  box-shadow: var(--up-strm-shadow-sm);
  text-align: left;
  cursor: pointer;
  transition:
    transform var(--up-strm-dur-fast) var(--up-strm-ease),
    box-shadow var(--up-strm-dur-fast) var(--up-strm-ease),
    border-color var(--up-strm-dur-fast) var(--up-strm-ease);

  &:hover {
    transform: translateY(-2px);
    border-color: var(--el-border-color);
    box-shadow: var(--up-strm-shadow-md);
  }

  &__top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    min-height: 48px;
  }

  &__module {
    color: var(--el-text-color-secondary);
    font-size: var(--up-strm-font-size-sm);
    line-height: 20px;
  }

  &__headline {
    overflow: hidden;
    color: var(--el-text-color-primary);
    font-size: var(--up-strm-fs-15);
    font-weight: 600;
    line-height: 22px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__summary {
    flex: 1;
    overflow: hidden;
    color: var(--el-text-color-secondary);
    font-size: var(--up-strm-font-size-xs);
    line-height: 18px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__action {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--up-primary-600);
    font-size: var(--up-strm-font-size-sm);
    font-weight: 600;
  }

  &--running .flow-card__headline {
    color: var(--up-primary-600);
  }

  &--success .flow-card__headline {
    color: var(--up-success-text);
  }

  &--fail .flow-card__headline {
    color: var(--up-danger-text);
  }

  &--warning .flow-card__headline {
    color: var(--up-warning-text);
  }
}

@media (prefers-reduced-motion: reduce) {
  .flow-card:hover {
    transform: none;
  }
}
</style>
