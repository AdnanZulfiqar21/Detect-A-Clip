// swift-tools-version:5.9
import PackageDescription

// Platform-independent core of the iPhone lab build: result contract, scan coordinator,
// bounded sampler, synthetic L0 catalogue and hash/flat retrieval. Foundation only, so the
// unit tests run with `swift test` on any macOS host without a simulator.
let package = Package(
    name: "DetectAClipCore",
    platforms: [.iOS(.v16), .macOS(.v13)],
    products: [
        .library(name: "DetectAClipCore", targets: ["DetectAClipCore"]),
    ],
    targets: [
        .target(name: "DetectAClipCore"),
        .testTarget(name: "DetectAClipCoreTests", dependencies: ["DetectAClipCore"]),
    ]
)
