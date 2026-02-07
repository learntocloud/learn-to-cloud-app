---
applyTo: "api/templates/**/*.html"
description: "Jinja2 templates, HTMX interactions, Alpine.js reactivity, Tailwind CSS v4"
---

# HTMX / Jinja2 / Alpine.js Coding Standards

## Jinja2 Templates
- Templates live in `api/templates/` — `pages/` for full pages, `partials/` for fragments
- All pages extend `base.html`
- Use `{% include %}` for reusable partials
- Pass context via route handlers; avoid logic in templates

## HTMX
- Use `hx-get`, `hx-post`, etc. for server-driven interactions
- Return HTML fragments from HTMX routes, not full pages
- Use `hx-target` and `hx-swap` to control where responses are inserted
- HTMX routes live in `api/routes/htmx_routes.py`

## Alpine.js
- Use for client-side interactivity (toggles, dropdowns, modals)
- Keep Alpine state minimal — server is the source of truth
- Use `x-data`, `x-show`, `x-on` directives

## Tailwind CSS v4
- Order responsive prefixes consistently: `sm:`, `md:`, `lg:`, `xl:`
- Avoid conflicting utility classes on same element
- Dark mode: use `dark:` prefix classes

## Content Files
- Course content is stored as YAML in `content/phases/`
- Phase metadata: `content/phases/phaseN/_phase.yaml`
- Topic files: `content/phases/phaseN/topic-slug.yaml`

## Accessibility
- ARIA labels on icon-only buttons
- Form inputs must have associated labels
- Semantic HTML elements (`<nav>`, `<main>`, `<article>`)

---

## Feedback
If you encounter a pattern, convention, or edge case that should be added to these instructions, let me know so we can consider including it.
