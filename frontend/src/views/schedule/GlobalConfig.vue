<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Edit, FolderOpened, Plus, Refresh } from '@element-plus/icons-vue'

import { openlistApi } from '@/api/openlist'
import { useOpenlistStore } from '@/stores/openlist'
import type { OpenListConfig, OpenListServer } from '@/types/openlist'

const store = useOpenlistStore()

const loading = ref(false)
/** 单服务器模式：配置与唯一服务器统一取自 store（`server` = servers[0] ?? null）。 */
const config = computed<OpenListConfig | null>(() => store.config)
const server = computed<OpenListServer | null>(() => store.server)

// 服务器弹窗
const serverDialogVisible = ref(false)
const editingServerId = ref<number | null>(null)
const savingServer = ref(false)
const refreshingCache = ref(false)
const serverForm = reactive({ name: '', server_url: '', token: '', parent_dirs: '', skip_validation: false })

// 全局配置弹窗
const configDialogVisible = ref(false)
const savingConfig = ref(false)
const configForm = reactive({ video_formats: '', subtitle_formats: '', max_concurrent: 1, pause_count: 50, pause_time: '0,3,5', disable_ssl_verify: false, log_to_db: false, output_dir_prefix: '', output_root: '' })

async function load() {
  loading.value = true
  try {
    await store.fetchConfig()
  } finally {
    loading.value = false
  }
}

function openCreateServer() {
  editingServerId.value = null
  serverForm.name = ''
  serverForm.server_url = ''
  serverForm.token = ''
  serverForm.parent_dirs = ''
  serverForm.skip_validation = false
  serverDialogVisible.value = true
}

function openEditServer(target: OpenListServer) {
  editingServerId.value = target.id
  serverForm.name = target.name ?? ''
  serverForm.server_url = target.server_url
  // 编辑时不回填 Token：留空表示保持原 Token 不变
  serverForm.token = ''
  serverForm.parent_dirs = (target.parent_dirs ?? []).join('\n')
  serverForm.skip_validation = false
  serverDialogVisible.value = true
}

/** 解析父级目录输入（每行一个路径，去空白去重）。 */
function parseParentDirs(): string[] {
  const dirs: string[] = []
  for (const line of serverForm.parent_dirs.split('\n')) {
    const path = line.trim()
    if (path && !dirs.includes(path)) dirs.push(path)
  }
  return dirs
}

async function handleSaveServer() {
  if (!serverForm.server_url.trim()) {
    ElMessage.warning('请填写服务器地址')
    return
  }
  const parentDirs = parseParentDirs()
  savingServer.value = true
  try {
    if (editingServerId.value != null) {
      await openlistApi.updateServer(editingServerId.value, {
        name: serverForm.name.trim() || undefined,
        server_url: serverForm.server_url.trim(),
        token: serverForm.token.trim() || undefined,
        parent_dirs: parentDirs,
        skip_validation: serverForm.skip_validation
      })
    } else {
      await openlistApi.createServer({
        name: serverForm.name.trim() || undefined,
        server_url: serverForm.server_url.trim(),
        token: serverForm.token.trim() || undefined,
        parent_dirs: parentDirs,
        skip_validation: serverForm.skip_validation
      })
    }
    ElMessage.success('服务器配置已保存')
    serverDialogVisible.value = false
    await load()
  } catch {
    /* 拦截器提示 */
  } finally {
    savingServer.value = false
  }
}

/** 手动刷新该服务器所有父级目录的一级子目录缓存。 */
async function handleRefreshCache(target: OpenListServer) {
  refreshingCache.value = true
  try {
    const dirs = target.parent_dirs ?? []
    const paths: Array<string | undefined> = dirs.length ? dirs : [undefined]
    const results = await Promise.all(paths.map(p => openlistApi.refreshServerDirs(target.id, p)))
    const total = results.reduce((sum, r) => sum + (r.data.count ?? 0), 0)
    ElMessage.success(
      dirs.length
        ? `目录缓存已刷新（${results.length} 个父级目录，共 ${total} 个子目录）`
        : `目录缓存已刷新（共 ${total} 个子目录）`
    )
  } catch {
    /* 拦截器提示 */
  } finally {
    refreshingCache.value = false
  }
}

