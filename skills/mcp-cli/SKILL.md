---
name: "mcp-cli"
description: "通过命令行与 MCP（模型上下文协议）服务器交互。适用于需要通过 MCP 连接外部工具、API 或数据源，查看可用的 MCP 服务器及工具列表，或直接在命令行调用 MCP 工具的场景。"
version: "1.0.0"
license: "MIT"
---
# MCP-CLI

Access MCP servers through the command line. MCP enables interaction with external systems like GitHub, filesystems, databases, and APIs.

## Commands

| Command                            | Output                          |
| ---------------------------------- | ------------------------------- |
| `mcp-cli`                          | List all servers and tool names |
| `mcp-cli <server>`                 | Show tools with parameters      |
| `mcp-cli <server>/<tool>`          | Get tool JSON schema            |
| `mcp-cli <server>/<tool> '<json>'` | Call tool with arguments        |
| `mcp-cli grep "<glob>"`            | Search tools by name            |

**Add `-d` to include descriptions** (e.g., `mcp-cli filesystem -d`)

## Workflow

1. **Discover**: `mcp-cli` → see available servers and tools
2. **Explore**: `mcp-cli <server>` → see tools with parameters
3. **Inspect**: `mcp-cli <server>/<tool>` → get full JSON input schema
4. **Execute**: `mcp-cli <server>/<tool> '<json>'` → run with arguments

## Examples

```bash
# List all servers and tool names
mcp-cli

# See all tools with parameters
mcp-cli filesystem

# With descriptions (more verbose)
mcp-cli filesystem -d

# Get JSON schema for specific tool
mcp-cli filesystem/read_file

# Call the tool
mcp-cli filesystem/read_file '{"path": "./README.md"}'

# Search for tools
mcp-cli grep "*file*"

# JSON output for parsing
mcp-cli filesystem/read_file '{"path": "./README.md"}' --json

# Complex JSON with quotes (use heredoc or stdin)
mcp-cli server/tool <<EOF
{"content": "Text with 'quotes' inside"}
EOF

# Or pipe from a file/command
cat args.json | mcp-cli server/tool

# Find all TypeScript files and read the first one
mcp-cli filesystem/search_files '{"path": "src/", "pattern": "*.ts"}' --json | jq -r '.content[0].text' | head -1 | xargs -I {} sh -c 'mcp-cli filesystem/read_file "{\"path\": \"{}\"}"'
```

## Options

| Flag         | Purpose                   |
| ------------ | ------------------------- |
| `-j, --json` | JSON output for scripting |
| `-r, --raw`  | Raw text content          |
| `-d`         | Include descriptions      |

## Exit Codes

- `0`: Success
- `1`: Client error (bad args, missing config)
- `2`: Server error (tool failed)
- `3`: Network error

