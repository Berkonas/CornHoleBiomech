from pathlib import Path
import json
import importlib.metadata
import numpy as np
import pytest

from cornhole_biomech.config import merged_config
from cornhole_biomech.normalization import resample_curve
from cornhole_biomech.comparison import curve_errors, build_reference_set
from cornhole_biomech.insights import (
    comparison_references_are_current,
    consistency_model,
    differences,
    release_window_quality,
    valid_comparison,
)
from cornhole_biomech.sports2d_adapter import availability, build_config, read_trc, read_mot, elbow_included_from_sports2d, Sports2DAdapter
from cornhole_biomech.video import VideoMetadata


def test_time_normalization_never_bridges_long_occlusion():
    values=np.arange(20,dtype=float);values[5:15]=np.nan
    tau,out=resample_curve(values,0,19,101)
    assert np.isnan(out[(tau>.25)&(tau<.75)]).all()
    assert out[0]==0 and out[-1]==19


def test_segment_orientation_errors_are_circular():
    result=curve_errors(np.array([179,178]),np.array([-179,-178]),circular=True)
    assert result['mae']==pytest.approx(3)
    reference=build_reference_set([{'upper_arm_orientation_deg':np.array([179.])},{'upper_arm_orientation_deg':np.array([-179.])}])
    assert abs(reference['upper_arm_orientation_deg']['mean'][0])==pytest.approx(180)
    assert reference['upper_arm_orientation_deg']['sd'][0]==pytest.approx(np.sqrt(2))


@pytest.mark.parametrize('included',[0,45,90,135,180])
def test_sports2d_elbow_convention_both_signs(included):
    for signed in (180-included,included-180):
        assert elbow_included_from_sports2d(signed)==pytest.approx(included)


def test_sports2d_missing_and_wrong_version(monkeypatch):
    def missing(_):raise importlib.metadata.PackageNotFoundError('sports2d')
    monkeypatch.setattr(importlib.metadata,'version',missing)
    assert availability()['available'] is False
    with pytest.raises(RuntimeError,match='not installed'):
        Sports2DAdapter().analyze(VideoMetadata('/video','hash',60,100,100,30,.5),Path('/tmp/unused-cornhole-test'),merged_config(),lambda *a:None)
    monkeypatch.setattr(importlib.metadata,'version',lambda _: '99.0')
    assert availability()['supported'] is False


def test_sports2d_configuration_is_explicit_and_independent_of_workdir(tmp_path,monkeypatch):
    defaults={'base':{'first_person_height':1.65},'post-processing':{'filter_type':'kalman'}}
    video=tmp_path/'a.mp4';out=tmp_path/'exports'
    config=build_config(video,out,merged_config(),defaults=defaults)
    monkeypatch.chdir('/')
    assert config['base']['video_input']==[str(video)]
    assert config['base']['result_dir']==str(out)
    assert config['pose']['device']=='cpu'
    assert not config['kinematics']['do_ik']
    assert not config['px_to_meters_conversion']['to_meters']
    assert not config['px_to_meters_conversion']['make_c3d']
    assert config['post-processing']['fill_large_gaps_with']=='nan'
    assert config['base']['person_ordering_method']!='on_click'
    assert defaults['post-processing']['filter_type']=='kalman'
    with pytest.raises(ValueError,match='CPU'):build_config(video,out,merged_config(),device='mps')


def test_trc_mot_ingestion_preserves_missing_and_units(tmp_path):
    trc=tmp_path/'sample.trc'
    trc.write_text('PathFileType\t4\t(X/Y/Z)\tsample.trc\nDataRate\tCameraRate\tNumFrames\tNumMarkers\tUnits\n60\t60\t2\t1\tpx\nFrame#\tTime\tRWrist\t\t\n\t\tX1\tY1\tZ1\n\n1\t0\t4\t5\t0\n2\t0.0166667\tnan\tnan\t0\n')
    result=read_trc(trc)
    assert result['units']=='px'
    assert result['markers']==['RWrist']
    assert np.isnan(result['coordinates'][1,0,0])
    mot=tmp_path/'sample.mot';mot.write_text('name sample\ninDegrees=yes\nendheader\ntime\tright elbow\n0\t90\n0.0166667\t100\n')
    assert read_mot(mot)['right elbow'][1]==100
    mot.write_text('bad');
    with pytest.raises(ValueError,match='endheader'):read_mot(mot)


