---
name: "react18-legacy-context"
description: "提供将 React 旧版 Context API（contextTypes、childContextTypes、getChildContext）完整迁移至现代 createContext API 的操作指南。在类组件中重构旧版 Context 时使用——此类迁移涉及跨文件联动，必须确保 Provider 与所有 Consumer 同步更新。在修改任何旧版 Context 相关代码前务必先调用此技能；单方面迁移任意一侧均会导致运行时崩溃。开始迁移前请务必阅读，遵循其中的跨文件协作步骤以规避最常见的迁移陷阱。"
version: "1.0.0"
license: "MIT"
---
# React 18 Legacy Context Migration

Legacy context (`contextTypes`, `childContextTypes`, `getChildContext`) was deprecated in React 16.3 and warns in React 18.3.1. It is **removed in React 19**.

## This Is Always a Cross-File Migration

Unlike most other migrations that touch one file at a time, context migration requires coordinating:
1. Create the context object (usually a new file)
2. Update the **provider** component
3. Update **every consumer** component

Missing any consumer leaves the app broken - it will read from the wrong context or get `undefined`.

## Migration Steps (Always Follow This Order)

```
Step 1: Find the provider (childContextTypes + getChildContext)
Step 2: Find ALL consumers (contextTypes)
Step 3: Create the context file
Step 4: Update the provider
Step 5: Update each consumer (class components → contextType, function components → useContext)
Step 6: Verify - run the app, check no legacy context warnings remain
```

## Scan Commands

```bash
# Find all providers
grep -rn "childContextTypes\|getChildContext" src/ --include="*.js" --include="*.jsx" | grep -v "\.test\."

# Find all consumers
grep -rn "contextTypes\s*=" src/ --include="*.js" --include="*.jsx" | grep -v "\.test\."

# Find this.context usage (may be legacy or modern - check which)
grep -rn "this\.context\." src/ --include="*.js" --include="*.jsx" | grep -v "\.test\."
```

## Reference Files

- **`references/single-context.md`** - complete migration for one context (theme, auth, etc.) with provider + class consumer + function consumer
- **`references/multi-context.md`** - apps with multiple legacy contexts (nested providers, multiple consumers of different contexts)
- **`references/context-file-template.md`** - the standard file structure for a new context module

