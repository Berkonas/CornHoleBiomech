import XCTest
@testable import CornholeBiomechanics

final class PendulumTests: XCTestCase {
    // Independent Cartesian kinetic/potential energy, not coefficient reuse.
    private func lagrangian(_ model: PendulumMechanics, _ s: PendulumState) -> Double {
        let p = model.p
        func v2(_ r1: Double, _ r2: Double) -> Double {
            let x = r1*s.w1*cos(s.q1) + r2*s.w2*cos(s.q2)
            let y = r1*s.w1*sin(s.q1) + r2*s.w2*sin(s.q2)
            return x*x+y*y
        }
        if !model.kind.isDouble {
            let l = p.l1+p.l2, m = p.m1+p.m2
            if model.kind == .singleSimple { return 0.5*(m+p.bag)*l*l*s.w1*s.w1 + (m+p.bag)*p.g*l*cos(s.q1) }
            return 0.5*m*pow(l/2*s.w1,2) + 0.5*m*l*l/12*s.w1*s.w1 + 0.5*p.bag*l*l*s.w1*s.w1 + (m/2+p.bag)*p.g*l*cos(s.q1)
        }
        if model.kind == .doubleSimple {
            return 0.5*p.m1*v2(p.l1,0) + 0.5*(p.m2+p.bag)*v2(p.l1,p.l2) + p.m1*p.g*p.l1*cos(s.q1) + (p.m2+p.bag)*p.g*(p.l1*cos(s.q1)+p.l2*cos(s.q2))
        }
        let t = 0.5*p.m1*v2(p.l1/2,0) + 0.5*p.m2*v2(p.l1,p.l2/2) + 0.5*p.bag*v2(p.l1,p.l2)
        let rotation = 0.5*p.m1*p.l1*p.l1/12*s.w1*s.w1 + 0.5*p.m2*p.l2*p.l2/12*s.w2*s.w2
        let negativeV = p.m1*p.g*p.l1/2*cos(s.q1) + p.m2*p.g*(p.l1*cos(s.q1)+p.l2/2*cos(s.q2)) + p.bag*p.g*(p.l1*cos(s.q1)+p.l2*cos(s.q2))
        return t + rotation + negativeV
    }

    private func partial(_ m: PendulumMechanics, _ s: PendulumState, _ key: WritableKeyPath<PendulumState, Double>) -> Double {
        let h = 1e-5
        var plus = s, minus = s
        plus[keyPath: key] += h; minus[keyPath: key] -= h
        return (lagrangian(m, plus)-lagrangian(m, minus))/(2*h)
    }

    func testAllFourModelsSatisfyIndependentEulerLagrangeEquationsWithTorques() {
        for kind in PendulumKind.allCases {
            for bag in [0.0, 0.45] {
                var m = PendulumMechanics(kind: kind); m.p.bag = bag
                for q in [-1.1, 0.25, 1.3] {
                    let s = PendulumState(q1: q, q2: q+0.7, w1: 1.4, w2: -0.8)
                    let ds = m.rate(s, shoulderTorque: 0.9, elbowTorque: -0.3)
                    let h = 1e-5
                    let timeMomentum1 = (partial(m,s.adding(ds,scale:h),\.w1)-partial(m,s.adding(ds,scale:-h),\.w1))/(2*h)
                    XCTAssertEqual(timeMomentum1-partial(m,s,\.q1), kind.isDouble ? 1.2 : 0.9, accuracy: 5e-5, "\(kind)")
                    if kind.isDouble {
                        let timeMomentum2 = (partial(m,s.adding(ds,scale:h),\.w2)-partial(m,s.adding(ds,scale:-h),\.w2))/(2*h)
                        XCTAssertEqual(timeMomentum2-partial(m,s,\.q2), -0.3, accuracy: 5e-5, "\(kind)")
                    }
                }
            }
        }
    }

