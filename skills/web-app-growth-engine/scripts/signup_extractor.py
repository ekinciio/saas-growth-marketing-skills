#!/usr/bin/env python3
"""Signup step fact extractor for web-app-growth-engine.

Reads one signup page (a URL, a saved or rendered HTML file, or '-' for
stdin) and returns the facts a model needs to write a friction ledger:
the signup step and its questions, the sign-in options offered (Google,
Microsoft, Apple, GitHub, ChatGPT, SAML SSO, passkeys ...), bot protection
as typed evidence, card fields, consent, verification and plan hints,
the text around the form, and links to the signup page when the input is
a homepage. It never scores and never recommends: judging is done by the
model with references/signup-friction-rubric.md.

    python3 signup_extractor.py https://app.example.com/signup --json
    python3 signup_extractor.py rendered.html --page-url https://app.example.com/signup \\
        --step-label "step 2: after Continue with email" --json --out step2.json

A "step" is any group of visible inputs and controls that starts an
account, with or without a <form> element (many SSO-first pages have no
form at all). Every form and the formless group are returned as candidates
with a deterministic score and the reasons for it; the best one is the
primary step.

Output (JSON envelope from _growthkit.cli):
    signup_status   ok | no_form | blocked | fetch_error | js_shell
    source, fetch, page
    primary_step    questions, actions, consent boxes, dropped inputs
    candidates      every form and formless group with kind and score
    auth_options    provider, evidence (type, value, zone), control_seen
    auth_methods    email path, password at signup, passkey, reveal controls
    bot_protection  vendor, mode (invisible | visible_checkbox | managed |
                    risk_based | unknown), evidence. Never a penalty.
    payment         card fields in the signup step (form-level evidence
                    only) and page-text mentions as context snippets
    hints           verification, work email, plan and trial, legal consent
    context         step text, panel text, proof candidates, page excerpt
    signup_links    signup and login links found on the page
    coverage        render_recommended and its reasons, what static HTML
                    cannot show

Exit codes: 0 a signup step was found, 2 usage error, 3 blocked or
unreachable, 4 partial (page truncated), 5 nothing to analyze (no signup
step, or a JavaScript shell).
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qsl, urlparse

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _growthkit import cli  # noqa: E402
from _growthkit import html as gk_html  # noqa: E402
from _growthkit import http as gk_http  # noqa: E402

Tag = gk_html.Tag

TOOL = "signup_extractor"
SNIPPET_RADIUS = 80
MAX_SNIPPETS = 6

# ---------------------------------------------------------------------------
# Sign-in providers
# ---------------------------------------------------------------------------

# (display name, regex for the name in text or attributes)
PROVIDERS: List[Tuple[str, str]] = [
    ("Google", r"google|gmail"),
    ("Microsoft", r"microsoft|azure(?:\s?ad)?|entra(?:\s?id)?|office\s?365|outlook"),
    ("Apple", r"apple"),
    ("GitHub", r"git\s?hub"),
    ("GitLab", r"git\s?lab"),
    ("Bitbucket", r"bitbucket"),
    ("Slack", r"slack"),
    ("LinkedIn", r"linked\s?in"),
    ("Facebook", r"facebook"),
    ("X (Twitter)", r"twitter"),
    ("ChatGPT", r"chat\s?gpt|openai"),
    ("Atlassian", r"atlassian"),
    ("Salesforce", r"salesforce"),
    ("Discord", r"discord"),
    ("Okta", r"okta"),
    ("Amazon", r"amazon"),
    ("Yahoo", r"yahoo"),
    ("Enterprise SSO", r"saml(?:\s?sso)?|single[\s-]sign[\s-]on|enterprise\s?sso|sso"),
    ("Passkey", r"pass\s?keys?|webauthn|face\s?id|touch\s?id"),
]
_PROVIDER_RES = [(name, re.compile(r"(?<![a-z0-9])(?:%s)(?![a-z0-9])" % pattern, re.I))
                 for name, pattern in PROVIDERS]

# Words for "with" in common UI languages: "Continue with Google",
# "Google ile devam et", "Mit Google anmelden", "Continuer avec Google".
_WITH_BEFORE = r"(?:with|using|via|mit|avec|con|com|met|z|med|tramite|przez)"
_WITH_AFTER = r"(?:ile|ilə|で|を使用)"

# Path segments of first-party auth routes: /auth/google/login,
# /auth/google_oauth2?state=signup, /users/auth/github, /sso/saml, /oauth/microsoft.
_ROUTE_PROVIDERS = (
    r"google|gmail|github|gitlab|bitbucket|microsoft|azure(?:ad|_ad|-ad)?|entra|office365|live|"
    r"windowslive|apple|slack|linkedin|facebook|twitter|chatgpt|openai|atlassian|salesforce|"
    r"discord|okta|amazon|yahoo|saml|sso|passkey|webauthn"
)
_AUTH_ROUTE_RE = re.compile(
    r"/(?:auth|oauth2?|login|log-in|signin|sign-in|signup|sign-up|sso|connect|social|accounts?|"
    r"session|sessions|identity|idp|users/auth|api/auth/signin)/(?:[\w.-]+/){0,2}?"
    r"(?:oauth[_-]?)?(?P<p>" + _ROUTE_PROVIDERS + r")(?:[_-]?oauth2?|[_-]login|[_-]signin)?(?=[/?#._-]|$)",
    re.I,
)
_AUTH_QUERY_KEYS = {
    "provider", "connection", "idp", "strategy", "identity_provider", "social", "oauth_provider",
    "auth_provider", "login_provider", "kc_idp_hint", "identity_provider_hint",
}
_AUTH_QUERY_VALUE_RE = re.compile(r"^(?:oauth[_-]?)?(?P<p>" + _ROUTE_PROVIDERS + r")(?:[_-]?oauth2)?$", re.I)

# Third-party authorization endpoints (the browser leaves the site to sign in).
_OAUTH_HOSTS: List[Tuple[str, re.Pattern]] = [
    ("Google", re.compile(r"accounts\.google\.com/(?:o/oauth2|signin/oauth|gsi)", re.I)),
    ("GitHub", re.compile(r"github\.com/login/oauth", re.I)),
    ("GitLab", re.compile(r"gitlab\.com/oauth", re.I)),
    ("Bitbucket", re.compile(r"bitbucket\.org/site/oauth2", re.I)),
    ("Microsoft", re.compile(r"login\.microsoftonline\.com|login\.live\.com", re.I)),
    ("Apple", re.compile(r"appleid\.apple\.com/auth", re.I)),
    ("Slack", re.compile(r"slack\.com/(?:oauth|openid)", re.I)),
    ("LinkedIn", re.compile(r"linkedin\.com/oauth", re.I)),
    ("Facebook", re.compile(r"facebook\.com/(?:v\d+\.\d+/)?dialog/oauth", re.I)),
    ("X (Twitter)", re.compile(r"(?:twitter|x)\.com/i/oauth2|api\.twitter\.com/oauth", re.I)),
    ("ChatGPT", re.compile(r"auth\.openai\.com/|chatgpt\.com/(?:auth|oauth)", re.I)),
    ("Discord", re.compile(r"discord(?:app)?\.com/(?:api/)?oauth2", re.I)),
    ("Atlassian", re.compile(r"auth\.atlassian\.com/authorize", re.I)),
    ("Salesforce", re.compile(r"login\.salesforce\.com/services/oauth2", re.I)),
    ("Okta", re.compile(r"\.okta\.com/oauth2", re.I)),
]

# Identity SDKs that render a sign-in button or prompt client-side.
_SDK_SCRIPTS: List[Tuple[str, re.Pattern, str]] = [
    ("Google", re.compile(r"accounts\.google\.com/gsi/client", re.I), "Google Identity Services script"),
    ("Google", re.compile(r"apis\.google\.com/js/platform\.js", re.I), "Google Sign-In platform script (legacy)"),
    ("Apple", re.compile(r"appleid\.cdn-apple\.com/appleauth/static/jsapi/appleid/.*appleid\.auth\.js", re.I),
     "Sign in with Apple JS"),
    ("Microsoft", re.compile(r"msal-browser|alcdn\.msauth\.net", re.I), "Microsoft MSAL.js"),
]
_SDK_INLINE: List[Tuple[str, re.Pattern, str]] = [
    ("Apple", re.compile(r"AppleID\.auth\.init\s*\(", re.I), "AppleID.auth.init() call"),
    ("Google", re.compile(r"google\.accounts\.id\.(?:initialize|renderButton|prompt)\s*\(", re.I),
     "google.accounts.id call"),
]

# Attribute values (id, data-*, class tokens) that name an auth control:
# "signUpWithGoogle", "sign-up-google", "social-login-github", "btn-google".
_AUTH_WORD = r"(?:sign[-_]?up|sign[-_]?in|signin|signup|log[-_]?in|login|auth|oauth|sso|social|continue)"
_ATTR_AUTH_RE = re.compile(
    r"%s[-_]?(?:with[-_]?)?(?:by[-_]?)?(?P<a>[a-z]+)|(?P<b>[a-z]+)[-_]?(?:%s|button|btn)\b|(?:btn|button)[-_](?P<c>[a-z]+)"
    % (_AUTH_WORD, _AUTH_WORD),
    re.I,
)

_EMAIL_PATH_RE = re.compile(
    r"^(?:(?:continue|sign\s?up|sign\s?in|log\s?in|register|join|start|get started)\s+(?:with|using|via)\s+"
    r"(?:your\s+|an?\s+)?(?:work\s+|business\s+)?e-?mail(?:\s+address)?|(?:use|enter)\s+(?:your\s+)?e-?mail(?:\s+instead)?|"
    r"e-?mail(?:\s+address)?|sign\s?up\s+with\s+e-?mail\s+instead)$",
    re.I,
)
_REVEAL_RE = re.compile(
    r"^(?:continue|sign\s?up|register|join|get started)\s+(?:with|using)\s+(?:your\s+|an?\s+)?(?:work\s+)?e-?mail"
    r"|^(?:use|enter)\s+(?:your\s+)?e-?mail|^(?:more|other)\s+(?:sign[\s-]?(?:up|in)\s+)?(?:options|ways|methods)"
    r"|^show\s+(?:more|all)\s+(?:options|providers)|^sign\s?up\s+with\s+e-?mail\s+instead",
    re.I,
)
_SIGNUP_ACTION_RE = re.compile(
    r"sign\s?up|create (?:an |your |my |a free |a )?(?:account|workspace|team|project)|get started|"
    r"start (?:for )?free|start (?:your |my |a )?(?:free )?trial|try (?:it |\w+ )?(?:for )?free|register|"
    r"\bjoin\b|get (?:early )?access|request access|claim|kostenlos|registrieren|inscri|cr[ée]er|"
    r"crear|registr|kay[ıi]t|[üu]cretsiz",
    re.I,
)
_CONTINUE_RE = re.compile(r"^(?:continue|next|weiter|continuer|continuar|devam(?: et)?|proceed|submit)\b", re.I)
_LOGIN_ACTION_RE = re.compile(r"\blog\s?in\b|\bsign\s?in\b|\banmelden\b|\bconnexion\b|giri[şs] yap", re.I)
_SUBSCRIBE_RE = re.compile(r"subscribe|newsletter|notify me|get updates|stay (?:in the loop|updated)", re.I)
_UI_CONTROL_RE = re.compile(
    r"^(?:close|menu|open menu|toggle\b.*|search|previous|next slide|play|pause|accept(?: all)?(?: cookies)?|"
    r"show|hide|show password|hide password|copy|edit|change|back|"
    r"reject(?: all)?(?: cookies)?|decline|dismiss|skip\b.*|×|x)$",
    re.I,
)

# ---------------------------------------------------------------------------
# Bot protection, payment, hints
# ---------------------------------------------------------------------------

_RECAPTCHA_SCRIPT_RE = re.compile(r"(?:google\.com|recaptcha\.net)/recaptcha/(?:api|enterprise)\.js(?P<q>\?[^\"'\s]*)?", re.I)
_HCAPTCHA_SCRIPT_RE = re.compile(r"(?:js\.)?hcaptcha\.com/1/api\.js", re.I)
_TURNSTILE_SCRIPT_RE = re.compile(r"challenges\.cloudflare\.com/turnstile", re.I)
_ARKOSE_RE = re.compile(r"arkoselabs\.com|funcaptcha\.com", re.I)
_FRIENDLY_RE = re.compile(r"friendlycaptcha|frc-captcha", re.I)
_GEETEST_RE = re.compile(r"geetest", re.I)
_AWS_CAPTCHA_RE = re.compile(r"captcha\.awswaf\.com|jsapi\.js\?.*awswaf|awswaf.*captcha", re.I)
_RECAPTCHA_INLINE_RE = re.compile(r"grecaptcha\.(?:enterprise\.)?(?P<call>execute|render|ready)\s*\(", re.I)
_BADGE_HIDDEN_RE = re.compile(r"\.grecaptcha-badge\s*\{[^}]*(?:visibility\s*:\s*hidden|display\s*:\s*none|opacity\s*:\s*0)", re.I)
_DISCLOSURE_RE = re.compile(r"protected by (?:re)?captcha|recaptcha and the google|invisible recaptcha|protected by hcaptcha", re.I)

_CARD_AUTOCOMPLETE = {"cc-number", "cc-exp", "cc-exp-month", "cc-exp-year", "cc-csc", "cc-name", "cc-type"}
_CARD_NAME_RE = re.compile(
    r"card[\s_-]?(?:number|no\b|num)|cardnumber|\bcc[\s_-]?(?:num|number)\b|\bpan\b|credit[\s_-]?card|"
    r"\bcvc\b|\bcvv2?\b|security[\s_-]?code|expir(?:y|ation)[\s_-]?(?:date|month|year)?|\bmm\s*/\s*yy\b|"
    r"karten(?:nummer)?|num[ée]ro de carte|n[uú]mero de tarjeta|kart numaras",
    re.I,
)
_PAYMENT_FRAME_RE = re.compile(
    r"js\.stripe\.com|checkout\.stripe\.com|elements-inner-card|braintreegateway|braintree-api|"
    r"hosted-fields|checkoutshopper|adyen|cdn\.paddle\.com|paddle\.com/checkout|js\.chargebee\.com|"
    r"\.chargebee\.com/hosted|js\.recurly\.com|api\.recurly\.com|frames\.checkout\.com|"
    r"pay\.google\.com|paypal\.com/sdk",
    re.I,
)
_PAYMENT_CLASS_RE = re.compile(
    r"(?:^|\s)(?:StripeElement|__PrivateStripeElement|braintree-hosted-field|adyen-checkout__card|"
    r"recurly-element-card|cb-card|card-element|CardField)(?:\s|$|-)",
    re.I,
)
_PAYMENT_SDK_RE = re.compile(r"js\.stripe\.com/v\d|js\.braintreegateway\.com|checkoutshopper-live|cdn\.paddle\.com|js\.chargebee\.com|js\.recurly\.com", re.I)

_PAYMENT_MENTION_RE = re.compile(
    r"credit[\s-]?card|debit card|card (?:details|info(?:rmation)?|number)|payment (?:details|info(?:rmation)?|method)|"
    r"billing (?:details|info(?:rmation)?)|\bno cc\b|valid payment",
    re.I,
)
_PAYMENT_NEGATION_RE = re.compile(
    r"\bno\b[^.!?]{0,20}(?:credit[\s-]?)?card|without (?:a |any |your )?(?:credit[\s-]?)?card|"
    r"card (?:is )?not (?:required|needed)|\bno cc\b|no payment (?:details|info|method)|"
    r"never ask(?:s)? for (?:a |your )?(?:credit[\s-]?)?card|(?:credit[\s-]?)?card (?:not|isn.t) (?:required|needed)",
    re.I,
)
_VERIFY_RE = re.compile(
    r"verif(?:y|ication)|confirm(?:ation)? (?:your )?(?:e-?mail|code|account)|check your (?:e-?mail|inbox)|"
    r"we(?:'ll| will) (?:send|e-?mail) (?:you )?(?:a |an )?(?:code|link|e-?mail)|magic link|sign-?in link|"
    r"one-time (?:code|password|passcode)|\botp\b|\d-digit code|activation (?:link|e-?mail)|"
    r"temporary (?:login |sign-?in )?code",
    re.I,
)
_WORK_EMAIL_RE = re.compile(
    r"(?:work|business|company|corporate|professional) e-?mail|personal e-?mail(?:s| addresses)? (?:are )?not|"
    r"use your (?:work|company) e-?mail|gmail(?:\.com)? (?:is |are )?not (?:accepted|allowed)",
    re.I,
)
_PLAN_RE = re.compile(
    r"\d+[\s-]?day(?:s)? (?:free )?trial|free trial|free (?:plan|forever|tier|for (?:up to|ever))|"
    r"free for \d+|no (?:credit )?card|cancel any ?time|reverse trial|"
    r"(?:starts?|begins?) (?:on|with) (?:a |the )?(?:free|pro|premium|paid)|upgrade any ?time|"
    r"(?:trial|plan) (?:ends|expires)|billed (?:monthly|annually|after)",
    re.I,
)
_LEGAL_RE = re.compile(
    r"by (?:signing up|clicking|continuing|creating (?:an |your )?account|registering|proceeding|"
    r"using|submitting|entering)[^.]{0,120}(?:agree|accept|consent|acknowledge)|"
    r"(?:i )?agree to (?:the |our )?(?:terms|privacy)|terms of (?:service|use)",
    re.I,
)
_CONSENT_LABEL_RE = re.compile(
    r"terms|privacy|agree|consent|accept|policy|marketing|newsletter|updates|news|offers|"
    r"promotional|communications|kvkk|gdpr|einwillig|zustimm",
    re.I,
)
_RATING_RE = re.compile(r"\b[0-5](?:\.\d)?\s?(?:/\s?5|out of 5|stars?)\b|\b(?:g2|capterra|trustpilot|trustradius|getapp)\b", re.I)

# Purposes of a question, from autocomplete, type, name and label.
_PURPOSES: List[Tuple[str, re.Pattern]] = [
    ("email", re.compile(r"e-?mail|e-?posta|courriel", re.I)),
    ("username", re.compile(r"user[\s_-]?name|login[\s_-]?name|handle|kullan[ıi]c[ıi] ad[ıi]", re.I)),
    ("password", re.compile(r"pass(?:word|wd|phrase)?\b|\bpwd\b|\bpw\b|kennwort|mot de passe|contrase|[şs]ifre|parola", re.I)),
    ("country", re.compile(r"country|region|\bstate\b|province|land\b|[üu]lke", re.I)),
    ("first_name", re.compile(r"first[\s_-]?name|given[\s_-]?name|fname|vorname|pr[ée]nom", re.I)),
    ("last_name", re.compile(r"last[\s_-]?name|family[\s_-]?name|surname|lname|nachname", re.I)),
    ("full_name", re.compile(r"full[\s_-]?name|your name|^name$|\bname\b|ad[ıi]n[ıi]z|ad soyad", re.I)),
    ("company_size", re.compile(r"employees|company[\s_-]?size|team[\s_-]?size|headcount|how many (?:people|employees)", re.I)),
    ("company", re.compile(r"company|organi[sz]ation|business name|\borg\b|employer|firma|[şs]irket", re.I)),
    ("role", re.compile(r"job|title|role|position|function|department", re.I)),
    ("phone", re.compile(r"phone|mobile|tel\b|telefon|cell", re.I)),
    ("website", re.compile(r"website|domain|url|site", re.I)),
    ("workspace", re.compile(r"workspace|subdomain|team name|account name|site name|store name", re.I)),
    ("use_case", re.compile(r"use case|how (?:will|do) you|what (?:will|brings)|goal|interest|purpose", re.I)),
    ("card", _CARD_NAME_RE),
]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _attr_text(tag: Tag, name: str) -> str:
    value = tag.get(name)
    if isinstance(value, list):
        value = " ".join(str(v) for v in value)
    return gk_html.normalize_space(str(value or ""))


def _classes(tag: Tag) -> List[str]:
    value = tag.get("class") if isinstance(tag, Tag) and tag.attrs else None
    if not value:
        return []
    if isinstance(value, str):
        value = value.split()
    return [str(c) for c in value]


def _control_text(tag: Tag) -> str:
    """Visible text of a control, falling back to aria-label, title, value and image alt."""
    text = gk_html.clean_text(tag, collapse=True)
    if not text:
        for attr in ("aria-label", "title", "value"):
            text = _attr_text(tag, attr)
            if text:
                break
    if not text:
        img = tag.find("img", alt=True)
        if img is not None:
            text = _attr_text(img, "alt")
    return text[:120]


def _absolute(href: Optional[str], base: Optional[str]) -> Optional[str]:
    if not href:
        return None
    value = str(href).strip()
    if not value or value.lower().startswith(("javascript:", "#", "data:", "mailto:", "tel:")):
        return None
    if base:
        try:
            from urllib.parse import urljoin
            return urljoin(base, value)
        except ValueError:
            return value
    return value


def _snippets(text: str, pattern: re.Pattern, limit: int = MAX_SNIPPETS,
              radius: int = SNIPPET_RADIUS) -> List[Dict[str, Any]]:
    """Merged context windows around regex matches in visible text."""
    windows: List[Tuple[int, int]] = []
    for match in pattern.finditer(text or ""):
        start = max(0, match.start() - radius)
        end = min(len(text), match.end() + radius)
        if windows and start <= windows[-1][1]:
            windows[-1] = (windows[-1][0], max(windows[-1][1], end))
        else:
            windows.append((start, end))
        if len(windows) > limit * 3:
            break
    out: List[Dict[str, Any]] = []
    seen = set()
    for start, end in windows:
        snippet = text[start:end].strip()
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."
        key = gk_html.normalize_space(snippet).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"text": snippet})
        if len(out) >= limit:
            break
    return out


def _zone(tag: Tag) -> str:
    """Where a visible element sits: main, dialog, nav, footer or cookie."""
    node = tag
    while isinstance(node, Tag):
        name = node.name
        role = str(node.get("role") or "").lower()
        if name == "nav" or role == "navigation":
            return "nav"
        if role in ("dialog", "alertdialog") or name == "dialog" or str(node.get("aria-modal") or "").lower() == "true":
            return "dialog"
        if role == "contentinfo" or (name == "footer" and not _in_sectioning(node)):
            return "footer"
        if role == "banner" or (name == "header" and not _in_sectioning(node)):
            h1 = node.find("h1")
            if h1 is None or gk_html.word_count(gk_html.clean_text(h1)) < 3:
                return "nav"
        ident = " ".join([str(node.get("id") or "")] + _classes(node)).lower()
        if ident and re.search(r"onetrust|cookiebot|cookieyes|osano|didomi|usercentrics|trustarc|"
                               r"(?:^|[-_\s])cookies?(?:[-_\s]|$)|cookie-?banner|cookie-?consent", ident):
            return "cookie"
        node = node.parent
    return "main"


def _in_sectioning(tag: Tag) -> bool:
    parent = tag.parent
    while isinstance(parent, Tag):
        if parent.name in ("article", "section", "aside", "blockquote", "figure", "li", "form"):
            return True
        parent = parent.parent
    return False


def _attached(tag: Tag, root: Tag) -> bool:
    node = tag
    while node is not None:
        if node is root:
            return True
        node = node.parent
    return False


def _ancestors(tag: Tag) -> List[Tag]:
    out = []
    node = tag
    while isinstance(node, Tag):
        out.append(node)
        node = node.parent
    return out


def _lowest_common_ancestor(tags: List[Tag]) -> Optional[Tag]:
    if not tags:
        return None
    common = _ancestors(tags[0])
    for tag in tags[1:]:
        ids = {id(t) for t in _ancestors(tag)}
        common = [t for t in common if id(t) in ids]
        if not common:
            return None
    return common[0]


def _contains(ancestor: Tag, node: Tag) -> bool:
    current = node
    while current is not None:
        if current is ancestor:
            return True
        current = current.parent
    return False


def _provider_in(text: str) -> Optional[str]:
    for name, pattern in _PROVIDER_RES:
        if pattern.search(text or ""):
            return name
    return None


def _provider_from_token(token: str) -> Optional[str]:
    token = (token or "").lower()
    if not token:
        return None
    for name, pattern in _PROVIDER_RES:
        if pattern.fullmatch(token):
            return name
    aliases = {"azuread": "Microsoft", "live": "Microsoft", "windowslive": "Microsoft", "office365": "Microsoft",
               "entra": "Microsoft", "x": "X (Twitter)", "openai": "ChatGPT", "saml": "Enterprise SSO",
               "sso": "Enterprise SSO", "webauthn": "Passkey", "gmail": "Google"}
    if token in aliases:
        return aliases[token]
    if token.startswith("azure"):
        return "Microsoft"
    return None


_AUTH_VERB_RE = re.compile(
    r"\b(?:continue|sign[\s-]?up|sign[\s-]?in|log[\s-]?in|login|register|join|get started|start|create|"
    r"anmelden|registrieren|continuer|s.inscrire|connexion|continuar|registrarse|iniciar|entrar|"
    r"devam|kaydol|giri[sş]|inloggen|accedi|registrati)\b",
    re.I,
)


def _text_provider(text: str) -> Tuple[Optional[str], str]:
    """(provider, strength) for a control's text.

    strength: 'auth_with' ("Sign up with Google", "Google ile devam et"),
    'with' ("with Google" without an auth verb), 'exact' (just "Google",
    "Google account"), 'weak' (a short text that names a provider).
    """
    value = gk_html.normalize_space(text)
    if not value or len(value) > 80:
        return None, ""
    for name, pattern in _PROVIDER_RES:
        match = pattern.search(value)
        if not match:
            continue
        before = value[:match.start()].strip()
        after = value[match.end():].strip()
        with_before = re.search(r"(?:^|\s)%s\s*(?:your\s+)?(?:an?\s+)?$" % _WITH_BEFORE, before, re.I)
        with_after = re.match(r"^%s\b" % _WITH_AFTER, after, re.I)
        if with_before or with_after:
            verb = _AUTH_VERB_RE.search(before) or _AUTH_VERB_RE.search(after)
            return name, ("auth_with" if verb else "with")
        if _AUTH_VERB_RE.search(after) and len(value.split()) <= 5:
            return name, "auth_with"  # "Google ile devam et", "Google Sign-In"
        stripped = re.sub(r"\b(?:logo|icon|account|button)\b", "", value, flags=re.I)
        if pattern.fullmatch(gk_html.normalize_space(stripped)):
            return name, "exact"
        if len(value.split()) <= 5:
            return name, "weak"
    return None, ""


def _href_provider(href: str) -> Optional[Tuple[str, str]]:
    """(provider, evidence kind) when a URL is an auth route or an OAuth endpoint."""
    if not href:
        return None
    for name, pattern in _OAUTH_HOSTS:
        if pattern.search(href):
            return name, "oauth-endpoint"
    try:
        parsed = urlparse(href)
    except ValueError:
        return None
    match = _AUTH_ROUTE_RE.search(parsed.path or "")
    if match:
        provider = _provider_from_token(match.group("p"))
        if provider:
            return provider, "auth-route"
    for key, value in parse_qsl(parsed.query or "", keep_blank_values=False):
        if key.lower() in _AUTH_QUERY_KEYS:
            qmatch = _AUTH_QUERY_VALUE_RE.match(value.strip())
            if qmatch:
                provider = _provider_from_token(qmatch.group("p"))
                if provider:
                    return provider, "auth-query"
    return None


def _attr_provider(tag: Tag) -> Optional[Tuple[str, str]]:
    """(provider, attribute value) from id, data-* and class tokens of an element."""
    values: List[str] = []
    for name, value in (tag.attrs or {}).items():
        if name == "id" or name.startswith("data-"):
            if isinstance(value, list):
                value = " ".join(str(v) for v in value)
            values.append(str(value))
    values.extend(_classes(tag))
    for value in values:
        if not value or len(value) > 120:
            continue
        flat = re.sub(r"([a-z])([A-Z])", r"\1-\2", value)
        for match in _ATTR_AUTH_RE.finditer(flat):
            token = match.group("a") or match.group("b") or match.group("c")
            provider = _provider_from_token(token)
            if provider and provider not in ("Enterprise SSO",):
                return provider, value
    return None


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def _bot_protection(soup: Tag, visible_text: str) -> List[Dict[str, Any]]:
    """Typed bot-protection evidence. Comments and <style> never count as presence."""
    found: Dict[str, Dict[str, Any]] = {}

    modes: Dict[str, List[str]] = {}

    def add(vendor: str, mode: str, kind: str, value: str) -> None:
        entry = found.setdefault(vendor, {"vendor": vendor, "mode": "unknown", "evidence": []})
        modes.setdefault(vendor, []).append(mode)
        item = {"type": kind, "value": value[:120], "mode": mode}
        if item not in entry["evidence"] and len(entry["evidence"]) < 6:
            entry["evidence"].append(item)

    for script in soup.find_all("script"):
        src = str(script.get("src") or "")
        if src:
            match = _RECAPTCHA_SCRIPT_RE.search(src)
            if match:
                query = match.group("q") or ""
                render = re.search(r"[?&]render=([^&]+)", query)
                if render and render.group(1).lower() not in ("explicit", "onload"):
                    add("recaptcha", "invisible", "script", "api.js?render=<site key> (score-based, no checkbox)")
                else:
                    add("recaptcha", "unknown", "script", src)
            if _HCAPTCHA_SCRIPT_RE.search(src):
                add("hcaptcha", "unknown", "script", src)
            if _TURNSTILE_SCRIPT_RE.search(src):
                add("turnstile", "managed", "script", src)
            if _ARKOSE_RE.search(src):
                add("arkose", "risk_based", "script", src)
            if _FRIENDLY_RE.search(src):
                add("friendly_captcha", "managed", "script", src)
            if _GEETEST_RE.search(src):
                add("geetest", "unknown", "script", src)
            if _AWS_CAPTCHA_RE.search(src):
                add("aws_waf_captcha", "unknown", "script", src)
        elif script.string and "ld+json" not in str(script.get("type") or "").lower():
            body = str(script.string)[:200000]
            inline = _RECAPTCHA_INLINE_RE.search(body)
            if inline:
                mode = "invisible" if inline.group("call").lower() == "execute" else "unknown"
                add("recaptcha", mode, "inline-script", "grecaptcha.%s()" % inline.group("call"))
    for frame in soup.find_all("iframe", src=True):
        src = str(frame.get("src"))
        if re.search(r"recaptcha/(?:api2|enterprise)/anchor", src, re.I):
            mode = "invisible" if re.search(r"[?&]size=invisible", src, re.I) else "visible_checkbox"
            add("recaptcha", mode, "iframe", src.split("?")[0] + (" (size=invisible)" if mode == "invisible" else ""))
        elif re.search(r"recaptcha/(?:api2|enterprise)/bframe", src, re.I):
            add("recaptcha", "unknown", "iframe", "challenge frame (bframe, opens only when a challenge is shown)")
        elif re.search(r"hcaptcha\.com", src, re.I):
            mode = "invisible" if re.search(r"size=invisible", src, re.I) else "unknown"
            add("hcaptcha", mode, "iframe", src.split("?")[0])
        elif _TURNSTILE_SCRIPT_RE.search(src):
            add("turnstile", "managed", "iframe", src.split("?")[0])
        elif _ARKOSE_RE.search(src):
            add("arkose", "risk_based", "iframe", src.split("?")[0])
    for tag in soup.find_all(True):
        if not tag.attrs:
            continue
        classes = " ".join(_classes(tag)).lower()
        size = str(tag.get("data-size") or "").lower()
        if "g-recaptcha" in classes.split():
            if size == "invisible" or tag.name in ("button", "input"):
                add("recaptcha", "invisible", "widget", "%s.g-recaptcha%s" % (
                    tag.name, ' data-size="invisible"' if size == "invisible" else " bound to a button"))
            elif gk_html.is_hidden(tag):
                add("recaptcha", "unknown", "widget", "hidden div.g-recaptcha")
            else:
                add("recaptcha", "visible_checkbox", "widget", 'div.g-recaptcha without data-size="invisible"')
        if "grecaptcha-badge" in classes.split():
            add("recaptcha", "invisible", "widget", "div.grecaptcha-badge (shown only for invisible or v3)")
        if "h-captcha" in classes.split():
            if size == "invisible" or tag.name in ("button", "input"):
                add("hcaptcha", "invisible", "widget", "%s.h-captcha (invisible)" % tag.name)
            elif not gk_html.is_hidden(tag):
                add("hcaptcha", "visible_checkbox", "widget", 'div.h-captcha without data-size="invisible"')
        if "cf-turnstile" in classes.split() or tag.has_attr("data-turnstile-sitekey"):
            appearance = str(tag.get("data-appearance") or "").lower()
            mode = "invisible" if appearance == "interaction-only" else "managed"
            add("turnstile", mode, "widget", "cf-turnstile%s" % (
                ' data-appearance="interaction-only"' if appearance else ""))
        if "frc-captcha" in classes.split():
            add("friendly_captcha", "managed", "widget", "div.frc-captcha")
    for style in soup.find_all("style"):
        css = str(style.string or "")
        if _BADGE_HIDDEN_RE.search(css):
            add("recaptcha", "invisible", "css", ".grecaptcha-badge hidden by the site's CSS")
    disclosure = _DISCLOSURE_RE.search(visible_text or "")
    if disclosure:
        vendor = "hcaptcha" if "hcaptcha" in disclosure.group(0).lower() else "recaptcha"
        add(vendor, "invisible", "disclosure-text", disclosure.group(0))
    for vendor, entry in found.items():
        seen = set(modes.get(vendor) or [])
        if "visible_checkbox" in seen and "invisible" in seen:
            entry["mode"] = "conflicting"  # both kinds of evidence; a screenshot decides
        else:
            for mode in ("visible_checkbox", "invisible", "managed", "risk_based"):
                if mode in seen:
                    entry["mode"] = mode
                    break
    return list(found.values())


def _auth_sdks(soup: Tag) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen = set()
    for script in soup.find_all("script"):
        src = str(script.get("src") or "")
        candidates = _SDK_SCRIPTS if src else _SDK_INLINE
        text = src if src else str(script.string or "")[:200000]
        for provider, pattern, label in candidates:
            if pattern.search(text) and (provider, label) not in seen:
                seen.add((provider, label))
                out.append({"provider": provider, "type": "sdk-script" if src else "sdk-inline", "value": label})
    for tag in soup.find_all(True, id=re.compile(r"^(?:g_id_onload|appleid-signin)$")):
        provider = "Google" if tag.get("id") == "g_id_onload" else "Apple"
        if (provider, "markup") not in seen:
            seen.add((provider, "markup"))
            out.append({"provider": provider, "type": "sdk-markup", "value": "#%s" % tag.get("id")})
    for tag in soup.find_all(class_=re.compile(r"^g_id_signin$")):
        if ("Google", "markup") not in seen:
            seen.add(("Google", "markup"))
            out.append({"provider": "Google", "type": "sdk-markup", "value": ".g_id_signin"})
    # Empty mount points that a script fills with a sign-in button:
    # <div id="signinBtnDiv" data-mc-el="signUpWithGoogle"></div>.
    for tag in soup.find_all(True):
        if tag.name in ("a", "button", "input", "script", "style", "meta", "link") or not tag.attrs:
            continue
        if str(tag.get("role") or "").lower() in ("button", "link"):
            continue
        attrs = {k: v for k, v in tag.attrs.items() if k == "id" or k.startswith("data-")}
        if not attrs:
            continue
        found = _attr_provider(gk_html.BeautifulSoup("", gk_html.PARSER).new_tag("div", attrs=attrs))
        if found and (found[0], "mount") not in seen and not gk_html.is_hidden(tag):
            seen.add((found[0], "mount"))
            out.append({"provider": found[0], "type": "markup-attribute", "value": found[1][:80]})
    return out


def _payment_raw(soup: Tag) -> Tuple[List[Tuple[set, str]], List[str]]:
    """Payment iframes or hosted-field containers and payment SDK scripts.

    Each frame is returned as (ids of its ancestors, label): iframes are
    removed with the other non-rendered nodes later, so containment in a
    signup step is decided from the ancestors recorded now.
    """
    frames: List[Tuple[set, str]] = []
    for frame in soup.find_all("iframe"):
        src = str(frame.get("src") or "") + " " + str(frame.get("name") or "") + " " + str(frame.get("title") or "")
        if _PAYMENT_FRAME_RE.search(src) and not gk_html.is_hidden(frame.parent if frame.parent else frame):
            frames.append(({id(a) for a in _ancestors(frame)}, "iframe: %s" % gk_html.normalize_space(src)[:100]))
    for tag in soup.find_all(class_=True):
        if _PAYMENT_CLASS_RE.search(" ".join(_classes(tag))) and not gk_html.is_hidden(tag):
            frames.append(({id(a) for a in _ancestors(tag)}, "hosted card field: .%s" % " .".join(_classes(tag)[:2])))
    sdks = []
    for script in soup.find_all("script", src=True):
        match = _PAYMENT_SDK_RE.search(str(script.get("src")))
        if match and match.group(0) not in sdks:
            sdks.append(match.group(0))
    return frames, sdks


def _purpose(question: Dict[str, Any]) -> str:
    autocomplete = (question.get("autocomplete") or "").lower()
    qtype = (question.get("type") or "").lower()
    if autocomplete in _CARD_AUTOCOMPLETE:
        return "card"
    if "new-password" in autocomplete or qtype == "password":
        return "password"
    if qtype == "email" or "email" in autocomplete:
        return "email"
    if qtype == "tel" or autocomplete.startswith("tel"):
        return "phone"
    if autocomplete in ("given-name",):
        return "first_name"
    if autocomplete in ("family-name",):
        return "last_name"
    if autocomplete == "name":
        return "full_name"
    if autocomplete == "organization":
        return "company"
    if autocomplete == "organization-title":
        return "role"
    if autocomplete in ("country", "country-name"):
        return "country"
    if qtype == "checkbox" and _CONSENT_LABEL_RE.search(question.get("label") or ""):
        return "consent"
    haystack = " ".join(str(question.get(k) or "") for k in ("label", "name"))
    for purpose, pattern in _PURPOSES:
        if pattern.search(haystack):
            return purpose
    return "other"


def _question_view(question: Dict[str, Any]) -> Dict[str, Any]:
    marker = None
    if question.get("required"):
        marker = "required-attribute-or-asterisk"
    item = {
        "label": question.get("label") or "",
        "label_source": question.get("label_source"),
        "name": question.get("name") or "",
        "type": question.get("type"),
        "autocomplete": question.get("autocomplete"),
        "purpose": _purpose(question),
        "required_marker": marker,
        "optional_label": bool(question.get("optional_label")),
    }
    if question.get("options"):
        item["options"] = question["options"]
    return item


def _synthetic_form(container: Tag) -> Dict[str, Any]:
    """Run the shared form reader on a formless container (forms inside it removed)."""
    copy = gk_html.parse("<form data-gk-synthetic=\"1\">%s</form>" % str(container))
    synthetic = copy.find("form")
    for inner in synthetic.find_all("form"):
        inner.decompose()
    forms = gk_html.extract_forms(copy)
    form = forms[0] if forms else {"questions": 0, "fields": [], "dropped": {}, "kind": "other",
                                   "submit_text": "", "has_email": False, "has_password": False,
                                   "has_new_password": False, "has_current_password": False,
                                   "required_count": 0, "candidate_score": 0, "action": None}
    form.pop("_tag", None)
    return form


class _Control:
    __slots__ = ("tag", "text", "href", "role", "element", "zone", "provider", "provider_evidence",
                 "in_form", "reveal", "email_path")

    def __init__(self, tag: Tag, page_url: Optional[str]) -> None:
        self.tag = tag
        self.element = tag.name
        self.role = str(tag.get("role") or "").lower() or None
        self.text = _control_text(tag)
        self.href = _absolute(tag.get("href"), page_url) if tag.name == "a" else None
        self.zone = _zone(tag)
        self.in_form = tag.find_parent("form") is not None
        self.provider: Optional[str] = None
        self.provider_evidence: List[Dict[str, str]] = []
        self.reveal = bool(_REVEAL_RE.search(self.text or ""))
        self.email_path = bool(_EMAIL_PATH_RE.match(self.text or ""))

    def view(self) -> Dict[str, Any]:
        out = {"text": self.text, "element": self.element if not self.role else "%s[role=%s]" % (self.element, self.role),
               "zone": self.zone}
        if self.href:
            out["href"] = self.href
        return out


def _collect_controls(soup: Tag, page_url: Optional[str]) -> List[_Control]:
    controls: List[_Control] = []
    seen = set()
    for tag in soup.find_all(["a", "button", "input"]) + soup.find_all(attrs={"role": re.compile(r"^(?:button|link)$", re.I)}):
        if id(tag) in seen:
            continue
        seen.add(id(tag))
        if tag.name == "input" and str(tag.get("type") or "").lower() not in ("submit", "button", "image"):
            continue
        if tag.name == "a" and not tag.get("href") and str(tag.get("role") or "").lower() != "button":
            continue
        control = _Control(tag, page_url)
        if not control.text and not control.href:
            continue
        controls.append(control)
    order = {id(t): i for i, t in enumerate(soup.find_all(True))}
    controls.sort(key=lambda c: order.get(id(c.tag), 0))
    return controls


def _detect_provider(control: _Control, signup_context: bool) -> None:
    """Fill control.provider from its href, label, text and attributes.

    Strength rules keep integration links and customer-logo walls out:
    an auth route or OAuth endpoint always counts; "Sign up / Continue /
    Log in with X" counts anywhere; a bare provider name ("Google") or
    "with X" without an auth verb counts only on a control that does not
    navigate elsewhere (a button, or a link to an auth route), outside the
    nav, footer and logo walls.
    """
    evidence: List[Dict[str, str]] = []
    provider = None
    href = control.href or ""
    if href:
        found = _href_provider(href)
        if found:
            provider = found[0]
            evidence.append({"type": found[1], "value": href[:120]})
    navigates = bool(href) and not evidence
    social_link = navigates and bool(gk_html.classify_social(href))
    chrome = control.zone in ("nav", "footer", "cookie")
    plain_ok = not navigates and not chrome and not _in_logo_wall(control.tag)

    def accept(strength: str) -> bool:
        if strength == "auth_with":
            return not social_link
        if strength == "with":
            return plain_ok and signup_context
        if strength == "exact":
            return plain_ok
        if strength == "weak":
            return plain_ok and signup_context
        return False

    def consider(name: Optional[str], strength: str, kind: str, value: str) -> None:
        nonlocal provider
        if name and accept(strength):
            provider = provider or name
            if name == provider:
                item = {"type": kind, "value": value[:120]}
                if item not in evidence:
                    evidence.append(item)

    for attr in ("aria-label", "title"):
        value = _attr_text(control.tag, attr)
        name, strength = _text_provider(value)
        consider(name, strength, attr, value)
    text = gk_html.clean_text(control.tag, collapse=True)
    alts = " ".join(_attr_text(img, "alt") for img in control.tag.find_all("img", alt=True))
    if alts and re.search(r"\b%s\s*$" % _WITH_BEFORE, text or "", re.I):
        # "Continue with" + a provider logo: the logo's alt text names the provider.
        text = "%s %s" % (text, alts)
    name, strength = _text_provider(text)
    consider(name, strength, "text", text)
    if not text and alts:
        name, strength = _text_provider(alts.split("  ")[0])
        consider(name, strength if strength != "weak" else "", "img-alt", alts)
    attr = _attr_provider(control.tag)
    if attr and not navigates:
        consider(attr[0], "auth_with", "attribute", attr[1])
    if provider:
        control.provider = provider
        control.provider_evidence = evidence


_LOGO_WALL_RE = re.compile(r"logo|marquee|ticker|customer|brand|partner|trusted", re.I)


def _in_logo_wall(tag: Tag) -> bool:
    node = tag
    for _ in range(4):
        if not isinstance(node, Tag):
            return False
        if _LOGO_WALL_RE.search(" ".join(_classes(node) + [str(node.get("id") or "")])):
            return True
        node = node.parent
    return False


def _page_signup_context(page_url: Optional[str], title: Optional[str], h1s: List[str]) -> Dict[str, Any]:
    url_intent = gk_html.classify_href(page_url) if page_url else None
    texts = [t for t in [title or ""] + list(h1s or []) if t]
    text_intents = [gk_html.classify_cta_text(t) for t in texts]
    signup = url_intent == "signup" or "signup" in text_intents or any(
        _SIGNUP_ACTION_RE.search(t) for t in texts)
    login = (url_intent == "login" or "login" in text_intents) and not signup
    return {"url_intent": url_intent, "signup": bool(signup), "login_only": bool(login)}


def _score_candidate(cand: Dict[str, Any], context: Dict[str, Any]) -> None:
    score = 0
    reasons: List[str] = []
    kind = cand["kind"]
    base = 0 if cand["formless"] else \
        {"signup": 6, "lead": 1, "other": 0, "newsletter": -4, "login": -6, "search": -10}.get(kind, 0)
    if base:
        score += base
        reasons.append("form kind %s (%+d)" % (kind, base))
    actions = " | ".join(a["text"] for a in cand["actions"])
    if any(_SIGNUP_ACTION_RE.search(a["text"]) for a in cand["actions"]):
        score += 3
        reasons.append("signup wording on an action (+3)")
    elif any(_LOGIN_ACTION_RE.search(a["text"]) for a in cand["actions"]):
        score -= 3
        reasons.append("log-in wording on the actions (-3)")
    if any(_CONTINUE_RE.match(a["text"]) for a in cand["actions"]):
        score += 1
        reasons.append("continue/next action (+1)")
    if _SUBSCRIBE_RE.search(actions):
        score -= 4
        reasons.append("subscribe/newsletter wording (-4)")
    if cand["auth_providers"]:
        score += 3
        reasons.append("sign-in provider controls inside (+3)")
    if cand.get("has_new_password"):
        score += 3
        reasons.append("new-password field (+3)")
    if cand.get("has_current_password"):
        score -= 5
        reasons.append("current-password field: a log-in form (-5)")
    if cand.get("has_email"):
        score += 1
        reasons.append("email question (+1)")
    if cand["zone"] in ("nav", "footer", "cookie"):
        score -= 4
        reasons.append("sits in the %s (-4)" % cand["zone"])
    if cand["question_count"] == 0 and not cand["auth_providers"] and not cand["reveal_controls"]:
        score -= 10
        reasons.append("no questions and no sign-in options (-10)")
    if context["signup"]:
        score += 1
        reasons.append("page URL or headline says signup (+1)")
    if context["login_only"]:
        score -= 2
        reasons.append("page URL or headline says log in (-2)")
    cand["score"] = score
    cand["reasons"] = reasons


def _panel(tag: Tag, max_words: int = 300, max_levels: int = 4) -> Tag:
    """The nearest ancestor that adds context around a step without becoming the whole page."""
    best = tag
    node = tag.parent
    level = 0
    while isinstance(node, Tag) and node.name not in ("body", "html", "[document]") and level < max_levels:
        if gk_html.word_count(gk_html.clean_text(node)) > max_words:
            break
        best = node
        node = node.parent
        level += 1
    return best


def _proof_candidates(panel: Tag, soup: Tag) -> Dict[str, Any]:
    alts = []
    for img in panel.find_all("img", alt=True):
        alt = _attr_text(img, "alt")
        if alt and alt not in alts:
            alts.append(alt)
    logo_rows = []
    for node in soup.find_all(["div", "ul", "section"]):
        imgs = [i for i in node.find_all("img", alt=True, recursive=True) if _attr_text(i, "alt")]
        direct = node.find_all(True, recursive=False)
        if len(imgs) >= 4 and len(direct) >= 4 and gk_html.word_count(gk_html.clean_text(node)) <= 30:
            row = []
            for img in imgs[:12]:
                alt = _attr_text(img, "alt")
                if alt not in row and len(alt.split()) <= 5:
                    row.append(alt)
            # Logo walls carry short names; rows of long alt texts are screenshots.
            if len(row) >= 4 and row not in logo_rows and not any(set(row) <= set(r) for r in logo_rows):
                logo_rows.append(row)
        if len(logo_rows) >= 3:
            break
    quotes = [gk_html.clean_text(q)[:240] for q in panel.find_all(["blockquote", "q", "figcaption"]) if gk_html.clean_text(q)]
    panel_text = gk_html.clean_text(panel)
    ratings = [m["text"] for m in _snippets(panel_text, _RATING_RE, limit=4, radius=40)]
    return {
        "image_alts_near_step": alts[:15],
        "logo_rows": logo_rows[:3],
        "quotes_near_step": quotes[:4],
        "rating_mentions_near_step": ratings,
    }


def extract(markup: str, page_url: Optional[str] = None, step_label: Optional[str] = None,
            text_chars: int = 1500) -> Dict[str, Any]:
    """All signup facts for one HTML document (no network)."""
    facts = gk_html.page_facts(markup, page_url, text_chars=text_chars)
    soup = gk_html.parse(markup)

    # Raw scans: script tags, iframes and CSS still present.
    raw_visible_text = gk_html.visible_text(markup)
    bot = _bot_protection(soup, raw_visible_text)
    sdks = _auth_sdks(soup)
    pay_frames, pay_sdks = _payment_raw(soup)
    forms = gk_html.extract_forms(soup, page_url)

    # From here on, only what a visitor can see.
    gk_html.strip_invisible(soup)
    body = soup.body or soup
    headings = facts.get("headings") or {}
    h1s = headings.get("h1") or []
    context = _page_signup_context(page_url, facts.get("title"), h1s)

    controls = [c for c in _collect_controls(soup, page_url)]
    for control in controls:
        _detect_provider(control, context["signup"] or control.in_form)

    # Candidates: every visible form, plus one formless group.
    candidates: List[Dict[str, Any]] = []
    for form in forms:
        tag = form.pop("_tag")
        if form["hidden"] or not _attached(tag, soup):
            continue
        form_controls = [c for c in controls if _contains(tag, c.tag)]
        cand = _candidate_from_form("form-%d" % (form["index"] + 1), form, tag, form_controls, pay_frames)
        candidates.append(cand)

    chrome = ("nav", "footer", "cookie")
    orphan_auth = [c for c in controls if not c.in_form and c.zone not in chrome
                   and (c.provider or c.reveal or c.email_path)]
    # Sign-in buttons usually sit next to the form ("or continue with Google"):
    # they belong to that form's step when both fit in one small container.
    assigned = set()
    for cand in candidates:
        _attach_nearby_auth(cand, orphan_auth, body, assigned)
    leftover = [c for c in orphan_auth if id(c) not in assigned]
    orphan_inputs = [i for i in body.find_all(["input", "select", "textarea"])
                     if i.find_parent("form") is None
                     and str(i.get("type") or "text").lower() not in ("hidden", "submit", "button", "image", "reset", "search")
                     and _zone(i) not in chrome]
    if orphan_inputs or leftover:
        members = [c.tag for c in leftover] + orphan_inputs
        container = _lowest_common_ancestor(members) or body
        if container.name in ("html", "[document]"):
            container = body
        form = _synthetic_form(container)
        group_controls = [c for c in controls if _contains(container, c.tag) and not c.in_form
                          and (id(c) not in assigned)]
        candidates.append(_candidate_from_form("formless-1", form, container, group_controls, pay_frames,
                                               formless=True))
    for cand in candidates:
        _score_candidate(cand, context)
    candidates.sort(key=lambda c: -c["score"])
    primary = None
    for cand in candidates:
        if cand["score"] > 0 and cand["kind"] not in ("search", "login", "newsletter"):
            primary = cand
            break

    auth_options = _auth_options(controls, sdks, primary)
    visible_text = gk_html.clean_text(body)
    primary_view = None
    panel = None
    if primary is not None:
        panel = _panel(primary["_group"])
        primary_view = _candidate_view(primary, detail=True)

    payment = _payment(primary, pay_sdks, visible_text)
    password_seen = bool(primary and any(q["purpose"] == "password" for q in primary["questions"]))
    email_seen = bool(primary and any(q["purpose"] == "email" for q in primary["questions"]))
    reveal = [c.view() for c in controls if c.reveal and c.zone not in ("nav", "footer", "cookie")][:5]
    passkey = any(o["provider"] == "Passkey" for o in auth_options) or bool(
        primary and any("webauthn" in (q.get("autocomplete") or "") for q in primary["questions"]))

    lang = facts.get("lang")
    english = None if not lang else lang.lower().startswith("en")
    panel_text = gk_html.clean_text(panel)[:1200] if panel is not None else ""
    step_text = gk_html.clean_text(primary["_group"])[:600] if primary is not None else ""

    signup_links, login_links = _links(facts.get("ctas") or [], page_url)
    coverage = _coverage(facts, primary, auth_options, sdks, bot, english)

    result = {
        "page": {
            "url": page_url,
            "title": facts.get("title"),
            "lang": lang,
            "english": english,
            "h1": h1s[:3],
            "h2": (headings.get("h2") or [])[:6],
            "word_count": facts.get("word_count"),
            "is_js_shell": facts.get("is_js_shell"),
            "signup_context": context,
            "step_label": step_label,
        },
        "primary_step": primary_view,
        "candidates": [_candidate_view(c) for c in candidates][:8],
        "auth_options": auth_options,
        "auth_methods": {
            "email_question_seen": email_seen,
            "email_path_control": next((c.text for c in controls if c.email_path and c.zone not in ("nav", "footer", "cookie")), None),
            "password_at_this_step": password_seen,
            "passkey_offered": passkey,
            "enterprise_sso_offered": any(o["provider"] == "Enterprise SSO" for o in auth_options),
            "reveal_controls": reveal,
        },
        "bot_protection": bot,
        "edge_protection": None,
        "payment": payment,
        "hints": {
            "verification": _snippets(visible_text, _VERIFY_RE),
            "work_email": _work_email(primary, visible_text),
            "plan_and_trial": _snippets(visible_text, _PLAN_RE),
            "legal_consent": _snippets(visible_text, _LEGAL_RE, limit=3),
        },
        "context": {
            "step_text": step_text,
            "panel_text": panel_text,
            "proof_candidates": _proof_candidates(panel if panel is not None else body, soup),
            "page_excerpt": facts.get("main_text") or "",
        },
        "signup_links": signup_links,
        "login_links": login_links,
        "embedded_forms": _foreign_embeds(facts.get("embedded_forms") or [], page_url),
        "coverage": coverage,
    }
    return result


def _candidate_from_form(cid: str, form: Dict[str, Any], tag: Tag, controls: List[_Control],
                         pay_frames: List[Tuple[set, str]], formless: bool = False) -> Dict[str, Any]:
    questions = [_question_view(q) for q in form.get("fields") or []]
    for q in questions:
        if q["purpose"] == "password" and (q.get("autocomplete") or "") == "current-password":
            q["purpose"] = "password_current"
    actions = []
    for control in controls:
        if control.provider or _UI_CONTROL_RE.match(control.text or "") or not control.text:
            continue
        if control.element == "a" and control.href and not control.role:
            continue
        view = control.view()
        if view not in actions:
            actions.append(view)
    submit = "" if formless else (form.get("submit_text") or "")
    if submit and not any(a["text"] == submit for a in actions):
        actions.insert(0, {"text": submit, "element": "submit", "zone": _zone(tag)})
    providers = []
    for control in controls:
        if control.provider and control.provider not in providers:
            providers.append(control.provider)
    card_fields = []
    for q in questions:
        if q["purpose"] == "card" or (q.get("autocomplete") or "") in _CARD_AUTOCOMPLETE:
            card_fields.append("field: %s (%s)" % (q["label"] or q["name"], q.get("autocomplete") or q["type"]))
    for ancestor_ids, label in pay_frames:
        if id(tag) in ancestor_ids and label not in card_fields:
            card_fields.append(label)
    consent = [{"label": q["label"], "required_marker": q["required_marker"]} for q in questions if q["purpose"] == "consent"]
    kind = form.get("kind") or "other"
    if formless:
        kind = "signup" if (providers or any(c.reveal or c.email_path for c in controls)) else "other"
    return {
        "id": cid,
        "_tag": tag,
        "_group": tag,
        "_controls": list(controls),
        "formless": formless,
        "kind": kind,
        "zone": _zone(tag),
        "action_url": form.get("action"),
        "method": form.get("method") if not formless else None,
        "questions": questions,
        "question_count": len(questions),
        "required_marked_count": sum(1 for q in questions if q["required_marker"]),
        "optional_labelled_count": sum(1 for q in questions if q["optional_label"]),
        "purposes": sorted({q["purpose"] for q in questions}),
        "has_email": bool(form.get("has_email")),
        "has_new_password": bool(form.get("has_new_password")),
        "has_current_password": any(q["purpose"] == "password_current" for q in questions),
        "dropped": form.get("dropped") or {},
        "actions": actions[:6],
        "auth_providers": providers,
        "reveal_controls": [c.text for c in controls if c.reveal][:3],
        "consent": consent,
        "card_fields": card_fields,
        "score": 0,
        "reasons": [],
    }


def _attach_nearby_auth(cand: Dict[str, Any], orphan_auth: List["_Control"], body: Tag, assigned: set,
                        max_words: int = 600) -> None:
    """Give a form candidate the sign-in controls that share a small container with it."""
    if not orphan_auth or cand["zone"] in ("nav", "footer", "cookie"):
        return
    tag = cand["_tag"]
    joined = _lowest_common_ancestor([tag] + [c.tag for c in orphan_auth])
    if joined is None or joined.name in ("html", "[document]"):
        return
    if gk_html.word_count(gk_html.clean_text(joined)) > max_words:
        # Too big: try each control on its own (the closest ones only).
        near = []
        for control in orphan_auth:
            pair = _lowest_common_ancestor([tag, control.tag])
            if pair is not None and pair.name not in ("html", "[document]") and \
                    gk_html.word_count(gk_html.clean_text(pair)) <= max_words:
                near.append(control)
        if not near:
            return
        joined = _lowest_common_ancestor([tag] + [c.tag for c in near])
        if joined is None:
            return
    else:
        near = list(orphan_auth)
    cand["_group"] = joined
    for control in near:
        assigned.add(id(control))
        if control.provider and control.provider not in cand["auth_providers"]:
            cand["auth_providers"].append(control.provider)
        if (control.reveal or control.email_path) and control.text not in cand["reveal_controls"]:
            cand["reveal_controls"].append(control.text)
        cand["_controls"].append(control)


def _candidate_view(cand: Dict[str, Any], detail: bool = False) -> Dict[str, Any]:
    keys = ["id", "formless", "kind", "score", "reasons", "zone", "action_url", "question_count",
            "required_marked_count", "optional_labelled_count", "purposes", "auth_providers", "actions"]
    if detail:
        keys += ["method", "questions", "dropped", "reveal_controls", "consent", "card_fields"]
    view = {k: cand.get(k) for k in keys}
    if not detail:
        view["actions"] = [a["text"] for a in cand.get("actions") or []][:4]
    return view


def _auth_options(controls: List[_Control], sdks: List[Dict[str, str]],
                  primary: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    options: Dict[str, Dict[str, Any]] = {}
    for control in controls:
        if not control.provider:
            continue
        entry = options.setdefault(control.provider, {
            "provider": control.provider, "control_seen": False, "zones": [], "in_primary_step": False,
            "evidence": [],
        })
        entry["control_seen"] = True
        if control.zone not in entry["zones"]:
            entry["zones"].append(control.zone)
        if primary is not None and _contains(primary["_group"], control.tag):
            entry["in_primary_step"] = True
        for item in control.provider_evidence:
            item = dict(item, zone=control.zone)
            if item not in entry["evidence"] and len(entry["evidence"]) < 4:
                entry["evidence"].append(item)
    for sdk in sdks:
        entry = options.setdefault(sdk["provider"], {
            "provider": sdk["provider"], "control_seen": False, "zones": [], "in_primary_step": False,
            "evidence": [],
        })
        item = {"type": sdk["type"], "value": sdk["value"], "zone": None}
        if item not in entry["evidence"] and len(entry["evidence"]) < 5:
            entry["evidence"].append(item)
    out = list(options.values())
    for entry in out:
        chrome_only = entry["control_seen"] and all(z in ("nav", "footer", "cookie") for z in entry["zones"])
        entry["note"] = None
        if not entry["control_seen"]:
            entry["note"] = "identity SDK loaded but no button in this HTML; render the page to confirm the button"
        elif chrome_only:
            entry["note"] = "seen only in the %s (often a log-in link)" % "/".join(entry["zones"])
    out.sort(key=lambda e: (not e["in_primary_step"], not e["control_seen"], e["provider"]))
    return out


def _payment(primary: Optional[Dict[str, Any]], pay_sdks: List[str], visible_text: str) -> Dict[str, Any]:
    mentions = []
    for item in _snippets(visible_text, _PAYMENT_MENTION_RE, limit=6):
        item["negated"] = bool(_PAYMENT_NEGATION_RE.search(item["text"]))
        mentions.append(item)
    card_fields = primary["card_fields"] if primary is not None else []
    return {
        "card_fields_in_step": card_fields,
        "card_fields_seen": (bool(card_fields) if primary is not None else None),
        "payment_sdks_on_page": pay_sdks,
        "page_mentions": mentions,
        "note": "card_fields_seen covers this step only; page_mentions are context (terms of a paid plan, "
                "'no credit card' claims) for the model to read, not evidence of a card gate.",
    }


def _work_email(primary: Optional[Dict[str, Any]], visible_text: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    if primary is not None:
        for q in primary["questions"]:
            if _WORK_EMAIL_RE.search(q.get("label") or ""):
                out.append({"source": "field label (%s)" % q.get("label_source"), "text": q["label"]})
    for item in _snippets(visible_text, _WORK_EMAIL_RE, limit=3, radius=60):
        out.append({"source": "page text", "text": item["text"]})
    return out[:5]


_LOCALE_SEG_RE = re.compile(r"^/[a-z]{2}(?:[-_][a-zA-Z]{2,4})?(?=/)")


def _link_key(href: str) -> str:
    """Comparison key for a link: host and path without fragment, trailing slash or locale prefix."""
    try:
        parsed = urlparse(href)
    except ValueError:
        return href
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = _LOCALE_SEG_RE.sub("", parsed.path or "/").rstrip("/") or "/"
    return "%s%s%s" % (host, path, ("?" + parsed.query) if parsed.query else "")


def _foreign_embeds(embeds: List[Dict[str, Any]], page_url: Optional[str]) -> List[Dict[str, Any]]:
    """Embedded third-party forms, minus the site's own product (calendly.com embeds Calendly)."""
    host = (urlparse(page_url).hostname or "").lower() if page_url else ""
    return [e for e in embeds if not (host and str(e.get("provider") or "").split("_")[0] in host)]


