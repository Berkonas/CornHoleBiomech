import Foundation

let applicationName = "Cornhole Biomechanics Lab"
let applicationVersion = "0.3.0"
let currentProjectSchemaVersion = 2

enum AppSection: String, CaseIterable, Identifiable {
    case overview = "Overview"
    case athletes = "Athletes"
    case reference = "References"
    case trials = "Throws"
    case compare = "Compare"
    case results = "Results"

    var id: String { rawValue }
    var symbol: String {
        switch self {
        case .overview: "square.grid.2x2"
        case .athletes: "person.2"
        case .reference: "scope"
        case .trials: "video"
        case .compare: "rectangle.split.2x1"
        case .results: "chart.xyaxis.line"
        }
    }
}

enum ThrowingSide: String, Codable, CaseIterable, Identifiable {
    case right, left
    var id: String { rawValue }
    var label: String { rawValue.capitalized }
}

enum CameraView: String, Codable, CaseIterable, Identifiable {
    case side, front, other
    var id: String { rawValue }
    var label: String { self == .other ? "Other / Exploratory" : rawValue.capitalized }
}

enum TargetDirection: String, Codable, CaseIterable, Identifiable {
    case leftToRight = "left_to_right"
    case rightToLeft = "right_to_left"
    var id: String { rawValue }
    var label: String { self == .leftToRight ? "Left to Right" : "Right to Left" }
}

enum ScoreCategory: Int, Codable, CaseIterable, Identifiable {
    case offBoard = 0
    case onBoard = 1
    case throughHole = 3
    var id: Int { rawValue }
    var label: String {
        switch self {
        case .offBoard: "0 - Off board / foul"
        case .onBoard: "1 - On board"
        case .throughHole: "3 - Through hole"
        }
    }
}

struct BoardPoint: Codable, Equatable, Hashable {
    var xInches: Double
    var yInches: Double
    var precision: String = "approximate_manual_click"

    enum CodingKeys: String, CodingKey {
        case xInches = "x_inches"
        case yInches = "y_inches"
        case precision
    }
}

struct TrialOutcome: Codable, Equatable, Hashable {
    var intendedTarget = "Hole center"
    var scoreCategory: ScoreCategory = .offBoard
    var throwType = "Standard"
    var notes = ""
    var intendedPoint: BoardPoint?
    var firstContactPoint: BoardPoint?
    var finalRestingPoint: BoardPoint?

    enum CodingKeys: String, CodingKey {
        case intendedTarget = "intended_target"
        case scoreCategory = "score_category"
        case throwType = "throw_type"
        case notes
        case intendedPoint = "intended_point"
        case firstContactPoint = "first_contact_point"
        case finalRestingPoint = "final_resting_point"
    }
}

struct Athlete: Codable, Identifiable, Hashable {
    var id: UUID = UUID()
    var participantCode: String
    var dominantHand: ThrowingSide
    var heightCentimeters: Double?
    var armSpanCentimeters: Double?
    var notes: String

    var displayName: String { participantCode.isEmpty ? "Unnamed participant" : participantCode }
}

struct Trial: Codable, Identifiable, Hashable {
    var id: UUID = UUID()
    var athleteID: UUID
    var createdAt: Date = Date()
    var sourceVideoRelativePath: String
    var originalFilename: String
    var sourceURL: String?
    var sourceAttribution: String?
    var cameraView: CameraView
    var throwingSide: ThrowingSide
    var targetDirection: TargetDirection
    var outcome: TrialOutcome?
    var isReference = false
    var analysisRelativePath: String?
    var analysisStatus = "Not analyzed"
    var sessionID: UUID?
    var name: String?

    var shortID: String { String(id.uuidString.prefix(8)) }
    var displayName: String {
        let trimmed = name?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return trimmed.isEmpty ? originalFilename : trimmed
    }

    enum CodingKeys: String, CodingKey {
        case id, athleteID, createdAt, sourceVideoRelativePath, originalFilename, sourceURL, sourceAttribution
        case cameraView, throwingSide, targetDirection, outcome, isReference, analysisRelativePath, analysisStatus
        case sessionID, name
    }

