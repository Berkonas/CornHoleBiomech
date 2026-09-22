"""Reviewed flight observations; no ballistic extrapolation or automatic scoring."""
from __future__ import annotations
import math
from typing import Any
import numpy as np

from .bag import GRAVITY_M_S2, _robust_polynomial

# Foot points that approximate floor contact, in order of preference. Sports2D
# (HALPE-26) names are "RHeel"/"LBigToe"; the RTMPose adapter uses snake case.
FOOT_POINTS = ("RHeel", "LHeel", "RBigToe", "LBigToe", "RSmallToe", "LSmallToe",
               "right_heel", "left_heel", "right_big_toe", "left_big_toe",
               "right_small_toe", "left_small_toe")
ANKLE_POINTS = ("right_ankle", "left_ankle")


def flight_summary(points, release_frame, contact_frame, fps, reviewed_through,
                   release_reviewed=False, camera_view='other', fixed_camera=False):
    """Frames are zero-based; bag centroids are unsmoothed image pixels.

    Contact is the first externally observed collision (board OR ground), not
    final rest. A video ending with an airborne bag never implies contact.
    """
    p = np.asarray(points, float)
    if p.ndim != 2 or p.shape[1] != 2 or not math.isfinite(fps) or fps <= 0:
        raise ValueError('Flight requires [frame,2] points and a positive finite fps')
    result: dict[str, Any] = dict(status='needs_review', classification='derived_from_reviewed_observations',
        release_frame=release_frame, first_contact_frame=contact_frame,
        time_of_flight_seconds=None, observed_apex_frame=None, observed_rise_pixels=None,
        horizontal_travel_pixels=None, coverage=0.0, trajectory=[],
        frame_interval_seconds=1/fps, timing_resolution_note='Two reviewed events: ±1 frame each gives a ±2/fps sensitivity bound, not a confidence interval.',
        message='Confirm release and first contact in the video. No landing is inferred from tracker loss.')
    if release_frame is None or not release_reviewed or contact_frame is None:
        return result
    if not (0 <= release_frame < contact_frame < len(p)):
        raise ValueError('First contact must follow release and both must lie inside the clip')
    result['time_of_flight_seconds'] = (contact_frame-release_frame)/fps
    result['status'] = 'events_reviewed'
    result['message'] = 'Flight time comes from reviewed events; bag identity must be reviewed separately for the trajectory.'
    if reviewed_through is None or reviewed_through < contact_frame:
        return result
    segment = p[release_frame:contact_frame+1]
    valid = np.isfinite(segment).all(axis=1)
    result['coverage'] = float(np.mean(valid))
    # Include explicit gaps so plots never join through unobserved intervals.
    result['trajectory'] = [dict(frame=release_frame+i, x=float(v[0]) if ok else None,
                                y=float(v[1]) if ok else None) for i,(v,ok) in enumerate(zip(segment,valid))]
    result['status'] = 'reviewed_track'
    result['message'] = 'Reviewed image-plane path. Missing points remain gaps; no depth, aerodynamic or landing extrapolation.'
    if valid.all() and fixed_camera and camera_view == 'side':
        apex = int(np.argmin(segment[:,1]))
        # Interior peak only: endpoint maxima do not prove the apex was observed.
        if 0 < apex < len(segment)-1:
            result['observed_apex_frame'] = release_frame+apex
            result['observed_rise_pixels'] = float(segment[0,1]-segment[apex,1])
        result['horizontal_travel_pixels'] = float(abs(segment[-1,0]-segment[0,0]))
    else:
        result['message'] += ' Apex/range withheld unless coverage is complete and a fixed side camera is confirmed.'
    return result


