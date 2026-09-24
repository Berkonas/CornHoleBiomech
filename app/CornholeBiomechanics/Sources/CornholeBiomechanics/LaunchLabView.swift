import SwiftUI

/// Release-physics explorer (Tools → Launch Lab). Placeholder until the Launch Lab task replaces it.
struct LaunchLabView: View {
    var body: some View {
        EmptyState("Launch Lab", symbol: launchLabSymbol,
                   message: "Explore how release speed, angle and height decide where the bag lands.")
    }
}

let launchLabSymbol = "point.topleft.down.to.point.bottomright.curvepath"
