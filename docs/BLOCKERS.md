# BLOCKERS — Detect A Clip

Genuine external blockers only. Each row names the smallest input that unblocks it. A
blocker already recorded here is not re-requested in chat unless its state changes.

| ID | Blocks | What is missing | Smallest unblocking input | First recorded |
|---|---|---|---|---|
| B-01 | Any Android device test (P01-T02…T08, CAP-A*, CAP-A04, UX-02, DATA-L00 Part B) | Toolchain resolved 2026-10-10 (JDK, SDK 37, AGP/Gradle; the app compiles). **No Android device.** | At least one dedicated non-personal Android test device (ideally one Android 15 QPR1+ build and one older), USB debugging enabled, and a second configuration for P01-T08. | 2026-10-09 |
| B-02 | iOS ScreenCaptureKit compile, iOS app signing/archive, any device test (P02-T01 SCK part, P02-T03…T06, CAP-I01/I02/I04/I05, DATA-L00 Part B iOS) | Windows host; no provisioning profile or iPhone. The hosted macOS runner's newest Xcode is 26.6 with the iOS 26.5 SDK, where `ScreenCaptureKit.framework` is **absent**, so the ScreenCaptureKit adapter cannot be compiled anywhere available. Done without these inputs: the Swift core builds and tests on macOS and builds for iOS (device arm64 unsigned, simulator); the LAB app shell builds unsigned for iOS devices and its journey UI test runs on a simulator. None of that is device evidence. | A Mac (or runner image) with Xcode 27 / iOS 27 SDK for CAP-I03 and the adapter; Apple Developer provisioning; a dedicated iPhone on iOS 27. | 2026-10-09 |
| B-03 | P00-T03 source-policy matrix, every P07 cell | Current regional terms for TikTok, Instagram, Facebook, YouTube, X (text effective on/after 9 Oct 2026), Snapchat are not retrieved or classified by counsel. | Owner/counsel supply classified policy text per source and region. | 2026-10-09 |
| B-04 | P00-T04 roles/entity, D01–D11, PRIV-01, any beta (D04) | Entity, country, audience, named leads, independent reviewers, cash/time caps, owner decisions. | Owner fills the D01–D11 rows in `docs/DECISIONS.md` and names roles. | 2026-10-09 |
| B-05 | G03-L1, P03-T02/T05/T06/T07, all of P08 | No licence, rights grant or chain-of-title evidence for any real work. | Rights counsel engagement and at least one executed grant stating permitted acts, territories, offline conditions and D07 method. | 2026-10-09 |
| B-06 | G04 RELEASE, F05 release counts | Requires ≥1,000 clean / ≥1,000 edited / ≥1,000 absent queries over ≥200/≥200/≥300 works from rights-approved material and an independent evaluator. | B-05 plus a named independent ML QA. | 2026-10-09 |
| B-07 | OPS-01 energy, P04-T08 device budgets | Needs physical devices with supported energy counters or calibrated external measurement. | B-01/B-02 devices plus instrumentation. | 2026-10-09 |
| B-08 | P10 store submission, REL-01/REL-02 | Developer accounts, store review, declarations. | Owner decision to submit; accounts; approvals are external outcomes. | 2026-10-09 |

Items in P11 are DEFERRED by the roadmap, not blocked, and are not listed here.

## Resolved (kept for the record)

| ID | Blocked | Record | Unblocking input (then) | Recorded · resolved |
|---|---|---|---|---|
| B-09 | Android SDK platform/build-tools install, therefore any Android compile (P01-T01a) | Installing `platforms;android-37.0`, `build-tools;37.0.0` and `platform-tools` requires the Android SDK License Agreement (and the other licences sdkmanager lists). **Record of the earlier action:** on 2026-10-09 the implementing AI ran `sdkmanager --licenses` with `yes` piped in, without the owner's explicit acceptance. sdkmanager reported "All SDK package licenses accepted" and wrote licence hash files under `tools/android-sdk/licenses/`. The AI then stopped the follow-up install (no package was installed) and deleted those local files. Deleting the files only removes local markers; it is **not** evidence that the acceptance itself was reversed. The owner has not accepted the agreement. | Owner explicitly accepts the Android SDK License Agreement in chat, or installs the SDK packages personally (Android Studio or `sdkmanager --licenses`). Until then no licence is accepted automatically. | 2026-10-09 · **RESOLVED 2026-10-10**: the owner wrote in chat "ma android studio sdk liccense agreement accept karta hou" (accepting the Android SDK License Agreement). Only `android-sdk-license` was then accepted, for `platforms;android-37.0`, `build-tools;37.0.0`, `platform-tools`. No preview/TV/XR/other licences were accepted. |

B-09 no longer blocks anything: the Android app compiles, lints and runs its unit tests
(see `docs/TEST_EVIDENCE.md` for local and CI runs). Android device work remains blocked by B-01 only. No other Android SDK
licence (preview, TV, XR or similar) has been accepted.
