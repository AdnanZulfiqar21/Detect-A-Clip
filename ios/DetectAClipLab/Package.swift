// swift-tools-version:5.9
// Not compilable on the Windows authoring host; CI compiles and tests it on macOS
// (.github/workflows/swift-core.yml). See ios/README.md.
import PackageDescription

let package = Package(
    name: "DetectAClipLab",
    // CryptoKit (Ed25519, SHA-256) needs macOS 10.15+/iOS 13+; ScreenCaptureKit paths are gated separately.
    platforms: [.macOS(.v13), .iOS(.v17)],
    products: [.library(name: "DetectAClipCore", targets: ["DetectAClipCore"])],
    targets: [
        .target(name: "DetectAClipCore", path: "Sources"),
        .testTarget(name: "DetectAClipCoreTests", dependencies: ["DetectAClipCore"], path: "Tests"),
    ]
)
