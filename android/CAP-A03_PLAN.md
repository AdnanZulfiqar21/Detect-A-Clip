# CAP-A03 / CAP-04 plan — Android capture-source restriction (P01-T04)

Status: **NOT_STARTED / UNVERIFIED.** Nothing here is compiled. Symbols come from the
official documentation (S03, S04, Q03), not from an installed SDK (P00-T02 open, B-09).

## Question

Can the requesting app restrict the system picker to app-window sharing so that a full
display can never be selected, on API 37 and on older builds?

## Steps (each on two physical configurations, dedicated devices, synthetic content only)

1. With the installed API 37 SDK, confirm in headers that
   `MediaProjectionConfig.Builder`, `setSourceEnabled(int, boolean)`,
   `PROJECTION_SOURCE_DISPLAY`, `PROJECTION_SOURCE_APP` and `PROJECTION_SOURCE_APP_CONTENT`
   exist with the documented signatures. Record the availability attributes.
2. Build the picker config with DISPLAY disabled and APP enabled. Compile it behind an
   `SDK_INT` check, in a separate source set, so the API-34 path stays unchanged.
3. 20 attempts per device to select a full display (CAP-A03 "escape attempts"): mode
   swaps, rotation, split-screen, PiP, recents, notification shade, lock/unlock.
4. CAP-04 transitions inside the chosen app with seeded synthetic private views and the
   overlay classes (notification banner, incoming call, keyboard/password field, PiP,
   share sheet). Record what was acquired, separately from processing and egress.
5. Legacy (API 34–36) builds: record the user-choice picker behaviour. A user choosing an
   app is **not** proof that a display cannot be chosen.

## Decision rule

App-only constraint demonstrated and not escapable → scope evidence for G01. Otherwise
the Android consumer cell stays **BLOCKED** (D01 default) and only L0 lab research
continues. `APP_CONTENT` is out of scope for third-party sources (F-13).
