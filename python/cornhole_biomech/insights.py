"""Deterministic trial explanations, within-athlete repeatability and local reports."""
from __future__ import annotations
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


def read(path, default=None):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else default


def quality_index(quality, raw, confidence, landmarks, release, side, config):
    required = [landmarks.index(n) for n in ("left_shoulder", "right_shoulder", f"{side}_elbow", f"{side}_wrist", "left_hip", "right_hip") if n in landmarks]
    conf = np.asarray(confidence)[:, required]
    finite = np.isfinite(np.asarray(raw)[:, required]).all(axis=-1)
    usable = finite & np.isfinite(conf) & (conf >= config["confidence_threshold"])
    visibility = float(np.mean(np.all(usable, axis=1))) if usable.size else 0
    mean_conf = float(np.mean(np.where(finite & np.isfinite(conf), np.clip(conf, 0, 1), 0))) if conf.size else 0
    release_visibility = None
    if release is not None and 0 <= release < len(raw):
        radius = max(1, int(round(quality["frame_rate_fps"] * .05)))
        release_visibility = float(np.mean(np.all(usable[max(0,release-radius):release+radius+1], axis=1)))
    components = {"raw_landmark_coverage": {"score":100*visibility, "weight":.5},
                  "mean_required_confidence": {"score":100*mean_conf,"weight":.3}}
    if release_visibility is not None:
        components["release_window_visibility"]={"score":100*release_visibility,"weight":.2}
    total=sum(v['score']*v['weight'] for v in components.values())/sum(v['weight'] for v in components.values())
    warnings = list(quality['warnings'])
    if release_visibility is not None and release_visibility < .8:
        warnings.append("Throwing-arm or trunk landmarks were obscured within 50 ms of the release candidate.")
    return {"score":total,"score_components":components,"release_visibility":release_visibility,
            "release_confidence":float(np.nanmean(conf[release])) if release is not None and 0 <= release < len(conf) else None,
            "warnings":warnings,"score_note":"Pilot tracking index: 50% raw coverage + 30% required-landmark confidence + 20% release-window visibility. Missing release component omitted. Manual correction does not inflate raw tracking confidence. FPS/view warnings remain separate."}


def compatible_key(trial, manifest):
    config = manifest.get('analysis_configuration', {})
    return (trial.get('cameraView'), trial.get('throwingSide'), trial.get('sessionID'),
            (trial.get('outcome') or {}).get('throw_type','Standard'),
            (trial.get('outcome') or {}).get('intended_target','Hole center'),
            manifest.get('pose_backend'),manifest.get('pose_model'),manifest.get('pose_model_version'),
            manifest.get('pose_model_sha256'),manifest.get('engine_source_sha256'),canonical_hash(config))


