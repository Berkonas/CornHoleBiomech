import XCTest
import AppKit
import SwiftUI
@testable import CornholeBiomechanics

final class TemporaryVisualQA: XCTestCase {
    @MainActor func testRenderFeatureViews() throws {
        let output = URL(fileURLWithPath: "/tmp/cornhole-arm-visual-qa")
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        func render<V: View>(_ view: V, name: String, width: CGFloat, height: CGFloat) throws {
            let hosting = NSHostingView(rootView: view.frame(width: width, height: height).background(Color.white).environment(\.colorScheme, .light))
            hosting.frame = NSRect(x:0,y:0,width:width,height:height)
            hosting.layoutSubtreeIfNeeded()
            let bitmap = try XCTUnwrap(hosting.bitmapImageRepForCachingDisplay(in:hosting.bounds))
            hosting.cacheDisplay(in:hosting.bounds,to:bitmap)
            try XCTUnwrap(bitmap.representation(using:.png,properties:[:])).write(to:output.appendingPathComponent(name+".png"))
        }
        for kind in PendulumKind.allCases {
            try render(PendulumLabView(initialKind:kind),name:kind.rawValue,width:1050,height:1080)
        }
        try render(PendulumLabView(initialKind:.doubleCompound,showEquations:true),name:"equations",width:1050,height:2250)
        try render(PendulumLabView(initialKind:.doubleCompound),name:"narrow",width:760,height:1200)
        let path = URL(fileURLWithPath:"/tmp/cornhole-arm-qa.cornholeproject/analyses/E006574B-5C53-4A4D-85D5-6650D74435E3")
        let result = try JSONDecoder().decode(AnalysisResults.self,from:Data(contentsOf:path.appendingPathComponent("results.json")))
        let normalized = try JSONDecoder().decode(NormalizedDocument.self,from:Data(contentsOf:path.appendingPathComponent("normalized.json")))
        let store = ProjectStore(automaticallyRestore:false)
        try render(ArmMotionPanel(result:result.armMotion, normalized:normalized,stale:false,fraction:.constant(0.4)).environmentObject(store),name:"measured",width:1050,height:720)
    }
}
