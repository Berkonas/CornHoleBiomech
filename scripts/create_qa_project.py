#!/usr/bin/env python3
"""Create clearly labeled synthetic software-QA data, never participant evidence."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
import json
import uuid
import cv2
import numpy as np
from cornhole_biomech.models import PointEstimate,PoseFrame,PoseSequence,TrialContext
from cornhole_biomech.pipeline import analyze_trial,compare_trial
from cornhole_biomech.insights import generate_insights


def create(destination):
    root=Path(destination).resolve()
    if root.exists():raise ValueError('Choose a new QA folder; existing data is never overwritten.')
    for name in ['videos','analyses','comparisons','exports','relationships']:(root/name).mkdir(parents=True,exist_ok=True)
    aid=str(uuid.uuid4()).upper();sid=str(uuid.uuid4()).upper();date='2026-09-07T15:00:00Z'
    project={'schemaVersion':1,'appVersion':'0.2.0','id':str(uuid.uuid4()).upper(),'name':'SYNTHETIC QA — Not participant data','createdAt':date,'updatedAt':date,
             'athletes':[{'id':aid,'participantCode':'SYNTHETIC QA Athlete — repeated-throw software test','dominantHand':'right','notes':'Synthetic kinematics. Not participant or validation data.'}],
             'trials':[],'analysisSettings':{'confidenceThreshold':.35,'maxInterpolationGapFrames':3,'filterEnabled':True,'filterOrder':4,'filterCutoffHz':6.,'normalizationSamples':101,'minimumRelationshipTrials':8,'poseBackend':'sports2d','poseModel':'body_with_feet','poseMode':'balanced'},
             'sessions':[{'id':sid,'athleteID':aid,'name':'Synthetic QA session','date':date,'cameraSetup':'Synthetic fixed 640×480 image plane','cameraView':'side','throwingSide':'right','targetDirection':'left_to_right','notes':'Software testing only','referenceTrialIDs':[]}]}
    for k in range(9):
        tid=str(uuid.uuid4()).upper();video=root/'videos'/f'SYNTHETIC-QA-throw-{k+1:02}.mp4';output=root/'analyses'/tid
        frames=[];writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),60,(640,480))
        for i,t in enumerate(np.linspace(0,1,90)):
            theta=-1.0+1.5*np.sin((t-.3)*np.pi); elbow=(300+95*np.sin(theta),165+95*np.cos(theta)); fore=theta+.35+.035*k*np.sin(np.pi*t)
            wrist=(elbow[0]+90*np.sin(fore),elbow[1]+90*np.cos(fore))
            points={'left_shoulder':(275,165),'right_shoulder':(300,165),'left_hip':(278,340),'right_hip':(308,340),'left_elbow':(254,243),'left_wrist':(250,325),'right_elbow':elbow,'right_wrist':wrist}
            image=np.full((480,640,3),(41,37,29),np.uint8)
            for a,b in [('left_shoulder','right_shoulder'),('left_hip','right_hip'),('left_shoulder','left_hip'),('right_shoulder','right_hip'),('right_shoulder','right_elbow'),('right_elbow','right_wrist'),('left_shoulder','left_elbow'),('left_elbow','left_wrist')]:cv2.line(image,tuple(map(int,points[a])),tuple(map(int,points[b])),(198,205,210),4,cv2.LINE_AA)
            for xy in points.values():cv2.circle(image,tuple(map(int,xy)),6,(152,161,71),-1,cv2.LINE_AA)
            cv2.putText(image,'SYNTHETIC QA - NOT PARTICIPANT DATA',(24,40),cv2.FONT_HERSHEY_SIMPLEX,.6,(210,210,210),1,cv2.LINE_AA)
            cv2.putText(image,f'Throw {k+1:02}   Frame {i:02}',(24,440),cv2.FONT_HERSHEY_SIMPLEX,.5,(210,210,210),1,cv2.LINE_AA)
            writer.write(image)
            frames.append(PoseFrame(i,i/60,{n:PointEstimate(float(x),float(y),.96) for n,(x,y) in points.items()}))
        writer.release();pose=root/f'qa-pose-{k}.json';PoseSequence(1,60,640,480,90,'synthetic_qa','known_geometry','1',frames).save(pose)
        analyze_trial(TrialContext(tid,aid,'side','right','left_to_right',str(video)),output,pose_input=pose,make_annotated_video=True)
        outcome={'intended_target':'Hole center','score_category':[3,3,1,1,0,1,0,0,1][k],'throw_type':'Synthetic QA','notes':'Not observed performance','intended_point':{'x_inches':12,'y_inches':39,'precision':'synthetic_qa'},'first_contact_point':{'x_inches':12+k*.65,'y_inches':39-k*1.1,'precision':'synthetic_qa'},'final_resting_point':{'x_inches':12+k*.5,'y_inches':39-k*.5,'precision':'synthetic_qa'}}
        project['trials'].append({'id':tid,'athleteID':aid,'sessionID':sid,'createdAt':date,'sourceVideoRelativePath':str(video.relative_to(root)),'originalFilename':video.name,'cameraView':'side','throwingSide':'right','targetDirection':'left_to_right','outcome':outcome,'isReference':k<2,'analysisRelativePath':str(output.relative_to(root)),'analysisStatus':'Analyzed — synthetic QA'})
    project['sessions'][0]['referenceTrialIDs']=[t['id'] for t in project['trials'] if t['isReference']]
    (root/'project.json').write_text(json.dumps(project,indent=2))
    for trial in project['trials'][2:]:compare_trial(root/trial['analysisRelativePath'],[root/t['analysisRelativePath'] for t in project['trials'][:2]],root/'comparisons'/trial['id'])
    generate_insights(root,project['trials'][4]['id'])
    print(root)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);create(p.parse_args().output)
