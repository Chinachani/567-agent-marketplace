---
name: "pydantic-models-py"
description: "遵循包含 Base、Create、Update、Response 及 InDB 等变体的多模型模式构建 Pydantic 模型。适用于在基于 Pydantic v2 的 Python 项目中定义 API 请求与响应结构、数据库模型或执行数据验证。"
version: "1.0.0"
license: "MIT"
metadata:
  author: Microsoft
  version: "1.0.0"
---
# Pydantic Models

Create Pydantic models following the multi-model pattern for clean API contracts.

## Quick Start

Copy the template from [assets/template.py](assets/template.py) and replace placeholders:
- `{{ResourceName}}` → PascalCase name (e.g., `Project`)
- `{{resource_name}}` → snake_case name (e.g., `project`)

## Multi-Model Pattern

| Model | Purpose |
|-------|---------|
| `Base` | Common fields shared across models |
| `Create` | Request body for creation (required fields) |
| `Update` | Request body for updates (all optional) |
| `Response` | API response with all fields |
| `InDB` | Database document with `doc_type` |

## camelCase Aliases

```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

class MyModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    workspace_id: str = Field(..., alias="workspaceId")
    created_at: datetime = Field(..., alias="createdAt")
```

## Optional Update Fields

```python
class MyUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
```

## Database Document

```python
class MyInDB(MyResponse):
    doc_type: str = "my_resource"
```

## Integration Steps

1. Create models in `src/backend/app/models/`
2. Export from `src/backend/app/models/__init__.py`
3. Add corresponding TypeScript types

## Reference Files

| File | Contents |
|------|----------|
| [references/capabilities.md](references/capabilities.md) | Additional non-hero capabilities, operation-group coverage, and production checklists. |

