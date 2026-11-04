import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'OpenList',
      component: () => import('@/views/OpenList/index.vue'),
      meta: { title: '任务调度' }
    },
    {
      path: '/settings',
      name: 'Settings',
      component: () => import('@/views/Settings/index.vue'),
      meta: { title: '设置' }
    }
  ]
})

export default router