async function handleDeleteServer(target: OpenListServer) {
  try {
    await ElMessageBox.confirm(
      `删除服务器「${target.name || target.server_url}」？该操作不可恢复。`,
      '删除服务器',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    await openlistApi.deleteServer(target.id)
    ElMessage.success('已删除')
    await load()
  } catch {
    /* 拦截器提示 */
  }
}

function openEditConfig() {
  const current = config.value
  if (!current) return
  configForm.video_formats = current.video_formats ?? ''
  configForm.subtitle_formats = current.subtitle_formats ?? ''
  configForm.max_concurrent = current.max_concurrent || 1
  configForm.pause_count = current.pause_count || 50
  configForm.pause_time = current.pause_time ?? '0,3,5'
  configForm.disable_ssl_verify = current.disable_ssl_verify ?? false
  configForm.log_to_db = current.log_to_db ?? false
  configForm.output_dir_prefix = current.output_dir_prefix ?? ''
  configForm.output_root = current.output_root ?? ''
  configDialogVisible.value = true
}

/** 桌面版唤起系统文件夹选择框；浏览器版没有该能力，提示手动填写。 */
async function pickOutputRoot() {
  const bridge = (window as unknown as {
    pywebview?: { api?: { pick_directory?: (startDir?: string) => Promise<string> } }
  }).pywebview
  if (!bridge?.api?.pick_directory) {
    ElMessage.warning('当前不是桌面版，请手动填写路径')
    return
  }
  try {
    const picked = await bridge.api.pick_directory(configForm.output_root.trim() || '')
    if (picked) configForm.output_root = picked
  } catch {
    ElMessage.error('打开文件夹选择框失败')
  }
}

async function handleSaveConfig() {
  savingConfig.value = true
  try {
    await openlistApi.updateConfig({
      video_formats: configForm.video_formats.trim(),
      subtitle_formats: configForm.subtitle_formats.trim(),
      max_concurrent: configForm.max_concurrent,
      pause_count: configForm.pause_count,
      pause_time: configForm.pause_time.trim(),
      disable_ssl_verify: configForm.disable_ssl_verify,
      log_to_db: configForm.log_to_db,
      output_dir_prefix: configForm.output_dir_prefix.trim(),
      output_root: configForm.output_root.trim()
    })
    ElMessage.success('全局配置已保存')
    configDialogVisible.value = false
    await load()
  } catch {
    /* 拦截器提示 */
  } finally {
    savingConfig.value = false
  }
}

onMounted(load)

defineExpose({ reload: load })
</script>

<template>
  <div class="page global-config">
    <el-row :gutter="16">
      <!-- 左 8 栏：唯一服务器配置卡 -->
      <el-col :xs="24" :lg="16">
        <el-card v-loading="loading" shadow="never" class="global-config__card">
          <template #header>
            <div class="card-header">
              <span class="card-title">服务器配置</span>
              <div v-if="server" class="card-header__actions">
                <el-button :icon="Refresh" :loading="refreshingCache" @click="handleRefreshCache(server)">
                  刷新缓存
                </el-button>
                <el-button :icon="Edit" @click="openEditServer(server)">编辑</el-button>
                <el-button type="danger" plain :icon="Delete" @click="handleDeleteServer(server)">删除</el-button>
              </div>
            </div>
          </template>

          <div v-if="server" class="server-card">
            <div class="server-card__head">
              <span class="server-card__name">{{ server.name || '未命名' }}</span>
              <el-tag :type="server.is_active ? 'success' : 'info'" effect="light" size="small">
                {{ server.is_active ? '启用' : '停用' }}
              </el-tag>
            </div>

            <dl class="meta-list">
              <div class="meta-list__item">
                <dt>服务器地址</dt>
                <dd>{{ server.server_url }}</dd>
              </div>
              <div class="meta-list__item">
                <dt>访问 Token</dt>
                <dd>
                  <el-tag :type="server.has_token ? 'success' : 'danger'" effect="light" size="small">
                    {{ server.has_token ? '已配置' : '未配置' }}
                  </el-tag>
                </dd>
              </div>
              <div class="meta-list__item">
                <dt>父级目录</dt>
                <dd>
                  <template v-if="server.parent_dirs?.length">
                    <el-tag
                      v-for="dir in server.parent_dirs"
                      :key="dir"
                      type="info"
                      effect="plain"
                      size="small"
                      class="meta-list__dir"
                    >
                      {{ dir }}
                    </el-tag>
                  </template>
                  <span v-else class="global-config__muted">未配置父级目录</span>
                </dd>
              </div>
            </dl>
          </div>

          <el-empty v-else-if="!loading" description="尚未配置 OpenList 服务器" :image-size="90">
            <el-button type="primary" :icon="Plus" @click="openCreateServer">新增服务器</el-button>
          </el-empty>
        </el-card>
      </el-col>

      <!-- 右 4 栏：运行参数摘要卡（definition list，消除留白） -->
      <el-col :xs="24" :lg="8">
        <el-card shadow="never" class="global-config__card">
          <template #header>
            <div class="card-header">
              <span class="card-title">运行参数</span>
              <el-button :icon="Edit" :disabled="!config" @click="openEditConfig">编辑配置</el-button>
            </div>
          </template>

          <dl v-if="config" class="meta-list">
            <div class="meta-list__item">
              <dt>最大并发</dt>
              <dd>{{ config.max_concurrent || 1 }} 个任务</dd>
            </div>
            <div class="meta-list__item">
              <dt>视频格式</dt>
              <dd>{{ config.video_formats || '—' }}</dd>
            </div>
            <div class="meta-list__item">
              <dt>字幕格式</dt>
              <dd>{{ config.subtitle_formats || '—' }}</dd>
            </div>
            <div class="meta-list__item">
              <dt>暂停策略</dt>
              <dd>
                每 {{ config.pause_count || 50 }} 个文件暂停一次（{{ config.pause_time || '0,3,5' }} 秒）
              </dd>
            </div>
            <div class="meta-list__item">
              <dt>SSL 校验</dt>
              <dd>
                <el-tag :type="config.disable_ssl_verify ? 'warning' : 'success'" effect="light" size="small">
                  {{ config.disable_ssl_verify ? '不校验' : '校验证书' }}
                </el-tag>
              </dd>
            </div>
            <div class="meta-list__item">
              <dt>日志入库</dt>
              <dd>
                <el-tag :type="config.log_to_db ? 'warning' : 'success'" effect="light" size="small">
                  {{ config.log_to_db ? '双写数据库' : '仅写文件' }}
                </el-tag>
              </dd>
            </div>
            <div class="meta-list__item">
              <dt>输出前缀</dt>
              <dd>{{ config.output_dir_prefix || '—' }}</dd>
            </div>
            <div class="meta-list__item">
              <dt>输出根目录</dt>
              <dd>{{ config.output_root || '默认（程序目录下 output）' }}</dd>
            </div>
          </dl>
          <el-empty v-else description="暂无运行参数" :image-size="70" />
        </el-card>
      </el-col>
    </el-row>

    <el-dialog
      v-model="serverDialogVisible"
      :title="editingServerId != null ? '编辑服务器' : '新增服务器'"
      width="520px"
      destroy-on-close
    >
      <el-form label-width="100px">
        <el-form-item label="名称">
          <el-input v-model="serverForm.name" placeholder="如：主服务器" maxlength="128" />
        </el-form-item>
        <el-form-item label="服务器地址">
          <el-input v-model="serverForm.server_url" placeholder="http://192.168.199.238:5244" maxlength="512" />
          <div class="remark">OpenList/AList 等 API 地址</div>
        </el-form-item>
        <el-form-item label="访问 Token">
          <el-input
            v-model="serverForm.token"
            type="password"
            show-password
            autocomplete="new-password"
            :placeholder="editingServerId != null ? '已设置，留空保持不变' : '请输入 Token'"
            maxlength="512"
          />
          <div class="remark">编辑时不回填，留空表示保持原 Token 不变</div>
        </el-form-item>
        <el-form-item label="父级目录">
          <el-input
            v-model="serverForm.parent_dirs"
            type="textarea"
            :rows="3"
            placeholder="每行一个目录，自动补全 / 前缀，如：&#10;emby/音乐&#10;电影"
          />
          <div class="remark">无需手写 /（如 emby/音乐 → /emby/音乐）；保存时校验格式、存在性与读写权限（校验通过后自动缓存一级子目录）</div>
        </el-form-item>
        <el-form-item label="跳过校验">
          <el-switch v-model="serverForm.skip_validation" />
          <div class="remark">服务器暂时不可达时可跳过存在性/读写校验，格式校验始终执行</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="serverDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingServer" @click="handleSaveServer">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="configDialogVisible" title="编辑全局配置" width="520px" destroy-on-close>
      <el-form label-width="130px">
        <el-form-item label="同时执行任务个数">
          <el-input-number v-model="configForm.max_concurrent" :min="1" :max="100" />
          <div class="remark">限制同时运行的任务数量，超出排队等待</div>
        </el-form-item>
        <el-form-item label="视频格式">
          <el-input v-model="configForm.video_formats" placeholder="mp4,mkv,avi,wmv,flv,mov,webm,ts" maxlength="512" />
          <div class="remark">英文逗号分隔</div>
        </el-form-item>
        <el-form-item label="字幕格式">
          <el-input v-model="configForm.subtitle_formats" placeholder="srt,ass,ssa,sub,vtt" maxlength="512" />
          <div class="remark">英文逗号分隔</div>
        </el-form-item>
        <el-form-item label="限流间隔文件数">
          <el-input-number v-model="configForm.pause_count" :min="1" :max="100000" />
          <div class="remark">每隔 N 个文件限流暂停一次</div>
        </el-form-item>
        <el-form-item label="限流暂停时间">
          <el-input v-model="configForm.pause_time" placeholder="0,3,5" maxlength="512" />
          <div class="remark">秒，逗号分隔；随机暂停其中一项；填 0 表示不限流</div>
        </el-form-item>
        <el-form-item label="禁用 SSL 验证">
          <el-switch v-model="configForm.disable_ssl_verify" />
          <div class="remark">默认关闭（校验证书）；内网自签名 HTTPS 时开启可禁用验证</div>
        </el-form-item>
        <el-form-item label="日志写入数据库">
          <el-switch v-model="configForm.log_to_db" />
          <div class="remark">默认关闭（仅写日志文件，DB 不再积累日志）；需结构化日志时开启</div>
        </el-form-item>
        <el-form-item label="输出根目录">
          <div class="path-row">
            <el-input v-model="configForm.output_root" placeholder="留空=程序目录下 output；如 D:\Media\strm" maxlength="512" />
            <el-button :icon="FolderOpened" @click="pickOutputRoot">选择</el-button>
          </div>
          <div class="remark">任务输出目录以 / 开头时相对此目录生成；留空时相对程序目录下的 output 生成</div>
        </el-form-item>
        <el-form-item label="输出目录前缀">
          <el-input v-model="configForm.output_dir_prefix" placeholder="如：/volume1/media（默认空）" maxlength="128" />
          <div class="remark">快速添加任务配置时拼接到输出目录前，默认空则不拼接</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="configDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingConfig" @click="handleSaveConfig">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
.global-config {
  &__card {
    height: 100%;
  }

  &__muted {
    color: var(--el-text-color-secondary);
    font-size: var(--up-strm-font-size-sm, 13px);
  }
}

.server-card {
  display: flex;
  flex-direction: column;
  gap: var(--up-strm-space-3, 12px);
  padding: var(--up-strm-space-4, 16px);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--up-strm-radius-md, 8px);
  background: var(--el-bg-color-overlay);

  &__head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--up-strm-space-2, 8px);
  }

  &__name {
    color: var(--el-text-color-primary);
    font-size: var(--up-strm-font-size-lg, 16px);
    font-weight: 600;
    line-height: 1.4;
    word-break: break-all;
  }

  .meta-list__item:last-child {
    padding-bottom: 0;
  }
}