def normalized_trial(i,offset=0):
    t=np.linspace(0,1,101)
    return {'trial_id':str(i),'tau':t.tolist(),'event_timing':{'release':.5},'values':{
        'elbow_angle_deg':(90+30*t+offset).tolist(),
        'trunk_inclination_deg':(5+t+offset).tolist(),
        'wrist_path_arm_lengths':np.column_stack((t,np.sin(t)+offset/100)).tolist()}}


def test_consistency_requires_five_trials_and_reports_raw_spread_without_a_score():
    assert consistency_model([normalized_trial(i) for i in range(4)])['components'] == []
    equal=consistency_model([normalized_trial(i) for i in range(5)])
    assert all(c['variability']==pytest.approx(0) for c in equal['components'])
    varied=consistency_model([normalized_trial(i,i) for i in range(5)])
    assert 'score' not in varied and all('score' not in c for c in varied['components'])
    elbow=next(c for c in varied['components'] if c['name']=='Elbow angle')
    assert elbow['variability']==pytest.approx(np.std(range(5),ddof=1))
    assert len(varied['components'])==4
    assert len(varied['traces'])==5
    bad=[normalized_trial(i) for i in range(5)]
    for t in bad:t['values']['elbow_angle_deg']=[None]*101
    assert 'Elbow angle' not in [c['name'] for c in consistency_model(bad)['components']]


def test_raw_tracking_quality_not_inflated_by_manual_points():
    names=('left_shoulder','right_shoulder','right_elbow','right_wrist','left_hip','right_hip')
    raw=np.ones((20,6,2));conf=np.full((20,6),.1)
    quality={'warnings':[],'frame_rate_fps':60}
    low=release_window_quality(quality,raw,conf,names,10,'right',merged_config())
    assert 'score' not in low
    assert low['release_visibility']==0
    assert 'obscured' in low['warnings'][0]


def test_differences_describe_correct_elbow_direction():
    n=normalized_trial(1);a=np.array(n['values']['elbow_angle_deg']);b=a+8
    c={'curves':{'tau':n['tau'],'test':{'elbow_angle_deg':a},'reference_mean':{'elbow_angle_deg':b}}}
    d=differences(c,n)[0]
    assert d['signed_difference']==-8
    assert 'More flexed' in d['explanation']


def test_stale_comparison_rejected(tmp_path):
    from cornhole_biomech.video import file_sha256
    d=tmp_path/'trial';d.mkdir();(d/'normalized.json').write_text('{}')
    c=tmp_path/'comparison.json';c.write_text(json.dumps({'source_hashes':{str(d):file_sha256(d/'normalized.json')}}))
    assert valid_comparison(c) is not None
    (d/'normalized.json').write_text('{"changed":true}')
    assert valid_comparison(c) is None


def test_reference_set_membership_controls_saved_comparison_validity():
    project = {
        "trials": [
            {"id": "test", "cameraView": "side"},
            {"id": "ref-a", "cameraView": "side", "isReference": True},
            {"id": "ref-b", "cameraView": "side", "isReference": True},
        ],
        "referenceSets": [
            {"id": "set-a", "trialIDs": ["ref-a"]},
            {"id": "set-b", "trialIDs": ["ref-b"]},
        ],
    }
    trial = project["trials"][0]
    assert comparison_references_are_current(project, trial, {"reference_trial_ids": ["ref-a"]})
    project["referenceSets"][0]["trialIDs"] = []
    project["trials"][1]["isReference"] = False
    assert not comparison_references_are_current(project, trial, {"reference_trial_ids": ["ref-a"]})


