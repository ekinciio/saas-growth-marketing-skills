"""growthkit - shared helpers for the SaaS Growth Marketing Skills scripts.

The source lives in shared/growthkit/. tools/sync_shared.py copies it into
every skill as scripts/_growthkit/ so an installed skill folder stays
self-contained. Skill scripts import the modules they need explicitly:

    from _growthkit import cli, http, html, report

Modules:
    cli     argument parsing, exit codes, JSON envelope, input coercion
    http    fetch() that never raises and reports blocked / JS-shell pages
    html    clean_text(), hidden-node removal, page_facts()
    report  growth-reports/<date>-<skill>-<slug>.md plus a JSON sidecar

This file deliberately imports nothing heavy, so cli and report keep working
when requests or beautifulsoup4 are not installed (http and html print an
install hint and exit 2 in that case).
"""

import warnings

__version__ = "2.0.0"

TOOLKIT_NAME = "SaaS Growth Marketing Skills"
REPO_URL = "https://github.com/ekinciio/saas-growth-marketing-skills"
# Short form used in the report footer (no scheme, matches every SKILL.md).
REPO_SHORT = "github.com/ekinciio/saas-growth-marketing-skills"

INSTALL_HINT = "python3 -m pip install --user requests beautifulsoup4"

# Stock macOS python3 (3.9 + LibreSSL) makes urllib3 print a NotOpenSSLWarning
# on import. The model reads stderr and may treat it as an error, so silence
# it before any submodule imports requests.
warnings.filterwarnings("ignore", message=".*OpenSSL.*")

__all__ = [
    "__version__",
    "TOOLKIT_NAME",
    "REPO_URL",
    "REPO_SHORT",
    "INSTALL_HINT",
]
