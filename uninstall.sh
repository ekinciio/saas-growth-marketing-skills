#!/usr/bin/env bash
# SaaS Growth Marketing Skills Uninstaller
# https://github.com/ekinciio/saas-growth-marketing-skills

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

CLAUDE_DIR="$HOME/.claude"
SKILLS_DIR="$CLAUDE_DIR/skills"
AGENTS_DIR="$CLAUDE_DIR/agents"
TEMPLATES_DIR="$CLAUDE_DIR/templates"

# Skills to remove
SKILLS=(
    "geo-seo-auditor"
    "aso-optimizer"
    "local-seo-optimizer"
    "review-sentiment"
    "landing-page-cro"
    "plg-funnel-analyzer"
    "subscription-metrics"
    "onboarding-optimizer"
    "retention-playbook"
    "pricing-analyzer"
    "competitor-intel"
    "web-app-growth-engine"
    "saas-landing-builder"
    "reddit-opportunity-finder"
    "brand-mention-scanner"
    "growth-skills"
)

AGENTS=(
    "growth-strategist.md"
    "launch-planner.md"
    "metrics-analyst.md"
)

TEMPLATES_LIST=(
    "gtm-strategy.md"
    "pricing-analysis.md"
    "launch-checklist.md"
    "report-template.md"
)

echo ""
echo -e "${BOLD}SaaS Growth Marketing Skills - Uninstaller${NC}"
echo ""
echo "This will remove all SaaS Growth Marketing Skills from your system."
echo ""
echo "The following will be deleted:"
echo -e "  - ${YELLOW}${#SKILLS[@]} skills${NC} from $SKILLS_DIR"
echo -e "  - ${YELLOW}${#AGENTS[@]} agents${NC} from $AGENTS_DIR"
echo -e "  - ${YELLOW}${#TEMPLATES_LIST[@]} templates${NC} from $TEMPLATES_DIR"
echo ""

read -p "Are you sure? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Uninstall cancelled.${NC}"
    exit 0
fi

echo ""

# Remove skills
echo -e "${BOLD}Removing skills...${NC}"
for skill in "${SKILLS[@]}"; do
    if [ -d "$SKILLS_DIR/$skill" ]; then
        rm -rf "$SKILLS_DIR/$skill"
        echo -e "  ${RED}-${NC} $skill"
    fi
done

# Remove agents
echo -e "${BOLD}Removing agents...${NC}"
for agent in "${AGENTS[@]}"; do
    if [ -f "$AGENTS_DIR/$agent" ]; then
        rm -f "$AGENTS_DIR/$agent"
        echo -e "  ${RED}-${NC} ${agent%.md}"
    fi
done

# Remove templates
echo -e "${BOLD}Removing templates...${NC}"
for template in "${TEMPLATES_LIST[@]}"; do
    if [ -f "$TEMPLATES_DIR/$template" ]; then
        rm -f "$TEMPLATES_DIR/$template"
        echo -e "  ${RED}-${NC} ${template%.md}"
    fi
done

echo ""
echo -e "${GREEN}${BOLD}Uninstall complete.${NC}"
echo ""
echo "SaaS Growth Marketing Skills have been removed from your system."
echo "Python dependencies (requests, beautifulsoup4, lxml) were not removed."
echo ""
