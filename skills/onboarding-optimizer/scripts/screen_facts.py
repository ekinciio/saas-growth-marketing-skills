#!/usr/bin/env python3
"""Facts from first-run screens: what each screen asks, offers and loads.

For saved or rendered HTML of in-app onboarding screens (captured with the
browser fallback or saved by the user), and for public pages a new user sees
before or right after signup (a try-without-signup app, the first signup
step, a "get started" page). One or more inputs; each becomes one screen.

Per screen it reports, without judging:
  - title, headings, visible word count and the first part of the main text
  - CTAs and forms (growthkit html.page_facts), plus input controls that
    sit outside any <form> (single-page apps rarely use <form>)
  - progress markers: role=progressbar, <progress>, aria-current="step",
    "Step 2 of 5" and "3 of 5 completed" text
  - skip and defer controls ("Skip", "Do this later", "Not now", ...)
  - controls that mention templates, sample data, examples or starting blank
  - video embeds
  - onboarding and analytics tools loaded by the page (script hosts and
    inline snippets): Appcues, Pendo, Userpilot, Chameleon, Intercom,
    PostHog, Mixpanel, Amplitude, Segment, GA4 and others. Detection works
    on JavaScript shells too, so a static fetch of app.example.com can still
    say which analytics tool to export from.

Usage (from the user's project folder):
    python3 screen_facts.py https://app.example.com/ --json
    python3 screen_facts.py growth-reports/.cache/2026-10-24-step1-rendered.html \\
        growth-reports/.cache/2026-10-24-step2-rendered.html --json

Exit codes (growthkit cli): 0 every screen read, 4 some screens failed,
3 every screen blocked or unreachable, 5 nothing to analyze (every screen is
an empty page or a JavaScript shell; tool detection is still returned),
2 usage error.
"""

from __future__ import annotations

import os
import re
import sys
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _growthkit import cli  # noqa: E402
from _growthkit import html as gk_html  # noqa: E402

TOOL = "screen_facts"
MAX_SCREENS = 12
MAIN_TEXT_CHARS = 1500

# ---------------------------------------------------------------------------
# Tool detection: (name, category, script host suffixes, inline snippet regex)
# Hosts are matched as a suffix of the script host; the inline pattern is
# matched against inline <script> text only.
# ---------------------------------------------------------------------------

TOOLS: List[Tuple[str, str, Tuple[str, ...], Optional[str]]] = [
    ("Appcues", "in_app_guidance", ("appcues.com", "appcues.net"), r"\bAppcues\.(?:identify|page|show)\b"),
    ("Pendo", "in_app_guidance", ("pendo.io",), r"\bpendo\.initialize\b"),
    ("Userpilot", "in_app_guidance", ("userpilot.io",), r"\buserpilot\.(?:identify|reload)\b"),
    ("Chameleon", "in_app_guidance", ("chameleon.io",), r"\bchmln\.(?:identify|track)\b"),
    ("WalkMe", "in_app_guidance", ("walkme.com",), None),
    ("Whatfix", "in_app_guidance", ("whatfix.com",), None),
    ("UserGuiding", "in_app_guidance", ("userguiding.com",), None),
    ("Userflow", "in_app_guidance", ("userflow.com",), r"\buserflow\.(?:init|identify)\b"),
    ("Product Fruits", "in_app_guidance", ("productfruits.com",), r"\bproductFruits\b"),
    ("Gainsight PX", "in_app_guidance", ("aptrinsic.com",), r"\baptrinsic\b"),
    ("Userlane", "in_app_guidance", ("userlane.com",), None),
    ("Stonly", "in_app_guidance", ("stonly.com",), r"\bStonlyWidget\b"),
    ("Frigade", "in_app_guidance", ("frigade.com",), None),
    ("Intercom", "messaging", ("intercom.io", "intercomcdn.com"), r"\bintercomSettings\b"),
    ("PostHog", "analytics", ("posthog.com",), r"\bposthog\.init\s*\("),
    ("Mixpanel", "analytics", ("mxpnl.com", "mixpanel.com"), r"\bmixpanel\.init\s*\("),
    ("Amplitude", "analytics", ("amplitude.com",), r"\bamplitude\.(?:init|getInstance)\b"),
    ("Segment", "analytics", ("segment.com", "segment.io"), r"\banalytics\.load\s*\("),
    ("Heap", "analytics", ("heapanalytics.com", "heap-api.com"), r"\bheap\.load\s*\("),
    ("RudderStack", "analytics", ("rudderlabs.com", "rudderstack.com"), r"\brudderanalytics\b"),
    ("Google Analytics 4", "analytics", (), r"gtag\(\s*['\"]config['\"]\s*,\s*['\"]G-"),
    ("Google Tag Manager", "tag_manager", (), r"googletagmanager\.com/gtm\.js|['\"]GTM-[A-Z0-9]+['\"]"),
    ("Hotjar", "session_replay", ("hotjar.com",), r"\b_hjSettings\b"),
    ("FullStory", "session_replay", ("fullstory.com",), r"\b_fs_org\b"),
    ("LogRocket", "session_replay", ("logrocket.io", "lr-ingest.io", "lr-in.com"), r"\bLogRocket\.init\b"),
    ("Microsoft Clarity", "session_replay", ("clarity.ms",), r"clarity\.ms/tag"),
]
_GTAG_SRC_RE = re.compile(r"googletagmanager\.com/gtag/js\?id=G-", re.I)
_GTM_SRC_RE = re.compile(r"googletagmanager\.com/gtm\.js", re.I)

