"""Integrate the verified repeatability supplement without replacing the original audit."""
from pathlib import Path
import csv, hashlib, json, re, shutil

ROOT = Path(__file__).resolve().parent
DEST = ROOT / 'thesis_handoff'
OUT = ROOT / 'outputs/repeatability_20261018'
STEM = 'BAURods_Manual_Calibration_Technical_Report'

def rows(name):
    with (OUT/'tables'/f'{name}.csv').open(newline='',encoding='utf-8') as f:
        return list(csv.DictReader(f))

def table(headers, data):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |'] +
                     ['| '+' | '.join(map(str,r))+' |' for r in data])

def interval(record, places=2):
    return f"{float(record['ci95_lower']):.{places}f} to {float(record['ci95_upper']):.{places}f}"

def supplement():
    s=json.loads((OUT/'summary.json').read_text())
    data={(r['taxel'],r['statistic']):r for r in rows('repeatability_intervals')}
    model={r['statistic']:r for r in rows('model_bootstrap_intervals')}
    jr=rows('delete_one_round');jt=rows('delete_one_taxel')
    ci=s['force_effect_round_jackknife'];ct=s['force_effect_taxel_jackknife']
    optical=[];force=[]
    for t in [f'T{i}' for i in range(1,10)]:
        m,sd,cv=[data[t,'optical_'+k] for k in ['mean','sd','cv_percent']]
        optical.append([t,f"{float(m['estimate']):.3f}",f"{float(sd['estimate']):.3f}",interval(sd,3),f"{float(cv['estimate']):.2f}",interval(cv)])
        m,sd,cv=[data[t,'force_'+k] for k in ['mean','sd','cv_percent']]
        force.append([t,f"{float(m['estimate']):.3f}",f"{float(sd['estimate']):.3f}",f"{float(cv['estimate']):.2f}",interval(cv)])
    dispersion=[]
    for label,key,df in [('Within taxels; no round or force adjustment','pooled_within_taxel_sd',63),
                         ('Taxel and TEST-group effects','taxel_round_residual_sd',56),
                         ('Taxel, TEST group and mean force','force_adjusted_residual_sd',55)]:
        r=model[key]
        dispersion.append([label,str(df),f"{float(r['estimate']):.4f}",interval(r,4)])
    sens=[]
    for r in rows('model_sensitivity')[:4]:
        sens.append([r['model'],f"{float(r['force_effect']):.4f}",interval(r,4),r['response_scale']+' / N'])
    roundtable=[]
    for r in rows('round_summaries'):
        roundtable.append([r['trial_group'],f"{float(r['mean_force_N']):.3f}",f"{float(r['raw_optical_mean']):.3f}",f"{float(r['adjusted_round_deviation']):+.3f}"])
    return f'''
## Part VIII  Repeatability and force-adjusted analysis

**Supplement completed:** 18 October 2026. **Decision requested:** quantify consistency and its uncertainty without an acceptance limit or pass/fail judgment. This section adds completed statistical work to the original 5 October audit. All original measurements, descriptive findings and trained-model artifacts are preserved.

### 1. Main findings and interpretation

Across eight recordings per taxel, observed optical recording-mean CVs range from **9.45% to 28.66%**. The approximate 95% interval is **{interval(data['T5','optical_cv_percent'])}% for T5** and **{interval(data['T3','optical_cv_percent'])}% for T3**, the taxels with the lowest and highest point estimates. These are observed extrema, not statistically established rankings. Interval overlap is not an equivalence test.

The pooled within-taxel optical SD is **{s['pooled_within_taxel_sd']:.4f} digital delta V**. After allowing for taxel, TEST-group and mean-force differences, the residual SD is **{s['residual_sd']:.4f}**, with an approximate 95% BCa interval of **{s['residual_sd_BCa'][0]:.4f} to {s['residual_sd_BCa'][1]:.4f}**. The fitted common force slope is **{ci['estimate']:.4f} digital delta V/N**, with a primary group-jackknife 95% interval of **{ci['lower']:.4f} to {ci['upper']:.4f}**. Its positive estimate is compatible with a small negative or a larger positive conditional association under this uncertainty calculation.

No application-specific acceptance limit was supplied. Consequently, these estimates quantify the recorded variability; they do not establish that repeatability is sufficient or insufficient for the intended use. Neither an interval containing zero nor a nonsignificant difference establishes equivalence. No pass/fail result, equivalence test, universal CV cutoff, or new trained-model performance result is reported.

### 2. Analytical unit and comparable conditions

The researcher confirmed that the TEST groups were intended to be collected under comparable conditions. The source contains a complete 9-by-8 matrix: one press-designated recording for each taxel T1-T9 in TEST1, TEST2, TEST3, TEST4, TEST5, TEST6, TEST7 and TEST1_v2. All **72 recordings** are retained, including groups used as replay-only data in a separate model-training workflow. That training role does not make their acquisition records ineligible for this quality assessment. The 11 dedicated no-contact recordings remain covered by the original stability analysis and are not treated as contact-response replicates here.

For each recording, Y is the mean target-ROI optical response over the same core-valid, force-defined contact frames used by the original audit; F is the mean synchronized force over those frames. Each recording receives equal weight. All 144 optical/force means were independently recomputed from the original master CSVs; the largest absolute difference from the audited summary was {s['max_source_mean_difference']:.2e}. Optical delta V refers to the baseline-corrected HSV value channel in the saved motion-magnified pipeline, **not electrical volts**.

The term round below is shorthand for a matched TEST group, not proof of an independently randomized or contiguous collection block. Timestamp ranges for TEST2-TEST6 overlap, and saved baselines are reused across groups. TEST1 recording durations span 103.5-161.4 s, whereas TEST7 spans 18.0-23.5 s. Intended comparable conditions therefore coexist with observed differences in force, recording duration, baseline context and acquisition order. All observations belong to source session S3 on 8 August 2026. The analysis has eight observed group profiles, not 72 independent sessions or thousands of independent frames.

### 3. Repeatability estimates and uncertainty method

For each taxel, the eight recording means were summarized by the arithmetic mean, sample SD with denominator n-1, and CV = 100 x SD / mean. The response means are positive. CV describes relative dispersion on this particular digital feature scale; it is not automatically a metrological relative uncertainty or an intrinsic property of the sensing material. SD remains necessary because CV depends on the mean and the feature's zero point. NIST describes SD as a measure of repeatability precision; the uncontrolled loading and recording aggregation here require the more limited interpretation of observed recording-level dispersion. [NIST repeatability guidance](https://www.itl.nist.gov/div898/handbook/mpc/section4/mpc441.htm).

Approximate 95% bias-corrected and accelerated (BCa) bootstrap intervals were calculated with **50,000 resamples**, seed **20261018**, using SciPy. Each draw samples eight complete TEST-group profiles with replacement. The nine taxels remain matched within each selected profile. Individual frames were never resampled as independent observations. BCa acceleration uses deletion of one whole profile. The same resamples support per-taxel means, SDs, CVs and the model dispersion summaries. [SciPy bootstrap documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html).

These are marginal intervals for each reported statistic, not simultaneous bounds across all nine taxels, prediction intervals for a future recording, or intervals for individual frame values. They are conditional on the observed-session sampling structure and an exchangeability assumption for group profiles. Eight groups are few; bootstrap resampling cannot create independent days, remove confounding or establish nominal 95% coverage when that assumption fails. A diagnostic comparison of the two halves of the bootstrap draws found a maximum difference of {s['cv_percentile_endpoint_MC_half_difference_pp']:.2f} percentage points in unadjusted optical-CV percentile endpoints. This diagnoses Monte Carlo/discrete-distribution sensitivity; it is not an extra uncertainty margin added to the BCa intervals. Decimal formatting should not be mistaken for precision of that order.

**Table R1. Optical recording-level dispersion.** Each row uses n = 8 recordings. Mean and SD are in digital delta V. Intervals use whole-group BCa resampling.

{table(['Taxel','Mean','SD','95% interval: SD','CV (%)','95% interval: CV (%)'],optical)}

T5 has the smallest observed optical CV. T3 has the largest. T6's interval is especially broad relative to its point estimate, illustrating the limited information in eight observations. The source values and uncertainty intervals are retained without deleting high or low recordings. Comparisons among taxels are descriptive; the analysis does not claim a statistically established ordering.

**Table R2. Applied-force variation.** Mean and SD are in N; n = 8 per taxel. The CV intervals describe manual input variability, not uncertainty in the load-cell calibration.

{table(['Taxel','Mean force (N)','SD (N)','Force CV (%)','95% interval: CV (%)'],force)}

![Figure 16. Observed optical and force CVs with approximate 95% BCa intervals; eight recordings per taxel and no acceptance threshold](../outputs/repeatability_20261018/figures/16_repeatability_uncertainty.png)

### 4. Force-adjusted model and uncertainty

An additive fixed-effects regression was fitted to the 72 recording summaries:

```text
Y_tr = intercept + taxel_t + TEST_group_r + beta * (F_tr - 3.5 N) + error_tr
```

This is an ANCOVA-style model with taxel and TEST-group effects. It allows a separate response level for each observed taxel and group, together with one common linear force slope. Ordinary least squares gives one vote to each recording. The design contains an intercept, eight taxel indicators, seven group indicators and one force term: **17 parameters and 55 residual degrees of freedom**. It was full rank. The 3.5 N reference lies inside the common intersection of all nine taxels' observed recording-mean force ranges ({s['common_force_range_N'][0]:.3f}-{s['common_force_range_N'][1]:.3f} N). Centering aids interpretation and does not alter the slope or fitted residuals.

The fit is a conditional descriptive adjustment, not a validated calibration function or a causal estimate of force response. It assumes an additive mean structure and a common linear slope; measured mean force is treated as a covariate without propagating load-cell calibration error. It does not make the actual experiments fixed-force trials. With only one recording per taxel-by-group cell, interaction variation and residual variation cannot be separately estimated. Fixed effects avoid assigning an unsupported population distribution to the eight observed group levels.

For the force coefficient, the primary interval uses the **CV3J delete-one-group jackknife**. The complete model, including nuisance effects, is refitted after deleting each TEST group. The jackknife variance is (G-1)/G times the sum of squared differences between the deleted-group slopes and their mean. The interval uses the full-data coefficient plus or minus t(0.975, G-1) times its jackknife SE, with G = 8 and **7 reference degrees of freedom**, rather than treating 72 recordings as independent clusters. The cluster-jackknife approach is described by MacKinnon, Nielsen and Webb; with so few clusters its coverage remains approximate and relies on independence across clusters. [MacKinnon, Nielsen and Webb (2023)](https://journals.sagepub.com/doi/10.1177/1536867X231212433).

**Table R3. Conditional force association and sensitivity to uncertainty method.** All rows refer to the same slope estimate {ci['estimate']:.4f} digital delta V/N.

{table(['Uncertainty calculation','Approximate 95% interval','Interpretation'],[
['Primary: delete one TEST group',f"{ci['lower']:.4f} to {ci['upper']:.4f}",'8 group clusters; t reference with 7 df'],
['Sensitivity: delete one taxel',f"{ct['lower']:.4f} to {ct['upper']:.4f}",'9 taxel clusters; t reference with 8 df'],
['Sensitivity: whole-group BCa bootstrap',interval(model['force_coefficient'],4),'50,000 complete-profile resamples']])}

The bootstrap slope interval excludes zero, whereas both jackknife intervals include zero. This method dependence must be retained in the thesis: it is evidence that the uncertainty conclusion is sensitive to the small dataset and dependence assumptions. No preferred significance claim is selected from these alternatives. The taxel calculation examines dependence within a repeated physical taxel, while the primary grouping examines dependence within TEST groups. These are separate sensitivity calculations, **not simultaneous two-way clustering**. Shared session and baseline effects can still link observations across either grouping.

**Table R4. Residual dispersion as adjustment terms are added.** SD is in digital delta V; df is the denominator used for the SD estimate. These are descriptive fits of the same observations, not cross-validated prediction errors.

{table(['Adjustment','Residual df','SD','Approximate 95% BCa interval'],dispersion)}

Adding mean force to the taxel-and-group model reduces residual SD from {s['blocked_residual_sd']:.4f} to {s['residual_sd']:.4f}, a {(1-s['residual_sd']/s['blocked_residual_sd'])*100:.1f}% reduction. Its partial R-squared is {s['partial_r_squared_force']:.3f}: force accounts for {s['partial_r_squared_force']*100:.1f}% of the residual sum of squares left after taxel and group effects in this fitted sample. The full model's in-sample R-squared is {s['r_squared']:.3f}, including all taxel and group indicators. Neither quantity measures repeatability acceptance, causal variance attribution or performance on new sessions. Residual SD is not an intrinsic sensor-only error estimate.

![Figure 17. Conditional force association after removing taxel and group means, and residuals versus fitted optical response; 72 recording summaries](../outputs/repeatability_20261018/figures/17_force_adjusted_diagnostics.png)

### 5. Diagnostics and sensitivity checks

The residual-versus-fitted and normal Q-Q plots were inspected as diagnostics, not used as an automatic pass/fail normality gate. The Q-Q points broadly follow a line with deviations in the tails. Residual RMS differs across taxels, from {s['residual_rms_taxel_range'][0]:.3f} to {s['residual_rms_taxel_range'][1]:.3f} digital delta V, so equal residual dispersion should not be presumed. The maximum leverage is {s['max_leverage']:.3f} and maximum Cook's distance is {s['max_cooks_distance']:.3f}. These values were recorded for influence review; no cutoff was used to remove data.

After allowing for mean force, descriptive group offsets range from {s['adjusted_round_deviation_range'][0]:+.3f} to {s['adjusted_round_deviation_range'][1]:+.3f} digital delta V relative to the adjusted grand mean. They are calculated from group mean Y minus beta times group mean force centered at 3.5 N, then centered across groups. They describe this fitted sample. They cannot isolate an effect of baseline, elapsed time, operator behavior or material change.

**Table R5. Group context and descriptive offsets.** Each row contains nine taxels; optical means and offsets are digital delta V. No confidence interval or causal interpretation is assigned to these offsets.

{table(['TEST group','Mean force (N)','Mean optical response','Adjusted group offset'],roundtable)}

![Figure 18. Descriptive force-adjusted group offsets and residual normal Q-Q diagnostic; offsets are not causal effects or pass/fail results](../outputs/repeatability_20261018/figures/18_round_effects_residual_shape.png)

Deleting one group at a time gives slope estimates from {min(float(r['force_coefficient']) for r in jr):.4f} to {max(float(r['force_coefficient']) for r in jr):.4f}; deleting one taxel gives {min(float(r['force_coefficient']) for r in jt):.4f} to {max(float(r['force_coefficient']) for r in jt):.4f} digital delta V/N. The larger taxel sensitivity, particularly when T1 is omitted, limits confidence in a common population-wide slope. These refits are influence diagnostics; all 72 recordings remain in the reported primary analysis.

**Table R6. Mean-structure sensitivity.** Intervals use the same delete-one-TEST-group method. The log-response row has different units and its residual SD is not directly comparable to the untransformed model. The quadratic row reports the derivative at 3.5 N.

{table(['Model','Force effect','Approximate 95% interval','Effect units'],sens)}

Each listed interval includes zero. Allowing nine separate taxel force slopes was also examined: residual SD becomes 0.1728 digital delta V with 47 residual degrees of freedom. This more flexible, 25-parameter model is exploratory; eight observations per taxel and one observation per taxel-group cell provide limited support for stable slope-specific interpretation. A smaller fitted residual alone does not establish better generalization. The saved sensitivity table's force coefficient in this interaction model is **T1's reference slope**, not a common slope for all taxels.

![Figure 19. Force-slope influence when one complete TEST group or one taxel is omitted; dashed lines show the full-data estimate](../outputs/repeatability_20261018/figures/19_model_influence.png)

### 6. Thesis wording and remaining uncertainty

> Across eight recording-level repetitions for each of nine taxels, optical response CVs ranged from 9.45% to 28.66% under the recorded manual-loading conditions. Whole-group bootstrap intervals showed substantial uncertainty in these dispersion estimates. A model allowing for taxel, TEST-group and mean-force differences yielded a residual SD of {s['residual_sd']:.4f} digital delta V (approximate 95% BCa interval {s['residual_sd_BCa'][0]:.4f}-{s['residual_sd_BCa'][1]:.4f}). The estimated common force association was {ci['estimate']:.4f} digital delta V/N, with a primary group-jackknife interval of {ci['lower']:.4f} to {ci['upper']:.4f}. Uncertainty conclusions varied with the resampling and clustering approach. These findings quantify within-session recording variability without establishing a pass/fail judgment, fixed-force per-press repeatability or independent-session reproducibility.

The practical question of sufficient consistency remains open because no application tolerance was defined before analysis. Future work can specify a maximum acceptable SD, CV or force-adjusted response difference based on the downstream sensing requirement, then collect independent sessions with controlled loading and annotated presses. Any later acceptance analysis must identify its criterion and uncertainty method explicitly. This report does not choose a favorable limit after seeing the results. The saved single-reference force calibration, motion magnification, shared baselines, unknown physical-press count and absence of independent days remain limitations after regression adjustment.

### 7. Reproducibility and additional evidence

The executed script is `baurods_quality/repeatability_analysis.py`. It verifies the original archive hash and all 144 recording means, checks the complete 9-by-8 matrix, computes the bootstrap and cluster-jackknife estimates, and exports tables and figures. No recording is excluded. An independent QR solution agreed with the ordinary least-squares coefficients to {s['qr_coefficient_max_difference']:.2e}; the force coefficient and residual SD also matched a separate calculation using double-centered taxel/group arrays. All 50,000 bootstrap draws and all reported interval endpoints were finite.

Run from the workspace root with the existing analysis environment:

```text
calibration_gui/.venv/Scripts/python.exe baurods_quality/repeatability_analysis.py
calibration_gui/.venv/Scripts/python.exe baurods_quality/build_repeatability_supplement.py
```

The original ZIP is required for the first command and is not embedded in the handoff. The PDF builder at `thesis_handoff/create_pdf_report.py` requires ReportLab, Pillow and pypdf, available in the document runtime used for this report. The numerical environment is Python {s['software']['python']}, NumPy {s['software']['numpy']}, pandas {s['software']['pandas']}, SciPy {s['software']['scipy']} and Matplotlib {s['software']['matplotlib']}. The numerical supplement uses seed 20261018; seed 20261005 in Part VI refers to the original audit's graphical jitter.

The supplement's evidence folder is `outputs/repeatability_20261018`. It contains 13 CSV tables, four 320 dpi PNG/SVG figure pairs, `summary.json` and `analysis.log`. `analysis_recordings.csv` preserves all 72 analysis rows and their original provenance; `repeatability_intervals.csv` retains full-precision means, SDs, CVs and intervals; `force_coefficient_uncertainty.csv`, `model_bootstrap_intervals.csv` and `model_sensitivity.csv` preserve the alternative uncertainty calculations. Residuals, influence refits, force ranges, acquisition context and the baseline crosswalk are also saved. The source ZIP SHA-256 remains `{s['archive_sha256']}`.

The methodological references above support the estimators and their assumptions. They do not provide a BAURods acceptance threshold. The force-adjusted regression is part of this data-quality supplement and must remain distinct from the separate trained-model report.
'''

