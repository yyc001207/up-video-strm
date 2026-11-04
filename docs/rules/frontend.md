# docs/rules/frontend.md — 前端工程说明

> 核心规范见 [AGENTS.md](../../AGENTS.md)；项目总览见 [project.md](project.md)；后端实现见 [backend.md](backend.md)。

## 技术栈

- Vue 3.5（`<script setup>` + TypeScript）+ Vite + Element Plus（含 `@element-plus/icons-vue`）+ Pinia + vue-router + axios + dayjs + Sass
- Vite 开发服务器 `/api` 代理到后端并透传 WebSocket；包名 `up-video-strm-web`，npm / pnpm 均可
- 依赖清单：[frontend/package.json](../../frontend/package.json)

## 目录结构

```text
frontend/
├── src/
│   ├── main.ts / App.vue / router/index.ts  # 入口、根组件、路由（/ 主页面、/settings 设置页）
│   ├── api/                # axios 实例 + openlist / desktop 接口封装
│   ├── stores/             # Pinia（openlist 业务 / theme 主题）
│   ├── views/              # OpenList 五页签（components/ 子组件、DirTreePanel）+ Settings 设置页
│   ├── components/         # 通用组件（ThemeToggle.vue）
│   ├── types/ / utils/     # 类型（openlist / desktop）、工具（date / ws）
│   └── styles/             # global / dark / variables / element-reset（scss）
├── index.html              # 标题「up-video-strm 任务调度」+ 首屏主题预加载
├── vite.config.ts          # 别名 @ → src；dev server :5173；/api 代理 → 127.0.0.1:8000（ws 透传）
├── .env.development / .env.production / tsconfig*.json
└── package.json / package-lock.json / pnpm-lock.yaml
```

## 页面与组件

主页面 [views/OpenList/index.vue](../../frontend/src/views/OpenList/index.vue) 为五个页签（懒加载，切页时按需刷新）：

| 页签 | 组件 | 说明 |
|------|------|------|
| 全局配置 | `GlobalConfig.vue` | 视频/字幕格式、并发度、限流、SSL、日志落库、输出前缀，以及服务器列表 |
| 任务配置 | `TaskManage.vue` | 任务 CRUD、快速添加（目录树/搜索/下钻）、批量删除、按服务器筛选 |
| 执行管理 | `Execution.vue` | 选服务器 + 多选任务批量执行、取消、系列层优化开关 |
| 任务历史 | `TaskHistory.vue` | 每任务最近执行 + 全部记录 + 日志回放/下载 |
| 实时日志 | `RealtimeLog.vue` | WebSocket 实时推送，多任务切换查看 |

辅助组件 `DirTreePanel.vue` 用于目录树勾选；[views/Settings/index.vue](../../frontend/src/views/Settings/index.vue) 为桌面设置页（开机自启、托盘偏好、数据目录、关于）。

## 接口与状态

- axios 实例：[api/index.ts](../../frontend/src/api/index.ts)；业务接口：[api/openlist.ts](../../frontend/src/api/openlist.ts)；桌面接口：[api/desktop.ts](../../frontend/src/api/desktop.ts)。
- 后端 API 基址由 `VITE_API_BASE_URL` 控制（默认 `/api`）。
- Pinia store：[stores/openlist.ts](../../frontend/src/stores/openlist.ts)（业务）、[stores/theme.ts](../../frontend/src/stores/theme.ts)（浅色/深色/跟随系统，localStorage 记忆，键名 `up-video-strm-theme`，首屏无闪烁）。
- WebSocket 工具：[utils/ws.ts](../../frontend/src/utils/ws.ts)，连接 `ws://.../api/openlist/ws/{execution_id}`。
- 桌面外壳导航桥：[main.ts](../../frontend/src/main.ts) 把路由挂到 `window.__upVideoStrmNavigate(path)`，托盘菜单「设置…」通过它直接切页而不整页重载（后端 [desktop.py](../../backend/app/desktop.py) 调用）。

## 常用命令

安装、启动、构建与类型检查命令见 [README.md 快速开始](../../README.md#方式二源码运行)（`npm run build` = `vue-tsc` + `vite build`）。

> 开发服务器与后端端口被占用时须自动切换，并保持 [vite.config.ts](../../frontend/vite.config.ts) 代理目标与后端实际端口一致（见 [AGENTS.md](../../AGENTS.md) 规则 4）。
