#!/usr/bin/env python3
"""
Signup Flow Auditor

Analyzes SaaS signup pages for friction points and provides a friction score
with actionable recommendations. Fetches the page HTML and evaluates form
fields, SSO options, trust signals, and other conversion factors.

Usage:
    python signup_auditor.py <signup_page_url_or_html_file>

Example:
    python signup_auditor.py https://example.com/signup
    python signup_auditor.py ./saved-signup-page.html
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional
from urllib.parse import urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Required dependencies: requests, beautifulsoup4")
    print("Install with: pip install requests beautifulsoup4")
    sys.exit(1)


@dataclass
class SignupAuditResult:
    """Result of a signup page friction audit."""

    url: str
    friction_score: int = 0
    field_count: int = 0
    required_field_count: int = 0
    required_checkbox_count: int = 0
    has_sso: bool = False
    sso_providers: list = field(default_factory=list)
    possible_sso: list = field(default_factory=list)
    has_password: bool = False
    has_captcha: bool = False
    requires_cc: bool = False
    cta_text: str = ""
    trust_signals: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    fetch_failed: bool = False
    form_found: bool = False


# SSO provider page-wide hint patterns. Substring matches on raw HTML are
# only used to report "possible SSO (unverified)" - they are NOT scored,
# because analytics scripts (googletagmanager.com) and footer social links
# produce false positives. Verified detection uses buttons/links below.
SSO_PATTERNS: dict[str, list[str]] = {
    "Google": ["google", "gmail", "gsi", "accounts.google"],
    "GitHub": ["github"],
    "Microsoft": ["microsoft", "azure", "live.com", "outlook"],
    "Apple": ["apple", "appleid"],
    "Facebook": ["facebook", "fb-login"],
    "LinkedIn": ["linkedin"],
    "Twitter": ["twitter"],
    "Okta": ["okta"],
    "Auth0": ["auth0"],
    "Passkey": ["passkey", "webauthn"],
    "SSO Generic": ["saml", "sso", "single-sign-on"],
}

# Verified SSO detection: button/link text like "Continue with Google"
SSO_BUTTON_RE = re.compile(
    r"(continue|sign\s?(in|up)|log\s?in|register)\s+with\s+"
    r"(?P<provider>google|github|microsoft|azure|apple|facebook|linkedin|"
    r"twitter|okta|auth0|slack|passkey|sso|saml)",
    re.IGNORECASE,
)

# Verified SSO detection: hrefs pointing at known OAuth endpoints
OAUTH_ENDPOINT_PATTERNS: dict[str, list[str]] = {
    "Google": ["accounts.google.com/o/oauth2", "accounts.google.com/gsi"],
    "GitHub": ["github.com/login/oauth"],
    "Microsoft": ["login.microsoftonline.com", "login.live.com"],
    "Apple": ["appleid.apple.com/auth"],
    "Facebook": ["facebook.com/dialog/oauth"],
    "LinkedIn": ["linkedin.com/oauth"],
    "Twitter": ["api.twitter.com/oauth", "twitter.com/i/oauth"],
    "Okta": [".okta.com/oauth"],
    "Auth0": [".auth0.com/authorize"],
}

# Display names for providers matched from button text
SSO_PROVIDER_DISPLAY: dict[str, str] = {
    "google": "Google",
    "github": "GitHub",
    "microsoft": "Microsoft",
    "azure": "Microsoft",
    "apple": "Apple",
    "facebook": "Facebook",
    "linkedin": "LinkedIn",
    "twitter": "Twitter",
    "okta": "Okta",
    "auth0": "Auth0",
    "slack": "Slack",
    "passkey": "Passkey",
    "sso": "SSO Generic",
    "saml": "SSO Generic",
}

# Trust signal detection patterns
TRUST_PATTERNS: list[dict[str, str]] = [
    {"name": "Security badge", "pattern": r"ssl|secure|encrypt|256[\s-]?bit|https"},
    {"name": "Money-back guarantee", "pattern": r"money[\s-]?back|guarantee|refund"},
    {"name": "No credit card required", "pattern": r"no\s+credit\s+card|no\s+cc\b|free\s+(trial|plan|forever)"},
    {"name": "User count social proof", "pattern": r"\d+[,.]?\d*[kKmM]?\s*(users|customers|teams|companies)"},
    {"name": "Rating/review badge", "pattern": r"g2|capterra|trustpilot|stars?\s*rat"},
    {"name": "SOC2/compliance", "pattern": r"soc\s*2|gdpr|hipaa|complian"},
    {"name": "Testimonial", "pattern": r"testimonial|\"[^\"]{20,}\""},
    {"name": "Logo bar", "pattern": r"trusted\s+by|used\s+by|loved\s+by|companies\s+like"},
]

# CAPTCHA detection patterns
CAPTCHA_PATTERNS: list[str] = [
    "recaptcha",
    "hcaptcha",
    "captcha",
    "g-recaptcha",
    "h-captcha",
    "cf-turnstile",
    "turnstile",
    "arkose",
]

# Credit card text patterns, checked against visible page text AFTER
# negations like "no credit card required" have been stripped. Indirect
# hints (stripe, payment method, billing info) were removed - they flagged
# pages that merely mention payments elsewhere.
CC_PATTERNS: list[str] = [
    "credit card",
    "card number",
    "cardnumber",
    "cc-number",
    "cvv",
    "cvc",
    "expiry date",
    "expiration date",
]

# Negation phrases to strip before scanning page text for CC patterns
CC_NEGATION_RE = re.compile(r"(no|without(\s+a)?)\s+credit\s+card[^.]*", re.IGNORECASE)

# Form-level credit card evidence (strongest signal)
CC_INPUT_AUTOCOMPLETE: set = {"cc-number", "cc-exp", "cc-csc"}
CC_INPUT_NAME_RE = re.compile(r"card|cvv|cvc|expiry", re.IGNORECASE)


def fetch_page(url: str, timeout: int = 15) -> Optional[BeautifulSoup]:
    """Fetch a web page and return a BeautifulSoup object.

    Args:
        url: The URL to fetch.
        timeout: Request timeout in seconds.

    Returns:
        BeautifulSoup object or None if the fetch failed.
    """
    # NOTE: refresh the Chrome version below periodically so the UA stays current.
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/138.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    try:
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except requests.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return None


def load_source(source: str) -> Optional[BeautifulSoup]:
    """Load a page from a URL or a local HTML file path."""
    if os.path.isfile(source):
        try:
            with open(source, encoding="utf-8", errors="replace") as fh:
                return BeautifulSoup(fh.read(), "html.parser")
        except OSError as e:
            print(f"Error reading {source}: {e}")
            return None
    return fetch_page(source)


def detect_page_language(soup: BeautifulSoup) -> str:
    """Return the declared <html lang> value (lowercased), or '' if unset."""
    html_tag = soup.find("html")
    if html_tag is None:
        return ""
    return (html_tag.get("lang") or "").strip().lower()


def find_forms(soup: BeautifulSoup) -> list:
    """Find signup-related forms on the page.

    Args:
        soup: Parsed HTML page.

    Returns:
        List of form elements that appear to be signup forms.
    """
    forms = soup.find_all("form")
    signup_forms = []

    signup_keywords = [
        "signup", "sign-up", "sign_up", "register", "create-account",
        "create_account", "join", "get-started", "get_started", "trial",
        "onboard",
    ]

    for form in forms:
        form_str = str(form).lower()
        form_action = (form.get("action") or "").lower()
        form_id = (form.get("id") or "").lower()
        form_class = " ".join(form.get("class") or []).lower()

        is_signup = any(
            kw in text
            for kw in signup_keywords
            for text in [form_str, form_action, form_id, form_class]
        )

        # If no signup-specific form found, include forms with email fields
        if not is_signup:
            email_inputs = form.find_all("input", attrs={"type": "email"})
            name_pattern = re.compile(r"email|mail", re.IGNORECASE)
            email_named = form.find_all("input", attrs={"name": name_pattern})
            if email_inputs or email_named:
                is_signup = True

        if is_signup:
            signup_forms.append(form)

    # Fallback: if no signup forms found, return all forms with inputs
    if not signup_forms:
        signup_forms = [f for f in forms if f.find_all("input")]

    return signup_forms


def count_form_fields(form) -> tuple[int, int, int]:
    """Count total, required, and required-checkbox form fields.

    Required checkboxes (consent boxes, terms acceptance) are counted
    separately: they add friction, but less than a text field.

    Args:
        form: A BeautifulSoup form element.

    Returns:
        Tuple of (total_field_count, required_field_count,
        required_checkbox_count).
    """
    excluded_types = {"hidden", "submit", "button", "image", "reset", "checkbox"}

    inputs = form.find_all("input")
    visible_inputs = [
        inp for inp in inputs
        if inp.get("type", "text").lower() not in excluded_types
    ]

    # Also count select and textarea elements
    selects = form.find_all("select")
    textareas = form.find_all("textarea")

    total = len(visible_inputs) + len(selects) + len(textareas)

    required_count = 0
    for elem in visible_inputs + selects + textareas:
        if elem.get("required") is not None or elem.get("aria-required") == "true":
            required_count += 1

    required_checkboxes = 0
    for inp in inputs:
        if inp.get("type", "text").lower() != "checkbox":
            continue
        if inp.get("required") is not None or inp.get("aria-required") == "true":
            required_checkboxes += 1

    return total, required_count, required_checkboxes


def detect_password_field(form) -> bool:
    """Check if the form contains a password field.

    Args:
        form: A BeautifulSoup form element.

    Returns:
        True if a password field is found.
    """
    password_inputs = form.find_all("input", attrs={"type": "password"})
    name_pattern = re.compile(r"password|passwd|pwd", re.IGNORECASE)
    named_passwords = form.find_all("input", attrs={"name": name_pattern})
    return bool(password_inputs or named_passwords)


def detect_sso_providers(soup: BeautifulSoup) -> tuple[list[str], list[str]]:
    """Detect SSO/social login providers on the page.

    Verified providers come from actual <a>/<button> elements: button text
    like "Continue with Google" or hrefs pointing at known OAuth endpoints.
    Raw-HTML substring matches (analytics scripts, footer social links) are
    returned separately as "possible" and must NOT be used for scoring.

    Args:
        soup: Parsed HTML page.

    Returns:
        Tuple of (verified_provider_names, possible_provider_names).
    """
    verified: list[str] = []

    for el in soup.find_all(["a", "button"]):
        text = el.get_text(" ", strip=True)
        match = SSO_BUTTON_RE.search(text)
        if match:
            provider = SSO_PROVIDER_DISPLAY.get(
                match.group("provider").lower(),
                match.group("provider").title(),
            )
            if provider not in verified:
                verified.append(provider)

        href = (el.get("href") or "").lower()
        if href:
            for provider, endpoints in OAUTH_ENDPOINT_PATTERNS.items():
                if any(ep in href for ep in endpoints) and provider not in verified:
                    verified.append(provider)

    # Page-wide substring scan: report-only, excluded from scoring
    page_html = str(soup).lower()
    possible: list[str] = []
    for provider, patterns in SSO_PATTERNS.items():
        if provider in verified:
            continue
        if any(pattern in page_html for pattern in patterns):
            possible.append(provider)

    return verified, possible


def detect_captcha(soup: BeautifulSoup) -> bool:
    """Check if the page uses CAPTCHA.

    Args:
        soup: Parsed HTML page.

    Returns:
        True if CAPTCHA is detected.
    """
    page_text = str(soup).lower()
    return any(pattern in page_text for pattern in CAPTCHA_PATTERNS)


def detect_credit_card(soup: BeautifulSoup) -> bool:
    """Check if the page requires credit card information.

    Prefers form-level evidence (actual card input fields). For page text,
    negations like "no credit card required" are stripped first so that the
    best pages are not penalized for advertising their lack of friction.

    Args:
        soup: Parsed HTML page.

    Returns:
        True if credit card requirement is detected.
    """
    # Form-level evidence: inputs that collect card data
    for inp in soup.find_all("input"):
        autocomplete = (inp.get("autocomplete") or "").lower()
        if autocomplete in CC_INPUT_AUTOCOMPLETE:
            return True
        name_and_id = f"{inp.get('name') or ''} {inp.get('id') or ''}"
        if CC_INPUT_NAME_RE.search(name_and_id):
            return True

    # Visible-text scan with negations removed
    page_text = soup.get_text(" ", strip=True).lower()
    page_text = CC_NEGATION_RE.sub("", page_text)
    return any(pattern in page_text for pattern in CC_PATTERNS)


def detect_trust_signals(soup: BeautifulSoup) -> list[str]:
    """Detect trust signals on the page.

    Args:
        soup: Parsed HTML page.

    Returns:
        List of detected trust signal descriptions.
    """
    page_text = soup.get_text().lower()
    found_signals = []

    for signal in TRUST_PATTERNS:
        if re.search(signal["pattern"], page_text, re.IGNORECASE):
            found_signals.append(signal["name"])

    return found_signals


def extract_cta_text(form) -> str:
    """Extract the call-to-action button text from a form.

    Args:
        form: A BeautifulSoup form element.

    Returns:
        CTA button text or empty string.
    """
    # Check submit buttons
    buttons = form.find_all("button", attrs={"type": "submit"})
    if buttons:
        return buttons[0].get_text(strip=True)

    # Check input submit
    submits = form.find_all("input", attrs={"type": "submit"})
    if submits:
        return submits[0].get("value", "")

    # Check any button in the form
    any_buttons = form.find_all("button")
    if any_buttons:
        return any_buttons[0].get_text(strip=True)

    return ""


def calculate_friction_score(result: SignupAuditResult) -> int:
    """Calculate the friction score based on audit findings.

    Scoring:
        - Each required field: +8
        - Each required checkbox (consent/terms): +2
        - No SSO: +15
        - Password requirement: +10
        - CAPTCHA: +10
        - Credit card: +25
        - More than 5 fields: +15
        - No trust signals: +10

    Args:
        result: The audit result with detected features.

    Returns:
        Friction score from 0 (frictionless) to 100 (maximum friction).
    """
    score = 0

    # Each required field adds 8 points
    score += result.required_field_count * 8

    # Required checkboxes add friction at a lower weight
    score += result.required_checkbox_count * 2

    # No SSO adds 15 points
    if not result.has_sso:
        score += 15

    # Password requirement adds 10 points
    if result.has_password:
        score += 10

    # CAPTCHA adds 10 points
    if result.has_captcha:
        score += 10

    # Credit card requirement adds 25 points
    if result.requires_cc:
        score += 25

    # More than 5 fields adds 15 points
    if result.field_count > 5:
        score += 15

    # No trust signals adds 10 points
    if not result.trust_signals:
        score += 10

    # Cap at 100
    return min(score, 100)


def generate_recommendations(result: SignupAuditResult) -> list[str]:
    """Generate actionable recommendations based on audit findings.

    Args:
        result: The audit result with detected features.

    Returns:
        List of recommendation strings.
    """
    recs = []

    if result.field_count > 3:
        recs.append(
            f"Reduce form fields from {result.field_count} to 3 or fewer. "
            f"Industry studies suggest each additional field costs roughly "
            f"5-10% in conversions. Use progressive profiling to collect "
            f"additional data after signup."
        )

    if not result.has_sso:
        recs.append(
            "Add SSO options (Google at minimum). SSO reduces signup friction "
            "by 30-50% and increases completion rates to 85-95%."
        )
    elif len(result.sso_providers) == 1:
        recs.append(
            "Add a second SSO provider. Offering 2-3 SSO options maximizes "
            "coverage without causing decision paralysis."
        )

    if result.has_password:
        recs.append(
            "Consider passwordless authentication (passkeys/WebAuthn, magic "
            "link, email OTP, or SSO-only). Password fields add friction and "
            "create future support burden for password resets."
        )

    if result.has_captcha:
        recs.append(
            "Replace visible CAPTCHA with invisible alternatives (reCAPTCHA v3 "
            "or Cloudflare Turnstile invisible mode). Visible CAPTCHAs add "
            "friction without significantly improving the user experience."
        )

    if result.requires_cc:
        recs.append(
            "Remove credit card requirement from signup. Industry studies "
            "suggest requiring a card up front sharply reduces signups "
            "(figures of 60-80% are often cited). Collect payment "
            "information at the point of conversion instead."
        )

    if not result.trust_signals:
        recs.append(
            "Add trust signals near the signup form: customer logos, user count, "
            "security badges, or a brief testimonial. Trust signals can improve "
            "signup rates by 10-20%."
        )

    if result.cta_text.lower() in ("submit", "sign up", "register", ""):
        recs.append(
            "Improve CTA button text. Use value-oriented language like "
            "'Start free trial', 'Get started free', or 'Create your workspace' "
            "instead of generic labels."
        )

    if result.required_field_count > 5:
        recs.append(
            f"You have {result.required_field_count} required fields. "
            f"Mark most fields as optional and only require email. "
            f"Collect remaining data during onboarding."
        )

    return recs


def get_benchmark_comparison(friction_score: int) -> str:
    """Compare the friction score against industry benchmarks.

    Args:
        friction_score: The calculated friction score (0-100).

    Returns:
        A benchmark comparison string.
    """
    if friction_score <= 15:
        return "Excellent - Top 10% of SaaS signup flows. Very low friction."
    elif friction_score <= 30:
        return "Good - Top 25% of SaaS signup flows. Minor friction points."
    elif friction_score <= 50:
        return "Average - Typical SaaS signup friction. Room for improvement."
    elif friction_score <= 70:
        return "Below Average - Significant friction detected. Likely losing 30-50% of potential signups."
    else:
        return "Poor - Excessive friction. Likely losing 50-70% of potential signups. Immediate optimization needed."


def audit_signup_page(source: str) -> SignupAuditResult:
    """Perform a complete signup page friction audit.

    Fetches the signup page (or reads a local HTML file), analyzes form
    fields, SSO options, trust signals, and other friction factors. Returns
    a detailed result with friction score and recommendations.

    Args:
        source: The signup page URL or local HTML file path to audit.

    Returns:
        SignupAuditResult with all findings and recommendations.
    """
    result = SignupAuditResult(url=source)

    # Validate URL (skip validation for local files)
    if not os.path.isfile(source):
        parsed = urlparse(source)
        if not parsed.scheme or not parsed.netloc:
            result.errors.append("Invalid URL. Please provide a full URL including https://")
            result.fetch_failed = True
            return result

    # Fetch the page (or read the local file)
    soup = load_source(source)
    if soup is None:
        result.errors.append(
            "Could not fetch the page. This may be due to JavaScript rendering "
            "(SPA), access restrictions, or network issues."
        )
        result.fetch_failed = True
        return result

    # Non-English pages: the text-pattern heuristics are English-only and
    # would silently punish the page. Warn prominently instead.
    lang = detect_page_language(soup)
    if lang and not lang.startswith("en"):
        result.warnings.append(
            f"Page language is '{lang}'. Text-pattern checks (trust signals, "
            "credit card mentions, SSO button text) are unreliable for "
            "non-English pages - verify those manually from the page content."
        )

    # Find signup forms
    forms = find_forms(soup)
    if not forms:
        result.errors.append(
            "No signup form detected. The page may use JavaScript rendering "
            "(SPA) or the form may be loaded dynamically. Friction score is "
            "reported as N/A."
        )
        # Still check page-level signals for information, but do not score
        result.sso_providers, result.possible_sso = detect_sso_providers(soup)
        result.has_sso = bool(result.sso_providers)
        result.has_captcha = detect_captcha(soup)
        result.requires_cc = detect_credit_card(soup)
        result.trust_signals = detect_trust_signals(soup)
        result.recommendations = generate_recommendations(result)
        return result

    result.form_found = True

    # Analyze the primary form (first signup form found)
    primary_form = forms[0]

    # Count fields
    (
        result.field_count,
        result.required_field_count,
        result.required_checkbox_count,
    ) = count_form_fields(primary_form)

    # Detect password field
    result.has_password = detect_password_field(primary_form)

    # Detect SSO providers (verified buttons/links; page-wide = possible only)
    result.sso_providers, result.possible_sso = detect_sso_providers(soup)
    result.has_sso = bool(result.sso_providers)

    # Detect CAPTCHA
    result.has_captcha = detect_captcha(soup)

    # Detect credit card requirement
    result.requires_cc = detect_credit_card(soup)

    # Detect trust signals
    result.trust_signals = detect_trust_signals(soup)

    # Extract CTA text
    result.cta_text = extract_cta_text(primary_form)

    # Calculate friction score
    result.friction_score = calculate_friction_score(result)

    # Generate recommendations
    result.recommendations = generate_recommendations(result)

    return result


def format_report(result: SignupAuditResult) -> str:
    """Format the audit result as a readable report.

    Args:
        result: The completed audit result.

    Returns:
        Formatted report string.
    """
    lines = [
        "=" * 60,
        "SIGNUP FLOW FRICTION AUDIT",
        "=" * 60,
        f"URL: {result.url}",
    ]

    # Fetch failure: report the error prominently and no score at all.
    if result.fetch_failed:
        lines.extend([
            "",
            "!" * 60,
            "ERROR: The page could not be audited.",
        ])
        for error in result.errors:
            lines.append(f"  ! {error}")
        lines.extend([
            "!" * 60,
            "No friction score is available for this URL.",
            "=" * 60,
        ])
        return "\n".join(lines)

    if result.warnings:
        lines.append("")
        lines.append("!" * 60)
        for warning in result.warnings:
            lines.append(f"WARNING: {warning}")
        lines.append("!" * 60)

    if result.form_found:
        lines.extend([
            "",
            f"FRICTION SCORE: {result.friction_score}/100",
            f"Benchmark: {get_benchmark_comparison(result.friction_score)}",
        ])
    else:
        lines.extend([
            "",
            "FRICTION SCORE: N/A - no form detected on this page",
            "(Benchmark comparison suppressed: nothing was scored.)",
        ])

    lines.extend([
        "",
        "--- Form Analysis ---",
        f"Total form fields: {result.field_count}",
        f"Required fields: {result.required_field_count}",
        f"Required checkboxes: {result.required_checkbox_count}",
        f"Password field: {'Yes' if result.has_password else 'No'}",
        f"CTA text: {result.cta_text or 'Not detected'}",
        "",
        "--- Authentication ---",
        f"SSO available: {'Yes' if result.has_sso else 'No'}",
    ])

    if result.sso_providers:
        lines.append(f"SSO providers: {', '.join(result.sso_providers)}")
    if result.possible_sso:
        lines.append(
            "Possible SSO (unverified, page-wide mention only, not scored): "
            + ", ".join(result.possible_sso)
        )

    lines.extend([
        "",
        "--- Friction Factors ---",
        f"CAPTCHA: {'Yes' if result.has_captcha else 'No'}",
        f"Credit card required: {'Yes' if result.requires_cc else 'No'}",
        "",
        "--- Trust Signals ---",
    ])

    if result.trust_signals:
        for signal in result.trust_signals:
            lines.append(f"  + {signal}")
    else:
        lines.append("  No trust signals detected")

    lines.extend([
        "",
        "--- Recommendations ---",
    ])

    for i, rec in enumerate(result.recommendations, 1):
        lines.append(f"  {i}. {rec}")

    if result.errors:
        lines.extend([
            "",
            "--- Warnings ---",
        ])
        for error in result.errors:
            lines.append(f"  ! {error}")

    lines.append("=" * 60)
    return "\n".join(lines)


def main() -> None:
    """Run the signup auditor from the command line."""
    if len(sys.argv) < 2:
        print("Usage: python signup_auditor.py <signup_page_url_or_html_file>")
        print("Example: python signup_auditor.py https://example.com/signup")
        print("Example: python signup_auditor.py ./saved-signup-page.html")
        sys.exit(1)

    source = sys.argv[1]

    # Ensure URL has scheme (skip for local HTML files)
    if not os.path.isfile(source) and not source.startswith("http"):
        source = "https://" + source

    print(f"Auditing signup flow: {source}")
    print("Loading page...")
    print()

    result = audit_signup_page(source)

    # Print formatted report
    print(format_report(result))

    # Also output JSON for programmatic use
    print("\n--- JSON Output ---")
    print(json.dumps(asdict(result), indent=2))

    # Exit non-zero when nothing could be scored so callers do not mistake
    # a failed audit for a frictionless page.
    if result.fetch_failed or not result.form_found:
        sys.exit(1)


if __name__ == "__main__":
    main()
