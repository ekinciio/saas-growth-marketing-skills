"""HTML helpers: readable text, hidden-node removal and page facts.

Everything here parses static HTML with the stdlib-backed 'html.parser'
(no lxml). The functions collect facts; judging them is the model's job.

Main entry points:
    clean_text(node_or_str)    text with a space at every element boundary,
                               so "agents<br>Think<span>together</span>"
                               reads "agents Think together", never
                               "agentsThinktogether"
    strip_invisible(soup)      remove hidden and non-rendered nodes in place
    js_shell_signals(markup)   cheap regex check for client-rendered shells
    page_facts(markup, url)    one JSON-serializable dict of page facts
    decode_bytes(content, ...) bytes -> str honouring BOM, header and
                               <meta charset>
"""

from __future__ import annotations

import html as stdlib_html
import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

from .cli import import_or_exit

import_or_exit("bs4", "beautifulsoup4")
from bs4 import BeautifulSoup, Comment, NavigableString, Tag  # noqa: E402

PARSER = "html.parser"

# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------

_META_CHARSET_RE = re.compile(
    rb"<meta[^>]+charset\s*=\s*[\"']?\s*([a-zA-Z0-9_:.\-]+)", re.IGNORECASE
)


def sniff_meta_charset(content: bytes) -> Optional[str]:
    """Return the charset declared in a <meta> tag in the first 4 KB, if any."""
    match = _META_CHARSET_RE.search(content[:4096])
    if not match:
        return None
    return match.group(1).decode("ascii", "ignore").lower() or None


def decode_bytes(
    content: bytes, header_charset: Optional[str] = None, is_html: bool = True
) -> Tuple[str, str]:
    """Decode a response body. Returns (text, encoding_used).

    Order follows the HTML spec: byte-order mark, then the Content-Type
    charset, then <meta charset>, then UTF-8, then Windows-1252 (which
    never fails). ISO-8859-1 and ASCII labels mean Windows-1252, as in
    browsers, and a body with such a label that is valid UTF-8 is read as
    UTF-8. When no candidate decodes cleanly, the first declared charset is
    used with replacement characters. requests' response.text skips the
    meta step and falls back to ISO-8859-1, which garbles UTF-8 pages
    served without a charset.
    """
    if content is None:
        return "", "utf-8"
    boms = (
        (b"\xef\xbb\xbf", "utf-8-sig"),
        (b"\xff\xfe", "utf-16"),
        (b"\xfe\xff", "utf-16"),
    )
    for bom, encoding in boms:
        if content.startswith(bom):
            return content.decode(encoding, "replace"), encoding
    declared: List[str] = []
    if header_charset:
        declared.append(_charset_label(header_charset))
    if is_html:
        meta = sniff_meta_charset(content)
        if meta:
            declared.append(_charset_label(meta))
    order: List[str] = []
    for encoding in declared:
        # A legacy single-byte label on a body that is valid UTF-8 (with
        # non-ASCII bytes) is a mislabelled UTF-8 page: real cp1252 text
        # almost never forms valid UTF-8 sequences, so try UTF-8 first.
        if encoding in _SINGLE_BYTE_LABELS and _HIGH_BYTE_RE.search(content):
            order.append("utf-8")
        order.append(encoding)
    order.append("utf-8")
    for encoding in order:
        try:
            return content.decode(encoding), encoding
        except (LookupError, UnicodeDecodeError):
            continue
    # Nothing decoded cleanly. A declared charset still wins (browsers use it
    # with replacement characters), so one stray byte in a UTF-8 page does
    # not turn every accented letter into mojibake. Only an undeclared body
    # falls back to Windows-1252, which never fails.
    for encoding in declared:
        try:
            return content.decode(encoding, "replace"), encoding
        except LookupError:
            continue
    return content.decode("cp1252", "replace"), "cp1252"


# The HTML standard decodes these labels as Windows-1252: pages labelled
# ISO-8859-1 routinely contain cp1252 curly quotes and dashes in 0x80-0x9F,
# which Python's latin-1 codec would turn into invisible control characters.
_CP1252_ALIASES = {
    "iso-8859-1", "iso8859-1", "iso_8859-1", "latin-1", "latin1", "l1",
    "us-ascii", "ascii", "ansi_x3.4-1968", "cp819", "ibm819",
}
_SINGLE_BYTE_LABELS = {"cp1252", "windows-1252", "x-cp1252"}
_HIGH_BYTE_RE = re.compile(rb"[\x80-\xff]")


def _charset_label(label: str) -> str:
    """Normalize a declared charset label (quotes, case, WHATWG aliases)."""
    value = label.strip().strip("\"'").lower()
    return "cp1252" if value in _CP1252_ALIASES else value


def parse(markup: Union[str, bytes, None]) -> BeautifulSoup:
    """Parse HTML with html.parser. Bytes are decoded with decode_bytes()."""
    if isinstance(markup, bytes):
        markup = decode_bytes(markup)[0]
    return BeautifulSoup(markup or "", PARSER)


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

_WS_RE = re.compile(r"\s+")
# Only punctuation that ends a word ("together ." -> "together."): the mark
# must be followed by a space, the end, or more punctuation, so ".NET",
# ".csv" and ".5" keep their leading space.
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?%)\]}])(?=$|\s|[,.;:!?%)\]}\"'])")
_SPACE_AFTER_OPEN_RE = re.compile(r"([(\[{])\s+")
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_ALNUM_RE = re.compile(r"[^\W_]", re.UNICODE)


def normalize_space(text: Optional[str]) -> str:
    """Collapse every run of whitespace (including newlines) to one space."""
    return _WS_RE.sub(" ", text or "").strip()


def collapse_repeats(text: str, min_words: int = 3) -> str:
    """Return one copy of a sentence that is repeated back to back.

    Responsive sites often put two or three variants of a headline inside
    one element ("The product development system for teams and agents" x3
    on linear.app); all variants become visible text in static HTML.
    """
    words = text.split()
    count = len(words)
    best = text
    for parts in range(2, count // max(min_words, 1) + 1):
        if count % parts:
            continue
        size = count // parts
        if size < min_words:
            break
        keys = [_key(" ".join(words[i * size:(i + 1) * size])) for i in range(parts)]
        if keys[0] and all(k == keys[0] for k in keys[1:]):
            best = " ".join(words[:size])
    return best


def clean_text(node: Any, collapse: bool = False) -> str:
    """Visible-looking text of a node (or string) with words never glued.

    Uses get_text(" ") so every element boundary becomes a space, then
    collapses whitespace and removes the stray space that this leaves
    before punctuation ("together ." -> "together."). With collapse=True,
    a sentence repeated back to back is reduced to one copy.
    """
    if node is None:
        return ""
    if isinstance(node, str):
        raw = str(node)
    elif hasattr(node, "get_text"):
        raw = node.get_text(" ", strip=True)
    else:
        raw = str(node)
    text = normalize_space(raw)
    text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    text = _SPACE_AFTER_OPEN_RE.sub(r"\1", text)
    if collapse:
        text = collapse_repeats(text)
    return text


def word_count(text: Optional[str]) -> int:
    """Count words; CJK characters count as roughly one word per two characters."""
    if not text:
        return 0
    tokens = [t for t in text.split() if _ALNUM_RE.search(t)]
    cjk = len(_CJK_RE.findall(text))
    return len(tokens) + cjk // 2


def _key(text: str) -> str:
    """Normalized comparison key: case-folded letters and digits only."""
    return " ".join(re.sub(r"[\W_]+", " ", (text or "").casefold()).split())


def dedupe_texts(items: Iterable[str], containment: bool = False) -> List[str]:
    """Drop repeated strings in order (case and punctuation insensitive).

    With containment=True a string that is contained in a kept one is
    dropped too, and a later, longer string replaces a shorter kept one in
    place (useful for nested wrappers that repeat a child's text).
    """
    kept: List[str] = []
    keys: List[str] = []
    seen = set()  # same keys as `keys`, for O(1) exact-duplicate checks
    for item in items:
        key = _key(item)
        if not key:
            continue
        if key in seen:
            continue
        if containment:
            if any(key in k for k in keys):
                continue
            replaced = False
            for idx, existing in enumerate(keys):
                if existing in key:
                    kept[idx] = item
                    seen.discard(existing)
                    keys[idx] = key
                    seen.add(key)
                    replaced = True
                    break
            if replaced:
                continue
        kept.append(item)
        keys.append(key)
        seen.add(key)
    return kept


# ---------------------------------------------------------------------------
# Hidden and non-rendered nodes
# ---------------------------------------------------------------------------

# Tags whose text a visitor never reads as page copy.
NON_RENDERED_TAGS = (
    "script", "style", "noscript", "template", "svg", "iframe", "object",
    "embed", "canvas", "audio", "video", "map", "math",
)

_HIDDEN_STYLE_RE = re.compile(
    r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)\b", re.IGNORECASE
)
_SR_ONLY_CLASSES = {
    "sr-only", "visually-hidden", "visuallyhidden", "screen-reader-text",
    "screen-reader-only", "screenreader-only", "a11y-hidden", "u-visually-hidden",
    "element-invisible", "assistive-text",
}
_HIDE_CLASSES = {"hidden", "d-none", "hide", "is-hidden", "u-hidden", "invisible", "display-none"}
# "hidden md:block" (Tailwind) or "d-none d-md-block" (Bootstrap) is visible
# on desktop, so it is a responsive variant, not hidden content.
_RESPONSIVE_SHOW_RE = re.compile(
    r"^(?:(?:sm|md|lg|xl|2xl|min-\[[^\]]+\]):(?:block|flex|grid|inline|inline-block|inline-flex|"
    r"inline-grid|table|table-cell|contents|flow-root|visible)|d-(?:sm|md|lg|xl|xxl)-(?:block|flex|inline|"
    r"inline-block|inline-flex|grid|table|table-cell))$"
)