    init(
        id: UUID = UUID(), athleteID: UUID, createdAt: Date = Date(), sourceVideoRelativePath: String,
        originalFilename: String, sourceURL: String? = nil, sourceAttribution: String? = nil,
        cameraView: CameraView, throwingSide: ThrowingSide, targetDirection: TargetDirection,
        outcome: TrialOutcome? = nil, isReference: Bool = false, analysisRelativePath: String? = nil,
        analysisStatus: String = "Not analyzed", sessionID: UUID? = nil, name: String? = nil
    ) {
        self.id = id
        self.athleteID = athleteID
        self.createdAt = createdAt
        self.sourceVideoRelativePath = sourceVideoRelativePath
        self.originalFilename = originalFilename
        self.sourceURL = sourceURL
        self.sourceAttribution = sourceAttribution
        self.cameraView = cameraView
        self.throwingSide = throwingSide
        self.targetDirection = targetDirection
        self.outcome = outcome
        self.isReference = isReference
        self.analysisRelativePath = analysisRelativePath
        self.analysisStatus = analysisStatus
        self.sessionID = sessionID
        self.name = name
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decodeIfPresent(UUID.self, forKey: .id) ?? UUID()
        athleteID = try c.decode(UUID.self, forKey: .athleteID)
        createdAt = try c.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date()
        sourceVideoRelativePath = try c.decode(String.self, forKey: .sourceVideoRelativePath)
        originalFilename = try c.decodeIfPresent(String.self, forKey: .originalFilename)
            ?? URL(fileURLWithPath: sourceVideoRelativePath).lastPathComponent
        sourceURL = try c.decodeIfPresent(String.self, forKey: .sourceURL)
        sourceAttribution = try c.decodeIfPresent(String.self, forKey: .sourceAttribution)
        cameraView = try c.decodeIfPresent(CameraView.self, forKey: .cameraView) ?? .side
        throwingSide = try c.decodeIfPresent(ThrowingSide.self, forKey: .throwingSide) ?? .right
        targetDirection = try c.decodeIfPresent(TargetDirection.self, forKey: .targetDirection) ?? .leftToRight
        outcome = try c.decodeIfPresent(TrialOutcome.self, forKey: .outcome)
        isReference = try c.decodeIfPresent(Bool.self, forKey: .isReference) ?? false
        analysisRelativePath = try c.decodeIfPresent(String.self, forKey: .analysisRelativePath)
        analysisStatus = try c.decodeIfPresent(String.self, forKey: .analysisStatus) ?? (analysisRelativePath == nil ? "Not analyzed" : "Analyzed")
        sessionID = try c.decodeIfPresent(UUID.self, forKey: .sessionID)
        name = try c.decodeIfPresent(String.self, forKey: .name)
    }
}

struct AnalysisSettings: Codable, Equatable {
    var poseBackend: String? = "sports2d"
    var poseModel: String? = "body_with_feet"
    var poseMode: String? = "balanced"
    var confidenceThreshold = 0.35
    var maxInterpolationGapFrames = 3
    var filterEnabled = true
    var filterOrder = 4
    var filterCutoffHz = 6.0
    var normalizationSamples = 101
    var minimumRelationshipTrials = 8

    var pythonPayload: [String: Any] {
        [
            "sports2d": ["pose_model": poseModel ?? "body_with_feet", "mode": poseMode ?? "balanced"],
            "confidence_threshold": confidenceThreshold,
            "max_interpolation_gap_frames": maxInterpolationGapFrames,
            "filter": [
                "enabled": filterEnabled,
                "type": filterEnabled ? "butterworth_zero_phase" : "none",
                "order": filterOrder,
                "cutoff_hz": filterCutoffHz,
            ],
            "normalization_samples": normalizationSamples,
            "minimum_relationship_trials": minimumRelationshipTrials,
        ]
    }
}

enum ReferenceScope: String, Codable, CaseIterable, Identifiable {
    case global
    case athlete
    var id: String { rawValue }
    var label: String { self == .global ? "Global" : "Athlete-specific" }
}

