#!/usr/bin/env python3
"""Deterministic helpers for saas-landing-builder blueprints, drafts and rebuild plans.

Subcommands (each prints one JSON envelope with --json):

    sections     [--page-type ID]
        The section set for a page type (required, recommended and optional
        slots, the labels that fill each slot) or the list of page types.

    completeness LABELS.json [--outline OUTLINE.json] [--page-type ID]
        Counts the model's block labels against the page type's section set.
        LABELS.json:
            {"page_type": "plg-homepage",
             "outline": "growth-reports/.cache/<slug>-outline.json",
             "blocks": [{"block": 0, "labels": ["hero"], "evidence": "H1 '...'"},
                        {"block": "footer", "labels": ["footer"]}],
             "not_measured": ["pricing"]}
        Every outline block must carry a label ("other" when none fits).
        Slots in not_measured are left out of the counts. No order verdict.

    lint FILE (.md, .html or .txt)
        Proof placeholders, claim candidates (numbers, ratings, rankings,
        time claims, money, before/after) and attributed quotes that need a
        source. For HTML prototypes also: DRAFT label, noindex, viewport,
        lang, one h1, external resources, live form actions, missing alt
        text and labels, responsive and focus styles.

    test-plan --baseline 3.8% [--weekly-visitors N | --monthly-visitors N] [--mde 20%]
        A/B test sizing with the shared stats helper (two proportions, alpha
        0.05 two-sided, power 0.8, 4-week limit): A/B test or ship-and-measure.

    benchmarks [--metric M ...] [--motion free_trial|freemium|...]
        Rows from references/_shared/saas-benchmarks.json with source and year.

Exit codes (shared contract): 0 ok, 2 usage or input error, 4 partial,
5 nothing to analyze (empty file).
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _growthkit import cli  # noqa: E402
import builder_common  # noqa: E402
import proof_patterns  # noqa: E402

TOOL = "blueprint_tools"
SECTION_SETS_VERSION_PREFIX = "section-sets-"
MIN_MEASURED_SHARE = 0.6  # report-contract.md section 4: composite needs 60% measured
DEFAULT_METRICS = ("landing_page_conversion", "visitor_to_signup", "form_view_to_completion")
CHROME_BLOCKS = ("footer", "nav")


# ---------------------------------------------------------------------------
# sections
# ---------------------------------------------------------------------------


def page_type_or_error(sets: Dict[str, Any], page_type: Optional[str]) -> Dict[str, Any]:
    types = sets.get("page_types") or {}
    if not page_type:
        raise cli.UsageError("No page type given. Use one of: %s" % ", ".join(sorted(types)))
    key = page_type.strip().lower().replace(" ", "-").replace("_", "-")
    if key not in types:
        raise cli.UsageError("Unknown page type %r. Use one of: %s" % (page_type, ", ".join(sorted(types))))
    return dict(types[key], id=key)


def _section_sets() -> Dict[str, Any]:
    try:
        return builder_common.load_section_sets()
    except (OSError, ValueError) as exc:
        raise cli.UsageError("Cannot read %s: %s (reinstall the skill)" % (builder_common.SECTION_SETS_PATH, exc))


def cmd_sections(args: Any, run: cli.Run) -> int:
    sets = _section_sets()
    if args.page_type:
        try:
            page = page_type_or_error(sets, args.page_type)
        except cli.UsageError as exc:
            return run.fail(cli.STATUS_USAGE, str(exc))
        labels = sets.get("labels") or {}
        slots = []
        for slot in page["slots"]:
            slots.append(dict(slot, label_meanings={name: labels.get(name) for name in slot["any_of"]}))
        return run.emit({
            "section_sets_version": sets.get("version"),
            "page_type": {k: page[k] for k in ("id", "label", "conversion", "nav")},
            "slots": slots,
            "labels": labels,
        }, human=lambda env: _human_sections(env))
    types = [
        {"id": key, "label": value.get("label"), "conversion": value.get("conversion"), "nav": value.get("nav"),
         "required": [s["id"] for s in value.get("slots", []) if s["level"] == "required"]}
        for key, value in (sets.get("page_types") or {}).items()
    ]
    return run.emit({"section_sets_version": sets.get("version"), "page_types": types,
                     "labels": sets.get("labels") or {}})


def _human_sections(env: Dict[str, Any]) -> str:
    page = env.get("page_type") or {}
    lines = ["%s (%s)" % (page.get("label"), page.get("id"))]
    for slot in env.get("slots") or []:
        lines.append("  %-11s %-18s any of: %s" % (slot["level"], slot["id"], ", ".join(slot["any_of"])))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# completeness
# ---------------------------------------------------------------------------


def _load_outline(value: Any, base_dir: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """The analyzer envelope, from a dict or a path (relative to cwd or the labels file)."""
    if value is None:
        return None, None
    if isinstance(value, dict):
        return value, "inline"
    path = str(value)
    candidates = [path, os.path.join(base_dir, path)]
    for candidate in candidates:
        if os.path.isfile(candidate):
            try:
                with open(candidate, encoding="utf-8") as handle:
                    data = json.load(handle)
            except (OSError, ValueError) as exc:
                raise cli.UsageError("Cannot read outline %s: %s" % (candidate, exc))
            if not isinstance(data, dict):
                raise cli.UsageError("Outline %s is not a JSON object." % candidate)
            return data, candidate
    raise cli.UsageError("Outline file not found: %s" % path)


def _normalize_block_ref(value: Any) -> Any:
    if isinstance(value, bool):
        raise cli.UsageError("block must be an index or 'footer'/'nav', got %r" % value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = str(value).strip().lower()
    if text in CHROME_BLOCKS:
        return text
    if re.match(r"^\d+$", text):
        return int(text)
    raise cli.UsageError("block must be an outline index or 'footer'/'nav', got %r" % value)


def compute_completeness(labels_doc: Dict[str, Any], sets: Dict[str, Any], outline: Optional[Dict[str, Any]],
                         page_type: Optional[str], mode: Optional[str]) -> Dict[str, Any]:
    """Pure function behind the completeness command. Raises cli.UsageError."""
    page = page_type_or_error(sets, page_type or labels_doc.get("page_type"))
    vocabulary = set((sets.get("labels") or {}).keys())
    entries = labels_doc.get("blocks")
    if not isinstance(entries, list) or not entries:
        raise cli.UsageError("'blocks' must be a non-empty list of {\"block\": <index>, \"labels\": [...]}")

    labelled: Dict[Any, List[str]] = {}
    evidence: Dict[Any, Any] = {}
    unknown_labels: List[str] = []
    for item in entries:
        if not isinstance(item, dict):
            raise cli.UsageError("Each entry in 'blocks' must be an object, got %r" % (item,))
        ref = _normalize_block_ref(item.get("block", item.get("index")))
        raw = item.get("labels", item.get("label"))
        names = [raw] if isinstance(raw, str) else list(raw or [])
        clean = []
        for name in names:
            key = str(name).strip().lower().replace(" ", "_").replace("-", "_")
            if key not in vocabulary:
                unknown_labels.append(str(name))
            elif key not in clean:
                clean.append(key)
        if not names:
            raise cli.UsageError("Block %s has no labels; use 'other' when none fits." % ref)
        labelled.setdefault(ref, [])
        for key in clean:
            if key not in labelled[ref]:
                labelled[ref].append(key)
        if item.get("evidence"):
            evidence[ref] = item.get("evidence")
    if unknown_labels:
        raise cli.UsageError("Unknown label(s): %s. Use: %s" % (
            ", ".join(sorted(set(unknown_labels))), ", ".join(sorted(vocabulary))))

    notes: List[str] = []
    order: List[Any] = sorted([r for r in labelled if isinstance(r, int)])
    outline_blocks: List[Dict[str, Any]] = []
    if outline is not None:
        outline_blocks = [b for b in (outline.get("blocks") or []) if isinstance(b, dict)]
        indices = [b.get("index") for b in outline_blocks]
        unknown = sorted(r for r in labelled if isinstance(r, int) and r not in indices)
        if unknown:
            raise cli.UsageError("Label(s) for block index %s, which the outline does not have (indices: %s)." % (
                ", ".join(str(u) for u in unknown), ", ".join(str(i) for i in indices)))
        missing = [i for i in indices if i not in labelled]
        if missing:
            raise cli.UsageError(
                "Outline block(s) %s have no label. Label every block; use 'other' when none fits."
                % ", ".join(str(m) for m in missing))
        order = [i for i in indices]
        if outline.get("status") not in (None, cli.STATUS_OK):
            notes.append("the outline run ended with status %r; say so in the coverage note" % outline.get("status"))
        chrome = outline.get("chrome") or {}
        if (chrome.get("footer") or {}).get("present") and "footer" not in labelled:
            notes.append("the outline found a page footer, but it has no 'footer' label")
        if page.get("nav") == "minimal":
            nav = chrome.get("nav") or {}
            if nav.get("present"):
                notes.append(
                    "this page type usually keeps navigation minimal; the page's nav has %d link(s)"
                    % int(nav.get("link_count") or 0))
        render = outline.get("render") or {}
        if render.get("render_recommended"):
            notes.append("the outline recommended a browser render (%s); labels may miss content"
                         % "; ".join(render.get("reasons") or []))
    for ref in CHROME_BLOCKS:
        if ref in labelled:
            order.append(ref)

    raw_not_measured = labels_doc.get("not_measured") or []
    if isinstance(raw_not_measured, str):
        raw_not_measured = [raw_not_measured]
    not_measured = {str(x).strip().lower().replace("-", "_") for x in raw_not_measured}

    slots_out = []
    counts = {level: {"present": 0, "missing": 0, "not_measured": 0, "total": 0}
              for level in ("required", "recommended", "optional")}
    for slot in page["slots"]:
        level = slot["level"]
        filled_by = [ref for ref in order if set(labelled.get(ref, [])) & set(slot["any_of"])]
        slot_key = slot["id"].replace("-", "_")
        if filled_by:
            status = "present"
        elif slot_key in not_measured or any(name in not_measured for name in slot["any_of"]):
            status = "not_measured"
        else:
            status = "missing"
        counts[level]["total"] += 1
        counts[level][status] += 1
        slots_out.append({
            "id": slot["id"], "level": level, "any_of": slot["any_of"], "status": status,
            "blocks": filled_by, "why": slot.get("why"),
        })

    scored_levels = ("required", "recommended")
    total = sum(counts[l]["total"] for l in scored_levels)
    measured = sum(counts[l]["total"] - counts[l]["not_measured"] for l in scored_levels)
    present = sum(counts[l]["present"] for l in scored_levels)
    measured_share = (measured / float(total)) if total else 0.0
    show_counts = mode != "none" and measured_share >= MIN_MEASURED_SHARE
    if mode == "none":
        notes.append("scoring_mode is none: report slot status only, no 'X of N' counts")
    elif not show_counts:
        notes.append("less than 60%% of required and recommended slots were measured (%.0f%%); "
                     "show slot status only, no counts" % (measured_share * 100))

    def fmt(level: str) -> str:
        c = counts[level]
        measured_level = c["total"] - c["not_measured"]
        text = "%d of %d" % (c["present"], measured_level)
        if c["not_measured"]:
            text += " (%d not measured)" % c["not_measured"]
        return text

    summary = None
    if show_counts:
        summary = "%s: required %s; recommended %s" % (page["label"], fmt("required"), fmt("recommended"))

    sequence = [{"block": ref, "labels": labelled.get(ref, [])} for ref in order]
    first_position: Dict[str, int] = {}
    for position, ref in enumerate(order):
        for name in labelled.get(ref, []):
            first_position.setdefault(name, position)
    extra_labels = sorted({
        name for ref in order for name in labelled.get(ref, [])
        if name not in {n for s in page["slots"] for n in s["any_of"]} and name != "other"
    })

    dimensions = []
    for slot in slots_out:
        if slot["level"] == "optional":
            continue
        dimensions.append({
            "id": slot["id"], "level": slot["level"],
            "score": None if slot["status"] == "not_measured" or not show_counts else (1 if slot["status"] == "present" else 0),
            "max": 1, "weight": 1,
            "status": "not_measured" if slot["status"] == "not_measured" else ("scored" if show_counts else "na"),
            "confidence": None, "evidence": [],
        })
    version = SECTION_SETS_VERSION_PREFIX + str(sets.get("version"))
    sidecar = {
        "scoring": {
            "mode": mode, "version": version,
            "value": present if show_counts else None,
            "max": measured if show_counts else None,
            "confidence": None,
            "measured_weight": round(measured_share, 3) if show_counts else None,
        },
        "dimensions": dimensions if show_counts else [],
        "metrics": ({
            "required_sections_present": {"value": counts["required"]["present"], "unit": "count", "period": "point_in_time"},
            "required_sections_measured": {"value": counts["required"]["total"] - counts["required"]["not_measured"], "unit": "count", "period": "point_in_time"},
            "recommended_sections_present": {"value": counts["recommended"]["present"], "unit": "count", "period": "point_in_time"},
            "recommended_sections_measured": {"value": counts["recommended"]["total"] - counts["recommended"]["not_measured"], "unit": "count", "period": "point_in_time"},
        } if show_counts else {}),
    }
    return {
        "page_type": {k: page[k] for k in ("id", "label", "conversion", "nav")},
        "section_sets_version": sets.get("version"),
        "scoring_mode": mode,
        "show_counts": show_counts,
        "summary": summary,
        "counts": counts if show_counts else None,
        "measured_share": round(measured_share, 3),
        "slots": slots_out,
        "missing_required": [s["id"] for s in slots_out if s["level"] == "required" and s["status"] == "missing"],
        "missing_recommended": [s["id"] for s in slots_out if s["level"] == "recommended" and s["status"] == "missing"],
        "labels_outside_set": extra_labels,
        "sequence": sequence,
        "first_position": first_position,
        "block_count": len([r for r in order if isinstance(r, int)]),
        "evidence": {str(k): v for k, v in evidence.items()},
        "sidecar": sidecar,
        "notes": notes,
    }


def cmd_completeness(args: Any, run: cli.Run) -> int:
    try:
        labels_doc, source = cli.load_json_input(args.input, expect=dict)
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    base_dir = os.path.dirname(os.path.abspath(source["value"])) if source.get("kind") == "file" else os.getcwd()
    try:
        outline, outline_source = _load_outline(args.outline or labels_doc.get("outline"), base_dir)
        sets = _section_sets()
        result = compute_completeness(labels_doc, sets, outline, args.page_type, builder_common.scoring_mode())
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    if outline is None:
        run.note("no outline given: block labels were not checked against the extracted page")
    result["outline_source"] = outline_source
    return run.emit(result, human=lambda env: env.get("summary") or "Slot status only (no counts); see --json.")


# ---------------------------------------------------------------------------
# lint
# ---------------------------------------------------------------------------

_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_DRAFT_RE = re.compile(r"\bDRAFT\b")
_HEADING_TAG_RE = re.compile(r"^h[1-6]$")
_BLOCK_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "figcaption", "summary", "td", "th",
               "div", "section", "article", "header", "footer", "main", "aside", "nav", "figure", "dt", "dd", "label",
               "details", "form", "table", "tr", "ul", "ol", "br"]


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def lint_text(text: str, markdown: bool = True) -> Dict[str, Any]:
    """Placeholders, claims and quotes in Markdown or plain text, with the nearest heading."""
    headings: List[Tuple[int, str]] = []
    if markdown:
        offset = 0
        in_fence = False
        masked_lines = []
        for line in text.splitlines(True):
            if _FENCE_RE.match(line):
                in_fence = not in_fence
                masked_lines.append(" " * (len(line) - 1) + ("\n" if line.endswith("\n") else ""))
            elif in_fence:
                masked_lines.append(" " * (len(line) - 1) + ("\n" if line.endswith("\n") else ""))
            else:
                match = _MD_HEADING_RE.match(line.rstrip("\n"))
                if match:
                    headings.append((offset, match.group(2)))
                masked_lines.append(line)
            offset += len(line)
        scan = "".join(masked_lines)
    else:
        scan = text

    def section_at(position: int) -> Optional[str]:
        current = None
        for start, title in headings:
            if start <= position:
                current = title
            else:
                break
        return current

    placeholders = [
        {"kind": p["kind"], "text": p["text"], "line": _line_of(text, p["start"]), "section": section_at(p["start"])}
        for p in proof_patterns.find_placeholders(scan)
    ]
    claims = [
        {"type": c["type"], "text": c["text"], "line": _line_of(text, c["start"]),
         "section": section_at(c["start"]), "context": c["context"]}
        for c in proof_patterns.find_claims(scan)
    ]
    quotes = [
        {"text": q["text"], "attribution": q["attribution"], "line": _line_of(text, q["start"]),
         "section": section_at(q["start"])}
        for q in proof_patterns.find_quotes(scan)
    ]
    return {"placeholders": placeholders, "claims": claims, "quotes": quotes}


def _by_kind(items: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for item in items:
        out[item[key]] = out.get(item[key], 0) + 1
    return out


def lint_html(markup: str) -> Dict[str, Any]:
    """Text checks on the visible copy plus prototype checks on the HTML itself."""
    from _growthkit import html as html_mod
    from bs4 import NavigableString

    soup = html_mod.parse(markup)
    html_tag = soup.find("html")
    head = soup.find("head")
    title = html_mod.extract_title(soup) or ""
    meta = html_mod.extract_meta(soup)
    robots = " ".join((meta.get("robots") or {}).values()).lower()
    styles = " ".join(s.get_text() for s in soup.find_all("style"))
    external: List[str] = []
    for tag, attr in (("script", "src"), ("link", "href"), ("img", "src"), ("iframe", "src"),
                      ("source", "src"), ("video", "src"), ("audio", "src"), ("embed", "src"), ("object", "data")):
        for node in soup.find_all(tag):
            value = str(node.get(attr) or "").strip()
            if tag == "link":
                rel = " ".join(node.get("rel") or []).lower()
                if not any(word in rel for word in ("stylesheet", "preload", "icon", "modulepreload", "prefetch")):
                    continue
            if re.match(r"^(?:https?:)?//", value, re.I):
                external.append("<%s %s=%s>" % (tag, attr, value[:120]))
    for match in re.finditer(r"(?:@import\s+(?:url\()?|url\()\s*['\"]?((?:https?:)?//[^'\")\s]+)", styles, re.I):
        external.append("css url(%s)" % match.group(1)[:120])
    inline_scripts = [s for s in soup.find_all("script") if not s.get("src")
                      and str(s.get("type") or "").lower() not in ("application/ld+json",)]
    forms = []
    for form in soup.find_all("form"):
        action = str(form.get("action") or "").strip()
        forms.append({"action": action or None, "live_action": bool(action) and action not in ("#", "")})
    images = soup.find_all("img")
    missing_alt = sum(1 for img in images if not img.has_attr("alt"))
    controls = [c for c in soup.find_all(["input", "select", "textarea"])
                if str(c.get("type") or "").lower() not in ("hidden", "submit", "button", "image", "reset")]
    unlabelled = 0
    for control in controls:
        cid = control.get("id")
        has_label = bool(cid and soup.find("label", attrs={"for": cid})) or control.find_parent("label") is not None
        if not has_label and not control.get("aria-label") and not control.get("aria-labelledby"):
            unlabelled += 1
    empty_controls = 0
    for node in soup.find_all(["a", "button"]):
        text = html_mod.clean_text(node, collapse=True)
        if not text and not node.get("aria-label") and not node.find("img", alt=True):
            empty_controls += 1
    sections = []
    for node in soup.find_all(attrs={"data-section": True}):
        sections.append(str(node.get("data-section")))

    # Visible copy: hidden nodes, scripts and styles removed. Alt text is kept
    # because logo and screenshot slots are usually <img alt="[LOGO: ...]">.
    visible = html_mod.parse(markup)
    html_mod.strip_invisible(visible)
    for img in visible.find_all("img"):
        alt = str(img.get("alt") or "").strip()
        img.replace_with(" %s " % alt if alt else " ")
    body = visible.body or visible
    for node in body.find_all(_BLOCK_TAGS):
        if _HEADING_TAG_RE.match(node.name):
            node.insert(0, NavigableString("\n" + "#" * int(node.name[1]) + " "))
        else:
            node.insert(0, NavigableString("\n"))
        node.append(NavigableString("\n"))
    for node in body.find_all(attrs={"data-section": True}):
        node.insert(0, NavigableString("\n###### section: %s\n" % node.get("data-section")))
    deduped: List[str] = []
    for raw_line in body.get_text("").split("\n"):
        line = " ".join(raw_line.split())
        if line and (not deduped or deduped[-1] != line):
            deduped.append(line)
    copy_text = "\n".join(deduped)
    text_result = lint_text(copy_text, markdown=True)
    visible_text = html_mod.clean_text(body)
    h1_count = len(soup.find_all("h1"))
    levels = [int(h.name[1]) for h in soup.find_all(re.compile(r"^h[1-6]$"))]
    skips = sum(1 for a, b in zip(levels, levels[1:]) if b - a > 1)

    must_fix: List[str] = []
    should_fix: List[str] = []
    if not _DRAFT_RE.search(visible_text):
        must_fix.append("no visible 'DRAFT' label on the page")
    if "DRAFT" not in title:
        must_fix.append("the <title> does not contain 'DRAFT'")
    if "noindex" not in robots:
        must_fix.append("missing <meta name=\"robots\" content=\"noindex\">")
    if external:
        must_fix.append("%d external resource(s); the prototype must be one self-contained file" % len(external))
    live_forms = [f for f in forms if f["live_action"]]
    if live_forms:
        must_fix.append("%d form(s) post to a live action; drafts must not submit data" % len(live_forms))
    if not meta.get("viewport"):
        must_fix.append("missing <meta name=\"viewport\">")
    if html_tag is None or not html_tag.get("lang"):
        must_fix.append("missing lang attribute on <html>")
    if h1_count != 1:
        must_fix.append("%d <h1> elements; use exactly one" % h1_count)
    if missing_alt:
        should_fix.append("%d image(s) without alt text" % missing_alt)
    if unlabelled:
        should_fix.append("%d form control(s) without a label" % unlabelled)
    if empty_controls:
        should_fix.append("%d link(s) or button(s) without text or aria-label" % empty_controls)
    if skips:
        should_fix.append("%d heading level skip(s) (for example h2 to h4)" % skips)
    if "@media" not in styles:
        should_fix.append("no @media rule; check the layout at 390 px width")
    if ":focus" not in styles:
        should_fix.append("no :focus or :focus-visible style; keyboard users need a visible focus")
    if ("transition" in styles or "@keyframes" in styles or "animation" in styles) and "prefers-reduced-motion" not in styles:
        should_fix.append("motion without a prefers-reduced-motion rule")
    if inline_scripts:
        should_fix.append("%d inline script(s); keep the prototype working without JavaScript" % len(inline_scripts))
    if head is None:
        should_fix.append("no <head> element")

    text_result["html"] = {
        "title": title,
        "has_draft_label": bool(_DRAFT_RE.search(visible_text)),
        "noindex": "noindex" in robots,
        "viewport": meta.get("viewport"),
        "lang": html_tag.get("lang") if html_tag is not None else None,
        "h1_count": h1_count,
        "heading_levels": levels[:60],
        "data_sections": sections,
        "external_resources": external[:20],
        "inline_scripts": len(inline_scripts),
        "forms": forms,
        "images": len(images),
        "images_missing_alt": missing_alt,
        "unlabelled_controls": unlabelled,
        "empty_links_or_buttons": empty_controls,
        "has_media_query": "@media" in styles,
        "has_focus_style": ":focus" in styles,
        "bytes": len(markup.encode("utf-8")),
        "must_fix": must_fix,
        "should_fix": should_fix,
    }
    text_result["visible_words"] = len(visible_text.split())
    return text_result


def cmd_lint(args: Any, run: cli.Run) -> int:
    try:
        source = cli.resolve_input(args.input, allow_url=False, allow_file=True, allow_stdin=True)
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    text = source["text"] or ""
    if not text.strip():
        return run.fail(cli.STATUS_NOTHING, "The file is empty.")
    name = (source.get("value") or "").lower()
    is_html = name.endswith((".html", ".htm")) or bool(re.match(r"\s*(?:<!doctype html|<html)", text, re.I))
    kind = "html" if is_html else ("markdown" if name.endswith((".md", ".markdown")) or source["kind"] == "stdin" else "text")
    result = lint_html(text) if is_html else lint_text(text, markdown=(kind == "markdown"))
    result["file"] = source.get("value")
    result["kind"] = kind
    result["counts"] = {
        "placeholders": len(result["placeholders"]),
        "placeholders_by_kind": _by_kind(result["placeholders"], "kind"),
        "claims": len(result["claims"]),
        "claims_by_type": _by_kind(result["claims"], "type"),
        "quotes": len(result["quotes"]),
    }
    if result["claims"] or result["quotes"]:
        run.note("each claim and quote must trace to proof the user supplied (cite it) or become a [PLACEHOLDER]")
    if is_html and result["html"]["must_fix"]:
        run.note("fix every html.must_fix item before handing over the prototype")
    return run.emit(result, human=lambda env: json.dumps(env.get("counts"), indent=2))


# ---------------------------------------------------------------------------
# test-plan
# ---------------------------------------------------------------------------


def _rate(value: Any, field: str) -> Optional[float]:
    """'3.8%' -> 0.038, '0.038' -> 0.038, '3.8' -> 0.038 (values of 1 or more are percents)."""
    if value is None:
        return None
    text = str(value).strip()
    try:
        number = cli.to_number(text.replace("%", ""), field=field)
    except cli.CoercionError as exc:
        raise cli.UsageError(str(exc))
    if number is None:
        return None
    if "%" in text or number >= 1:
        number = number / 100.0
    return number


def cmd_test_plan(args: Any, run: cli.Run) -> int:
    from _growthkit import stats

    try:
        baseline = _rate(args.baseline, "--baseline")
        mde = _rate(args.mde, "--mde")
        if baseline is None or not 0 < baseline < 1:
            raise cli.UsageError("--baseline must be a rate between 0%% and 100%%, got %r" % args.baseline)
        if mde is None or mde <= 0:
            raise cli.UsageError("--mde must be a positive relative change such as 20%%, got %r" % args.mde)
        weekly = None
        source = None
        if args.weekly_visitors is not None:
            weekly = cli.to_number(args.weekly_visitors, field="--weekly-visitors", minimum=1)
            source = "weekly_visitors"
        elif args.monthly_visitors is not None:
            monthly = cli.to_number(args.monthly_visitors, field="--monthly-visitors", minimum=1)
            weekly = monthly / 4.33 if monthly is not None else None
            source = "monthly_visitors / 4.33"
    except (cli.UsageError, cli.CoercionError) as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    max_weeks = args.max_weeks
    try:
        n_per_arm = stats.sample_size_per_arm(baseline, mde, relative=True)
        total = n_per_arm * args.arms
        required_weekly = total / max_weeks
        plan = None
        if weekly is not None:
            plan = stats.plan_test(baseline, weekly, mde, relative=True, arms=args.arms, max_weeks=max_weeks)
    except ValueError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    if plan is None:
        decision = "traffic_unknown"
        run.note("traffic unknown: state the weekly traffic an A/B test would need (required_weekly_visitors)")
    elif plan["feasible"]:
        decision = "ab_test"
    else:
        decision = "ship_and_measure"
    data = {
        "inputs": {"baseline": baseline, "mde_relative": mde, "weekly_visitors": weekly,
                   "weekly_visitors_source": source, "arms": args.arms, "max_weeks": max_weeks,
                   "alpha": stats.DEFAULT_ALPHA, "power": stats.DEFAULT_POWER, "two_sided": True},
        "decision": decision,
        "n_per_arm": int(round(n_per_arm)) if n_per_arm == n_per_arm else None,
        "total_visitors": int(round(total)),
        "required_weekly_visitors": int(round(required_weekly)),
        "duration_weeks": max(2, plan["weeks_rounded"]) if plan and plan["feasible"] else None,
        "plan": plan,
    }
    return run.emit(data, human=lambda env: "%s: n per arm %s, needs %s visitors/week for %s weeks" % (
        env["decision"], env["n_per_arm"], env["required_weekly_visitors"], env["inputs"]["max_weeks"]))


# ---------------------------------------------------------------------------
# benchmarks
# ---------------------------------------------------------------------------

_ROW_KEYS = ("id", "metric", "metric_label", "definition", "unit", "period", "segment", "p25", "median",
             "p75", "mean", "value", "value_note", "source_name", "source_url", "year", "data_period",
             "verified", "verified_on")


def cmd_benchmarks(args: Any, run: cli.Run) -> int:
    try:
        with open(builder_common.BENCHMARKS_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        return run.fail(cli.STATUS_USAGE, "Cannot read %s: %s (reinstall the skill)" % (builder_common.BENCHMARKS_PATH, exc))
    metrics = args.metric or list(DEFAULT_METRICS)
    rows = []
    for row in data.get("rows") or []:
        if row.get("metric") not in metrics:
            continue
        if not args.include_unverified and row.get("verified") is False:
            continue
        motion = ((row.get("segment") or {}).get("motion") or "all")
        if args.motion and motion not in (args.motion, "all"):
            continue
        rows.append({key: row.get(key) for key in _ROW_KEYS if key in row})
    if not rows:
        return run.fail(cli.STATUS_NOTHING, "No benchmark rows for metric(s) %s%s." % (
            ", ".join(metrics), " and motion %s" % args.motion if args.motion else ""))
    run.note("cite value, source, year and segment; benchmarks are context, never a score")
    return run.emit({"benchmarks_last_verified": data.get("last_verified"), "rows": rows},
                    human=lambda env: "\n".join(
                        "%s: %s %s (%s %s)" % (r["id"], r.get("median") if r.get("median") is not None else r.get("value") if r.get("value") is not None else r.get("mean"),
                                               r.get("unit"), r.get("source_name"), r.get("year"))
                        for r in env["rows"]))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def build_parser() -> cli.ArgumentParser:
    parser = cli.ArgumentParser(
        prog="blueprint_tools.py",
        description="Deterministic helpers for saas-landing-builder (section sets, completeness, lint, test plans, benchmarks).",
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + __import__("_growthkit").__version__)
    sub = parser.add_subparsers(dest="command")

    def common(p: Any) -> None:
        p.add_argument("--json", action="store_true", help="print only JSON to stdout")
        p.add_argument("--out", metavar="PATH", help="also save the JSON result to PATH")

    p = sub.add_parser("sections", help="section set for a page type, or the list of page types")
    p.add_argument("--page-type", help="page type id, for example plg-homepage")
    common(p)

    p = sub.add_parser("completeness", help="count block labels against the page type's section set")
    p.add_argument("input", nargs="?", help="labels JSON file, or '-' for stdin")
    p.add_argument("--outline", help="page_structure_analyzer.py --out file to check labels against")
    p.add_argument("--page-type", help="override page_type in the labels file")
    common(p)

    p = sub.add_parser("lint", help="placeholders, claim candidates and prototype checks in a draft")
    p.add_argument("input", nargs="?", help=".md, .html or .txt file, or '-' for stdin")
    common(p)

    p = sub.add_parser("test-plan", help="A/B test sizing or ship-and-measure, from the shared stats helper")
    p.add_argument("--baseline", required=True, help="baseline conversion rate, for example 3.8%% or 0.038")
    p.add_argument("--weekly-visitors", help="visitors per week reaching the page")
    p.add_argument("--monthly-visitors", help="visitors per month (divided by 4.33)")
    p.add_argument("--mde", default="20%", help="minimum detectable relative effect (default: 20%%)")
    p.add_argument("--arms", type=int, default=2, choices=range(2, 6), metavar="2-5", help="variants including control (default: 2)")
    p.add_argument("--max-weeks", type=float, default=4.0, help="longest acceptable test (default: 4)")
    common(p)

    p = sub.add_parser("benchmarks", help="landing-page benchmark rows with source and year")
    p.add_argument("--metric", action="append", help="metric key; repeatable (default: landing_page_conversion, "
                   "visitor_to_signup, form_view_to_completion)")
    p.add_argument("--motion", help="segment motion filter, for example free_trial or freemium")
    p.add_argument("--include-unverified", action="store_true", help="also list rows marked verified=false")
    common(p)
    return parser


COMMANDS = {
    "sections": cmd_sections,
    "completeness": cmd_completeness,
    "lint": cmd_lint,
    "test-plan": cmd_test_plan,
    "benchmarks": cmd_benchmarks,
}


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_usage(sys.stderr)
        json_mode = "--json" in (sys.argv[1:] if argv is None else argv)
        if json_mode:
            print(cli.to_json({"tool": TOOL, "status": cli.STATUS_USAGE,
                               "errors": ["No subcommand. Use one of: %s" % ", ".join(COMMANDS)], "notes": []}))
        return cli.EXIT_USAGE
    run = cli.Run(TOOL + " " + args.command, args)
    builder_common.ensure_private_reports_dir(getattr(args, "out", None), run.log)
    try:
        return COMMANDS[args.command](args, run)
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))


if __name__ == "__main__":
    sys.exit(main())
