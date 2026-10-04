# MCP discovery entries

This directory is the shared source path for upstream MCP directory records that are not yet approved for direct installation. These entries have no `mcp.json`; the consuming app must honor `mcpMetadata.installable: false` and show upstream links instead of an install action.

Classification suggestions are generated in `mcp-classification-suggestions.json`. Maintainers must review and copy approved `category` and up to three controlled `tags` into `mcp-curation.json`. Automated suggestions never change published classification.
