<script setup lang="ts">
/** 空态：一句话 + 一个主按钮，每页最多一个。 */
import { ArrowRight } from '@element-plus/icons-vue'

withDefaults(
  defineProps<{
    title: string
    description?: string
    actionText?: string
    compact?: boolean
  }>(),
  { description: '', actionText: '', compact: false }
)

const emit = defineEmits<{ action: [] }>()
</script>

<template>
  <div class="empty-state" :class="{ 'empty-state--compact': compact }">
    <slot name="icon">
      <span class="empty-state__mark" aria-hidden="true">◌</span>
    </slot>
    <p class="empty-state__title">{{ title }}</p>
    <p v-if="description" class="empty-state__desc">{{ description }}</p>
    <el-button v-if="actionText" type="primary" round @click="emit('action')">
      {{ actionText }}
      <el-icon class="empty-state__arrow"><ArrowRight /></el-icon>
    </el-button>
  </div>
</template>

<style scoped lang="scss">
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--up-strm-space-2);
  padding: var(--up-strm-space-14) var(--up-strm-space-6);
  text-align: center;

  &--compact {
    padding: var(--up-strm-space-8) var(--up-strm-space-4);
  }

  &__mark {
    color: var(--up-ink-300);
    font-size: 32px;
    line-height: 1;
  }

  &__title {
    margin: var(--up-strm-space-2) 0 0;
    color: var(--el-text-color-primary);
    font-size: var(--up-strm-fs-15);
    font-weight: 600;
  }

  &__desc {
    max-width: 420px;
    margin: 0;
    color: var(--el-text-color-secondary);
    font-size: var(--up-strm-font-size-sm);
    line-height: 1.6;
  }

  &__arrow {
    margin-left: 4px;
  }
}
</style>
