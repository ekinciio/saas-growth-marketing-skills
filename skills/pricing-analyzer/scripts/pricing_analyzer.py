"""
SaaS Pricing Analyzer

Analyzes pricing strategy through tier gap analysis, competitive positioning,
and Van Westendorp price sensitivity calculations.

Usage:
    from pricing_analyzer import analyze_pricing

    own_pricing = {
        "tiers": [
            {"name": "Starter", "price": 29, "features": ["5 users", "Basic analytics", "Email support"]},
            {"name": "Pro", "price": 79, "features": ["25 users", "Advanced analytics", "Priority support", "API access"]},
            {"name": "Enterprise", "price": "custom", "features": ["Unlimited users", "Custom analytics", "Dedicated support", "API access", "SSO", "SLA"]},
        ]
    }

    result = analyze_pricing(own_pricing)
    print(result)

Accepted input shapes (all normalized before analysis):
    - Tier price: a number, a numeric string ("$10", "10.99", "1,200",
      "9,99"), "Free", or null / "custom" / "Contact sales" for a tier with no
      published price. Custom tiers sort last, count toward the tier count,
      and are left out of all price math.
    - Tier features: a list of strings, a comma-separated string, or
      missing (treated as an empty list).
    - Competitors: {"company": ..., "tiers": [...]} or the shorthand
      {"name": ..., "prices": [0, 19, 79]}. Competitors without any
      published price are skipped with a warning.
    - plg_motion: true/false/null, or the strings "true"/"false"/"yes"/"no".

Invalid input raises PricingInputError listing every bad field; the CLI
prints those messages and exits with code 2.
"""

from __future__ import annotations

import math
import re
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Input normalization and validation
# ---------------------------------------------------------------------------

class PricingInputError(ValueError):
    """Raised when the pricing input cannot be analyzed.

    ``problems`` holds one readable message per bad field so the CLI can
    print all of them at once.
    """

    def __init__(self, problems: list[str]) -> None:
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


SURVEY_KEYS = ("too_cheap", "bargain", "expensive", "too_expensive")

# Price strings that mean "no published price" (a "Contact sales" tier).
_CUSTOM_PRICE_RE = re.compile(
    r"\b(?:custom|contact|sales|quote|talk|call|demo|request|bespoke|"
    r"negotiable|enterprise|tbd)\b|get\s+in\s+touch|let'?s\s+chat",
    re.IGNORECASE,
)
_FREE_PRICE_RE = re.compile(r"^\s*free\b", re.IGNORECASE)
# "$1,200/yr", "99 per year": all price math here is monthly, so a yearly
# figure must not be read as a monthly one. ("$10/mo billed yearly" is fine.)
_YEARLY_PRICE_RE = re.compile(
    r"\d\s*(?:/|per|a)\s*(?:yr|year)\b", re.IGNORECASE
)
# The first number-like token in a price string: digits with "," or "."
# inside. _parse_number_token() decides what the separators mean.
_NUMBER_TOKEN_RE = re.compile(r"\d[\d.,]*\d|\d")
_PLAIN_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)?$")  # "29", "10.99"
_THOUSANDS_RE = re.compile(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$")  # "1,200", "1,200.50"
_DECIMAL_COMMA_RE = re.compile(r"^\d+,\d{1,2}$")  # "9,99" (European decimal comma)
_EU_THOUSANDS_RE = re.compile(r"^\d{1,3}(?:\.\d{3})+,\d{1,2}$")  # "1.200,50"
# "1.5k", "2M": a magnitude suffix right after the number would otherwise be
# dropped silently ("1.5k" read as 1.5). "10 mo" / "10 month" are fine.
_MAGNITUDE_SUFFIX_RE = re.compile(r"^\s*[km](?![a-z])", re.IGNORECASE)


def _parse_number_token(token: str) -> Optional[float]:
    """Read one number token, or return None when its separators are ambiguous."""
    if _PLAIN_NUMBER_RE.match(token):
        return float(token)
    if _THOUSANDS_RE.match(token):
        return float(token.replace(",", ""))
    if _DECIMAL_COMMA_RE.match(token):
        return float(token.replace(",", "."))
    if _EU_THOUSANDS_RE.match(token):
        return float(token.replace(".", "").replace(",", "."))
    return None

_TRUE_STRINGS = {"true", "yes", "y", "1", "on"}
_FALSE_STRINGS = {"false", "no", "n", "0", "off"}
_UNKNOWN_STRINGS = {"", "null", "none", "unknown", "skip", "n/a", "na", "?"}

_PRICE_HINT = (
    "use a number (0 for a free tier), or null / \"custom\" for a "
    "Contact sales tier"
)


def _clean_number(value: float) -> float:
    """Return an int when the value is whole, so $29 does not print as $29.0."""
    return int(value) if float(value).is_integer() else value


def _to_number(raw: Any, where: str) -> float:
    """Coerce a JSON number or numeric string to a non-negative number.

    Raises ValueError with a readable message for anything else.
    """
    if isinstance(raw, bool):
        # bool is a subclass of int; true/false is never a price.
        raise ValueError(f"{where}: {raw!r} is not a number")
    if isinstance(raw, (int, float)):
        value = raw
    elif isinstance(raw, str):
        text = raw.strip()
        if text.startswith("-"):
            raise ValueError(f"{where}: {raw!r} is negative")
        match = _NUMBER_TOKEN_RE.search(text)
        if not match:
            raise ValueError(f"{where}: {raw!r} is not a number")
        parsed = _parse_number_token(match.group(0))
        if parsed is None or _MAGNITUDE_SUFFIX_RE.match(text[match.end():]):
            raise ValueError(
                f"{where}: {raw!r} is not a clear number (write it in full, "
                "e.g. 1200 or 10.99)"
            )
        value = _clean_number(parsed)
    else:
        raise ValueError(
            f"{where}: expected a number, got {type(raw).__name__}"
        )
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"{where}: {raw!r} is not a finite number")
    if value < 0:
        raise ValueError(f"{where}: {raw!r} is negative")
    return value


