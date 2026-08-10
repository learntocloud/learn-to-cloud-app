---
target: homepage
total_score: 20
max_score: 28
na_heuristics: 5,7,9
p0_count: 0
p1_count: 3
timestamp: 2026-08-10T20-36-19Z
slug: api-src-learn-to-cloud-templates-pages-home-html
---
Method: dual-agent (A: homepage-design-review · B: homepage-detector-review)

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|---|---:|---|
| 1 | Visibility of System Status | 3 | The primary CTA does not explain the next step or GitHub authentication. |
| 2 | Match System / Real World | 3 | The phase sequence is clear, but Phase 0 and cloud acronyms assume prior literacy. |
| 3 | User Control and Freedom | 3 | Community and FAQ disappear on mobile with no replacement navigation. |
| 4 | Consistency and Standards | 3 | “Get Started” and “Sign in with GitHub” describe the same destination differently. |
| 5 | Error Prevention | n/a | No input or destructive action exists on this surface. |
| 6 | Recognition Rather Than Recall | 3 | Card styling suggests the phase summaries are clickable when they are not. |
| 7 | Flexibility and Efficiency | n/a | Not meaningfully applicable to this persuasive landing page. |
| 8 | Aesthetic and Minimalist Design | 2 | Eight equally weighted cards flatten the narrative and dilute the CTA. |
| 9 | Error Recovery | n/a | No recoverable workflow or error state exists on this surface. |
| 10 | Help and Documentation | 3 | Help routes exist on desktop, but FAQ is unavailable from mobile navigation. |
| **Total** | | **20/28** | **Good baseline, weak product expression** |

## Design Specificity Verdict

**LLM assessment:** Category-interchangeable with product-specific content. The logo, phase names, and “prove your skills” language identify Learn to Cloud, but the centered logo, blue CTA, and uniform bordered-card grid could belong to almost any course platform. The interface does not embody progression, hands-on verification, cloud systems, or the transition from beginner to job-ready.

**Deterministic scan:** The CLI detector returned 0 findings for `api/src/learn_to_cloud/templates/pages/home.html`. This means no registered source-level anti-patterns were detected; it does not invalidate the structural, responsive, or experiential issues found in the design review. There were no false positives.

**Visual evidence:** Production was reachable, but no browser automation, mutable DOM evaluation, fresh-tab control, or console-reading interface was exposed. No reliable user-visible overlay is available.

## Overall Impression

The homepage is calm, legible, and credible, but it presents a syllabus rather than a transformation. The biggest opportunity is to turn the phase inventory into an authored learning journey that makes beginners feel capable and shows how skills are proven.

## What’s Working

1. The value proposition clearly communicates structure, practice, challenges, and verification.
2. Phase names and summaries make the curriculum breadth understandable without inflated marketing language.
3. The constrained width, responsive grid, semantic links, meaningful logo alt text, and light/dark support form a solid baseline.

## Priority Issues

### [P1] The homepage lacks an authored learning narrative

**Why it matters:** Visitors see inventory, not transformation, so the product feels replaceable and offers no emotional peak.

**Fix:** Recompose the hero and journey around a clear beginner-to-proven-practitioner arc. Show a concrete outcome, how verification works, and one unmistakable moment of learner progress.

**Suggested command:** `/impeccable bolder`

### [P1] Mobile navigation removes trust and help routes

**Why it matters:** Community and FAQ disappear below the `sm` breakpoint, leaving first-time mobile visitors without reassurance or support.

**Fix:** Add a compact mobile navigation pattern that preserves Community, FAQ, curriculum, theme, and authentication access with 44px touch targets.

**Suggested command:** `/impeccable adapt`

### [P1] Authentication intent is inconsistent

**Why it matters:** “Get Started” silently leads to GitHub authentication while the secondary sign-in action names GitHub, creating uncertainty at the highest-value conversion point.

**Fix:** Use one authentication vocabulary and disclose the GitHub step near the primary CTA without adding friction.

**Suggested command:** `/impeccable clarify`

### [P2] The journey grid is flat and behaviorally ambiguous

**Why it matters:** Eight identical, noninteractive cards exceed a comfortable chunk size, appear clickable, and provide no recommended starting point, duration, or progression model.

**Fix:** Group phases into a smaller number of meaningful chapters, establish a visible path, and either make phase items genuine destinations or remove card affordances.

**Suggested command:** `/impeccable layout`

### [P2] Accessibility details weaken the baseline

**Why it matters:** The page has no textual `h1`; low-emphasis phase numbers may miss contrast targets; several navbar controls appear smaller than recommended touch targets.

**Fix:** Add a meaningful visible heading, verify text contrast in both themes, and increase interactive hit areas.

**Suggested command:** `/impeccable audit`

## Persona Red Flags

**Jordan (First-Timer):** “Phase 0” is unexplained, cloud acronyms arrive immediately, and “Get Started” conceals the GitHub requirement. No prerequisite, time-commitment, or beginner reassurance answers whether this path is realistic.

**Casey (Distracted Mobile User):** Community and FAQ vanish, the eight-card sequence creates a long undifferentiated scroll, and small utility controls increase missed taps.

**Riley (Stress Tester):** If `phases` is empty, the entire journey disappears without an empty state. The “prove your skills” promise has no visible evidence, and the same login destination has two labels.

## Minor Observations

- The large hero logo repeats the brand already present in the navbar.
- Authenticated visitors see generic curriculum inventory instead of contextual progress.
- Uneven phase-description lengths can create inconsistent card density.
- “Program overview” in the footer duplicates the curriculum destination under another label.

## Questions to Consider

- Is the homepage selling a curriculum, a career transformation, or a system for proving competence?
- What should a nervous beginner feel certain about within five seconds?
- Why are phases presented as cards if visitors cannot enter them?
- What would make a learner think, “I can actually finish this”?