.card-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--up-strm-space-3, 12px);
}

.card-header__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
}

.card-title {
  font-size: var(--up-strm-font-size-lg, 16px);
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.meta-list {
  margin: 0;

  &__item {
    display: grid;
    grid-template-columns: 84px minmax(0, 1fr);
    gap: var(--up-strm-space-2, 8px);
    padding: 10px 0;
    border-top: 1px solid var(--el-border-color-lighter);

    &:first-child {
      border-top: none;
      padding-top: 0;
    }

    dt {
      font-size: var(--up-strm-font-size-sm, 13px);
      color: var(--el-text-color-secondary);
      line-height: 1.5;
    }

    dd {
      margin: 0;
      font-size: var(--up-strm-font-size-sm, 13px);
      color: var(--el-text-color-primary);
      line-height: 1.5;
      word-break: break-all;
    }
  }

  &__dir {
    margin: 2px 4px 2px 0;
  }
}

.remark {
  font-size: var(--up-strm-font-size-sm, 13px);
  color: var(--el-text-color-secondary);
  line-height: 1.5;
  margin-top: 2px;
}

.path-row {
  display: flex;
  align-items: center;
  gap: var(--up-strm-space-2, 8px);
  width: 100%;

  :deep(.el-input) {
    flex: 1;
  }
}
</style>