struct ReferenceSet: Codable, Identifiable, Hashable {
    var id = UUID()
    var name: String
    var scope: ReferenceScope = .global
    var athleteID: UUID?
    var trialIDs: [UUID] = []
    var provenance: String = "coach_selected"
    var notes: String = ""
    var createdAt = Date()
}

struct StudyProject: Codable {
    var schemaVersion = currentProjectSchemaVersion
    var appVersion = applicationVersion
    var id: UUID = UUID()
    var name: String
    var createdAt: Date = Date()
    var updatedAt: Date = Date()
    var athletes: [Athlete] = []
    var trials: [Trial] = []
    var analysisSettings = AnalysisSettings()
    var sessions: [RecordingSession]? = []
    var referenceSets: [ReferenceSet] = []

    enum CodingKeys: String, CodingKey {
        case schemaVersion, appVersion, id, name, createdAt, updatedAt, athletes, trials, analysisSettings, sessions, referenceSets
    }

    init(
        schemaVersion: Int = currentProjectSchemaVersion, appVersion: String = applicationVersion,
        id: UUID = UUID(), name: String, createdAt: Date = Date(), updatedAt: Date = Date(),
        athletes: [Athlete] = [], trials: [Trial] = [], analysisSettings: AnalysisSettings = AnalysisSettings(),
        sessions: [RecordingSession]? = [], referenceSets: [ReferenceSet] = []
    ) {
        self.schemaVersion = schemaVersion
        self.appVersion = appVersion
        self.id = id
        self.name = name
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.athletes = athletes
        self.trials = trials
        self.analysisSettings = analysisSettings
        self.sessions = sessions
        self.referenceSets = referenceSets
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try c.decodeIfPresent(Int.self, forKey: .schemaVersion) ?? 1
        appVersion = try c.decodeIfPresent(String.self, forKey: .appVersion) ?? "unknown"
        id = try c.decodeIfPresent(UUID.self, forKey: .id) ?? UUID()
        name = try c.decodeIfPresent(String.self, forKey: .name) ?? "Imported Cornhole Study"
        createdAt = try c.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date()
        updatedAt = try c.decodeIfPresent(Date.self, forKey: .updatedAt) ?? createdAt
        athletes = try c.decodeIfPresent([Athlete].self, forKey: .athletes) ?? []
        trials = try c.decodeIfPresent([Trial].self, forKey: .trials) ?? []
        analysisSettings = try c.decodeIfPresent(AnalysisSettings.self, forKey: .analysisSettings) ?? AnalysisSettings()
        sessions = try c.decodeIfPresent([RecordingSession].self, forKey: .sessions) ?? []
        referenceSets = try c.decodeIfPresent([ReferenceSet].self, forKey: .referenceSets) ?? []
    }
}

struct ImportDraft {
    var videoURL: URL
    var athleteID: UUID?
    var cameraView: CameraView = .side
    var throwingSide: ThrowingSide = .right
    var targetDirection: TargetDirection = .leftToRight
    var sourceURL = ""
    var sourceAttribution = ""
    var sessionID: UUID?
    var isReference = false
}

struct NewAthleteDraft {
    var participantCode = ""
    var dominantHand: ThrowingSide = .right
    var height = ""
    var armSpan = ""
    var notes = ""
}

struct PosePoint: Codable, Equatable {
    var x: Double?
    var y: Double?
    var confidence: Double
}

struct PoseFrame: Codable, Identifiable {
    var frameIndex: Int
    var timeSeconds: Double
    var landmarks: [String: PosePoint]
    var id: Int { frameIndex }

    enum CodingKeys: String, CodingKey {
        case frameIndex = "frame_index"
        case timeSeconds = "time_seconds"
        case landmarks
    }
}

struct PoseDocument: Codable {
    var fps: Double
    var width: Int
    var height: Int
    var frameCount: Int
    var backend: String
    var modelName: String
    var frames: [PoseFrame]

