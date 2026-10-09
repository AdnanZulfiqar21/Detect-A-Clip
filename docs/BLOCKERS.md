# BLOCKERS — Detect A Clip

Genuine external blockers only. Each row names the smallest input that unblocks it. A
blocker already recorded here is not re-requested in chat unless its state changes.

| ID | Blocks | What is missing | Smallest unblocking input | First recorded |
|---|---|---|---|---|
| B-01 | Android compile (P01-T01a), any Android device test (P01-T02…T08, CAP-A*, CAP-A04, UX-02, DATA-L00 Part B) | No JDK, Android SDK, adb or Gradle on this host; no Android device. Toolchain install is being attempted locally (see RESUME_STATE). Device remains missing. | At least one dedicated non-personal Android test device (ideally one Android 15 QPR1+ build and one older), USB debugging enabled, and a second configuration for P01-T08. | 2026-10-09 |
| B-02 | iOS compile, archive, any device test (P02-T02…T06, CAP-I01/I02/I03/I04/I05, DATA-L00 Part B iOS) | Windows host; no macOS, Xcode, iOS 27 SDK, provisioning profile or iPhone. | Mac with Xcode (27 for the ScreenCaptureKit path), Apple Developer provisioning, dedicated iPhone. | 2026-10-09 |
| B-03 | P00-T03 source-policy matrix, every P07 cell | Current regional terms for TikTok, Instagram, Facebook, YouTube, X (text effective on/after 9 Oct 2026), Snapchat are not retrieved or classified by counsel. | Owner/counsel supply classified policy text per source and region. | 2026-10-09 |
| B-04 | P00-T04 roles/entity, D01–D11, PRIV-01, any beta (D04) | Entity, country, audience, named leads, independent reviewers, cash/time caps, owner decisions. | Owner fills the D01–D11 rows in `docs/DECISIONS.md` and names roles. | 2026-10-09 |
| B-05 | G03-L1, P03-T02/T05/T06/T07, all of P08 | No licence, rights grant or chain-of-title evidence for any real work. | Rights counsel engagement and at least one executed grant stating permitted acts, territories, offline conditions and D07 method. | 2026-10-09 |
| B-06 | G04 RELEASE, F05 release counts | Requires ≥1,000 clean / ≥1,000 edited / ≥1,000 absent queries over ≥200/≥200/≥300 works from rights-approved material and an independent evaluator. | B-05 plus a named independent ML QA. | 2026-10-09 |
| B-07 | OPS-01 energy, P04-T08 device budgets | Needs physical devices with supported energy counters or calibrated external measurement. | B-01/B-02 devices plus instrumentation. | 2026-10-09 |
| B-08 | P10 store submission, REL-01/REL-02 | Developer accounts, store review, declarations. | Owner decision to submit; accounts; approvals are external outcomes. | 2026-10-09 |
| B-09 | Android SDK platform/build-tools install, therefore any Android compile (P01-T01a) | Installing `platforms;android-37.0`, `build-tools;37.0.0` and `platform-tools` requires accepting the Android SDK License Agreement (and sdkmanager's other listed licences). Accepting terms on the owner's behalf needs the owner's explicit confirmation in chat. An acceptance that ran by mistake on 2026-10-09 was stopped and its `licenses/` files deleted before any package installed. | Owner confirms in chat that they accept the Android SDK License Agreement for this machine, or installs the SDK packages themselves (Android Studio or `sdkmanager --licenses`). | 2026-10-09 |

Items in P11 are DEFERRED by the roadmap, not blocked, and are not listed here.
