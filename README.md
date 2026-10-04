# 567 Agent 官方能力市场 (567 Agent Marketplace)

本仓库是 [567 Agent](https://github.com/Chinachani/567-agent) 的官方能力市场源，提供即开即用、自动同步更新的 **AI 技能 (Skills)** 与 **模型上下文协议服务 (MCP)**。

## 特色

- 🎯 **多源自动收录**：定时扫描 `microsoft/skills`、`github/awesome-copilot` 和 `addyosmani/agent-skills` 中的 `SKILL.md`，保留技能所需的嵌套参考文件，并记录上游仓库、路径、作者和许可证。已有的 `anbeime/skill` 条目继续展示并参与分类，但暂不自动更新，待上游授权信息核实后再恢复同步。
- 🗂️ **按用途分类**：能力分为编程研发、设计创意、办公文档、音视频与图像、研究分析、数据分析、内容创作、商业运营、效率协作、安全合规和实用技能等类别。
- 🔌 **精选 MCP**：收录 MCP 参考服务（本地文件系统、网页抓取、Brave 搜索、GitHub 协同、Postgres/SQLite 数据库等）。其中 Brave、GitHub、Postgres 和 SQLite 为已归档的参考实现，后续迁移应逐项验证维护中的替代服务。
- 🚀 **自动化流**：GitHub Actions 每日同步上游目录，使用 567 API 翻译新描述；每次同步前运行本地校验。

自动抓取范围仅限列出的、仓库声明 MIT 许可且提供标准 `SKILL.md` 的来源；逐项保留技能的独立许可，当前识别 MIT 和 Apache-2.0，以及指向本地 `LICENSE.txt` 的这两种许可。未知许可会停止本次同步，等待审核。Apache-2.0 技能附带完整许可文本，原技能内的许可文件也一并保留。新增来源前应先确认其许可证允许再分发。

同步器跳过隐藏路径、符号链接、超过 512 KiB 的说明、单文件超过 2 MiB 或总资源超过 10 MiB 的技能。被跳过的已收录技能保留此前镜像；上游成功扫描后消失的受管理技能才会清理。上游拉取失败、目录意外为空或仓库许可变更时，本次同步失败并保留现有目录。生成在临时目录完成，替换输出失败时回滚，三个清单副本保持一致。

镜像保留 `allowed-tools`、`compatibility` 和嵌套 `metadata` 等运行元数据，并读取嵌套的作者及版本信息。技能标识按上游仓库及文件路径复用；重名条目使用来源后缀。文件内容指纹覆盖 `SKILL.md` 和嵌套资源，内容变化会递增 `configVersion` 和市场版本；相同上游再次运行不会制造版本更新。分类优先依据技能名称，再读取描述，避免仓库路径和英文词片段误匹配。

只缓存成功的中文翻译。没有 API 密钥或翻译失败时保留原描述，后续运行可重新翻译。GitHub Secrets 中未填写 `API_567_BASE_URL` 和 `API_567_MODEL` 时使用脚本默认值。

## 客户端接入方式

在 567 Agent 桌面端中，本仓库已作为默认官方市场源预置。在“能力中心”中即可直接浏览、一键安装和使用！

## 本地维护

```bash
python3 -m unittest discover -s tests -v
python3 sync_marketplace.py
```

第二条命令会联网拉取上游并更新 `skills/`、`mcps/`、根目录及 `.567agent/`、`.vetta/` 中的清单。有 `API_567_KEY` 时翻译新描述；不配置密钥也可同步，但新条目保留原语言。可选变量为 `API_567_BASE_URL`、`API_567_MODEL`。

客户端运行 Node MCP 需要 Node.js/npm；Fetch 和 SQLite 使用 `uvx`（需安装 uv），SQLite 还使用 `--db-path` 指定数据库。对应启动配置见 [Fetch 上游说明](https://github.com/modelcontextprotocol/servers/tree/main/src/fetch) 和 [SQLite 上游说明](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/sqlite)。GitHub/Brave 等服务仍需各自账号凭据，本同步器不验证这些外部服务的运行环境。

GitHub Actions 每日北京时间 08:00（00:00 UTC）触发，也可在 Actions 页面手动运行；同一分支的同步任务串行执行。代码和来源配置修改推送到默认分支后才会影响远端工作流。
