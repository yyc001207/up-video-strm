<script setup lang="ts">
/** 页面头：标题 28/600 + 副标题 13 + 右侧主行动（8.5 页面骨架 ①）。 */
defineProps<{
  title: string
  description?: string
}>()
</script>

<template>
  <header class="page-header">
    <div class="page-header__text">
      <h1 class="page-header__title">{{ title }}</h1>
      <p v-if="description" class="page-header__desc">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="page-header__actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped lang="scss">
.page-header {
  display: flex;
  flex: none;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--up-strm-space-4);
  padding: var(--up-strm-space-6) var(--up-strm-page-pad) 0;
}

.page-header__text {
  min-width: 0;
}

.page-header__title {
  margin: 0;
  color: var(--el-text-color-primary);
  font-size: var(--up-strm-fs-28);
  font-weight: 600;
  line-height: 36px;
  letter-spacing: 0;
}

.page-header__desc {
  margin: 6px 0 0;
  overflow: hidden;
  color: var(--el-text-color-secondary);
  font-size: var(--up-strm-font-size-sm);
  line-height: 20px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.page-header__actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: var(--up-strm-space-2);
  padding-top: var(--up-strm-space-1);
}

@media (max-width: 1279px) {
  .page-header {
    padding: var(--up-strm-space-5) var(--up-strm-space-5) 0;
  }
}
</style>
