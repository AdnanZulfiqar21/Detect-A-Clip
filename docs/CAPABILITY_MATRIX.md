# CAPABILITY_MATRIX (F02, F03 stop-path matrix, D09)

Every cell records capture Stop, post-capture Cancel, process-termination behaviour and
discoverability separately. LAB_CAPTURE, CONSUMER_SCOPE, SOURCE_POLICY, RIGHTS and STORE
are independent statuses. **No cell is enabled.** Snapchat stays OFF.

| Cell | Capture Stop candidates | Post-capture Cancel | Termination | Lab | Consumer | Policy | Store |
|---|---|---|---|---|---|---|---|
| Android 15 QPR1+ (tested builds) | System chip; notification "Stop"; in-app Stop/Cancel | Notification switches to "Cancel" while matching (code); return-to-app Stop/Cancel. Chip may disappear at close | Task Manager kills without callback; nothing restored | NOT_STARTED (B-01) | BLOCKED (D01, CAP-A03) | BLOCKED (B-03) | BLOCKED |
| Older Android, notifications permitted | Notification action; OS controls if any; in-app | As above | As above | NOT_STARTED | BLOCKED | BLOCKED | BLOCKED |
| Older Android, notifications denied | OS controls if any; in-app; Task Manager fallback | Return-to-app only | As above | NOT_STARTED | BLOCKED (D09) | BLOCKED | BLOCKED |
| iPhone, ScreenCaptureKit candidate | System indicator (behaviour UNVERIFIED); in-app | Return-to-app; background task expiry cancels | Unknown | BLOCKED (B-02) | BLOCKED | BLOCKED | BLOCKED |
| iPhone, ReplayKit research candidate | System broadcast control; host/extension lifetime | Unknown | Orphan extension risk | BLOCKED (B-02) | BLOCKED | BLOCKED | BLOCKED |

Source cells (SRC-TIK, SRC-INS, SRC-FBK, SRC-YTB, SRC-X) × OS: all UNKNOWN; SRC-SNP BLOCKED/OFF.