    func testKnownSingleLimitsAndMassIndependence() {
        let s = PendulumState(q1: 0.6,q2:0.6,w1:0,w2:0)
        var simple = PendulumMechanics(kind:.singleSimple)
        XCTAssertEqual(simple.rate(s).w1, -9.81/0.65*sin(0.6), accuracy:1e-12)
        let baseline = simple.rate(s).w1
        simple.p.m1 = 100; simple.p.bag = 10
        XCTAssertEqual(simple.rate(s).w1, baseline, accuracy:1e-12)
        var rod = PendulumMechanics(kind:.singleCompound); rod.p.bag = 0
        XCTAssertEqual(rod.rate(s).w1, -3*9.81/(2*0.65)*sin(0.6), accuracy:1e-12)
        XCTAssertEqual(rod.smallAnglePeriod!, 2 * .pi * sqrt(2*0.65/(3*9.81)), accuracy:1e-12)
    }

    func testEnergyConservationAndPositiveMassMatrixAcrossControlExtremes() throws {
        for kind in PendulumKind.allCases {
            for length in [0.4, 1.0] {
                for bag in [0.0, 0.6] {
                    for bend in [-90.0, 90.0] {
                        var m = PendulumMechanics(kind:kind)
                        m.p.l1 = length*0.30/0.65; m.p.l2 = length*0.35/0.65; m.p.bag = bag
                        let c = m.coefficients
                        if kind.isDouble { XCTAssertGreaterThan(c.a*c.b-c.c*c.c, 0) }
                        let samples = m.simulate(angleDegrees:80,bendDegrees:bend)
                        let initial = try XCTUnwrap(samples.first)
                        XCTAssertEqual(samples.last?.time, 4)
                        XCTAssertTrue(samples.allSatisfy { $0.energy.isFinite })
                        let drift = samples.map { abs($0.energy-initial.energy) }.max()!
                        XCTAssertLessThan(drift/(c.g1+c.g2), 1e-5, "\(kind) energy drift")
                    }
                }
            }
        }
    }

    func testIntegrationConvergenceAndEquilibrium() throws {
        for kind in PendulumKind.allCases {
            let m = PendulumMechanics(kind:kind)
            XCTAssertTrue(m.simulate(angleDegrees:0,bendDegrees:0).allSatisfy { $0.state.q1 == 0 && $0.state.q2 == 0 })
            let reference = try XCTUnwrap(m.simulate(angleDegrees:-45,bendDegrees:40,dt:0.0001).last).state
            func error(_ dt: Double) -> Double {
                let s = m.simulate(angleDegrees:-45,bendDegrees:40,dt:dt).last!.state
                return abs(s.q1-reference.q1)+abs(s.q2-reference.q2)+abs(s.w1-reference.w1)+abs(s.w2-reference.w2)
            }
            // Use the asymptotic step-size range, below the UI solver step.
            XCTAssertLessThan(error(0.001), error(0.002)/8, "RK4 refinement: \(kind)")
        }
    }

    func testInvalidParametersDoNotSimulate() {
        var m = PendulumMechanics(kind:.doubleCompound); m.p.l1 = 0
        XCTAssertTrue(m.simulate(angleDegrees:30,bendDegrees:30).isEmpty)
        m.p.l1 = 0.3
        XCTAssertTrue(m.simulate(angleDegrees:.nan,bendDegrees:30).isEmpty)
        XCTAssertTrue(m.simulate(angleDegrees:30,bendDegrees:30,dt:0).isEmpty)
    }

    func testArmMotionOptionalDecodingAndNullMetrics() throws {
        let data = Data(#"{"status":"insufficient_tracking","summaries":{"arm_motion_mean_flexion_deg":null},"start_frame":2,"release_frame":10,"sample_count":9,"valid_sample_count":2,"coverage":0.222,"radius_coverage":null,"message":"Review tracking"}"#.utf8)
        let result = try JSONDecoder().decode(ArmMotionAnalysis.self,from:data)
        XCTAssertEqual(result.sample_count,9)
        XCTAssertNil(result.summaries["arm_motion_mean_flexion_deg"] ?? nil)
        XCTAssertEqual(metricLabel("arm_motion_radius_cv_ratio"),"Forward-swing radius CV (ratio)")
    }
}
