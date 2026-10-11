"""Deterministic trial explanations, within-athlete repeatability and local reports."""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
from typing import Any
import html
import json
import math
import numpy as np

from .serialization import write_json, json_ready, canonical_hash
from .video import file_sha256

MINIMUM_CONSISTENCY = 5
LABELS = {"elbow_angle_deg": "Elbow angle", "arm_to_trunk_deg": "Arm relative to trunk",
          "trunk_inclination_deg": "Trunk inclination", "upper_arm_orientation_deg": "Upper-arm orientation",
          "forearm_orientation_deg": "Forearm orientation", "wrist_path_arm_lengths": "Wrist path"}


def physics_sentence(zones, rows, minimum=5):
    """Model-based priority: which release variable's spread or aim most exceeds its green window."""
    if zones.get("status")!="available" or len([r for r in rows if r.get('bag_release_speed_m_s') is not None])<minimum:
        return None
    fmt=lambda v,u: f"{v:.1f}°" if u=="°" else f"{v:.2f} {u}"
    parts=[]
    for v in sorted((x for x in zones["variables"] if x.get("green_half_width")), key=lambda x:-(x.get("demand_ratio") or 0)):
        half,sd,bias,u=v["green_half_width"],v["athlete_sd"],v["aim_bias"],v["unit"]
        if sd is not None and sd>half:
            parts.append(f"{v['label'].lower()} varies by {fmt(sd,u)} (SD) but the hole window is only ±{fmt(half,u)} wide")
        if bias is not None and abs(bias)>half:
            parts.append(f"median {v['label'].lower()} is {fmt(abs(bias),u)} {'above' if bias>0 else 'below'} the centre of the hole window")
    if not parts:
        return "Physics check: this athlete's release spread fits inside the model's hole window; misses likely come from aim or bag behaviour after landing."
    return "Physics check (drag-free model): "+"; ".join(parts[:2])+"."


def read(path, default=None):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else default


def release_window_quality(quality, raw, confidence, landmarks, release, side, config):
    """Visibility of throwing-arm/trunk landmarks within ±50 ms of release (no composite score)."""
    required = [landmarks.index(n) for n in ("left_shoulder", "right_shoulder", f"{side}_elbow", f"{side}_wrist", "left_hip", "right_hip") if n in landmarks]
    conf = np.asarray(confidence)[:, required]
    finite = np.isfinite(np.asarray(raw)[:, required]).all(axis=-1)
    usable = finite & np.isfinite(conf) & (conf >= config["confidence_threshold"])
    release_visibility = None
    if release is not None and 0 <= release < len(raw):
        radius = max(1, int(round(quality["frame_rate_fps"] * .05)))
        release_visibility = float(np.mean(np.all(usable[max(0,release-radius):release+radius+1], axis=1)))
    warnings = list(quality['warnings'])
    if release_visibility is not None and release_visibility < .8:
        warnings.append("Throwing-arm or trunk landmarks were obscured within 50 ms of the release candidate.")
    return {"release_visibility":release_visibility,
            "release_confidence":float(np.nanmean(conf[release])) if release is not None and 0 <= release < len(conf) else None,
            "warnings":warnings}


def compatible_key(trial, manifest):
    from .pipeline import method_signature
    config = manifest.get('analysis_configuration', {})
    return (trial.get('cameraView'), trial.get('throwingSide'), trial.get('sessionID'),
            (trial.get('outcome') or {}).get('throw_type','Standard'),
            (trial.get('outcome') or {}).get('intended_target','Hole center'),
            manifest.get('pose_backend'),manifest.get('pose_model'),manifest.get('pose_model_version'),
            manifest.get('pose_model_sha256'),method_signature(manifest),canonical_hash(config))


def incompatibility_reason(trial, manifest, base_trial, base_manifest) -> str:
    """Why a throw cannot be pooled with the base throw (plain words for the coach)."""
    from .pipeline import method_signature
    if trial.get('cameraView') != base_trial.get('cameraView'):
        return 'different camera view'
    if trial.get('throwingSide') != base_trial.get('throwingSide'):
        return 'different throwing hand'
    if trial.get('sessionID') != base_trial.get('sessionID'):
        return 'recorded in a different session (camera setup may differ)'
    if (trial.get('outcome') or {}).get('throw_type', 'Standard') != (base_trial.get('outcome') or {}).get('throw_type', 'Standard'):
        return 'different throw type'
    if (trial.get('outcome') or {}).get('intended_target', 'Hole center') != (base_trial.get('outcome') or {}).get('intended_target', 'Hole center'):
        return 'different target'
    if method_signature(manifest) != method_signature(base_manifest):
        return 'analyzed with a different app version: re-analyze to include it'
    if (manifest.get('pose_backend'), manifest.get('pose_model'), manifest.get('pose_model_sha256')) != \
            (base_manifest.get('pose_backend'), base_manifest.get('pose_model'), base_manifest.get('pose_model_sha256')):
        return 'different body-tracking model: re-analyze to include it'
    return 'different analysis settings: re-analyze to include it'