def _classes(tag: Tag) -> List[str]:
    value = tag.attrs.get("class") if tag.attrs else None
    if not value:
        return []
    if isinstance(value, str):
        value = value.split()
    return [str(c).lower() for c in value]


def hidden_reason(tag: Any) -> Optional[str]:
    """Why this element itself is hidden, or None. Ancestors are not checked."""
    if not isinstance(tag, Tag) or not tag.attrs:
        if isinstance(tag, Tag) and tag.name == "dialog":
            return "closed-dialog"
        return None
    attrs = tag.attrs
    if "hidden" in attrs and str(attrs.get("hidden") or "").lower() != "until-found":
        return "hidden-attribute"
    if str(attrs.get("aria-hidden", "")).strip().lower() == "true":
        return "aria-hidden"
    style = attrs.get("style")
    if style and _HIDDEN_STYLE_RE.search(str(style)):
        return "inline-style"
    classes = _classes(tag)
    if classes:
        if any(c in _SR_ONLY_CLASSES for c in classes):
            return "screen-reader-only"
        if any(c in _HIDE_CLASSES for c in classes) and not any(
            _RESPONSIVE_SHOW_RE.match(c) for c in classes
        ):
            return "hidden-class"
    if tag.name == "dialog" and "open" not in attrs:
        return "closed-dialog"
    if tag.name == "input" and str(attrs.get("type", "")).lower() == "hidden":
        return "hidden-input"
    return None


def is_hidden(tag: Any) -> bool:
    """True when the element or any ancestor is hidden or non-rendered."""
    node = tag
    while isinstance(node, Tag):
        if node.name in NON_RENDERED_TAGS or hidden_reason(node):
            return True
        node = node.parent
    return False


# Classes that hide an element from a breakpoint up: a mobile-only variant.
_MOBILE_ONLY_RE = re.compile(r"^(?:(?:sm|md|lg|xl|2xl):hidden|d-(?:sm|md|lg|xl|xxl)-none|hidden-(?:sm|md|lg)-up|show-for-small-only)$")


def _mobile_only(tag: Tag) -> bool:
    classes = _classes(tag)
    return any(_MOBILE_ONLY_RE.match(c) for c in classes) and not any(
        _RESPONSIVE_SHOW_RE.match(c) for c in classes
    )


def remove_responsive_duplicates(soup: Tag) -> int:
    """Drop mobile-only variants ("md:hidden") whose text repeats a nearby element.

    Sites often render the same headline or CTA twice, one copy per
    breakpoint. Static HTML shows both, which doubles text and counts. The
    desktop variant is kept; a mobile-only element without a twin nearby
    (sibling, or child of a sibling of its parent) is kept too.
    """
    # "Nearby" is every element grandchild of the grandparent (siblings plus
    # the uncles' children). The text keys of those elements are computed
    # once per container and cached, because comparing every mobile-only
    # element against every nearby element re-reads the same text and is
    # quadratic: a 500 KB page with 800 cards took over 10 seconds.
    child_keys: Dict[int, set] = {}
    grandchild_keys: Dict[int, set] = {}

    def keys_of_children(node: Tag) -> set:
        cached = child_keys.get(id(node))
        if cached is None:
            cached = {
                _key(child.get_text(" ", strip=True))
                for child in node.find_all(True, recursive=False)
                if not _mobile_only(child)
            }
            cached.discard("")
            child_keys[id(node)] = cached
        return cached

    def keys_of_grandchildren(node: Tag) -> set:
        cached = grandchild_keys.get(id(node))
        if cached is None:
            cached = set()
            for child in node.find_all(True, recursive=False):
                cached |= keys_of_children(child)
            grandchild_keys[id(node)] = cached
        return cached

    removed = 0
    for tag in soup.find_all(True):
        if tag.parent is None or not _mobile_only(tag):
            continue
        key = _key(tag.get_text(" ", strip=True))
        if not key:
            continue
        parent = tag.parent
        grandparent = parent.parent
        nearby = keys_of_grandchildren(grandparent) if grandparent is not None else keys_of_children(parent)
        if key in nearby:
            tag.extract()
            removed += 1
    return removed


def _attached(tag: Tag, root: Tag) -> bool:
    node = tag
    while node is not None:
        if node is root:
            return True
        node = node.parent
    return False


def strip_invisible(soup: Tag, hidden: bool = True, non_rendered: bool = True) -> Dict[str, int]:
    """Remove hidden and non-rendered nodes in place. Returns counts by reason.

    Hidden means: the hidden attribute, aria-hidden="true", inline
    display:none / visibility:hidden, screen-reader-only classes, hide
    classes without a responsive "show" class, closed <dialog>, and
    <input type="hidden">, plus mobile-only twins of desktop elements
    (remove_responsive_duplicates). Non-rendered means script, style, noscript,
    template, svg, iframe and similar. HTML comments are removed too.

    One rescue: an element with aria-label whose visible text was all inside
    aria-hidden children (split-letter headline animations) gets its
    aria-label back as text, so the headline is not lost.
    """
    counts: Dict[str, int] = {}
    if hidden:
        rescue: List[Tuple[Tag, str]] = []
        for tag in soup.find_all(attrs={"aria-label": True}):
            label = normalize_space(str(tag.get("aria-label") or ""))
            if label and tag.find(attrs={"aria-hidden": "true"}) is not None and tag.get_text(strip=True):
                rescue.append((tag, label))
        targets = []
        for tag in soup.find_all(True):
            reason = hidden_reason(tag)
            if reason:
                targets.append((tag, reason))
        for tag, reason in targets:
            counts[reason] = counts.get(reason, 0) + 1
            tag.extract()
        for tag, label in rescue:
            if _attached(tag, soup) and not tag.get_text(strip=True):
                tag.append(NavigableString(label))
        duplicates = remove_responsive_duplicates(soup)
        if duplicates:
            counts["responsive-duplicate"] = duplicates
    if non_rendered:
        for tag in soup.find_all(list(NON_RENDERED_TAGS)):
            counts[tag.name] = counts.get(tag.name, 0) + 1
            tag.extract()
        for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
            comment.extract()
    return counts


def visible_text(markup_or_soup: Any) -> str:
    """Clean visible text of a page (hidden and non-rendered nodes removed)."""
    if isinstance(markup_or_soup, (str, bytes)) or markup_or_soup is None:
        soup = parse(markup_or_soup)
    else:
        soup = BeautifulSoup(str(markup_or_soup), PARSER)
    strip_invisible(soup)
    return clean_text(soup.body or soup)


# ---------------------------------------------------------------------------
# JS-shell detection (regex based, so http.fetch() can run it cheaply)
# ---------------------------------------------------------------------------

_SCRIPT_BLOCK_RE = re.compile(r"<script\b[^>]*>(.*?)</script\s*>", re.IGNORECASE | re.DOTALL)
_SCRIPT_OPEN_RE = re.compile(r"<script\b", re.IGNORECASE)
_NOSCRIPT_RE = re.compile(r"<noscript\b[^>]*>(.*?)</noscript\s*>", re.IGNORECASE | re.DOTALL)
_DROP_BLOCKS_RE = re.compile(
    r"<(style|template|svg|head|title)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL
)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_EMPTY_ROOT_RE = re.compile(
    r"<div\b[^>]*\bid\s*=\s*[\"']?(root|app|__next|__nuxt|svelte|___gatsby|react-root|app-root|"
    r"main-app|application|q-app)[\"']?[^>]*>\s*</div\s*>"
    r"|<(app-root)\b[^>]*>\s*</app-root\s*>",
    re.IGNORECASE,
)
_NOSCRIPT_JS_RE = re.compile(
    r"enable javascript|javascript (?:is )?(?:required|disabled|needed)|requires? javascript|"
    r"turn on javascript|need(?:s)? (?:to enable )?javascript|without javascript",
    re.IGNORECASE,
)
_H1_RE = re.compile(r"<h1\b", re.IGNORECASE)

