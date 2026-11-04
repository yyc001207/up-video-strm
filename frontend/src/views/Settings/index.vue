<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { FolderOpened, Refresh } from '@element-plus/icons-vue'

import { desktopApi } from '@/api/desktop'
import type { DesktopInfo } from '@/types/desktop'

const loading = ref(false)
const info = ref<DesktopInfo | null>(null)
const saving = ref('')

async function load() {
  loading.value = true
  try {
    info.value = (await desktopApi.getInfo()).data
  } finally {
    loading.value = false
  }
}

/** 开机自启：写 HKCU Run，立即生效（下次登录时启动）。 */
async function handleAutostart(value: boolean | string | number) {
  saving.value = 'autostart'
  try {
    info.value = (await desktopApi.setAutostart(Boolean(value))).data
    ElMessage.success(Boolean(value) ? '已设置开机自启' : '已取消开机自启')
  } catch {
    await load()
  } finally {
    saving.value = ''
  }
}

/** 托盘偏好：保存到数据目录 desktop.json，下次启动生效。 */
async function handlePreference(key: 'start_minimized' | 'close_to_tray', value: boolean | string | number) {
  saving.value = key
  try {
    info.value = (await desktopApi.savePreferences({ [key]: Boolean(value) })).data
    ElMessage.success('已保存，重启应用后生效')
  } catch {
    await load()
  } finally {
    saving.value = ''
  }
}

async function handleOpenDataDir() {
  try {
    await desktopApi.openDataDir()
  } catch {
    /* 拦截器已提示 */
  }
}

/** Win11 折叠区修复：把本程序托盘图标写为「始终显示」。 */
async function handleFixTray() {
  saving.value = 'tray'
  try {
    const res = await desktopApi.fixTray()
    if (res.data.promoted) {
      ElMessage.success('已写入固定标记，重启资源管理器或下次登录后生效')
    } else {
      ElMessage.warning('未找到托盘图标注册项，请先启动一次应用后重试')
    }
  } catch {
    /* 拦截器已提示 */
  } finally {
    saving.value = ''
  }
}

/** 打开系统任务栏设置，手动把托盘图标设为显示。 */
async function handleTaskbarSettings() {
  try {
    await desktopApi.openTaskbarSettings()
  } catch {
    /* 拦截器已提示 */
  }
}

onMounted(load)

defineExpose({ reload: load })
</script>

<template>
  <div class="page settings-page">
    <div class="settings" v-loading="loading">
      <el-alert
        v-if="info && !info.is_desktop"
        type="info"
        :closable="false"
        show-icon
        title="当前为网页版（源码运行）"
        description="开机自启、托盘等桌面能力仅在 Windows 安装版中可用；下方开关为只读展示。"
        class="settings__alert"
      />

    <el-card shadow="never" class="settings__card">
      <template #header>
        <div class="settings__header">
          <span>常规</span>
          <el-button link type="primary" :icon="Refresh" @click="load">刷新</el-button>
        </div>
      </template>

      <div v-if="info" class="settings__rows">
        <div class="settings__row">
          <div class="settings__label">
            <div class="settings__title">开机自动启动</div>
            <div class="settings__desc">登录 Windows 后自动在后台启动服务（不弹窗口）</div>
          </div>
          <el-switch
            :model-value="info.autostart"
            :loading="saving === 'autostart'"
            :disabled="!info.autostart_supported"
            @change="handleAutostart"
          />
        </div>

        <div class="settings__row">
          <div class="settings__label">
            <div class="settings__title">启动时最小化到托盘</div>
            <div class="settings__desc">双击启动时不显示窗口，只在托盘常驻；左键托盘图标可打开</div>
          </div>
          <el-switch
            :model-value="info.start_minimized"
            :loading="saving === 'start_minimized'"
            :disabled="!info.is_desktop"
            @change="(v: boolean | string | number) => handlePreference('start_minimized', v)"
          />
        </div>

        <div class="settings__row">
          <div class="settings__label">
            <div class="settings__title">关闭窗口时最小化到托盘</div>
            <div class="settings__desc">点 × 后服务继续运行；关闭后需从托盘菜单「退出」才会结束</div>
          </div>
          <el-switch
            :model-value="info.close_to_tray"
            :loading="saving === 'close_to_tray'"
            :disabled="!info.is_desktop"
            @change="(v: boolean | string | number) => handlePreference('close_to_tray', v)"
          />
        </div>

        <div class="settings__row">
          <div class="settings__label">
            <div class="settings__title">托盘图标显示</div>
            <div class="settings__desc">Windows 11 默认把新图标折叠进「^」，程序无法强制置顶；可写入固定标记（重启资源管理器后生效），或到任务栏设置里手动开启</div>
          </div>
          <div class="settings__actions">
            <el-button
              :disabled="!info?.is_desktop"
              :loading="saving === 'tray'"
              @click="handleFixTray"
            >
              固定到任务栏
            </el-button>
            <el-button link :disabled="!info?.is_desktop" @click="handleTaskbarSettings">
              任务栏设置
            </el-button>
          </div>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="settings__card">
      <template #header>
        <div class="settings__header">
          <span>数据与日志</span>
          <el-button :icon="FolderOpened" :disabled="!info?.is_desktop" @click="handleOpenDataDir">
            打开数据目录
          </el-button>
        </div>
      </template>

      <el-descriptions v-if="info" :column="1" border>
        <el-descriptions-item label="数据目录">{{ info.data_dir }}</el-descriptions-item>
        <el-descriptions-item label="日志文件">{{ info.log_file }}</el-descriptions-item>
        <el-descriptions-item label="程序路径">{{ info.exe_path || '—（网页版无独立程序）' }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card shadow="never" class="settings__card">
      <template #header>
        <span>关于</span>
      </template>
      <el-descriptions v-if="info" :column="1" border>
        <el-descriptions-item label="版本">{{ info.version }}</el-descriptions-item>
        <el-descriptions-item label="运行模式">
          <el-tag :type="info.is_desktop ? 'success' : 'info'" effect="light" size="small">
            {{ info.is_desktop ? 'Windows 桌面版' : '网页版' }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>
    </div>
  </div>
</template>

<style scoped lang="scss">
.settings-page {
  display: flex;
  flex-direction: column;
  gap: var(--up-strm-space-3, 12px);
}

.settings {
  display: flex;
  flex-direction: column;
  gap: var(--up-strm-space-3, 12px);

  &__alert {
    flex-shrink: 0;
  }

  &__card {
    flex-shrink: 0;
  }

  &__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  &__rows {
    display: flex;
    flex-direction: column;
  }

  &__row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 24px;
    padding: 10px 0;

    & + & {
      border-top: 1px solid var(--el-border-color-lighter);
    }
  }

  &__label {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  &__title {
    font-size: 14px;
  }

  &__desc {
    font-size: var(--el-font-size-extra-small);
    color: var(--el-text-color-secondary);
  }

  &__actions {
    display: flex;
    align-items: center;
    gap: 8px;
  }
}
</style>
