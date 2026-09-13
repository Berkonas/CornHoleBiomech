"""Self-contained local HTML and focused figures, built only from stored results."""
from pathlib import Path
import base64
import html
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle


def board_figure(path, trials):
    fig,ax=plt.subplots(figsize=(4,6),layout='constrained')
    ax.add_patch(Rectangle((0,0),24,48,facecolor='#E4D4B8',edgecolor='#24394A',linewidth=2))
    ax.add_patch(Circle((12,39),3,facecolor='white',edgecolor='#24394A',linewidth=1.5))
    for kind,marker,color,label in [('intended_point','+','#244D70','Target'),('first_contact_point','o','#BB6849','First contact'),('final_resting_point','s','#427F83','Final rest')]:
        points=[t['outcome'].get(kind) for t in trials if t.get('outcome',{}).get(kind)]
        if points:ax.scatter([p['x_inches'] for p in points],[p['y_inches'] for p in points],marker=marker,color=color,label=label,s=45,zorder=3)
    ax.set(xlim=(-4,28),ylim=(-4,52),xlabel='Left → right (inches)',ylabel='Pitcher → back (inches)',title='Bag locations • approximate manual points')
    ax.set_aspect('equal');ax.grid(alpha=.15)
    if ax.get_legend_handles_labels()[0]:ax.legend(loc='lower center',fontsize=8)
    fig.savefig(path,dpi=160);plt.close(fig)


def create_report(directory, insight, normalized, comparison):
    directory=Path(directory)
    from .export import plot_angles_angles, plot_wrist_trajectory
    values={key:np.asarray(value,float) for key,value in normalized['values'].items()}
    plot_angles_angles(directory/'angle_trajectories.png',np.asarray(normalized['tau']),values,'Projected upper-body angles')
    if 'wrist_path_arm_lengths' in values:
        plot_wrist_trajectory(directory/'wrist_trajectory.png',values['wrist_path_arm_lengths'],'Shoulder-relative wrist path')
    # These are app-generated optional plots; remove stale previous summaries.
    for name in ('comparison_elbow_angle.png', 'reference_deviation.png', 'consistency.png', 'performance_relationship.png'):
        (directory/name).unlink(missing_ok=True)
    board_figure(directory/'board_outcome.png',insight['board_trials'])
    images=['angle_trajectories.png','wrist_trajectory.png','board_outcome.png']
    if comparison:
        from .export import plot_comparison
        c=comparison['curves']
        for field,name in [('elbow_angle_deg','comparison_elbow_angle.png')]:
            if field in c['test']:
                plot_comparison(directory/name,np.asarray(c['tau']),np.asarray(c['test'][field],float),np.asarray(c['reference_mean'][field],float),np.asarray(c['reference_sd'][field],float),'Projected elbow included angle',len(comparison['reference_trial_ids']))
                images.insert(0,name)
        fig,ax=plt.subplots(figsize=(6,5),layout='constrained')
        for key,label,color in [('reference_mean','Reference','#78838D'),('test','Athlete','#247F8A')]:
            a=np.asarray(c[key].get('wrist_path_arm_lengths',[]),float)
            if a.size:ax.plot(a[:,0],a[:,1],color=color,label=label)
        ax.set_aspect('equal',adjustable='datalim');ax.set(xlabel='Toward target (arm lengths)',ylabel='Up (arm lengths)',title='Normalized wrist path');ax.legend();ax.grid(alpha=.2)
        fig.savefig(directory/'reference_deviation.png',dpi=160);plt.close(fig);images.append('reference_deviation.png')
    con=insight['consistency']
    if con.get('curves',{}).get('elbow_angle_deg'):
        curve=con['curves']['elbow_angle_deg'];x=100*np.asarray(con['tau']);mean=np.asarray(curve['mean'],float);sd=np.asarray(curve['sd'],float)
        fig,ax=plt.subplots(figsize=(8,4),layout='constrained')
        for trace in con['traces']:ax.plot(x,trace['elbow'],color='#247F8A',alpha=.15)
        ax.plot(x,mean,color='#247F8A',label='Athlete mean');ax.fill_between(x,mean-sd,mean+sd,color='#247F8A',alpha=.15,label='±1 sample SD')
        ax.set(xlabel='Movement cycle (%)',ylabel='Elbow included angle (degrees)',title=f"Repeatability across {con['n']} throws");ax.legend()
        fig.savefig(directory/'consistency.png',dpi=160);plt.close(fig);images.append('consistency.png')
    rel=insight.get('relationships') or {};estimated=[k for k,v in rel.get('relationships',{}).items() if v.get('status')=='estimated']
    if estimated:
        feature=estimated[0];outcome=rel['outcome_variable'];rows=[r for r in rel['data_rows'] if r.get(feature) is not None and r.get(outcome) is not None]
        fig,ax=plt.subplots(figsize=(7,4),layout='constrained');ax.scatter([r[feature] for r in rows],[r[outcome] for r in rows],color='#247F8A');ax.set(xlabel=feature.replace('_',' '),ylabel=outcome.replace('_',' '),title=f"Exploratory relationship • n={len(rows)}");fig.savefig(directory/'performance_relationship.png',dpi=160);plt.close(fig);images.append('performance_relationship.png')
    esc=lambda v:html.escape(str(v))
    fmt=lambda v:'Unavailable' if v is None else f'{v:.1f}'
    task=insight.get('outcome');score=insight.get('similarity') or {};quality=insight['quality']
    summary_path = directory / 'results.json'
    summaries = json.loads(summary_path.read_text()).get('summaries', {}) if summary_path.exists() else {}
    measures = [
        ('Elbow included angle at release', 'elbow_angle_deg_at_release', '°'),
        ('Trunk inclination at release', 'trunk_inclination_deg_at_release', '°'),
        ('Forward-swing wrist travel', 'wrist_forward_swing_path_length_arm_lengths', ' arm lengths'),
        ('Movement duration', 'movement_duration_seconds', ' s'),
    ]
    measurement_cards = ''.join(f'<div><b>{fmt(summaries.get(key))}{unit if summaries.get(key) is not None else ""}</b>{label}</div>' for label, key, unit in measures)
    rows=''.join(f"<tr><td>{esc(d['name'])}</td><td>{d['amount']:.2f} {esc(d['units'])}</td><td>{esc(d['explanation'])}</td></tr>" for d in insight['differences'][:3])
    figures=''.join(f'<figure><img alt="{esc(name.replace("_"," "))}" src="data:image/png;base64,{base64.b64encode((directory/name).read_bytes()).decode()}"></figure>' for name in images if (directory/name).exists())
    warnings=''.join(f'<li>{esc(w)}</li>' for w in insight['warnings'])
    components=''.join(f"<tr><td>{esc(k.replace('_',' '))}</td><td>{v['raw_error']:.2f} {esc(v.get('units',''))}</td><td>{v['tolerance']}</td><td>{v['weight']}</td><td>{v['score']:.1f}</td></tr>" for k,v in score.get('components',{}).items())
    report=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Throw report — {esc(insight['trial_name'])}</title>
