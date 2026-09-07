// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "CornholeBiomechanics",
    platforms: [.macOS(.v15)],
    products: [
        .executable(name: "CornholeBiomechanics", targets: ["CornholeBiomechanics"])
    ],
    targets: [
        .executableTarget(
            name: "CornholeBiomechanics",
            path: "Sources/CornholeBiomechanics"
        ),
        .testTarget(
            name: "CornholeBiomechanicsTests",
            dependencies: ["CornholeBiomechanics"],
            path: "Tests/CornholeBiomechanicsTests"
        ),
    ],
    swiftLanguageModes: [.v5]
)

