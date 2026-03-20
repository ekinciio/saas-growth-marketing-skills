#!/usr/bin/env python3
"""
Signup Flow Auditor

Analyzes SaaS signup pages for friction points and provides a friction score
with actionable recommendations. Fetches the page HTML and evaluates form
fields, SSO options, trust signals, and other conversion factors.

Usage:
    python signup_auditor.py <signup_page_url>

Example:
    python signup_auditor.py https://example.com/signup
"""

import json
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
    has_sso: bool = False
    sso_providers: list = field(default_factory=list)
    has_password: bool = False
    has_captcha: bool = False
    requires_cc: bool = False
    cta_text: str = ""
    trust_signals: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    errors: list = field(default_factory=list)


# SSO provider detection patterns
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
    "SSO Generic": ["saml", "sso", "single-sign-on"],
}

# Trust signal detection patterns
TRUST_PATTERNS: list[dict[str, str]] = [
    {"name": "Security badge", "pattern": r"ssl|secure|encrypt|256[\s-]?bit|https"},
    {"name": "Money-back guarantee", "pattern": r"money[\s-]?back|guarantee|refund"},
    {"name": "No credit card required", "pattern": r"no\s+credit\s+card|no\s+cc|free"},
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

# Credit card detection patterns
CC_PATTERNS: list[str] = [
    "credit card",
    "credit-card",
    "card number",
    "card-number",
    "stripe",
    "payment method",
    "billing info",
    "cc-number",
    "cardNumber",
    "expiry",
    "cvv",
    "cvc",
]


def fetch_page(url: str, timeout: int = 15) -> Optional[BeautifulSoup]:
    """Fetch a web page and return a BeautifulSoup object.

    Args:
        url: The URL to fetch.
        timeout: Request timeout in seconds.

    Returns:
        BeautifulSoup object or None if the fetch failed.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
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


def count_form_fields(form) -> tuple[int, int]:
    """Count total and required form fields.

    Args:
        form: A BeautifulSoup form element.

    Returns:
        Tuple of (total_field_count, required_field_count).
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

    return total, required_count


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


def detect_sso_providers(soup: BeautifulSoup) -> list[str]:
    """Detect SSO/social login providers on the page.

    Args:
        soup: Parsed HTML page.

    Returns:
        List of detected SSO provider names.
    """
    page_text = str(soup).lower()
    found_providers = []

    for provider, patterns in SSO_PATTERNS.items():
        for pattern in patterns:
            if pattern in page_text:
                if provider not in found_providers:
                    found_providers.append(provider)
                break

    return found_providers


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

    Args:
        soup: Parsed HTML page.

    Returns:
        True if credit card requirement is detected.
    """
    page_text = str(soup).lower()
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
            f"Each field costs approximately 7% in conversions. Use progressive "
            f"profiling to collect additional data after signup."
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
            "Consider passwordless authentication (magic link or SSO-only). "
            "Password fields add friction and create future support burden "
            "for password resets."
        )

    if result.has_captcha:
        recs.append(
            "Replace visible CAPTCHA with invisible alternatives (reCAPTCHA v3 "
            "or Cloudflare Turnstile invisible mode). Visible CAPTCHAs add "
            "friction without significantly improving the user experience."
        )

    if result.requires_cc:
        recs.append(
            "Remove credit card requirement from signup. Products that require "
            "a credit card at signup see 60-80% fewer signups. Collect payment "
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


def audit_signup_page(url: str) -> SignupAuditResult:
    """Perform a complete signup page friction audit.

    Fetches the signup page, analyzes form fields, SSO options,
    trust signals, and other friction factors. Returns a detailed
    result with friction score and recommendations.

    Args:
        url: The signup page URL to audit.

    Returns:
        SignupAuditResult with all findings and recommendations.
    """
    result = SignupAuditResult(url=url)

    # Validate URL
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        result.errors.append("Invalid URL. Please provide a full URL including https://")
        return result

    # Fetch the page
    soup = fetch_page(url)
    if soup is None:
        result.errors.append(
            "Could not fetch the page. This may be due to JavaScript rendering "
            "(SPA), access restrictions, or network issues."
        )
        return result

    # Find signup forms
    forms = find_forms(soup)
    if not forms:
        result.errors.append(
            "No signup form detected. The page may use JavaScript rendering "
            "(SPA) or the form may be loaded dynamically."
        )
        # Still check page-level signals
        result.sso_providers = detect_sso_providers(soup)
        result.has_sso = bool(result.sso_providers)
        result.has_captcha = detect_captcha(soup)
        result.requires_cc = detect_credit_card(soup)
        result.trust_signals = detect_trust_signals(soup)
        result.friction_score = calculate_friction_score(result)
        result.recommendations = generate_recommendations(result)
        return result

    # Analyze the primary form (first signup form found)
    primary_form = forms[0]

    # Count fields
    result.field_count, result.required_field_count = count_form_fields(primary_form)

    # Detect password field
    result.has_password = detect_password_field(primary_form)

    # Detect SSO providers (check whole page, not just form)
    result.sso_providers = detect_sso_providers(soup)
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
        "",
        f"FRICTION SCORE: {result.friction_score}/100",
        f"Benchmark: {get_benchmark_comparison(result.friction_score)}",
        "",
        "--- Form Analysis ---",
        f"Total form fields: {result.field_count}",
        f"Required fields: {result.required_field_count}",
        f"Password field: {'Yes' if result.has_password else 'No'}",
        f"CTA text: {result.cta_text or 'Not detected'}",
        "",
        "--- Authentication ---",
        f"SSO available: {'Yes' if result.has_sso else 'No'}",
    ]

    if result.sso_providers:
        lines.append(f"SSO providers: {', '.join(result.sso_providers)}")

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
        print("Usage: python signup_auditor.py <signup_page_url>")
        print("Example: python signup_auditor.py https://example.com/signup")
        sys.exit(1)

    url = sys.argv[1]

    # Ensure URL has scheme
    if not url.startswith("http"):
        url = "https://" + url

    print(f"Auditing signup flow: {url}")
    print("Fetching page...")
    print()

    result = audit_signup_page(url)

    # Print formatted report
    print(format_report(result))

    # Also output JSON for programmatic use
    print("\n--- JSON Output ---")
    print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    main()