    enum CodingKeys: String, CodingKey {
        case fps, width, height, backend, frames
        case frameCount = "frame_count"
        case modelName = "model_name"
    }
}

struct PointCorrection: Codable, Equatable {
    var frameIndex: Int
    var landmark: String
    var x: Double
    var y: Double
    var kind = "manual"
    var createdAt = ISO8601DateFormatter().string(from: Date())

    enum CodingKeys: String, CodingKey {
        case frameIndex = "frame_index"
        case landmark, x, y, kind
        case createdAt = "created_at"
    }
}

struct CorrectionDocument: Codable {
    var schemaVersion = 1
    var corrections: [PointCorrection] = []
    enum CodingKeys: String, CodingKey { case schemaVersion = "schema_version", corrections }
    init() {}
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try c.decodeIfPresent(Int.self, forKey: .schemaVersion) ?? 1
        corrections = try c.decode([PointCorrection].self, forKey: .corrections)
    }
}

struct BagSeedDocument: Codable, Equatable {
    var frameIndex: Int
    var bboxXYWH: [Double]
    var source = "manual_bbox"

    enum CodingKeys: String, CodingKey {
        case frameIndex = "frame_index"
        case bboxXYWH = "bbox_xywh"
        case source
    }
}

struct BagPointCorrection: Codable, Equatable {
    var frameIndex: Int
    var x: Double
    var y: Double
    var kind = "manual"
    var createdAt = ISO8601DateFormatter().string(from: Date())

    enum CodingKeys: String, CodingKey {
        case frameIndex = "frame_index"
        case x, y, kind
        case createdAt = "created_at"
    }
}

struct BagCorrectionDocument: Codable {
    var schemaVersion = 1
    var corrections: [BagPointCorrection] = []
    var reviewedThroughFrame: Int?
    var reviewedAt: String?
    var reviewNote: String?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case corrections
        case reviewedThroughFrame = "reviewed_through_frame"
        case reviewedAt = "reviewed_at"
        case reviewNote = "review_note"
    }

    init() {}

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(Int.self, forKey: .schemaVersion) ?? 1
        corrections = try container.decodeIfPresent([BagPointCorrection].self, forKey: .corrections) ?? []
        reviewedThroughFrame = try container.decodeIfPresent(Int.self, forKey: .reviewedThroughFrame)
        reviewedAt = try container.decodeIfPresent(String.self, forKey: .reviewedAt)
        reviewNote = try container.decodeIfPresent(String.self, forKey: .reviewNote)
    }
}

struct BagTrackDocument: Codable {
    struct Centroid: Codable, Equatable {
        var x: Double
        var y: Double
        var confidence: Double?
    }
    struct Sample: Codable, Identifiable {
        var frameIndex: Int
        var automaticCentroid: Centroid?
        var effectiveCentroid: Centroid?
        var filteredCentroid: Centroid?
        var provenance: String
        var id: Int { frameIndex }

        enum CodingKeys: String, CodingKey {
            case frameIndex = "frame_index"
            case automaticCentroid = "automatic_centroid"
            case effectiveCentroid = "effective_centroid"
            case filteredCentroid = "filtered_centroid"
            case provenance
        }
    }
    struct Tracker: Codable {
        var requestedMethod: String
        var effectiveMethod: String
        var status: String
        var fallbackReason: String?
        var failureFrames: [Int]
        var qualityNote: String

        enum CodingKeys: String, CodingKey {
            case requestedMethod = "requested_method"
            case effectiveMethod = "effective_method"
            case status
            case fallbackReason = "fallback_reason"
            case failureFrames = "failure_frames"
            case qualityNote = "quality_note"
        }
    }

    var schemaVersion: Int
    var coordinateSystem: String
    var units: String
    var tracker: Tracker
    var seed: BagSeedDocument
    var corrections: BagCorrectionDocument
    var samples: [Sample]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case coordinateSystem = "coordinate_system"
        case units, tracker, seed, corrections, samples
    }
}

