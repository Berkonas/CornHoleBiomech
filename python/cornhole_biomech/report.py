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
    if insight.get('needs_reanalysis'):
        (directory/'report.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Reanalysis required</title><h1>Reanalysis required</h1><p>Tracking or event corrections changed. Review and reanalyze this throw before interpreting or exporting measurements.</p></html>')
        return
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
    task=insight.get('outcome');quality=insight['quality']
    summary_path = directory / 'results.json'
    summaries = json.loads(summary_path.read_text()).get('summaries', {}) if summary_path.exists() else {}
    scaled = summaries.get('bag_release_speed_m_s') is not None
    measures = [
        ('Release angle', 'bag_release_angle_deg', '°'),
        ('Release speed', 'bag_release_speed_m_s' if scaled else 'bag_release_speed_arm_lengths_s', ' m/s' if scaled else ' arm lengths/s'),
        ('Release height', 'bag_release_height_m' if summaries.get('bag_release_height_m') is not None else 'bag_release_height_arm_lengths',
         ' m' if summaries.get('bag_release_height_m') is not None else ' arm lengths'),
        ('Elbow included angle at release', 'elbow_angle_deg_at_release', '°'),
        ('Release to first contact', 'bag_time_of_flight_seconds', ' s'),
    ]
    measurement_cards = ''.join(f'<div><b>{fmt(summaries.get(key))}{unit if summaries.get(key) is not None else ""}</b>{label}</div>' for label, key, unit in measures)
    rows=''.join(f"<tr><td>{esc(d['name'])}</td><td>{d['amount']:.2f} {esc(d['units'])}</td><td>{esc(d['explanation'])}</td></tr>" for d in insight['differences'][:3])
    figures=''.join(f'<figure><img alt="{esc(name.replace("_"," "))}" src="data:image/png;base64,{base64.b64encode((directory/name).read_bytes()).decode()}"></figure>' for name in images if (directory/name).exists())
    warnings=''.join(f'<li>{esc(w)}</li>' for w in insight['warnings'])
    feedback=(insight.get('performance') or {}).get('summary',{}).get('feedback')
    summary_block=('<h2>Athlete summary</h2><table>'
                   f"<tr><th>Result</th><td>{esc(feedback['result'])}</td></tr>"
                   f"<tr><th>What differed</th><td>{esc(feedback['why'])}</td></tr>"
                   f"<tr><th>Next practice</th><td>{esc(feedback['next'])}</td></tr></table>"
                   f"<p><small>{esc(feedback['caveat'])}</small></p>") if feedback else f"<p>{esc(insight['coach_summary'])}</p>"
    arm_section = arm_motion_report(directory, normalized, insight.get('needs_reanalysis', False))
    full_throw_section = full_throw_report(directory, insight)
    report=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Throw report — {esc(insight['trial_name'])}</title>
