---
name: "ai-ready"
description: "一键让代码仓库全面就绪 AI 开发：深度分析代码库，自动生成 AGENTS.md、copilot-instructions.md、CI 工作流及 Issue 模板等配置；挖掘团队 PR 审查规范，量身定制适配当前技术栈的文件。当用户需要“让仓库支持 AI”、“配置 AI 开发环境”或“准备 AI 协作规范”时使用此技能。"
version: "1.0.0"
license: "MIT"
---
# AI Ready

This skill helps the user install the latest [ai-ready](https://github.com/johnpapa/ai-ready) skill by [John Papa](https://github.com/johnpapa).

*Why?*: The full ai-ready skill is ~600 lines of detailed instructions that evolve frequently. This wrapper keeps it discoverable here while the source of truth stays in [johnpapa/ai-ready](https://github.com/johnpapa/ai-ready) — always up to date.

## Steps

1. Tell the user to add the skill by running this command inside Copilot CLI:

   ```
   /skills add johnpapa/ai-ready
   ```

   This downloads the latest version of the skill to their personal skills directory. Re-running the command updates to the latest version.

2. Remind the user to review the skill before loading it. They can inspect it with:
   ```bash
   head -20 ~/.copilot/skills/ai-ready/SKILL.md
   ```
3. After the user confirms they've reviewed and installed it, tell them to reload skills with `/skills reload` and then say `make this repo ai-ready`.
4. Do **not** run the command on the user's behalf. The user must run it themselves.

