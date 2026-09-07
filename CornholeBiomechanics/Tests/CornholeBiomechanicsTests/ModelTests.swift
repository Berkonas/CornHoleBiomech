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
}