def _links(ctas: List[Dict[str, Any]], page_url: Optional[str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    signup: List[Dict[str, Any]] = []
    login: List[Dict[str, Any]] = []
    seen = set()
    self_key = _link_key(page_url) if page_url else None
    for cta in ctas:
        href = cta.get("href")
        intent = cta.get("intent")
        if not href or intent not in ("signup", "login", "app"):
            continue
        key = (intent, _link_key(href))
        if key in seen or key[1] == self_key:
            continue
        seen.add(key)
        item = {"text": cta.get("text"), "href": href, "zone": cta.get("zone")}
        if _href_provider(href):
            continue  # a "Sign up with Google" route, not a link to the signup page
        if intent == "signup":
            signup.append(item)
        elif intent == "login":
            login.append(item)
    zone_rank = {"hero": 0, "body": 1, "nav": 2, "dialog": 3, "footer": 4}
    signup.sort(key=lambda i: zone_rank.get(i.get("zone"), 5))
    return signup[:8], login[:3]


def _coverage(facts: Dict[str, Any], primary: Optional[Dict[str, Any]], auth_options: List[Dict[str, Any]],
              sdks: List[Dict[str, str]], bot: List[Dict[str, Any]], english: Optional[bool]) -> Dict[str, Any]:
    reasons: List[str] = []
    if facts.get("is_js_shell"):
        reasons.append("static HTML looks client-rendered")
    if primary is None:
        reasons.append("no signup step in this HTML")
    else:
        if primary["question_count"] == 0 and not primary["auth_providers"]:
            reasons.append("the signup step has no questions or sign-in buttons in this HTML")
        if not primary["actions"] and not primary["auth_providers"]:
            reasons.append("no visible submit or continue control in the step")
    if any(not o["control_seen"] for o in auth_options):
        reasons.append("an identity SDK is loaded but its button is rendered client-side")
    if _foreign_embeds(facts.get("embedded_forms") or [], facts.get("url")):
        reasons.append("a third-party form is rendered by JavaScript")
    if any(b["mode"] == "unknown" for b in bot):
        reasons.append("bot-protection mode is unknown in static HTML")
    cannot = [
        "steps after the first data-entry step (verification code, password, profile questions)",
        "what a logged-in or returning visitor sees",
        "client-side validation errors and their wording",
    ]
    if english is False:
        cannot.append("text hints (verification, plan, payment, consent) use English patterns; read step_text and panel_text")
    return {"render_recommended": bool(reasons), "render_reasons": reasons, "static_html_cannot_show": cannot}


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


_STATUS_FOR_FETCH = {
    gk_http.STATUS_BLOCKED: "blocked",
    gk_http.STATUS_UNREACHABLE: "fetch_error",
    gk_http.STATUS_HTTP_ERROR: "fetch_error",
    gk_http.STATUS_NOT_HTML: "fetch_error",
}


def _human(envelope: Dict[str, Any]) -> str:
    lines = ["Signup extractor: %s (%s)" % (envelope.get("signup_status"), envelope.get("status"))]
    page = envelope.get("page") or {}
    if page:
        lines.append("Page: %s | %s" % (page.get("url") or envelope.get("source", {}).get("input"), page.get("title")))
    step = envelope.get("primary_step")
    if step:
        lines.append("Primary step: %s (%s), %d question(s): %s" % (
            step["id"], step["kind"], step["question_count"],
            ", ".join(q["purpose"] for q in step["questions"]) or "none"))
        lines.append("Actions: %s" % ", ".join(a["text"] for a in step["actions"]))
    for option in envelope.get("auth_options") or []:
        lines.append("Sign-in option: %s (control seen: %s, zones: %s)" % (
            option["provider"], option["control_seen"], ", ".join(z for z in option["zones"] if z) or "-"))
    for item in envelope.get("bot_protection") or []:
        lines.append("Bot protection: %s, mode %s" % (item["vendor"], item["mode"]))
    payment = envelope.get("payment") or {}
    if payment:
        lines.append("Card fields in step: %s" % payment.get("card_fields_seen"))
    for link in (envelope.get("signup_links") or [])[:3]:
        lines.append("Signup link: %s -> %s" % (link["text"], link["href"]))
    for note in envelope.get("notes") or []:
        lines.append("Note: %s" % note)
    return "\n".join(lines)


def build_parser() -> cli.ArgumentParser:
    parser = cli.build_parser(
        "Extract signup-step facts (questions, sign-in options, bot protection, card fields, "
        "hints) from a signup page URL or saved HTML. Never scores.",
        input_help="signup page URL, saved or rendered HTML file, or '-' for stdin",
        prog="signup_extractor.py",
        demo=False,
    )
    parser.add_argument("--page-url", metavar="URL",
                        help="original URL of a saved or rendered HTML file (resolves links, adds page context)")
    parser.add_argument("--step-label", metavar="TEXT",
                        help="label for this step when walking a flow, e.g. \"step 2: after Continue with email\"")
    parser.add_argument("--psi", action="store_true",
                        help="also fetch PageSpeed Insights field data (mobile); uses PAGESPEED_API_KEY or GOOGLE_API_KEY when set")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    run = cli.Run(TOOL, args)
    try:
        source = cli.resolve_input(args.input)
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))

    page_url = args.page_url
    if page_url:
        try:
            page_url = gk_http.normalize_url(page_url)
        except ValueError as exc:
            return run.fail(cli.STATUS_USAGE, "--page-url: %s" % exc)
    data: Dict[str, Any] = {
        "signup_status": None,
        "source": {"kind": source["kind"], "input": source["value"], "page_url": page_url,
                   "step_label": args.step_label},
        "fetch": None,
    }
    status = cli.STATUS_OK
    markup = source.get("text")
    fetch_result = None
    if source["kind"] == "url":
        fetch_result = gk_http.fetch(source["value"], timeout=args.timeout)
        data["fetch"] = gk_http.summarize(fetch_result)
        page_url = page_url or fetch_result.get("final_url") or fetch_result.get("url")
        data["source"]["page_url"] = page_url
        fetch_status = fetch_result.get("status")
        if fetch_status in _STATUS_FOR_FETCH:
            env_status, message = cli.fetch_outcome(fetch_result)
            data["signup_status"] = _STATUS_FOR_FETCH[fetch_status]
            if fetch_status == gk_http.STATUS_BLOCKED:
                run.note("The site blocks automated fetches. Render the page in a browser (headless Chrome or "
                         "a browser tool) and pass the saved HTML file with --page-url; do not retry in a loop.")
            elif fetch_status in (gk_http.STATUS_HTTP_ERROR, gk_http.STATUS_UNREACHABLE):
                run.note("Check the URL (typo, missing path, moved signup page). A browser sees the same error "
                         "for 404, DNS and TLS failures.")
            return run.fail(env_status, message, data)
        if fetch_status == gk_http.STATUS_TOO_LARGE:
            _, message = cli.fetch_outcome(fetch_result)
            run.error(message)
            status = cli.STATUS_PARTIAL
        markup = fetch_result.get("html") or ""
    if not (markup or "").strip():
        data["signup_status"] = "no_form"
        return run.fail(cli.STATUS_NOTHING, "The HTML is empty.", data)

    facts = extract(markup, page_url, args.step_label)
    data.update(_plain_dashes(facts))
    if fetch_result is not None:
        data["edge_protection"] = fetch_result.get("bot_protection")

    if args.psi:
        data["speed"] = _psi(page_url, run)

    primary = data.get("primary_step")
    js_shell = bool((data.get("page") or {}).get("is_js_shell"))
    if primary is None:
        challenge = _challenge_page(markup, (data.get("page") or {}).get("word_count") or 0)
        if challenge:
            data["signup_status"] = "blocked"
            data["challenge"] = challenge
            run.note("A headless render cannot pass a bot challenge. Use a browser tool with a normal profile, "
                     "or ask the user for screenshots of each signup screen (browser-fallback.md Path C).")
            return run.fail(cli.STATUS_BLOCKED, "The HTML is a bot-protection challenge page (%s), not the signup "
                            "page." % challenge["vendor"], data)
        if js_shell:
            data["signup_status"] = "js_shell"
            return run.fail(cli.STATUS_NOTHING, "The HTML is a JavaScript shell with no signup step. Render the "
                            "page in a browser and pass the saved HTML file with --page-url.", data)
        data["signup_status"] = "no_form"
        links = data.get("signup_links") or []
        if links:
            run.note("No signup step on this page, but it links to a signup page: %s. Run the extractor on that URL."
                     % links[0]["href"])
        elif (data.get("login_links") or []) or (data.get("page") or {}).get("signup_context", {}).get("login_only"):
            run.note("Only a log-in form or link was found; the signup entry point is elsewhere.")
        return run.fail(cli.STATUS_NOTHING, "No signup step (inputs or sign-in controls that start an account) "
                        "was found in this HTML. If the page is the signup page, render it in a browser.", data)
    data["signup_status"] = "ok"
    if js_shell:
        run.note("The static HTML looks client-rendered; facts may be incomplete. Render the page to confirm.")
    if (data.get("page") or {}).get("english") is False:
        run.note("Page language is %s: structural facts (fields, sign-in options, bot protection, card fields) "
                 "are language independent, but the text hints use English patterns. Read step_text and "
                 "panel_text yourself." % data["page"]["lang"])
    return run.emit(data, status=status, human=_human)


