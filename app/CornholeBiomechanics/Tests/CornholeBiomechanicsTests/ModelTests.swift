import XCTest
@testable import CornholeBiomechanics

final class ModelTests: XCTestCase {
    @MainActor
    func testMetadataChangeRequiresReanalysisAndCrossAthleteSessionIsRejected() throws {
        let base = try temporaryDirectory("metadata")
        defer { try? FileManager.default.removeItem(at: base) }
        let paths = LibraryPaths(applicationSupportURL: base.appendingPathComponent("Support"), defaultLibraryURL: base.appendingPathComponent("Data"), libraryRootWasOverridden: false)
        let store = ProjectStore(paths: paths, trashHandler: { _ in })
        try store.addAthlete(NewAthleteDraft(participantCode: "A", dominantHand: .right))
        let athleteID = try XCTUnwrap(store.selectedAthleteID)
        let source = base.appendingPathComponent("source.mov")
        try Data("original".utf8).write(to: source)
        var trial = try store.importVideo(ImportDraft(videoURL: source, athleteID: athleteID))
        let analysis = try store.analysisOutput(for: trial)
        try FileManager.default.createDirectory(at: analysis.url, withIntermediateDirectories: true)
        try store.markAnalysisComplete(trialID: trial.id, relativePath: analysis.relativePath)
        trial = try XCTUnwrap(store.selectedTrial)
        trial.name = "Readable name"
        try store.updateTrialMetadata(trial)
        let marker = analysis.url.appendingPathComponent("needs_reanalysis.json")
        XCTAssertFalse(FileManager.default.fileExists(atPath: marker.path))
        trial.throwingSide = .left
        try store.updateTrialMetadata(trial)
        XCTAssertTrue(FileManager.default.fileExists(atPath: marker.path))
        XCTAssertTrue(store.selectedTrial?.analysisStatus.contains("reanalyze") == true)
        var draft = ImportDraft(videoURL: source, athleteID: athleteID)
        draft.sessionID = UUID()
        XCTAssertThrowsError(try store.importVideo(draft))
        XCTAssertEqual(store.project?.trials.count, 1)
    }
    func testRelationshipIncludesNewNumericFeatures() throws {
        let json = #"{"trial_id":"T1","bag_release_angle_deg":24.5,"shoulder_translation_net_arm_lengths":0.2,"missing":null}"#
        let row = try JSONDecoder().decode(RelationshipDocument.DataRow.self, from: Data(json.utf8))
        XCTAssertEqual(row.numericFeatures["bag_release_angle_deg"], 24.5)
        XCTAssertEqual(row.numericFeatures["shoulder_translation_net_arm_lengths"], 0.2)
        XCTAssertNil(row.numericFeatures["missing"])
        let roundTrip = try JSONDecoder().decode(RelationshipDocument.DataRow.self, from: JSONEncoder().encode(row))
        XCTAssertEqual(roundTrip.numericFeatures, row.numericFeatures)
    }

