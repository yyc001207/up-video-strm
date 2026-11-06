<script setup lang="ts">
/** 运行中抽屉：列运行中条目，支持「看详情」与「停止」。 */
import { useRouter } from 'vue-router'

import AvatarTile from '@/components/AvatarTile.vue'
import EmptyState from '@/components/EmptyState.vue'
import ProgressRing from '@/components/ProgressRing.vue'
import StatusPill from '@/components/StatusPill.vue'
import { useRunningStore, type RunningModuleItem } from '@/stores/running'

defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const router = useRouter()
const running = useRunningStore()

function openDetail(item: RunningModuleItem): void {
  emit('update:modelValue', false)
  router.push(item.detailPath)
}

async function stop(item: RunningModuleItem): Promise<void> {
  try {
    await item.stop()
    await running.fetchCounts()
  } catch {
    /* 错误提示由请求层统一处理 */
  }
}
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    direction="rtl"
    size="420px"
    title="正在执行"
    :append-to-body="true"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="activity">
      <div class="activity__summary">
        <span>{{ running.total }} 个正在执行</span>
        <el-button link type="primary" @click="running.fetchCounts()">刷新</el-button>
      </div>

      <EmptyState
        v-if="running.total === 0"
        compact
        title="现在没有正在执行的任务"
        description="从「开始执行」发起后，这里会出现实时进度。"
      />

      <ul v-else class="activity__list">
        <li v-for="item in running.items" :key="`${item.module}-${item.id}`" class="activity__row">
          <AvatarTile :name="item.name" :size="36" :radius="10" />
          <div class="activity__main">
            <div class="activity__line">
              <span class="activity__name">{{ item.name }}</span>
              <StatusPill status="running" :breathe="false" />
            </div>
            <div class="activity__meta">
              <span>{{ item.moduleLabel }}</span>
              <span v-if="item.progress !== null">{{ Math.round(item.progress) }}%</span>
            </div>
          </div>
          <ProgressRing v-if="item.progress !== null" :value="item.progress" :size="36" :stroke="4" />
          <div class="activity__actions">
            <el-button link type="primary" @click="openDetail(item)">看详情</el-button>
            <el-button link @click="stop(item)">停止</el-button>
          </div>
        </li>
      </ul>
    </div>
  </el-drawer>
</template>

<style scoped lang="scss">
.activity {
  display: flex;
  flex-direction: column;
  gap: var(--up-strm-space-3);
}

.activity__summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--el-text-color-secondary);
  font-size: var(--up-strm-font-size-sm);
}

.activity__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.activity__row {
  display: flex;
  align-items: center;
  gap: var(--up-strm-space-3);
  padding: var(--up-strm-space-3);
  border-radius: var(--up-strm-radius-md);

  &:hover {
    background: var(--el-fill-color-light);
  }
}

.activity__main {
  flex: 1;
  min-width: 0;
}

.activity__line {
  display: flex;
  align-items: center;
  gap: var(--up-strm-space-2);
  min-width: 0;

  .status-pill {
    flex: none;
  }
}

.activity__name {
  overflow: hidden;
  color: var(--el-text-color-primary);
  font-size: var(--up-strm-font-size-sm);
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.activity__meta {
  display: flex;
  gap: var(--up-strm-space-2);
  color: var(--el-text-color-secondary);
  font-size: var(--up-strm-font-size-xs);
}

.activity__actions {
  display: flex;
  flex: none;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}
</style>