def test_circular_peak_rom_and_correlation_do_not_have_branch_artifacts():
    from cornhole_biomech.comparison import compare_normalized
    a=np.array([175,180,185,190.])
    reference=build_reference_set([{'forearm_orientation_deg':np.array([175,180,-175,-170.])}])
    result=compare_normalized({'forearm_orientation_deg':a},reference,{}, {})
    assert result['forearm_orientation_rmse_deg']==pytest.approx(0)
    assert result['forearm_orientation_rom_difference_deg']==pytest.approx(0)
    assert result['forearm_orientation_peak_difference_deg']==pytest.approx(0)
    assert result['forearm_orientation_waveform_correlation']==pytest.approx(1)


@pytest.mark.parametrize('dirty,settings',[(True,False),(False,True)])
def test_comparison_rejects_pending_edits_or_mixed_settings(tmp_path,dirty,settings):
    from cornhole_biomech.pipeline import compare_trial
    directories=[tmp_path/'a',tmp_path/'b']
    for i,d in enumerate(directories):
        d.mkdir();n=normalized_trial(i);n['camera_view']='side'
        (d/'normalized.json').write_text(json.dumps(n))
        (d/'manifest.json').write_text(json.dumps({'analysis_configuration':{'cutoff':6+i if settings else 6}}))
    if dirty:(directories[1]/'needs_reanalysis.json').write_text('{}')
    with pytest.raises(ValueError,match='Reanalyze'):
        compare_trial(directories[0],[directories[1]],tmp_path/'comparison')


@pytest.mark.parametrize('failure',[None,'engine','missing_exports'])
def test_adapter_public_api_raw_confidence_exports_and_failure_cleanup(tmp_path,monkeypatch,failure):
    import sys,types,ssl
    import cornhole_biomech.sports2d_adapter as adapter
    package=types.ModuleType('Sports2D');package.__path__=[]
    api=types.ModuleType('Sports2D.Sports2D');engine=types.ModuleType('Sports2D.process');engine.__file__=__file__
    def process_fun(cfg):
        # Person 1 is a small, confident bystander Sports2D would pick; person 0 is the thrower.
        all_frames_X_homog=np.stack((np.ones((3,8))*50,np.ones((3,8))*90),1)
        all_frames_Y_homog=np.stack((np.tile(np.linspace(20,80,8),(3,1)),np.tile(np.linspace(60,70,8),(3,1))),1)
        all_frames_scores_homog=np.stack((np.ones((3,8))*.2,np.ones((3,8))*.9),1)
        new_keypoints_names=['LShoulder','RShoulder','LElbow','RElbow','LWrist','RWrist','LHip','RHip']
        selected_persons=[1];pose_tracker=None
        if failure=='engine':raise ValueError('deliberate test failure')
        if failure!='missing_exports':
            d=Path(cfg['base']['result_dir'])
            (d/'sample.trc').write_text('PathFileType\t4\t(X/Y/Z)\tsample.trc\nDataRate\tCameraRate\tNumFrames\tNumMarkers\tUnits\n60\t60\t1\t1\tpx\nFrame#\tTime\tRWrist\t\t\n\t\tX1\tY1\tZ1\n1\t0\t4\t5\t0\n')
            (d/'sample.mot').write_text('name sample\nendheader\ntime\tright elbow\n0\t90\n')
    engine.process_fun=process_fun;api.process=process_fun;api.DEFAULT_CONFIG={};package.Sports2D=api;package.process=engine
    for name,value in [('Sports2D',package),('Sports2D.Sports2D',api),('Sports2D.process',engine)]:monkeypatch.setitem(sys.modules,name,value)
    monkeypatch.setattr(adapter,'availability',lambda:{'available':True,'supported':True,'version':'0.8.34'})
    monkeypatch.setattr(importlib.metadata,'version',lambda _: 'test')
    profile=sys.getprofile();context=ssl._create_default_https_context
    video=VideoMetadata(str(tmp_path/'video.mp4'),'hash',60,100,100,3,.05)
    if failure:
        with pytest.raises(RuntimeError,match='could not finish' if failure=='engine' else 'expected TRC'):
            Sports2DAdapter().analyze(video,tmp_path/'out',merged_config(),lambda *a:None)
    else:
        result=Sports2DAdapter().analyze(video,tmp_path/'out',merged_config(),lambda *a:None)
        assert result.frames[0].landmarks['right_wrist'].confidence==.2
        assert result.frames[0].landmarks['right_wrist'].x==50
        provenance=json.loads((tmp_path/'out/provenance.json').read_text())
        assert provenance['selected_person_index']==0 and provenance['sports2d_selected_person_index']==1
        assert result.backend=='sports2d' and result.frame_count==3
        assert (tmp_path/'out/provenance.json').exists()
        assert (tmp_path/'out/configuration.json').exists()
    assert sys.getprofile() is profile
    assert ssl._create_default_https_context is context


