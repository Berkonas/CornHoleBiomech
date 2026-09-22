"""Independent analytical and failure-mode checks for full-throw measurement."""
import json
import numpy as np
import pytest
from cornhole_biomech.flight import flight_summary, landing_dispersion, personal_evidence
from cornhole_biomech.bag import estimate_projectile_release_kinematics, SpatialCalibration
from cornhole_biomech.models import TrialOutcome, BoardPoint
from cornhole_biomech.outcomes import outcome_summary
from cornhole_biomech.pipeline import analyze_relationships


def trajectory(fps=60, n=61):
    t=np.arange(n)/fps
    return np.column_stack((100+300*t,500-240*t+300*t*t))


def test_contact_and_rest_are_distinct_and_unknown_is_not_miss():
    o=TrialOutcome('hole',None,'Standard', intended_point=BoardPoint(12,39),final_resting_point=BoardPoint(12,39))
    result=outcome_summary(o)
    assert result['score_category'] is None and result['score_status']=='unobserved'
    assert result['spatial_error'] is None
    assert result['final_resting_error']['radial_error_inches']==0
    o.first_contact_point=BoardPoint(15,43)
    assert outcome_summary(o)['first_contact_error']['radial_error_inches']==5


def test_time_of_flight_needs_both_reviewed_events_not_track_loss():
    p=trajectory()
    for released,contact in [(False,60),(True,None)]:
        assert flight_summary(p,0,contact,60,60,released)['time_of_flight_seconds'] is None
    r=flight_summary(p,0,60,60,None,True)
    assert r['time_of_flight_seconds']==1 and r['trajectory']==[]


def test_reviewed_flight_equal_image_axes_apex_and_gaps():
    p=trajectory()
    r=flight_summary(p,0,60,60,60,True,'side',True)
    assert r['observed_apex_frame']==24
    assert r['observed_rise_pixels']==pytest.approx(48)
    assert r['horizontal_travel_pixels']==300
    p[22:25]=np.nan
    r=flight_summary(p,0,60,60,60,True,'side',True)
    assert r['observed_apex_frame'] is None
    assert r['trajectory'][23]['x'] is None
    assert r['coverage']==pytest.approx(58/61)


@pytest.mark.parametrize('fixed,view',[(False,'side'),(True,'front'),(True,'other')])
def test_moving_or_oblique_camera_withholds_spatial_flight_metrics(fixed,view):
    r=flight_summary(trajectory(),0,60,60,60,True,view,fixed)
    assert r['time_of_flight_seconds']==1
    assert r['observed_apex_frame'] is None and r['horizontal_travel_pixels'] is None


@pytest.mark.parametrize('release,contact',[(10,9),(10,10),(0,61),(-1,10)])
def test_invalid_contact_order_rejected(release,contact):
    with pytest.raises(ValueError): flight_summary(trajectory(),release,contact,60,60,True)


def test_quadratic_release_fit_avoids_linear_midwindow_bias_at_30fps():
    p=trajectory(30,15)
    r=estimate_projectile_release_kinematics(p,0,30,100,'left_to_right',window_seconds=.10)
    assert r['fit_degree']==2
    assert r['velocity']['forward_px_s']==pytest.approx(300)
    assert r['velocity']['vertical_px_s']==pytest.approx(240)
    assert r['velocity']['angle_deg']==pytest.approx(np.degrees(np.arctan2(240,300)))
    assert r['acceleration']['status']=='suppressed'


def test_scale_units_and_wrong_plane():
    p=trajectory()
    bad=SpatialCalibration(100,'board_plane',True,'board')
    good=SpatialCalibration(100,'athlete_release_motion_plane',True,'ruler')
    for scale,available in [(None,False),(bad,False),(good,True)]:
        r=estimate_projectile_release_kinematics(p,0,60,100,'left_to_right',scale)
        assert ('velocity' in r['physical_units']) == available
    assert estimate_projectile_release_kinematics(p,0,60,100,'left_to_right',good)['physical_units']['velocity']['forward_m_s']==pytest.approx(3)


