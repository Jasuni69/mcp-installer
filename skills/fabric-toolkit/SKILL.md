---
name: fabric-toolkit
description: Comprehensive reference for Microsoft Fabric and Power BI toolkit. Use when looking up MCP tool signatures, translation workflows, CI/CD pipelines, Git integration, deployment pipelines, or raw API endpoints. Covers all 138 fabric-core tools, Power BI report translation, Git connect/commit/pull, deployment pipeline stages, and REST API patterns for Fabric, Power BI, Graph, and OneLake.
---

# Fabric & Power BI Toolkit Reference

## Tool Reference

Full catalog of all 138 fabric-core MCP tools across 24 categories: Workspace, Lakehouse, Warehouse, Tables & Delta, SQL, Semantic Models & DAX, Power BI, Reports, Notebooks, Pipelines & Scheduling, OneLake, Data Loading, Items & Permissions, Microsoft Graph, Git Integration, Deployment Pipelines, Capacities, Raw API, Environments, Connections, Admin, Item Definitions, Spark Job Definitions, Context.

See [TOOL_REFERENCE.md](TOOL_REFERENCE.md) for complete tool signatures and parameters.

## Translation Workflow

End-to-end Power BI report translation pipeline. Covers semantic model translation (Phases 0-9 via MCP tools) and report layer translation (Phase 10 via JSON file editing). Includes rules for nativeQueryRef handling, displayName injection, and scripting repetitive edits.

See [TRANSLATION_GUIDE.md](TRANSLATION_GUIDE.md) for the full workflow.

## CI/CD Workflows

Git integration (connect, commit, pull, status) and deployment pipelines (create, deploy stages, assign workspaces).

See [CICD_GUIDE.md](CICD_GUIDE.md) for step-by-step workflows.

## Raw API Reference

REST API endpoints and Python code patterns for Fabric, Power BI, Microsoft Graph, and OneLake ADLS Gen2. Authentication scopes, LRO handling, DAX execution, SQL via ODBC.

See [API_REFERENCE.md](API_REFERENCE.md) for endpoints and code samples.
