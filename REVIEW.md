# Code Review — MCP Server Installer

Full review of the `mcp-installer` project.

---

## BUGS

### ~~1. `installer.py:1266` — Missing `mainloop()` call~~ FIXED

---

### ~~2. `installer.py:186` — `__all__` export mismatch in `tools/__init__.py`~~ FIXED

Cleaned up `get_sql_endpoint` import (removed alias), added missing `update_workspace` and `delete_workspace` to imports and `__all__`.

---

### 3. `installer.py:26` — `_CREATION_FLAGS` crashes on non-Windows

```python
_CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
```

This is fine at runtime, but `subprocess.CREATE_NO_WINDOW` is only defined on Windows Python. On macOS/Linux, accessing `subprocess.CREATE_NO_WINDOW` raises `AttributeError` **before** the ternary evaluates. The current code works because Python evaluates the condition first in a ternary — so it's actually OK. **Not a bug**, just a potential confusion point.

---

### ~~4. `installer.py:1152-1162` — `_is_claude_desktop_running()` is Windows-only~~ FIXED

Added `platform.system() != "Windows"` early return.

---

### ~~5. `azure-sql/server.py:119` — SQL injection in `read_resource`~~ FIXED

Added `_quote_identifier()` helper that escapes `]` by doubling. Applied to `read_resource` and `sample_table`.

---

### ~~6. `azure-sql/server.py:244-245` — `execute_query` lacks write warning~~ FIXED

Added WARNING to tool description about INSERT/UPDATE/DELETE/DROP capability.

---

### ~~7. `fabric-core/pyproject.toml:6` — Python version pin~~ FIXED

Pinned to `==3.12.*` across all three servers. Research confirmed `semantic-link-labs` caps at `<3.12`, `passlib` breaks on 3.13+, `pythonnet` caps at `<3.14`. Python 3.12 is the only version where all deps work.

---

### ~~8. `fabric-core/helpers/utils/context.py:12` — `ctx = mcp.get_context()` at module level~~ FIXED

Removed dead code line.

---

### ~~9. `installer.py:969` — Step count is wrong~~ FIXED

Changed `+ 3` to `+ 4` to account for fabric CLAUDE.md step.

---

### ~~10. `fabric-core/fabric_mcp.py` and `fabric_mcp_stdio.py` — Duplicate `clear_context` tool~~ FIXED

Moved `clear_context` to `context.py` (single definition). Both entry points import it.

---

### ~~11. `installer.py:799-806` — Regex replacement may strip trailing newline from CLAUDE.md~~ FIXED

Removed `\r?\n?` from regex pattern so the marker_end match doesn't consume the trailing newline.

---

## POTENTIAL ISSUES / WARNINGS

### ~~12. `fabric-core/helpers/clients/fabric_client.py` — `lru_cache` on async methods~~ FIXED

Replaced with dict-based async cache that stores resolved results, not coroutines. Removed unused `lru_cache` import.

---

### ~~13. `fabric-core/helpers/utils/authentication.py` — `client_id` parameter name is misleading~~ FIXED

Renamed parameter from `client_id` to `session_id` to clarify it's an MCP session ID, not an Azure client ID. Callers pass `ctx.client_id` positionally — no caller changes needed.

---

### ~~14. `azure-sql/server.py:51` — `AZURE_SQL_AUTH` defaults to `"sql"` not `"az_cli"`~~ FIXED

Changed default from `"sql"` to `"az_cli"` to match installer default.

---

### ~~15. No `build-system` in `fabric-core/pyproject.toml`~~ FIXED

Added `[build-system]` section with setuptools.

---

### ~~16. `installer.py:586` — `_az_subscription_id` set as attribute, not `tk.StringVar`~~ FIXED

Initialized `self._az_subscription_id = ""` in `__init__`.

---

### ~~17. `fabric-core/fabric_mcp.py:33` — HTTP server binds to `0.0.0.0`~~ FIXED

Changed to `127.0.0.1`.

---

### ~~18. README.md:17 — ODBC Driver version mismatch~~ FIXED

Added `_pick_odbc_driver()` that tries Driver 18 first, falls back to Driver 17.

---

### 19. Thread safety in installer

Multiple `self.after(0, lambda: ...)` calls in `_run_install` are correct for tkinter thread safety, but the `_log_append` method modifies widget state and is sometimes called directly from threads (e.g., `installer.py:677`):

```python
self._log_append(f"Installing {winget_id} via winget...")
```

This is called from the main thread so it's OK, but the pattern is inconsistent — some log calls go through `self.after()` and some don't. **Not a bug** — the direct calls are always from the main thread.

---

### ~~20. `powerbi-modeling/dll_resolver.py:27` — Only searches `net45` NuGet paths~~ FIXED

Now searches net45, net6.0, net8.0, and netstandard2.0 TFM directories.

---

## CODE SMELLS (not bugs, but worth noting)

- **`fabric_client.py` is ~500 lines** with `_make_request` being ~200 lines of nested logic. Could benefit from splitting LRO handling into its own method.
- **`tools/notebook.py` is 1727 lines** — largest file, hard to navigate. Consider splitting into notebook CRUD, code generation, and job management.
- ~~**`tools/__init__.py` `__all__` list** has 80+ entries manually maintained — easy to get out of sync.~~ Synced — FIXED
- **No tests anywhere** in the project. No `tests/` directory, no pytest config.
- **`fabric-core` depends on `fastapi`, `fastapi-mcp`, `python-jose`, `passlib`** but only uses them in the HTTP entry point (`fabric_mcp.py`), not STDIO. These are unnecessary for the primary use case and bloat the install.
- ~~**Commented-out code** in `fabric_client.py:14`: `# from sempy_labs._helper_functions import create_item`~~ Removed — FIXED

---

## SUMMARY

| Severity | Count | Fixed | Remaining |
|----------|-------|-------|-----------|
| Bug (will crash/break) | 4 | 4 | — |
| Bug (logic error) | 3 | 3 | — |
| Security | 3 | 3 | — |
| Warning | 5 | 5 | — |
| Code smell | 6 | 3 | Large files, no tests, unnecessary deps |
| Not-a-bug | 2 | 0 | #3 ternary (safe), #19 thread calls (safe) |
