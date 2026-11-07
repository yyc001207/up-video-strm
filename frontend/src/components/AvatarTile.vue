<script setup lang="ts">
/**
 * 任务头像块：名称首字 + 名称哈希取 6 色（紫 / 蜜桃 / 青 / 粉 / 琥珀 / 蓝）。
 * 现有接口没有封面图，用色块建立条目识别度；色值走 --up-avatar-* 令牌，保证白字对比度 ≥4.9:1。
 */
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    name: string
    size?: number
    radius?: number
  }>(),
  { size: 40, radius: 12 }
)

const COLORS = ['violet', 'peach', 'cyan', 'pink', 'amber', 'blue'] as const

const tone = computed(() => {
  let hash = 0
  for (const char of props.name || '?') {
    hash = (hash * 31 + char.codePointAt(0)! ) % 100000
  }
  return COLORS[hash % COLORS.length]
})

const initial = computed(() => {
  const text = (props.name || '').trim()
  return text ? Array.from(text)[0]!.toUpperCase() : '?'
})
</script>

<template>
  <span
    class="avatar-tile"
    :class="`avatar-tile--${tone}`"
    :style="{
      width: `${size}px`,
      height: `${size}px`,
      borderRadius: `${radius}px`,
      fontSize: `${Math.max(12, Math.round(size * 0.38))}px`
    }"
    aria-hidden="true"
  >
    {{ initial }}
  </span>
</template>

<style scoped lang="scss">
.avatar-tile {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-weight: 600;
  line-height: 1;
  user-select: none;

  &--violet {
    background: var(--up-avatar-1);
  }

  &--peach {
    background: var(--up-avatar-6);
  }

  &--cyan {
    background: var(--up-avatar-4);
  }

  &--pink {
    background: var(--up-avatar-3);
  }

  &--amber {
    background: var(--up-avatar-5);
  }

  &--blue {
    background: var(--up-avatar-2);
  }
}
</style>