def gravity_scale_from_flight(points, release_frame, contact_frame, fps, fixed_camera, camera_view,
                              reference_pixels_per_meter=None, minimum_points=15, minimum_coverage=0.8):
    """Pixels per meter implied by the reviewed flight's vertical acceleration.

    A free bag accelerates downward at g, so the fitted image-down acceleration
    a (px/s²) gives s = a / g in the bag's own flight plane. Only frames strictly
    between release and first contact are used (no hand contact, no impact).

    Assumptions, each stated in the result: fixed camera; flight plane roughly
    perpendicular to the optical axis (side view); level camera; aerodynamic
    drag small relative to g (its vertical component opposes gravity on the
    way down and adds to it on the way up, so it partly cancels over an arc).
    With an independent scale, `apparent_gravity_m_s2` checks that scale: it
    should be close to 9.8 m/s².
    """
    result: dict[str, Any] = dict(
        status='needs_reviewed_events', pixels_per_meter=None, pixels_per_meter_se=None,
        vertical_acceleration_px_s2=None, horizontal_acceleration_px_s2=None, sample_count=0,
        coverage=0.0, fit_rmse_px=None, apparent_gravity_m_s2=None, scale_ratio_to_reference=None,
        assumptions='Fixed level side camera; flight plane perpendicular to the optical axis; drag small relative to gravity.')
    if not (fixed_camera and camera_view == 'side'):
        result['status'] = 'unsupported_camera'
        return result
    if release_frame is None or contact_frame is None or contact_frame - release_frame < 3:
        return result
    p = np.asarray(points, float)
    frames = np.arange(release_frame + 1, min(contact_frame, len(p)))
    segment = p[frames]
    valid = np.isfinite(segment).all(axis=1)
    result.update(sample_count=int(valid.sum()), coverage=float(valid.mean()) if len(valid) else 0.0)
    if valid.sum() < minimum_points or result['coverage'] < minimum_coverage:
        result['status'] = 'insufficient_flight_samples'
        return result
    t = (frames[valid] - release_frame) / fps
    coeff_y, res_y, cov_y = _robust_polynomial(t, segment[valid, 1], 2)
    coeff_x, res_x, _ = _robust_polynomial(t, segment[valid, 0], 2)
    down = 2.0 * float(coeff_y[2])
    result.update(vertical_acceleration_px_s2=down, horizontal_acceleration_px_s2=2.0 * float(coeff_x[2]),
                  fit_rmse_px=float(np.sqrt(np.mean(res_x**2 + res_y**2))))
    if down <= 0:
        result['status'] = 'implausible_curvature'
        return result
    result['pixels_per_meter'] = down / GRAVITY_M_S2
    if cov_y is not None:
        result['pixels_per_meter_se'] = 2.0 * math.sqrt(float(cov_y[2, 2])) / GRAVITY_M_S2
    if reference_pixels_per_meter:
        result['apparent_gravity_m_s2'] = down / float(reference_pixels_per_meter)
        result['scale_ratio_to_reference'] = result['pixels_per_meter'] / float(reference_pixels_per_meter)
    result['status'] = 'estimated'
    return result


def release_height(bag_points, landmarks, release_frame, arm_length_px, pixels_per_meter, window=3):
    """Bag height at release above the lowest visible foot point.

    The floor line is the per-frame lowest (largest image-y) heel/toe point,
    medianed over ±`window` frames around release so one lifted foot or one
    noisy frame does not move it. Ankles are a labelled fallback that sits
    roughly 7–9 cm above the floor. Assumes a level camera.
    """
    result = dict(height_px=None, height_arm_lengths=None, height_m=None, floor_reference=None)
    bag = np.asarray(bag_points, float)
    if release_frame is None or not 0 <= release_frame < len(bag) or not np.isfinite(bag[release_frame]).all():
        return result
    for names, label in ((FOOT_POINTS, 'lowest_heel_or_toe'), (ANKLE_POINTS, 'lowest_ankle')):
        present = [np.asarray(landmarks[n], float) for n in names if n in landmarks]
        if not present:
            continue
        lo, hi = max(0, release_frame - window), min(len(bag), release_frame + window + 1)
        ys = np.stack([p[lo:hi, 1] for p in present])
        with np.errstate(all='ignore'):
            per_frame = np.nanmax(np.where(np.isfinite(ys), ys, -np.inf), axis=0)
        per_frame = per_frame[np.isfinite(per_frame)]
        if not per_frame.size:
            continue
        height = float(np.median(per_frame) - bag[release_frame, 1])
        result.update(height_px=height, floor_reference=label)
        if arm_length_px and arm_length_px > 0:
            result['height_arm_lengths'] = height / arm_length_px
        if pixels_per_meter and pixels_per_meter > 0:
            result['height_m'] = height / pixels_per_meter
        return result
    return result


