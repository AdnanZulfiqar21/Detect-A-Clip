#!/usr/bin/env bash
# CAP-I03 / P02-T01a: pin iOS SDK facts from INSTALLED headers on a macOS host (CI runner).
# Read-only: prints Xcode/SDK inventory and the availability attributes of every symbol the
# iOS capture path uses. Never captures, never signs, never touches a device.
set -uo pipefail

section() { printf '\n## %s\n' "$1"; }

section "Host"
sw_vers || true
uname -m

section "Installed Xcode versions"
for X in /Applications/Xcode*.app; do
  [ -d "$X" ] || continue
  printf '%s: ' "$X"
  "$X/Contents/Developer/usr/bin/xcodebuild" -version 2>/dev/null | tr '\n' ' '
  echo
done
echo "Selected: $(xcode-select -p)"
xcodebuild -version

section "iOS SDKs of the selected Xcode"
xcodebuild -showsdks 2>/dev/null | grep -iE "iphoneos|iphonesimulator" || true
IOS_SDK="$(xcrun --sdk iphoneos --show-sdk-path 2>/dev/null || true)"
IOS_VER="$(xcrun --sdk iphoneos --show-sdk-version 2>/dev/null || true)"
echo "iphoneos SDK: ${IOS_SDK:-none} (version ${IOS_VER:-?})"
[ -n "$IOS_SDK" ] || { echo "No iOS SDK installed; nothing further to probe."; exit 0; }

FW="$IOS_SDK/System/Library/Frameworks"
for f in ScreenCaptureKit ReplayKit; do
  if [ -d "$FW/$f.framework" ]; then echo "$f.framework: PRESENT in iOS SDK"; else echo "$f.framework: ABSENT in iOS SDK"; fi
done

# Print each symbol's declaration with the availability macros around it.
probe() {
  local fw="$1"; shift
  local hdrs="$FW/$fw.framework/Headers"
  [ -d "$hdrs" ] || { echo "($fw headers absent)"; return; }
  for sym in "$@"; do
    echo "### $fw: $sym"
    grep -n -B3 -A1 -E "(@interface|@protocol|typedef NS_ENUM\(.*\)|^- |^\+ |@property).*\b$sym\b" "$hdrs"/*.h 2>/dev/null \
      | grep -E "$sym|API_AVAILABLE|API_UNAVAILABLE|API_DEPRECATED|NS_AVAILABLE|NS_DEPRECATED|API_TO_BE_DEPRECATED" \
      | sed "s#$hdrs/##" | head -12
  done
}

section "ScreenCaptureKit symbols used by ScreenCaptureAdapter.swift"
probe ScreenCaptureKit SCContentSharingPicker SCContentSharingPickerObserver SCContentSharingPickerConfiguration \
  SCStream SCStreamConfiguration SCContentFilter SCStreamOutput SCStreamDelegate SCStreamOutputType \
  SCShareableContent allowedPickerModes
section "ReplayKit candidate symbols"
probe ReplayKit RPSystemBroadcastPickerView RPBroadcastSampleHandler RPScreenRecorder

section "Swift-visible availability (typecheck against the iOS SDK at its own version)"
TMP="$(mktemp -d)"
cat > "$TMP/probe.swift" <<'EOF'
import Foundation
#if canImport(ScreenCaptureKit)
import ScreenCaptureKit
func probeSCK() {
    _ = SCStreamConfiguration()
    _ = SCContentSharingPicker.shared
    let _: SCStreamOutputType = .screen
}
let sckImportable = true
#else
let sckImportable = false
#endif
EOF
if xcrun --sdk iphoneos swiftc -typecheck -target "arm64-apple-ios${IOS_VER}" "$TMP/probe.swift" 2> "$TMP/err.txt"; then
  echo "swiftc typecheck: OK (ScreenCaptureKit symbols above resolve for arm64-apple-ios${IOS_VER})"
else
  echo "swiftc typecheck: FAILED; diagnostics:"; sed 's/^/    /' "$TMP/err.txt" | head -40
fi
exit 0
