<script setup lang="ts">
/**
 * 任务头像块：名称首字 + 名称哈希取 6 色（紫 / 蜜桃 / 青 / 粉 / 琥珀 / 蓝）。
 * 现有接口没有封面图，用色块建立条目识别度。
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
    background: #6b4ee6;
  }

  &--peach {
    background: #ff8a5b;
  }

  &--cyan {
    background: #2aa8a8;
  }

  &--pink {
    background: #d95c9a;
  }

  &--amber {
    background: #d98a00;
  }

  &--blue {
    background: #3f74d9;
  }
}
</style>