def integrate(report):
    report=report.split('\n## Part VIII  Repeatability and force-adjusted analysis')[0].rstrip()+'\n'
    replacements={
        '**Assessment date:** 5 October 2026, Asia/Manila. **Acquisition date:** 8 August 2026. **Version:** 1.0.':
        '**Original assessment:** 5 October 2026. **Statistical supplement:** 18 October 2026, Asia/Manila. **Acquisition date:** 8 August 2026. **Version:** 1.1.',
        'No new normalization by force, response threshold tuning, imputation, raw-pixel processing, optical detrending, outlier deletion, or classifier fitting was performed.':
        'The original 5 October audit performed no force normalization, response threshold tuning, imputation, raw-pixel processing, optical detrending, outlier deletion or classifier fitting. Part VIII subsequently adds a force-adjusted statistical regression while preserving the original measurements; no classifier is fitted.',
        'The analysis uses descriptive rank association because a stable linear calibration relationship was not established.':
        'The original audit used descriptive rank association because a stable linear calibration relationship was not established. Part VIII adds a conditional linear regression with uncertainty and sensitivity checks; it does not establish a calibration curve.',
        'No force normalization or model has been used to erase that variation.':
        'The raw variation is preserved. Part VIII adds a force-adjusted regression to describe conditional association and remaining dispersion; it does not replace the recorded values.',
        'No Pearson model is imposed because a stable linear relationship is not established.':
        'This original rank-correlation subsection imposes no linear calibration model. The later regression in Part VIII explicitly examines a conditional linear mean structure and its limitations.',
        'The analysis uses a fixed seed of 20261005 for any seeded graphical jitter. Summary statistics and the deterministic timing/correlation calculations do not rely on a Monte Carlo procedure.':
        'The original audit uses a fixed seed of 20261005 for seeded graphical jitter. Its summary statistics and deterministic timing/correlation calculations do not rely on a Monte Carlo procedure. The later bootstrap analysis in Part VIII uses seed 20261018 and 50,000 resamples.',
        'Draft these assessment sections, not an entire thesis or new model-training chapter.':
        'Include the completed repeatability and force-adjusted analysis in Part VIII, its approximate intervals, dependence assumptions and disagreement between uncertainty methods. Do not infer an acceptance limit or turn interval overlap, an interval containing zero, or an absence of significance into equivalence. Keep this statistical adjustment separate from learned-model evaluation. Draft these assessment sections, not an entire thesis or new model-training chapter.',
    }
    for old,new in replacements.items():
        if old in report and new not in report:report=report.replace(old,new)
    notice='**Revision note:** Part VIII adds recording-level repeatability uncertainty and a force-adjusted model on 18 October 2026. Statements about analyses not performed in the original audit refer to the 5 October work. The new statistics use all 72 press-designated recordings, impose no acceptance threshold and do not alter later trained-model results.\n\n'
    if '**Revision note:**' not in report:report=report.replace('## How to use this report',notice+'## How to use this report',1)
    return report+supplement()

