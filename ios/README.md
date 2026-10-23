# Detect A Clip — iPhone lab build

Native Swift / SwiftUI lab app for the iOS research track (roadmap P02). It is a **no-frame
build** in the sense of P02-T02: screen capture of other apps is disabled until the iOS G00
gate, so choosing "Another app's screen" ends in `UNSUPPORTED_CAPTURE`. Everything else in
the F03 flow is real and runs on the phone:

- first-use Terms/Privacy with a stored `TermsReceipt` (version, text hash, locale, time);
- per-scan consent sheet → bounded acquisition (≤ 2 fps, ≥ 500 ms spacing, ≤ 12 frames,
  8 s window) → post-capture matching → atomic commit → result on screen;
- in-app **Stop** during sampling and separate **Cancel** after sampling; leaving the app
  or locking the phone cancels; post-capture (8 s) and total (15 s) deadlines;
- local recognition: dHash + flat Hamming search over a synthetic L0 pack built in memory
  from seeds (6 works × 30 s), temporal-order check, thresholds marked `UNCALIBRATED`;
- results `VERIFIED_MATCH`, `POSSIBLE_MATCH`, `NO_CONFIDENT_MATCH`, `INSUFFICIENT_SIGNAL`,
  `UNSUPPORTED_CAPTURE`, `CANCELLED` (`OUTSIDE_CATALOGUE` is never emitted in L0);
- memory only (D08): frames become hashes and are dropped; results expire after 15 min.

The in-app "synthetic test clip" source plays a self-generated clip on the app's own screen
so each result path can be exercised. It is not evidence of cross-app capture on iPhone.

## Layout

| Path | What |
|---|---|
| `DetectAClipCore/` | Swift package: result enum, `ScanCoordinator`, `FrameSampler`, synthetic renderer, catalogue, `Matcher`, unit tests |
| `DetectAClip/` | SwiftUI app (onboarding, home, consent, scanning, result, legal) |
| `project.yml` | XcodeGen spec; the `.xcodeproj` is generated, not committed |

## Getting a build

### Without a Mac (GitHub Actions)

Every push touching `ios/` runs `.github/workflows/ios-build.yml` on a GitHub-hosted Mac:
`swift test`, simulator build, unsigned Release build for iPhone. Download the artifact
`DetectAClip-iOS-<commit>` from the workflow run. It contains:

- `DetectAClip-unsigned.ipa` — arm64 iPhone build, **not signed**;
- `DetectAClip-simulator.app.zip` — for the iOS Simulator on a Mac;
- `SHA256SUMS.txt`.

iOS only installs signed apps. To put the unsigned `.ipa` on your own iPhone, re-sign it with
your Apple ID using a sideloading tool on a Windows PC or Mac (for example Sideloadly or
AltStore). With a free Apple ID the signature lasts 7 days; a paid Apple Developer account
gives a year and enables TestFlight.

### With a Mac

```bash
brew install xcodegen
cd ios
swift test --package-path DetectAClipCore   # core unit tests
xcodegen generate
open DetectAClip.xcodeproj
```

In Xcode select the `DetectAClip` target → Signing & Capabilities → choose your Team (a free
Apple ID works) and, if needed, change the bundle identifier. Plug in the iPhone, enable
Developer Mode on it (Settings → Privacy & Security), and press Run.

## Verification status

Nothing here has been compiled on the authoring host (Linux, no Xcode). The CI run is the
first compile evidence; a physical-iPhone run is still required for any device claim
(blocker B-02). Requirements: Xcode 15+ (Swift 5.9), iOS 16.0+ deployment target.
