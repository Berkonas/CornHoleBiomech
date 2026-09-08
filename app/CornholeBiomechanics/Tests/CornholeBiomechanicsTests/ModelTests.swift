import XCTest
@testable import CornholeBiomechanics

final class ModelTests: XCTestCase {
    func testProjectRoundTripPreservesTrialMetadata() throws {
        let athlete = Athlete(participantCode: "P01", dominantHand: .left, notes: "")
        let trial = Trial(
            athleteID: athlete.id,
            sourceVideoRelativePath: "videos/test.mov",
            originalFilename: "test.mov",
            cameraView: .side,
            throwingSide: .left,
            targetDirection: .rightToLeft
        )
        let project = StudyProject(name: "Test", athletes: [athlete], trials: [trial])
        let data = try JSONEncoder.projectEncoder.encode(project)
        let decoded = try JSONDecoder.projectDecoder.decode(StudyProject.self, from: data)
        XCTAssertEqual(decoded.trials.first?.cameraView, .side)
        XCTAssertEqual(decoded.trials.first?.throwingSide, .left)
    }

    func testOutcomeUsesDocumentedBoardCoordinates() throws {
        let outcome = TrialOutcome(
            scoreCategory: .onBoard,
            intendedPoint: BoardPoint(xInches: 12, yInches: 39),
            firstContactPoint: BoardPoint(xInches: 10, yInches: 36)
        )
        let decoded = try JSONDecoder.projectDecoder.decode(
            TrialOutcome.self,
            from: JSONEncoder.projectEncoder.encode(outcome)
        )
        XCTAssertEqual(decoded.firstContactPoint?.xInches, 10)
        XCTAssertEqual(decoded.scoreCategory, .onBoard)
    }