def consistency_model(normalized: list[dict], minimum=MINIMUM_CONSISTENCY):
    result = {"n":len(normalized),"minimum_trials":minimum,"score":None,"components":[],"curves":{},"traces":[],
              "message":f"More trials needed: record at least {minimum} comparable throws with usable tracking."}
    if len(normalized)<minimum:
        return result
    n_samples=len(normalized[0]['tau'])
    fields = {"elbow_angle_deg":(15.0,"degrees"), "trunk_inclination_deg":(10.0,"degrees"), "wrist_path_arm_lengths":(.25,"arm lengths")}
    for field,(tolerance,units) in fields.items():
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
        result['components'].append({'name':LABELS[field], 'variability':variability,'units':units,'tolerance':tolerance,'weight':1.0,'score':100*max(0,1-variability/tolerance)})
        result['curves'][field]={'mean':mean,'sd':sd,'count':count}
    timings=np.array([n.get('event_timing',{}).get('release') for n in normalized],float)
    if np.isfinite(timings).sum()>=minimum:
        sd=float(np.nanstd(timings,ddof=1))
        result['components'].append({'name':'Release timing','variability':sd,'units':'cycle fraction','tolerance':.1,'weight':1.0,'score':100*max(0,1-sd/.1)})
    # All four components required so scores remain comparable across athletes/sessions.
    if len(result['components'])==4:
        result['score']=float(np.mean([c['score'] for c in result['components']]))
        result['message']=f"Across {len(normalized)} comparable throws, this pilot index describes repeatability of elbow, trunk, wrist path and release timing. It does not rate technique quality."
    else:
        result['message']='More complete tracking needed for all four consistency components.'
    result['tau']=normalized[0]['tau']
    result['traces']=[{'trial_id':n['trial_id'],'wrist':n['values'].get('wrist_path_arm_lengths',[]),'elbow':n['values'].get('elbow_angle_deg',[])} for n in normalized]
    result['equation']='100 × mean(max(0, 1 − variability / tolerance)); waveform variability = RMS pointwise sample SD; wrist uses sqrt(mean(SDx² + SDy²)); release uses sample SD. Four equally weighted components, pilot tolerances 15°, 10°, 0.25 arm lengths, 0.10 cycle.'
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
    compatible=[];excluded=[];eligible_dirs=[];outcomes={};board=[];feedback_eligible={};feedback_bag_eligible={}
    trial_labels={t['id']:(t.get('name') or t.get('originalFilename') or t['id']) for t in project['trials']}
    for t in project['trials']:
        if t['athleteID']!=trial['athleteID'] or not t.get('analysisRelativePath'):continue
        d=root/t['analysisRelativePath'];m=read(d/'manifest.json',{});r=read(d/'results.json',{});n=read(d/'normalized.json')
        if compatible_key(t,m)!=compatible_key(trial,manifest) or (d/'needs_reanalysis.json').exists():
            excluded.append(t['id']);continue
        if t.get('outcome'):board.append({'trial_id':t['id'],'label':t['originalFilename'],'outcome':t['outcome']})
        outcomes[t['id']]=t.get('outcome') or {}
        if not n or r.get('quality',{}).get('usable_frame_percentage',0)<80:
            excluded.append(t['id']);continue
        compatible.append(n);eligible_dirs.append(d)
        # Colors require an explicit reviewed side-camera setup and visible release landmarks.
        feedback_eligible[t['id']] = bool(t.get('cameraView') == 'side'
            and m.get('flight_review',{}).get('fixed_camera')
            and r.get('events',{}).get('release',{}).get('manual_frame') is not None
            and (r.get('quality',{}).get('release_visibility') or 0) >= .8)
        bag = r.get('bag') or {}
        feedback_bag_eligible[t['id']] = bool(feedback_eligible[t['id']]
            and bag.get('review',{}).get('covers_launch_fit')
            and bag.get('launch',{}).get('status') == 'estimated')
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
    if release.get('manual_frame') is None:
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
    from .flight import landing_dispersion, personal_evidence
    evidence_rows=[dict(row,feedback_eligible=feedback_eligible.get(row['trial_id'],False),
                        feedback_bag_eligible=feedback_bag_eligible.get(row['trial_id'],False))
                   for row in (relationships or {}).get('data_rows',[])]
    performance = {"first_contact": landing_dispersion(list(outcomes.values())),
                   "final_rest": landing_dispersion(list(outcomes.values()), 'final_resting_point'),
                   "observed_scores": {str(k):sum(o.get('score_category')==k for o in outcomes.values()) for k in (0,1,3)},
                   "unknown_scores":sum(o.get('score_category') is None for o in outcomes.values()),
                   "personal_evidence": personal_evidence(evidence_rows,trial_id)}
    from .performance import performance_summary
    rows=(relationships or {}).get('data_rows',[])
    performance["summary"]=performance_summary(rows,trial_labels)
    # Level 1-3 coaching feedback leads; review reminders follow it.
    feedback=performance["summary"]["feedback"]
    payload_summary=' '.join([feedback['result'],feedback['why'],feedback['next']]+sentences[1:])
    athlete=next((a for a in project['athletes'] if a['id']==trial['athleteID']),{})
    payload={'schema_version':1,'trial_id':trial_id,'athlete':athlete.get('participantCode','Unknown athlete'),
             'trial_name':trial.get('name') or trial['originalFilename'],'date':trial.get('createdAt'), 'quality':results['quality'],
             'outcome':outcome,'similarity':comparison.get('similarity') if comparison else None,
             'differences':diffs,'coach_summary':payload_summary,'consistency':consistency,
             'warnings':warnings,'excluded_trials':excluded,'board_trials':board,'relationships':relationships,
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
