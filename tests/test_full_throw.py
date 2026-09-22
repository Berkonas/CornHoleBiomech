"""Independent analytical and failure-mode checks for full-throw measurement."""
import json
import numpy as np
import pytest
from cornhole_biomech.flight import flight_summary, landing_dispersion
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


def test_precision_note_follows_how_points_were_measured():
    measured=TrialOutcome('hole',1,'Standard',intended_point=BoardPoint(12,39),
                          first_contact_point=BoardPoint(11,37,'board_camera_homography'))
    assert 'homography' in outcome_summary(measured)['precision_note']
    measured.final_resting_point=BoardPoint(12,40)
    assert 'approximate' in outcome_summary(measured)['precision_note']
