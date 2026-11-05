<script setup lang="ts">
/**
 * 123 云盘目录选择面板（懒加载树）。
 *
 * 交互：
 * - 根节点「/」展开后逐级列出子目录，点击 `+` 号可继续下钻（懒加载）；
 * - 单击节点 = 选中（高亮 + 底部醒目展示“已选路径”）；
 * - 双击节点 = 继续展开（等价于点左侧箭头）。
 */
import { ref } from 'vue'
import { ElMessage, type ElTree } from 'element-plus'
import { FolderOpened, Refresh } from '@element-plus/icons-vue'

import { uploaderApi } from '@/api/uploader'

export interface RemoteDirNode {
  id: number
  name: string
  path: string
}

const emit = defineEmits<{
  (e: 'select', path: string): void
}>()

const treeRef = ref<InstanceType<typeof ElTree>>()
const treeKey = ref(0)
const treeData = ref<RemoteDirNode[]>([{ id: 0, name: '/（根目录）', path: '/' }])
const selected = ref<RemoteDirNode | null>(null)

const treeProps = {
  label: 'name',
  children: 'children'
}

function joinPath(parentPath: string, name: string): string {
  return parentPath === '/' ? `/${name}` : `${parentPath}/${name}`
}

/** el-tree 懒加载：按父目录 fileId 拉取子目录。 */
async function loadNode(node: { level: number; data: RemoteDirNode }, resolve: (data: RemoteDirNode[]) => void): Promise<void> {
  if (node.level === 0) {
    resolve(treeData.value)
    return
  }
  const current = node.data
  try {
    const res = await uploaderApi.listRemoteDirs({ parent_id: current.id, path: current.path })
    resolve(
      res.data.items.map(item => ({
        id: item.file_id,
        name: item.file_name,
        path: joinPath(current.path, item.file_name)
      }))
    )
  } catch {
    resolve([])
  }
}

function handleNodeClick(data: RemoteDirNode): void {
  selected.value = data
}

function handleNodeDblClick(data: RemoteDirNode): void {
  selected.value = data
  treeRef.value?.getNode(data.id)?.expand()
}

function refreshTree(): void {
  selected.value = null
  treeKey.value += 1
}

function confirmSelect(): void {
  if (!selected.value) {
    ElMessage.warning('请先点选要上传到的云端目录')
    return
  }
  emit('select', selected.value.path)
}
</script>

<template>
  <div class="remote-dir">
    <div class="remote-dir__toolbar">
      <span class="remote-dir__hint">点击目录选中，点左侧箭头或双击继续下钻</span>
      <el-button :icon="Refresh" size="small" @click="refreshTree">刷新</el-button>
    </div>

    <div class="remote-dir__tree">
      <el-tree
        :key="treeKey"
        ref="treeRef"
        lazy
        :load="loadNode"
        :data="treeData"
        :props="treeProps"
        node-key="id"
        :expand-on-click-node="false"
        :default-expanded-keys="[0]"
        highlight-current
        @node-click="handleNodeClick"
        @node-dblclick="handleNodeDblClick"
      >
        <template #default="{ data }">
          <span class="remote-dir__node">
            <el-icon :size="15"><FolderOpened /></el-icon>
            <span class="remote-dir__node-name">{{ data.name }}</span>
          </span>
        </template>
      </el-tree>
    </div>

    <div class="remote-dir__footer">
      <div class="remote-dir__selected">
        <span class="remote-dir__selected-label">已选路径</span>
        <strong class="remote-dir__selected-path">{{ selected?.path ?? '未选择' }}</strong>
      </div>
      <el-button type="primary" :disabled="selected === null" @click="confirmSelect">
        选为上传目录
      </el-button>
    </div>

    <p class="remote-dir__tip">测试与联调请仅使用 123 云盘 /test 目录；正式上传请选择对应目录。</p>
  </div>
</template>

<style scoped lang="scss">
.remote-dir {
  display: flex;
  flex-direction: column;
  gap: var(--up-strm-space-3, 12px);

  &__toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--up-strm-space-2, 8px);
  }

  &__tree {
    min-height: 260px;
    max-height: 360px;
    padding: var(--up-strm-space-1, 4px);
    overflow: auto;
    border: 1px solid var(--el-border-color-lighter);
    border-radius: var(--up-strm-radius-sm, 6px);

    :deep(.el-tree-node__content) {
      height: 32px;
    }

    :deep(.el-tree-node.is-current > .el-tree-node__content) {
      color: var(--el-color-primary);
      background: var(--el-color-primary-light-9);
      font-weight: 600;
    }
  }

  &__node {
    display: inline-flex;
    align-items: center;
    gap: var(--up-strm-space-2, 8px);
    min-width: 0;
    font-size: var(--up-strm-font-size-sm, 13px);
  }

  &__node-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--up-strm-space-3, 12px);
    padding: var(--up-strm-space-2, 8px) var(--up-strm-space-3, 12px);
    background: var(--el-fill-color-light);
    border-radius: var(--up-strm-radius-sm, 6px);
  }

  &__selected {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  &__selected-label {
    font-size: var(--up-strm-font-size-xs, 12px);
    color: var(--el-text-color-secondary);
  }

  &__selected-path {
    overflow: hidden;
    color: var(--el-color-primary);
    font-family: ui-monospace, 'SFMono-Regular', Consolas, monospace;
    font-size: var(--up-strm-font-size-md, 14px);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__hint,
  &__tip {
    margin: 0;
    font-size: var(--up-strm-font-size-xs, 12px);
    color: var(--el-text-color-placeholder);
  }
}
</style>
