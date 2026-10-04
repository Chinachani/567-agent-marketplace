---
name: "wiki-changelog"
description: "分析 Git 提交历史，按变更类型分类生成结构化更新日志。适用于查询近期改动、生成更新日志或了解代码仓库变更的场景。"
version: "1.0.0"
license: "MIT"
metadata:
  author: Microsoft
  version: "1.0.0"
---
# Wiki Changelog

Generate structured changelogs from git history.

## Source Repository Resolution (MUST DO FIRST)

Before generating any changelog, you MUST determine the source repository context:

1. **Check for git remote**: Run `git remote get-url origin` to detect if a remote exists
2. **Ask the user**: _"Is this a local-only repository, or do you have a source repository URL (e.g., GitHub, Azure DevOps)?"_
   - Remote URL provided → store as `REPO_URL`, use **linked citations** for commit hashes and file references
   - Local-only → use plain commit hashes and file references
3. **Do NOT proceed** until source repo context is resolved

## When to Activate

- User asks "what changed recently", "generate a changelog", "summarize commits"
- User wants to understand recent development activity

## Procedure

1. Examine git log (commits, dates, authors, messages)
2. Group by time period: daily (last 7 days), weekly (older)
3. Classify each commit: Features (🆕), Fixes (🐛), Refactoring (🔄), Docs (📝), Config (🔧), Dependencies (📦), Breaking (⚠️)
4. Generate concise user-facing descriptions using project terminology

## Constraints

- Focus on user-facing changes
- Merge related commits into coherent descriptions
- Use project terminology from README
- Highlight breaking changes prominently with migration notes
- When `REPO_URL` is available, link commit hashes: `[abc1234](REPO_URL/commit/abc1234)` and changed files: `[file_path](REPO_URL/blob/BRANCH/file_path)`