<style>body{{font:16px/1.6 -apple-system,BlinkMacSystemFont,sans-serif;color:#233647;background:#f8f7f3;max-width:1000px;margin:40px auto;padding:0 28px}}h1{{font-size:34px;line-height:1.2}}h2{{margin-top:32px;font-size:21px}}small{{color:#586570}}header{{border-bottom:3px solid #267B86;padding-bottom:24px}}.numbers{{display:flex;flex-wrap:wrap;gap:28px;margin:25px 0}}.numbers b{{display:block;font-size:28px}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{text-align:left;padding:10px;border-bottom:1px solid #d4d9dc}}img{{width:100%;height:auto;max-height:540px;object-fit:contain}}figure{{margin:24px 0}}@media print{{body{{background:white;margin:0}}figure,tr{{break-inside:avoid}}}}</style>
<header><small>CORNHOLE BIOMECHANICS LAB · LOCAL TRIAL REPORT</small><h1>{esc(insight['athlete'])}</h1><p>{esc(insight['trial_name'])} · {esc(insight['date'])}</p></header>
<h2>Body → release → flight → outcome</h2><div class="numbers">{measurement_cards}</div>
<p>Observed bag result: <strong>{str(task['score_category'])+' points' if task and task.get('score_category') is not None else 'Unknown / not observed'}</strong>. An elbow included angle of 180° is straight in this camera projection. Review landmarks and release before interpretation.</p>
{summary_block}<ul>{warnings}</ul>
{full_throw_section}
<details><summary>Advanced body mechanics and reference comparison</summary>
<h2>Largest movement differences</h2><table>{rows or '<tr><td>Run a compatible reference comparison.</td></tr>'}</table>
{arm_section}
<h2>Measurements and movement</h2>{figures}
</details>
<h2>Measurement context</h2><p>{esc(insight['provenance']['camera_view'])} view · {quality['frame_rate_fps']:.2f} fps · {quality['resolution_pixels']['width']} × {quality['resolution_pixels']['height']} pixels</p><p>Backend: {esc(insight['provenance']['backend'])} · model: {esc(insight['provenance']['model'])} · Sports2D: {esc(insight['provenance'].get('sports2d_version') or 'not used')}</p><p>Usable frames: {fmt(quality.get('usable_frame_percentage'))}% · release-window visibility: {fmt(None if quality.get('release_visibility') is None else 100*quality['release_visibility'])}%</p><p>Repeatability: {esc(con.get('equation','Needs at least five comparable valid trials.'))}</p>
<h2>Limits of this measurement</h2><p>These are projected 2D measurements. Camera perspective, occlusion and markerless joint estimates affect them. Automatic release is a frame-level candidate from reviewed bag–wrist divergence when available, otherwise from wrist motion; manual review remains authoritative. Bag launch quantities are suppressed unless the complete fit interval is explicitly reviewed. Manual board points are approximate. Reference comparisons describe resemblance, not quality. Repeatability does not establish accuracy. Associations do not establish causation. Real participant and criterion validation remain required.</p><small>Analysis ID: {esc(insight['provenance'].get('analysis_id'))}. Full settings, source hashes, raw pose and corrections accompany the research export.</small></html>'''
    (directory/'report.html').write_text(report)
    (directory/'summary.md').write_text(f"# {insight['athlete']} — {insight['trial_name']}\n\n{insight['coach_summary']}\n\n"+'\n'.join('- '+w for w in insight['warnings'])+'\n')


def arm_motion_report(directory, normalized, stale=False):
    """Export measured arm descriptors with the same gates as the native UI."""
    from .arm_motion import ARM_METRICS
    image_path = directory / "arm_motion.png"
    image_path.unlink(missing_ok=True)
    result_path = directory / "results.json"
    result = json.loads(result_path.read_text()).get("arm_motion") if result_path.exists() else None
    heading = "<h2>Elbow motion during the forward swing</h2>"
    if stale:
        return heading + "<p>Corrections changed. Reanalyze before interpreting arm-motion measurements.</p>"
    if not result:
        return heading + "<p>Reanalyze to calculate the new arm-motion metrics.</p>"
    section = heading + "<p>" + html.escape(result["message"]) + "</p>"
    if result.get("coverage") is not None:
        section += (f'<p>Forward swing → release, frames {result["start_frame"]}–{result["release_frame"]} '
                    f'(zero-based, inclusive). Elbow coverage: {result["valid_sample_count"]}/{result["sample_count"]} '
                    f'({100*result["coverage"]:.1f}%). At least 5 samples and 80% coverage required; '
                    'practical availability gates, not validated accuracy thresholds.</p>')
    if result["status"] == "available":
        rows = []
        for key, label in ARM_METRICS.items():
            value = result["summaries"].get(key)
            text = "Unavailable" if value is None else f"{value:.4f}" if key.endswith("ratio") else f"{value:.2f}"
            rows.append(f"<tr><td>{label}</td><td>{text}</td></tr>")
        section += "<table>" + "".join(rows) + "</table>"
        radius_coverage = result.get("radius_coverage")
        section += f'<p>Radius coverage: {"unavailable" if radius_coverage is None else f"{radius_coverage*100:.1f}%"}. CV is sample SD / mean positive shoulder–wrist radius.</p>'
        values = normalized.get("values", {}).get("elbow_angle_deg")
        if values is not None:
            x = 100*np.asarray(normalized["tau"], float)
            flex = 180 - np.asarray(values, float)
            fig, ax = plt.subplots(figsize=(8, 3.8), layout="constrained")
            timing = normalized.get("event_timing", {})
            start, release = timing.get("forward_swing"), timing.get("release")
            if start is not None and release is not None and start < release:
                ax.axvspan(start*100, release*100, alpha=.09, color="#247F8A", label="Forward swing → release")
                ax.axvline(release*100, color="#BB6849", linewidth=1, label="Release")
            ax.plot(x, flex, color="#247F8A", linewidth=2, label="Projected flexion")
            ax.set(xlim=(0,100), ylim=(0,180), xlabel="Movement cycle (%)", ylabel="Elbow flexion (°)", title="Elbow motion • 0° is straight in this projection")
            ax.grid(alpha=.15); ax.legend(fontsize=8)
            fig.savefig(image_path,dpi=160); plt.close(fig)
            section += '<figure><img alt="Projected elbow flexion with forward swing to release shaded" src="data:image/png;base64,' + base64.b64encode(image_path.read_bytes()).decode() + '"></figure>'
    section += ('<p>Flexion = 180° − included elbow angle. Excursion = maximum − minimum. SD uses n − 1. '
                'Summaries use native-rate filtered samples; the figure uses the normalized cycle. Missing intervals '
                'can hide peaks. Low excursion describes a more fixed elbow within one throw; a fixed bent arm '
                'can also act as one rigid link. Repeatability requires multiple throws. These descriptors do not '
                'measure torque or establish better performance.</p>')
    return section


def full_throw_report(directory, insight):
    """Report the same endpoint definitions and empirical feedback as UI."""
    esc=lambda v:html.escape(str(v))
    results=json.loads((directory/'results.json').read_text())
    flight=results.get('flight',{})
    content='<h2>Bag flight and performance</h2><p>'+esc(flight.get('message','Reanalyze for flight review.'))+'</p>'
    points=flight.get('trajectory',[])
    if points:
        a=np.array([[p['x'],p['y']] for p in points],float)
        fig,ax=plt.subplots(figsize=(8,3.5),layout='constrained')
        ax.plot(a[:,0],a[:,1],'.-',color='#247F8A',markersize=3)
        ax.invert_yaxis();ax.set_aspect('equal',adjustable='datalim')
        ax.set(xlabel='Image x (pixels)',ylabel='Image y (pixels, down)',title='Reviewed image trajectory — gaps remain missing')
        fig.savefig(directory/'bag_flight.png',dpi=150);plt.close(fig)
        content+='<img alt="Reviewed image-plane bag path" src="data:image/png;base64,'+base64.b64encode((directory/'bag_flight.png').read_bytes()).decode()+'">'
    task=insight.get('outcome') or {}
    for name,key in [('First-contact target error','first_contact_error'),('Final-rest target error','final_resting_error')]:
        error=task.get(key)
        content+='<p>'+name+': '+(f"{error['radial_error_inches']:.1f} in" if error else 'unavailable')+'</p>'
    performance=insight.get('performance',{})
    d=performance.get('first_contact',{})
    radius=d.get('rms_radius_inches')
    content+='<p>First-contact grouping RMS radius: '+(f'{radius:.1f} in' if radius is not None else 'unavailable')+f"; n={d.get('n',0)}. "+esc(d.get('note',''))+'</p>'
    summary=performance.get('summary') or {}
    variables=summary.get('variables') or {}
    if variables:
        content+='<h2>Scored vs missed throws</h2><table><tr><th>Measure</th><th>Scored median (middle half)</th><th>Missed median (middle half)</th><th>n scored / missed</th><th>Cliff’s δ</th><th>Differed?</th></tr>'
        def cell(g,v):
            if g.get('median') is None: return '—'
            d=v['decimals'];return f"{g['median']:.{d}f} ({g['q25']:.{d}f}–{g['q75']:.{d}f}) {esc(v['unit'])}"
        for v in variables.values():
            delta='—' if v.get('cliffs_delta') is None else f"{v['cliffs_delta']:.2f}"
            verdict='yes' if v['distinguishes'] else 'within measurement error' if v['below_noise_floor'] else 'no'
            content+=f"<tr><td>{esc(v['label'])}</td><td>{cell(v['scored'],v)}</td><td>{cell(v['miss'],v)}</td><td>{v['n_scored']} / {v['n_miss']}</td><td>{delta}</td><td>{verdict}</td></tr>"
        content+='</table><p><small>'+esc(summary.get('method',''))+'</small></p>'
    return content

