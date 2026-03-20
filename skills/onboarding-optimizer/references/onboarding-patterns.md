# Onboarding Patterns Library

Five proven onboarding patterns for SaaS products, with guidance on when to use each, when to avoid, real-world examples, and metrics to track.

---

## 1. Product Tour

A guided walkthrough that highlights key features and UI elements using tooltips, spotlights, or coach marks. Typically triggered on first login and walks users through the main interface.

### Best For
- Products with a visual interface where users need to learn where things are
- Low-to-medium complexity products with a clear primary workflow
- Products where the UI is the main value driver (design tools, dashboards, editors)
- B2C or prosumer SaaS with a broad user base
- Products where users already understand the problem but need to learn the tool

### Avoid When
- The product requires significant data import or setup before it becomes useful
- The interface is highly customizable and the tour would not match every user's layout
- Users have very different roles and workflows (a single tour will not fit all)
- The product is API-first or developer-focused with minimal UI

### Examples
- Canva: highlights key tools in the editor on first use
- Figma: brief tour of the design canvas, layers panel, and collaboration features
- Notion: walkthrough of page creation, blocks, and navigation

### Implementation Tips
- Keep tours under 5 steps; longer tours see steep drop-off after step 3
- Allow users to skip and replay the tour from settings
- Use progressive tooltips that appear contextually rather than all at once
- Highlight the single most important action first
- Do not block the UI - let users interact during the tour

### Metrics to Track
- Tour completion rate (target: >60%)
- Tour skip rate (if >40%, the tour is too long or poorly timed)
- Feature adoption rate for toured features vs. non-toured features
- Time to first key action after tour completion
- 7-day retention for users who completed tour vs. skipped

---

## 2. Progressive Disclosure

Reveals features and complexity gradually as users become more experienced. Starts with a simplified view and unlocks advanced capabilities over time based on usage signals.

### Best For
- Complex products with many features that would overwhelm new users
- Products serving both beginners and power users
- Platforms where users grow into advanced functionality over weeks or months
- Enterprise tools with deep feature sets
- Products where different features matter at different lifecycle stages

### Avoid When
- The product is simple enough that all features should be visible from the start
- Users are technical experts who expect full access immediately
- The core value requires access to advanced features on day one
- Hiding features would confuse users who saw them in marketing materials

### Examples
- Slack: starts with basic messaging, gradually introduces channels, apps, workflows, and admin features
- HubSpot: surfaces basic CRM first, reveals marketing automation and reporting as usage grows
- GitHub: basic repo and code features first, then actions, packages, and security features emerge with use

### Implementation Tips
- Define 3-4 maturity levels (beginner, intermediate, advanced, power user)
- Tie feature unlocks to meaningful usage milestones, not just time
- Always give an option to "show all features" for power users who want full control
- Use subtle UI cues (badges, gentle prompts) to introduce new capabilities
- Track which features users discover organically vs. which need nudging

### Metrics to Track
- Feature discovery rate by maturity level
- Time between maturity level transitions
- Activation rate at each level (what percentage of users reach level 2, 3, etc.)
- Drop-off rate at each transition point
- Power user conversion rate (percentage reaching the highest maturity level)

---

## 3. Checklist/Wizard

A structured, step-by-step setup process with a visible checklist or wizard interface. Users complete required setup tasks in a defined sequence with clear progress tracking.

### Best For
- Products that require meaningful configuration before delivering value
- Products with a clear sequence of setup tasks (connect accounts, import data, invite team)
- B2B products where the admin needs to set up the workspace for their team
- Products where skipping setup would result in a broken or empty experience
- Tools that integrate with external systems and need credentials or permissions

### Avoid When
- The product can deliver value immediately without setup
- There are fewer than 3 setup steps (a checklist feels heavy for simple flows)
- Users are exploring the product casually and commitment to a wizard feels premature
- The setup requires information users may not have handy (API keys, billing details)

### Examples
- Stripe: step-by-step business verification, bank account connection, and API setup
- Asana: create first project, invite team, set up first task, choose a view
- Calendly: set availability, connect calendar, create first event type, share link

### Implementation Tips
- Show progress clearly (3 of 5 steps complete, progress bar)
- Allow saving progress and returning later
- Mark truly required steps vs. recommended steps
- Celebrate completion of each step with micro-interactions
- Pre-fill data where possible (from signup info, OAuth, or defaults)
- Provide a "skip for now" option with a persistent reminder to complete setup

