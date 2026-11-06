<script setup lang="ts">
/**
 * 「连接与格式 · 生成设置」卡片。
 *
 * 由任务页迁移而来：默认运行参数全局生效，任务未单独设置时使用。
 * 卡片只读展示，点「编辑」在抽屉中修改（保存后刷新 openlist store）。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Edit, FolderOpened } from '@element-plus/icons-vue'

import { openlistApi } from '@/api/openlist'
import { useOpenlistStore } from '@/stores/openlist'

const store = useOpenlistStore()

const saving = ref(false)
const drawerVisible = ref(false)
const form = reactive({
  max_concurrent: 1,
  pause_count: 50,
  pause_time: '0,3,5',
  disable_ssl_verify: false,
  output_dir_prefix: '',
  output_root: '',
  openlist_remote_prefix: ''
})

const configured = computed(() => store.config !== null)

function openDrawer() {
  const current = store.config
  form.max_concurrent = current?.max_concurrent || 1
  form.pause_count = current?.pause_count || 50
  form.pause_time = current?.pause_time || '0,3,5'
  form.disable_ssl_verify = current?.disable_ssl_verify ?? false
  form.output_dir_prefix = current?.output_dir_prefix ?? ''
  form.output_root = current?.output_root ?? ''
  form.openlist_remote_prefix = current?.openlist_remote_prefix ?? ''
  drawerVisible.value = true
}

/** 桌面版唤起系统文件夹选择框；浏览器版没有该能力，提示手动填写。 */
async function pickOutputRoot() {
  const bridge = (
    window as unknown as {
      pywebview?: { api?: { pick_directory?: (startDir?: string) => Promise<string> } }
    }
  ).pywebview
  if (!bridge?.api?.pick_directory) {
    ElMessage.warning('当前不是桌面版，请手动填写路径')
    return
  }
  try {
    const picked = await bridge.api.pick_directory(form.output_root.trim() || '')
    if (picked) form.output_root = picked
  } catch {
    ElMessage.error('打开文件夹选择框失败')
  }
}

/** 只提交本卡字段，视频/字幕格式保持不变。 */
async function handleSave() {
  saving.value = true
  try {
    await openlistApi.updateConfig({
      max_concurrent: form.max_concurrent,
      pause_count: form.pause_count,
      pause_time: form.pause_time.trim(),
      disable_ssl_verify: form.disable_ssl_verify,
      output_dir_prefix: form.output_dir_prefix.trim(),
      output_root: form.output_root.trim(),
      openlist_remote_prefix: form.openlist_remote_prefix.trim()
    })
    ElMessage.success('生成设置已保存')
    drawerVisible.value = false
    await store.fetchConfig()
  } catch {
    /* 拦截器提示 */
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  if (!store.config) await store.fetchConfig()
})
</script>

