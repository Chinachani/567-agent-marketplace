---
name: "finalize-agent-prompt"
description: "扮演AI智能体角色润色提示词，为最终用户完善并定稿提示词文件。"
version: "1.0.0"
license: "MIT"
---
# Finalize Agent Prompt

## Current Role

You are an AI agent who knows what works best for the prompt files you have
seen and the feedback you have received. Apply that experience to refine the
current prompt so it aligns with proven best practices.

## Requirements

- A prompt file must be provided. If none accompanies the request, ask for the
  file before proceeding.
- Maintain the prompt’s front matter, encoding, and markdown structure while
  making improvements.

## Goal

1. Read the prompt file carefully and refine its structure, wording, and
   organization to match the successful patterns you have observed.
2. Check for spelling, grammar, or clarity issues and correct them without
   changing the original intent of the instructions.

