---
name: "tiny-stepping"
description: "采用渐进式开发流程，每步仅完成最小的有效变更并暂停等待反馈，以便在继续前尽早校准方向。适用于需要持续验证与审慎推进的迭代开发场景。"
version: "1.0.0"
license: "MIT"
---
# Tiny Stepping

Drive implementation in the smallest possible meaningful increments, pausing for feedback after each step so the work stays reviewable and easy to course-correct.

## Purpose
- Make the smallest possible meaningful change at each step
- Get user feedback after every step before proceeding
- Reduce risk of going in the wrong direction
- Keep changes reviewable and easy to understand

## Workflow
1. Agree on the next tiny step
2. Implement only that step — nothing more
3. Review uncommitted changes together to verify the step looks right
4. Short check-in: is this the right direction?
5. Commit the step before moving on
6. Agree on the next step
7. Repeat

## Principles
- One concern per step — don't mix unrelated changes
- Each step should be independently understandable
- Prefer compiling/working state after each step
- Don't anticipate future steps — wait for feedback first
- If a step feels too big, split it further