    func testAnalysisResultDecoderAcceptsUnavailableValues() throws {
        let json = #"""
        {
          "trial_id":"T1", "athlete_id":"A1",
          "summaries":{"elbow_angle_deg_at_release":112.5,"velocity":null},
          "quality":{
            "average_pose_confidence":0.88, "usable_frame_percentage":94.0,
            "missing_data_percentage":3.0, "low_confidence_landmark_counts":{"right_wrist":2},
            "manual_correction_count":1, "interpolated_sample_count":2,
            "frame_rate_fps":60, "resolution_pixels":{"width":1920,"height":1080},
            "camera_view":"side", "warnings":[],
            "confidence_note":"Confidence is not physical error."
          },
          "events":{}, "warnings":[],
          "claim_scope":"projected_2d_kinematics_not_true_3d_joint_orientation"
        }
        """#
        let result = try JSONDecoder.projectDecoder.decode(AnalysisResults.self, from: Data(json.utf8))
        XCTAssertEqual(result.quality.frameRateFPS, 60)
        XCTAssertEqual(result.summaries["elbow_angle_deg_at_release"]!, 112.5)
        XCTAssertNil(result.summaries["velocity"]!)
    }

    func testComparisonAndRelationshipDecodersMatchPythonBoundary() throws {
        let comparisonJSON = #"""
        {
          "test_trial_id":"T1", "reference_trial_ids":["R1"], "camera_view":"side",
          "label":"Prototype reference similarity - single reference trial",
          "raw_metrics":{"elbow_angle_paired_samples":101,"elbow_angle_mae_deg":3.5},
          "similarity":{"overall":82.0,"components":{},"omitted_components":[],"interpretation":"reference_similarity_not_performance_quality"},
          "curves":{"tau":[0,1],"test":{"elbow_path_arm_lengths":[[0,0],[0.5,0.2]]},"reference_mean":{},"reference_sd":{}},
          "claim_scope":"reference_similarity_not_performance_quality"
        }
        """#
        let comparison = try JSONDecoder.projectDecoder.decode(ComparisonDocument.self, from: Data(comparisonJSON.utf8))
        XCTAssertEqual(comparison.rawMetrics["elbow_angle_paired_samples"]!, 101)
        XCTAssertEqual(comparison.curves?.test["elbow_path_arm_lengths"]?.vectors?.count, 2)

        let relationshipJSON = #"""
        {
          "athlete_id":"A1", "trial_count":8, "outcome_variable":"score_category",
          "relationships":{"reference_similarity_score":{"n":8,"status":"estimated","message":"Exploratory.","spearman_rho":0.5,"spearman_p_value_exploratory":0.2,"spearman_bootstrap_95_ci":[0.1,0.8]}},
          "within_athlete_consistency":{"reference_similarity_score":{"n":8,"mean":80,"standard_deviation":4,"median":81,"range":12,"units":"0-100 reference similarity index"}},
          "data_rows":[{"trial_id":"T1","score_category":3,"reference_similarity_score":84}],
          "claim_scope":"within_athlete_observational_association_not_causation"
        }
        """#
        let relationship = try JSONDecoder.projectDecoder.decode(RelationshipDocument.self, from: Data(relationshipJSON.utf8))
        XCTAssertEqual(relationship.dataRows?.first?.scoreCategory, 3)
        XCTAssertEqual(relationship.relationships["reference_similarity_score"]?.n, 8)
    }

    @MainActor
    func testCorrectionUndoPreservesSeparateRawPoseFile() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let raw = Data(#"{"fps":60,"width":100,"height":100,"frame_count":1,"backend":"test","model_name":"test","frames":[{"frame_index":0,"time_seconds":0,"landmarks":{"right_wrist":{"x":10,"y":20,"confidence":0.9}}}]}"#.utf8)
        try raw.write(to: directory.appendingPathComponent("pose_raw.json"))
        let originalRaw = try Data(contentsOf: directory.appendingPathComponent("pose_raw.json"))
        let controller = TrialDataController()
        controller.load(analysisURL: directory)
        let undo = controller.correctionUndoManager
        controller.setCorrection(frame: 0, landmark: "right_wrist", x: 30, y: 40, undoManager: undo)
        XCTAssertEqual(controller.correction(frame: 0, landmark: "right_wrist")?.x, 30)
        undo.undo()
        XCTAssertNil(controller.correction(frame: 0, landmark: "right_wrist"))
        undo.redo()
        XCTAssertEqual(controller.correction(frame: 0, landmark: "right_wrist")?.x, 30)
        XCTAssertEqual(try Data(contentsOf: directory.appendingPathComponent("pose_raw.json")), originalRaw)
        controller.load(analysisURL: nil)
        XCTAssertFalse(undo.canUndo, "Switching trials must clear the previous trial’s undo history")
    }
    func testPythonInsightsDecodeWithUnavailableComparison() throws {
        let url = try XCTUnwrap(Bundle.module.url(forResource: "insights", withExtension: "json", subdirectory: "Fixtures"))
        let value = try JSONDecoder.projectDecoder.decode(TrialInsights.self, from: Data(contentsOf: url))
        XCTAssertEqual(value.consistency.n, 9)
        XCTAssertNotNil(value.quality.score)
        XCTAssertNotNil(value.provenance.configuration?.filter?.cutoff_hz)
        XCTAssertTrue(value.athlete.contains("SYNTHETIC"))
    }

    func testCanonicalPythonCorrectionsDecodeAndEncodeSnakeCase() throws {
        let json = #"{"schema_version":1,"corrections":[{"frame_index":3,"landmark":"right_wrist","x":12,"y":34,"kind":"manual","created_at":"2026-09-07T12:00:00Z"}]}"#
        let document = try JSONDecoder.projectDecoder.decode(CorrectionDocument.self, from: Data(json.utf8))
        XCTAssertEqual(document.corrections.first?.frameIndex, 3)
        let encoded = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder.projectEncoder.encode(document)) as? [String: Any])
        XCTAssertEqual(encoded["schema_version"] as? Int, 1)
        XCTAssertNil(encoded["schemaVersion"])
    }

}
