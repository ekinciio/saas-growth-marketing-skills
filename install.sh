#!/usr/bin/env bash
# SaaS Growth Marketing Skills Installer
# https://github.com/ekinciio/saas-growth-marketing-skills

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

REPO_URL="https://github.com/ekinciio/saas-growth-marketing-skills.git"
REPO_NAME="saas-growth-marketing-skills"
CLAUDE_DIR="$HOME/.claude"
SKILLS_DIR="$CLAUDE_DIR/skills"
AGENTS_DIR="$CLAUDE_DIR/agents"
TEMPLATES_DIR="$CLAUDE_DIR/templates"
TEMP_DIR=$(mktemp -d)

echo ""
echo -e "${CYAN}${BOLD}"
echo "  ____    _    ____ ____     ____                   _   _     "
echo " / ___|  / \  |  _ / ___|   / ___|_ __ _____      _| |_| |__  "
echo " \___ \ / _ \ | |_\___ \  | |  _| '__/ _ \ \ /\ / / __| '_ \ "
echo "  ___) / ___ \|  _|___) | | |_| | | | (_) \ V  V /| |_| | | |"
echo " |____/_/   \_|_| |____/   \____|_|  \___/ \_/\_/  \__|_| |_|"
echo ""
echo -e "  Marketing Skills${NC}"
echo ""
echo -e "${BOLD}  Growth marketing skills for AI coding agents${NC}"
echo -e "  Built for Claude Code"
echo ""
echo "---------------------------------------------------"
echo ""

# Check dependencies
echo -e "${BLUE}Checking dependencies...${NC}"

if ! command -v git &> /dev/null; then
    echo -e "${RED}Error: git is not installed. Please install git first.${NC}"
    exit 1
fi
echo -e "  ${GREEN}git${NC} - found"

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is not installed. Please install Python 3.8+ first.${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "  ${GREEN}python3${NC} - found (v$PYTHON_VERSION)"

if ! command -v pip3 &> /dev/null && ! command -v pip &> /dev/null; then
    echo -e "${YELLOW}Warning: pip not found. Python dependencies will need manual installation.${NC}"
    PIP_AVAILABLE=false
else
    PIP_AVAILABLE=true
    echo -e "  ${GREEN}pip${NC} - found"
fi

echo ""

# Clone repository
echo -e "${BLUE}Downloading SaaS Growth Marketing Skills...${NC}"
git clone --quiet "$REPO_URL" "$TEMP_DIR/$REPO_NAME" 2>/dev/null || {
    echo -e "${RED}Error: Failed to clone repository.${NC}"
    echo -e "  Check your internet connection and try again."
    rm -rf "$TEMP_DIR"
    exit 1
}
echo -e "  ${GREEN}Repository cloned successfully${NC}"
echo ""

# Create directories
echo -e "${BLUE}Setting up directories...${NC}"
mkdir -p "$SKILLS_DIR"
mkdir -p "$AGENTS_DIR"
mkdir -p "$TEMPLATES_DIR"

# Install skills
echo -e "${BLUE}Installing skills...${NC}"
SKILL_COUNT=0
for skill_dir in "$TEMP_DIR/$REPO_NAME/skills"/*/; do
    if [ -d "$skill_dir" ]; then
        skill_name=$(basename "$skill_dir")
        cp -r "$skill_dir" "$SKILLS_DIR/$skill_name"
        echo -e "  ${GREEN}+${NC} $skill_name"
        SKILL_COUNT=$((SKILL_COUNT + 1))
    fi
done
echo -e "  ${GREEN}$SKILL_COUNT skills installed${NC}"
echo ""

# Install agents
echo -e "${BLUE}Installing agents...${NC}"
AGENT_COUNT=0
for agent_file in "$TEMP_DIR/$REPO_NAME/agents"/*.md; do
    if [ -f "$agent_file" ]; then
        agent_name=$(basename "$agent_file")
        cp "$agent_file" "$AGENTS_DIR/$agent_name"
        echo -e "  ${GREEN}+${NC} ${agent_name%.md}"
        AGENT_COUNT=$((AGENT_COUNT + 1))
    fi
done
echo -e "  ${GREEN}$AGENT_COUNT agents installed${NC}"
echo ""

# Install templates
echo -e "${BLUE}Installing templates...${NC}"
TEMPLATE_COUNT=0
for template_file in "$TEMP_DIR/$REPO_NAME/templates"/*.md; do
    if [ -f "$template_file" ]; then
        template_name=$(basename "$template_file")
        cp "$template_file" "$TEMPLATES_DIR/$template_name"
        echo -e "  ${GREEN}+${NC} ${template_name%.md}"
        TEMPLATE_COUNT=$((TEMPLATE_COUNT + 1))
    fi
done
echo -e "  ${GREEN}$TEMPLATE_COUNT templates installed${NC}"
echo ""

# Install Python dependencies
if [ "$PIP_AVAILABLE" = true ]; then
    echo -e "${BLUE}Installing Python dependencies...${NC}"
    if command -v pip3 &> /dev/null; then
        pip3 install -q -r "$TEMP_DIR/$REPO_NAME/requirements.txt" 2>/dev/null || {
            echo -e "${YELLOW}Warning: Some Python dependencies failed to install.${NC}"
            echo -e "  Run manually: pip3 install -r requirements.txt"
        }
    else
        pip install -q -r "$TEMP_DIR/$REPO_NAME/requirements.txt" 2>/dev/null || {
            echo -e "${YELLOW}Warning: Some Python dependencies failed to install.${NC}"
        }
    fi
    echo -e "  ${GREEN}Dependencies installed${NC}"
    echo ""
fi

# Cleanup
rm -rf "$TEMP_DIR"

# Summary
echo "---------------------------------------------------"
echo ""
echo -e "${GREEN}${BOLD}Installation complete!${NC}"
echo ""
echo -e "  ${BOLD}Skills:${NC}    $SKILL_COUNT installed"
echo -e "  ${BOLD}Agents:${NC}    $AGENT_COUNT installed"
echo -e "  ${BOLD}Templates:${NC} $TEMPLATE_COUNT installed"
echo ""
echo -e "${BOLD}Installed skills:${NC}"
echo ""
for skill_dir in "$SKILLS_DIR"/*/; do
    if [ -d "$skill_dir" ]; then
        echo -e "  ${CYAN}$(basename "$skill_dir")${NC}"
    fi
done
echo ""
echo "---------------------------------------------------"
echo ""
echo -e "${BOLD}Quick Start:${NC}"
echo ""
echo -e "  ${YELLOW}/geo-seo-auditor audit https://example.com${NC}"
echo -e "    Audit a website for AI search visibility"
echo ""
echo -e "  ${YELLOW}/aso-optimizer analyze \"My App Name\"${NC}"
echo -e "    Analyze app store listing quality"
echo ""
echo -e "  ${YELLOW}/subscription-metrics calculate${NC}"
echo -e "    Calculate SaaS metrics (MRR, ARR, CAC, LTV)"
echo ""
echo -e "  ${YELLOW}/landing-page-cro audit https://example.com${NC}"
echo -e "    Audit landing page for conversion optimization"
echo ""
echo -e "  ${YELLOW}/competitor-intel analyze https://competitor.com${NC}"
echo -e "    Analyze competitor positioning and strategy"
echo ""
echo "---------------------------------------------------"
echo ""
echo -e "  ${BLUE}GitHub:${NC} https://github.com/ekinciio/saas-growth-marketing-skills"
echo -e "  ${BLUE}Issues:${NC} https://github.com/ekinciio/saas-growth-marketing-skills/issues"
echo ""
