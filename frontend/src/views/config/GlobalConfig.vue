<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Edit, Plus, Refresh } from '@element-plus/icons-vue'

import { openlistApi } from '@/api/openlist'
import { uploaderApi } from '@/api/uploader'
import { useOpenlistStore } from '@/stores/openlist'
import type { OpenListConfig, OpenListServer } from '@/types/openlist'
import type { UploadPlatformConfig } from '@/types/uploader'
import { formatDateTime } from '@/utils/date'
import GenerationSettings from './components/GenerationSettings.vue'

const store = useOpenlistStore()

const loading = ref(false)
/** 单服务器模式：配置与唯一服务器统一取自 store（`server` = servers[0] ?? null）。 */
const config = computed<OpenListConfig | null>(() => store.config)
const server = computed<OpenListServer | null>(() => store.server)

/** 服务器连通状态：未配置 / 检测中 / 在线 / 离线。 */
type ServerStatus = 'none' | 'checking' | 'online' | 'offline'
const serverStatus = ref<ServerStatus>('none')
const statusTextMap: Record<ServerStatus, string> = {
  none: '未配置',
  checking: '检测中',
  online: '在线',
  offline: '离线'
}
const serverStatusText = computed(() => statusTextMap[serverStatus.value])
const serverStatusTag = computed<'success' | 'danger' | 'warning' | 'info'>(() => {
  if (serverStatus.value === 'online') return 'success'
  if (serverStatus.value === 'offline') return 'danger'
  if (serverStatus.value === 'checking') return 'warning'
  return 'info'
})
let statusTimer: number | undefined

// 服务器弹窗
const serverDialogVisible = ref(false)
const editingServerId = ref<number | null>(null)
const savingServer = ref(false)
const testingConnection = ref(false)
const refreshingCache = ref(false)
const serverForm = reactive({ server_url: '', token: '', parent_dirs: '', skip_validation: false })

// 视频/字幕格式编辑抽屉
const formatDrawerVisible = ref(false)
const savingFormats = ref(false)
const formatForm = reactive({ video_formats: '', subtitle_formats: '' })

// 123 云盘：clientID/clientSecret 保存后只回显脱敏值；token 由后端自动续期
const pan123Config = ref<UploadPlatformConfig | null>(null)
const pan123Form = reactive({ client_id: '', client_secret: '' })
const pan123DialogVisible = ref(false)
const savingPan123 = ref(false)
const testingPan123 = ref(false)
const clearingPan123 = ref(false)

type Pan123Status = 'none' | 'checking' | 'online' | 'offline'
const pan123Status = computed<Pan123Status>(() => {
  const current = pan123Config.value
  if (!current || !current.has_secret) return 'none'
  if (current.token_status === 'valid') return 'online'
  return 'offline'
})
const pan123StatusText = computed(() => {
  const current = pan123Config.value
  if (!current || !current.has_secret) return '未配置'
  if (current.token_status === 'valid') return '已连接'
  if (current.token_status === 'expired') return '凭证已过期'
  return '待连接'
})
const pan123StatusTag = computed<'success' | 'danger' | 'warning' | 'info'>(() => {
  if (pan123Status.value === 'online') return 'success'
  if (pan123Status.value === 'offline') return 'warning'
  return 'info'
})
const pan123TokenText = computed(() => {
  const current = pan123Config.value
  if (!current?.has_secret) return '未配置凭据'
  if (current.token_status === 'valid') return '有效（请求时自动续期）'
  if (current.token_status === 'expired') return '已过期（下次请求自动刷新）'
  return '尚未获取'
})

async function load() {
  loading.value = true
  try {
    await store.fetchConfig()
  } finally {
    loading.value = false
  }
}

/** 探测当前服务器连通性（未配置时为 none）。 */
async function checkServerStatus() {
  const current = server.value
  if (!current) {
    serverStatus.value = 'none'
    return
  }
  serverStatus.value = 'checking'
  try {
    // silent：后台轮询状态失败时不弹全局错误消息，仅更新状态标签
    await openlistApi.testServerConnection({ server_url: current.server_url, server_id: current.id }, { silent: true })
    serverStatus.value = 'online'
  } catch {
    serverStatus.value = 'offline'
  }
}

function openCreateServer() {
  editingServerId.value = null
  serverForm.server_url = ''
  serverForm.token = ''
  serverForm.parent_dirs = ''
  serverForm.skip_validation = false
  serverDialogVisible.value = true
}