def _parse_price(raw: Any, where: str) -> tuple[Optional[float], bool]:
    """Parse a tier price. Returns (price, is_custom).

    price is None for custom ("Contact sales") tiers. Raises ValueError
    when the value cannot be read as a price.
    """
    if raw is None:
        return None, True
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise ValueError(f"{where}: empty price - {_PRICE_HINT}")
        if _CUSTOM_PRICE_RE.search(text):
            return None, True
        if _FREE_PRICE_RE.match(text):
            # "Free", "Free forever", "Free for 3 users" (the 3 is not a price)
            return 0, False
        if _YEARLY_PRICE_RE.search(text):
            raise ValueError(
                f"{where}: {raw!r} looks like a yearly price - enter the "
                "monthly price (yearly price / 12)"
            )
    try:
        return _to_number(raw, where), False
    except ValueError as exc:
        raise ValueError(f"{exc} - {_PRICE_HINT}") from None


def _normalize_features(raw: Any, where: str, problems: list[str]) -> list[str]:
    """Return features as a list of non-empty strings (missing -> [])."""
    if raw is None:
        return []
    if isinstance(raw, str):
        # A single string is a comma/semicolon/newline separated list, not
        # one feature per character.
        return [part.strip() for part in re.split(r"[,;\n]", raw) if part.strip()]
    if isinstance(raw, (list, tuple)):
        features = []
        for item in raw:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                features.append(text)
        return features
    problems.append(
        f"{where}: expected a list of feature names, got {type(raw).__name__}"
    )
    return []


def _normalize_tier(
    raw: Any, where: str, index: int, problems: list[str]
) -> Optional[dict[str, Any]]:
    """Normalize one tier into {name, price, custom_price, features}.

    Accepts a tier dict, or a bare price (number, string or null) as used by
    the {"name": ..., "prices": [...]} competitor shorthand.
    """
    default_name = f"Tier {index + 1}"
    if isinstance(raw, dict):
        name = raw.get("name") or raw.get("tier") or raw.get("plan")
        name = str(name).strip() if name is not None else ""
        if "price" not in raw:
            problems.append(f"{where}.price is missing - {_PRICE_HINT}")
            return None
        price_raw = raw.get("price")
        price_where = f"{where}.price"
        features = _normalize_features(
            raw.get("features"), f"{where}.features", problems
        )
    elif raw is None or (
        isinstance(raw, (int, float, str)) and not isinstance(raw, bool)
    ):
        name = ""
        price_raw = raw
        price_where = where
        features = []
    else:
        problems.append(
            f"{where}: expected a tier object like "
            "{\"name\": \"Pro\", \"price\": 29, \"features\": [...]} or a "
            f"price, got {type(raw).__name__}"
        )
        return None

    try:
        price, custom = _parse_price(price_raw, price_where)
    except ValueError as exc:
        problems.append(str(exc))
        return None

    return {
        "name": name or default_name,
        "price": price,
        "custom_price": custom,
        "features": features,
    }


def _normalize_tier_list(
    raw: Any, where: str, problems: list[str]
) -> list[dict[str, Any]]:
    """Normalize a list of tiers (or a {name: price} mapping)."""
    if isinstance(raw, dict):
        # {"Free": 0, "Pro": 19} or {"Pro": {"price": 19, "features": [...]}}
        raw = [
            dict(value, name=value.get("name") or key)
            if isinstance(value, dict)
            else {"name": key, "price": value}
            for key, value in raw.items()
        ]
    if not isinstance(raw, list):
        problems.append(
            f"{where}: expected a list of tiers, got {type(raw).__name__}"
        )
        return []
    tiers = []
    for i, item in enumerate(raw):
        tier = _normalize_tier(item, f"{where}[{i}]", i, problems)
        if tier is not None:
            tiers.append(tier)
    return tiers


