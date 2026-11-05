# 版本记录（CHANGELOG）

本文件专门记录 **up-video-strm** 的版本演进：每个交付版本的级别、日期、变更要点与提交号，以及版本级别为何这样判定。开发规范与交付流程见 [AGENTS.md](AGENTS.md)。

## 版本规则

版本号遵循 [SemVer](https://semver.org/lang/zh-CN/) `MAJOR.MINOR.PATCH`。唯一版本源是 `backend/app/version.py` 的 `__version__`，由 `packaging/bump_version.py` 同步到 `frontend/package.json`、`frontend/package-lock.json`、`packaging/version_info.txt`（四处必须一致，打包脚本会校验）。

| 位 | 何时递增 | 本项目实例 |
|----|----------|------------|
| `MAJOR` | 不兼容变更：接口移除/改名、配置或数据库结构破坏性调整、部署方式变更 | 3.0.0 单服务器化；4.0.0 移除接口字段与配置项 |
| `MINOR` | 新增功能：新页面、新接口、新交互、新配置项 | 2.1.0 前端 UI 重构；3.1.0 连通性测试；4.1.0 测试版打包 |
| `PATCH` | 缺陷修复、样式/文案微调、性能优化、依赖安全更新 | 2.0.1 重命名与 Docker 清理 |

- 一次交付只递增一次；多个改动合并按最高级别递增。
- 每次递增必须在本文件「未发布」下方新增对应条目，记录版本号、日期、级别与 commit。
- 纯文档 / 规范整理不递增版本，也不单独发版。
- 仓库内可追溯的起点为 **2.0.0**（首个 Git 提交），更早的产品历史不在本仓库。

## 未发布（Unreleased）

- 暂无。

## [4.13.1] - 2026-11-06

**级别：PATCH（缺陷修复与轮询收敛）** · 代码见本次提交

- 修复自动化任务启动接口 500：`registry.set_runtime` 与 `execution_engine.start_task` 重复传 `task_id` 导致 `TypeError`，异常发生在后台任务登记之后，出现「接口报错但任务已启动」；同时全局异常处理器补充 `logger.exception` 堆栈记录。
- 自动化实时日志 / 历史日志新增 A/B 执行日志镜像（`[A#id]` / `[B#id]` 前缀），可在自动化页面直接看到本轮上传与 STRM 的详细执行行。
- 收敛轮询：自动化执行管理仅在有运行中任务且页面可见时每 5s 轮询 `GET /active`；运行状态胶囊改为 30s 且页面隐藏时跳过；任务配置仍只在存在运行中任务时 5s 刷新。
- 任务调度 / 上传管理的执行管理与任务历史表格新增「触发方式」列（手动 / 自动化任务名），与后端 `trigger_source`/`trigger_name` 字段对应。

## [4.13.0] - 2026-11-06

**级别：MINOR（新增「自动化任务」独立模块与相关接口/页面）** · 代码见本次提交

- 新增侧栏第四个平级模块**「自动化任务」**：把上传任务（B）与 STRM 任务（A）串联为轮询链路——本地目录指纹判断 → 等待 A/B 空闲 → 上传到 123 云盘 → 校验 OpenList 可见性 → 触发 STRM 生成；失败保留待校验文件，下一轮优先补偿。
- 任务配置：绑定唯一的上传/STRM 任务（被占用选项置灰并显示绑定者）、校验目录自动推导与「检测」（一致性 / 可达性 / 文件样例）、上传并发/失败重试/生成模式/可见性轮询与等待上限/空闲等待/阶段超时/轮次间隔；列表支持搜索、批量删除与运行中 5s 自动刷新。
- 执行管理：批量启动、停止、重置指纹、清空待校验、本轮参数覆盖；展示运行阶段、下一轮时间、待校验文件数、轮次与连续失败次数。
- 实时日志：WebSocket `/api/automation/ws/{task_id}`，回放最近 200 帧，log/progress/status/alert 帧；异常终止推送网页常驻通知与托盘通知，主动停止不通知。
- 任务历史：按任务/状态筛选与服务端分页，展示轮次、阶段、新增/待校验/已校验/跳过、缺失文件与 A/B 执行摘要；详情抽屉含错误码/错误信息/缺失文件清单、日志回放与「重试失败」（写回待校验，不自动启动）。
- 后端新增 `automation_task` / `automation_run` 模型与索引；链式执行引擎（2s 轮询、阶段超时取消 + 30s 宽限、退避与连续 3 次失败终止、进程重启不自动恢复）；每日保留清理（运行记录 90 天/每任务 1000 条、日志 90 天/每任务 200 个）。
- 其他：自动化任务运行数计入顶栏运行状态胶囊与侧栏徽标；`/api/desktop/open-log-dir` 支持打开 `automation_logs`；`docs/rules/backend.md`、`docs/rules/frontend.md`、用户手册与 README 同步更新。

## [4.12.0] - 2026-11-06

**级别：MINOR（新增配置项与执行记录字段，为自动化任务模块做准备）** · 代码见本次提交

- 任务调度「默认运行参数」新增 **OpenList 远程目录前缀**（`open_list_config.openlist_remote_prefix`），供后续自动化任务按前缀定位云端目录；页面卡片与编辑抽屉同步展示、可编辑。
- 任务调度与上传管理的执行记录新增 `error_code` / `error_message`（失败原因分级）与 `trigger_source` / `trigger_ref` / `trigger_name`（触发来源，手动/自动化），历史与实时日志接口一并返回；列表排序改为按 `coalesce(started_time, created_time)` 倒序，未开始执行的记录也能稳定排序。
- 新增跨模块**活跃执行注册表**：同模块同一任务已有活跃执行时，再次启动返回 400「任务正在执行，请等待当前执行结束」；目录执行（`task_id=0`）互不排斥；引擎结束（含异常/取消）统一注销。
- 新增**进程重启清理**：启动时把遗留 `running` 的执行置为 `fail`，写入 `error_code=PROCESS_RESTART`、`error_message=进程重启中断`，不自动恢复执行。
- 新增**引用保护**：A/B 任务或服务器被自动化任务绑定时，删除操作返回 400 并提示先解除绑定（`automation_task` 表尚未创建时直接放行）。
- 新增 `AUTOMATION_LOG_DIR` 配置项（默认 `./automation_logs`），`/api/desktop/open-log-dir` 支持 `kind=automation`；桌面态新增可注入的全局通知器（`desktop.set_notifier` / `desktop.notify`），供自动化任务异常终止时发托盘通知。
- WebSocket 连接管理的执行键放宽为 `int | str`（内部统一按字符串归一化），为自动化任务实时日志预留。
- 清理：移除残留的 `app/business/autoflow/__pycache__`，`.gitignore` 增加 `backend/upload_logs/`、`backend/automation_logs/`。

## [4.11.0] - 2026-11-06

**级别：MINOR（交互行为调整）** · 代码见本次提交

- 托盘图标默认行为改为**收进 Windows 11 任务栏「^」溢出区**：启动时（在注册托盘图标之前）把 `HKCU\Control Panel\NotifyIconSettings\<hash>` 的 `IsPromoted` 写为 `0`，升级后首次启动即生效，不再像旧版本那样每次启动把图标固定到任务栏常驻区；用户手动调整后，重启应用仍恢复默认收起。
- 移除启动时「图标在折叠区」的一次性气泡提示（折叠已是默认行为）。
- 设置页「修复托盘图标」保留，仍可显式将图标固定到常驻区（本次运行有效）。
- 新增 `backend/tests/test_tray_win.py`（6 个用例，用假 `winreg` 校验按可执行文件路径匹配条目与 `IsPromoted` 写入）；后端全量 103 tests OK。
- 文档：`manual/用户手册.md`（§2 系统托盘、§10 设置表、FAQ）、`docs/rules/backend.md`（tray_win 职责）。
- 验证：`python -m compileall app` 通过；后端全量 unittest 通过。

## [4.10.3] - 2026-11-05

**级别：PATCH（文案调整）** · 代码见本次提交

- 移除「上传管理 · 实时日志」打开且没有正在执行的上传时的弹窗提示（「当前没有正在执行的上传，请到执行管理发起执行」）；页面仍通过工具条状态与日志区空态展示当前无任务，不再额外弹窗打扰。
- 验证：`npx vue-tsc -b --force` 0 错误；`npm run build` 成功并同步两份 dist。

## [4.10.2] - 2026-11-05

**级别：PATCH（缺陷修复）** · 代码见本次提交

- 修复「任务调度 · 实时日志」进度卡的「执行状态」在没有选中任何执行时错误显示「运行中」的问题：未选择执行时显示「—」，仅在选中的执行尚未结束（或回放尚未收到结束帧）时显示「运行中」。
- 文档：`manual/用户手册.md` §7 补充该显示规则。
- 验证：`npx vue-tsc -b --force` 0 错误；`npm run build` 成功并同步两份 dist。

## [4.10.1] - 2026-11-05

**级别：PATCH（样式与交互统一）** · 代码见本次提交

- 「任务调度 · 实时日志」按「上传管理 · 实时日志」的设计规范重做页面结构：顶部说明段 → 工具条（执行选择、连接状态、启动中、执行状态点 / 「无运行中任务」，右侧「重连 / 清空 / 打开日志文件夹」）→ 进度卡（视频总数 / 视频成功 / 字幕总数 / 字幕成功 / 执行状态 / 用时 / 当前任务）→ 日志工具条（级别、关键字、行数，右侧「返回执行管理」）→ 日志终端；两页类名与样式一致。
- 两模块实时日志的级别筛选项统一为「全部级别 / 信息 / 警告 / 错误」（此前上传为 INFO / WARN / ERROR），宽度同步为 128px。
- 「上传管理 · 任务历史」列表页按「任务调度 · 任务历史」对齐：补页面功能说明、任务名主行 + 本地目录副行（悬停显示云端目录）、状态列宽 110、文件计数右对齐宽 96、执行时间与耗时列宽一致、右侧固定「详情」按钮；工具栏筛选项宽度统一为 200 / 280 / 140。
- 文档：`manual/用户手册.md`（§7 实时日志结构、§9 上传实时日志与任务历史结构）、`docs/rules/frontend.md`（两模块实时日志共用骨架、上传历史对齐说明）。
- 验证：`npx vue-tsc -b --force` 0 错误；`npm run build` 成功并同步两份 dist。

## [4.10.0] - 2026-11-05

**级别：MINOR（新增交互与列表页规范）** · 代码见本次提交

- 任务调度「执行管理」：「选择任务」卡支持关键字过滤，底部右侧新增「全选 / 取消全选」（仅作用于当前筛选结果中的可选任务，运行中任务不参与），左侧显示「可选 N · 已选 N」。
- 上传管理「执行管理」：按任务调度执行管理整页对齐（同一套 `exec-*` 骨架与栅格常量），三卡头部补标题与用途说明；「选择任务」卡支持名称 / 目录搜索与「全选 / 取消全选」；「已选任务」卡头部与摘要均显示已选数量，保留移除与清空；参数卡底部补参数用途说明。
- 上传管理「任务配置」「重命名规则」：工具栏新增名称搜索与「批量删除」（后端新增 `POST /api/upload/tasks/batch-delete`、`POST /api/upload/rules/batch-delete`，被任务引用的规则拒绝删除并返回规则名）；列表改为客户端分页 20 / 10 / 50。
- 任务调度与上传管理「任务历史」：新增「任务名称 / 时间范围 / 任务状态（成功 / 失败 / 已取消 / 未执行）」三项组合筛选、客户端分页，并补页面功能说明；时间范围按北京时间自然日包含首尾。
- 列表页规范：`frontend/src/styles/global.scss` 新增 `.list-page / .list-card / .list-card__table / .list-card__pager` 骨架，所有列表页统一分页与「滚动条只在卡片内部」；上传实时日志页顶部补说明文案。
- 测试：新增 `backend/tests/test_upload_batch_delete.py`；`test_smoke.py` 中前端标题断言同步为「up-video-strm 控制台」。
- 文档：`manual/用户手册.md`（全选、筛选、分页、批量删除、滚动约束）、`docs/rules/frontend.md`（列表页骨架与筛选约定、两执行页对齐）。
- 验证：`npx vue-tsc -b --force` 0 错误；`npm run build` 成功并同步两份 dist；后端全量 unittest 通过。

## [4.9.2] - 2026-11-05

**级别：PATCH（交互细节修复）** · 代码见本次提交

- 上传管理「执行管理」三张卡片高度随内容变化的问题：勾选/取消任务时「已选任务」卡片在有数据与空态之间切换导致整行高度跳变。现与任务调度「执行管理」保持一致——卡片区整行高度固定为 `clamp(380px, 52vh, 560px)`、三卡等高拉伸，内容超出时在卡片内部滚动（任务列表 / 已选列表），空态在剩余空间内垂直居中；「正在执行」表加 `max-height: 320`，行数变化不再撑高页面。窄屏（≤1280px）堆叠时恢复内容自适应高度。
- 验证：`npx vue-tsc -b --force` 0 错误；`npm run build` 成功并同步 `frontend/dist` / `backend/frontend/dist`。

## [4.9.1] - 2026-11-05

**级别：PATCH（回归缺陷修复 + 一致性收敛）** · 代码见本次提交

按 [docs/design/ui-review-round2.md](docs/design/ui-review-round2.md) 第 7 节修复回归问题：

- 执行管理（调度 / 上传）竖向压缩缺陷：两页根节点是 flex 列容器，卡片区默认 `flex-shrink: 1`，窗口变矮时被压扁导致「正在执行」卡片重叠、上传页 running 卡被压到 2px；现为卡片区（调度 `.exec-workspace`、上传 `.upload-execution__cards` 与 `.running-card`）显式 `flex: none`，内容过高时由外层滚动，全高度下卡片完整可见。
- 工具栏布局原语收敛到 `frontend/src/styles/global.scss` 的 `.toolbar`（含 `__left/__right`，右侧 `margin-left: auto` 恒贴右），五个列表页删除各自重复定义，仅保留页面专有规则（`.toolbar__keyword`、`.toolbar__hint`）；同时重建并同步 `frontend/dist` 与 `backend/frontend/dist`，排除「看到的仍是旧构建产物」。
- 侧栏导航选中态：移除 `font-weight: 600`（Windows 微软雅黑映射为 Bold 会加宽文字、观感像换字体），改为「主色文字 + 12% 主色底 + 左侧 2px 主色指示条」。
- 顶栏标题改为「模块 · 页面」（如「任务调度 · 任务配置」）；单页模块同名只显示一次（全局配置），无模块归属显示页面名（设置）；新增动态 `document.title`（`<页面标题> - up-video-strm`，默认「up-video-strm 控制台」）。
- 验证：`npx vue-tsc -b --force` 0 错误；`npm run build` 成功并同步两份 dist。

## [4.9.0] - 2026-11-05

**级别：MINOR（新增交互与 UI 治理）** · 代码见本次提交

按 [docs/design/ui-review-round2.md](docs/design/ui-review-round2.md) 完成第二轮 UI 评审修复：

- 全局错误治理：axios 响应拦截器错误提示按文案 3 秒去重，避免并发/轮询失败时 toast 轰炸；请求支持 `{ silent: true }`（轮询全部静默，手动操作才提示）；后端不可达时顶栏下方展示可关闭的 `el-alert`「无法连接后端服务，正在自动重试…」，恢复后自动消失。
- 运行状态聚合：新增 `frontend/src/stores/running.ts`，每 10s 静默聚合「任务调度」与「上传管理」的 `running` 执行数；顶栏状态胶囊改为三态（连接失败 / 运行中 N / 空闲）并按来源分流到对应实时日志页；两个模块「实时日志」导航项均带运行数徽标。
- 执行管理（调度 / 上传）：三卡片栅格统一为 `1.6fr / 0.9fr(300px起) / 1fr(280px起)`，堆叠断点统一 1280px；模式文案改「增量 / 全量 / 仅 strm」。
- 首访空态分层：任务配置在「默认运行参数」未配置时参数卡给 CTA、表格空态只给说明，已配置后空态 CTA 改「创建第一个任务」；上传任务配置空态文案同步。
- 重命名规则页：模板变量提示移入「命名模板」表单项并去掉负边距，`.toolbar__hint` 改次要色。
- 刷新控件统一：列表页刷新统一放工具栏右侧组首位（任务配置 / 任务历史 / 上传任务配置、上传重命名规则），任务配置补刷新；目录树与云端目录面板刷新按钮统一 `small`；设置页刷新 `link` 去掉 primary。
- 实时日志：顶部进度区域间距统一，耗时数值固定最小宽度避免基线松散；全局配置页空态图 60px、两卡栅格顶部对齐消除右侧留白；浏览器标签页标题改为「up-video-strm 控制台」。
- 文档：`manual/用户手册.md`（顶栏状态胶囊/离线提示、导航徽标说明）与 `docs/rules/frontend.md`（壳层、运行状态 store、错误去重与 silent、标题）同步。
- 验证：`npx vue-tsc -b --force` 0 错误；`npm run build` 成功（后端无改动）。

## [4.8.0] - 2026-11-05

**级别：MINOR（新增交互与配置项）** · 代码见本次提交

- 修正默认集数解析把噪音数字当集数的问题：此前文件名 `[Dynamis One] Seitokai ni mo Ana wa Aru! - 13 (Baha 1920x1080 AVC AAC MP4) [5AAEB1E9].mp4` 会因哈希 `5AAEB1E9` 中的 `E9` 被解析为第 9 集；现在 `E`/`EP` 需落在非字母数字边界后，方括号内独立数字视为集号，兜底只取最后一段独立数字，分辨率 `1080p` 与哈希不再参与解析。
- 重命名规则新增可选「集数提取正则」（`episode_pattern`）：留空使用默认解析；填写后只按该正则提取第 1 个分组作为集号，不再回退默认规则。规则保存时校验（可编译、至少 1 个分组），非法返回 400；任务创建执行时把正则快照进执行记录，重跑沿用。
- 规则页新增正则输入与说明、列表新增「集数正则」列，预览支持自定义正则；旧库启动时自动为 `upload_rename_rule` / `upload_execution` 补列。
- 单测：新增默认正则回归（哈希/分辨率不误判）、自定义正则校验与规则预览用例，后端全量 **94 tests OK**。
- 文档：`manual/用户手册.md`、`docs/rules/backend.md`、`docs/rules/frontend.md`、`docs/design/upload-module-plan.md` 同步。

## [4.7.0] - 2026-11-05

**级别：MINOR（新增交互与接口）** · 代码见本次提交

- 日志收尾信息补全：上传执行在重命名阶段输出 `重命名：原文件 -> 新文件`（如 `重命名：Show.S01E13.mp4 -> S02E01.mp4`），上传前输出 `开始上传：共 N 个文件（并发 M）`，上传后输出 `上传完成：成功/跳过/失败/剩余待处理`，结束时输出 `任务结束：状态=成功|失败|部分完成|已取消 … 用时 N 秒`。
- 实时日志状态一致性：无执行记录时上传实时日志显示「无运行中任务」而非「运行中」；WebSocket 建连后若执行已结束，直接显示最终状态并断开连接（刷新回放不再卡在「运行中」）。
- 全系统日志操作统一为「打开日志文件夹」：新增 `POST /api/desktop/open-log-dir`（`kind=openlist|upload`，在资源管理器打开对应日志目录，非 Windows/网页版返回 400），移除任务调度与上传管理的 `log-download` 接口与前端下载方法；实时日志工具条与任务历史行操作按钮同步替换。
- 文档：`manual/用户手册.md`、`docs/rules/frontend.md`、`docs/rules/backend.md`、`README.md`、`docs/design/upload-module-plan.md`、`docs/design/ui-redesign-plan.md` 同步日志目录、上传业务层与打开日志文件夹说明。
- 单测：新增 `backend/tests/test_desktop_open_log_dir.py`（4 用例）与流水线日志断言，后端全量 **86 tests OK**。

## [4.6.1] - 2026-11-05

**级别：PATCH（缺陷修复）** · 代码见本次提交

- 修复上传管理「上传失败：123 云盘返回非 JSON 数据（HTTP 404）」：上传接口路径由错误的 `/api/v1/upload/*` 改为官方 `/upload/v1/file/*`（`create` / `get_upload_url` / `list_upload_parts` / `upload_complete` / `upload_async_result`），请求头 `Platform` 改为官方要求的 `open_platform`，`create` 的父目录字段改为 `parentFileID`。
- 已在 123 云盘 `/test` 目录用真实凭据完成上传冒烟（探针文件上传成功后删除），并回填 `docs/design/upload-module-plan.md` §5.2 的官方端点与实测结论。
- 单测补充 mock 传输层对官方路径与 `Platform` 头的断言；后端全量 80 tests OK。

## [4.6.0] - 2026-11-05

**级别：MINOR（新增接口与交互）** · 代码见本次提交

- 「全局配置 → 123 云盘」卡片在「编辑」右侧新增「删除」按钮：二次确认后调用新增的 `DELETE /api/upload/config` 清空 Client ID、Client Secret 与缓存的 Token（未配置时按钮不显示），删除后上传管理需重新配置凭据。
- 统一全局配置页三张卡片的操作按钮为**镂空（`plain`）风格**：服务器卡「刷新缓存 / 编辑」、视频与字幕格式卡「编辑」、123 云盘卡「测试连接 / 编辑 / 删除」（删除为 `danger plain`）；空态 CTA（新增服务器 / 立即配置）同步为 `primary plain`。
- 文档：`manual/用户手册.md` 与 `docs/rules/frontend.md` 同步删除入口、按钮风格与接口说明。

## [4.5.1] - 2026-11-05

**级别：PATCH（交互缺陷修复）** · 代码见本次提交

- 修复「全局配置 → 123 云盘」弹框中点击「测试连接」成功后**已填写的 Client ID / Client Secret 被清空**的问题：测试本身不保存配置，原先成功后重新拉取配置会覆盖弹框表单；现改为只提示「连接成功」，表单内容保持不变，需点「保存」才生效。
- 文档：`manual/用户手册.md` 补充「测试不保存配置、表单保持不变」说明。

## [4.5.0] - 2026-11-05

**级别：MINOR（新增发布能力）** · 代码见本次提交

- 新增 GitHub Actions 发布流水线 `.github/workflows/release.yml`：**仅在推送 `v*` 标签时触发**，自动构建 Windows 正式版安装包并发布到 GitHub Release（附加 `up-video-strm-<版本>-win-x64-setup.exe`，自动生成发布说明）。
- 流水线先校验 `v<版本>` 与 `backend/app/version.py` 一致，不一致直接失败；分支 push / PR 不触发构建。
- 文档：README 与 `docs/rules/project.md` 补充发布流程说明（先 bump 版本并提交，再打/推匹配标签）。

## [4.4.2] - 2026-11-05

**级别：PATCH（缺陷修复）** · 代码见本次提交

- 修复「云端目录」选择弹框点击目录后 `parent_id` 恒为 0、一直显示根目录的问题：123 云盘官方文件对象里的 ID 字段是 **`fileID`**（大写 D），此前按 `fileId` 解析得到 0。新增 `get_file_id()` 兼容 `fileID` / `fileId` / `file_id`，目录列表、目录路径解析、重复检查与上传结果解析统一使用该函数。
- 修复全局配置页 123 云盘卡片撑满整页高度并出现滚动条的问题：移除 `.global-config__card { height: 100% }`，卡片高度随内容自适应。
- 测试：新增 `get_file_id` 字段变体单测，并让目录列表 mock 使用真实字段 `fileID`（后端全量 79 个用例通过）。

## [4.4.1] - 2026-11-05

**级别：PATCH（缺陷修复）** · 代码见本次提交

- 修复上传任务「云端目录」选择面板一次性递归加载导致接口请求爆炸的问题：`RemoteDirPanel.vue` 由懒加载树改为**逐级导航**——打开时只请求根目录一次，点击目录行进入下级时仅请求一次，不做任何预加载；提供面包屑与「返回上级」，底部醒目展示当前目录并确认回填。
- 文档：`docs/rules/frontend.md`、`manual/用户手册.md` 同步为逐级导航描述。

## [4.4.0] - 2026-11-05

**级别：MINOR（新增交互与全局时间约定）** · 代码见本次提交

### 统一北京时间（全局约定）

- 后端新增 `backend/app/core/beijing.py`（`BEIJING_TZ` / `beijing_now()`）：模型创建/更新时间默认值、业务写入与执行日志时间全部改为北京时间（SQLite 的 `func.now()` 为 UTC，不再用于默认值）；`pan123_client` 的 Token 过期时间、OpenList 文件修改时间也统一转北京时间。
- 前端 `frontend/src/utils/date.ts` 重写：所有时间按 `Asia/Shanghai` 解释（无时区墙钟字符串直接按北京时间，自带 Z / 偏移则先换算），统一 `formatDateTime`（`YYYY-MM-DD HH:mm:ss`）、`formatDate`（`YYYY-MM-DD`）与 `beijingMillis`（耗时计算）；各页面时间展示全部走该工具。

### 界面优化

- 全局配置「123 云盘」改为「摘要卡 + 编辑弹框」：卡片展示 Client ID、脱敏 Client Secret、Token 状态与过期时间，卡头提供测试连接 / 编辑；未配置时为空态「立即配置」；弹框内编辑 Client ID / Secret。
- 上传任务配置：本地目录新增「浏览」系统目录选择（桌面版）；云端目录不再默认填入 `/test`；云端目录选择改为懒加载目录树，支持逐级下钻、单击选中，底部醒目展示已选路径。
- 上传执行管理：选择任务 / 执行参数 / 已选任务三张卡片高度随内容自适应（列表超高时卡片内部滚动）。
- 任务调度实时日志：级别过滤、关键字搜索、清屏、下载日志等工具条从底部移到日志终端上方。

### 文档

- `manual/用户手册.md`（时间约定、123 云盘、上传任务目录选择、实时日志工具条位置、执行卡片高度）、`docs/rules/frontend.md` 同步更新。

## [4.3.0] - 2026-11-05

**级别：MINOR（新增模块）** · 代码 `0e2b21a`

### 新增：上传管理模块（与全局配置、任务调度平级）

- 侧栏新增「上传管理」（`/upload/*`）：任务配置、重命名规则、执行管理、实时日志、任务历史五个页面；面向 123 云盘，执行流程为扫描 → 过滤 → 重命名 → 预上传清单 → 重复检查 → 上传，同名冲突支持跳过（默认）/ 覆盖 / 追加后缀。

### 上传管理（阶段一：凭据与 API 客户端）

- 新增 `upload_platform_config` 表与 `/api/upload/config` 接口：123 云盘 Client ID / Client Secret 配置，密钥使用 Windows DPAPI 加密存储、接口只回显脱敏值；Token 缓存到期前 5 分钟自动刷新。
- 新增 `pan123_client.py`：123 云盘开放平台客户端（申请 Token、分页列目录、按路径解析目录且不自动创建、创建/分片/完成上传与异步结果、删除文件）。
- 全局配置页新增「123 云盘」卡：凭据脱敏回显、Token 状态、测试连接与保存。
- 文档：`manual/用户手册.md` §3、`docs/rules/frontend.md` 同步。

### 上传管理（阶段二：任务与重命名规则）

- 数据表 `upload_rename_rule`（命名模板）、`upload_task`（本地目录 / 云端目录 / 输出季数 / 源起始集号 / 规则引用），首次启动自动 seed 默认规则 `S{season:02}E{episode:02}.{ext}`。
- 重命名与集数映射：从文件名解析绝对集号（`S01E13` / `第13集` / `EP13` / `[13]` 等），输出名 `S{季:02}E{季内集:02}.{ext}`，季内集号 = 绝对集号 − 源起始集号 + 1；规则预校验必须含 episode 与 ext 且渲染为 `SxxExx.ext`。
- `/api/upload/rules`（CRUD + 预览）、`/api/upload/tasks`（CRUD）、`/api/upload/remote/dirs`（列云端目录）接口。
- 前端新增「上传管理」平级模块：任务配置页（表格 + 抽屉编辑 + 云端目录浏览）与重命名规则页（规则 CRUD + 预览）。
- 文档：`manual/用户手册.md` 新增 §9 上传管理（后续章节顺延）、`docs/rules/frontend.md` 同步。

### 上传管理（阶段三：执行流水线、执行管理与实时日志）

- 数据表 `upload_execution`（创建时固化任务参数：本地/云端目录、季数与起始集号、模板、冲突策略、并发、重试、试运行）与 `upload_file_record`（文件级明细：状态/阶段/原因/远端 fileId/被替换 fileID）。
- 六阶段执行流水线（扫描 → 视频过滤 → 重命名 → 预上传清单 → 重复检查 → 上传）：同名冲突支持跳过（默认）/ 覆盖（`duplicate=2` 先传新后删旧）/ 追加后缀（`_1`、`_2`）；按执行参数限制单执行并发与单文件重试；试运行只生成清单不查重上传；取消通过 `TaskStatusManager` 半实时生效。
- 日志只写文件（`data/upload_logs/execution_{id}.log`）并经 WS 推送 log/progress/status 帧，心跳/回放复用日志文件尾部。
- `/api/upload/executions*`（创建/批量创建/启动/取消/列表/详情/文件明细/日志/下载）与 `/api/upload/ws/{execution_id}` 接口。
- 前端新增「上传管理 → 运行」分组：执行管理页（三卡片：选择任务 / 执行参数 / 已选任务 + 正在执行列表）与实时日志页（连接状态、六阶段进度摘要、日志终端、级别/关键字过滤、下载日志、批量排队逐个启动）。
- 测试：`backend/tests/test_upload_pipeline.py` 覆盖试运行、跳过/覆盖/后缀三策略、单文件失败与启动/取消；后端全量 unittest 通过。
- 文档：`manual/用户手册.md` §9 增补执行管理与实时日志、`docs/rules/frontend.md` 路由与页面说明同步。

### 上传管理（阶段四：历史与收尾）

- 历史接口：`GET /api/upload/history`（按任务汇总：任务信息 + 最近执行 + 累计次数）、`GET /api/upload/history/task/{task_id}`（分页执行记录）、`POST /api/upload/executions/{id}/retry`（按原执行固化参数新建执行，整任务重跑）。
- 前端新增「上传管理 → 记录 → 任务历史」页：按任务汇总 → 任务执行记录 → 文件粒度明细抽屉（本地文件 / 远端名称 / 大小 / 状态 / 原因 / fileId）+ 日志回放 / 下载 + 重跑（确认后跳转实时日志自动启动）。
- 测试：`backend/tests/test_upload_history.py` 覆盖空历史、最近执行与计数、按任务分页、未知任务、重跑参数固化（不继承试运行）、任务删除后不可重跑；后端全量 78 个 unittest 通过。
- 文档：`manual/用户手册.md` §9 增补任务历史、`docs/rules/frontend.md`、`README.md` 同步。
- 版本：`bump_version.py minor` 4.2.0 → 4.3.0（四处一致）；前端 `vue-tsc` 与 `npm run build` 通过。

## [4.2.0] - 2026-11-05

**级别：MINOR（新增模块 + 交互调整）** · 代码 `1abe694`

### 调整

- 全局配置升级为与「任务调度」**平级的独立模块**（路由 `/config`，侧栏排在任务调度之上；旧 `/schedule/config` 保留重定向）：模块内只保留服务器配置与视频/字幕格式，格式编辑改为右侧抽屉。
- 原全局配置的其他运行参数（并发度、限流间隔/暂停时间、SSL 校验、输出目录前缀/根目录）迁至**任务配置**页顶部「默认运行参数」卡与编辑抽屉，语义仍为全局默认。
- 壳层导航支持「单页模块不显示分组标题」，模块顺序改为数据驱动（全局配置 → 任务调度）。

## [4.1.2] - 2026-11-05

**级别：PATCH（缺陷修复）** · 代码 `88d8ebc`

### 修复

- 中文 Windows 下执行 `pip install -r packaging/requirements-build.txt` 报 `UnicodeDecodeError: 'gbk' codec can't decode byte 0x96`：该文件含中文注释但未声明编码，pip 按系统默认 GBK 解码失败。按 PEP 263 在首行加入 `# -*- coding: utf-8 -*-`，pip 可正确解析并安装 PyInstaller 等打包依赖（已用 `pip install --dry-run` 验证解析通过）。

## [4.1.1] - 2026-11-05

**级别：PATCH（缺陷修复 + 布局调整）** · 代码 `2274002`、`8f218eb`

### 修复

- 升级后旧数据库点击「执行任务」返回 500：旧库遗留的 `open_list_execution.strip_series` 为 `NOT NULL` 且无默认值，新代码不再写该列，`INSERT` 触发 `IntegrityError`。启动时由 `obsolete_column_statements()` 生成 `ALTER TABLE ... DROP COLUMN`（SQLite ≥ 3.35），清理 `open_list_execution.strip_series`/`server_name`、`open_list_config.log_to_db`、`open_list_server.name`，升级用户无需重建数据库。

### 变更

- 执行管理改为「选择任务 / 执行参数 / 已选任务」三卡片一行展示；「已选任务」卡片承载逐条移除、清空选择、摘要与「执行任务」按钮，移除底部常驻操作条；窄屏（< 1100px）回退为纵向堆叠。「正在执行」表格与业务流程不变。

### 文档

- `manual/用户手册.md` §6 执行管理、`docs/rules/frontend.md`、`docs/design/ui-redesign-plan.md` §3.1 与验收清单、`docs/rules/backend.md` 数据层同步。

## [4.1.0] - 2026-11-05

**级别：MINOR（新增能力）** · 代码 `b22fbc2`

- 新增测试版打包：`packaging/build-test.ps1`（内部以 `-Profile test` 复用 `build.ps1`）产出 `up-video-strm-test.exe` 与 `dist/up-video-strm-test-<版本>-win-x64-setup.exe`；应用名、安装目录、数据目录（`%LOCALAPPDATA%\up-video-strm-test`）、快捷方式、自启动项、单实例互斥体均与正式版隔离，可同时安装运行。
- `build.ps1` 新增 `-Profile prod|test`（默认 `prod`，行为不变）；`installer.iss` 通过 `MyTestBuild` 切换 AppId/安装目录/产物名；`paths.py` 新增 `APP_DIR_NAME` 与 `build_profile()`，测试版应用携带 `build_profile.json` 构建标记，`run.py`/`desktop.py`/`desktop_prefs.py`/`main.py` 的应用名统一取自 `APP_DIR_NAME`。
- 测试：新增 `backend/tests/test_build_profile.py`（6 例：源码/冻结、prod/test 标记、数据目录隔离、应用名），`test_smoke.py` 同步打包命名断言。
- 文档：README「构建与打包」新增测试版说明与 `-Profile` 参数；`docs/rules/project.md` 同步打包发布与冻结运行差异。

## [4.0.0] - 2026-11-05

**级别：MAJOR（不兼容）** · 代码 `1d2fe82` · 文档 `5cc2e17`

**为什么是 MAJOR**：移除了对外接口字段（服务器 `name`、任务/执行响应中的 `server_name`、全局配置的 `log_to_db`），属于「接口移除 + 配置结构破坏性调整」，按规则必须递增 MAJOR。

### 不兼容变更

- 删除服务器「名称」字段：`OpenListServerCreate` / `OpenListServerUpdate` / `OpenListServerResponse`、`OpenListServer` 模型、前端类型与表单/卡片全部移除；删除确认改用服务器地址标识。
- 删除全局配置 `log_to_db`：`OpenListConfigUpdate` / `OpenListConfigResponse`、`get_config` / `get_config_for_run`、前端类型与摘要卡同步移除。
- 任务 / 执行响应不再返回 `server_name`。

### 新增

- 服务器配置卡片标题右侧显示连通状态：在线（绿）/ 离线（红）/ 未配置（灰）/ 检测中（黄）；进入页面探测一次，之后每 60s 轮询（后台失败静默）。
- 「编辑配置」由弹窗改为右侧抽屉（520px，底部固定「取消 / 保存」）。
- axios 请求新增 `silent` 选项：后台轮询等场景失败不弹全局错误提示。

### 变更

- 执行日志只写文件，移除 `LogPump` 的批量落库分支（WebSocket 推送 + 追加文件）。
- 数据库旧列 `config.log_to_db`、`server.name`、`execution.server_name` 物理保留但不再读写，升级不丢历史数据。

### 文档

- 用户手册：全局配置参数表移除日志入库项、编辑配置改为抽屉；服务器配置去掉「名称」字段与卡片名称展示，改为标题右侧状态标签说明。
- `docs/rules/frontend.md`：同步 `GlobalConfig.vue` 页面职责。

## [3.1.0] - 2026-11-05

**级别：MINOR（新增功能）** · 代码 `de27dff` · 文档 `f34bc75`

- 新增服务器连通性测试：后端 `POST /openlist/servers/test-connection`（可带 `server_id` 复用已保存 Token），前端服务器弹窗提供「测试连通性」按钮。
- 成功时返回「连接成功」及根目录条目数；失败时返回具体原因（超时、地址不可达、Token 无效等）。

## [3.0.0] - 2026-11-05

**级别：MAJOR（不兼容）** · 代码 `afb63b3` · 文档 `b48bff3`

**为什么是 MAJOR**：接口请求/响应字段变更，并删除配置项（系列层优化），属于破坏性调整。

### 不兼容变更

- 服务器配置单服务器化：创建第二个服务器会被拒绝；任务创建、执行/目录执行批量创建均可省略 `server_id`，自动绑定唯一启用服务器；相关 schema 的 `server_id` 改为可选。
- 移除「系列层优化」：前后端彻底删除 `strip_series` / `stripSeries`（schema、执行引擎、STRM 生成器、前端类型与请求体）；数据库旧列保留但不再读写。
- 执行接口响应不再返回 `strip_series`。

### 变更

- 前端移除所有服务器选择器、筛选条件与多服务器相关文案。

### 文档

- 用户手册与工程规范同步单服务器化与系列层移除说明。

## [2.1.0] - 2026-11-05

**级别：MINOR（新增功能）** · 代码 `9491fbe` · 文档 `3a5ea57`

- 前端按 [docs/design/ui-redesign-plan.md](docs/design/ui-redesign-plan.md) 重建：
  - 侧栏壳层（220/64 可折叠、模块 → 分组 → 页面数据驱动）+ 顶栏页面标题/描述/运行状态胶囊；
  - 路由拆分为 `/schedule/{config,tasks,execution,history,realtime}` 与 `/settings`；
  - 五个页面重写：执行管理（双栏）、全局配置（8/4 布局）、任务管理（工具栏分组）、任务历史（状态点 + 页面级详情）、实时日志（三段式）；
  - 新增设计令牌与 Element Plus 变量映射、`zh-cn` 语言包、焦点环与减动效支持，新增 `StatusDot.vue` / `LogViewer.vue`。

## [2.0.1] - 2026-11-04

**级别：PATCH（修正 / 清理）** · 代码 `34b5af7` · 文档 `6ad41a2`

- 项目整体重命名 `video-strm` → `up-video-strm`：进程名、窗口标题、数据目录（`%LOCALAPPDATA%\up-video-strm`）、数据库名 `up_video_strm.db`、打包产物与前端包名；旧数据目录 / 旧库原地沿用做兼容。
- 移除 Docker 与相关发布物：Dockerfile、docker-compose、镜像相关文档与 CI 引用；文档去掉部署 / 镜像章节。
- 版本号 2.0.0 → 2.0.1。

## [2.0.0] - 2026-11-04

**级别：基线（Git 首个提交 `3b09166`）**

- 仓库纳入 Git 时的既有状态：FastAPI + SQLite 后端、Vue 3 + Element Plus 前端、pywebview 桌面外壳、PyInstaller + Inno Setup 打包，已具备 STRM 生成与任务调度核心功能。更早的产品版本历史不在本仓库，故作为基线记录。
