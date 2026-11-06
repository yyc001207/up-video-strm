<script setup lang="ts">
/**
 * 进度环：48px（卡片内）/ 96px（详情页头部）。
 * value 为 null 时显示不确定态（底环 + 短弧），避免分母为 0 时画成 0% 误导。
 */
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    value: number | null
    size?: number
    stroke?: number
  }>(),
  { size: 48, stroke: 6 }
)

const radius = computed(() => (props.size - props.stroke) / 2)
const circumference = computed(() => 2 * Math.PI * radius.value)
const clamped = computed(() =>
  props.value === null ? null : Math.max(0, Math.min(100, Math.round(props.value)))
)
const dashOffset = computed(() =>
  clamped.value === null ? circumference.value * 0.75 : circumference.value * (1 - clamped.value / 100)
)
const center = computed(() => props.size / 2)
</script>

<template>
  <span
    class="progress-ring"
    :class="{ 'progress-ring--indeterminate': clamped === null }"
    :style="{ width: `${size}px`, height: `${size}px` }"
    role="img"
    :aria-label="clamped === null ? '进度未知' : `进度 ${clamped}%`"
  >
    <svg :width="size" :height="size" :viewBox="`0 0 ${size} ${size}`">
      <circle
        class="progress-ring__track"
        :cx="center"
        :cy="center"
        :r="radius"
        fill="none"
        :stroke-width="stroke"
      />
      <circle
        class="progress-ring__value"
        :cx="center"
        :cy="center"
        :r="radius"
        fill="none"
        :stroke-width="stroke"
        stroke-linecap="round"
        :stroke-dasharray="circumference"
        :stroke-dashoffset="dashOffset"
      />
    </svg>
    <span v-if="clamped !== null" class="progress-ring__label nums">{{ clamped }}%</span>
  </span>
</template>

<style scoped lang="scss">
.progress-ring {
  position: relative;
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;

  svg {
    transform: rotate(-90deg);
  }

  &__track {
    stroke: var(--up-ink-200);
  }

  &__value {
    stroke: var(--up-primary-500);
    transition: stroke-dashoffset var(--up-strm-dur-slow) var(--up-strm-ease);
  }

  &__label {
    position: absolute;
    color: var(--el-text-color-primary);
    font-size: var(--up-strm-fs-15);
    font-weight: 600;
    line-height: 1;
  }

  &--indeterminate &__value {
    animation: progress-ring-spin 1.6s linear infinite;
  }

  &--indeterminate &__label {
    display: none;
  }
}

@keyframes progress-ring-spin {
  to {
    transform: rotate(270deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .progress-ring--indeterminate .progress-ring__value {
    animation: none;
  }
}
</style>
