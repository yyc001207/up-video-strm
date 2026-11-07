import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vitest/config'

/**
 * 前端单测配置：
 * - 只测 `src/utils` 与 `src/composables` 这类纯逻辑，用 node 环境，不挂载组件、不依赖 DOM；
 * - 组件与页面的回归仍以 `vue-tsc` + `npm run build` + 手工回归清单为准。
 */
export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  test: {
    environment: 'node',
    include: ['src/__tests__/**/*.test.ts']
  }
})