struct AnalysisResults: Codable {
    struct Quality: Codable {
        var score: Double?
        var releaseVisibility: Double?
        var releaseConfidence: Double?
        var scoreNote: String?
        var averagePoseConfidence: Double?
        var usableFramePercentage: Double
        var missingDataPercentage: Double
        var lowConfidenceLandmarkCounts: [String: Int]
        var manualCorrectionCount: Int
        var interpolatedSampleCount: Int
        var frameRateFPS: Double
        var resolutionPixels: Resolution
        var cameraView: String
        var warnings: [String]
        var confidenceNote: String

        struct Resolution: Codable { var width: Int; var height: Int }
        enum CodingKeys: String, CodingKey {
            case score
            case releaseVisibility = "release_visibility"
            case releaseConfidence = "release_confidence"
            case scoreNote = "score_note"
            case averagePoseConfidence = "average_pose_confidence"
            case usableFramePercentage = "usable_frame_percentage"
            case missingDataPercentage = "missing_data_percentage"
            case lowConfidenceLandmarkCounts = "low_confidence_landmark_counts"
            case manualCorrectionCount = "manual_correction_count"
            case interpolatedSampleCount = "interpolated_sample_count"
            case frameRateFPS = "frame_rate_fps"
            case resolutionPixels = "resolution_pixels"
            case cameraView = "camera_view"
            case warnings
            case confidenceNote = "confidence_note"
        }
    }

    struct Event: Codable {
        var name: String
        var automaticFrame: Int?
        var automaticConfidence: Double?
        var automaticMethod: String?
        var manualFrame: Int?
        var effectiveFrame: Int?
        enum CodingKeys: String, CodingKey {
            case name
            case automaticFrame = "automatic_frame"
            case automaticConfidence = "automatic_confidence"
            case automaticMethod = "automatic_method"
            case manualFrame = "manual_frame"
            case effectiveFrame = "effective_frame"
        }
    }

    struct BagAnalysis: Codable {
        struct Review: Codable {
            var reviewedThroughFrame: Int?
            var requiredThroughFrameForLaunch: Int?
            var coversLaunchFit: Bool
            var reviewedAt: String?
            var note: String?

            enum CodingKeys: String, CodingKey {
                case reviewedThroughFrame = "reviewed_through_frame"
                case requiredThroughFrameForLaunch = "required_through_frame_for_launch"
                case coversLaunchFit = "covers_launch_fit"
                case reviewedAt = "reviewed_at"
                case note
            }
        }
        struct Tracker: Codable {
            var requestedMethod: String
            var effectiveMethod: String
            var status: String
            var fallbackReason: String?
            var failureFrames: [Int]

            enum CodingKeys: String, CodingKey {
                case requestedMethod = "requested_method"
                case effectiveMethod = "effective_method"
                case status
                case fallbackReason = "fallback_reason"
                case failureFrames = "failure_frames"
            }
        }
        struct Launch: Codable {
            struct Velocity: Codable {
                var forwardPixelsPerSecond: Double?
                var verticalPixelsPerSecond: Double?
                var speedPixelsPerSecond: Double?
                var angleDegrees: Double?
                var forwardArmLengthsPerSecond: Double?
                var verticalArmLengthsPerSecond: Double?
                var speedArmLengthsPerSecond: Double?

                enum CodingKeys: String, CodingKey {
                    case forwardPixelsPerSecond = "forward_px_s"
                    case verticalPixelsPerSecond = "vertical_px_s"
                    case speedPixelsPerSecond = "speed_px_s"
                    case angleDegrees = "angle_deg"
                    case forwardArmLengthsPerSecond = "forward_arm_lengths_s"
                    case verticalArmLengthsPerSecond = "vertical_arm_lengths_s"
                    case speedArmLengthsPerSecond = "speed_arm_lengths_s"
                }
            }
            struct PhysicalUnits: Codable {
                var status: String
            }
            var status: String
            var releaseFrame: Int?
            var velocity: Velocity?
            var physicalUnits: PhysicalUnits

            enum CodingKeys: String, CodingKey {
                case status
                case releaseFrame = "release_frame"
                case velocity
                case physicalUnits = "physical_units"
            }
        }

