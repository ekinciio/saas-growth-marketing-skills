"""geokit - fact extraction for the geo-seo-auditor skill.

Skill-specific helpers on top of the shared _growthkit library. Everything
here collects, parses, counts or matches; nothing judges quality. The model
scores with references/scoring-rubric.md and references/citability-guide.md.

Modules:
    roster     the AI crawler roster (references/ai-crawlers.json)
    robots     RFC 9309 robots.txt parsing and matching, Content-Signal
    discovery  page-type classification, sitemap parsing, URL sampling
    page       AI controls, rendering, schema and date facts for one page
    blocks     heading-scoped content blocks and numeric claims
    llms       llms.txt parsing, validation, drafts and suggestions
"""

from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
SKILL_DIR = SCRIPTS_DIR.parent
REFERENCES_DIR = SKILL_DIR / "references"
ROSTER_PATH = REFERENCES_DIR / "ai-crawlers.json"

# Seconds between two requests to the same host (politeness).
POLITE_DELAY = 1.0

__all__ = ["SCRIPTS_DIR", "SKILL_DIR", "REFERENCES_DIR", "ROSTER_PATH", "POLITE_DELAY"]