<template>
  <el-card shadow="never" class="generation-settings">
    <template #header>
      <div class="generation-settings__header">
        <div class="generation-settings__left">
          <span class="generation-settings__title">生成设置</span>
          <span class="generation-settings__hint">全局生效，任务未单独设置时使用</span>
        </div>
        <el-button :icon="Edit" :disabled="!configured" @click="openDrawer">编辑</el-button>
      </div>
    </template>

    <dl v-if="configured" class="generation-settings__grid">
      <div class="generation-settings__item">
        <dt>最大并发</dt>
        <dd>{{ store.config?.max_concurrent || 1 }} 个任务</dd>
      </div>
      <div class="generation-settings__item">
        <dt>限流间隔</dt>
        <dd>每 {{ store.config?.pause_count || 50 }} 个文件暂停一次</dd>
      </div>
      <div class="generation-settings__item">
        <dt>限流暂停时间</dt>
        <dd>{{ store.config?.pause_time || '0,3,5' }} 秒</dd>
      </div>
      <div class="generation-settings__item">
        <dt>SSL 校验</dt>
        <dd>
          <el-tag :type="store.config?.disable_ssl_verify ? 'warning' : 'success'" effect="light" size="small">
            {{ store.config?.disable_ssl_verify ? '不校验' : '校验证书' }}
          </el-tag>
        </dd>
      </div>
      <div class="generation-settings__item">
        <dt>输出目录前缀</dt>
        <dd>{{ store.config?.output_dir_prefix || '—' }}</dd>
      </div>
      <div class="generation-settings__item">
        <dt>输出根目录</dt>
        <dd>{{ store.config?.output_root || '默认（程序目录下 output）' }}</dd>
      </div>
      <div class="generation-settings__item">
        <dt>OpenList 远程目录前缀</dt>
        <dd>{{ store.config?.openlist_remote_prefix || '—' }}</dd>
      </div>
    </dl>
    <div v-else class="generation-settings__empty">
      <span>还没有生成设置。先跑一次生成，或现在就把输出目录定下来。</span>
      <el-button type="primary" round :icon="Edit" @click="openDrawer">配置生成设置</el-button>
    </div>

    <el-drawer v-model="drawerVisible" title="编辑生成设置" size="520px" destroy-on-close>
      <el-form label-width="130px">
        <el-form-item label="同时执行任务个数">
          <el-input-number v-model="form.max_concurrent" :min="1" :max="100" />
          <div class="remark">限制同时运行的任务数量，超出排队等待</div>
        </el-form-item>
        <el-form-item label="限流间隔文件数">
          <el-input-number v-model="form.pause_count" :min="1" :max="100000" />
          <div class="remark">每隔 N 个文件限流暂停一次</div>
        </el-form-item>
        <el-form-item label="限流暂停时间">
          <el-input v-model="form.pause_time" placeholder="0,3,5" maxlength="512" />
          <div class="remark">秒，逗号分隔；随机暂停其中一项；填 0 表示不限流</div>
        </el-form-item>
        <el-form-item label="禁用 SSL 验证">
          <el-switch v-model="form.disable_ssl_verify" />
          <div class="remark">默认关闭（校验证书）；内网自签名 HTTPS 时开启可禁用验证</div>
        </el-form-item>
        <el-form-item label="输出目录前缀">
          <el-input v-model="form.output_dir_prefix" placeholder="如：/volume1/media（默认空）" maxlength="128" />
          <div class="remark">快速添加任务时拼接到输出目录前，默认空则不拼接</div>
        </el-form-item>
        <el-form-item label="输出根目录">
          <div class="path-row">
            <el-input v-model="form.output_root" placeholder="留空=程序目录下 output；如 D:\Media\strm" maxlength="512" />
            <el-button :icon="FolderOpened" @click="pickOutputRoot">选择</el-button>
          </div>
          <div class="remark">任务输出目录以 / 开头时相对此目录生成；留空时相对程序目录下的 output 生成</div>
        </el-form-item>
        <el-form-item label="OpenList 远程目录前缀">
          <el-input v-model="form.openlist_remote_prefix" placeholder="如：/volume1/media（默认空）" maxlength="256" />
          <div class="remark">自动追更比对云端文件时拼接在任务输出目录前；留空表示从根目录直接匹配</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="drawer-footer">
          <el-button @click="drawerVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
        </div>
      </template>
    </el-drawer>
  </el-card>
</template>

<style scoped lang="scss">
.generation-settings {
  &__header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--up-strm-space-3);
  }

  &__left {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--up-strm-space-2);
  }

  &__title {
    font-size: var(--up-strm-font-size-lg);
    font-weight: 600;
    color: var(--el-text-color-primary);
  }

  &__hint {
    font-size: var(--up-strm-font-size-xs);
    color: var(--el-text-color-secondary);
  }

  &__grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: var(--up-strm-space-3) var(--up-strm-space-5);
    margin: 0;
  }

  &__item {
    dt {
      font-size: var(--up-strm-font-size-xs);
      color: var(--el-text-color-secondary);
      line-height: 1.5;
    }

    dd {
      margin: 2px 0 0;
      font-size: var(--up-strm-font-size-sm);
      color: var(--el-text-color-primary);
      line-height: 1.5;
      word-break: break-all;
    }
  }

  &__empty {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--up-strm-space-3);
    color: var(--el-text-color-secondary);
    font-size: var(--up-strm-font-size-sm);
  }
}

.path-row {
  display: flex;
  align-items: center;
  gap: var(--up-strm-space-2);
  width: 100%;

  :deep(.el-input) {
    flex: 1;
  }
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--up-strm-space-3);
}

.remark {
  font-size: var(--up-strm-font-size-sm);
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
</style>