def test_event_candidates_never_use_long_missing_gap():
    from cornhole_biomech.events import detect_events
    wrist=np.column_stack((np.linspace(0,1,60),np.zeros(60)))
    wrist[15:45]=np.nan
    wrist[45:,0]+=10
    events=detect_events(wrist,60)
    for event in events.values():
        assert event.effective_frame is None or np.isfinite(wrist[event.effective_frame]).all()


def test_stationary_sequence_does_not_invent_release():
    from cornhole_biomech.events import detect_events
    assert all(e.effective_frame is None for e in detect_events(np.zeros((60,2)),60).values())


def test_pixel_trc_unit_repair_preserves_original_bytes_and_coordinates(tmp_path):
    from cornhole_biomech.sports2d_adapter import correct_pixel_trc_units
    p=tmp_path/'pixel.trc'
    original=b'PathFileType\t4\t(X/Y/Z)\tpixel.trc\nDataRate\tCameraRate\tNumFrames\tNumMarkers\tUnits\n60\t60\t1\t1\tm\nFrame#\tTime\tRWrist\t\t\n\t\tX1\tY1\tZ1\n1\t0\t450\t300\t0\n'
    p.write_bytes(original);before=read_trc(p)['coordinates'].copy()
    repair=correct_pixel_trc_units(p)
    assert p.with_suffix('.trc.original').read_bytes()==original
    assert repair['original_header_units']=='m'
    assert read_trc(p)['units']=='px'
    np.testing.assert_array_equal(read_trc(p)['coordinates'],before)
    assert correct_pixel_trc_units(p) is None


def test_compatibility_uses_method_version_not_source_hash():
    from cornhole_biomech.insights import compatible_key
    trial={'cameraView':'side','throwingSide':'right','sessionID':'S'}
    a={'method_version':'v1','engine_source_sha256':'aaa'}
    b={'method_version':'v1','engine_source_sha256':'bbb'}      # code edited, same definitions
    c={'method_version':'v2','engine_source_sha256':'aaa'}      # definitions changed
    legacy={'engine_source_sha256':'aaa'}
    assert compatible_key(trial,a)==compatible_key(trial,b)
    assert compatible_key(trial,a)!=compatible_key(trial,c)
    assert compatible_key(trial,legacy)!=compatible_key(trial,a)


def test_thrower_is_the_largest_steadily_tracked_person_not_the_most_confident():
    # Clip "playe1 - 7": a still bystander by the board out-scored the blurred
    # thrower on confidence (19.1 vs 18.05) at half the thrower's body height.
    from cornhole_biomech.sports2d_adapter import choose_thrower
    frames,kpts=100,8
    X=np.full((frames,3,kpts),np.nan);Y=np.full((frames,3,kpts),np.nan);S=np.full((frames,3,kpts),np.nan)
    X[:,0]=np.linspace(250,350,kpts);Y[:,0]=np.linspace(1150,1840,kpts);S[:,0]=.8    # thrower
    X[:,1]=np.linspace(3300,3340,kpts);Y[:,1]=np.linspace(1180,1520,kpts);S[:,1]=.9  # bystander
    X[:10,2]=np.linspace(1000,1400,kpts);Y[:10,2]=np.linspace(600,1900,kpts);S[:10,2]=.9  # brief passer-by
    choice=choose_thrower(X,Y,S)
    assert choice['person']==0
    assert [c['person'] for c in choice['candidates']][:2]==[0,1]
    assert choice['runner_up_ratio']<.6


