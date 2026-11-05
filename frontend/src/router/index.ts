import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/schedule/execution'
    },
    {
      path: '/schedule',
      redirect: '/schedule/execution'
    },
    {
      path: '/schedule/execution',
      name: 'ScheduleExecution',
      component: () => import('@/views/schedule/Execution.vue'),
      meta: { title: '执行管理', description: '选择任务与执行模式，批量启动 STRM 生成' }
    },
    {
      path: '/schedule/realtime',
      name: 'ScheduleRealtime',
      component: () => import('@/views/schedule/RealtimeLog.vue'),
      meta: { title: '实时日志', description: '跟踪执行进度与实时输出' }
    },
    {
      // 旧路径兼容：全局配置已升级为与任务调度平级的模块
      path: '/schedule/config',
      redirect: '/config'
    },
    {
      path: '/config',
      name: 'GlobalConfig',
      component: () => import('@/views/config/GlobalConfig.vue'),
      meta: { title: '全局配置', description: '服务器连接与视频/字幕格式' }
    },
    {
      path: '/schedule/tasks',
      name: 'ScheduleTasks',
      component: () => import('@/views/schedule/TaskManage.vue'),
      meta: { title: '任务配置', description: '维护 STRM 生成任务与处理路径' }
    },
    {
      path: '/schedule/history',
      name: 'ScheduleHistory',
      component: () => import('@/views/schedule/TaskHistory.vue'),
      meta: { title: '任务历史', description: '查看任务历次执行记录与日志' }
    },
    {
      path: '/upload',
      redirect: '/upload/tasks'
    },
    {
      path: '/upload/tasks',
      name: 'UploadTasks',
      component: () => import('@/views/upload/TaskConfig.vue'),
      meta: { title: '任务配置', description: '维护上传任务：本地目录、云端目录与集数映射' }
    },
    {
      path: '/upload/rename',
      name: 'UploadRenameRules',
      component: () => import('@/views/upload/RenameRules.vue'),
      meta: { title: '重命名规则', description: '维护上传文件命名模板（SxxExx.ext）' }
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
      redirect: '/schedule/execution'
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