        var automaticTrackingCoveragePercent: Double
        var effectiveTrackingCoveragePercent: Double
        var medianAutomaticQuality: Double?
        var manualCorrectionCount: Int
        var interpolatedSampleCount: Int
        var review: Review?
        var tracker: Tracker
        var launch: Launch
        var qualityNote: String

        enum CodingKeys: String, CodingKey {
            case automaticTrackingCoveragePercent = "automatic_tracking_coverage_percent"
            case effectiveTrackingCoveragePercent = "effective_tracking_coverage_percent"
            case medianAutomaticQuality = "median_automatic_quality"
            case manualCorrectionCount = "manual_correction_count"
            case interpolatedSampleCount = "interpolated_sample_count"
            case review, tracker, launch
            case qualityNote = "quality_note"
        }
    }

    var trialID: String
    var athleteID: String
    var summaries: [String: Double?]
    var quality: Quality
    var bag: BagAnalysis?
    var events: [String: Event]
    var warnings: [String]
    var claimScope: String

    enum CodingKeys: String, CodingKey {
        case trialID = "trial_id"
        case athleteID = "athlete_id"
        case summaries, quality, bag, events, warnings
        case claimScope = "claim_scope"
    }
}

struct EventDocument: Codable {
    struct Entry: Codable {
        var name: String
        var automaticFrame: Int?
        var automaticConfidence: Double?
        var automaticMethod: String?
        var manualFrame: Int?
        var effectiveFrame: Int?

        enum CodingKeys: String, CodingKey {
            case name
            case automaticFrame = "automatic_frame"
            case automaticConfidence = "automatic_confidence"
            case automaticMethod = "automatic_method"
            case manualFrame = "manual_frame"
            case effectiveFrame = "effective_frame"
        }
    }

    var schemaVersion = 1
    var frameIntervalSeconds: Double?
    var releasePrecisionNote: String?
    var events: [String: Entry]
    var manualOverrides: [String: Int?]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case frameIntervalSeconds = "frame_interval_seconds"
        case releasePrecisionNote = "release_precision_note"
        case events
        case manualOverrides = "manual_overrides"
    }
}

struct NormalizedDocument: Codable {
    var trialID: String
    var athleteID: String
    var cameraView: String
    var tau: [Double]
    var values: [String: FlexibleNumericArray]
    var eventTiming: [String: Double?]
    enum CodingKeys: String, CodingKey {
        case trialID = "trial_id"
        case athleteID = "athlete_id"
        case cameraView = "camera_view"
        case tau, values
        case eventTiming = "event_timing"
    }
}

enum FlexibleNumericArray: Codable {
    case scalar([Double?])
    case vector([[Double?]])

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let value = try? container.decode([Double?].self) { self = .scalar(value); return }
        self = .vector(try container.decode([[Double?]].self))
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .scalar(let value): try container.encode(value)
        case .vector(let value): try container.encode(value)
        }
    }
}

extension FlexibleNumericArray {
    var scalars: [Double?]? { if case .scalar(let values) = self { return values }; return nil }
    var vectors: [[Double?]]? { if case .vector(let values) = self { return values }; return nil }
}