def main():
    source=DEST/f'{STEM}.md'
    current=source.read_text(encoding='utf-8')
    backup=DEST/'history/20261005_v1_0'
    if '**Version:** 1.0.' in current:
        backup.mkdir(parents=True,exist_ok=True)
        for name in [STEM+'.md',STEM+'.txt','ChatGPT_Writing_Prompt.txt','README.md','handoff_verification.json','PACKAGE_MANIFEST.csv']:
            p=DEST/name
            if p.exists() and not (backup/name).exists():shutil.copy2(p,backup/name)
        pdf=ROOT.parent/'output/pdf'/f'{STEM}.pdf'
        if pdf.exists() and not (backup/pdf.name).exists():shutil.copy2(pdf,backup/pdf.name)
    report=integrate(current)
    for ext in ['md','txt']:(DEST/f'{STEM}.{ext}').write_text(report,encoding='utf-8')
    (DEST/'Repeatability_Statistical_Supplement.md').write_text(supplement(),encoding='utf-8')
    prompt=re.search(r'^> Draft the Methodology.*$',report,re.M).group()[2:]
    (DEST/'ChatGPT_Writing_Prompt.txt').write_text(prompt+'\n',encoding='utf-8')
    assert report.count('## Part VIII ')==1
    assert all(f'## Part {part}  ' in report for part in ['I','II','III','IV','V','VI','VII','VIII'])
    assert len(list((OUT/'tables').glob('*.csv')))==13
    for image in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',report):assert (DEST/image).exists(),image
    receipt={'version':'1.1','date':'2026-10-18','words':len(report.split()),'original_parts_retained':7,
             'statistical_supplement_tables':13,'new_figure_pairs':4,'report_sha256':hashlib.sha256(report.encode()).hexdigest(),
             'acceptance_limit':None,'pass_fail_judgment':False}
    (DEST/'repeatability_handoff_verification.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt,indent=2))

if __name__=='__main__':main()
