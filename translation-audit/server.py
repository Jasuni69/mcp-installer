#!/usr/bin/env python3
"""
MCP server for Power BI translation audit (v2).

Deep-scans .pbip report JSON for potentially untranslated content.
Uses the MCP Python SDK for protocol handling.
"""

import json
import glob
import os
import re
from typing import List, Dict, Any, Tuple, Set, Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("powerbi-translation-audit")


# ---------------------------------------------------------------------------
# Target-language character sets
# ---------------------------------------------------------------------------
LANGUAGE_CHARS: Dict[str, Set[str]] = {
    "sv-SE": set("åäöÅÄÖ"),
    "nb-NO": set("æøåÆØÅ"),
    "da-DK": set("æøåÆØÅ"),
    "de-DE": set("äöüßÄÖÜ"),
    "fr-FR": set("éèêëàâùûçîïôÉÈÊËÀÂÙÛÇÎÏÔ"),
    "es-ES": set("ñáéíóúüÑÁÉÍÓÚÜ"),
    "pt-BR": set("ãõáéíóúâêôçÃÕÁÉÍÓÚÂÊÔÇ"),
    "it-IT": set("àèéìòùÀÈÉÌÒÙ"),
    "pl-PL": set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ"),
    "fi-FI": set("äöÄÖ"),
}


# ---------------------------------------------------------------------------
# Value-level filters (always non-translatable regardless of location)
# ---------------------------------------------------------------------------
_NON_TRANSLATABLE_RE = [
    re.compile(r"^#[0-9a-fA-F]{3,8}$"),
    re.compile(r"^rgba?\("),
    re.compile(r"^-?\d+(\.\d+)?[DL]?$"),
    re.compile(r"^(true|false)$", re.I),
    re.compile(r"^datetime'.*'$"),
    re.compile(r"^null$"),
    re.compile(r"^https?://"),
    re.compile(r"^[\d\s.,;:/%+\-–—=<>()]+$"),
]

_FONT_RE = re.compile(
    r"(serif|sans-serif|mono|wf_|segoe|helvetica|arial|calibri|cambria|"
    r"verdana|tahoma|trebuchet|georgia|consolas|courier)", re.I,
)


def _strip_quotes(text: str) -> str:
    s = text.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


def _is_non_translatable(raw: str) -> bool:
    clean = _strip_quotes(raw.strip())
    if len(clean) < 2:
        return True
    for pat in _NON_TRANSLATABLE_RE:
        if pat.match(clean):
            return True
    if _FONT_RE.search(clean) and ("," in clean or "'" in clean):
        return True
    return False


def _has_target_chars(text: str, target: Set[str]) -> bool:
    return bool(set(text) & target)


def _is_readable(text: str) -> bool:
    clean = _strip_quotes(text.strip())
    if not any(c.isalpha() for c in clean):
        return False
    if clean.startswith("_") and " " not in clean:
        return False
    return True


# ---------------------------------------------------------------------------
# Exceptions loading
# ---------------------------------------------------------------------------

def load_exceptions(file_path: Optional[str]) -> Tuple[Set[str], Set[str]]:
    if not file_path or not os.path.isfile(file_path):
        return set(), set()
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return set(), set()

    skip_nqr: Set[str] = set()
    known_good: Set[str] = set()

    if "translations" in data:
        known_good.update(data["translations"].values())
    if "skip" in data:
        skip_nqr.update(data["skip"])
    if "skip_nqr" in data:
        skip_nqr.update(data["skip_nqr"])
    if "known_good" in data:
        known_good.update(data["known_good"])

    return skip_nqr, known_good


# ---------------------------------------------------------------------------
# Visual scanner
# ---------------------------------------------------------------------------

def _get_literal_value(obj: dict, *prop_path: str) -> Optional[str]:
    node = obj
    for key in prop_path:
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            return None
    return node if isinstance(node, str) else None


