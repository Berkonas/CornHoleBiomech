import Foundation

/// Turns a body measure that differed from the athlete's throws that went in into a coaching cue: a biomechanical
/// reason in plain words, what to do, and whether the difference points the same way as this throw's miss (the
/// mechanism that would link them). Associations from the athlete's own throws, never a proven cause.
struct BodyCue: Equatable {
    var reason: String
    var fix: String
    /// The difference is the kind that would produce this throw's miss (e.g. a slower swing on a short throw).
    var fitsMiss: Bool

    /// - Parameters:
    ///   - missAlong: − short / + long (in), nil when unknown; missAcross: − left / + right (in).
    ///   - angleChange: the launch-angle change (°) that would have fixed the distance (+ higher, − flatter), from the
    ///     drag-free flight; nil when the angle barely moves the landing for this release. Only then does a higher or
    ///     flatter release "fit" the miss.
    static func make(_ change: ThrowAttribution.Fix.BodyChange, missAlong: Double?, missAcross: Double?,
                     angleChange: Double? = nil) -> BodyCue? {
        guard let value = change.value, let target = change.target else { return nil }
        let more = value > target                       // this throw had more of it than the throws that went in
        let v = WhyItMissedCard.value(value, change.unit), t = WhyItMissedCard.value(target, change.unit)
        let short = (missAlong ?? 0) <= -3, long = (missAlong ?? 0) >= 3, sideways = abs(missAcross ?? 0) >= 3
        func distance(_ moreSpeed: Bool) -> Bool { moreSpeed ? long : short }   // does "more speed" fit the miss?
        // Does a higher (true) or flatter (false) release fit? Only when flatter/higher would have fixed the distance.
        func launch(_ higher: Bool) -> Bool { angleChange.map { higher ? $0 < 0 : $0 > 0 } ?? false }
        switch change.key {
        case "swing_forward_duration_s":
            return BodyCue(reason: "The forward swing took \(v) (\(t) on throws that went in): a \(more ? "slower" : "quicker") arm swing gives \(more ? "less" : "more") release speed.",
                           fix: more ? "Swing through a little quicker, about \(t) from the top of the backswing to release." : "Let the swing come through a touch slower and smoother.",
                           fitsMiss: distance(!more))
        case "swing_tempo_ratio":
            let vt = number(value, digits: 2), tt = number(target, digits: 2)
            return BodyCue(reason: "Tempo (backswing time ÷ forward swing time) was \(vt) vs \(tt): the rhythm of the swing changed.",
                           fix: more ? "Keep the same rhythm as your good throws: a slightly shorter backswing for the same swing (about \(tt))." : "Take the backswing a little slower, then swing through (rhythm about \(tt)).",
                           fitsMiss: false)
        case "swing_backswing_angle_deg":
            // More negative = further behind the body.
            let bigger = value < target
            return BodyCue(reason: "The backswing reached \(v) (\(t) on throws that went in): a \(bigger ? "bigger" : "shorter") backswing gives \(bigger ? "more" : "less") speed.",
                           fix: bigger ? "Shorten the backswing a little (about \(t))." : "Take the arm a little further back (about \(t)) before swinging through.",
                           fitsMiss: distance(bigger))
        case "wrist_peak_speed_arm_lengths_s", "wrist_speed_at_release_arm_lengths_s":
            return BodyCue(reason: "The hand moved \(more ? "faster" : "slower") (\(v) vs \(t)): hand speed sets the bag's release speed.",
                           fix: more ? "Ease off slightly: a smoother, less forceful swing." : "Accelerate the arm through release a little more.",
                           fitsMiss: distance(more))
        case "swing_release_arm_angle_deg":
            return BodyCue(reason: "The arm was at \(v) from vertical when the bag left the hand (\(t) on throws that went in): the bag was let go \(more ? "later, higher in the swing" : "earlier, lower in the swing"), which changes its launch angle.",
                           fix: more ? "Let go of the bag a little earlier in the swing (arm about \(t))." : "Hold the bag a fraction longer and let go a little higher (arm about \(t)).",
                           fitsMiss: launch(more))
        case "wrist_direction_at_release_deg":
            return BodyCue(reason: "The hand was moving \(more ? "more upward" : "flatter") at release (\(v) vs \(t)), so the bag left on a \(more ? "higher" : "flatter") line.",
                           fix: more ? "Swing more toward the board and less upward at release." : "Lift through the release a little more (a slightly higher arc).",
                           fitsMiss: launch(more))
        case "elbow_angle_deg_at_release":
            return BodyCue(reason: "The elbow was \(more ? "straighter" : "more bent") at release (\(v) vs \(t)): a bent elbow shortens the lever and changes the release.",
                           fix: more ? "Keep the arm relaxed rather than locked at release." : "Keep the arm straighter through the swing (elbow about \(t)).",
                           fitsMiss: false)
        case "trunk_inclination_deg_at_release":
            return BodyCue(reason: "The trunk leaned \(more ? "further forward" : "less forward") at release (\(v) vs \(t)), moving where the bag is released.",
                           fix: more ? "Stay a little taller through the throw." : "Lean into the throw a little more (about \(t)).",
                           fitsMiss: false)
        case "arm_across_body_sw":
            return BodyCue(reason: "The hand \(more ? "crossed further toward the body's midline" : "swung further out") at release (\(v) vs \(t), front camera): the bag leaves on a line \(more ? "across" : "away from") the body.",
                           fix: "Keep the hand moving straight at the hole through release.", fitsMiss: sideways)
        case "hand_path_range_sw":
            return BodyCue(reason: "The hand drifted sideways more during the swing (\(v) vs \(t), front camera): the swing was not in one straight plane.",
                           fix: "Swing in a straight line, like a pendulum pointing at the hole.", fitsMiss: sideways && more)
        case "trunk_side_lean_deg", "trunk_lean_change_deg":
            return BodyCue(reason: "The trunk leaned \(more ? "more" : "less") to the side (\(v) vs \(t), front camera), shifting the shoulder and the swing line.",
                           fix: "Stay square and balanced over the front foot through release.", fitsMiss: sideways)
        default:
            return BodyCue(reason: "\(change.label) was \(v) (\(t) on throws that went in).", fix: "Aim for about \(t).", fitsMiss: false)
        }
    }
}