# Visible-word thresholds for the JS-shell decision (see js_shell_signals).
SHELL_EMPTY_WORDS = 20
SHELL_MAX_WORDS = 50
# Up to this many words, an empty SPA root and no <h1> still mean a shell.
SHELL_SOFT_MAX_WORDS = 150


def js_shell_signals(markup: Union[str, bytes, None]) -> Dict[str, Any]:
    """Decide whether static HTML is a client-rendered shell.

    A shell is (a) under 20 visible words with any script or SPA marker,
    (b) under 50 words with an empty SPA root (<div id="root"></div>,
    #__next, #app, <app-root>), a noscript "enable JavaScript" message,
    20 KB+ of inline script, or 3+ scripts and no <h1>, or (c) under 150
    words with an SPA marker and no <h1>. A short static page with a real
    headline is not a shell.
    Returns {"is_js_shell", "visible_words", "script_count", "script_bytes",
    "empty_root", "noscript_js_required", "has_h1"}.
    """
    if isinstance(markup, bytes):
        markup = decode_bytes(markup)[0]
    text = markup or ""
    script_count = len(_SCRIPT_OPEN_RE.findall(text))
    scripts = _SCRIPT_BLOCK_RE.findall(text)
    script_bytes = sum(len(s) for s in scripts)
    stripped = _COMMENT_RE.sub(" ", text)
    stripped = _SCRIPT_BLOCK_RE.sub(" ", stripped)
    noscript_text = " ".join(_NOSCRIPT_RE.findall(stripped))
    noscript_js = bool(_NOSCRIPT_JS_RE.search(_TAG_RE.sub(" ", noscript_text)))
    stripped = _NOSCRIPT_RE.sub(" ", stripped)
    stripped = _DROP_BLOCKS_RE.sub(" ", stripped)
    visible = stdlib_html.unescape(_TAG_RE.sub(" ", stripped))
    words = word_count(visible)
    root_match = _EMPTY_ROOT_RE.search(stripped)
    empty_root = (root_match.group(1) or root_match.group(2)) if root_match else None
    has_h1 = bool(_H1_RE.search(stripped))
    spa_marker = bool(empty_root) or noscript_js
    is_shell = (
        # Practically empty, and scripts are what is left.
        (words < SHELL_EMPTY_WORDS and (script_count >= 1 or spa_marker))
        # Very little text plus a clear client-rendering marker.
        or (words < SHELL_MAX_WORDS and (
            spa_marker or script_bytes >= 20000 or (script_count >= 3 and not has_h1)))
        # Some static text (cookie notice, footer) around an empty app root.
        or (words < SHELL_SOFT_MAX_WORDS and spa_marker and not has_h1)
    )
    return {
        "is_js_shell": bool(is_shell),
        "visible_words": words,
        "script_count": script_count,
        "script_bytes": script_bytes,
        "empty_root": empty_root,
        "noscript_js_required": noscript_js,
        "has_h1": has_h1,
    }


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

_TWO_LEVEL_SUFFIXES = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "net.au", "org.au", "com.br",
    "co.jp", "co.in", "co.nz", "com.tr", "com.mx", "co.za", "com.sg", "com.cn",
    "co.kr", "com.ar", "com.hk", "com.tw", "co.il", "com.my", "co.id",
}


def site_domain(host: Optional[str]) -> str:
    """Approximate registrable domain: 'app.linear.app' -> 'linear.app'."""
    host = (host or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    labels = host.split(".")
    if len(labels) >= 3 and ".".join(labels[-2:]) in _TWO_LEVEL_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def _host(url: Optional[str]) -> str:
    try:
        return (urlparse(url or "").hostname or "").lower()
    except ValueError:
        return ""


def _absolute(href: Optional[str], base: Optional[str]) -> Optional[str]:
    if href is None:
        return None
    href = str(href).strip()
    if not href:
        return None
    if base and not href.lower().startswith(("javascript:", "mailto:", "tel:", "data:")):
        try:
            return urljoin(base, href)
        except ValueError:
            return href
    return href


# ---------------------------------------------------------------------------
# Meta, JSON-LD, social links, scripts
# ---------------------------------------------------------------------------


def _meta_content(soup: Tag, **attrs: Any) -> Optional[str]:
    for key, value in attrs.items():
        tag = soup.find("meta", attrs={key: re.compile(r"^%s$" % re.escape(value), re.I)})
        if tag is not None and tag.get("content") is not None:
            return normalize_space(str(tag.get("content"))) or None
    return None


def extract_title(soup: Tag) -> Optional[str]:
    """The document <title> (ignores <title> elements inside inline SVG)."""
    head = soup.find("head")
    title = head.find("title") if head is not None else None
    if title is None:
        for candidate in soup.find_all("title"):
            if candidate.find_parent("svg") is None:
                title = candidate
                break
    text = clean_text(title) if title is not None else ""
    return text or None


def extract_meta(soup: Tag) -> Dict[str, Any]:
    """Meta description, robots directives, canonical, Open Graph, Twitter, hreflang."""
    og_keys = ("title", "description", "image", "type", "url", "site_name", "locale")
    tw_keys = ("card", "site", "title", "description", "image")
    canonical = None
    for link in soup.find_all("link", href=True):
        rels = [r.lower() for r in (link.get("rel") or [])]
        if "canonical" in rels:
            canonical = str(link.get("href")).strip()
            break
    hreflang = []
    for link in soup.find_all("link", hreflang=True):
        rels = [r.lower() for r in (link.get("rel") or [])]
        if "alternate" in rels and link.get("href"):
            hreflang.append({"lang": str(link.get("hreflang")), "href": str(link.get("href"))})
    robots = {}
    for tag in soup.find_all("meta", attrs={"name": True, "content": True}):
        name = str(tag.get("name")).strip().lower()
        if name in ("robots", "googlebot", "googlebot-news", "bingbot", "msnbot", "slurp") or name.endswith("bot"):
            robots[name] = normalize_space(str(tag.get("content")))
    charset_tag = soup.find("meta", charset=True)
    return {
        "description": _meta_content(soup, name="description"),
        "robots": robots,
        "canonical": canonical,
        "viewport": _meta_content(soup, name="viewport"),
        "generator": _meta_content(soup, name="generator"),
        "charset": str(charset_tag.get("charset")).lower() if charset_tag is not None else None,
        "og": {k: _meta_content(soup, property="og:" + k) for k in og_keys},
        "twitter": {k: _meta_content(soup, name="twitter:" + k, property="twitter:" + k) for k in tw_keys},
        "hreflang_count": len(hreflang),
        "hreflang": hreflang[:50],
    }


def _parse_json_ld_text(raw: str) -> Any:
    """json.loads with fallbacks for comments, CDATA and raw control characters.

    NaN and Infinity (which Python's json accepts) become None, so
    page_facts() output stays valid JSON for strict parsers such as jq.
    """
    try:
        return json.loads(raw, parse_constant=_no_constant)
    except ValueError:
        pass
    cleaned = raw.strip()
    cleaned = re.sub(r"^\s*(?:<!--|//\s*<!\[CDATA\[|<!\[CDATA\[)", "", cleaned)
    cleaned = re.sub(r"(?:-->|//\s*\]\]>|\]\]>)\s*$", "", cleaned)
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)  # trailing commas
    return json.loads(cleaned, strict=False, parse_constant=_no_constant)


def _no_constant(_name: str) -> None:
    return None


def _flatten_ld(data: Any, out: List[Dict[str, Any]]) -> None:
    if isinstance(data, list):
        for item in data:
            _flatten_ld(item, out)
    elif isinstance(data, dict):
        graph = data.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                _flatten_ld(item, out)
            rest = {k: v for k, v in data.items() if k not in ("@graph", "@context")}
            if rest:
                out.append(rest)
        else:
            out.append(data)


def _ld_types(item: Dict[str, Any]) -> List[str]:
    value = item.get("@type")
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)] if value else []


def extract_json_ld(soup: Tag, max_items: int = 50) -> Dict[str, Any]:
    """Parse every application/ld+json block, flattening lists and @graph.

    Returns {"blocks", "errors", "types", "items", "items_truncated"}.
    Invalid blocks are counted with a short error instead of raising.
    """
    items: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    blocks = 0
    for index, script in enumerate(soup.find_all("script")):
        kind = str(script.get("type") or "").split(";")[0].strip().lower()
        if kind != "application/ld+json":
            continue
        blocks += 1
        raw = script.string if script.string is not None else "".join(script.strings)
        if not raw or not raw.strip():
            errors.append({"block": blocks, "error": "empty block"})
            continue
        try:
            _flatten_ld(_parse_json_ld_text(raw), items)
        except (ValueError, RecursionError) as exc:  # RecursionError: absurdly deep nesting
            errors.append({"block": blocks, "error": str(exc)[:160]})
    types: List[str] = []
    for item in items:
        for name in _ld_types(item):
            if name not in types:
                types.append(name)
    return {
        "blocks": blocks,
        "errors": errors,
        "types": types,
        "items": items[:max_items],
        "items_truncated": len(items) > max_items,
    }