def test_poor_fit_suppresses_velocity_instead_of_false_precision():
    p=trajectory();p[:9,1]+=[0,90,-80,110,-70,95,-110,70,20]
    r=estimate_projectile_release_kinematics(p,0,60,100,'left_to_right')
    assert r['status']=='suppressed_poor_fit' and r['velocity'] is None


def test_dispersion_is_about_centroid_not_target_and_no_n1_claim():
    points=[dict(first_contact_point=dict(x_inches=x,y_inches=10)) for x in (1,5)]
    d=landing_dispersion(points+[{}])
    assert d['rms_radius_inches']==2 and d['missing']==1
    assert d['lateral_sd_inches']==pytest.approx(np.sqrt(8))
    assert landing_dispersion(points[:1])['rms_radius_inches'] is None


def test_personal_ranges_exclude_current_throw_and_unknown_scores():
    rows=[dict(trial_id=str(i),bag_release_angle_deg=i,score_category=3) for i in range(6)]
    rows.append(dict(trial_id='unknown',bag_release_angle_deg=99,score_category=None))
    r=personal_evidence(rows,'5')[0]
    assert r['groups']['hole']['n']==5 and r['groups']['hole']['median']==2
    assert r['groups']['board_or_miss']['n']==0
    assert personal_evidence(rows[:5],'4')[0]['groups']['hole']['median'] is None


def test_relationship_never_relabels_final_rest_as_contact(tmp_path):
    paths=[];outcomes={}
    for i in range(8):
        p=tmp_path/str(i);p.mkdir();paths.append(p)
        (p/'results.json').write_text(json.dumps(dict(trial_id=str(i),athlete_id='A',summaries={'elbow_angle_deg_at_release':100+i})))
        outcomes[str(i)]=dict(intended_target='hole',score_category=None,throw_type='Standard',intended_point=dict(x_inches=12,y_inches=39),final_resting_point=dict(x_inches=i,y_inches=39),spatial_error={'radial_error_inches':99})
    result=analyze_relationships(paths,outcomes,tmp_path/'relationships.json')
    assert all(r['radial_error_inches'] is None and r['score_category'] is None for r in result['data_rows'])
    assert result['relationships']['elbow_angle_deg_at_release']['n']==0


def test_native_unknown_score_omission_loads_in_insights(tmp_path):
    from cornhole_biomech.insights import generate_insights
    directory=tmp_path/'analysis';directory.mkdir()
    trial=dict(id='T',athleteID='A',analysisRelativePath='analysis',cameraView='side',throwingSide='right',originalFilename='throw.mov',outcome=dict(intended_target='Hole center',throw_type='Standard',notes='Not visible'))
    (tmp_path/'project.json').write_text(json.dumps(dict(trials=[trial],athletes=[dict(id='A',participantCode='P1')])))
    (directory/'results.json').write_text(json.dumps(dict(trial_id='T',athlete_id='A',quality=dict(warnings=[],usable_frame_percentage=100),summaries={})))
    (directory/'normalized.json').write_text(json.dumps(dict(trial_id='T',camera_view='side',tau=[0,1],values={})))
    result=generate_insights(tmp_path,'T',export_report=False)
    assert result['outcome']['score_category'] is None
    assert result['performance']['unknown_scores']==1
    assert result['performance']['observed_scores']['0']==0
    assert result['relationships']['relationships']['bag_release_angle_deg']['n']==0


def test_stationary_bag_does_not_get_an_arbitrary_launch_angle():
    r=estimate_projectile_release_kinematics(np.tile([10.,20.],(15,1)),0,60,100,'left_to_right')
    assert r['velocity'] is None


def evidence_rows(current=25):
    rows=[dict(trial_id=f'h{i}',score_category=3,bag_release_angle_deg=20+i,
               feedback_eligible=True,feedback_bag_eligible=True) for i in range(10)]
    rows += [dict(trial_id=f'o{i}',score_category=0 if i%2 else 1,bag_release_angle_deg=40+i,
                  feedback_eligible=True,feedback_bag_eligible=True) for i in range(10)]
    rows.append(dict(trial_id='current',score_category=3,bag_release_angle_deg=current,
                     feedback_eligible=True,feedback_bag_eligible=True))
    return rows