def test_thrower_choice_needs_a_tracked_person():
    from cornhole_biomech.sports2d_adapter import choose_thrower
    empty=np.full((5,2,4),np.nan)
    assert choose_thrower(empty,empty,empty)['person'] is None


def test_bystander_boxes_cover_everyone_but_the_thrower_and_bridge_short_dropouts():
    from cornhole_biomech.sports2d_adapter import bystander_boxes
    frames,kpts=30,4
    X=np.full((frames,2,kpts),np.nan);Y=np.full((frames,2,kpts),np.nan)
    X[:,0]=[100,120,110,105];Y[:,0]=[500,700,600,800]              # thrower
    X[:,1]=[2800,2840,2820,2810];Y[:,1]=[1100,1200,1300,1400]      # bystander, 300 px tall
    X[10:13,1]=np.nan                                             # 3-frame detector dropout
    X[20:,1]=np.nan                                               # walked out of view
    boxes=bystander_boxes(X,Y,thrower=0,hold_frames=4)
    assert all(len(boxes[f])==1 for f in range(20))               # dropout bridged
    assert all(f not in boxes for f in range(25,30))              # not held forever
    x0,y0,x1,y1=boxes[0][0]
    assert x0<2800 and x1>2840 and y0<1100 and y1>1400            # padded around the keypoints
    assert x1<3000 and y0>1000


def test_candidates_inside_a_bystander_box_cannot_seed():
    from cornhole_biomech.auto_bag import Candidate
    from cornhole_biomech.scene import tag_bystanders
    boxes={5:[[2700.0,1000.0,2900.0,1500.0]]}
    tagged=tag_bystanders([Candidate(5,2800,1200,40),Candidate(5,1500,900,40),Candidate(6,2800,1200,40)],boxes)
    assert [c.in_person for c in tagged]==[True,False,False]


def test_bystander_box_on_the_thrower_is_dropped():
    # A fragment of the thrower's own track (ID switch) must not mask the hand at release.
    from cornhole_biomech.sports2d_adapter import bystander_boxes
    frames,kpts=10,4
    X=np.full((frames,3,kpts),np.nan);Y=np.full((frames,3,kpts),np.nan)
    X[:,0]=[100,300,200,150];Y[:,0]=[500,900,700,800]              # thrower
    X[:,1]=[120,280,200,160];Y[:,1]=[520,880,700,790]              # thrower fragment
    X[:,2]=[2800,2840,2820,2810];Y[:,2]=[1100,1200,1300,1400]      # real bystander
    boxes=bystander_boxes(X,Y,thrower=0)
    assert all(len(boxes[f])==1 and boxes[f][0][0]>2000 for f in range(frames))


def test_clip_too_large_for_memory_is_refused_before_decoding(monkeypatch):
    import cornhole_biomech.auto_bag as auto_bag
    class FakeCapture:
        def __init__(self,path):pass
        def get(self,prop):return {3:1920.0,4:1080.0,7:1500.0}[prop]
        def release(self):pass
    monkeypatch.setattr(auto_bag.cv2,'VideoCapture',FakeCapture)
    monkeypatch.setattr(auto_bag.os,'sysconf',lambda name:{'SC_PHYS_PAGES':4*1024**2,'SC_PAGE_SIZE':4096}[name])  # 16 GiB
    monkeypatch.setattr(auto_bag,'read_frames',lambda path,scale=1.0:(_ for _ in ()).throw(AssertionError('decoded anyway')))
    result=auto_bag.auto_track_bag('clip.mov',None,None,'left_to_right')
    assert result['status']=='not_found' and result['memory_limited']
    assert '9.3 GB' in result['reasons'][0] and 'Prepare Video' in result['reasons'][0]
    assert auto_bag.frame_memory_check('clip.mov',fraction=0.9) is None     # fits a larger budget
    FakeCapture.get=lambda self,prop:{3:3840.0,4:2160.0,7:369.0}[prop]
    assert auto_bag.frame_memory_check('clip.mov') is None                 # 4K is searched at 1080p: 2.3 GB