# ---------------------------------------------------------------------------
# Text facts (closed lists of control labels; they record what a control
# says, they do not judge the screen)
# ---------------------------------------------------------------------------

SKIP_LABEL_RE = re.compile(
    r"^(?:skip(?: (?:this|this step|for now|tour|the tour|setup|intro|onboarding|to (?:the )?"
    r"(?:app|dashboard|editor)))?|(?:i'?ll )?do (?:this|it) later|set (?:this |it )?up later|decide later|"
    r"maybe later|later|not now|remind me later|no,? thanks|dismiss|close tour|end tour|"
    r"(?:i'?ll )?explore on my own|continue without|"
    r"atla|daha sonra|sonra|şimdi değil|omitir|más tarde|überspringen|später|passer|plus tard|"
    r"ignorer|salta|più tardi)\b[.!]?$",
    re.I,
)
STARTER_LABEL_RE = re.compile(
    r"\btemplates?\b|\bsample (?:data|project|workspace|file|dashboard)s?\b|"
    r"\bexample (?:project|data|workspace|board|file)s?\b|\bdemo (?:data|project|workspace)\b|"
    r"\bstart from scratch\b|\bblank (?:canvas|page|project|document|diagram|board|file)\b|"
    r"\bimport\b|\bgenerate\b|\bdescribe (?:what|your)\b",
    re.I,
)
STEP_OF_RE = re.compile(r"\bstep\s+(\d{1,2})\s*(?:of|/)\s*(\d{1,2})\b", re.I)
COUNTER_RE = re.compile(r"\b(\d{1,2})\s*(?:of|/)\s*(\d{1,2})\s+(?:steps?|tasks?|items?|completed?|done)\b", re.I)
PERCENT_DONE_RE = re.compile(r"\b(\d{1,3})\s*%\s*(?:complete|completed|done)\b", re.I)
VIDEO_HOST_RE = re.compile(r"youtube\.com|youtube-nocookie\.com|youtu\.be|vimeo\.com|wistia\.(?:com|net)|"
                           r"loom\.com|vidyard\.com", re.I)


def _host_matches(host: str, suffixes: Tuple[str, ...]) -> bool:
    host = host.lower()
    return any(host == s or host.endswith("." + s) for s in suffixes)


def detect_tools(soup: Any) -> List[Dict[str, str]]:
    """Onboarding, analytics and replay tools from <script src> hosts and inline snippets."""
    found: "OrderedDict[str, Dict[str, str]]" = OrderedDict()
    inline_parts: List[str] = []
    for script in soup.find_all("script"):
        src = script.get("src")
        if src:
            src = str(src)
            match = re.match(r"^(?:https?:)?//([^/:?#]+)", src, re.I)
            host = match.group(1) if match else ""
            for name, category, hosts, _inline in TOOLS:
                if host and _host_matches(host, hosts) and name not in found:
                    found[name] = {"tool": name, "category": category, "via": "script host %s" % host}
            if _GTAG_SRC_RE.search(src) and "Google Analytics 4" not in found:
                found["Google Analytics 4"] = {"tool": "Google Analytics 4", "category": "analytics",
                                               "via": "gtag.js with a G- id"}
            if _GTM_SRC_RE.search(src) and "Google Tag Manager" not in found:
                found["Google Tag Manager"] = {"tool": "Google Tag Manager", "category": "tag_manager",
                                               "via": "gtm.js"}
        else:
            kind = str(script.get("type") or "").lower()
            if "ld+json" not in kind:
                inline_parts.append(script.get_text() or "")
    inline = "\n".join(inline_parts)
    for name, category, hosts, pattern in TOOLS:
        if name in found:
            continue
        if pattern and re.search(pattern, inline):
            found[name] = {"tool": name, "category": category, "via": "inline snippet"}
        elif hosts and any(re.search(r"//(?:[\w-]+\.)*" + re.escape(h) + r"\b", inline, re.I) for h in hosts):
            found[name] = {"tool": name, "category": category, "via": "inline loader for %s" % hosts[0]}
    return list(found.values())


