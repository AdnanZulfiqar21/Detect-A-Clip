"""Source-level privacy guard (P06-T03, DATA-L02 source scope, T-01/T-02).

Fails if shipped Android/iOS sources gain logging, networking, media/microphone/camera or
Photos APIs, if capture-path files gain persistence APIs, or if the Android manifest / iOS
plist gain permissions or usage keys outside the approved set. This is static evidence only;
packet, file-system and crash-log inspection on devices stay DATA-L01/L02 device tests (B-01/B-02).
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ANDROID_MAIN = REPO / "android" / "app" / "src" / "main"
IOS_SOURCES = [REPO / "ios" / "DetectAClipLab" / "Sources", REPO / "ios" / "LabApp" / "Sources"]


def _files(root: Path, ext: str):
    return sorted(p for p in root.rglob(f"*{ext}") if p.is_file())


def _code(p: Path) -> str:
    """Source without // and /* */ comments, so documentation may name forbidden APIs."""
    s = p.read_text(encoding="utf-8")
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    return "\n".join(line.split("//", 1)[0] if "://" not in line else line for line in s.splitlines())


FORBIDDEN_ANDROID = {
    "logging": r"\bandroid\.util\.Log\b|\bLog\.[vdiwe]\(|\bprintln\(|\bprintStackTrace\(",
    "network": r"\bjava\.net\.|\bHttpURLConnection\b|\bokhttp3?\b|\bSocket\(|\bURL\(",
    "media/camera/audio": r"\bandroid\.hardware\.camera|\bCameraManager\b|\bAudioRecord\b|\bMediaRecorder\b",
    "gallery/external storage": r"\bMediaStore\b|\bgetExternal\w*\(|\bBitmap\b.*\bcompress\(",
}
FORBIDDEN_IOS = {
    "logging": r"\bNSLog\(|\bos_log\(|\bLogger\(|(?<![\w.])print\(|\bdebugPrint\(",
    "network": r"\bURLSession\b|\bimport\s+Network\b|\bNWConnection\b|\bCFNetwork\b|\bURLRequest\b",
    "media/camera/audio": r"\bAVCaptureDevice\b|\bAVAudio\w*\b|\bimport\s+AVFoundation\b",
    "photos": r"\bimport\s+Photos\b|\bPHPhotoLibrary\b|\bUIImageWriteToSavedPhotosAlbum\b",
}
# Files on the capture/recognition path must not persist anything (D08 memory-only).
CAPTURE_PATH = ["CaptureService.kt", "CaptureLifecycle.kt", "RecognitionSession.kt", "FrameSelector.kt", "Recognition.kt",
                "DacDhash.kt", "ScanCoordinator.kt", "CaptureStartPolicy.kt",
                "CaptureLifecycle.swift", "RecognitionSession.swift", "FrameSelector.swift", "Recognition.swift",
                "DacDhash.swift", "DacExact.swift", "ScanCoordinator.swift", "ScreenCaptureAdapter.swift", "LabFlow.swift"]
PERSISTENCE = r"\bFiles\.write\w*\(|\bFileOutputStream\b|\bFileChannel\b|\bopenFileOutput\b|\bSharedPreferences\b|" \
              r"\.write\(to:|\bcreateFile\(|\bUserDefaults\b|\bFileManager\b|\bfsync\(|\bObjectOutputStream\b"


def _hits(files, patterns):
    out = []
    for f in files:
        code = _code(f)
        for what, rx in patterns.items():
            for m in re.finditer(rx, code):
                out.append(f"{f.relative_to(REPO)}: {what}: {m.group(0)}")
    return out


def test_android_sources_have_no_logging_network_or_media_apis():
    assert _hits(_files(ANDROID_MAIN / "java", ".kt"), FORBIDDEN_ANDROID) == []


def test_ios_sources_have_no_logging_network_media_or_photos_apis():
    files = [f for root in IOS_SOURCES for f in _files(root, ".swift")]
    assert len(files) > 10
    assert _hits(files, FORBIDDEN_IOS) == []


def test_capture_path_files_never_persist():
    files = [f for f in _files(ANDROID_MAIN / "java", ".kt") + [f for r in IOS_SOURCES for f in _files(r, ".swift")]
             if f.name in CAPTURE_PATH]
    assert {f.name for f in files} == set(CAPTURE_PATH)
    assert _hits(files, {"persistence": PERSISTENCE}) == []


def test_android_manifest_permissions_are_exactly_the_approved_set():
    m = (ANDROID_MAIN / "AndroidManifest.xml").read_text(encoding="utf-8")
    requested = {p for p, removed in re.findall(r'<uses-permission android:name="([^"]+)"\s*(tools:node="remove")?', m) if not removed}
    assert requested == {"android.permission.FOREGROUND_SERVICE", "android.permission.FOREGROUND_SERVICE_MEDIA_PROJECTION",
                         "android.permission.POST_NOTIFICATIONS"}
    for removed in ("INTERNET", "ACCESS_NETWORK_STATE", "RECORD_AUDIO"):
        assert re.search(rf'android\.permission\.{removed}"\s*tools:node="remove"', m), removed
    assert 'android:allowBackup="false"' in m
    assert re.search(r'android:name="\.CaptureService"\s*android:exported="false"', m)


def test_capture_disabled_by_default_in_both_lab_builds():
    props = (REPO / "android" / "gradle.properties").read_text(encoding="utf-8")
    assert re.search(r"^dac\.captureEnabled=false$", props, re.M)
    plist = (REPO / "ios" / "LabApp" / "project.yml").read_text(encoding="utf-8")
    assert re.search(r"^\s*DACCaptureEnabled: false$", plist, re.M)


def test_ios_plist_has_no_capture_sensitive_usage_keys_or_background_audio():
    spec = (REPO / "ios" / "LabApp" / "project.yml").read_text(encoding="utf-8")
    for key in ("NSCameraUsageDescription", "NSMicrophoneUsageDescription", "NSPhotoLibrary", "UIBackgroundModes",
                "NSLocalNetworkUsageDescription", "NSAllowsArbitraryLoads"):
        assert key not in spec, key
    privacy = (REPO / "ios" / "LabApp" / "Resources" / "PrivacyInfo.xcprivacy").read_text(encoding="utf-8")
    assert re.search(r"<key>NSPrivacyTracking</key>\s*<false/>", privacy)
    assert re.search(r"<key>NSPrivacyCollectedDataTypes</key>\s*<array/>", privacy)


def test_desktop_harness_has_no_network_imports():
    bad = []
    for f in sorted((REPO / "l0" / "dac_l0").rglob("*.py")):
        for m in re.finditer(r"^\s*(?:import|from)\s+(socket|urllib|requests|http\.client|httpx|aiohttp)\b", f.read_text(encoding="utf-8"), re.M):
            bad.append(f"{f.relative_to(REPO)}: {m.group(1)}")
    assert bad == []
