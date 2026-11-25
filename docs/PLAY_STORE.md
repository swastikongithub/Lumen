# Lumen — Google Play release guide

Everything needed to get the Android app (SPEC §12.1) from a signed `.aab` to production on Google Play.
Requirements were checked on **25 Nov 2026**. Google changes them often, so re-check each linked page before you submit.

---

## 1. Requirements that shape the plan

| Requirement | What it means for Lumen | Source |
|---|---|---|
| **Closed test: 12 testers for 14 days** | Personal developer accounts created after 13 Nov 2023 must run a closed test with at least 12 testers opted in for 14 continuous days before applying for production. Internal testing does **not** count. | [Play Console Help](https://support.google.com/googleplay/android-developer/answer/14151465) |
| **Target API level 36** | Since 31 Aug 2026, new apps and app updates must target Android 16 (API 36). | [Android Developers](https://developer.android.com/google/play/requirements/target-sdk) |
| **Not just a webview** | Apps that only wrap a website risk removal as webview spam. Lumen's app-only features (offline saved answers, native share, back button, offline mode, update check) are the answer to this; mention them in the listing. | [Android Developers Blog](https://android-developers.googleblog.com/2020/10/developer-tips-and-guides-common-policy.html) |
| **In-app reporting of AI content** | Apps that generate content with AI must let users report or flag offensive content without leaving the app. Lumen: thumbs-down → "Offensive or harmful". | [Play policy](https://support.google.com/googleplay/android-developer/answer/13985936) |
| **Privacy policy URL** | Must be public and match the Data safety answers: the web app's `/privacy` page. | Play Console → App content |
| **Android App Bundle + Play App Signing** | Upload `.aab` files signed with your upload key; Google holds the app signing key. | Play Console |
| **No impersonation** | No LPU logo, no "LPU" in the app title or icon; "Unofficial" stated clearly in the description. | Play impersonation policy |

---

## 2. Timeline

| When | Step |
|---|---|
| During Phase 4 | Create the Play Console **personal** account (one-time registration fee, US$25 at the time of writing) and finish identity verification, which can take days. |
| Before Phase 8 | Recruit **15–20 testers** (buffer above 12) from your class. Collect the Gmail addresses they use for the Play Store. |
| Phase 8, day 0 | Create the app in Play Console, fill in every **App content** item (§4), upload the first `.aab` to **Internal testing** and install it yourself. |
| Day 1 | Promote the same build to **Closed testing**, add the tester list, share the opt-in link. **The 14-day clock starts when 12 testers are opted in.** |
| Days 1–14 | Testers keep the app installed and use it a few times a week. Fix real bugs, but avoid shipping lots of builds. Log the feedback you get (you'll need it in §6). |
| Day 15+ | Apply for production access (Dashboard), answering the questions with your notes. |
| After approval | Publish to production (consider a staged rollout, e.g. 20% first). |

---

## 3. Pre-submission checklist

**Build**
- [ ] `targetSdkVersion` 36 in `android/variables.gradle`; min SDK = Capacitor default
- [ ] `versionCode` incremented, `versionName` set (e.g. `1.0.0`)
- [ ] Release `.aab` built and signed with the upload key; keystore + passwords stored **outside the repo** with a backup
- [ ] `capacitor.config.json` has no `server.url`; `CapacitorHttp` disabled
- [ ] `VITE_API_URL` points at production; `/api/v1/meta` returns `min_app_version` ≤ this version
- [ ] Only `INTERNET` and network-state permissions in `AndroidManifest.xml`

**Behaviour (test on one Android 16 phone and one older phone)**
- [ ] Streaming answers work over mobile data
- [ ] Back button order matches DESIGN.md §7
- [ ] Edge-to-edge: nothing hidden under the status or navigation bar
- [ ] Airplane mode: offline banner shows, saved answers open
- [ ] Share sheet works; source links open in a Custom Tab
- [ ] Thumbs-down → "Offensive or harmful" sends a report
- [ ] Privacy & data → Clear my data deletes server data and saved answers
- [ ] Update-required screen appears when `min_app_version` is raised (test against staging)
- [ ] No crashes in Play Console's **pre-launch report** for the internal test build

---

## 4. Play Console → App content (draft answers, review each one)

| Item | Draft answer |
|---|---|
| Privacy policy | `https://<your-pages-domain>/privacy` |
| Ads | No, the app contains no ads |
| App access | All functionality is available without special access (no login) |
| Content rating | Fill in the questionnaire honestly: Education category, users type questions and get AI-generated text; no user-to-user communication, no violence or mature content. Don't guess the rating; let the questionnaire assign it. |
| Target audience | Select only adult/older-teen age groups (e.g. 18+, optionally 16–17). **Don't select any under-13 group**, or the Families policy applies. |
| Data safety | See §5 |
| Government app | No |
| Financial features | None |
| Health | None |

---

## 5. Data safety form (draft; match it to the live app before submitting)

| Question | Draft answer |
|---|---|
| Does the app collect or share user data? | Yes, it collects data |
| Data types collected | **App activity → Other user-generated content** (questions typed, feedback comments). **Device or other IDs** (a random anonymous ID created by the app). |
| Purposes | App functionality (answering, history), Analytics (improving answer quality), Fraud prevention / security (rate limiting) |
| Is data shared? | Check Play's definition in the form: data passed to service providers that process it on your behalf (LLM API, hosting) generally isn't "sharing". Read the form's help text and answer accordingly. |
| Required or optional? | Questions are required to use the app; feedback is optional |
| Encrypted in transit? | Yes (HTTPS only) |
| Can users request deletion? | Yes: Privacy & data → Clear my data |
| Not collected | Name, email, phone, location, contacts, photos, files, payment info |

The privacy policy must say the same things: what's collected, why, 30-day retention, the salted IP hash used only for rate limiting, and how to delete.

---

## 6. Production-access application notes (fill in during the closed test)

Play asks about your closed test before granting production access. Keep notes as you go:
- How you recruited testers (e.g. classmates from your section and hostel)
- How many stayed opted in for the full 14 days
- What feedback you got (count thumbs-down reasons, bugs reported)
- What you changed because of it (list builds and fixes)
- Why it's ready: crash-free pre-launch report, checklist in §3 complete

---

## 7. Store listing drafts

**App name** (max 30 characters): `Lumen: Cited Campus Answers` (27)

**Short description** (max 80 characters):
`Ask about exams, attendance & hostel rules. Every answer cites its source.` (74)

**Full description** (max 4,000 characters):

```
Lumen answers questions about university rules using only official public documents, and shows exactly where each answer comes from.

Unofficial student project. Lumen is not affiliated with or endorsed by Lovely Professional University. Always confirm important details with the official document linked in each answer.

WHAT YOU CAN ASK
• Attendance and exam eligibility
• Exam schedules, re-appear rules and grading
• Hostel rules and timings
• Fees, payments and refunds
• Placement policy

WHY IT'S DIFFERENT
• Every sentence is cited: tap a citation to see the exact passage and page
• If the documents don't cover your question, Lumen says so instead of guessing
• Filter answers by category
• Save answers and read them offline
• Share an answer together with its sources

PRIVACY
No account needed. Lumen keeps your questions and feedback for 30 days to improve answers, linked to a random anonymous ID, not your name. Delete your data anytime from Privacy & data.

Found a wrong, outdated or offensive answer? Tap thumbs down and tell us why.
```

**Category:** Education · **Contact email:** `[your email]` (required, shown publicly) · **Website:** `[web app URL]`

**Graphics** (check sizes in Play Console when uploading):
- App icon: 512 × 512 PNG, from `design/brand/lumen-mark.svg`
- Feature graphic: 1024 × 500, the mark + "lumen" wordmark on `#F6F7F9`, tagline "Cited answers to campus rules". No LPU logo.
- Phone screenshots: at least 2, ideally the 5 listed in DESIGN.md §7, taken from the real app

Save final versions in `store/` (`store/listing.md`, `store/icon-512.png`, `store/feature-graphic.png`, `store/screenshots/`).
