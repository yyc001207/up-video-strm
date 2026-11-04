# AGENTS.md — 开发规范与协作约定

本文件定义 **up-video-strm** 项目中所有开发者与 AI 协作方必须遵守的开发规范；规则冲突时，以用户当次明确指令优先。

> 技术栈、目录结构、模块职责、构建运行命令等工程细节见 [docs/rules/](docs/rules/)；用户侧的安装与操作说明见 [manual/用户手册.md](manual/用户手册.md)。

## 1. 每次改动必须创建 Git Commit

- commit 信息说明「改了什么、为什么改」，遵循 `feat:` / `fix:` / `docs:` / `refactor:` 前缀 + 中文描述；一次 commit 只做一件事。
- 仅逐项 `git add` 本次相关文件，禁止 `git add -A` / `git add .`；不提交含密钥的文件（`.env`、凭据）。
- 用户未明确要求时**不执行** `git push`。

## 2. 每次改动必须编写/更新测试，交付前全部通过

- 后端：在 [backend/tests/](backend/tests/) 补充用例并实际运行；前端：至少 `npm run type-check`，涉及构建产物时跑 `npm run build`。
- 不得以「应当通过」代替实际执行结果，交付前必须**全绿**。
- 测试文件（`backend/tests/` 下的临时/新增脚本）无需提交；**纯文档改动**（仅 `*.md`）不需要新增测试。

## 3. 有疑问的需求必须反复确认

- 需求边界、技术选型、方案取舍存在多种可能时先提问澄清，不自行假设后实施。
- 影响面大或不可逆操作（删除、数据结构变更、批量改动）必须先获用户确认。
- 有歧义时默认暂停执行、等待确认，确认可多轮直至无歧义。

## 4. 默认端口被占用时自动切换

- 后端 `8000`、前端 `5173` 被占用时自动探测并切换到可用端口，不直接报错退出。
- 切换后保持 [frontend/vite.config.ts](frontend/vite.config.ts) 的 `/api` 代理目标与后端实际端口一致。
- 端口变更须在启动日志与交付说明中告知用户实际端口。

## 5. 文档与注释必须与实际代码逻辑一致

- 改代码逻辑时同步更新受影响的注释、docstring、[README.md](README.md)、[manual/用户手册.md](manual/用户手册.md) 与 [docs/rules/](docs/rules/)。
- 不保留失效的注释与默认值说明；删除/重命名功能时同步清理相关描述。
- 提交前逐条对照：文档/注释所述行为与代码实际行为无出入。

## 6. 已提交代码视为既定事实，不得擅自回退

- 禁止在用户未要求时执行 `git reset --hard`、`git checkout --`、`git restore`、`git revert`、`git clean -f`、强制推送等回退/破坏性操作。
- 历史代码有问题时向前修复（新增修改）而非回退既有提交；确需回退须先说明原因与影响并获明确许可。

## 7. 版本号必须随交付递增（语义化版本）

- 每次交付可用产物（安装包 / 功能变更）前必须更新版本号，不允许多次改动停留在同一版本。

| 位 | 递增场景 |
|----|----------|
| `MAJOR` | 不兼容变更：接口移除/改名、配置或数据库结构破坏性调整、部署方式变更 |
| `MINOR` | 新增功能：新页面、新接口、新交互、新配置项 |
| `PATCH` | 缺陷修复、样式/文案微调、性能优化、依赖安全更新 |

- 唯一版本源：`backend/app/version.py` 的 `__version__`；**必须通过脚本修改**（同步 `frontend/package.json`、`frontend/package-lock.json`、`packaging/version_info.txt`）：

```bash
backend/.venv/Scripts/python.exe packaging/bump_version.py patch   # 或 minor / major
backend/.venv/Scripts/python.exe packaging/bump_version.py --show  # 查看当前版本
```

- [packaging/build.ps1](packaging/build.ps1) 打包前校验上述**四处版本一致**，不一致直接失败；禁止手改单处。
- 安装包文件名、exe 版本资源、关于页版本均取自该版本号；一次交付只递增一次，多个改动按最高级别合并递增。
- 发布时建议打标签 `git tag v<version>`（未经用户许可不 push）。

## 附：交付前检查清单

- [ ] 已创建语义清晰的 Git commit
- [ ] 已编写/更新测试且全部通过（纯文档改动除外）
- [ ] 测试文件未提交（纯文档改动除外）
- [ ] 不确定的决策均已由用户确认
- [ ] 端口占用时已自动切换并告知用户
- [ ] 文档与注释已与代码逻辑同步
- [ ] 版本号已按语义递增，且四处一致（`bump_version.py`）
- [ ] 未对已提交代码执行未经许可的回退操作
