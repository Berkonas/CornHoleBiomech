import cv2
import numpy as np
import pytest
from cornhole_biomech.preparation import prepare_video
from cornhole_biomech.video import file_sha256
from cornhole_biomech.pipeline import _summary_units


@pytest.fixture
def recording(tmp_path):
    path = tmp_path / 'original.avi'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 30, (80, 60))
    assert writer.isOpened()
    for i in range(12):
        image = np.full((60, 80, 3), i * 15, np.uint8)
        image[:30, :40, 2] = 250
        writer.write(image)
    writer.release()
    return path


@pytest.mark.parametrize('rotation,size', [(0,(40,20)), (90,(20,40)), (180,(40,20)), (270,(20,40))])
def test_preparation_preserves_original_frame_mapping_and_geometry(recording, tmp_path, rotation, size):
    original_hash = file_sha256(recording)
    output = tmp_path / 'prepared.mp4'
    manifest = prepare_video(recording, output, 3, 9, [10, 10, 40, 20], rotation)
    assert file_sha256(recording) == original_hash
    assert manifest['derived']['frame_count'] == 6
    assert manifest['derived']['fps'] == 30
    assert (manifest['derived']['width'], manifest['derived']['height']) == size
    assert manifest['start_frame_inclusive'] == 3
    assert manifest['resized'] is False
    assert output.with_suffix('.preparation.json').exists()
    cap = cv2.VideoCapture(str(output)); ok, first = cap.read(); cap.release()
    assert ok and abs(float(first[..., 0].mean()) - 45) < 8
    with pytest.raises(ValueError, match='overwritten'):
        prepare_video(recording, output)


@pytest.mark.parametrize('kwargs', [dict(start_frame=-1), dict(end_frame=13), dict(start_frame=5,end_frame=5), dict(crop=[-1,0,40,20]), dict(crop=[0,0,41,20]), dict(crop=[70,0,40,20]), dict(rotation=45)])
def test_invalid_edits_do_not_create_output(recording, tmp_path, kwargs):
    output = tmp_path / 'invalid.mp4'
    with pytest.raises(ValueError): prepare_video(recording, output, **kwargs)
    assert not output.exists()


def test_original_cannot_be_overwritten(recording):
    before = file_sha256(recording)
    with pytest.raises(ValueError): prepare_video(recording, recording)
    assert file_sha256(recording) == before


def test_analysis_rejects_mismatched_preparation_provenance(recording, tmp_path):
    import json
    from cornhole_biomech.pipeline import analyze_trial
    from cornhole_biomech.models import TrialContext
    output = tmp_path / 'prepared.mp4'
    manifest = prepare_video(recording, output)
    manifest['derived']['sha256'] = 'wrong-recording'
    output.with_suffix('.preparation.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='provenance does not match'):
        analyze_trial(TrialContext('T1', 'A1', 'side', 'right', 'left_to_right', str(output)), tmp_path / 'analysis')


@pytest.mark.parametrize('name', ['elbow_angle_velocity_deg_s_peak_abs', 'elbow_angle_velocity_deg_s_mean', 'shoulder_wrist_peak_angular_velocity_forward_swing_deg_s'])
def test_derivative_units_are_not_angle_units(name):
    assert _summary_units(name) == 'degrees/s'