def landing_dispersion(outcomes, endpoint='first_contact_point'):
    """Grouping is RMS distance from centroid, independent of target accuracy.

    Board-only samples are conditional on visible deck contacts; never fabricate
    coordinates for ground misses or hole entries. Report that selection bias.
    """
    points = [o[endpoint] for o in outcomes if o.get(endpoint)]
    a = np.array([[p['x_inches'],p['y_inches']] for p in points], float).reshape(-1,2)
    a = a[np.isfinite(a).all(axis=1)]
    result = dict(endpoint=endpoint,n=len(a),missing=len(outcomes)-len(a),centroid=None,
                  rms_radius_inches=None,lateral_sd_inches=None,longitudinal_sd_inches=None,
                  note='Visible board-plane points only; excludes unlocated misses. Grouping is not target accuracy.')
    if len(a): result['centroid'] = dict(x_inches=float(a[:,0].mean()),y_inches=float(a[:,1].mean()))
    if len(a)>1:
        result.update(rms_radius_inches=float(np.sqrt(np.mean(np.sum((a-a.mean(axis=0))**2,axis=1)))),
                      lateral_sd_inches=float(a[:,0].std(ddof=1)),longitudinal_sd_inches=float(a[:,1].std(ddof=1)))
    return result


def personal_evidence(rows, current_id, minimum=5):
    """Leave-current-out distributions and explicit empirical comparison zones.

    Zones describe membership in outcome-group IQRs, never optimal technique,
    causality, safety, or success probability. Eligibility is passed by insights.
    """
    fields = ('bag_release_angle_deg','bag_release_speed_arm_lengths_s','bag_release_speed_m_s',
              'elbow_angle_deg_at_release','trunk_inclination_deg_at_release')
    result=[]
    for name in fields:
        previous=[r for r in rows if r['trial_id'] != current_id and r.get(name) is not None
                  and np.isfinite(r[name])]
        groups={}
        for label, subset in [('all', previous), ('hole', [r for r in previous if r.get('score_category')==3]),
                              ('board_or_miss',[r for r in previous if r.get('score_category') in (0,1)])]:
            a=np.asarray([r[name] for r in subset],float)
            groups[label]=dict(n=len(a),median=float(np.median(a)) if len(a)>=minimum else None,
                              low=float(np.quantile(a,.25)) if len(a)>=minimum else None,
                              high=float(np.quantile(a,.75)) if len(a)>=minimum else None)
        def eligible_for_color(r):
            return r.get('feedback_eligible') is True and (not name.startswith('bag_') or r.get('feedback_bag_eligible') is True)
        eligible=[r for r in previous if eligible_for_color(r)]
        colored={}
        for label, score_set in [('hole',(3,)),('board_or_miss',(0,1))]:
            values=np.asarray([r[name] for r in eligible if r.get('score_category') in score_set],float)
            colored[label]=dict(n=len(values),low=float(np.quantile(values,.25)) if len(values)>=10 else None,
                                high=float(np.quantile(values,.75)) if len(values)>=10 else None)
        current=next((r for r in rows if r['trial_id']==current_id),{})
        x=current.get(name)
        zone='neutral'
        explanation='Need a reviewed fixed side view and at least 10 other eligible hole throws plus 10 board/miss throws for this metric.'
        if (eligible_for_color(current) and x is not None and np.isfinite(x)
                and all(g['low'] is not None for g in colored.values())):
            hole=colored['hole']; other=colored['board_or_miss']
            in_hole=hole['low']<=x<=hole['high']; in_other=other['low']<=x<=other['high']
            if in_hole and not in_other:
                zone='green'; explanation='Matches the middle 50% of this athlete’s hole throws only.'
            elif in_other and not in_hole:
                zone='red'; explanation='Matches the middle 50% of this athlete’s board/miss throws only.'
            else:
                zone='yellow'; explanation='Overlapping ranges: outcome groups do not distinguish this value.' if in_hole else 'Outside both central ranges: these groups do not classify this value.'
        result.append(dict(metric=name,groups=groups,minimum=minimum,
            feedback=dict(zone=zone,explanation=explanation,minimum_per_group=10,ranges=colored,
                          meaning='Empirical range membership, not good/bad technique, causality, safety or a success probability.'),
            note='Middle 50% of other comparable throws; descriptive, not an optimal range. Hole is a scoring category, not universal tactical success.'))
    return result
