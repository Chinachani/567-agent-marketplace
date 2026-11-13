---
name: "on-device-delegate"
description: "通过将边界明确且读取密集型的子任务（超过约 25 KB 的长文本，或单个命令无法处理的多个文件）委派给运行在本地 MAI Code 1.1 Flash 模型上的本地编程插件端侧 worker，以节省云端模型的上下文。适用于日志与测试分类排查、多文件摘要或从大量输入中提取关键事实。当用户指定该技能时，必须与首次调用的其他工具在同一次回复中调用该技能工具，切勿作为独立步骤调用。"
version: "1.0.0"
license: "MIT"
compatibility: 'GitHub Copilot CLI on Windows with experimental features on, MAI Code 1.1 Flash installed from /model, and the local-coding plugin installed (it provides the on-device worker agent).'
---
# On-Device Delegate

Send the bulky reading in a task to the on-device worker, then check its answer
once. The main session keeps planning and answering. The worker reads the big
inputs on the local model, so they never enter the main context.

## Steps

1. **Gate on what you would read.** If one command or a short script can
   compute the answer, do it yourself now: no plan, no notes about this
   skill. Delegate only when you would otherwise READ more than about 25 KB
   of text into your context (prose, many files). Never delegate security
   review or design decisions.
2. **Check the worker.** The worker is the custom agent
   `local-coding:on-device-worker` (the plugin id). If the task tool lists it
   as plain `on-device-worker` instead (copied into an agents folder), use
   that. If neither is available, work normally.
3. **Brief.** Do not read the big input first. Make ONE task call:
   - `name`: "on-device-<short-kebab>"
   - `description`: 3-5 words
   - `agent_type`: the worker id from step 2
   - `mode`: "sync"
   - `model`: the on-device model id named in the session's routing line,
     exactly (if there is none:
     "winml-azureml-mai-code-1.1-flash-on-device/MAI-Code-1.1-Flash-On-Device").
     The worker does not pin a model, so without this it runs on your own
     model.
   - `prompt`, exactly:

     ```text
     GOAL: <one sentence>
     INPUTS: <exact paths>
     RULES: Read only INPUTS. At most 8 tool calls. Edit nothing but OUTPUT. No questions.
     OUTPUT: <file path and exact format, or: reply only>
     ANSWER: Reply ONCE with only <exact format>, then stop.
     If you cannot, reply only: UNABLE: <reason>
     ```

4. **Check once.** At most ONE cheap check (format, a count, or one spot
   check). Never recompute the answer or re-read the input. If the answer is
   wrong, UNABLE, or the task call fails: do it yourself. Then finish.

## Example

User: "Use the on-device-delegate skill. From the logs under `logs\`, list
every distinct error message with its count, most frequent first."

Task prompt:

```text
GOAL: Count each distinct error message in the logs.
INPUTS: logs\
RULES: Read only INPUTS. At most 8 tool calls. Edit nothing but OUTPUT. No questions.
OUTPUT: reply only
ANSWER: Reply ONCE with only lines of the form "<count> <message>", most frequent first, then stop.
If you cannot, reply only: UNABLE: <reason>
```

Check: confirm the lines match the format and spot-check one count with a
single search. Then answer the user.

## Limits

- The worker can return a confident but wrong answer. The single check
  catches format errors, not every wrong fact. Tell the user what you checked.
- Expect minutes, not seconds, per delegated task, especially on the first
  call while the local model loads.

## Setup scripts

[`scripts/`](scripts/) holds two setup scripts for the user, described in the
local-coding plugin README. They are not part of a task: never run them while
you work on the user's request.

- [`scripts/Set-LocalOutputCap.ps1`](scripts/Set-LocalOutputCap.ps1) caps the
  local model's output tokens in the user's `providers.json`.
- [`scripts/Update-LocalCodingPlugin.ps1`](scripts/Update-LocalCodingPlugin.ps1)
  installs or updates the plugin, then runs the cap script.