_CHALLENGE_TEXT_RE = re.compile(
    r"verify (?:that )?you(?:'re| are)? (?:a )?human|verify it.s you|unusual traffic|are you a robot|"
    r"(?:quick |complete the )?security check|access denied|you have been blocked|ray ?id:|"
    r"reference (?:id|#)|checking your browser|enable javascript and cookies|request (?:was )?blocked",
    re.I,
)


def _challenge_page(markup: str, words: int) -> Optional[Dict[str, Any]]:
    """Vendor and evidence when saved HTML is a bot-protection challenge, else None."""
    bot = gk_http.detect_bot_protection(None, None, markup, None, words)
    if bot and bot.get("challenge"):
        return {"vendor": bot.get("vendor"), "signals": bot.get("signals")}
    if words < 150:
        match = _CHALLENGE_TEXT_RE.search(gk_html.visible_text(markup))
        if match:
            return {"vendor": (bot or {}).get("vendor") or "unknown", "signals": ["text: %s" % match.group(0)]}
    return None


_DASHES = {ord(chr(0x2014)): "-", ord(chr(0x2013)): "-", ord(chr(0x2012)): "-", ord(chr(0x2015)): "-"}


def _plain_dashes(value: Any) -> Any:
    """Replace em and en dashes in extracted text with a hyphen (house style for reports)."""
    if isinstance(value, str):
        return value.translate(_DASHES)
    if isinstance(value, list):
        return [_plain_dashes(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain_dashes(v) for k, v in value.items()}
    return value


def _psi(page_url: Optional[str], run: cli.Run) -> Optional[Dict[str, Any]]:
    if not page_url or not re.match(r"(?i)^https?://", page_url):
        run.note("--psi needs a public URL (pass --page-url for a saved file); speed not measured.")
        return None
    from _growthkit import psi  # imported lazily: only this option needs it
    result = psi.fetch(page_url, strategy="mobile")
    field = result.get("field") or {}
    lab = result.get("lab") or {}
    for note in result.get("notes") or []:
        run.note("PageSpeed: %s" % note)
    for error in result.get("errors") or []:
        run.note("PageSpeed: %s" % error)
    return {
        "status": result.get("status"),
        "strategy": "mobile",
        "key_source": result.get("key_source"),
        "field_scope": field.get("scope"),
        "cwv_assessment": field.get("cwv_assessment"),
        "field_metrics": field.get("metrics"),
        "lab_diagnostics": {k: lab.get(k) for k in ("performance_score", "lcp_ms", "tbt_ms", "cls") if k in lab},
    }


if __name__ == "__main__":
    sys.exit(main())