function openEditServer(target: OpenListServer) {
  editingServerId.value = target.id
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

async function handleTestConnection() {
  const serverUrl = serverForm.server_url.trim()
  if (!serverUrl) {
    ElMessage.warning('请填写服务器地址')
    return
  }
  testingConnection.value = true
  try {
    const result = await openlistApi.testServerConnection({
      server_url: serverUrl,
      token: serverForm.token.trim() || undefined,
      // 编辑已有服务器且 Token 留空时，后端用已保存的 Token 测试
      server_id: editingServerId.value ?? undefined
    })
    ElMessage.success(result.data.message)
  } catch {
    /* 拦截器提示 */
  } finally {
    testingConnection.value = false
  }
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
        server_url: serverForm.server_url.trim(),
        token: serverForm.token.trim() || undefined,
        parent_dirs: parentDirs,
        skip_validation: serverForm.skip_validation
      })
    } else {
      await openlistApi.createServer({
        server_url: serverForm.server_url.trim(),
        token: serverForm.token.trim() || undefined,
        parent_dirs: parentDirs,
        skip_validation: serverForm.skip_validation
      })
    }
    ElMessage.success('服务器配置已保存')
    serverDialogVisible.value = false
    await load()
    await checkServerStatus()
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
    await checkServerStatus()
  } catch {
    /* 拦截器提示 */
  } finally {
    refreshingCache.value = false
  }
}

