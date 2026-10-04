---
name: "zustand-store-ts"
description: "使用 TypeScript、subscribeWithSelector 中间件和规范的状态/操作分离模式创建 Zustand store。适用于构建 React 状态管理、搭建全局 store 或实现响应式状态设计模式等场景。"
version: "1.0.0"
license: "MIT"
metadata:
  author: Microsoft
  version: "1.0.0"
---
# Zustand Store

Create Zustand stores following established patterns with proper TypeScript types and middleware.

## Quick Start

Copy the template from [assets/template.ts](assets/template.ts) and replace placeholders:
- `{{StoreName}}` → PascalCase store name (e.g., `Project`)
- `{{description}}` → Brief description for JSDoc

## Always Use subscribeWithSelector

```typescript
import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';

export const useMyStore = create<MyStore>()(
  subscribeWithSelector((set, get) => ({
    // state and actions
  }))
);
```

## Separate State and Actions

```typescript
export interface MyState {
  items: Item[];
  isLoading: boolean;
}

export interface MyActions {
  addItem: (item: Item) => void;
  loadItems: () => Promise<void>;
}

export type MyStore = MyState & MyActions;
```

## Use Individual Selectors

```typescript
// Good - only re-renders when `items` changes
const items = useMyStore((state) => state.items);

// Avoid - re-renders on any state change
const { items, isLoading } = useMyStore();
```

## Subscribe Outside React

```typescript
useMyStore.subscribe(
  (state) => state.selectedId,
  (selectedId) => console.log('Selected:', selectedId)
);
```

## Integration Steps

1. Create store in `src/frontend/src/store/`
2. Export from `src/frontend/src/store/index.ts`
3. Add tests in `src/frontend/src/store/*.test.ts`

