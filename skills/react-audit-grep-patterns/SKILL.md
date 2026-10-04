---
name: "react-audit-grep-patterns"
description: "提供经过全面验证的 grep 扫描命令库，用于在升级至 React 18.3.1 或 React 19 前审计 React 代码库。在 react18-auditor 或 react19-auditor 智能体执行迁移审计时调用此技能。内置完整规则库，可精准排查已废弃/已移除 API、不安全生命周期、批处理隐患、测试文件问题、依赖冲突及 React 19 特有变更。编写扫描命令时务必使用本技能，切勿凭记忆编写 grep 语法，特别是需要指定上下文参数的多行异步 setState 匹配模式。"
version: "1.0.0"
license: "MIT"
---
# React Audit Grep Patterns

Complete scan command library for React 18.3.1 and React 19 migration audits.

## Usage

Read the relevant section for your target:
- **`references/react18-scans.md`** - all scans for React 16/17 → 18.3.1 audit
- **`references/react19-scans.md`** - all scans for React 18 → 19 audit
- **`references/test-scans.md`** - test file specific scans (used by both auditors)
- **`references/dep-scans.md`** - dependency and peer conflict scans

## Base Patterns Used Across All Scans

```bash
# Standard flags used throughout:
# -r = recursive
# -n = show line numbers
# -l = show filenames only (for counting affected files)
# --include="*.js" --include="*.jsx" = JS/JSX files only
# | grep -v "\.test\.\|\.spec\.\|__tests__" = exclude test files
# | grep -v "node_modules" = safety (usually handled by not scanning node_modules)
# 2>/dev/null = suppress "no files found" errors

# Source files only (exclude tests):
SRC_FLAGS='--include="*.js" --include="*.jsx"'
EXCLUDE_TESTS='grep -v "\.test\.\|\.spec\.\|__tests__"'

# Test files only:
TEST_FLAGS='--include="*.test.js" --include="*.test.jsx" --include="*.spec.js" --include="*.spec.jsx"'
```