<style>body{{font:16px/1.6 -apple-system,BlinkMacSystemFont,sans-serif;color:#233647;background:#f8f7f3;max-width:1000px;margin:40px auto;padding:0 28px}}h1{{font-size:34px;line-height:1.2}}h2{{margin-top:32px;font-size:21px}}small{{color:#586570}}header{{border-bottom:3px solid #267B86;padding-bottom:24px}}.numbers{{display:flex;flex-wrap:wrap;gap:28px;margin:25px 0}}.numbers b{{display:block;font-size:28px}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{text-align:left;padding:10px;border-bottom:1px solid #d4d9dc}}img{{width:100%;height:auto;max-height:540px;object-fit:contain}}figure{{margin:24px 0}}@media print{{body{{background:white;margin:0}}figure,tr{{break-inside:avoid}}}}</style>
<header><small>CORNHOLE BIOMECHANICS LAB · LOCAL TRIAL REPORT</small><h1>{esc(insight['athlete'])}</h1><p>{esc(insight['trial_name'])} · {esc(insight['date'])}</p></header>
<h2>Projected movement measurements</h2><div class="numbers">{measurement_cards}</div>
<p>Observed bag result: <strong>{str(task['score_category'])+' points' if task else 'Not recorded'}</strong>. An elbow included angle of 180° is straight in this camera projection. Review landmarks and release before interpretation.</p>
<details><summary>Experimental indices — not validated skill scores</summary><p>Reference similarity: {fmt(score.get('overall'))}/100 · Tracking quality: {fmt(quality.get('score'))}/100 · Athlete consistency: {fmt(con.get('score'))}/100</p></details>
<p>{esc(insight['coach_summary'])}</p><ul>{warnings}</ul>
<h2>Largest movement differences</h2><table>{rows or '<tr><td>Run a compatible reference comparison.</td></tr>'}</table>
<h2>Measurements and movement</h2>{figures}
<h2>How Reference Similarity is calculated</h2><p>Component = 100 × max(0, 1 − error / tolerance). Total = weighted mean. Tolerances are pilot settings.</p><table><tr><th>Component</th><th>Error</th><th>Tolerance</th><th>Weight</th><th>Score</th></tr>{components}</table>
<h2>Measurement context</h2><p>{esc(insight['provenance']['camera_view'])} view · {quality['frame_rate_fps']:.2f} fps · {quality['resolution_pixels']['width']} × {quality['resolution_pixels']['height']} pixels</p><p>Backend: {esc(insight['provenance']['backend'])} · model: {esc(insight['provenance']['model'])} · Sports2D: {esc(insight['provenance'].get('sports2d_version') or 'not used')}</p><p>{esc(quality.get('score_note','Reanalyze to calculate the quality index.'))}</p><p>{esc(con.get('equation','Consistency requires at least five comparable valid trials.'))}</p>
<h2>Limits of this measurement</h2><p>These are projected 2D measurements. Camera perspective, occlusion and markerless joint estimates affect them. Automatic release is a frame-level candidate from reviewed bag–wrist divergence when available, otherwise from wrist motion; manual review remains authoritative. Bag launch quantities are suppressed unless the complete fit interval is explicitly reviewed. Manual board points are approximate. Similarity describes the selected reference. Repeatability does not establish accuracy. Associations do not establish causation. Real participant and criterion validation remain required.</p><small>Analysis ID: {esc(insight['provenance'].get('analysis_id'))}. Full settings, source hashes, raw pose and corrections accompany the research export.</small></html>'''
    (directory/'report.html').write_text(report)
    (directory/'summary.md').write_text(f"# {insight['athlete']} — {insight['trial_name']}\n\n{insight['coach_summary']}\n\n"+'\n'.join('- '+w for w in insight['warnings'])+'\n')
