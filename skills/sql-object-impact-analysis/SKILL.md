---
name: "sql-object-impact-analysis"
description: "在遗留代码库中修改数据表、列、存储过程、视图或触发器之前，全面追踪其在其他 SQL 对象及应用层代码（如 C#、Angular/TypeScript、JS 等）中的所有引用，生成结构化的改动影响面评估报告，提前排查潜在破坏风险。适用于分析“哪些地方使用了该对象/列”、“修改 X 是否安全”、“依赖项排查”、“重命名/删除 X 的影响”，或在陌生代码库中变更数据库结构与存储过程前的安全预检。不适用于隐私/敏感数据泄露分析（参见 data-breach-blast-radius）或 SQL 查询性能调优（参见 sql-optimization）。"
version: "1.0.0"
license: "MIT"
---
# SQL Object Impact Analysis

You are performing a **pre-change dependency trace** for a database object (table, column, stored procedure, view, function, or trigger) inside a legacy or unfamiliar codebase. The goal is a single, trustworthy answer to: *"If I change this, what else is affected?"*

## When to use this

Trigger when the user:
- Names a specific table, column, stored procedure, view, or trigger and asks what uses it, what depends on it, or whether it's safe to change/rename/drop
- Is about to modify a schema element in a codebase with no ORM, or a mixed legacy stack (raw SQL + stored procs + hand-written data access code)
- Asks for a "blast radius," "impact analysis," or "dependency trace" of a specific DB object

Do not use this for:
- General SQL performance tuning (use `sql-optimization`)
- SQL code quality/security review (use `sql-code-review`)
- Privacy/PII exposure analysis (use `data-breach-blast-radius`)
- Architecture-level documentation of an entire codebase (use `doc-and-modernize`)

## Process

1. **Confirm the target object and its exact name(s).** Ask if ambiguous (e.g., multiple tables with similar names, or the user says "the customer table" without specifying schema). Get the precise identifier before searching.

2. **Search the SQL layer first:**
   - Search all `.sql` files, stored procedure definitions, views, functions, and triggers in the repo/database scripts folder for direct references to the object name
   - For a column: check every proc/view/trigger that selects, inserts, updates, or filters on it
   - For a table: check every proc/view/trigger that references it, plus foreign key relationships to/from other tables
   - For a stored procedure: check every other proc that calls it, and every scheduled job/agent step that invokes it
   - Note indirect references too — dynamic SQL (`EXEC(@sql)`), synonyms, and views built on views

3. **Search the application layer:**
   - Search all application code (C#, Java, JS/TS, Angular, whatever the repo contains) for:
     - Direct SQL strings referencing the object name
     - ORM/data-access-layer method or class names that map to it (e.g., a repository method calling the stored procedure)
     - API endpoint handlers that ultimately call into the affected data path
   - Trace one layer further where reasonable: does a frontend component consume an endpoint that touches this object? Note it, but don't chase every UI consumer exhaustively — flag "further downstream consumers likely exist" if the trail runs cold rather than guessing.

4. **Classify each finding by confidence:**
   - **Direct** — object name found verbatim in code/SQL
   - **Indirect** — reached via a proc call chain, ORM mapping, or dynamic SQL that couldn't be fully resolved statically
   - **Uncertain** — plausible but unverified (e.g., dynamic SQL construction that couldn't be traced to a literal object name)
   - Never present an Uncertain finding as if it were Direct — flag it clearly so the reader knows to verify manually

5. **Produce the report** (see Output Format below).

## Output Format

Always structure the report as:

1. **Target Object** — exact name, type (table/column/proc/view/trigger), and schema
2. **Direct SQL Dependents** — list of procs/views/triggers/functions that reference it directly, grouped by object type
3. **Application Code Dependents** — list of files/classes/methods that reference it, grouped by layer (data access, API/service, frontend), with file paths
4. **Indirect / Dynamic References** — anything found via dynamic SQL, synonyms, or call chains that couldn't be fully resolved — labeled clearly as needing manual verification
5. **Risk Summary** — one paragraph: is this object narrowly used (low risk) or widely fanned-out (high risk)? Call out anything that touches a scheduled job, external integration, or reporting layer specifically, since those often get missed
6. **Suggested Verification Steps** — concrete next actions before making the change (e.g., "run these two procs against staging data first," "check if the ReportingService endpoint at X depends on this column")

## Guidelines

- Never claim a dependency is complete or exhaustive — static text search cannot catch every dynamic SQL construction or reflection-based ORM mapping. State the search method used and its limits explicitly in the report.
- Never fabricate a file path, proc name, or line reference. If you searched and found nothing, say "no references found via text search" — not silence, and not an invented result.
- If the codebase is large enough that a full trace isn't feasible in one pass, say so and propose scoping (e.g., "search only the `Orders` module first") rather than silently producing a partial report as if it were complete.
- Keep the report scannable — this is a pre-change safety check someone will read in a few minutes before making a decision, not a full architecture document.
