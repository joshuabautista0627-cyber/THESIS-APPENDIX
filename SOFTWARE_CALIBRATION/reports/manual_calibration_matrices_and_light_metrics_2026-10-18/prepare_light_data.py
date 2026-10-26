"""Read original manual CSV measurements and match saved held-out frame IDs.

These are acquisition-time optical measurements, not a replacement for the
video-recomputed features used to train the models. No model is fitted here.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import zipfile
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
RUN = ROOT / 'calibration_gui/analysis_outputs/live_sensor_manual_only/model_runs/tuning_20260909'
ARCHIVE_HASH = 'e039dcd49f3390d34dc979490dcf46a6ecc43d9e6a2aec08e4952acc14b5006a'
PRED_HASH = 'fda648280f60ca250e10a2e34e546a1677ae0a7cf0e7a6261c1bb9a3982e1817'

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--archive', type=Path, default=Path('C:/Users/DLSU/Downloads/THESIS DATA/Data Collection/Manual Calibration (2).zip'))
    args = ap.parse_args()
    data = OUT / 'data'
    data.mkdir(parents=True, exist_ok=True)
    checks = []
    def check(label, condition):
        assert condition, label
        checks.append(label)
    check('Original manual archive SHA-256 matches training provenance', sha(args.archive) == ARCHIVE_HASH)
    check('Saved prediction SHA-256 matches previous figure audit', sha(RUN/'outer_predictions.parquet') == PRED_HASH)
    p = pd.read_parquet(RUN/'outer_predictions.parquet')
    p = p[(p.model == 'Tuned selected') & p.task.isin(['contact', 'localization'])].copy()
    p.to_parquet(data/'held_out_predictions.parquet', index=False)
    c = p[p.task == 'contact'].copy()
    check('Exactly 8506 contact rows from 65 recordings', len(c) == 8506 and c.session_id.nunique() == 65)
    suffixes = ['area', 'mean_v', 'max_v', 'delta_v_sum', 'delta_v_sum_per_pixel', 'active_pixel_count', 'active_fraction']
    fields = ['capture_frame_id', 'elapsed_time_s', 'target_roi_ground_truth', 'frame_valid', 'baseline_valid']
    fields += [f'roi{i}_{s}' for i in range(1, 10) for s in suffixes]
    parts, members = [], []
    with zipfile.ZipFile(args.archive) as archive:
        candidates = [n for n in archive.namelist() if n.endswith('/frame_features.csv')]
        by_session = {n.split('/')[-2]: n for n in candidates}
        for sid, expected in c.groupby('session_id', sort=True):
            member = by_session[sid]
            baseline = json.loads(archive.read(member.rsplit('/',1)[0]+'/baseline_summary.json'))
            check(f'{sid}: saved active threshold is 10', baseline['processing_settings']['active_delta_v_threshold'] == 10)
            raw = archive.read(member)
            d = pd.read_csv(io.BytesIO(raw), usecols=fields)
            check(f'{sid}: unique capture IDs', not d.capture_frame_id.duplicated().any())
            d['frame_uid'] = [hashlib.sha256(f'{ARCHIVE_HASH}|{sid}|{index}|{int(cid)}'.encode()).hexdigest()
                              for index, cid in enumerate(d.capture_frame_id)]
            # Exact stable ID join; there is no nearest-time matching or row guessing.
            d = d[d.frame_uid.isin(expected.frame_uid)].copy()
            check(f'{sid}: every held-out frame has exactly one optical row', set(d.frame_uid) == set(expected.frame_uid))
            d = expected[['frame_uid', 'session_id', 'group', 'scientific_role', 'target_roi',
                          'capture_monotonic_relative_s', 'truth', 'reference_force_N']].merge(d, on='frame_uid', validate='one_to_one')
            check(f'{sid}: capture timestamps agree', np.allclose(d.elapsed_time_s, d.capture_monotonic_relative_s, rtol=0, atol=1e-9))
            check(f'{sid}: source validity flags pass', d.frame_valid.all() and d.baseline_valid.all())
            if (d.scientific_role == 'model_primary').all():
                check(f'{sid}: target labels agree', d.target_roi.eq(d.target_roi_ground_truth).all())
            parts.append(d)
            members.append({'session_id': sid, 'member': member, 'source_rows': len(pd.read_csv(io.BytesIO(raw), usecols=['capture_frame_id'])),
                            'selected_rows': len(d), 'source_sha256': hashlib.sha256(raw).hexdigest()})
    optical = pd.concat(parts, ignore_index=True)
    numeric = [f'roi{i}_{s}' for i in range(1, 10) for s in suffixes]
    check('Optical values are finite', np.isfinite(optical[numeric].to_numpy(float)).all())
    check('Frame IDs unique after join', not optical.frame_uid.duplicated().any())
    check('All selected prediction frame IDs preserved', set(optical.frame_uid) == set(c.frame_uid))
    layout = json.loads((ROOT/'calibration_gui/assets/live_sensor/roi_layout.json').read_text())
    for rect in layout['rois']:
        i = rect['roi_id']; a = optical[f'roi{i}_area']
        check(f'T{i}: area matches fixed layout', a.eq(rect['width'] * rect['height']).all())
        check(f'T{i}: sum/area equals recorded positive mean', np.allclose(optical[f'roi{i}_delta_v_sum']/a, optical[f'roi{i}_delta_v_sum_per_pixel'], atol=1e-12))
        check(f'T{i}: active fraction equals count/area', np.allclose(optical[f'roi{i}_active_pixel_count']/a, optical[f'roi{i}_active_fraction'], atol=1e-12))
        check(f'T{i}: intensity and fractions in range', optical[f'roi{i}_mean_v'].between(0,255).all() and optical[f'roi{i}_max_v'].between(0,255).all() and optical[f'roi{i}_active_fraction'].between(0,1).all())
        check(f'T{i}: positive response is nonnegative and bounded', optical[f'roi{i}_delta_v_sum_per_pixel'].between(0,255).all())
    optical.to_parquet(data/'matched_acquisition_optical_measurements.parquet', index=False)
    pd.DataFrame(members).to_csv(data/'archive_member_manifest.csv', index=False)
    provenance = {'archive': args.archive.name, 'archive_sha256': ARCHIVE_HASH, 'prediction_sha256': PRED_HASH,
        'optical_source': 'Original acquisition-time frame_features.csv; not video-recomputed model inputs',
        'join': 'Exact SHA-256 frame_uid rebuilt from archive hash, session directory, zero-based CSV row/video index, capture frame ID; then capture timestamps verified',
        'rows': len(optical), 'sessions': optical.session_id.nunique(), 'source_members': len(members),
        'processed_cache': 'Existing feature-store directory returned Windows access denied; source archive CSVs used for optical diagnostics only',
        'checks': checks}
    (OUT/'source_validation.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
    print(json.dumps({'matched_frames':len(optical), 'recordings':optical.session_id.nunique(), 'checks_passed':len(checks)}, indent=2))

if __name__ == '__main__':
    main()