def _control_text(tag: Any) -> str:
    if tag.name == "input":
        text = str(tag.get("value") or "")
    else:
        text = gk_html.clean_text(tag)
    if not text:
        text = str(tag.get("aria-label") or tag.get("title") or "")
    return gk_html.normalize_space(text)


def onboarding_signals(markup: str) -> Dict[str, Any]:
    """The first-run facts page_facts does not collect. Hidden nodes are ignored."""
    soup = gk_html.parse(markup)
    tools = detect_tools(soup)
    gk_html.strip_invisible(soup, hidden=True, non_rendered=False)
    videos = sum(1 for frame in soup.find_all("iframe") if VIDEO_HOST_RE.search(str(frame.get("src") or "")))
    videos += len(soup.find_all("video"))
    gk_html.strip_invisible(soup, hidden=False, non_rendered=True)

    loose: List[Dict[str, Any]] = []
    for control in soup.find_all(["input", "select", "textarea"]):
        if control.find_parent("form") is not None:
            continue
        ctype = str(control.get("type") or "text").lower() if control.name == "input" else control.name
        if ctype in ("hidden", "submit", "button", "image", "reset"):
            continue
        loose.append(OrderedDict([
            ("type", ctype),
            ("label", gk_html.normalize_space(str(control.get("aria-label") or control.get("placeholder")
                                                  or control.get("name") or ""))[:120]),
            ("required", control.has_attr("required") or str(control.get("aria-required") or "").lower() == "true"),
        ]))
    editable = [gk_html.normalize_space(str(tag.get("aria-label") or tag.get("data-placeholder") or ""))[:120]
                for tag in soup.find_all(attrs={"contenteditable": re.compile(r"^(?:true|)$", re.I)})]
    role_counts = OrderedDict()
    for role in ("radio", "checkbox", "switch", "option", "tab", "progressbar", "dialog"):
        count = len(soup.find_all(attrs={"role": role}))
        if count:
            role_counts[role] = count

    controls = soup.find_all(["button", "a"]) + soup.find_all(attrs={"role": "button"}) + \
        soup.find_all("input", attrs={"type": re.compile(r"^(?:button|submit)$", re.I)})
    seen = set()
    labels: List[str] = []
    for tag in controls:
        if id(tag) in seen:
            continue
        seen.add(id(tag))
        text = _control_text(tag)
        if text and len(text) <= 80:
            labels.append(text)
    labels = gk_html.dedupe_texts(labels)
    skip = [t for t in labels if len(t) <= 40 and SKIP_LABEL_RE.match(t.strip())]
    starter = [t for t in labels if STARTER_LABEL_RE.search(t)][:20]

    text = gk_html.clean_text(soup.body or soup)
    step_of = ["step %s of %s" % m for m in STEP_OF_RE.findall(text)]
    counters = ["%s of %s %s" % (a, b, "") for a, b in COUNTER_RE.findall(text)]
    counters = [c.strip() for c in counters]
    percent_done = ["%s%% complete" % m for m in PERCENT_DONE_RE.findall(text)]
    progressbars = []
    for tag in soup.find_all(attrs={"role": "progressbar"}) + soup.find_all("progress"):
        progressbars.append(OrderedDict([
            ("now", tag.get("aria-valuenow") or tag.get("value")),
            ("max", tag.get("aria-valuemax") or tag.get("max")),
            ("label", gk_html.normalize_space(str(tag.get("aria-label") or tag.get("aria-valuetext") or ""))[:80]),
        ]))
    return OrderedDict([
        ("tools", tools),
        ("controls_outside_forms", loose[:40]),
        ("controls_outside_forms_count", len(loose)),
        ("required_outside_forms", sum(1 for c in loose if c["required"])),
        ("editable_regions", [e for e in editable if e][:10]),
        ("editable_region_count", len(editable)),
        ("role_counts", role_counts),
        ("progress", OrderedDict([
            ("progressbars", progressbars[:10]),
            ("aria_current_step", len(soup.find_all(attrs={"aria-current": "step"}))),
            ("step_of_text", gk_html.dedupe_texts(step_of)[:10]),
            ("counter_text", gk_html.dedupe_texts(counters)[:10]),
            ("percent_complete_text", gk_html.dedupe_texts(percent_done)[:10]),
        ])),
        ("skip_controls", skip[:20]),
        ("starter_content_controls", starter),
        ("video_embeds", videos),
        ("control_labels", labels[:60]),
        ("control_label_count", len(labels)),
    ])