def scan_visual(file_path: str, target: Set[str],
                skip_nqr: Set[str] = frozenset(),
                known_good: Set[str] = frozenset()) -> Dict[str, List[Dict[str, str]]]:
    cats: Dict[str, List[Dict[str, str]]] = {
        "title_subtitle": [],
        "displayname": [],
        "missing_displayname": [],
        "textbox": [],
        "placeholder": [],
        "header_text": [],
        "button_text": [],
    }

    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, UnicodeDecodeError, FileNotFoundError):
        return cats

    visual = data.get("visual", {})
    visual_type = data.get("visualType", "")
    vco = visual.get("visualContainerObjects", {})
    objects = visual.get("objects", {})

    for section in ("title", "subTitle"):
        for obj in vco.get(section, []):
            val = _get_literal_value(obj, "properties", "text", "expr", "Literal", "Value")
            if val:
                clean = _strip_quotes(val)
                if clean and not _is_non_translatable(val) and _is_readable(clean):
                    if clean not in known_good and not _has_target_chars(clean, target):
                        cats["title_subtitle"].append({"text": clean, "section": section})

    qs = visual.get("query", {}).get("queryState", {})
    for bucket, bdata in qs.items():
        if not isinstance(bdata, dict):
            continue
        for proj in bdata.get("projections", []):
            nqr = proj.get("nativeQueryRef")
            dn = proj.get("displayName")
            if nqr and not dn:
                if nqr not in skip_nqr:
                    cats["missing_displayname"].append({"nativeQueryRef": nqr, "bucket": bucket})
            elif dn and nqr:
                if dn == nqr and not _is_non_translatable(dn) and _is_readable(dn):
                    if nqr not in skip_nqr and dn not in known_good and not _has_target_chars(dn, target):
                        cats["displayname"].append({"text": dn, "nativeQueryRef": nqr})

    if visual_type == "textbox":
        for gen in objects.get("general", []):
            for para in gen.get("properties", {}).get("paragraphs", []):
                for run in para.get("textRuns", []):
                    v = run.get("value", "").strip()
                    if v and _is_readable(v) and not _is_non_translatable(v):
                        if not _has_target_chars(v, target):
                            cats["textbox"].append({"text": v})
        for para in visual.get("paragraphs", []):
            for run in para.get("textRuns", []):
                v = run.get("value", "").strip()
                if v and _is_readable(v) and not _is_non_translatable(v):
                    if not _has_target_chars(v, target):
                        cats["textbox"].append({"text": v})

    for section_items in objects.values():
        if not isinstance(section_items, list):
            continue
        for obj in section_items:
            val = _get_literal_value(obj, "properties", "placeholder", "expr", "Literal", "Value")
            if val:
                clean = _strip_quotes(val)
                if clean and _is_readable(clean) and not _is_non_translatable(val):
                    if not _has_target_chars(clean, target):
                        cats["placeholder"].append({"text": clean})

    for section_name, section_items in objects.items():
        if section_name != "header":
            continue
        if not isinstance(section_items, list):
            continue
        for obj in section_items:
            val = _get_literal_value(obj, "properties", "text", "expr", "Literal", "Value")
            if val:
                clean = _strip_quotes(val)
                if clean and _is_readable(clean) and not _is_non_translatable(val):
                    if not _has_target_chars(clean, target):
                        cats["header_text"].append({"text": clean})

    if visual_type in ("actionButton", "button"):
        for section_items in objects.values():
            if not isinstance(section_items, list):
                continue
            for obj in section_items:
                for prop in ("text", "label"):
                    val = _get_literal_value(obj, "properties", prop, "expr", "Literal", "Value")
                    if val:
                        clean = _strip_quotes(val)
                        if clean and _is_readable(clean) and not _is_non_translatable(val):
                            if not _has_target_chars(clean, target):
                                cats["button_text"].append({"text": clean, "property": prop})

    return cats