struct ComparisonDocument: Codable {
    struct Curves: Codable {
        var tau: [Double]
        var test: [String: FlexibleNumericArray]
        var referenceMean: [String: FlexibleNumericArray]
        var referenceSD: [String: FlexibleNumericArray]
        enum CodingKeys: String, CodingKey {
            case tau, test
            case referenceMean = "reference_mean"
            case referenceSD = "reference_sd"
        }
    }
    struct Similarity: Codable {
        struct Component: Codable, Identifiable {
            var rawError: Double
            var tolerance: Double
            var weight: Double
            var score: Double
            var formula: String
            var id = UUID()
            enum CodingKeys: String, CodingKey {
                case rawError = "raw_error"
                case tolerance, weight, score, formula
            }
        }
        var overall: Double?
        var components: [String: Component]
        var omittedComponents: [String]
        var interpretation: String
        enum CodingKeys: String, CodingKey {
            case overall, components, interpretation
            case omittedComponents = "omitted_components"
        }
    }
    var testTrialID: String
    var referenceTrialIDs: [String]
    var cameraView: String
    var label: String
    var rawMetrics: [String: Double?]
    var similarity: Similarity
    var curves: Curves?
    var testEventTiming: [String: Double?]?
    var referenceEventTiming: [String: Double?]?
    var claimScope: String
    enum CodingKeys: String, CodingKey {
        case testTrialID = "test_trial_id"
        case referenceTrialIDs = "reference_trial_ids"
        case cameraView = "camera_view"
        case label
        case rawMetrics = "raw_metrics"
        case similarity, curves
        case testEventTiming = "test_event_timing"
        case referenceEventTiming = "reference_event_timing"
        case claimScope = "claim_scope"
    }
}

struct RelationshipDocument: Codable {
    struct DataRow: Codable, Identifiable {
        var trialID: String
        var scoreCategory: Double?
        var radialErrorInches: Double?
        var elbowAngleAtRelease: Double?
        var elbowROM: Double?
        var trunkInclinationAtRelease: Double?
        var movementDuration: Double?
        var releaseTimingCycle: Double?
        var referenceSimilarityScore: Double?
        var wristReferenceDeviation: Double?
        var wristAthleteMeanDeviation: Double?
        var id: String { trialID }
        enum CodingKeys: String, CodingKey {
            case trialID = "trial_id"
            case scoreCategory = "score_category"
            case radialErrorInches = "radial_error_inches"
            case elbowAngleAtRelease = "elbow_angle_deg_at_release"
            case elbowROM = "elbow_angle_deg_rom"
            case trunkInclinationAtRelease = "trunk_inclination_deg_at_release"
            case movementDuration = "movement_duration_seconds"
            case releaseTimingCycle = "release_timing_cycle"
            case referenceSimilarityScore = "reference_similarity_score"
            case wristReferenceDeviation = "wrist_reference_deviation_arm_lengths"
            case wristAthleteMeanDeviation = "wrist_path_deviation_from_athlete_mean_arm_lengths"
        }
    }
    struct Consistency: Codable {
        var n: Int
        var mean: Double?
        var standardDeviation: Double?
        var median: Double?
        var range: Double?
        var units: String
        enum CodingKeys: String, CodingKey {
            case n, mean, median, range, units
            case standardDeviation = "standard_deviation"
        }
    }
    struct Estimate: Codable {
        var n: Int
        var status: String
        var message: String
        var spearmanRho: Double?
        var spearmanPValue: Double?
        var confidenceInterval: [Double?]?
        enum CodingKeys: String, CodingKey {
            case n, status, message
            case spearmanRho = "spearman_rho"
            case spearmanPValue = "spearman_p_value_exploratory"
            case confidenceInterval = "spearman_bootstrap_95_ci"
        }
    }
    var athleteID: String?
    var trialCount: Int
    var outcomeVariable: String
    var relationships: [String: Estimate]
    var withinAthleteConsistency: [String: Consistency]?
    var dataRows: [DataRow]?
    var claimScope: String
    enum CodingKeys: String, CodingKey {
        case athleteID = "athlete_id"
        case trialCount = "trial_count"
        case outcomeVariable = "outcome_variable"
        case relationships
        case withinAthleteConsistency = "within_athlete_consistency"
        case dataRows = "data_rows"
        case claimScope = "claim_scope"
    }
}

extension JSONEncoder {
    static var projectEncoder: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }
}

extension JSONDecoder {
    static var projectDecoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }
}

struct RecordingSession: Codable, Identifiable, Hashable {
    var id = UUID()
    var athleteID: UUID
    var name: String
    var date = Date()
    var cameraSetup: String
    var cameraView: CameraView = .side
    var throwingSide: ThrowingSide = .right
    var targetDirection: TargetDirection = .leftToRight
    var notes: String = ""
    var referenceTrialIDs: [UUID] = []
}