def _split_priced(
    tiers: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split tiers into (priced tiers sorted by price, custom tiers in input order)."""
    priced = sorted(
        (t for t in tiers if not t["custom_price"]), key=lambda t: t["price"]
    )
    custom = [t for t in tiers if t["custom_price"]]
    return priced, custom


def normalize_own_tiers(raw: Any) -> list[dict[str, Any]]:
    """Validate and normalize the user's own tiers. Raises PricingInputError."""
    problems: list[str] = []
    if raw is None:
        raise PricingInputError(
            ["tiers: missing - add a \"tiers\" list with at least one tier"]
        )
    tiers = _normalize_tier_list(raw, "tiers", problems)
    if not problems and not tiers:
        problems.append("tiers: the list is empty - add at least one tier")
    if problems:
        raise PricingInputError(problems)
    return tiers


def normalize_competitors(
    raw: Any,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Normalize competitor data. Returns (competitors, warnings).

    Accepts both {"company", "tiers"} and {"name", "prices"} shapes (and the
    mixed {"name", "tiers"} / {"company", "prices"}). Competitors with no
    published price are skipped with a warning rather than crashing the
    average-price math.
    """
    if raw is None:
        return [], []
    if isinstance(raw, dict):
        # {"Competitor A": [0, 19, 79], ...}
        raw = [{"company": key, "tiers": value} for key, value in raw.items()]
    if not isinstance(raw, list):
        raise PricingInputError(
            [f"competitors: expected a list, got {type(raw).__name__}"]
        )

    problems: list[str] = []
    warnings: list[str] = []
    competitors: list[dict[str, Any]] = []
    for i, comp in enumerate(raw):
        where = f"competitors[{i}]"
        if not isinstance(comp, dict):
            problems.append(
                f"{where}: expected an object like "
                "{\"company\": \"Acme\", \"tiers\": [...]} or "
                "{\"name\": \"Acme\", \"prices\": [0, 19, 79]}"
            )
            continue
        name = str(
            comp.get("company") or comp.get("name") or f"Competitor {i + 1}"
        ).strip()
        if comp.get("tiers") is not None:
            raw_tiers, key = comp["tiers"], "tiers"
        else:
            raw_tiers, key = comp.get("prices"), "prices"
        if raw_tiers is None:
            warnings.append(
                f"Competitor '{name}' has no 'tiers' or 'prices' - skipped."
            )
            continue
        before = len(problems)
        tiers = _normalize_tier_list(raw_tiers, f"{where}.{key}", problems)
        if len(problems) > before:
            continue
        if not any(not t["custom_price"] for t in tiers):
            warnings.append(
                f"Competitor '{name}' has no published price (all tiers custom "
                "or none listed) - skipped from the price comparison."
            )
            continue
        competitors.append({"company": name, "tiers": tiers})

    if problems:
        raise PricingInputError(problems)
    return competitors, warnings


def normalize_plg_motion(raw: Any) -> Optional[bool]:
    """Coerce plg_motion to True/False/None ("false" must not mean True)."""
    if raw is None or isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)) and raw in (0, 1):
        return bool(raw)
    if isinstance(raw, str):
        text = raw.strip().lower()
        if text in _TRUE_STRINGS:
            return True
        if text in _FALSE_STRINGS:
            return False
        if text in _UNKNOWN_STRINGS:
            return None
    raise PricingInputError(
        [f"plg_motion: {raw!r} is not true/false (use true, false, or null "
         "if unknown)"]
    )


def normalize_survey(raw: Any, where: str = "survey_data") -> dict[str, list[float]]:
    """Validate Van Westendorp survey lists and coerce numeric strings."""
    if not isinstance(raw, dict):
        raise PricingInputError(
            [f"{where}: expected an object with the keys "
             f"{', '.join(SURVEY_KEYS)}"]
        )
    problems: list[str] = []
    missing = [k for k in SURVEY_KEYS if k not in raw]
    if missing:
        problems.append(f"{where}: missing key(s) {', '.join(missing)}")
    survey: dict[str, list[float]] = {}
    for key in SURVEY_KEYS:
        if key not in raw:
            continue
        values = raw[key]
        if not isinstance(values, list):
            problems.append(
                f"{where}.{key}: expected a list of prices, got "
                f"{type(values).__name__}"
            )
            continue
        numbers = []
        for j, value in enumerate(values):
            try:
                numbers.append(_to_number(value, f"{where}.{key}[{j}]"))
            except ValueError as exc:
                problems.append(str(exc))
        survey[key] = numbers
    if problems:
        raise PricingInputError(problems)
    return survey


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_pricing(
    own_pricing: dict[str, Any],
    competitor_pricing: Optional[list[dict[str, Any]]] = None,
    survey_data: Optional[dict[str, list[float]]] = None,
    plg_motion: Optional[bool] = None,
) -> dict[str, Any]:
    """
    Analyze SaaS pricing strategy.

    Args:
        own_pricing: Dictionary with key "tiers", a list of tier dicts.
            Each tier dict has:
                - name (str): Tier name.
                - price (float | str | None): Monthly price in dollars.
                  null, "custom" or "Contact sales" marks a tier with no
                  published price.
                - features (list[str], optional): Feature descriptions.
        competitor_pricing: Optional list of competitor dicts, each with:
                - company (str): Competitor name (alias: name).
                - tiers (list[dict]): Same format as own_pricing tiers
                  (alias: prices, a plain list of prices).
            Note: All competitor data must be manually entered by the user.
        survey_data: Optional Van Westendorp survey results with keys:
                - too_cheap (list[float]): Prices respondents consider too cheap.
                - bargain (list[float]): Prices respondents consider a bargain.
                - expensive (list[float]): Prices respondents consider getting expensive.
                - too_expensive (list[float]): Prices respondents consider too expensive.
        plg_motion: Whether the company runs a PLG/self-serve motion.
            True raises a firm "no free tier" issue; False suppresses it;
            None (unknown) phrases it as something to consider. The strings
            "true"/"false"/"yes"/"no" are accepted.

    Returns:
        Dictionary with keys:
            - tier_analysis (dict): Gap analysis of current tiers.
            - competitive_positioning (dict or None): Positioning vs competitors.
            - van_westendorp (dict or None): Price sensitivity results.
            - recommended_changes (list[str]): Prioritized recommendations.
            - positioning_summary (str): Overall positioning assessment.
            - warnings (list[str]): Data that was skipped or could not be used.

    Raises:
        PricingInputError: when the input cannot be analyzed; ``problems``
            lists every bad field.
    """
    # Validate everything first and report all problems in one go.
    problems: list[str] = []
    warnings: list[str] = []
    tiers: list[dict[str, Any]] = []
    competitors: list[dict[str, Any]] = []
    survey: Optional[dict[str, list[float]]] = None
    motion: Optional[bool] = None

    if not isinstance(own_pricing, dict):
        problems.append("own pricing: expected an object with a \"tiers\" list")
    else:
        try:
            tiers = normalize_own_tiers(own_pricing.get("tiers"))
        except PricingInputError as exc:
            problems.extend(exc.problems)
    try:
        competitors, comp_warnings = normalize_competitors(competitor_pricing)
        warnings.extend(comp_warnings)
    except PricingInputError as exc:
        problems.extend(exc.problems)
    if survey_data:
        try:
            survey = normalize_survey(survey_data)
        except PricingInputError as exc:
            problems.extend(exc.problems)
    try:
        motion = normalize_plg_motion(plg_motion)
    except PricingInputError as exc:
        problems.extend(exc.problems)
    if problems:
        raise PricingInputError(problems)

    own_priced, _ = _split_priced(tiers)
    if not own_priced:
        warnings.append(
            "All of your tiers are custom-priced (Contact sales), so there is "
            "no published price for gap or competitor analysis."
        )

    tier_analysis = _analyze_tiers(tiers, plg_motion=motion)

    competitive_positioning = None
    if competitors and own_priced:
        competitive_positioning = _analyze_competitive_positioning(
            tiers, competitors
        )
    elif competitor_pricing and not competitors:
        warnings.append(
            "No competitor had a published price - competitive positioning "
            "skipped."
        )

    van_westendorp = None
    if survey:
        van_westendorp = _calculate_van_westendorp(survey)

    recommended_changes = _generate_recommendations(
        tier_analysis, competitive_positioning, van_westendorp
    )

    positioning_summary = _generate_positioning_summary(
        tiers, competitive_positioning
    )

    return {
        "tier_analysis": tier_analysis,
        "competitive_positioning": competitive_positioning,
        "van_westendorp": van_westendorp,
        "recommended_changes": recommended_changes,
        "positioning_summary": positioning_summary,
        "warnings": warnings,
    }


def _analyze_tiers(
    tiers: list[dict[str, Any]],
    plg_motion: Optional[bool] = None,
) -> dict[str, Any]:
    """Analyze tier structure for gaps and issues.

    Expects normalized tiers (see _normalize_tier). Custom-priced tiers are
    listed last and counted in tier_count, but take no part in price-gap
    math.
    """
    if not tiers:
        return {"error": "No tiers provided"}

    priced, custom = _split_priced(tiers)
    ordered = priced + custom
    analysis: dict[str, Any] = {
        "tier_count": len(ordered),
        "custom_tier_count": len(custom),
        "price_range": {
            "min": priced[0]["price"] if priced else None,
            "max": priced[-1]["price"] if priced else None,
        },
        "tiers": [],
        "issues": [],
    }

    for i, tier in enumerate(priced):
        tier_info: dict[str, Any] = {
            "name": tier["name"],
            "price": tier["price"],
            "custom_price": False,
            "feature_count": len(tier["features"]),
            # None when no features were listed: "$0/feature" for a $10
            # tier would look like a real (and wrong) number.
            "price_per_feature": (
                round(tier["price"] / len(tier["features"]), 2)
                if tier["features"]
                else None
            ),
        }

        # Check price jump to the next published price
        if i < len(priced) - 1:
            next_tier = priced[i + 1]
            price_jump = next_tier["price"] - tier["price"]
            price_jump_pct = (
                (price_jump / tier["price"] * 100) if tier["price"] > 0 else 0
            )
            feature_jump = len(next_tier["features"]) - len(tier["features"])

            tier_info["price_jump_to_next"] = price_jump
            tier_info["price_jump_pct"] = round(price_jump_pct, 1)
            tier_info["feature_jump_to_next"] = feature_jump

            # Flag issues. The jump into the top (enterprise) tier is exempt:
            # a large premium there is a standard anchoring pattern. When a
            # custom tier exists, that custom tier is the top tier.
            jump_is_into_top_tier = (i + 1) == len(ordered) - 1
            if price_jump_pct > 300 and not jump_is_into_top_tier:
                analysis["issues"].append(
                    f"Large price gap ({price_jump_pct:.0f}%) between "
                    f"{tier['name']} and {next_tier['name']} - "
                    f"consider adding an intermediate tier"
                )

            # Tiers described as "everything in <lower tier>, plus ..." carry
            # inherited features implicitly, so a small feature-count delta
            # is not a weak upgrade signal there. A tier with no features
            # listed tells us nothing, so it is not flagged either.
            next_features_text = " ".join(
                str(f) for f in next_tier["features"]
            ).lower()
            inherits_features = "everything in" in next_features_text
            if (
                next_tier["features"]
                and feature_jump <= 1
                and price_jump > 0
                and not inherits_features
            ):
                analysis["issues"].append(
                    f"Only {feature_jump} new feature(s) between "
                    f"{tier['name']} (${tier['price']}) and "
                    f"{next_tier['name']} (${next_tier['price']}) - "
                    f"weak upgrade justification"
                )

        analysis["tiers"].append(tier_info)

    for tier in custom:
        analysis["tiers"].append(
            {
                "name": tier["name"],
                "price": None,
                "custom_price": True,
                "feature_count": len(tier["features"]),
                "price_per_feature": None,
            }
        )

    # Check tier count (custom tiers count: they still anchor the page)
    if len(ordered) < 3:
        analysis["issues"].append(
            "Fewer than 3 tiers - consider adding tiers for better price anchoring"
        )
    elif len(ordered) > 4:
        analysis["issues"].append(
            "More than 4 tiers may create decision paralysis - consider consolidating"
        )

    # Check if lowest tier is free. Only firmly flag this for PLG/self-serve
    # motions; sales-led products often deliberately have no free tier.
    if priced and priced[0]["price"] > 0:
        if plg_motion:
            analysis["issues"].append(
                "No free tier - for a PLG/self-serve motion, consider freemium "
                "or a reverse trial for top-of-funnel growth"
            )
        elif plg_motion is None:
            analysis["issues"].append(
                "No free tier - consider whether a free tier fits your motion "
                "(mainly relevant for PLG/self-serve products)"
            )

    return analysis


def _analyze_competitive_positioning(
    own_tiers: list[dict[str, Any]],
    competitors: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare pricing against competitors.

    Expects normalized tiers and competitors that each have at least one
    published price. Average prices use published (non-custom) tiers only;
    tier and feature counts include custom tiers.
    """
    own_priced, _ = _split_priced(own_tiers)
    own_avg_price = sum(t["price"] for t in own_priced) / len(own_priced)
    own_avg_features = sum(len(t["features"]) for t in own_tiers) / len(own_tiers)

    competitor_analysis = []
    for comp in competitors:
        comp_priced, comp_custom = _split_priced(comp["tiers"])
        comp_avg_price = sum(t["price"] for t in comp_priced) / len(comp_priced)
        comp_avg_features = (
            sum(len(t["features"]) for t in comp["tiers"]) / len(comp["tiers"])
        )

        price_diff_pct = ((own_avg_price - comp_avg_price) / comp_avg_price * 100) if comp_avg_price > 0 else 0

        positioning = "similar"
        if price_diff_pct > 20:
            positioning = "premium"
        elif price_diff_pct < -20:
            positioning = "value"

        competitor_analysis.append(
            {
                "company": comp["company"],
                "avg_price": round(comp_avg_price, 2),
                "avg_features": round(comp_avg_features, 1),
                "tier_count": len(comp["tiers"]),
                "custom_tier_count": len(comp_custom),
                "price_range": {
                    "min": comp_priced[0]["price"],
                    "max": comp_priced[-1]["price"],
                },
                "your_price_diff_pct": round(price_diff_pct, 1),
                "relative_positioning": positioning,
            }
        )

    all_avg_prices = [c["avg_price"] for c in competitor_analysis]
    market_avg = sum(all_avg_prices) / len(all_avg_prices) if all_avg_prices else 0

    return {
        "your_avg_price": round(own_avg_price, 2),
        "your_avg_features": round(own_avg_features, 1),
        "market_avg_price": round(market_avg, 2),
        "competitors": competitor_analysis,
        "your_position": (
            "above market" if own_avg_price > market_avg * 1.1
            else "below market" if own_avg_price < market_avg * 0.9
            else "at market"
        ),
    }


def _calculate_van_westendorp(
    survey_data: dict[str, list[float]],
) -> dict[str, Any]:
    """
    Calculate Van Westendorp price sensitivity intersections.

    Uses the standard Price Sensitivity Meter (PSM) cumulative curves:
        - "too cheap"     = % of respondents with too_cheap >= p (decreasing)
        - "cheap"         = % of respondents with bargain >= p (decreasing)
        - "expensive"     = % of respondents with expensive <= p (increasing)
        - "too expensive" = % of respondents with too_expensive <= p (increasing)

    Intersection points (R pricesensitivitymeter convention):
        - OPP (Optimal Price Point): "too cheap" x "too expensive"
        - IDP (Indifference Price Point): "cheap" x "expensive"
        - PMC (Point of Marginal Cheapness): "too cheap" x "not cheap"
          (where "not cheap" = 100 - "cheap", increasing)
        - PME (Point of Marginal Expensiveness): "too expensive" x
          "not expensive" (where "not expensive" = 100 - "expensive", decreasing)
    """
    too_cheap = sorted(survey_data["too_cheap"])
    bargain = sorted(survey_data["bargain"])
    expensive = sorted(survey_data["expensive"])
    too_expensive = sorted(survey_data["too_expensive"])

    # Build a common price range
    all_prices = too_cheap + bargain + expensive + too_expensive
    if not all_prices:
        return {"error": "No survey data provided"}

    min_price = min(all_prices)
    max_price = max(all_prices)
    step = (max_price - min_price) / 200
    if step == 0:
        return {"error": "All survey responses are the same price"}

    price_points = [min_price + i * step for i in range(201)]

    def pct_at_or_below(data: list[float], price: float) -> float:
        count = sum(1 for v in data if v <= price)
        return count / len(data) * 100 if data else 0

    def pct_at_or_above(data: list[float], price: float) -> float:
        count = sum(1 for v in data if v >= price)
        return count / len(data) * 100 if data else 0

    def curve_too_cheap(p: float) -> float:
        return pct_at_or_above(too_cheap, p)  # decreasing

    def curve_cheap(p: float) -> float:
        return pct_at_or_above(bargain, p)  # decreasing

    def curve_expensive(p: float) -> float:
        return pct_at_or_below(expensive, p)  # increasing

    def curve_too_expensive(p: float) -> float:
        return pct_at_or_below(too_expensive, p)  # increasing

    # Find intersections by scanning price points
    opp = _find_intersection(price_points, curve_too_cheap, curve_too_expensive)

    idp = _find_intersection(price_points, curve_cheap, curve_expensive)

    pmc = _find_intersection(
        price_points,
        curve_too_cheap,
        lambda p: 100.0 - curve_cheap(p),  # "not cheap", increasing
    )

    pme = _find_intersection(
        price_points,
        curve_too_expensive,
        lambda p: 100.0 - curve_expensive(p),  # "not expensive", decreasing
    )

    acceptable_range = {
        "low": round(pmc, 2) if pmc is not None else None,
        "high": round(pme, 2) if pme is not None else None,
    }

    return {
        "optimal_price_point": round(opp, 2) if opp is not None else None,
        "indifference_price_point": round(idp, 2) if idp is not None else None,
        "point_of_marginal_expensiveness": round(pme, 2) if pme is not None else None,
        "point_of_marginal_cheapness": round(pmc, 2) if pmc is not None else None,
        "acceptable_price_range": acceptable_range,
        "sample_size": len(too_cheap),
        "recommendation": (
            f"Set price between ${acceptable_range['low']} and "
            f"${acceptable_range['high']}, targeting ${round(opp, 2)} "
            f"as the optimal price point."
            if opp is not None and pmc is not None and pme is not None
            else "Insufficient data to determine optimal price point."
        ),
    }


def _find_intersection(
    price_points: list[float],
    curve_a: Any,
    curve_b: Any,
) -> Optional[float]:
    """Find the price where two cumulative curves intersect.

    Treats any sign change (including touching zero) as a crossing. When the
    two curves are exactly equal across a run of scan points, returns the
    midpoint of that zero-run. Otherwise linearly interpolates between the
    two scan points that bracket the sign flip.
    """
    prev_price: Optional[float] = None
    prev_diff: Optional[float] = None
    zero_start: Optional[float] = None
    zero_end: Optional[float] = None

    for price in price_points:
        diff = curve_a(price) - curve_b(price)

        if diff == 0:
            if zero_start is None:
                zero_start = price
            zero_end = price
            prev_price, prev_diff = price, diff
            continue

        if zero_start is not None:
            # A zero-run just ended: the crossing is inside the run.
            return (zero_start + zero_end) / 2

        if prev_diff is not None and prev_diff * diff < 0:
            # Sign flip between two scan points: linear interpolation.
            fraction = abs(prev_diff) / (abs(prev_diff) + abs(diff))
            return prev_price + (price - prev_price) * fraction

        prev_price, prev_diff = price, diff

    if zero_start is not None:
        return (zero_start + zero_end) / 2
    return None


def _generate_recommendations(
    tier_analysis: dict[str, Any],
    competitive: Optional[dict[str, Any]],
    van_westendorp: Optional[dict[str, Any]],
) -> list[str]:
    """Generate prioritized pricing recommendations."""
    recommendations: list[str] = []

    # Tier-based recommendations
    for issue in tier_analysis.get("issues", []):
        recommendations.append(f"Tier structure: {issue}")

    # Competitive recommendations
    if competitive:
        position = competitive.get("your_position", "")
        if position == "above market":
            recommendations.append(
                "Your average price is above market - ensure your premium positioning "
                "is justified by clear feature differentiation and brand strength."
            )
        elif position == "below market":
            recommendations.append(
                "Your average price is below market - you may have room for a price "
                "increase. Test a 10-15% increase on new customers first."
            )

    # Van Westendorp recommendations
    if van_westendorp and van_westendorp.get("optimal_price_point"):
        opp = van_westendorp["optimal_price_point"]
        recommendations.append(
            f"Van Westendorp analysis suggests an optimal price point of ${opp}. "
            f"Align your most popular tier close to this price."
        )

    if not recommendations:
        # Only suggest the analyses that were not already run.
        missing = []
        if van_westendorp is None:
            missing.append("running a Van Westendorp survey")
        if competitive is None:
            missing.append("adding competitor data")
        if missing:
            recommendations.append(
                f"No major issues detected. Consider {' or '.join(missing)} "
                "for deeper analysis."
            )
        else:
            recommendations.append(
                "No major issues detected in tier structure, competitive "
                "positioning or price sensitivity."
            )

    return recommendations


def _generate_positioning_summary(
    own_tiers: list[dict[str, Any]],
    competitive: Optional[dict[str, Any]],
) -> str:
    """Generate a text summary of pricing positioning."""
    priced, custom = _split_priced(own_tiers)
    ordered = priced + custom
    tier_names = ", ".join(t["name"] for t in ordered)
    custom_names = ", ".join(t["name"] for t in custom)

    if priced:
        price_range = f"${priced[0]['price']} - ${priced[-1]['price']}/mo"
        summary = (
            f"Your pricing spans {price_range} across {len(ordered)} tiers "
            f"({tier_names})."
        )
        if custom:
            verb = "is" if len(custom) == 1 else "are"
            summary += f" {custom_names} {verb} custom-priced (Contact sales)."
    else:
        summary = (
            f"All {len(ordered)} of your tiers are custom-priced "
            f"(Contact sales): {tier_names}."
        )

    if competitive:
        position = competitive["your_position"]
        market_avg = competitive["market_avg_price"]
        summary += (
            f" Relative to competitors, you are positioned {position} "
            f"(market average: ${market_avg}/mo)."
        )

    return summary


def _fmt_price(value: Optional[float]) -> str:
    """Format a price value, guarding against missing data."""
    return f"${value}" if value is not None else "insufficient data"


def _print_warnings(warnings: list[str]) -> None:
    """Print data that was skipped or could not be used, if any."""
    if not warnings:
        return
    print("Warnings:")
    for warning in warnings:
        print(f"  - {warning}")
    print()


def _print_van_westendorp(vw: dict[str, Any]) -> None:
    """Print a Van Westendorp result block."""
    if vw.get("error"):
        print(f"\nVan Westendorp Analysis: {vw['error']}")
        return
    print(f"\nVan Westendorp Analysis (n={vw['sample_size']}):")
    print(f"  Optimal Price Point: {_fmt_price(vw['optimal_price_point'])}")
    print(f"  Indifference Price Point: {_fmt_price(vw['indifference_price_point'])}")
    print(f"  Point of Marginal Cheapness: {_fmt_price(vw['point_of_marginal_cheapness'])}")
    print(f"  Point of Marginal Expensiveness: {_fmt_price(vw['point_of_marginal_expensiveness'])}")
    print(
        f"  Acceptable Range: {_fmt_price(vw['acceptable_price_range']['low'])}"
        f" - {_fmt_price(vw['acceptable_price_range']['high'])}"
    )
    print(f"  Recommendation: {vw['recommendation']}")


def _print_analysis(result: dict[str, Any]) -> None:
    """Print a full pricing analysis result."""
    _print_warnings(result.get("warnings") or [])

    print("Positioning Summary:")
    print(f"  {result['positioning_summary']}")

    print(f"\nTier Analysis ({result['tier_analysis']['tier_count']} tiers):")
    for tier in result["tier_analysis"]["tiers"]:
        if tier.get("custom_price"):
            features = (
                f"{tier['feature_count']} features"
                if tier["feature_count"] else "no features listed"
            )
            print(f"  {tier['name']}: custom price (Contact sales) - {features}")
            continue
        if tier["price_per_feature"] is None:
            print(f"  {tier['name']}: ${tier['price']}/mo - no features listed")
            continue
        print(
            f"  {tier['name']}: ${tier['price']}/mo - {tier['feature_count']} "
            f"features (${tier['price_per_feature']}/feature)"
        )

    if result["tier_analysis"]["issues"]:
        print("\n  Issues:")
        for issue in result["tier_analysis"]["issues"]:
            print(f"    - {issue}")

    if result["competitive_positioning"]:
        cp = result["competitive_positioning"]
        print("\nCompetitive Positioning:")
        print(f"  Your avg price: ${cp['your_avg_price']}")
        print(f"  Market avg price: ${cp['market_avg_price']}")
        print(f"  Position: {cp['your_position']}")
        for comp in cp["competitors"]:
            print(f"  vs {comp['company']}: {comp['your_price_diff_pct']:+.1f}% ({comp['relative_positioning']})")

    if result["van_westendorp"]:
        _print_van_westendorp(result["van_westendorp"])

    print("\nRecommended Changes:")
    for i, rec in enumerate(result["recommended_changes"], 1):
        print(f"  {i}. {rec}")


def main() -> None:
    """Standalone demo of the pricing analyzer."""
    print("=" * 60)
    print("Pricing Analyzer - Demo")
    print("=" * 60)

    # Example: Own pricing
    own_pricing = {
        "tiers": [
            {
                "name": "Starter",
                "price": 29,
                "features": [
                    "5 users",
                    "Basic analytics",
                    "Email support",
                    "1 GB storage",
                ],
            },
            {
                "name": "Pro",
                "price": 79,
                "features": [
                    "25 users",
                    "Advanced analytics",
                    "Priority support",
                    "API access",
                    "10 GB storage",
                    "Custom reports",
                ],
            },
            {
                "name": "Enterprise",
                "price": 199,
                "features": [
                    "Unlimited users",
                    "Custom analytics",
                    "Dedicated support",
                    "API access",
                    "Unlimited storage",
                    "SSO",
                    "SLA",
                    "Custom integrations",
                ],
            },
        ]
    }

    # Example: Competitor pricing (manually entered)
    competitors = [
        {
            "company": "Competitor A",
            "tiers": [
                {"name": "Basic", "price": 19, "features": ["3 users", "Basic reporting", "Email support"]},
                {"name": "Business", "price": 59, "features": ["15 users", "Advanced reporting", "Chat support", "API"]},
                {"name": "Enterprise", "price": 149, "features": ["Unlimited users", "Custom reporting", "Phone support", "API", "SSO"]},
            ],
        },
        {
            "company": "Competitor B",
            "tiers": [
                {"name": "Free", "price": 0, "features": ["2 users", "Basic features"]},
                {"name": "Team", "price": 49, "features": ["10 users", "Core features", "Email support"]},
                {"name": "Business", "price": 99, "features": ["50 users", "All features", "Priority support", "API"]},
                {"name": "Enterprise", "price": 249, "features": ["Unlimited users", "All features", "Dedicated CSM", "SLA", "SSO"]},
            ],
        },
    ]

    # Example: Van Westendorp survey data
    survey_data = {
        "too_cheap": [10, 15, 15, 20, 20, 20, 25, 25, 30, 30, 30, 35, 35, 40, 40],
        "bargain": [25, 30, 35, 35, 40, 40, 45, 45, 50, 50, 55, 55, 60, 60, 65],
        "expensive": [60, 65, 70, 70, 75, 80, 80, 85, 85, 90, 90, 95, 100, 100, 110],
        "too_expensive": [80, 90, 95, 100, 100, 110, 110, 120, 120, 130, 130, 140, 150, 150, 160],
    }

    print("\n--- Analysis with all data ---\n")
    result = analyze_pricing(own_pricing, competitors, survey_data)
    _print_analysis(result)


_PRICING_SHAPE_HINT = (
    "Expected shape: "
    "{\"tiers\": [{\"name\": \"Pro\", \"price\": 29, \"features\": [...]}], "
    "\"competitors\": [{\"company\": \"Acme\", \"tiers\": [...]}]} "
    "(see the docstring at the top of pricing_analyzer.py)."
)
_SURVEY_SHAPE_HINT = (
    "Expected shape: {\"too_cheap\": [...], \"bargain\": [...], "
    "\"expensive\": [...], \"too_expensive\": [...]} with one price per "
    "respondent in each list."
)


def _fail(problems: list[str], hint: str = _PRICING_SHAPE_HINT) -> None:
    """Print readable input errors to stderr and exit with code 2."""
    import sys

    print("Input error - the pricing JSON could not be analyzed:", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    print(f"Fix the fields above and run again. {hint}", file=sys.stderr)
    sys.exit(2)


def _cli() -> None:
    """Command-line entry point: JSON file, stdin, or --demo.

    The JSON file can be either:
      - a survey file with the four Van Westendorp keys
        (too_cheap, bargain, expensive, too_expensive), or
      - a pricing file with "tiers" (and optional "competitors",
        "survey_data", and "plg_motion" keys).

    Exit codes: 0 success, 2 invalid input (bad JSON, missing file or
    invalid fields; every problem is listed on stderr).
    """
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        description="SaaS pricing analyzer",
        epilog="Pass a tiers JSON ({\"tiers\": [...]}) or a Van Westendorp "
               "survey JSON (too_cheap/bargain/expensive/too_expensive lists).",
    )
    parser.add_argument(
        "input", nargs="?",
        help="Path to a JSON file (or '-' for stdin)",
    )
    parser.add_argument(
        "--demo", action="store_true", help="Run with built-in sample data"
    )
    args = parser.parse_args()

    if args.demo or (args.input is None and sys.stdin.isatty()):
        main()
        return

    source = "stdin" if args.input in (None, "-") else args.input
    try:
        if source == "stdin":
            payload = json.load(sys.stdin)
        else:
            with open(args.input, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
    except FileNotFoundError:
        _fail([f"input file not found: {args.input}"])
    except (OSError, UnicodeDecodeError) as exc:
        _fail([f"could not read {source}: {exc}"])
    except json.JSONDecodeError as exc:
        _fail([f"{source} is not valid JSON: {exc}"])

    if isinstance(payload, list):
        # A bare list is taken as the tiers list.
        payload = {"tiers": payload}
    if not isinstance(payload, dict):
        _fail(["the JSON must be an object with a \"tiers\" list (or the four "
               "Van Westendorp survey lists)"])

    survey_keys = set(SURVEY_KEYS)
    if "tiers" not in payload and survey_keys.issubset(payload):
        # Survey-only file: run just the Van Westendorp analysis.
        try:
            survey = normalize_survey(
                {k: payload[k] for k in survey_keys}, where="survey"
            )
        except PricingInputError as exc:
            _fail(exc.problems, _SURVEY_SHAPE_HINT)
        vw = _calculate_van_westendorp(survey)
        print("=" * 60)
        print("Pricing Analyzer - Van Westendorp Price Sensitivity")
        print("=" * 60)
        _print_van_westendorp(vw)
        return

    if "tiers" not in payload:
        _fail([
            "input JSON must contain either a 'tiers' list or the four Van "
            "Westendorp survey keys (too_cheap, bargain, expensive, "
            "too_expensive)"
        ])

    survey_data = payload.get("survey_data") or payload.get("survey")
    if survey_data is None and survey_keys.issubset(payload):
        survey_data = {k: payload[k] for k in survey_keys}

    try:
        result = analyze_pricing(
            {"tiers": payload["tiers"]},
            payload.get("competitors") or payload.get("competitor_pricing"),
            survey_data,
            plg_motion=payload.get("plg_motion"),
        )
    except PricingInputError as exc:
        _fail(exc.problems)
    print("=" * 60)
    print("Pricing Analyzer")
    print("=" * 60)
    print()
    _print_analysis(result)


if __name__ == "__main__":
    _cli()