async function handleDeleteServer(target: OpenListServer) {
  try {
    await ElMessageBox.confirm(
      `删除服务器「${target.server_url}」？该操作不可恢复。`,
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
    await checkServerStatus()
  } catch {
    /* 拦截器提示 */
  }
}

function openEditFormats() {
  const current = config.value
  if (!current) return
  formatForm.video_formats = current.video_formats ?? ''
  formatForm.subtitle_formats = current.subtitle_formats ?? ''
  formatDrawerVisible.value = true
}

/** 只提交视频/字幕格式：后端其余字段为 None 时保持原值，不会覆盖运行参数。 */
async function handleSaveFormats() {
  savingFormats.value = true
  try {
    await openlistApi.updateConfig({
      video_formats: formatForm.video_formats.trim(),
      subtitle_formats: formatForm.subtitle_formats.trim()
    })
    ElMessage.success('格式设置已保存')
    formatDrawerVisible.value = false
    await load()
  } catch {
    /* 拦截器提示 */
  } finally {
    savingFormats.value = false
  }
}

async function loadPan123() {
  try {
    const res = await uploaderApi.getConfig()
    pan123Config.value = res.data
    pan123Form.client_id = res.data.client_id ?? ''
    pan123Form.client_secret = ''
  } catch {
    /* 拦截器提示 */
  }
}

/** 打开编辑弹框：Client ID 回填，Secret 始终留空（留空表示不修改）。 */
function openPan123Edit() {
  pan123Form.client_id = pan123Config.value?.client_id ?? ''
  pan123Form.client_secret = ''
  pan123DialogVisible.value = true
}

/** 保存 123 云盘凭据：密钥留空表示保持不变。 */
async function handleSavePan123() {
  savingPan123.value = true
  try {
    const res = await uploaderApi.updateConfig({
      client_id: pan123Form.client_id.trim(),
      client_secret: pan123Form.client_secret.trim()
    })
    pan123Config.value = res.data
    pan123Form.client_id = res.data.client_id ?? ''
    pan123Form.client_secret = ''
    pan123DialogVisible.value = false
    ElMessage.success('123 云盘配置已保存')
  } catch {
    /* 拦截器提示 */
  } finally {
    savingPan123.value = false
  }
}

/** 删除（清空）123 云盘凭据：需二次确认，删除后云盘上传不可用。 */
async function handleClearPan123() {
  try {
    await ElMessageBox.confirm(
      '确认删除 123 云盘配置？删除后云盘上传将无法上传，需要重新填写 Client ID / Client Secret。',
      '删除 123 云盘配置',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  clearingPan123.value = true
  try {
    const res = await uploaderApi.clearConfig()
    pan123Config.value = res.data
    pan123Form.client_id = ''
    pan123Form.client_secret = ''
    ElMessage.success('123 云盘配置已删除')
  } catch {
    /* 拦截器提示 */
  } finally {
    clearingPan123.value = false
  }
}

/** 测试连通性：优先用输入框中的新凭据，留空时后端使用已保存凭据。 */
async function handleTestPan123() {  testingPan123.value = true
  try {
    const res = await uploaderApi.testConnection({
      client_id: pan123Form.client_id.trim() || undefined,
      client_secret: pan123Form.client_secret.trim() || undefined
    })
    // 测试只验证凭据，不保存配置；不要重新拉取配置，避免覆盖弹框中已填写的 Client ID / Secret
    ElMessage.success(res.data.message || '连接成功')
  } catch {
    /* 拦截器提示 */
  } finally {
    testingPan123.value = false
  }
}

onMounted(async () => {
  await load()
  await loadPan123()
  await checkServerStatus()
  // 页面停留期间定时刷新服务器状态（60s）
  statusTimer = window.setInterval(() => {
    void checkServerStatus()
  }, 60000)
})

onUnmounted(() => {
  if (statusTimer !== undefined) {
    window.clearInterval(statusTimer)
    statusTimer = undefined
  }
})

defineExpose({ reload: load })
</script>

<template>
  <div class="page global-config">
    <el-row :gutter="16" class="global-config__row">
      <!-- 左 8 栏：唯一服务器配置卡 -->
      <el-col :xs="24" :lg="16">
        <el-card v-loading="loading" shadow="never" class="global-config__card">
          <template #header>
            <div class="card-header">
              <div class="card-header__left">
                <span class="card-title">服务器配置</span>
                <el-tag :type="serverStatusTag" effect="light" size="small" class="server-status">
                  <span class="server-status__dot" :class="`server-status__dot--${serverStatus}`" />
                  {{ serverStatusText }}
                </el-tag>
              </div>
              <div v-if="server" class="card-header__actions">
                <el-button plain :icon="Refresh" :loading="refreshingCache" @click="handleRefreshCache(server)">
                  刷新缓存
                </el-button>
                <el-button plain :icon="Edit" @click="openEditServer(server)">编辑</el-button>
                <el-button type="danger" plain :icon="Delete" @click="handleDeleteServer(server)">删除</el-button>
              </div>
            </div>
          </template>

          <div v-if="server" class="server-card">
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

          <el-empty v-else-if="!loading" description="尚未配置 OpenList 服务器" :image-size="60">
            <el-button type="primary" plain :icon="Plus" @click="openCreateServer">新增服务器</el-button>
          </el-empty>
        </el-card>
      </el-col>

      <!-- 右 4 栏：视频/字幕格式（生成设置见下方独立卡片） -->
      <el-col :xs="24" :lg="8">
        <el-card shadow="never" class="global-config__card">
          <template #header>
            <div class="card-header">
              <span class="card-title">视频与字幕格式</span>
              <el-button plain :icon="Edit" :disabled="!config" @click="openEditFormats">编辑</el-button>
            </div>
          </template>

          <dl v-if="config" class="meta-list">
            <div class="meta-list__item">
              <dt>视频格式</dt>
              <dd>{{ config.video_formats || '—' }}</dd>
            </div>
            <div class="meta-list__item">
              <dt>字幕格式</dt>
              <dd>{{ config.subtitle_formats || '—' }}</dd>
            </div>
          </dl>
          <el-empty v-else description="暂无格式设置" :image-size="60" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 生成设置：原任务页「默认运行参数」，全局生效 -->
    <el-row :gutter="16" class="global-config__row">
      <el-col :span="24">
        <GenerationSettings />
      </el-col>
    </el-row>

    <!-- 123 云盘：云盘上传模块的凭据配置（全局唯一，密钥仅脱敏回显；展示卡片 + 编辑弹框） -->
    <el-card shadow="never" class="global-config__card pan123-card">
      <template #header>
        <div class="card-header">
          <div class="card-header__left">
            <span class="card-title">123 云盘</span>
            <el-tag :type="pan123StatusTag" effect="light" size="small" class="server-status">
              <span class="server-status__dot" :class="`server-status__dot--${pan123Status}`" />
              {{ pan123StatusText }}
            </el-tag>
          </div>
          <div class="card-header__actions">
            <el-button plain :loading="testingPan123" @click="handleTestPan123">测试连接</el-button>
            <el-button plain :icon="Edit" @click="openPan123Edit">编辑</el-button>
            <el-button
              v-if="pan123Config?.client_id || pan123Config?.has_secret"
              type="danger"
              plain
              :icon="Delete"
              :loading="clearingPan123"
              @click="handleClearPan123"
            >
              删除
            </el-button>
          </div>
        </div>
      </template>

      <dl v-if="pan123Config" class="meta-list">
        <div class="meta-list__item">
          <dt>Client ID</dt>
          <dd>{{ pan123Config.client_id || '未配置' }}</dd>
        </div>
        <div class="meta-list__item">
          <dt>Client Secret</dt>
          <dd>{{ pan123Config.has_secret ? `已配置（${pan123Config.secret_masked}）` : '未配置' }}</dd>
        </div>
        <div class="meta-list__item">
          <dt>Token 状态</dt>
          <dd>{{ pan123TokenText }}</dd>
        </div>
        <div class="meta-list__item">
          <dt>Token 过期时间</dt>
          <dd>{{ formatDateTime(pan123Config.token_expires_at) }}</dd>
        </div>
      </dl>
      <el-empty v-else description="尚未配置 123 云盘凭据" :image-size="60">
        <el-button type="primary" plain :icon="Edit" @click="openPan123Edit">立即配置</el-button>
      </el-empty>
    </el-card>

    <el-dialog
      v-model="pan123DialogVisible"
      title="编辑 123 云盘配置"
      width="520px"
      destroy-on-close
    >
      <el-form label-width="120px">
        <el-form-item label="Client ID">
          <el-input
            v-model="pan123Form.client_id"
            placeholder="123 云盘开放平台应用 Client ID"
            maxlength="128"
          />
        </el-form-item>
        <el-form-item label="Client Secret">
          <el-input
            v-model="pan123Form.client_secret"
            type="password"
            show-password
            autocomplete="new-password"
            :placeholder="
              pan123Config?.has_secret
                ? `已保存（${pan123Config.secret_masked}），留空表示不修改`
                : '123 云盘开放平台应用 Client Secret'
            "
            maxlength="256"
          />
          <div class="remark">密钥使用 Windows DPAPI 加密存储，接口只回显脱敏值</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button :loading="testingPan123" @click="handleTestPan123">测试连通性</el-button>
          <div class="dialog-footer__right">
            <el-button @click="pan123DialogVisible = false">取消</el-button>
            <el-button type="primary" :loading="savingPan123" @click="handleSavePan123">保存</el-button>
          </div>
        </div>
      </template>
    </el-dialog>


    <el-dialog
      v-model="serverDialogVisible"
      :title="editingServerId != null ? '编辑服务器' : '新增服务器'"
      width="520px"
      destroy-on-close
    >
      <el-form label-width="100px">
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
        <div class="dialog-footer">
          <el-button :loading="testingConnection" @click="handleTestConnection">测试连通性</el-button>
          <div class="dialog-footer__right">
            <el-button @click="serverDialogVisible = false">取消</el-button>
            <el-button type="primary" :loading="savingServer" @click="handleSaveServer">保存</el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <el-drawer v-model="formatDrawerVisible" title="编辑视频与字幕格式" size="460px" destroy-on-close>
      <el-form label-width="96px">
        <el-form-item label="视频格式">
          <el-input v-model="formatForm.video_formats" placeholder="mp4,mkv,avi,wmv,flv,mov,webm,ts" maxlength="512" />
          <div class="remark">英文逗号分隔</div>
        </el-form-item>
        <el-form-item label="字幕格式">
          <el-input v-model="formatForm.subtitle_formats" placeholder="srt,ass,ssa,sub,vtt" maxlength="512" />
          <div class="remark">英文逗号分隔</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="drawer-footer">
          <el-button @click="formatDrawerVisible = false">取消</el-button>
          <el-button type="primary" :loading="savingFormats" @click="handleSaveFormats">保存</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped lang="scss">
.global-config {
  &__muted {
    color: var(--el-text-color-secondary);
    font-size: var(--up-strm-font-size-sm, 13px);
  }
}

.global-config__row {
  align-items: flex-start;
}

.server-card {  display: flex;
  flex-direction: column;
  gap: var(--up-strm-space-3, 12px);
  padding: var(--up-strm-space-4, 16px);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--up-strm-radius-md, 8px);
  background: var(--el-bg-color-overlay);

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

.card-header__left {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--up-strm-space-2, 8px);
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

/* 服务器连通状态：在线/离线/未配置/检测中，颜色沿用 Element Plus 语义色 */
.server-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.server-status__dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--el-text-color-placeholder);

  &--online {
    background: var(--el-color-success);
  }

  &--offline {
    background: var(--el-color-danger);
  }

  &--checking {
    background: var(--el-color-warning);
  }
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

/* 服务器弹窗底部：左侧连通性测试，右侧取消/保存 */
.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--up-strm-space-2, 8px);

  &__right {
    display: flex;
    gap: var(--up-strm-space-2, 8px);
  }
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--up-strm-space-2, 8px);
}

.pan123-card {
  margin-top: var(--up-strm-space-4, 16px);
}
</style>
