#!/usr/bin/env python3
"""Audit one Sports2D analysis using saved raw pixels and upstream angle code.

This verifies data/convention compatibility, not human biomechanical validity.
"""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import matplotlib
import numpy as np
import cv2
from cornhole_biomech.models import PoseSequence
from cornhole_biomech.geometry import vector_angle_degrees
from cornhole_biomech.sports2d_adapter import read_trc, read_mot, elbow_included_from_sports2d


def validate(directory):
    directory=Path(directory)
    pose=PoseSequence.load(directory/'pose_raw.json')
    matplotlib.use('Agg',force=True)
    real_use=matplotlib.use
    with patch.object(matplotlib,'use',side_effect=lambda *a,**kw:real_use('Agg',force=True)):
        from Pose2Sim.common import fixed_angles
    errors=[]
    for side in ('left','right'):
        for frame in pose.frames:
            points=[frame.landmarks[f'{side}_{joint}'] for joint in ('wrist','elbow','shoulder')]
            coords=np.array([[p.x,p.y] for p in points],float)
            if np.isfinite(coords).all():
                included=vector_angle_degrees(coords[0],coords[1],coords[2])
                upstream=fixed_angles(coords,f'{side} elbow')
                errors.append(abs(float(included)-float(elbow_included_from_sports2d(upstream))))
    assert errors and max(errors)<1e-8, 'Elbow convention mismatch'
    files={}
    for p in (directory/'sports2d').rglob('*.trc'):
        d=read_trc(p);files[p.name]={'samples':len(d['time']),'units':d['units']}
    for p in (directory/'sports2d').rglob('*.mot'):
        d=read_mot(p);files[p.name]={'samples':len(next(iter(d.values()))),'columns':list(d)}
    videos={}
    for p in directory.rglob('*.mp4'):
        cap=cv2.VideoCapture(str(p));readable,frame=cap.read()
        videos[p.name]={'readable':readable,'frames':int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),'fps':cap.get(cv2.CAP_PROP_FPS)}
        cap.release()
        assert readable, f'Unreadable annotation: {p.name}'
    assert files and videos, 'Missing expected scientific exports'
    return {'scope':'software convention and export audit only','raw_frames':pose.frame_count,'elbow_samples':len(errors),
            'maximum_elbow_convention_error_degrees':max(errors),'scientific_files':files,'videos':videos}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--analysis',required=True)
    print(json.dumps(validate(parser.parse_args().analysis),indent=2))
