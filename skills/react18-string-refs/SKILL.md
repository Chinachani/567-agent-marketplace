---
name: "react18-string-refs"
description: "提供 React 类组件中将字符串 ref（ref=\"name\" 与 this.refs.name）迁移至 React.createRef() 的精准方案。适用于所有字符串 ref 迁移场景，涵盖单元素 ref、组件内多 ref、列表项 ref、回调 ref 及子组件跨层级传递。编写迁移代码前请务必使用——尤其针对极易出错的列表多 ref 模式，可有效规避常见陷阱。专用于 React 18.3.1（废弃警告）与 React 19（彻底移除）的平滑升级。"
version: "1.0.0"
license: "MIT"
---
# React 18 String Refs Migration

String refs (`ref="myInput"` + `this.refs.myInput`) were deprecated in React 16.3, warn in React 18.3.1, and are **removed in React 19**.

## Quick Pattern Map

| Pattern | Reference |
|---|---|
| Single ref on a DOM element | [→ patterns.md#single-ref](references/patterns.md#single-ref) |
| Multiple refs in one component | [→ patterns.md#multiple-refs](references/patterns.md#multiple-refs) |
| Refs in a list / dynamic refs | [→ patterns.md#list-refs](references/patterns.md#list-refs) |
| Callback refs (alternative approach) | [→ patterns.md#callback-refs](references/patterns.md#callback-refs) |
| Ref passed to a child component | [→ patterns.md#forwarded-refs](references/patterns.md#forwarded-refs) |

## Scan Command

```bash
# Find all string ref assignments in JSX
grep -rn 'ref="' src/ --include="*.js" --include="*.jsx" | grep -v "\.test\."

# Find all this.refs accessors
grep -rn "this\.refs\." src/ --include="*.js" --include="*.jsx" | grep -v "\.test\."
```

Both should be migrated together - find the `ref="name"` and the `this.refs.name` accesses for each component as a pair.

## The Migration Rule

Every string ref migrates to `React.createRef()`:

1. Add `refName = React.createRef();` as a class field (or in constructor)
2. Replace `ref="refName"` → `ref={this.refName}` in JSX
3. Replace `this.refs.refName` → `this.refName.current` everywhere

Read `references/patterns.md` for the full before/after for each case.

