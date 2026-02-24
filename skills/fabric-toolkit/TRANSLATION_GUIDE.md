# Translation Workflow

When user says "translate" or "translate using the playbook":

Read and follow `TRANSLATION_PLAYBOOK.md` from Phase 0 through Phase 10:
- **Phases 0-9**: Use MCP tools (ToolSearch for `powerbi-modeling` tools) to translate the semantic model
- **Phase 10**: Edit report JSON files on disk (visual titles, nativeQueryRef displayName injection, text boxes)
- For Phase 10 step 10.3, use `pbip_translate_display_names.py` with `translation_map_sv-SE.json` as the base dictionary
- After all phases: use the `powerbi-translation-audit` MCP tools to verify zero English remains
- Call `validate_translation_coverage` with the report's pages_dir for a PASS/FAIL verdict
- If FAIL, call `scan_english_remaining` for details on what to fix

## Translation Key Files

| File | When to use |
|------|-------------|
| `TRANSLATION_PLAYBOOK.md` | The full translation process — read this first |
| `pbip_translate_display_names.py` | Phase 10.3 — bulk nativeQueryRef -> displayName |
| `pbip_fix_visual_titles.py` | Phase 10.4 — fix auto-generated visual titles + slicer headers |
| `translation_map_sv-SE.json` | Swedish translation dictionary — start from this, add project-specific terms |

## Translation Rules

- Always scan ALL pages, not just a few. Targeted scans miss 80%+ of English.
- Never change `nativeQueryRef` values. Add `displayName` next to them instead.
- Never translate conditional formatting selectors (`scopeId.Comparison.Right.Literal.Value`).
- Run `pbip_fix_visual_titles.py` AFTER `pbip_translate_display_names.py` — the title script uses displayName values from projections.
- After editing .pbip JSON, user must close and reopen Power BI Desktop to see changes.
- Run `validate_translation_coverage` before declaring done. No "trust me it's translated" — get a PASS verdict.

## Scripting Repetitive Edits

When you find translatable content that requires repetitive manual edits across many files:
1. Write a project-specific script in the project's own folder
2. Follow the pattern: scan -> build map -> dry-run -> execute
3. Always include `--dry-run` mode
4. Goal: never do more than 5 manual edits of the same type. If there are more, script it.
