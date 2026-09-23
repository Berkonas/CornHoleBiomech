// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "CornholeBiomechanics",
    platforms: [.macOS(.v15)],
    products: [
        .executable(name: "CornholeBiomechanics", targets: ["CornholeBiomechanics"]),
        .executable(name: "SceneVision", targets: ["SceneVision"]),
    ],
    targets: [
        .executableTarget(
            name: "CornholeBiomechanics",
            path: "Sources/CornholeBiomechanics"
        ),
        .executableTarget(
            name: "SceneVision",
            path: "Sources/SceneVision"
        ),
        .testTarget(
            name: "CornholeBiomechanicsTests",
            dependencies: ["CornholeBiomechanics"],
            path: "Tests/CornholeBiomechanicsTests",
            resources: [.copy("Fixtures")]
        ),
    ],
    swiftLanguageModes: [.v5]
)

