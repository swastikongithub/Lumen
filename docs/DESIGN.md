# Lumen — Design guide

The approved UI for Lumen. Build the SvelteKit frontend (SPEC §12) to match this file and the mockups in `design/mockups/`.

Canvas the mockups came from (needs Swastik's claude.ai login): <https://claude.ai/artifact/5unrEP7Txd7LH1Zo7JcaCL>

---

## 1. How to read the mockup files

The mockups are `.dc.html` files from a design-canvas tool. They are **reference only**; don't ship or import them. Read them like this:

| In the mockup | Means |
|---|---|
| `<x-dc>`, `<helmet>`, `<script src="./support.js">`, `<script type="text/x-dc">` | Canvas runtime wrappers. Ignore them. |
| `{{accent}}` | `--accent` = `#0F766E` |
| `{{soft}}` | `--accent-soft` = accent at 12% opacity (`#0F766E1F`) |
| `<sc-if value="{{x}}">…</sc-if>` | `{#if x}…{/if}` in Svelte |
| `<sc-for list="{{items}}" as="item">…</sc-for>` | `{#each items as item}…{/each}` |
| `onClick="{{fn}}"` | `onclick={fn}` |
| `renderVals()` in the script block | Shows the state logic, e.g. the category menu |
| Inline `style="…"` | Source of truth for spacing, sizes and radii |
| Text in `[brackets]`, like `[X]%` | Placeholder. Real text always comes from the API, never hardcoded. |

| File | Screen |
|---|---|
| `Main.dc.html` | Mobile chat: cited answer, streaming follow-up, ☰ category menu, filter pill |
| `MobileSources.dc.html` | Mobile sources bottom sheet with highlighted excerpts |
| `Abstain.dc.html` | Mobile "not found" answer, thumbs-down reason chips, rate-limit banner |
| `Desktop.dc.html` | Desktop chat with category chips and sources side panel |

---

## 2. Tokens

Paste into `frontend/src/app.css`:

```css
:root {
  /* surfaces */
  --bg: #F6F7F9;
  --surface: #FFFFFF;
  --surface-muted: #F1F3F5;
  --info-bg: #EEF1F4;

  /* lines */
  --border: #E3E6EA;
  --border-strong: #C9CFD6;
  --divider: #EDEFF2;
  --dashed: #AEB6BF;

  /* text */
  --ink: #101418;          /* primary text, user bubble background */
  --ink-2: #2A3139;        /* excerpt text */
  --text-muted: #3D4650;   /* secondary text */
  --text-subtle: #5B6470;  /* meta text, icons */

  /* brand */
  --accent: #0F766E;
  --accent-hover: #0B5A54;
  --accent-soft: #0F766E1F;
  --highlight: #FCD34D;    /* logo mark highlight line */

  /* states */
  --danger: #B42318;
  --danger-soft: #FDECEA;
  --warning-bg: #FFF4E0;
  --warning-text: #7A4100;
  --scrim: rgba(16, 20, 24, 0.35);
  --scrim-strong: rgba(16, 20, 24, 0.5);

  /* type */
  --font-brand: 'Bricolage Grotesque', system-ui, sans-serif;
  --font-body: 'Inter', system-ui, sans-serif;

  /* radii */
  --r-xs: 6px;    /* inline citation chip */
  --r-sm: 8px;    /* logo tile, number badges */
  --r-md: 10px;   /* menu items, excerpt boxes */
  --r-lg: 12px;   /* icon buttons, banners */
  --r-xl: 14px;   /* source cards */
  --r-2xl: 16px;  /* answer cards, category menu panel */
  --r-pill: 999px;

  --shadow-menu: 0 16px 40px rgba(16, 20, 24, 0.18);
}
```

Fonts (add to `src/app.html` `<head>`):

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600..800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
```

### Typography
| Use | Font | Size / line-height | Weight | Notes |
|---|---|---|---|---|
| Wordmark "lumen" | Bricolage Grotesque | 23px mobile, 25px desktop, line-height 1 | 700 | Always lowercase, letter-spacing −0.035em |
| Headings ("Sources for this answer") | Bricolage Grotesque | 19–21px / 26px | 700 | letter-spacing −0.02em |
| Answer text | Inter | 15/22 mobile, 16/26 desktop | 400, numbers in 600 | |
| Bubbles, inputs | Inter | 15/21 | 400 | |
| Source titles | Inter | 14–15/19–20 | 500–600 | |
| Meta, hints | Inter | 12–13/16–18 | 400 | `--text-subtle` |
| Menu section label | Inter | 12/16 | 600 | uppercase, letter-spacing 0.04em |

### Spacing and sizing
- 4 px grid. Page padding 16 px on mobile, 24 px on desktop (content max-width 1240 px).
- Gap between messages: 14 px mobile, 20 px desktop.
- **Every tap target ≥ 44 × 44 px** (menu button, chips, thumbs, source rows, close buttons). The inline citation chips inside answer text are the only exception.
- Header height 56 px on mobile.
- User bubble: `--ink` background, white text, radius `18px 18px 4px 18px`, max-width 280 px on mobile and 520 px on desktop.
- Input: 48 px tall, pill radius, `--bg` fill, `--border-strong` border; send button is a 48 px accent circle.

---

## 3. Brand

**Mark** (`design/brand/lumen-mark.svg`): a rounded tile shaped like a document whose middle line is lit up in amber. It stands for the highlighted cited sentence. Use it as the favicon too (copy to `frontend/static/favicon.svg`).

```html
<svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
  <rect width="28" height="28" rx="8" fill="var(--accent)"/>
  <rect x="7" y="7.5" width="14" height="2.5" rx="1.25" fill="#FFFFFF" fill-opacity="0.6"/>
  <rect x="5.5" y="12.25" width="17" height="3.5" rx="1.75" fill="var(--highlight)"/>
  <rect x="7" y="18" width="9" height="2.5" rx="1.25" fill="#FFFFFF" fill-opacity="0.6"/>
</svg>
```

**Mini mark** (16 px, next to "Lumen" above each answer): the same tile with only the amber line (`design/brand/lumen-mark-mini.svg`).

**Logo** = mark + 8 px gap + wordmark "lumen" (live text, not an image). Size the mark at 28 px on mobile and 30 px on desktop.

---

## 4. Components and states

| Component | Notes and states |
|---|---|
| `Logo` | Mark + wordmark. Prop: `size` (`sm` for mobile, `md` for desktop). |
| `CategoryMenu` (mobile) | 44 px ☰ button left of the logo; the icon swaps to ✕ while open; `aria-expanded` + `aria-controls`. Panel: 272 px wide, 8 px from the left edge, 6 px below the header, `--shadow-menu`, radius 16. Section label "ANSWER FROM". Options: All, Academics, Exams, Hostel, Fees, Placements, each a 52 px row with label + one-line hint, selected row has `--accent-soft` background, weight 600 and an accent tick. Picking an option or tapping the scrim closes it. Below the categories, after a divider, a second section "LUMEN" holds 52 px link rows: Saved answers · Indexed documents · Privacy & data. |
| `CategoryChips` (desktop) | Row of 40 px pills; selected = accent fill, white text. |
| `ActiveFilterPill` | Only when the category isn't "All": "Answering from" + accent-soft pill with the name and ✕. Tap clears the filter. |
| `Disclaimer` | One line on mobile: "Unofficial · always confirm with the linked document" on `--info-bg`. Desktop: pill in the header. |
| `UserBubble` | See tokens above. |
| `AssistantMessage` | Label row (mini mark, "Lumen", meta like "· from 2 documents"), white answer card, inline citation chips `[1]` (accent-soft background, accent text, 12px/600, radius 6), divider, source rows (number badge, title, "Section · p.N · Category", chevron). **Streaming:** text grows with a 2 px accent caret; label meta reads "· found N matching passages". |
| `FeedbackButtons` | 44 px thumbs up/down, then copy on the web, or **Save** (bookmark) + **Share** in the Android app. Up selected = accent-soft fill + accent icon. Down selected = `--danger-soft` + `--danger` icon, then opens "What went wrong?" with reason chips: Wrong · Outdated · Didn't find it · Unclear · **Offensive or harmful**. The last chip is required by Google Play's AI-Generated Content policy and must always be shown. The selected chip is filled `--ink`. Save selected = filled bookmark in `--accent`. |
| `SourcesSheet` (mobile) | Bottom sheet (top radius 20) over `--scrim-strong`, grab handle, title + "N documents · tap to open the PDF at that page", ✕ close. Cards: number badge, title, meta, excerpt box (`--bg`) with the cited sentence highlighted in `--accent-soft`, "Open PDF at page N ↗". The card for the tapped citation has a 1.5 px accent border. Footer: "Something outdated? Report it". |
| `SourcesPanel` (desktop) | Right column, 340 px base width. Heading "Sources" + "N passages"; the first source is expanded like the sheet card, the rest are compact 56 px rows; then a `<details>` "How this answer was found" listing the pipeline steps in plain words. |
| `AbstainCard` | 1.5 px dashed `--dashed` border, search icon + "I couldn't find this in the indexed documents.", one explanatory line, closest matches as 44 px rows, accent link "Suggest a document to add". |
| `BusyBanner` | Above the input: `--warning-bg` / `--warning-text`, clock icon, "Lumen is busy right now. Try again in 0:24" (live countdown from `retry_after`); input and send are disabled and grey while it shows. |

### Category hints (menu copy)
| Category | Hint |
|---|---|
| All | Every indexed document |
| Academics | Attendance, credits, grading |
| Exams | Eligibility, schedules, re-appear |
| Hostel | Rules, timings, allotment |
| Fees | Payments, refunds, fines |
| Placements | Eligibility, drives, policy |

---

## 5. Responsive behaviour
- **< 768 px:** mobile layout. ☰ category menu, sources open as a bottom sheet when a citation or source row is tapped.
- **768–1023 px:** single column like mobile, but category chips replace the ☰ menu and the sheet becomes a centred dialog.
- **≥ 1024 px:** desktop layout. Chat column `flex: 999 1 560px`, sources panel `flex: 1 1 340px`, both in a wrapping flex row.
- Test at 360 px, 390 px, 768 px and 1280 px.

## 6. Accessibility checklist
- Real `<button>`, `<a href>`, `<input>` + `<label>`; no click handlers on divs.
- `aria-label` on every icon-only button; decorative SVGs `aria-hidden="true"`.
- Text contrast ≥ 4.5:1 (all token pairs above pass on their intended backgrounds).
- Visible focus ring: 2 px `--accent` outline with a 2 px offset.
- Streaming text in an `aria-live="polite"` region; the busy banner uses `role="status"`.
- The sources sheet is a dialog: focus trap, Esc closes it, focus returns to the citation that opened it.

---

## 7. Android app (Capacitor)

The app uses the mobile layout above unchanged. These are the app-only screens and native details. They aren't in the mockups yet, so build them from the tokens and components here.

### App icon, splash, system bars
| Item | Spec |
|---|---|
| Adaptive icon | Background layer: solid `--accent` (`#0F766E`). Foreground layer: the mark's three lines (two white at 60% opacity, amber highlight in the middle), centred inside the adaptive-icon safe zone. Monochrome layer (themed icons): the three lines in one colour. |
| Play Store icon | 512 × 512 PNG of the full mark (rounded tile on accent), from `design/brand/lumen-mark.svg`. |
| Source files | Put sources in `frontend/resources/` in the file names and sizes `@capacitor/assets` expects (check its README), then generate all densities with it. |
| Splash | Background `--bg` (`#F6F7F9`), mark centred, no text. Hide it as soon as the first screen has rendered. |
| Status bar | `#FFFFFF` with dark icons (matches the header). |
| Navigation bar | `#FFFFFF` with dark icons. |
| Edge-to-edge | The header gets `padding-top: env(safe-area-inset-top)`, the input bar and bottom sheet get `padding-bottom: env(safe-area-inset-bottom)`. Check on a gesture-navigation phone. |

### Back button (in this order)
1. Sources sheet open → close it.
2. ☰ menu open → close it.
3. Not on the chat screen → go back one route.
4. On the chat screen → minimise the app (don't exit with an error or a confirm dialog).

### App-only screens and states
| Screen / state | Spec |
|---|---|
| **Saved answers** (`/saved`) | Header: back arrow (44 px) + "Saved answers" (Bricolage 700, 21px). List of white cards (radius 14): question (Inter 15/600), first two lines of the answer (14px, `--text-muted`), meta "2 sources · Saved 25 Nov" (12px, `--text-subtle`), and a 44 px "Remove" icon button. Tapping a card opens the full answer read-only with its source rows. If the saved `corpus_version` differs from the current one, show a warning chip "Policy may have changed since you saved this" (`--warning-bg` / `--warning-text`). **Empty state:** bookmark icon + "Save answers to read them offline." |
| **Offline banner** | Under the disclaimer: `--info-bg`, wifi-off icon, "You're offline. Saved answers still work." plus a "Saved answers" link. Input and send disabled and grey while offline. |
| **Update required** | Full screen on `--bg`: mark at 56 px, "Update Lumen to keep using it" (Bricolage 700, 24px), one line "This version no longer works with the server.", then a 48 px full-width accent button "Open Play Store". No way to dismiss it. |
| **Privacy & data** | Short plain-language summary of what's collected (matches `/privacy`), a link to the full policy, and "Clear my data": a danger outline button (`--danger` text and border, 48 px). It asks for confirmation ("This deletes your chat history on our server and your saved answers on this phone."), then shows a success toast. |
| **Share** | The native share sheet with the answer text, then "Sources:" with numbered titles and links, then "via Lumen (unofficial)". |
| **Haptics** | Light impact on send, on a thumbs tap and on save. Nothing else. |

### Store screenshots to capture (phone, portrait)
1. Chat with a cited answer (Main mockup state)
2. Sources sheet with a highlighted passage
3. "I couldn't find this" answer
4. Saved answers list
5. Category menu open

Use real answers from the live app (never placeholders) and keep the disclaimer visible.