def scan_page_names(pages_dir: str, target: Set[str],
                    known_good: Set[str] = frozenset()) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    for fp in sorted(glob.glob(os.path.join(pages_dir, "*", "page.json"))):
        try:
            with open(fp, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        dn = data.get("displayName", "")
        if dn and _is_readable(dn) and not _is_non_translatable(dn):
            if dn not in known_good and not _has_target_chars(dn, target):
                findings.append({
                    "page_id": os.path.basename(os.path.dirname(fp)),
                    "displayName": dn,
                })
    return findings


# ---------------------------------------------------------------------------
# High-level scan + format
# ---------------------------------------------------------------------------

_ALL_CATS = [
    "title_subtitle", "displayname", "missing_displayname",
    "textbox", "placeholder", "header_text", "button_text",
]

_CAT_LABELS = {
    "title_subtitle": "Title/Subtitle",
    "displayname": "DisplayName (no target-lang chars)",
    "missing_displayname": "Missing displayName",
    "textbox": "Textbox content",
    "placeholder": "Placeholder text",
    "header_text": "Header/label text",
    "button_text": "Button text",
}


def scan_all(pages_dir: str, target: Set[str],
             skip_nqr: Set[str] = frozenset(),
             known_good: Set[str] = frozenset()) -> Dict[str, Any]:
    findings: List[Dict[str, Any]] = []
    for fp in sorted(glob.glob(os.path.join(pages_dir, "**", "visual.json"), recursive=True)):
        cats = scan_visual(fp, target, skip_nqr, known_good)
        if any(cats.values()):
            findings.append({"file": os.path.relpath(fp, pages_dir), **cats})
    return {"visuals": findings, "pages": scan_page_names(pages_dir, target, known_good)}


def format_findings(result: Dict[str, Any]) -> str:
    visuals = result["visuals"]
    pages = result["pages"]
    if not visuals and not pages:
        return "No suspected untranslated content found."

    lines = ["TRANSLATION AUDIT — DETAILED FINDINGS", "=" * 55, ""]

    if pages:
        lines.append(f"UNTRANSLATED PAGE NAMES ({len(pages)}):")
        for p in pages:
            lines.append(f"  {p['page_id']}: \"{p['displayName']}\"")
        lines.append("")

    totals: Dict[str, int] = {c: 0 for c in _ALL_CATS}
    for vf in visuals:
        file_lines: List[str] = []
        for cat in _ALL_CATS:
            items = vf.get(cat, [])
            if not items:
                continue
            totals[cat] += len(items)
            file_lines.append(f"  {_CAT_LABELS[cat]} ({len(items)}):")
            for item in items:
                if "text" in item:
                    extra = ""
                    if "section" in item:
                        extra = f"  [{item['section']}]"
                    elif "nativeQueryRef" in item and item["nativeQueryRef"]:
                        extra = f"  (nqr: {item['nativeQueryRef']})"
                    file_lines.append(f"    - \"{item['text']}\"{extra}")
                elif "nativeQueryRef" in item:
                    file_lines.append(f"    - nqr: \"{item['nativeQueryRef']}\"  [bucket: {item.get('bucket', '')}]")
        if file_lines:
            lines.append(f"File: {vf['file']}")
            lines.extend(file_lines)
            lines.append("")

    total_all = sum(totals.values()) + len(pages)
    lines.append("-" * 55)
    lines.append("SUMMARY:")
    if pages:
        lines.append(f"  Page names: {len(pages)}")
    for cat in _ALL_CATS:
        if totals[cat]:
            lines.append(f"  {_CAT_LABELS[cat]}: {totals[cat]}")
    lines.append(f"  TOTAL: {total_all}")
    lines.append("")
    return "\n".join(lines)


def _validate_coverage(pages_dir: str, target: Set[str],
                       skip_nqr: Set[str] = frozenset(),
                       known_good: Set[str] = frozenset()) -> str:
    result = scan_all(pages_dir, target, skip_nqr, known_good)
    visuals = result["visuals"]
    pages = result["pages"]

    total_proj = 0
    proj_with_dn = 0
    for fp in glob.glob(os.path.join(pages_dir, "**", "visual.json"), recursive=True):
        try:
            with open(fp, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        qs = data.get("visual", {}).get("query", {}).get("queryState", {})
        for bucket in qs.values():
            if isinstance(bucket, dict):
                for proj in bucket.get("projections", []):
                    if proj.get("nativeQueryRef"):
                        total_proj += 1
                        if "displayName" in proj:
                            proj_with_dn += 1

    issue_count = len(pages)
    for vf in visuals:
        for cat in _ALL_CATS:
            issue_count += len(vf.get(cat, []))

    cov = (proj_with_dn / total_proj * 100) if total_proj else 0
    verdict = "PASS" if issue_count == 0 else "FAIL"

    lines = [
        "TRANSLATION COVERAGE VALIDATION",
        "=" * 55, "",
        f"Projections total: {total_proj}",
        f"Projections with displayName: {proj_with_dn} ({cov:.1f}%)",
        f"Projections missing displayName: {total_proj - proj_with_dn}", "",
        f"Total suspected untranslated strings: {issue_count}", "",
        f"VERDICT: {verdict}", "",
    ]
    if verdict == "FAIL":
        lines.append("Run scan_english_remaining for details.")
    else:
        lines.append("No suspected untranslated content found!")
    return "\n".join(lines)


def _resolve_target(lang: Optional[str]) -> Set[str]:
    if lang and lang in LANGUAGE_CHARS:
        return LANGUAGE_CHARS[lang]
    if lang:
        for key, chars in LANGUAGE_CHARS.items():
            if key.startswith(lang):
                return chars
    return LANGUAGE_CHARS["sv-SE"]


# ---------------------------------------------------------------------------
# MCP tool definitions (using SDK)
# ---------------------------------------------------------------------------

@mcp.tool()
def scan_english_remaining(
    pages_dir: str,
    target_language: str = "sv-SE",
    exceptions_file: str = "",
) -> str:
    """Deep-scan all visual.json AND page.json files for suspected untranslated content.
    Checks: titles, subtitles, displayNames, missing displayNames, textboxes,
    placeholders, slicer/filter header text, and button labels."""
    target = _resolve_target(target_language)
    skip_nqr, known_good = load_exceptions(exceptions_file or None)
    return format_findings(scan_all(pages_dir, target, skip_nqr, known_good))


@mcp.tool()
def scan_missing_displaynames(
    pages_dir: str,
    exceptions_file: str = "",
) -> str:
    """Find ALL projections with nativeQueryRef but no displayName override."""
    skip_nqr, _ = load_exceptions(exceptions_file or None)
    findings: List[str] = []
    total = 0
    for fp in sorted(glob.glob(os.path.join(pages_dir, "**", "visual.json"), recursive=True)):
        try:
            with open(fp, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        qs = data.get("visual", {}).get("query", {}).get("queryState", {})
        for bucket, bdata in qs.items():
            if not isinstance(bdata, dict):
                continue
            for proj in bdata.get("projections", []):
                nqr = proj.get("nativeQueryRef")
                if nqr and "displayName" not in proj and nqr not in skip_nqr:
                    total += 1
                    findings.append(
                        f"  {os.path.relpath(fp, pages_dir)}  nqr: \"{nqr}\"  [bucket: {bucket}]"
                    )
    if findings:
        return f"MISSING DISPLAYNAME: {total} projections\n\n" + "\n".join(findings)
    return "All projections have displayName overrides."


@mcp.tool()
def validate_translation_coverage(
    pages_dir: str,
    target_language: str = "sv-SE",
    exceptions_file: str = "",
) -> str:
    """Run full deep scan and produce PASS/FAIL verdict.
    Checks titles, displayNames, textboxes, placeholders,
    header text, button labels, page names, missing displayNames."""
    target = _resolve_target(target_language)
    skip_nqr, known_good = load_exceptions(exceptions_file or None)
    return _validate_coverage(pages_dir, target, skip_nqr, known_good)


if __name__ == "__main__":
    mcp.run(transport="stdio")
