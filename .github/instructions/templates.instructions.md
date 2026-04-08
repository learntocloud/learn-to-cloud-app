---
applyTo: "**/*.html"
---

# Template & Frontend Conventions

These supplement the project-wide rules in `copilot-instructions.md`.

## Template Hierarchy
- Content pages extend `layouts/content_page.html`.
- Partials receive context via `{% with %}` blocks.
- Out-of-band HTMX updates (`hx-swap-oob="true"`) used for progress bars after step completion.

## Tailwind CSS v4
- Config lives in `api/static/css/input.css` — there is no `tailwind.config.js`.
- Dark mode: class-based, toggled by Alpine.js + localStorage.
- Renamed utilities (v4): `shadow-xs` (was `shadow-sm`), `rounded-xs` (was `rounded-sm`), `outline-hidden` (was `outline-none`).

## HTMX Patterns
- HTMX routes return `HTMLResponse` fragments, never full pages.
- Use `hx-target` and `hx-swap` to replace specific DOM elements.
- Prefer server-side state over client-side — the server is the source of truth.

## Alpine.js
- Used for client-side interactivity (dark mode toggle, dropdowns, modals).
- Keep logic minimal — heavy logic belongs on the server.