_SOCIAL_RULES: List[Tuple[str, re.Pattern, Optional[re.Pattern]]] = [
    ("x", re.compile(r"^(?:www\.|mobile\.)?(?:twitter\.com|x\.com)$"),
     re.compile(r"^/(?!intent/|share|home\b|hashtag/|search|i/)[A-Za-z0-9_]{1,30}/?$")),
    ("linkedin", re.compile(r"(?:^|\.)linkedin\.com$"), re.compile(r"^/(?:company|in|showcase|school)/[^/]+")),
    ("facebook", re.compile(r"(?:^|\.)(?:facebook\.com|fb\.com)$"),
     re.compile(r"^/(?!sharer|share|dialog|plugins|tr\b|login)[^/?]+/?$")),
    ("instagram", re.compile(r"(?:^|\.)instagram\.com$"), re.compile(r"^/(?!p/|reel/|explore/)[^/]+/?$")),
    ("youtube", re.compile(r"(?:^|\.)youtube\.com$"), re.compile(r"^/(?:channel/|c/|user/|@)[^/]+")),
    ("github", re.compile(r"^github\.com$"),
     re.compile(r"^/(?!features|pricing|login|signup|about|enterprise|marketplace|sponsors|topics)[^/]+/?$")),
    ("tiktok", re.compile(r"(?:^|\.)tiktok\.com$"), re.compile(r"^/@[^/]+")),
    ("threads", re.compile(r"(?:^|\.)threads\.(?:net|com)$"), re.compile(r"^/@[^/]+")),
    ("bluesky", re.compile(r"^bsky\.app$"), re.compile(r"^/profile/[^/]+")),
    ("discord", re.compile(r"^(?:discord\.gg|discord\.com)$"), re.compile(r"^/(?:invite/)?[^/]+/?$")),
    ("reddit", re.compile(r"(?:^|\.)reddit\.com$"), re.compile(r"^/(?:r|user|u)/[^/]+")),
    ("medium", re.compile(r"(?:^|\.)medium\.com$"), re.compile(r"^/@?[^/]+/?$")),
    ("producthunt", re.compile(r"(?:^|\.)producthunt\.com$"), re.compile(r"^/(?:products|posts|@)[^/]*")),
    ("pinterest", re.compile(r"(?:^|\.)pinterest\.[a-z.]+$"), re.compile(r"^/[^/]+/?$")),
]


