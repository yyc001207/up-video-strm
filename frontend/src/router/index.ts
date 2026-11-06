import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'Today',
      component: () => import('@/views/Today.vue'),
      meta: { title: '今天', description: '一屏看清生成、上传与追更三件事' }
    },
    {
      path: '/schedule',
      redirect: '/schedule/tasks'
    },
    {
      path: '/schedule/tasks',
      name: 'ScheduleTasks',
      component: () => import('@/views/schedule/TaskManage.vue'),
      meta: { title: '任务', description: '维护 STRM 生成任务与处理路径' }
    },
    {
      path: '/schedule/execution',
      name: 'ScheduleExecution',
      component: () => import('@/views/schedule/Execution.vue'),
      meta: { title: '开始执行', description: '选择任务与执行模式，批量启动 STRM 生成' }
    },
    {
      path: '/schedule/realtime',
      name: 'ScheduleRealtime',
      component: () => import('@/views/schedule/RealtimeLog.vue'),
      meta: { title: '运行详情', description: '跟踪执行进度与实时输出' }
    },
    {
      path: '/schedule/history',
      name: 'ScheduleHistory',
      component: () => import('@/views/schedule/TaskHistory.vue'),
      meta: { title: '运行记录', description: '查看任务历次执行记录与日志' }
    },
    {
      // 旧路径兼容：连接与格式已升级为与生成/上传/追更平级的入口
      path: '/schedule/config',
      redirect: '/config'
    },
    {
      path: '/config',
      name: 'GlobalConfig',
      component: () => import('@/views/config/GlobalConfig.vue'),
      meta: { title: '连接与格式', description: '服务器连接与视频/字幕格式' }
    },
    {
      path: '/upload',
      redirect: '/upload/tasks'
    },
    {
      path: '/upload/tasks',
      name: 'UploadTasks',
      component: () => import('@/views/upload/TaskConfig.vue'),
      meta: { title: '任务', description: '维护上传任务：本地目录、云端目录与集数映射' }
    },
    {
      path: '/upload/rename',
      name: 'UploadRenameRules',
      component: () => import('@/views/upload/RenameRules.vue'),
      meta: { title: '命名规则', description: '维护上传文件命名模板（SxxExx.ext）' }
    },
    {
      path: '/upload/execution',
      name: 'UploadExecution',
      component: () => import('@/views/upload/Execution.vue'),
      meta: { title: '开始执行', description: '勾选任务与执行参数，批量启动上传' }
    },
    {
      path: '/upload/realtime',
      name: 'UploadRealtime',
      component: () => import('@/views/upload/RealtimeLog.vue'),
      meta: { title: '运行详情', description: '跟踪上传进度、文件明细与实时输出' }
    },
    {
      path: '/upload/history',
      name: 'UploadHistory',
      component: () => import('@/views/upload/TaskHistory.vue'),
      meta: { title: '运行记录', description: '按任务查看上传执行记录、文件明细与日志回放' }
    },
    {
      path: '/automation',
      redirect: '/automation/tasks'
    },
    {
      path: '/automation/tasks',
      name: 'AutomationTasks',
      component: () => import('@/views/automation/TaskConfig.vue'),
      meta: { title: '任务配置', description: '维护自动追更：上传任务 + STRM 任务串联' }
    },
    {
      path: '/automation/execution',
      name: 'AutomationExecution',
      component: () => import('@/views/automation/Execution.vue'),
      meta: { title: '开始执行', description: '启动/停止自动追更并查看运行态与待校验文件' }
    },
    {
      path: '/automation/realtime',
      name: 'AutomationRealtime',
      component: () => import('@/views/automation/RealtimeLog.vue'),
      meta: { title: '运行详情', description: '实时查看自动追更每轮链路的执行日志' }
    },
    {
      path: '/automation/history',
      name: 'AutomationHistory',
      component: () => import('@/views/automation/TaskHistory.vue'),
      meta: { title: '运行记录', description: '按轮次查看自动追更运行结果与失败重试' }
    },
    {
      // 桌面托盘外壳经 window.__upVideoStrmNavigate('/settings') 跳转，此路径必须保持不变。
      path: '/settings',
      name: 'Settings',
      component: () => import('@/views/Settings/index.vue'),
      meta: { title: '设置', description: '桌面外壳、数据目录与版本信息' }
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/'
    }
  ],
  scrollBehavior() {
    return { top: 0 }
  }
})

router.afterEach(to => {
  const title = (to.meta.title as string | undefined) ?? 'up-video-strm'
  document.title = `${title} · up-video-strm`
})

export default router
