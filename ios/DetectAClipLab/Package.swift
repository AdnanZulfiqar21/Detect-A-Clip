// swift-tools-version:5.9
// NOT COMPILED on the authoring host (Windows). See ios/README.md.
import PackageDescription

let package = Package(
    name: "DetectAClipLab",
    products: [.library(name: "DetectAClipCore", targets: ["DetectAClipCore"])],
    targets: [
        .target(name: "DetectAClipCore", path: "Sources"),
        .testTarget(name: "DetectAClipCoreTests", dependencies: ["DetectAClipCore"], path: "Tests"),
    ]
)