### Metrics to Track
- Wizard completion rate (target: >70%)
- Drop-off rate by step (identify the step that loses the most users)
- Time to complete full wizard
- Activation rate for users who complete wizard vs. those who skip
- Return rate for users who abandoned the wizard mid-way

---

## 4. Template Gallery

Presents users with pre-built templates, examples, or starter content they can use immediately. Reduces the blank-canvas problem by giving users a starting point.

### Best For
- Creative tools where starting from scratch is intimidating (design, writing, websites)
- Products where the output varies significantly by use case
- Tools where templates demonstrate the range of what is possible
- Products targeting non-technical users who benefit from examples
- Platforms where showing the finished output inspires adoption

### Avoid When
- The product has a single fixed workflow (templates would all look the same)
- Templates would not accurately represent the user's real data or use case
- Users are developers or technical users who prefer building from scratch
- The product is data-driven and templates with fake data would be misleading

### Examples
- Webflow: website templates organized by industry and type
- Airtable: base templates for project management, CRM, content calendar, and more
- Mailchimp: email templates by campaign type (welcome, promotion, newsletter)

### Implementation Tips
- Organize templates by use case or industry, not by feature
- Show previews that look realistic and professional
- Include 5-10 high-quality templates rather than 50 mediocre ones
- Make it easy to customize a template after selection
- Feature templates that showcase your most powerful and differentiating features
- Add a "start from scratch" option for users who prefer it
- Track which templates are most popular and promote them prominently

### Metrics to Track
- Template selection rate (percentage of new users who pick a template)
- Most popular templates (indicates what use cases resonate)
- Customization depth (how much users modify the template)
- Activation rate for template users vs. blank-start users
- Time to first meaningful output (template vs. no template)

---

## 5. Empty State Education

Uses empty states as teaching moments instead of showing blank screens. When a section has no data yet, the empty state explains what belongs there, why it matters, and how to populate it.

### Best For
- Data-dependent products that start empty (analytics, CRM, project management)
- Products where the value emerges after data is added
- Products with multiple sections or modules that get populated over time
- Tools where users need to understand what each section does before adding data

### Avoid When
- The product can pre-populate with sample data instead
- Empty states would appear only briefly before real data flows in
- The product has a wizard that populates everything during setup
- Users are migrating from a competitor and will import data immediately

### Examples
- Mixpanel: empty dashboards explain what events to track and show example charts
- Linear: empty project views explain how to create issues and organize work
- Intercom: empty inbox shows what conversations will look like and how to set up the messenger

### Implementation Tips
- Every empty state should include: a clear explanation, a visual (illustration or example), and a single primary CTA
- Use conversational, encouraging language ("You are all set up - create your first project to get started")
- Show what the section will look like once populated (example screenshots or illustrations)
- Include links to help docs or video tutorials for complex sections
- Remove empty state education once the user has added their first item
- Do not use empty states as advertising for premium features

### Metrics to Track
- Empty state CTA click rate (target: >30%)
- Time from first seeing empty state to populating it
- Sections that remain empty after 7 days (indicates confusion or low value perception)
- Activation rate for users who interact with empty state CTAs vs. those who do not
- Help article click-through rate from empty states

---

## Pattern Selection Guide

| Product Type | Primary Pattern | Secondary Pattern |
|---|---|---|
| Visual/design tool | Product Tour | Template Gallery |
| Data/analytics platform | Empty State Education | Progressive Disclosure |
| Collaboration tool | Checklist/Wizard | Product Tour |
| Developer tool/API | Progressive Disclosure | Empty State Education |
| Business operations (CRM, ERP) | Checklist/Wizard | Progressive Disclosure |
| Content/creative tool | Template Gallery | Product Tour |
| Communication tool | Product Tour | Empty State Education |
| E-commerce platform | Checklist/Wizard | Template Gallery |

## Combining Patterns

Most successful onboarding flows combine two or three patterns:

- **Wizard + Product Tour:** Complete setup first, then tour the now-populated interface
- **Template Gallery + Product Tour:** Pick a template, then get a brief tour of how to customize it
- **Progressive Disclosure + Empty State Education:** Show a simplified view with educational empty states that guide feature discovery
- **Checklist + Empty State Education:** Use a checklist for required setup, empty states for optional sections

Avoid combining more than three patterns - it creates a disjointed experience. Choose one primary pattern and one or two supporting patterns.