@pytest.mark.parametrize('value,zone',[(25,'green'),(45,'red'),(35,'yellow'),(90,'yellow')])
def test_empirical_colors_are_leave_current_out_iqr_membership(value,zone):
    result=personal_evidence(evidence_rows(value),'current')[0]['feedback']
    assert result['zone']==zone
    assert result['ranges']['hole']==dict(n=10,low=22.25,high=26.75)
    assert result['ranges']['board_or_miss']==dict(n=10,low=42.25,high=46.75)


def test_color_requires_both_groups_reviewed_current_and_bag_identity():
    rows=evidence_rows()
    assert personal_evidence(rows[1:],'current')[0]['feedback']['zone']=='neutral'
    rows[-1]['feedback_eligible']=False
    assert personal_evidence(rows,'current')[0]['feedback']['zone']=='neutral'
    rows[-1]['feedback_eligible']=True;rows[-1]['feedback_bag_eligible']=False
    assert personal_evidence(rows,'current')[0]['feedback']['zone']=='neutral'
    rows=evidence_rows(); rows[0]['feedback_bag_eligible']=False
    assert personal_evidence(rows,'current')[0]['feedback']['ranges']['hole']['n']==9


def test_overlapping_outcome_groups_are_yellow_not_a_claim_of_success():
    rows=evidence_rows()
    for row in rows:
        if row['score_category'] in (0,1): row['bag_release_angle_deg']-=20
    assert personal_evidence(rows,'current')[0]['feedback']['zone']=='yellow'


def test_unknown_nan_and_unreviewed_trials_never_inflate_color_evidence():
    rows=evidence_rows()
    for i,(score,value,reviewed) in enumerate([(None,25,True),(3,float('nan'),True),(3,25,False)]):
        rows.append(dict(trial_id=f'bad{i}',score_category=score,bag_release_angle_deg=value,
                         feedback_eligible=reviewed,feedback_bag_eligible=reviewed))
    r=personal_evidence(rows,'current')[0]['feedback']
    assert r['ranges']['hole']['n']==10
    assert r['ranges']['board_or_miss']['n']==10


def test_insights_derives_color_eligibility_from_reviewed_sources(tmp_path):
    from cornhole_biomech.insights import generate_insights
    trials=[]
    for i,row in enumerate(evidence_rows()):
        d=tmp_path/f't{i}'; d.mkdir()
        trial=dict(id=row['trial_id'],athleteID='A',analysisRelativePath=f't{i}',cameraView='side',
                   throwingSide='right',sessionID='S',originalFilename=f'{i}.mov',
                   outcome=dict(intended_target='Hole center',throw_type='Standard',score_category=row['score_category']))
        trials.append(trial)
        (d/'results.json').write_text(json.dumps(dict(trial_id=row['trial_id'],athlete_id='A',camera_view='side',
            events=dict(release=dict(manual_frame=5)),
            quality=dict(warnings=[],usable_frame_percentage=100,release_visibility=1),
            summaries=dict(bag_release_angle_deg=row['bag_release_angle_deg']),
            bag=dict(review=dict(covers_launch_fit=True),launch=dict(status='estimated')))))
        (d/'normalized.json').write_text(json.dumps(dict(trial_id=row['trial_id'],camera_view='side',tau=[0,1],values={})))
        (d/'manifest.json').write_text(json.dumps(dict(flight_review=dict(fixed_camera=True))))
    (tmp_path/'project.json').write_text(json.dumps(dict(trials=trials,athletes=[dict(id='A',participantCode='Synthetic QA')])))
    r=generate_insights(tmp_path,'current',export_report=False)
    assert r['performance']['personal_evidence'][0]['feedback']['zone']=='green'
    # Legacy/unreviewed metadata must not become green merely because the scalar exists.
    (tmp_path/'t0/manifest.json').write_text('{}')
    r=generate_insights(tmp_path,'current',export_report=False)
    assert r['performance']['personal_evidence'][0]['feedback']['zone']=='neutral'