def screen_outcome(facts: Dict[str, Any], signals: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """ok / nothing_to_analyze for one screen.

    App screens are sparse by nature (an editor, a one-field signup step), so
    a rendered screen with few words but real controls is a screen, not a
    JavaScript shell. Only a page with no text and no controls, or a shell
    with neither controls nor forms, is nothing to analyze.
    """
    words = int(facts.get("word_count") or 0)
    controls = signals.get("control_label_count", 0) + signals.get("controls_outside_forms_count", 0) + \
        signals.get("editable_region_count", 0) + len([f for f in facts.get("forms") or [] if not f.get("hidden")])
    if words == 0 and controls == 0:
        return "nothing_to_analyze", "The screen has no visible text and no controls to analyze."
    if facts.get("is_js_shell") and controls < 3:
        return "nothing_to_analyze", ("The HTML is a JavaScript shell (%d visible words, %d controls). Render the "
                                      "page in a browser and pass the saved HTML file." % (words, controls))
    if facts.get("is_js_shell"):
        return "ok", ("Few visible words (%d) but %d controls: read as a rendered app screen; judge layout from "
                      "a screenshot." % (words, controls))
    if words < 150 and not (facts.get("headings") or {}).get("h1"):
        return "ok", "Sparse screen: %d visible words and no <h1> (normal for app screens)." % words
    return "ok", None


def screen_from_markup(markup: str, url: Optional[str], label: str) -> Dict[str, Any]:
    facts = gk_html.page_facts(markup, url, text_chars=MAIN_TEXT_CHARS, max_ctas=30)
    signals = onboarding_signals(markup)
    status, message = screen_outcome(facts, signals)
    screen = OrderedDict([
        ("label", label), ("url", url), ("status", status),
        ("message", message),
        ("title", facts.get("title")), ("lang", facts.get("lang")),
        ("headings", OrderedDict((k, v[:8]) for k, v in (facts.get("headings") or {}).items() if v)),
        ("word_count", facts.get("word_count")), ("main_text", facts.get("main_text")),
        ("main_text_truncated", facts.get("main_text_truncated")),
        ("ctas", [OrderedDict((k, c.get(k)) for k in ("text", "intent", "zone", "href") if k in c)
                  for c in (facts.get("ctas") or [])[:20]]),
        ("forms", [OrderedDict([
            ("kind", f.get("kind")), ("zone", f.get("zone")), ("questions", f.get("questions")),
            ("required_count", f.get("required_count")), ("submit_text", f.get("submit_text")),
            ("has_password", f.get("has_password")),
            ("fields", [OrderedDict((k, q.get(k)) for k in ("type", "label", "required", "options"))
                        for q in (f.get("fields") or [])])])
            for f in (facts.get("forms") or []) if not f.get("hidden")]),
        ("embedded_forms", facts.get("embedded_forms")),
        ("is_js_shell", facts.get("is_js_shell")),
    ])
    screen.update(signals)
    screen["page_notes"] = facts.get("notes")
    return screen


def screen_from_input(value: str, timeout: float, source_url: Optional[str]) -> Dict[str, Any]:
    source = cli.resolve_input(value, allow_url=True, allow_file=True, allow_stdin=False)
    if source["kind"] == "file":
        label = os.path.basename(value)
        markup = source["text"] or ""
        if not markup.strip():
            return OrderedDict([("label", label), ("url", source_url), ("status", "nothing_to_analyze"),
                                ("message", "The file is empty.")])
        screen = screen_from_markup(markup, source_url, label)
        screen["source"] = OrderedDict([("kind", "file"), ("path_name", label)])
        return screen
    from _growthkit import http as gk_http  # imported only for URLs (needs requests)

    result = gk_http.fetch(value, kind="html", timeout=timeout)
    status, message = cli.fetch_outcome(result)
    url = result.get("final_url") or result.get("url") or value
    fetch_info = OrderedDict((k, v) for k, v in gk_http.summarize(result).items()
                             if k in ("status", "http_status", "final_url", "error", "bot_protection",
                                      "is_js_shell", "elapsed_ms"))
    markup = result.get("html")
    if status == cli.STATUS_OK and markup:
        screen = screen_from_markup(markup, url, value)
    elif markup and status == cli.STATUS_NOTHING:
        # JS shell: no screen facts, but the loaded tools are still facts.
        soup = gk_html.parse(markup)
        screen = OrderedDict([("label", value), ("url", url), ("status", "nothing_to_analyze"),
                              ("message", message), ("tools", detect_tools(soup)),
                              ("title", gk_html.extract_title(soup))])
    else:
        screen = OrderedDict([("label", value), ("url", url),
                              ("status", status if status in (cli.STATUS_BLOCKED, cli.STATUS_UNREACHABLE,
                                                              cli.STATUS_NOTHING, cli.STATUS_PARTIAL)
                               else "unreachable"),
                              ("message", message)])
    screen["source"] = OrderedDict([("kind", "url"), ("fetch", fetch_info)])
    return screen


def overall_status(screens: List[Dict[str, Any]]) -> str:
    statuses = [s.get("status") for s in screens]
    if statuses and all(s == "ok" for s in statuses):
        return cli.STATUS_OK
    if any(s == "ok" for s in statuses):
        return cli.STATUS_PARTIAL
    if any(s in (cli.STATUS_BLOCKED, cli.STATUS_UNREACHABLE) for s in statuses):
        return cli.STATUS_BLOCKED if any(s == cli.STATUS_BLOCKED for s in statuses) else cli.STATUS_UNREACHABLE
    return cli.STATUS_NOTHING


def _human(env: Dict[str, Any]) -> str:
    lines = []
    for screen in env.get("screens") or []:
        lines.append("== %s [%s]" % (screen.get("label"), screen.get("status")))
        if screen.get("message"):
            lines.append("   " + screen["message"])
        if screen.get("title"):
            lines.append("   title: %s" % screen["title"])
        for key in ("controls_outside_forms_count", "skip_controls", "starter_content_controls", "video_embeds"):
            if key in screen:
                lines.append("   %s: %s" % (key, screen[key]))
        if screen.get("progress"):
            lines.append("   progress: %s" % dict(screen["progress"]))
        if screen.get("tools"):
            lines.append("   tools: %s" % ", ".join(t["tool"] for t in screen["tools"]))
    lines += ["Note: " + n for n in env.get("notes") or []]
    lines += ["Error: " + e for e in env.get("errors") or []]
    return "\n".join(lines)


def build_parser() -> cli.ArgumentParser:
    parser = cli.ArgumentParser(
        prog="screen_facts.py",
        description="Facts from first-run screens (saved or rendered HTML, or public URLs).",
    )
    parser.add_argument("inputs", nargs="+", help="screen URLs or saved HTML files, in flow order")
    parser.add_argument("--json", action="store_true", help="print only JSON to stdout")
    parser.add_argument("--out", metavar="PATH", help="also save the JSON result to PATH")
    parser.add_argument("--source-url", help="the page URL a single saved HTML file came from")
    parser.add_argument("--timeout", type=cli._positive_float, default=15.0, metavar="SECONDS",
                        help="network timeout per request (default: 15)")
    parser.add_argument("--version", action="version", version="%(prog)s " + cli.__version__)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    run = cli.Run(TOOL, args)
    if len(args.inputs) > MAX_SCREENS:
        return run.fail(cli.STATUS_USAGE, "At most %d screens per run." % MAX_SCREENS)
    if args.source_url and len(args.inputs) != 1:
        return run.fail(cli.STATUS_USAGE, "--source-url needs exactly one saved HTML file.")
    screens = []
    for position, value in enumerate(args.inputs, 1):
        try:
            screen = screen_from_input(value, args.timeout, args.source_url)
        except cli.UsageError as exc:
            return run.fail(cli.STATUS_USAGE, "input %d: %s" % (position, exc))
        screen["position"] = position
        if screen.get("status") != "ok":
            run.error("%s: %s" % (screen.get("label"), screen.get("message") or screen.get("status")))
        screens.append(screen)
    status = overall_status(screens)
    run.note("Tool detection reads script hosts and inline snippets in this HTML only; tools injected later "
             "by a tag manager or after login do not appear in a static fetch.")
    if any(s.get("source", {}).get("kind") == "url" for s in screens):
        run.note("URLs were fetched logged out with a static request: in-app screens behind a login are not "
                 "visible this way. Save rendered HTML or screenshots of those screens instead.")
    return run.emit({"screens": screens, "screen_count": len(screens)}, status=status, human=_human)


if __name__ == "__main__":
    sys.exit(main())