    @MainActor
    func testVideoPreparationArchivesAnalysisAndRestoresOriginalWithoutDuplicatingThrow() throws {
        let base = try temporaryDirectory("video-revisions")
        defer { try? FileManager.default.removeItem(at: base) }
        let paths = LibraryPaths(applicationSupportURL: base.appendingPathComponent("Support"), defaultLibraryURL: base.appendingPathComponent("Data"), libraryRootWasOverridden: false)
        let store = ProjectStore(paths: paths, trashHandler: { try FileManager.default.removeItem(at: $0) })
        try store.addAthlete(NewAthleteDraft(participantCode: "EDIT-01", dominantHand: .right))
        let source = base.appendingPathComponent("source.mov")
        try Data("original".utf8).write(to: source)
        var trial = try store.importVideo(ImportDraft(videoURL: source, athleteID: store.selectedAthleteID))
        let original = try XCTUnwrap(store.originalVideoURL(for: trial))
        let analysis = try store.analysisOutput(for: trial)
        try FileManager.default.createDirectory(at: analysis.url, withIntermediateDirectories: true)
        try Data("reviewed".utf8).write(to: analysis.url.appendingPathComponent("corrections.json"))
        try store.markAnalysisComplete(trialID: trial.id, relativePath: analysis.relativePath)
        trial = try XCTUnwrap(store.selectedTrial)
        let output = try store.preparationOutput(for: trial)
        try FileManager.default.createDirectory(at: output.deletingLastPathComponent(), withIntermediateDirectories: true)
        try Data("prepared".utf8).write(to: output)
        try store.usePreparedVideo(output, for: trial)
        trial = try XCTUnwrap(store.selectedTrial)
        XCTAssertEqual(store.project?.trials.count, 1)
        XCTAssertNil(store.analysisURL(for: trial))
        XCTAssertEqual(store.videoURL(for: trial), output)
        XCTAssertEqual(try Data(contentsOf: original), Data("original".utf8))
        XCTAssertTrue(FileManager.default.fileExists(atPath: output.deletingLastPathComponent().appendingPathComponent("previous-analysis/corrections.json").path))
        let reopened = ProjectStore(paths: paths, trashHandler: { _ in })
        XCTAssertEqual(reopened.selectedTrial?.preparedVideoRelativePath, trial.preparedVideoRelativePath)
        try FileManager.default.removeItem(at: output)
        XCTAssertNil(store.videoURL(for: trial), "Never silently substitute original geometry for a missing prepared clip")
        try store.usePreparedVideo(nil, for: trial)
        trial = try XCTUnwrap(store.selectedTrial)
        XCTAssertEqual(store.videoURL(for: trial), original)
        let revisionRoot = try XCTUnwrap(trial.preparationDirectoryRelativePath.flatMap(store.url(for:)))
        try store.deleteTrial(trial)
        XCTAssertFalse(FileManager.default.fileExists(atPath: revisionRoot.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: source.path), "External original must remain")
    }
    private func temporaryDirectory(_ label: String = "test") throws -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("CornholeBiomechanics-\(label)-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

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

    func testBagResultAndTrackDecodeWithExplicitProvenance() throws {
        let resultsJSON = #"""
        {
          "trial_id":"T1", "athlete_id":"A1", "summaries":{"bag_release_angle_deg":31.2},
          "quality":{"usable_frame_percentage":90,"missing_data_percentage":2,"low_confidence_landmark_counts":{},"manual_correction_count":0,"interpolated_sample_count":0,"frame_rate_fps":60,"resolution_pixels":{"width":100,"height":100},"camera_view":"side","warnings":[],"confidence_note":"not error"},
          "bag":{"automatic_tracking_coverage_percent":80,"effective_tracking_coverage_percent":90,"median_automatic_quality":0.82,"manual_correction_count":1,"interpolated_sample_count":2,"tracker":{"requested_method":"auto","effective_method":"template_matching","status":"partial_failure","fallback_reason":"CSRT unavailable","failure_frames":[8]},"launch":{"status":"estimated","release_frame":6,"velocity":{"speed_arm_lengths_s":2.1,"angle_deg":31.2},"physical_units":{"status":"not_available_without_valid_athlete_plane_calibration"}},"quality_note":"review required"},
          "events":{},"warnings":[],"claim_scope":"projected_2d_kinematics_not_true_3d_joint_orientation"
        }
        """#
        let results = try JSONDecoder.projectDecoder.decode(AnalysisResults.self, from: Data(resultsJSON.utf8))
        XCTAssertEqual(results.bag?.launch.velocity?.speedArmLengthsPerSecond, 2.1)
        XCTAssertEqual(results.bag?.tracker.failureFrames, [8])

        let trackJSON = #"""
        {"schema_version":1,"coordinate_system":"raw_video_pixels_x_right_y_down","units":"pixels","tracker":{"requested_method":"auto","effective_method":"template_matching","status":"complete","fallback_reason":null,"failure_frames":[],"quality_note":"review"},"seed":{"frame_index":4,"bbox_xywh":[10,20,12,13],"source":"manual_bbox"},"corrections":{"schema_version":1,"corrections":[]},"samples":[{"frame_index":4,"automatic_centroid":{"x":16,"y":26.5,"confidence":1},"effective_centroid":{"x":16,"y":26.5},"filtered_centroid":{"x":16,"y":26.5},"provenance":"automatic"}]}
        """#
        let track = try JSONDecoder.projectDecoder.decode(BagTrackDocument.self, from: Data(trackJSON.utf8))
        XCTAssertEqual(track.seed.frameIndex, 4)
        XCTAssertEqual(track.samples.first?.provenance, "automatic")
    }

    @MainActor
    func testBagCorrectionsRemainSeparateFromAutomaticTrack() throws {
        let directory = try temporaryDirectory("bag-correction")
        defer { try? FileManager.default.removeItem(at: directory) }
        let track = Data(#"{"schema_version":1,"coordinate_system":"raw_video_pixels_x_right_y_down","units":"pixels","tracker":{"requested_method":"auto","effective_method":"template_matching","status":"complete","fallback_reason":null,"failure_frames":[],"quality_note":"review"},"seed":{"frame_index":0,"bbox_xywh":[0,0,10,10],"source":"manual_bbox"},"corrections":{"schema_version":1,"corrections":[]},"samples":[{"frame_index":0,"automatic_centroid":{"x":5,"y":5,"confidence":1},"effective_centroid":{"x":5,"y":5},"filtered_centroid":{"x":5,"y":5},"provenance":"automatic"}]}"#.utf8)
        try track.write(to: directory.appendingPathComponent("bag_track.json"))
        let original = try Data(contentsOf: directory.appendingPathComponent("bag_track.json"))
        let controller = TrialDataController()
        controller.load(analysisURL: directory)
        controller.markBagReviewed(through: 12)
        XCTAssertEqual(controller.bagCorrections.reviewedThroughFrame, 12)
        controller.setBagCorrection(frame: 0, x: 8, y: 9)
        XCTAssertNil(controller.bagCorrections.reviewedThroughFrame)
        XCTAssertEqual(controller.bagPoint(frame: 0)?.x, 8)
        XCTAssertEqual(try Data(contentsOf: directory.appendingPathComponent("bag_track.json")), original)
        controller.resetBagCorrection(frame: 0)
        XCTAssertEqual(controller.bagPoint(frame: 0)?.x, 5)
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

    @MainActor
    func testAthleteLibraryRestoresAfterRelaunch() throws {
        let base = try temporaryDirectory("restore")
        defer { try? FileManager.default.removeItem(at: base) }
        let paths = LibraryPaths(
            applicationSupportURL: base.appendingPathComponent("Support"),
            defaultLibraryURL: base.appendingPathComponent("Visible Data"),
            libraryRootWasOverridden: false
        )
        let first = ProjectStore(paths: paths, automaticallyRestore: true, trashHandler: { _ in })
        try first.addAthlete(NewAthleteDraft(participantCode: "PERSIST-01", dominantHand: .right))
        let source = base.appendingPathComponent("source.mov")
        try Data("video".utf8).write(to: source)
        let trial = try first.importVideo(ImportDraft(videoURL: source, athleteID: first.selectedAthleteID))

        let second = ProjectStore(paths: paths, automaticallyRestore: true, trashHandler: { _ in })
        XCTAssertEqual(second.project?.athletes.first?.participantCode, "PERSIST-01")
        XCTAssertEqual(second.project?.trials.first?.id, trial.id)
        XCTAssertEqual(second.selectedAthleteID, first.selectedAthleteID)
        XCTAssertTrue(second.videoState(for: trial).isAvailable)
    }

    @MainActor
    func testMissingLibraryIsReportedWithoutDiscardingItsIndex() throws {
        let base = try temporaryDirectory("missing")
        defer { try? FileManager.default.removeItem(at: base) }
        let support = base.appendingPathComponent("Support")
        let library = base.appendingPathComponent("Visible Data")
        let paths = LibraryPaths(
            applicationSupportURL: support,
            defaultLibraryURL: library,
            libraryRootWasOverridden: false
        )
        let first = ProjectStore(paths: paths, automaticallyRestore: true, trashHandler: { _ in })
        try first.addAthlete(NewAthleteDraft(participantCode: "MISSING-01", dominantHand: .left))
        let moved = base.appendingPathComponent("Moved Data")
        try FileManager.default.moveItem(at: library, to: moved)

        // Without the sandbox, macOS can resolve a moved folder through its
        // bookmark. This fixture specifically tests an unavailable location,
        // so remove the recovery bookmark rather than assuming it cannot work.
        let indexURL = support.appendingPathComponent("library-location.json")
        var savedIndex = try JSONDecoder.projectDecoder.decode(LibraryLocationIndex.self, from: Data(contentsOf: indexURL))
        savedIndex.bookmarkData = nil
        try JSONEncoder.projectEncoder.encode(savedIndex).write(to: indexURL, options: .atomic)

        let second = ProjectStore(paths: paths, automaticallyRestore: true, trashHandler: { _ in })
        XCTAssertNil(second.project)
        XCTAssertEqual(second.missingLibraryURL?.standardizedFileURL.path, library.standardizedFileURL.path)
        XCTAssertTrue(FileManager.default.fileExists(atPath: moved.appendingPathComponent("project.json").path))
        try second.open(moved)
        XCTAssertEqual(second.project?.athletes.first?.participantCode, "MISSING-01")
    }

    @MainActor
    func testLegacyMigrationIsIdempotentAndDoesNotModifySource() throws {
        let base = try temporaryDirectory("migration")
        defer { try? FileManager.default.removeItem(at: base) }
        let source = base.appendingPathComponent("Legacy.cornholeproject")
        try FileManager.default.createDirectory(at: source.appendingPathComponent("videos"), withIntermediateDirectories: true)
        let athlete = Athlete(participantCode: "LEGACY-01", dominantHand: .right, notes: "")
        let video = source.appendingPathComponent("videos/throw.mov")
        try Data("original-video".utf8).write(to: video)
        let trial = Trial(
            athleteID: athlete.id, sourceVideoRelativePath: "videos/throw.mov", originalFilename: "throw.mov",
            cameraView: .side, throwingSide: .right, targetDirection: .leftToRight, isReference: true
        )
        let legacy = StudyProject(schemaVersion: 1, name: "Legacy", athletes: [athlete], trials: [trial])
        try JSONEncoder.projectEncoder.encode(legacy).write(
            to: source.appendingPathComponent("project.json"), options: .atomic
        )
        let originalProject = try Data(contentsOf: source.appendingPathComponent("project.json"))
        let originalVideo = try Data(contentsOf: video)
        let paths = LibraryPaths(
            applicationSupportURL: base.appendingPathComponent("Support"),
            defaultLibraryURL: base.appendingPathComponent("Managed"),
            libraryRootWasOverridden: false
        )
        let store = ProjectStore(paths: paths, automaticallyRestore: true, trashHandler: { _ in })
        let first = try store.importLegacyProject(at: source)
        let second = try store.importLegacyProject(at: source)

        XCTAssertEqual(first.athletesImported, 1)
        XCTAssertEqual(first.trialsImported, 1)
        XCTAssertTrue(second.wasAlreadyImported)
        XCTAssertEqual(store.project?.athletes.filter { $0.id == athlete.id }.count, 1)
        XCTAssertEqual(store.project?.trials.filter { $0.id == trial.id }.count, 1)
        XCTAssertEqual(store.project?.referenceSets.first?.provenance, "legacy_isReference_migration")
        XCTAssertEqual(try Data(contentsOf: source.appendingPathComponent("project.json")), originalProject)
        XCTAssertEqual(try Data(contentsOf: video), originalVideo)
    }

    @MainActor
    func testDeletingAnalysisPreservesSourceVideoAndThrowRecord() throws {
        let base = try temporaryDirectory("delete-analysis")
        defer { try? FileManager.default.removeItem(at: base) }
        let paths = LibraryPaths(
            applicationSupportURL: base.appendingPathComponent("Support"),
            defaultLibraryURL: base.appendingPathComponent("Managed"),
            libraryRootWasOverridden: false
        )
        let store = ProjectStore(
            paths: paths, automaticallyRestore: true,
            trashHandler: { try FileManager.default.removeItem(at: $0) }
        )
        try store.addAthlete(NewAthleteDraft(participantCode: "DELETE-01", dominantHand: .right))
        let source = base.appendingPathComponent("source.mov")
        try Data("video".utf8).write(to: source)
        var trial = try store.importVideo(ImportDraft(videoURL: source, athleteID: store.selectedAthleteID))
        let analysis = try store.analysisOutput(for: trial)
        try FileManager.default.createDirectory(at: analysis.url, withIntermediateDirectories: true)
        try Data("derived".utf8).write(to: analysis.url.appendingPathComponent("results.json"))
        try store.markAnalysisComplete(trialID: trial.id, relativePath: analysis.relativePath)
        trial = try XCTUnwrap(store.project?.trials.first { $0.id == trial.id })
        let reference = try store.addReferenceSet(name: "Keep assignment", scope: .global, athleteID: nil)
        try store.assign(trial, to: reference)
        let managedVideo = try XCTUnwrap(store.videoURL(for: trial))

        try store.deleteAnalysis(for: trial)
        XCTAssertTrue(FileManager.default.fileExists(atPath: managedVideo.path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: analysis.url.path))
        XCTAssertNotNil(store.project?.trials.first { $0.id == trial.id })
        XCTAssertNil(store.project?.trials.first { $0.id == trial.id }?.analysisRelativePath)
        XCTAssertTrue(store.project?.referenceSets.first { $0.id == reference.id }?.trialIDs.contains(trial.id) == true)
    }

    @MainActor
    func testReferenceAssignmentRemovalNeverDeletesSourceThrow() throws {
        let base = try temporaryDirectory("reference")
        defer { try? FileManager.default.removeItem(at: base) }
        let paths = LibraryPaths(
            applicationSupportURL: base.appendingPathComponent("Support"),
            defaultLibraryURL: base.appendingPathComponent("Managed"),
            libraryRootWasOverridden: false
        )
        let store = ProjectStore(paths: paths, automaticallyRestore: true, trashHandler: { _ in })
        try store.addAthlete(NewAthleteDraft(participantCode: "REF-01", dominantHand: .right))
        let source = base.appendingPathComponent("source.mov")
        try Data("video".utf8).write(to: source)
        let trial = try store.importVideo(ImportDraft(videoURL: source, athleteID: store.selectedAthleteID))
        let set = try store.addReferenceSet(name: "Personal baseline", scope: .athlete, athleteID: trial.athleteID)
        try store.assign(trial, to: set)
        try store.remove(trial, from: set)
        XCTAssertNotNil(store.project?.trials.first { $0.id == trial.id })
        XCTAssertTrue(store.videoState(for: trial).isAvailable)
        XCTAssertFalse(store.project?.trials.first { $0.id == trial.id }?.isReference ?? true)
    }

}
