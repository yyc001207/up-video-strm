<script setup lang="ts">
/**
 * 底部批量操作条（Next UI C15）。
 *
 * 放在列表之后占位一行（不覆盖内容），选中 ≥1 时由调用方渲染。
 * 左侧显示「已选 N 项」，右侧由 actions 插槽注入操作。
 */
defineProps<{
  /** 已选数量。 */
  count: number
  /** 对象名词，如「任务」。 */
  noun?: string
}>()

const emit = defineEmits<{
  (e: 'clear'): void
}>()
</script>

<template>
  <div class="bulk-bar" role="toolbar" aria-label="批量操作">
    <span class="bulk-bar__count">
      已选 <strong class="nums">{{ count }}</strong> 个{{ noun ?? '任务' }}
    </span>
    <div class="bulk-bar__actions">
      <slot />
      <el-button text @click="emit('clear')">取消</el-button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.bulk-bar {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: space-between;
  gap: var(--up-strm-space-3);
  height: 56px;
  padding: 0 var(--up-strm-space-4);
  border: 1px solid var(--up-primary-200);
  border-radius: var(--up-strm-radius-md);
  background: var(--up-primary-50);
  color: var(--el-text-color-primary);
  font-size: var(--up-strm-font-size-sm);

  &__count {
    color: var(--el-text-color-regular);

    strong {
      color: var(--up-primary-600);
      font-weight: 600;
    }
  }

  &__actions {
    display: flex;
    align-items: center;
    gap: var(--up-strm-space-2);
  }
}
</style>