def consistency_model(normalized: list[dict], minimum=MINIMUM_CONSISTENCY):
    result = {"n":len(normalized),"minimum_trials":minimum,"components":[],"curves":{},"traces":[],
              "message":f"More trials needed: record at least {minimum} comparable throws with usable tracking."}
    if len(normalized)<minimum:
        return result
    n_samples=len(normalized[0]['tau'])
    fields = {"elbow_angle_deg":"degrees", "trunk_inclination_deg":"degrees", "wrist_path_arm_lengths":"arm lengths"}
    for field,units in fields.items():
        arrays=[np.asarray(n['values'].get(field,[]),float) for n in normalized]
        if not arrays or any(len(a)!=n_samples for a in arrays):
            continue
        stack=np.stack(arrays)
        count=np.sum(np.isfinite(stack),axis=0)
        if np.mean(count>=minimum)<.8:
            continue
        mean=np.nanmean(stack,axis=0)
        if field == 'trunk_inclination_deg':
            mean=np.degrees(np.arctan2(np.nanmean(np.sin(np.radians(stack)),axis=0),np.nanmean(np.cos(np.radians(stack)),axis=0)))
            stack=mean+(stack-mean+180)%360-180
        sd=np.nanstd(stack,axis=0,ddof=1)
        sd=np.where(count>=minimum,sd,np.nan)
        variability=float(np.sqrt(np.nanmean(np.sum(sd**2,axis=-1)))) if sd.ndim==2 else float(np.sqrt(np.nanmean(sd**2)))
        result['components'].append({'name':LABELS[field], 'variability':variability,'units':units})
        result['curves'][field]={'mean':mean,'sd':sd,'count':count}
    timings=np.array([n.get('event_timing',{}).get('release') for n in normalized],float)
    if np.isfinite(timings).sum()>=minimum:
        sd=float(np.nanstd(timings,ddof=1))
        result['components'].append({'name':'Release timing','variability':sd,'units':'cycle fraction'})
    result['message']=(f"Across {len(normalized)} comparable throws: typical throw-to-throw spread (RMS pointwise SD) of each curve. "
                       "Smaller means more repeatable; it does not rate technique quality.") if result['components'] else 'More complete tracking needed to describe repeatability.'
    result['tau']=normalized[0]['tau']
    result['traces']=[{'trial_id':n['trial_id'],'wrist':n['values'].get('wrist_path_arm_lengths',[]),'elbow':n['values'].get('elbow_angle_deg',[])} for n in normalized]
    result['equation']='Waveform variability = RMS over the cycle of the pointwise sample SD; wrist uses sqrt(mean(SDx² + SDy²)); release timing uses the sample SD of the release fraction.'
    return json_ready(result)


def phase_at(tau, events):
    backswing=events.get('peak_backswing');release=events.get('release');follow=events.get('peak_follow_through')
    if release is not None and abs(tau-release)<=.05:return 'around release'
    if backswing is not None and tau<=backswing:return 'backswing'
    if release is not None and tau<release:return 'forward swing'
    if follow is not None and tau<=follow:return 'follow-through'
    return 'late follow-through'


def differences(comparison, normalized):
    if not comparison:return []
    result=[];curves=comparison.get('curves',{});tau=np.asarray(curves.get('tau',[]),float)
    for field in LABELS:
        if field not in curves.get('test',{}) or field not in curves.get('reference_mean',{}):continue
        a=np.asarray(curves['test'][field],float);b=np.asarray(curves['reference_mean'][field],float)
        error=a-b
        if 'orientation' in field or field=='trunk_inclination_deg':error=(error+180)%360-180
        distance=np.linalg.norm(error,axis=-1) if error.ndim==2 else np.abs(error)
        if not np.isfinite(distance).any():continue
        i=int(np.nanargmax(distance));amount=float(distance[i]);phase=phase_at(float(tau[i]), normalized.get('event_timing',{}))
        units='arm lengths' if error.ndim==2 else 'degrees'
        phase_phrase = phase if phase == 'around release' else 'during ' + phase
        tolerance=.25 if error.ndim==2 else 10 if field=='trunk_inclination_deg' else 15
        direction=''
        if error.ndim==1:
            direction=('More extended' if error[i]>0 else 'More flexed') if field=='elbow_angle_deg' else ('Higher' if error[i]>0 else 'Lower')
        result.append({'metric':field,'name':LABELS[field], 'amount':amount,'signed_difference':float(error[i]) if error.ndim==1 else None,
                       'units':units,'percent':float(100*tau[i]),'phase':phase,'relative_to_tolerance':amount/tolerance,
                       'explanation':f"{direction + ' than reference; ' if direction else ''}largest pointwise difference {phase_phrase}, at {100*tau[i]:.0f}% of the movement."})
    return sorted(result,key=lambda d:d['relative_to_tolerance'],reverse=True)