def classify_social(url: Optional[str]) -> Optional[str]:
    """Platform name for a social profile URL, or None (share links excluded)."""
    if not url:
        return None
    try:
        parsed = urlparse(str(url).strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    for platform, host_re, path_re in _SOCIAL_RULES:
        if host_re.search(host):
            if path_re is None or path_re.search(parsed.path or "/"):
                if platform == "discord" and host == "discord.com" and not parsed.path.startswith("/invite/"):
                    return None
                return platform
            return None
    return None


def _social_key(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    host = {"twitter.com": "x.com"}.get(host, host)
    return host + parsed.path.rstrip("/").lower()


def extract_social_links(
    soup: Tag, page_url: Optional[str] = None, json_ld_items: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """Social profiles from <a href> and JSON-LD sameAs, deduplicated.

    Each entry: {"platform", "url", "sources": ["anchor", "json-ld"]}.
    """
    found: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    def add(url: str, source: str) -> None:
        platform = classify_social(url)
        if not platform:
            return
        key = _social_key(url)
        if key not in found:
            found[key] = {"platform": platform, "url": url, "sources": []}
            order.append(key)
        if source not in found[key]["sources"]:
            found[key]["sources"].append(source)

    for item in json_ld_items or []:
        same_as = item.get("sameAs")
        if isinstance(same_as, str):
            same_as = [same_as]
        if isinstance(same_as, list):
            for url in same_as:
                if isinstance(url, str):
                    add(url.strip(), "json-ld")
    for link in soup.find_all("a", href=True):
        href = _absolute(link.get("href"), page_url)
        if href:
            add(href, "anchor")
    return [found[k] for k in order]


def extract_script_hosts(soup: Tag, page_url: Optional[str] = None) -> Dict[str, Any]:
    """Hosts of external <script src>, split into first and third party.

    Returns {"third_party": [{"host", "count"}], "first_party_count",
    "inline_count"}. Without page_url every external host is listed.
    """
    page_domain = site_domain(_host(page_url)) if page_url else ""
    third: Dict[str, int] = {}
    order: List[str] = []
    first_party = 0
    inline = 0
    for script in soup.find_all("script"):
        src = script.get("src")
        if not src:
            kind = str(script.get("type") or "").lower()
            if "ld+json" not in kind:
                inline += 1
            continue
        absolute = _absolute(src, page_url) or ""
        if absolute.startswith("//"):
            absolute = "https:" + absolute
        host = _host(absolute)
        if not host:
            first_party += 1
            continue
        if page_domain and site_domain(host) == page_domain:
            first_party += 1
            continue
        if host not in third:
            third[host] = 0
            order.append(host)
        third[host] += 1
    return {
        "third_party": [{"host": h, "count": third[h]} for h in order],
        "first_party_count": first_party,
        "inline_count": inline,
    }


_EMBED_PROVIDERS: List[Tuple[str, re.Pattern]] = [
    ("hubspot", re.compile(r"js\.hsforms\.net|hbspt\.forms\.create|forms\.hsforms\.com|share\.hsforms\.com|js\.hs-scripts\.com/.*forms", re.I)),
    ("hubspot_meetings", re.compile(r"meetings\.hubspot\.com|static\.hsappstatic\.net/MeetingsEmbed", re.I)),
    ("marketo", re.compile(r"MktoForms2|mktoForm_\d+|/js/forms2/js/forms2", re.I)),
    ("typeform", re.compile(r"embed\.typeform\.com|form\.typeform\.com|\.typeform\.com/to/", re.I)),
    ("calendly", re.compile(r"assets\.calendly\.com|calendly\.com/[^\"'\s]+", re.I)),
    ("chilipiper", re.compile(r"js\.chilipiper\.com|\.chilipiper\.com", re.I)),
    ("jotform", re.compile(r"jotform\.com|jotfor\.ms", re.I)),
    ("tally", re.compile(r"tally\.so/(?:widgets|embed|r/)", re.I)),
    ("pardot", re.compile(r"pi\.pardot\.com|go\.pardot\.com", re.I)),
    ("formstack", re.compile(r"formstack\.com/forms", re.I)),
    ("google_forms", re.compile(r"docs\.google\.com/forms", re.I)),
    ("cal_com", re.compile(r"app\.cal\.com/embed|cal\.com/embed\.js", re.I)),
]


def detect_embedded_forms(soup: Tag) -> List[Dict[str, str]]:
    """Forms rendered by third-party JavaScript (invisible in static HTML)."""
    sources: List[str] = []
    for script in soup.find_all("script"):
        if script.get("src"):
            sources.append(str(script.get("src")))
        elif script.string:
            sources.append(str(script.string)[:20000])
    for frame in soup.find_all("iframe", src=True):
        sources.append(str(frame.get("src")))
    for tag in soup.find_all(id=re.compile(r"^mktoForm_\d+", re.I)):
        sources.append(str(tag.get("id")))
    found: List[Dict[str, str]] = []
    seen = set()
    for provider, pattern in _EMBED_PROVIDERS:
        for source in sources:
            match = pattern.search(source)
            if match and provider not in seen:
                seen.add(provider)
                found.append({"provider": provider, "evidence": match.group(0)[:120]})
                break
    return found


# ---------------------------------------------------------------------------
# CTA intent
# ---------------------------------------------------------------------------

_SIGNUP_SEGS = {
    "signup", "sign-up", "sign_up", "register", "registration", "join", "get-started",
    "getstarted", "start", "try", "trial", "free-trial", "create-account", "onboarding",
    "start-free", "try-free",
}
_LOGIN_SEGS = {"login", "log-in", "signin", "sign-in", "sign_in", "sso", "auth"}
_DEMO_SEGS = {
    "demo", "demos", "book-a-demo", "request-demo", "request-a-demo", "get-a-demo",
    "book-demo", "schedule-demo", "contact-sales", "talk-to-sales", "sales", "enterprise-demo",
}
_PRICING_SEGS = {"pricing", "plans", "prices", "price"}
_BUY_SEGS = {"checkout", "buy", "purchase", "cart", "upgrade", "subscribe"}
_DOWNLOAD_SEGS = {"download", "downloads"}
_CONTACT_SEGS = {"contact", "contact-us", "contactus", "get-in-touch"}
_DOCS_SEGS = {"docs", "documentation", "developers", "api-reference"}
_SCHEDULER_HOSTS = ("calendly.com", "chilipiper.com", "meetings.hubspot.com", "savvycal.com", "cal.com")
_STORE_HOSTS = (
    "apps.apple.com", "itunes.apple.com", "play.google.com", "chrome.google.com",
    "chromewebstore.google.com", "apps.microsoft.com", "microsoftedge.microsoft.com",
)
_APP_PREFIXES = ("app.", "dashboard.", "console.", "my.", "portal.", "studio.", "web.")
_BINARY_EXT_RE = re.compile(r"\.(?:dmg|exe|msi|pkg|apk|deb|rpm|appimage)$", re.I)

_TEXT_INTENTS: List[Tuple[str, re.Pattern]] = [
    ("demo", re.compile(
        r"\b(?:book|request|get|schedule|watch|see|take)\s+(?:a\s+|the\s+|your\s+|our\s+)?"
        r"(?:free\s+|live\s+|personali[sz]ed\s+|quick\s+)?demo\b|\btalk to (?:sales|us|an expert|our team)\b|"
        r"\bcontact sales\b|\bget a quote\b|\bbook a (?:call|meeting)\b|\bschedule a (?:call|meeting)\b", re.I)),
    ("signup", re.compile(
        r"\bsign\s?up\b|\bget started\b|\bstart (?:for free|free|now|building|your|a free|trial|today)\b|"
        r"\btry (?:it |\w+ )?(?:for )?free\b|\btry (?:it )?now\b|\bfree trial\b|\bstart trial\b|"
        r"\bcreate (?:an |your |a free )?account\b|\bjoin (?:now|free|for free|today|the waitlist)\b|"
        r"\bget \w+ (?:for )?free\b|\bget (?:early )?access\b|\brequest access\b|\bjoin waitlist\b", re.I)),
    ("login", re.compile(r"\blog\s?in\b|\bsign\s?in\b", re.I)),
    ("pricing", re.compile(r"\bpricing\b|\b(?:see|view|compare) (?:all )?plans\b|^plans$", re.I)),
    ("buy", re.compile(r"\bbuy\b|\bpurchase\b|\bupgrade\b|\bcheckout\b|\badd to cart\b", re.I)),
    ("subscribe", re.compile(r"\bsubscribe\b|\bnewsletter\b|\bnotify me\b", re.I)),
    ("download", re.compile(r"\bdownload\b|\bapp store\b|\bgoogle play\b|\bget the app\b|\binstall\b", re.I)),
    ("contact", re.compile(r"\bcontact(?: us)?\b|\bget in touch\b|\bemail us\b", re.I)),
    ("learn", re.compile(
        r"\blearn more\b|\bread more\b|\bsee how\b|\bexplore\b|\bdiscover\b|\bfind out\b|"
        r"\bwatch (?:the )?video\b|\bsee (?:it|how|all|more)\b|\bmore info\b|\btake a tour\b", re.I)),
]

_UI_TEXT_RE = re.compile(
    r"^(?:close|menu|open menu|close menu|toggle\b.*|search|previous|next|prev|play|pause|mute|unmute|"
    r"back|skip\b.*|dismiss|accept(?: all)?(?: cookies)?|reject(?: all)?(?: cookies)?|decline|"
    r"(?:cookie|privacy) (?:settings|preferences)|manage (?:cookies|preferences)|preferences|language|"
    r"english\b.*|deutsch|fran\u00e7ais|espa\u00f1ol|portugu\u00eas|share|copy|expand|collapse|"
    r"show (?:more|less)|high contrast|x|\u00d7|\u2715|.*\b(?:slide|carousel)\b.*|(?:previous|next|prev) \w+)$",
    re.I,
)

STRONG_INTENTS = {"signup", "demo", "login", "pricing", "buy", "download", "contact", "app"}


def classify_href(href: Optional[str], page_host: Optional[str] = None) -> Optional[str]:
    """Intent of a link from its URL: signup, login, demo, pricing, buy,
    download, contact, docs, app, social, external, or None (internal or
    on-page anchor with no recognizable intent)."""
    if not href:
        return None
    value = str(href).strip()
    low = value.lower()
    if low.startswith("mailto:") or low.startswith("tel:"):
        return "contact"
    if low.startswith(("javascript:", "#", "data:")):
        return None
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    segments = [s for s in (parsed.path or "").lower().split("/") if s]
    query = (parsed.query or "").lower()
    same_site = not host or (page_host and site_domain(host) == site_domain(page_host))
    if host and not same_site:
        if any(host == h or host.endswith("." + h) for h in _SCHEDULER_HOSTS):
            return "demo"
        if any(host == h or host.endswith("." + h) for h in _STORE_HOSTS):
            return "download"
        if classify_social(value):
            return "social"
    if any(s in _SIGNUP_SEGS for s in segments) or re.search(
        r"(?:^|&)(?:signup|sign_up|register|mode=signup|screen_hint=signup)(?:=|&|$)", query
    ):
        return "signup"
    if any(s in _DEMO_SEGS or s.startswith(("book-a-demo", "request-demo", "contact-sales")) for s in segments):
        return "demo"
    if any(s in _LOGIN_SEGS for s in segments):
        return "login"
    if any(s in _BUY_SEGS for s in segments):
        return "buy"
    if any(s in _PRICING_SEGS for s in segments):
        return "pricing"
    if any(s in _DOWNLOAD_SEGS for s in segments) or _BINARY_EXT_RE.search(parsed.path or ""):
        return "download"
    if any(s in _CONTACT_SEGS for s in segments):
        return "contact"
    if (segments and segments[0] in _DOCS_SEGS) or host.startswith(("docs.", "developers.", "developer.")):
        return "docs"
    if host.startswith(_APP_PREFIXES):
        return "app"
    if host and not same_site:
        return "external"
    return None


def classify_cta_text(text: str) -> Optional[str]:
    """Intent of a CTA from its words (fallback when the href says nothing)."""
    value = normalize_space(text)
    if not value:
        return None
    for intent, pattern in _TEXT_INTENTS:
        if pattern.search(value):
            return intent
    return None


# ---------------------------------------------------------------------------
# Page structure: chrome, blocks, zones
# ---------------------------------------------------------------------------

# Cookie banners: consent-platform ids and classes, matched as whole tokens.
# Loose substrings misfire on real content: "truste" is inside "trusted-by"
# (the social-proof logo wall) and "cmp-" prefixes every Adobe Experience
# Manager component ("cmp-container", "cmp-teaser").
_COOKIE_VENDOR_RE = re.compile(
    r"onetrust|cookiebot|cookieyes|cookie-?law|osano|iubenda|didomi|usercentrics|trustarc|termly|"
    r"(?:^|[-_\s])(?:truste|qc-cmp2?|cmpbox|cmpwrapper|cc-window|cc-banner)(?:[-_\s]|$)",
    re.I,
)
_COOKIE_WORD_RE = re.compile(r"(?:^|[-_\s])cookies?(?:[-_\s]|$)", re.I)
# "consent" and "gdpr" also name ordinary content ("gdpr-compliance" on a
# security page, a form's consent checkbox), so they only count when the
# element is short and talks about cookies.
_CONSENT_WORD_RE = re.compile(r"(?:^|[-_\s])(?:consent|gdpr)(?:[-_\s]|$)", re.I)
_COOKIE_TEXT_RE = re.compile(r"\bcookies?\b", re.I)
_SECTIONING_PARENTS = {"article", "section", "aside", "blockquote", "figure", "li"}
_HEADING_RE = re.compile(r"^h[1-6]$")


def _in_sectioning(tag: Tag) -> bool:
    """True inside article/section/aside/blockquote/figure/li.

    Per the HTML spec a <header> or <footer> there belongs to that section
    (a card or section heading), not to the page, so it is not chrome.
    """
    parent = tag.parent
    while isinstance(parent, Tag):
        if parent.name in _SECTIONING_PARENTS:
            return True
        parent = parent.parent
    return False


def _chrome_kind(tag: Tag) -> Optional[str]:
    """nav / footer / cookie / dialog for page chrome, else None."""
    role = str(tag.get("role") or "").lower()
    name = tag.name
    if name == "nav" or role == "navigation":
        return "nav"
    if role == "banner" or (name == "header" and not _in_sectioning(tag)):
        # A header that holds the real headline is the hero, not chrome. A
        # one- or two-word <h1> around the logo does not count.
        h1 = tag.find("h1")
        if h1 is not None and word_count(clean_text(h1)) >= 3:
            return None
        return "nav"
    if role == "contentinfo":
        return "footer"
    if name == "footer" and not _in_sectioning(tag):
        return "footer"
    if role in ("dialog", "alertdialog") or str(tag.get("aria-modal") or "").lower() == "true" or name == "dialog":
        return "dialog"
    ident = " ".join([str(tag.get("id") or "")] + _classes(tag))
    if ident:
        if _COOKIE_VENDOR_RE.search(ident) or _COOKIE_WORD_RE.search(ident):
            return "cookie"
        if _CONSENT_WORD_RE.search(ident):
            text = tag.get_text(" ", strip=True)
            if _COOKIE_TEXT_RE.search(text) and word_count(text) <= 200:
                return "cookie"
    return None


def _has_content(tag: Tag) -> bool:
    if tag.get_text(strip=True):
        return True
    return tag.find(["img", "picture", "form", "input", "button", "select", "textarea"]) is not None


def _contains(ancestor: Tag, node: Tag) -> bool:
    current = node
    while current is not None:
        if current is ancestor:
            return True
        current = current.parent
    return False


class _Layout:
    """Chrome elements, main-content blocks and the hero block of a page."""

    def __init__(self, soup: BeautifulSoup) -> None:
        self.soup = soup
        self.body = soup.body or soup
        self.chrome: Dict[int, str] = {}
        self.chrome_tags: List[Tag] = []
        for tag in self.body.find_all(True):
            kind = _chrome_kind(tag)
            if kind:
                self.chrome[id(tag)] = kind
                self.chrome_tags.append(tag)
        self.root = self._content_root()
        self.blocks = self._find_blocks()
        self.block_index: Dict[int, int] = {id(b): i for i, b in enumerate(self.blocks)}
        self.hero_index = self._hero_index()

    def in_chrome(self, tag: Tag) -> Optional[str]:
        node = tag
        while isinstance(node, Tag):
            kind = self.chrome.get(id(node))
            if kind:
                return kind
            node = node.parent
        return None

    def _content_root(self) -> Tag:
        main = self.body.find("main")
        if main is None:
            main = self.body.find(attrs={"role": "main"})
        if main is not None and not self.in_chrome(main):
            return main
        return self.body

    def _significant_children(self, node: Tag) -> List[Tag]:
        return [
            child for child in node.find_all(True, recursive=False)
            if id(child) not in self.chrome and _has_content(child)
        ]

    def _find_blocks(self) -> List[Tag]:
        node = self.root
        children: List[Tag] = []
        for _ in range(30):
            children = self._significant_children(node)
            if len(children) == 1:
                node = children[0]
                continue
            break
        blocks = children if children else ([node] if _has_content(node) else [])
        blocks = self._expand_wrappers(blocks)
        # When <main> starts below a hero that sits outside it (for example
        # <header><h1>..</h1></header><main>..</main>), put that hero first.
        h1 = self._first_content_h1()
        if h1 is not None and not any(_contains(b, h1) for b in blocks):
            hero = h1
            while hero.parent is not None and hero.parent is not self.body and not _contains(hero.parent, self.root):
                hero = hero.parent
            if hero is not self.root and not _contains(hero, self.root):
                blocks = [hero] + blocks
        return blocks

    def _expand_wrappers(self, blocks: List[Tag], depth: int = 0) -> List[Tag]:
        """Replace a wrapper that holds several sections by those sections.

        CMS pages often put every section after the hero into one container
        (hubspot.com: hero + one module wrapper with 8 h2 sections), which
        made the outline 2 blocks long and could put all of the page's CTAs
        in the "hero" zone. A block is split when two or more of its
        children each contain an <h2> (a heading child itself does not
        count, so "<h2>Features</h2> + card grid" stays one section).
        """
        out: List[Tag] = []
        for block in blocks:
            children = self._significant_children(block) if depth < 6 else []
            sectioned = sum(
                1 for child in children
                if not _HEADING_RE.match(child.name or "") and child.find("h2") is not None
            )
            if sectioned >= 2:
                out.extend(self._expand_wrappers(children, depth + 1))
            else:
                out.append(block)
        return out

    def _first_content_h1(self) -> Optional[Tag]:
        for h1 in self.body.find_all("h1"):
            if not self.in_chrome(h1) and h1.get_text(strip=True):
                return h1
        return None

    def _hero_index(self) -> Optional[int]:
        if not self.blocks:
            return None
        h1 = self._first_content_h1()
        if h1 is not None:
            for i, block in enumerate(self.blocks):
                if _contains(block, h1):
                    return i
        return 0

    def locate(self, tag: Tag) -> Tuple[str, Optional[int]]:
        """(zone, block index) for an element.

        zone is hero, body, nav, footer, cookie, dialog, or hidden (the
        element was removed as hidden before the layout was built).
        """
        node = tag
        while isinstance(node, Tag):
            kind = self.chrome.get(id(node))
            if kind:
                return kind, None
            index = self.block_index.get(id(node))
            if index is not None:
                return ("hero" if index == self.hero_index else "body"), index
            if node.parent is None and node is not self.soup:
                return "hidden", None
            node = node.parent
        return "body", None

    def remove_chrome(self) -> None:
        for tag in self.chrome_tags:
            tag.extract()


# ---------------------------------------------------------------------------
# CTAs
# ---------------------------------------------------------------------------

_BUTTONISH_CLASS_RE = re.compile(r"btn|button|cta", re.I)
# Logo walls often reuse the button component (notion.com does); a logo link
# is social proof, not a call to action.
_LOGO_WALL_RE = re.compile(r"logo|marquee|ticker|customer-?wall", re.I)


def _in_logo_wall(tag: Tag) -> bool:
    node = tag
    for _ in range(3):
        if not isinstance(node, Tag):
            return False
        if _LOGO_WALL_RE.search(" ".join(_classes(node))):
            return True
        node = node.parent
    return False


def _element_text(tag: Tag) -> str:
    text = clean_text(tag, collapse=True)
    if not text:
        for attr in ("aria-label", "title", "value"):
            if tag.get(attr):
                text = normalize_space(str(tag.get(attr)))
                break
    if not text:
        img = tag.find("img", alt=True)
        if img is not None:
            text = normalize_space(str(img.get("alt")))
    return text[:120]


def extract_ctas(
    soup: Tag, layout: _Layout, page_url: Optional[str] = None, max_items: int = 80
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """CTA inventory with zone and href-based intent.

    Keeps: links and buttons with a conversion intent (signup, demo, login,
    pricing, buy, download, contact, app) in any zone; 'learn more' style
    links in the hero or body; submit buttons; and button-styled links
    (btn / button / cta classes) in the hero or body. Drops UI controls
    (menus, carousel arrows, cookie buttons, language pickers) and links
    or buttons with no intent (logo links, product-mockup buttons).
    Entries are deduplicated on (text, href, zone) with a count.
    """
    page_host = _host(page_url)
    scan = {"links": 0, "buttons": 0, "ui_controls_skipped": 0, "kept": 0}
    entries: List[Dict[str, Any]] = []
    index_by_key: Dict[Tuple[str, str, str], int] = {}
    position = 0
    candidates = soup.find_all(["a", "button", "input"]) + [
        t for t in soup.find_all(attrs={"role": "button"}) if t.name not in ("a", "button", "input")
    ]
    # Keep document order (role=button elements were appended at the end).
    order = {id(t): i for i, t in enumerate(soup.find_all(True))}
    candidates.sort(key=lambda t: order.get(id(t), 0))
    for tag in candidates:
        name = tag.name
        role = str(tag.get("role") or "").lower()
        input_type = str(tag.get("type") or "").lower()
        if name == "input" and input_type not in ("submit", "button"):
            continue
        if name == "a" and not tag.get("href") and role != "button":
            continue
        is_button = name in ("button", "input") or role == "button"
        scan["buttons" if is_button else "links"] += 1
        text = _element_text(tag)
        if not text:
            continue
        href = _absolute(tag.get("href"), page_url) if name == "a" else None
        zone, block = layout.locate(tag)
        if zone == "hidden":
            continue
        in_form = tag.find_parent("form") is not None
        is_submit = in_form and (input_type == "submit" or (name == "button" and input_type in ("", "submit")))
        intent = classify_href(href, page_host) if href else None
        source = "href" if intent else None
        text_intent = classify_cta_text(text)
        if text_intent and (intent in (None, "external", "docs")
                            # "Sign up with Google" often points at an /auth/sso URL.
                            or (intent in ("login", "app") and text_intent == "signup")):
            intent, source = text_intent, "text"
        if is_button and not href and intent is None and not is_submit and _UI_TEXT_RE.match(text):
            scan["ui_controls_skipped"] += 1
            continue
        if zone in ("cookie", "dialog") and intent not in STRONG_INTENTS:
            scan["ui_controls_skipped"] += 1
            continue
        styled_link = not is_button and bool(_BUTTONISH_CLASS_RE.search(" ".join(_classes(tag)))) \
            and not (intent is None and _in_logo_wall(tag))
        styled = is_button or styled_link
        # Links and buttons without a recognizable intent (customer-logo
        # links, product-mockup buttons such as "Copy issue URL") are not
        # CTAs, even in the hero, unless the site styles them as buttons.
        keep = (
            intent in STRONG_INTENTS
            or (intent == "learn" and zone in ("hero", "body"))
            or is_submit
            or (styled_link and zone in ("hero", "body") and intent not in ("social",))
        )
        position += 1
        if not keep:
            continue
        # The same CTA in the nav and in the hero are different facts, so the
        # zone is part of the key.
        key = (_key(text), href or "", zone)
        if key in index_by_key:
            entries[index_by_key[key]]["count"] += 1
            continue
        index_by_key[key] = len(entries)
        entries.append({
            "text": text,
            "href": href,
            "element": name,
            "style": "button" if styled else "link",
            "zone": zone,
            "block": block,
            "intent": intent,
            "intent_source": source,
            "submit": is_submit,
            "position": position,
            "count": 1,
        })
    scan["kept"] = len(entries)
    return entries[:max_items], scan


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------

_HONEYPOT_NAME_RE = re.compile(
    r"^(?:hp|hp[_-].*|.*[_-]hp|honeypot.*|_gotcha|bot[-_]?field|leave[-_]?(?:this[-_]?)?blank|"
    r"ohnohoney|b_[0-9a-f]{10,}.*|a_password|confirm_email_address)$",
    re.I,
)
_SOFT_HONEYPOT_NAMES = {"website", "url", "homepage", "fax", "company_website", "nickname"}
_OFFSCREEN_RE = re.compile(
    r"(?:left|top|right)\s*:\s*-\d{3,}px|(?:width|height)\s*:\s*[01]px|clip\s*:\s*rect\(\s*0|"
    r"opacity\s*:\s*0(?:\.0+)?\s*(?:;|$)",
    re.I,
)
_SEARCH_NAMES = {"q", "s", "query", "search", "keyword", "keywords", "term"}
_SIGNUP_SUBMIT_RE = re.compile(
    r"sign\s?up|create (?:an |your )?account|get started|start (?:free|trial|now|building)|"
    r"try (?:it )?free|register|join|continue with email|start my", re.I)
_NEWSLETTER_RE = re.compile(r"subscribe|newsletter|updates|stay in the loop|notify me", re.I)
_LEAD_RE = re.compile(r"contact|demo|request|talk|book|get in touch|send message|quote|sales", re.I)
_LOGIN_RE = re.compile(r"log\s?in|sign\s?in", re.I)


def _offscreen(tag: Tag, depth: int = 3) -> bool:
    node = tag
    for _ in range(depth + 1):
        if not isinstance(node, Tag):
            break
        style = node.get("style")
        if style and _OFFSCREEN_RE.search(str(style)):
            return True
        node = node.parent
    return False


def _is_honeypot(tag: Tag) -> bool:
    name = str(tag.get("name") or tag.get("id") or "").strip()
    if name and _HONEYPOT_NAME_RE.match(name):
        return True
    tabindex = str(tag.get("tabindex") or "").strip()
    # autocomplete="off" is not evidence: many real forms set it on every
    # field, and a visible, labelled "Company website" question is real.
    # A honeypot is unreachable by keyboard (tabindex=-1) or pushed off-screen.
    sneaky = tabindex == "-1" or _offscreen(tag)
    if name.lower() in _SOFT_HONEYPOT_NAMES and sneaky:
        return True
    return tabindex == "-1" and _offscreen(tag)


def _field_label(tag: Tag, soup: Tag) -> Tuple[str, str]:
    """(label text, where it came from) for a form control."""
    field_id = tag.get("id")
    if field_id:
        label = soup.find("label", attrs={"for": field_id})
        if label is not None:
            text = clean_text(label)
            if text:
                return text, "label"
    wrapper = tag.find_parent("label")
    if wrapper is not None:
        text = clean_text(wrapper)
        if text:
            return text, "label"
    if tag.get("aria-label"):
        return normalize_space(str(tag.get("aria-label"))), "aria-label"
    labelledby = tag.get("aria-labelledby")
    if labelledby:
        parts = []
        for ref in str(labelledby).split():
            ref_tag = soup.find(id=ref)
            if ref_tag is not None:
                parts.append(clean_text(ref_tag))
        if any(parts):
            return " ".join(p for p in parts if p), "aria-labelledby"
    for attr in ("placeholder", "title"):
        if tag.get(attr):
            return normalize_space(str(tag.get(attr))), attr
    return normalize_space(str(tag.get("name") or "")), "name" if tag.get("name") else "none"


def extract_forms(soup: Tag, page_url: Optional[str] = None, max_fields: int = 25) -> List[Dict[str, Any]]:
    """Forms as user-facing questions. Call BEFORE strip_invisible().

    Hidden inputs, aria-hidden or display:none controls and honeypots are
    dropped (and counted), radio groups and same-name checkbox groups count
    as one question. Each form gets a kind guess (signup, login, search,
    newsletter, lead, other) and a candidate score; the best non-search,
    non-login form is marked primary_candidate. Zone is filled in later by
    page_facts() (it needs the page layout).
    """
    forms: List[Dict[str, Any]] = []
    for index, form in enumerate(soup.find_all("form")):
        form_hidden = is_hidden(form)
        dropped = {"hidden": 0, "honeypot": 0, "non_field": 0}
        questions: List[Dict[str, Any]] = []
        groups: Dict[Tuple[str, str], Dict[str, Any]] = {}
        types_seen: List[str] = []
        autocompletes: List[str] = []
        for control in form.find_all(["input", "select", "textarea"]):
            ctype = str(control.get("type") or "text").lower() if control.name == "input" else control.name
            if ctype in ("hidden", "submit", "button", "image", "reset"):
                dropped["non_field"] += 1
                continue
            if not form_hidden and is_hidden(control):
                dropped["hidden"] += 1
                continue
            if _is_honeypot(control):
                dropped["honeypot"] += 1
                continue
            name = str(control.get("name") or control.get("id") or "")
            autocomplete = str(control.get("autocomplete") or "").lower() or None
            if autocomplete:
                autocompletes.append(autocomplete)
            label, label_source = _field_label(control, soup)
            required = control.has_attr("required") or str(control.get("aria-required") or "").lower() == "true" \
                or label.rstrip().endswith("*")
            if ctype in ("radio", "checkbox") and name:
                key = (ctype, name)
                if key in groups:
                    groups[key]["options"] += 1
                    groups[key]["required"] = groups[key]["required"] or required
                    continue
                group_label = label
                fieldset = control.find_parent("fieldset")
                if fieldset is not None and fieldset.find("legend") is not None:
                    group_label = clean_text(fieldset.find("legend")) or label
                entry = {
                    "name": name, "type": ctype, "label": group_label[:120], "label_source": label_source,
                    "required": required, "optional_label": "optional" in group_label.lower(),
                    "autocomplete": autocomplete, "options": 1,
                }
                groups[key] = entry
                questions.append(entry)
                types_seen.append(ctype)
                continue
            entry = {
                "name": name, "type": ctype, "label": label[:120], "label_source": label_source,
                "required": required, "optional_label": "optional" in label.lower(),
                "autocomplete": autocomplete,
            }
            if ctype == "select":
                entry["options"] = len(control.find_all("option"))
            questions.append(entry)
            types_seen.append(ctype)
        submit_tag = form.find(["button", "input"], attrs={"type": re.compile(r"^submit$", re.I)}) \
            or form.find("button")
        submit_text = _element_text(submit_tag) if submit_tag is not None else ""
        action = _absolute(form.get("action"), page_url) if form.get("action") else None
        names = {q["name"].lower() for q in questions}
        has_email = "email" in types_seen or any("email" in (q["name"] or "").lower() for q in questions) \
            or "email" in autocompletes
        has_password = "password" in types_seen
        has_new_password = "new-password" in autocompletes
        has_current_password = "current-password" in autocompletes
        ident = " ".join([str(form.get("id") or ""), str(form.get("name") or "")] + _classes(form) + [action or ""])
        role_search = str(form.get("role") or "").lower() == "search" or form.find_parent(attrs={"role": "search"}) is not None
        kind = "other"
        score = min(len(questions), 3)
        if role_search or "search" in types_seen or (len(questions) == 1 and names & _SEARCH_NAMES):
            kind, score = "search", -10
        elif has_current_password or (has_password and _LOGIN_RE.search(submit_text) and not _SIGNUP_SUBMIT_RE.search(submit_text)):
            kind, score = "login", -5
        elif has_new_password or _SIGNUP_SUBMIT_RE.search(submit_text) or re.search(r"sign-?up|register|trial|join", ident, re.I):
            kind = "signup"
            score += 6 + (2 if has_email else 0) + (2 if has_new_password else 0)
        elif len(questions) <= 2 and has_email and (_NEWSLETTER_RE.search(submit_text) or _NEWSLETTER_RE.search(ident)):
            kind = "newsletter"
            score -= 3
        elif "textarea" in types_seen or _LEAD_RE.search(submit_text) or _LEAD_RE.search(ident):
            kind = "lead"
            score += 4 + (1 if has_email else 0)
        elif has_email:
            score += 2
        required_count = sum(1 for q in questions if q["required"])
        forms.append({
            "index": index,
            "zone": None,
            "block": None,
            "hidden": form_hidden,
            "kind": kind,
            "candidate_score": score,
            "primary_candidate": False,
            "action": action,
            "action_host": _host(action) or None,
            "method": str(form.get("method") or "get").lower(),
            "submit_text": submit_text,
            "questions": len(questions),
            "required_count": required_count,
            "has_email": has_email,
            "has_password": has_password,
            "has_new_password": has_new_password,
            "has_current_password": has_current_password,
            "dropped": dropped,
            "fields": questions[:max_fields],
            "_tag": form,
        })
    return forms


def _pick_primary_form(forms: List[Dict[str, Any]]) -> None:
    best = None
    for form in forms:
        if form["hidden"] or form["kind"] in ("search", "login") or form["questions"] == 0:
            continue
        score = form["candidate_score"] + (2 if form["zone"] == "hero" else 0) - (2 if form["zone"] == "footer" else 0)
        form["candidate_score"] = score
        if best is None or score > best["candidate_score"]:
            best = form
    if best is not None and best["candidate_score"] > 0:
        best["primary_candidate"] = True


# ---------------------------------------------------------------------------
# page_facts
# ---------------------------------------------------------------------------


def _media_counts(soup: Tag) -> Dict[str, int]:
    images = soup.find_all("img")
    lazy = sum(1 for img in images if str(img.get("loading") or "").lower() == "lazy" or img.get("data-src"))
    missing_alt = sum(1 for img in images if not img.has_attr("alt"))
    videos = len(soup.find_all("video"))
    for frame in soup.find_all("iframe", src=True):
        if re.search(r"youtube\.com|youtube-nocookie\.com|player\.vimeo\.com|wistia|loom\.com|vidyard", str(frame.get("src")), re.I):
            videos += 1
    return {
        "images": len(images),
        "images_lazy": lazy,
        "images_missing_alt": missing_alt,
        "svgs": len(soup.find_all("svg")),
        "videos": videos,
    }


def _headings(root: Tag) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for level in range(1, 7):
        texts = [clean_text(h, collapse=True) for h in root.find_all("h%d" % level)]
        out["h%d" % level] = dedupe_texts(t for t in texts if t)
    return out


def _collapse_heading_repeats(root: Tag) -> int:
    """Rewrite headings whose text is one sentence repeated (responsive
    variants inside one element) to a single copy, in place. Returns count."""
    changed = 0
    for heading in root.find_all(_HEADING_RE):
        text = clean_text(heading)
        collapsed = collapse_repeats(text)
        if collapsed != text:
            heading.clear()
            heading.append(NavigableString(collapsed))
            changed += 1
    return changed


def _block_summary(index: int, tag: Tag, ctas: List[Dict[str, Any]], text_limit: int = 300) -> Dict[str, Any]:
    text = clean_text(tag)
    heads = []
    level = None
    for heading in tag.find_all(_HEADING_RE):
        value = clean_text(heading, collapse=True)
        if value:
            if level is None:
                level = int(heading.name[1])
            heads.append(value)
    heads = dedupe_texts(heads)
    classes = " ".join(_classes(tag)[:3])
    return {
        "index": index,
        "tag": tag.name,
        "id": str(tag.get("id")) if tag.get("id") else None,
        "class": classes[:80] or None,
        "heading": heads[0] if heads else None,
        "heading_level": level,
        "headings": heads[:8],
        "words": word_count(text),
        "text": text[:text_limit],
        "ctas": [c["text"] for c in ctas if c.get("block") == index][:6],
        "images": len(tag.find_all("img")),
        "list_items": len(tag.find_all("li")),
        "has_blockquote": tag.find("blockquote") is not None,
        "has_details": tag.find("details") is not None,
        "has_form": tag.find("form") is not None or tag.name == "form",
        "has_table": tag.find("table") is not None,
    }


def page_facts(
    markup: Union[str, bytes, None],
    url: Optional[str] = None,
    text_chars: int = 3000,
    max_blocks: int = 60,
    max_ctas: int = 80,
) -> Dict[str, Any]:
    """Collect the facts a model needs to judge a page, as plain JSON types.

    Keys: url, title, lang, meta, headings (main content, hidden removed,
    responsive duplicates merged), outline (ordered main-content blocks),
    ctas, cta_scan, forms, embedded_forms, json_ld, social_links,
    scripts, media, word_count (all visible text), main_word_count,
    main_text (first text_chars characters of main content), is_js_shell,
    js_shell_signals, hidden_removed, notes.
    """
    if isinstance(markup, bytes):
        markup = decode_bytes(markup)[0]
    markup = markup or ""
    notes: List[str] = []
    soup = parse(markup)

    # 1. Facts that live in <head> or in scripts, read before anything is removed.
    title = extract_title(soup)
    html_tag = soup.find("html")
    lang = normalize_space(str(html_tag.get("lang"))) if html_tag is not None and html_tag.get("lang") else None
    meta = extract_meta(soup)
    json_ld = extract_json_ld(soup)
    social = extract_social_links(soup, url, json_ld["items"])
    scripts = extract_script_hosts(soup, url)
    embedded_forms = detect_embedded_forms(soup)
    forms = extract_forms(soup, url)
    shell = js_shell_signals(markup)

    # 2. Remove hidden nodes, count media, then remove non-rendered nodes.
    hidden_removed = strip_invisible(soup, hidden=True, non_rendered=False)
    media = _media_counts(soup)
    hidden_removed.update(strip_invisible(soup, hidden=False, non_rendered=True))
    body = soup.body or soup
    total_words = word_count(clean_text(body))

    # 3. Layout: chrome, blocks, hero; then CTAs and form zones.
    layout = _Layout(soup)
    ctas, cta_scan = extract_ctas(soup, layout, url, max_ctas)
    for form in forms:
        tag = form.pop("_tag")
        if form["hidden"]:
            form["zone"] = "hidden"
        else:
            form["zone"], form["block"] = layout.locate(tag)
    _pick_primary_form(forms)

    # 4. Drop chrome and describe the main-content blocks.
    layout.remove_chrome()
    repeated = _collapse_heading_repeats(body)
    if repeated:
        hidden_removed["repeated-heading-variants"] = repeated
    outline: List[Dict[str, Any]] = []
    seen_blocks: Dict[str, int] = {}
    duplicates = 0
    for index, block in enumerate(layout.blocks):
        summary = _block_summary(index, block, ctas)
        key = _key(summary["text"])
        if key and key in seen_blocks:
            duplicates += 1
            continue
        if key:
            seen_blocks[key] = index
        outline.append(summary)
    if duplicates:
        notes.append("%d responsive duplicate block(s) merged" % duplicates)
    if len(outline) > max_blocks:
        notes.append("outline truncated to %d of %d blocks" % (max_blocks, len(outline)))
        outline = outline[:max_blocks]
    content_root = layout.root
    headings = _headings(body)
    main_parts = [clean_text(b) for b in layout.blocks if _attached(b, soup)]
    main_text = "\n\n".join(dedupe_texts(p for p in main_parts if p))
    main_words = word_count(main_text)
    if not layout.blocks:
        notes.append("no main content blocks found")
    if content_root is body:
        notes.append("no <main> element; blocks taken from <body>")
    if embedded_forms:
        notes.append("form(s) rendered by third-party JavaScript: "
                     + ", ".join(f["provider"] for f in embedded_forms)
                     + " - inspect the rendered page for their fields")
    if shell["is_js_shell"]:
        notes.append("page looks client-rendered (JS shell); static facts are incomplete")

    return {
        "url": url,
        "title": title,
        "lang": lang,
        "meta": meta,
        "headings": headings,
        "outline": outline,
        "ctas": ctas,
        "cta_scan": cta_scan,
        "forms": forms,
        "embedded_forms": embedded_forms,
        "json_ld": json_ld,
        "social_links": social,
        "scripts": scripts,
        "media": media,
        "word_count": total_words,
        "main_word_count": main_words,
        "main_text": main_text[:text_chars] if text_chars else "",
        "main_text_truncated": bool(text_chars) and len(main_text) > text_chars,
        "is_js_shell": shell["is_js_shell"],
        "js_shell_signals": shell,
        "hidden_removed": hidden_removed,
        "notes": notes,
    }


__all__ = [
    "PARSER", "parse", "decode_bytes", "sniff_meta_charset",
    "normalize_space", "clean_text", "collapse_repeats", "word_count", "dedupe_texts",
    "NON_RENDERED_TAGS", "hidden_reason", "is_hidden", "strip_invisible", "visible_text",
    "remove_responsive_duplicates",
    "js_shell_signals", "site_domain", "extract_title", "extract_meta", "extract_json_ld",
    "classify_social", "extract_social_links", "extract_script_hosts", "detect_embedded_forms",
    "classify_href", "classify_cta_text", "extract_ctas", "extract_forms", "page_facts",
]