def valid_comparison(path):
    value=read(path)
    if not value:return None
    hashes=value.get('source_hashes')
    if not hashes:return None
    for directory,expected in hashes.items():
        if (Path(directory)/'needs_reanalysis.json').exists():return None
        p=Path(directory)/'normalized.json'
        if not p.exists() or file_sha256(p)!=expected:return None
    return value


def comparison_references_are_current(project, trial, comparison):
    """Require every saved comparison member to remain assigned and compatible."""
    if not comparison:
        return False
    trial_by_id = {item['id']: item for item in project['trials']}
    assigned_reference_ids = {
        reference_id
        for reference_set in project.get('referenceSets', project.get('reference_sets', []))
        for reference_id in reference_set.get('trialIDs', reference_set.get('trial_ids', []))
    }
    assigned_reference_ids.update(item['id'] for item in project['trials'] if item.get('isReference'))
    comparison_ids = comparison.get('reference_trial_ids', [])
    return bool(comparison_ids) and all(
        reference_id in assigned_reference_ids
        and reference_id in trial_by_id
        and reference_id != trial['id']
        and trial_by_id[reference_id]['cameraView'] == trial['cameraView']
        for reference_id in comparison_ids
    )


def generate_insights(project_path, trial_id, export_report=True):
    root=Path(project_path).resolve();project=read(root/'project.json')
    if not project:raise ValueError('Open a valid research project first.')
    trial=next((t for t in project['trials'] if t['id']==trial_id),None)
    if not trial or not trial.get('analysisRelativePath'):raise ValueError('Analyze this throw before opening Results.')
    directory=root/trial['analysisRelativePath'];results=read(directory/'results.json');norm=read(directory/'normalized.json');manifest=read(directory/'manifest.json',{})
    if not results or not norm:raise ValueError('This analysis is incomplete. Reanalyze the throw to generate Results.')
    warnings=list(results.get('warnings',[]))+list(results.get('quality',{}).get('warnings',[]))
    dirty=(directory/'needs_reanalysis.json').exists()
    comparison=valid_comparison(root/'comparisons'/trial_id/'comparison.json')
    if dirty:
        warnings.insert(0,'Tracking or event corrections changed. Reanalyze this throw before interpreting derived results.')
        comparison=None
    if comparison and not comparison_references_are_current(project, trial, comparison):
        comparison = None
    compatible=[];excluded=[];eligible_dirs=[];outcomes={};board=[];exclusion_reasons=[]
    trial_labels={t['id']:(t.get('name') or t.get('originalFilename') or t['id']) for t in project['trials']}
    for t in project['trials']:
        if t['athleteID']!=trial['athleteID']:continue
        if not t.get('analysisRelativePath'):
            exclusion_reasons.append({'trial_id':t['id'],'label':trial_labels[t['id']],'reason':'not analyzed yet'});continue
        d=root/t['analysisRelativePath'];m=read(d/'manifest.json',{});r=read(d/'results.json',{});n=read(d/'normalized.json')
        if (d/'needs_reanalysis.json').exists():
            excluded.append(t['id']);exclusion_reasons.append({'trial_id':t['id'],'label':trial_labels[t['id']],'reason':'needs re-analysis'});continue
        if compatible_key(t,m)!=compatible_key(trial,manifest):
            excluded.append(t['id']);exclusion_reasons.append({'trial_id':t['id'],'label':trial_labels[t['id']],
                                                               'reason':incompatibility_reason(t,m,trial,manifest)});continue
        if t.get('outcome'):board.append({'trial_id':t['id'],'label':t['originalFilename'],'outcome':t['outcome']})
        outcomes[t['id']]=t.get('outcome') or {}
        if not n or r.get('quality',{}).get('usable_frame_percentage',0)<80:
            excluded.append(t['id']);exclusion_reasons.append({'trial_id':t['id'],'label':trial_labels[t['id']],
                                                               'reason':'body tracking covered less than 80% of the frames'});continue
        compatible.append(n);eligible_dirs.append(d)
    consistency=consistency_model(compatible)
    from .outcomes import outcome_summary
    from .models import TrialOutcome,BoardPoint
    raw_outcome=trial.get('outcome');outcome=None
    if raw_outcome:
        kwargs=dict(raw_outcome)
        kwargs.setdefault("score_category", None)
        for key in ('intended_point','first_contact_point','final_resting_point'):
            if kwargs.get(key):kwargs[key]=BoardPoint(**kwargs[key])
        outcome=outcome_summary(TrialOutcome(**kwargs))
        write_json(directory/'outcome.json',outcome)
    diffs=differences(comparison,norm)
    sentences=[]
    if outcome:
        points=outcome['score_category'];sentences.append('Outcome is unobserved.' if points is None else f"Observed bag value: {points} {'point' if points==1 else 'points'} (not round cancellation score).")
    else:sentences.append('Task outcome has not been recorded.')
    release=results.get('events',{}).get('release',{})
    if release.get('manual_frame') is None and not release.get('confirmed_by'):
        sentences.append('Confirm the release candidate in the video before interpreting release mechanics.')
    flight=results.get('flight',{})
    if flight.get('time_of_flight_seconds') is not None:
        sentences.append(f"Reviewed release-to-first-contact time: {flight['time_of_flight_seconds']:.2f} s.")
    else:
        sentences.append('Confirm first contact to connect release with flight duration; unseen contact stays unknown.')
    sentences.append(consistency['message'])
    if warnings:sentences.append('Review the measurement warnings before interpreting movement differences.')
    relationships=None
    if eligible_dirs:
        from .pipeline import analyze_relationships
        comparison_dirs=[root/'comparisons'/n['trial_id'] for n in compatible if valid_comparison(root/'comparisons'/n['trial_id']/'comparison.json')]
        relationships=analyze_relationships(eligible_dirs,outcomes,directory/'relationships.json',comparison_dirs,max(8,project.get('analysisSettings',{}).get('minimumRelationshipTrials',8)))
    from .flight import landing_dispersion
    performance = {"first_contact": landing_dispersion(list(outcomes.values())),
                   "final_rest": landing_dispersion(list(outcomes.values()), 'final_resting_point'),
                   "observed_scores": {str(k):sum(o.get('score_category')==k for o in outcomes.values()) for k in (0,1,3)},
                   "unknown_scores":sum(o.get('score_category') is None for o in outcomes.values())}
    from .performance import performance_summary
    rows=(relationships or {}).get('data_rows',[])
    performance["summary"]=performance_summary(rows,trial_labels)
    from .zones import ZoneSettings, sports_stats, zone_report
    settings=project.get('analysisSettings',{})
    measured=[x for x in ((read(d/'results.json',{}).get('summaries') or {}).get('release_to_board_front_m') for d in eligible_dirs) if isinstance(x,(int,float))]
    # Measured distances beyond the plausible range come from a failed board scale (one pilot throw read 24 m).
    measured=[x for x in measured if 1.5<=x<=15.0]
    default_distance=float(settings.get('releaseToBoardMeters') or 7.7)
    from .zones import personal_slide_allowance, personal_zone
    slides=[]
    for d in eligible_dirs:
        summ=read(d/'results.json',{}).get('summaries') or {}
        if summ.get('board_end_in_hole') is not None and isinstance(summ.get('board_slide_in'),(int,float)):
            slides.append(summ['board_slide_in'])
    slide_m,slide_source,_=personal_slide_allowance(slides)
    zone_settings=ZoneSettings(release_to_board_m=float(np.median(measured)) if len(measured)>=3 else default_distance,
                               slide_allowance_m=slide_m)
    performance["sports"]=sports_stats([o.get('score_category') for o in outcomes.values()])
    performance["zones"]=zone_report(rows,zone_settings)
    performance["zones"]["settings"]["distance_source"]="measured_median" if len(measured)>=3 else "assumed"
    from .verdict import throw_verdict
    other_metrics=[read(d/'results.json',{}).get('coach_metrics') or {} for d in eligible_dirs if d!=directory]
    grades={k:v.get('grade') for k,v in (results.get('quality',{}).get('grades') or {}).items() if isinstance(v,dict)}
    verdict=throw_verdict(results.get('coach_metrics') or {},other_metrics,grades,(results.get('summaries') or {}).get('release_to_board_front_m'),replace(zone_settings,release_to_board_m=default_distance),athlete_median_m=float(np.median(measured)) if len(measured)>=3 else None,observed_score=(trial.get('outcome') or {}).get('score_category'),board_phase=results.get('board_phase'))
    performance["summary"]["feedback"]["physics"]=physics_sentence(performance["zones"],rows)
    from .coaching import athlete_dashboard
    grade_rows,coach_rows=[],[]
    for d in eligible_dirs:
        r=read(d/'results.json',{})
        grade_rows.append({k:v.get('grade') for k,v in (r.get('quality',{}).get('grades') or {}).items() if isinstance(v,dict)})
        coach_rows.append(r.get('coach_metrics') or {})
    dashboard=athlete_dashboard(rows,performance["summary"],performance["sports"],performance["first_contact"],
                                performance["zones"],zone_settings,trial_labels,grade_rows,coach_rows)
    athlete_record=next((a for a in project['athletes'] if a['id']==trial['athleteID']),{})
    personal=personal_zone(rows,zone_settings,slides,"measured_median" if len(measured)>=3 else "settings")
    personal['distance_measured_n']=len(measured)
    dashboard.update(personal_zone=personal,
                     distance={'release_to_board_m':zone_settings.release_to_board_m,
                               'source':'measured_median' if len(measured)>=3 else 'settings','n_measured':len(measured),
                               'regulation_release_to_board_m':7.7,
                               'note':('Measured from the videos: release point to the front of the board. '
                                       'The regulation pitch is 27 ft between board fronts (about 7.7 m from a typical release point); '
                                       'this session was shorter, so zones and advice use the measured distance.')
                                      if len(measured)>=3 else
                                      'Not enough throws with a measured distance; the distance from Settings is used.'},
                     lateral={'measured':False,
                              'note':'The green zone covers distance along the throw line only; left/right aim is not modelled. '
                                     'Where each bag ended left/right is estimated from the side camera (about ±3 in) and drawn on the board; '
                                     'a board camera measures it precisely.'},
                     consistency=consistency,
                     cohort={'included':[n['trial_id'] for n in compatible],'excluded':exclusion_reasons,
                             'base_trial_id':trial_id})
    dashboard.update(athlete_id=trial['athleteID'],athlete=athlete_record.get('participantCode','Unknown athlete'),
                     trial_labels={t['id']:trial_labels[t['id']] for t in project['trials'] if t['athleteID']==trial['athleteID']},
                     trial_analysis_paths={t['id']:t.get('analysisRelativePath') for t in project['trials']
                                           if t['athleteID']==trial['athleteID']})
    (root/'dashboards').mkdir(exist_ok=True)
    write_json(root/'dashboards'/f"{trial['athleteID']}.json",dashboard)
    performance["dashboard_path"]=f"dashboards/{trial['athleteID']}.json"
    # Level 1-3 coaching feedback leads; review reminders follow it.
    feedback=performance["summary"]["feedback"]
    payload_summary=' '.join([feedback['result'],feedback['why'],feedback['next']]+sentences[1:])
    athlete=next((a for a in project['athletes'] if a['id']==trial['athleteID']),{})
    payload={'schema_version':1,'trial_id':trial_id,'athlete':athlete.get('participantCode','Unknown athlete'),
             'trial_name':trial.get('name') or trial['originalFilename'],'date':trial.get('createdAt'), 'quality':results['quality'],
             'outcome':outcome,'comparison_available':comparison is not None,
             'differences':diffs,'coach_summary':payload_summary,'consistency':consistency,
             'warnings':warnings,'excluded_trials':excluded,'exclusion_reasons':exclusion_reasons,
             'cohort_trial_ids':[n['trial_id'] for n in compatible],
             'board_trials':board,'relationships':relationships,'verdict':verdict,
             'provenance':{'backend':manifest.get('pose_backend','unknown'),'model':manifest.get('pose_model','unknown'),
                           'sports2d_version':manifest.get('pose_backend_metadata',{}).get('sports2d_version'),
                           'configuration':manifest.get('analysis_configuration',{}),'analysis_id':manifest.get('analysis_id'),
                           'model_hash':manifest.get('pose_model_sha256'),'camera_view':trial['cameraView']},
             'needs_reanalysis':dirty, 'performance':performance}
    write_json(directory/'insights.json',payload)
    if export_report:
        from .report import create_report
        create_report(directory,payload,norm,comparison)
    return json_ready(payload)
