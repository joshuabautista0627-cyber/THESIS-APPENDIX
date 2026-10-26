"""One self-contained, searchable thesis source PDF; never edits earlier reports."""
import ast
import csv
import hashlib
import json
import re
import textwrap
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer,
    PageBreak, LongTable, TableStyle, Image, Preformatted, KeepTogether)
from reportlab.platypus.tableofcontents import TableOfContents

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
BEST=ROOT/'reports/BEST_RESULTS'
RUN=ROOT/'calibration_gui/analysis_outputs/live_sensor_manual_only/model_runs'
TUNE=RUN/'tuning_20260909'
BASE=RUN/'retraining_20260909'
PDF_DIR=ROOT/'output/pdf/complete_thesis_report_2026-10-18'
PDF_DIR.mkdir(parents=True,exist_ok=True)
PDF=PDF_DIR/'Manual_Calibration_Complete_Thesis_Technical_Report.pdf'

def readj(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def readcsv(p):
    with p.open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))
def fnum(v,places=4): return f'{float(v):.{places}f}'
def pct(v): return f'{100*float(v):.2f}'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

M=readj(BEST/'BEST_METRICS.json')['results']
C=readj(BEST/'BEST_MODEL_CONFIGURATIONS.json')
E=readj(ROOT/'reports/manual_calibration_thesis_report_2026-10-05/Exact_Segmentation_and_Model_Configurations.json')
P=readj(TUNE/'protocol.json')
D=readj(HERE/'derived_evidence.json')
COM=readcsv(BEST/'reference/all_competing_models_ranked.csv')
LIGHT=readcsv(BEST/'data/light_metrics_by_taxel.csv')
TAX=readcsv(BEST/'data/best_models_per_taxel.csv')
FIXED=readj(BASE/'estimator_parameters.json')
V_DIR=ROOT/'reports/manual_v_channel_metrics_2026-10-18'
V=readcsv(V_DIR/'v_channel_metrics_by_taxel.csv')

for name,file in [('Calibri','calibri.ttf'),('CalibriBold','calibrib.ttf'),('CalibriItalic','calibrii.ttf'),('Consolas','consola.ttf')]:
    pdfmetrics.registerFont(TTFont(name,str(Path('C:/Windows/Fonts')/file)))
pdfmetrics.registerFontFamily('Calibri',normal='Calibri',bold='CalibriBold',italic='CalibriItalic',boldItalic='CalibriBold')
NAVY=colors.HexColor('#14314A'); TEAL=colors.HexColor('#087E8B'); GREY=colors.HexColor('#51606D')
PALE=colors.HexColor('#EDF5F6'); LIGHTGREY=colors.HexColor('#F3F5F7'); LINE=colors.HexColor('#D4DDE3')
PAGE_W,PAGE_H=A4; WIDTH=PAGE_W-100
ST={
 'body':ParagraphStyle('Body',fontName='Calibri',fontSize=10.25,leading=14,spaceAfter=8,textColor=NAVY),
 'small':ParagraphStyle('Small',fontName='Calibri',fontSize=8.6,leading=11.5,spaceAfter=6,textColor=GREY),
 'h1':ParagraphStyle('H1',fontName='CalibriBold',fontSize=19,leading=23,spaceAfter=14,textColor=NAVY),
 'h2':ParagraphStyle('H2',fontName='CalibriBold',fontSize=12.3,leading=16,spaceBefore=10,spaceAfter=6,textColor=TEAL,keepWithNext=True),
 'title':ParagraphStyle('Title',fontName='CalibriBold',fontSize=28,leading=33,spaceAfter=18,textColor=NAVY),
 'subtitle':ParagraphStyle('Subtitle',fontName='Calibri',fontSize=14,leading=19,spaceAfter=20,textColor=GREY),
 'th':ParagraphStyle('TH',fontName='CalibriBold',fontSize=8.5,leading=10.8,textColor=colors.white),
 'td':ParagraphStyle('TD',fontName='Calibri',fontSize=8.5,leading=10.8,textColor=NAVY),
 'tdsmall':ParagraphStyle('TDSmall',fontName='Calibri',fontSize=7.7,leading=9.7,textColor=NAVY),
 'caption':ParagraphStyle('Caption',fontName='Calibri',fontSize=9,leading=12,spaceBefore=7,spaceAfter=10,textColor=GREY),
 'code':ParagraphStyle('Code',fontName='Consolas',fontSize=7.5,leading=10,spaceAfter=8,textColor=NAVY),
}
story=[]; headings=[]; tables=[]; figures=[]; sources=[]

class Report(BaseDocTemplate):
    def __init__(self,path):
        super().__init__(str(path),pagesize=A4,leftMargin=50,rightMargin=50,topMargin=55,bottomMargin=47,
            title='Manual Calibration: Complete Technical Report for Thesis Writing',
            author='SPARE manual-calibration research project',subject='Best held-out models, full comparisons, exact methods and optical diagnostics')
        frame=Frame(50,47,WIDTH,PAGE_H-102,id='normal',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
        self.addPageTemplates(PageTemplate(id='normal',frames=[frame],onPage=self.decorate))
    def decorate(self,canv,doc):
        canv.saveState();canv.setStrokeColor(LINE);canv.setLineWidth(.5)
        if doc.page>1:
            canv.line(50,PAGE_H-35,PAGE_W-50,PAGE_H-35)
            canv.setFont('Calibri',8);canv.setFillColor(GREY)
            canv.drawString(50,PAGE_H-27,'MANUAL CALIBRATION  |  COMPLETE THESIS SOURCE REPORT')
        canv.line(50,34,PAGE_W-50,34);canv.setFont('Calibri',8);canv.setFillColor(GREY)
        canv.drawString(50,22,'18 October 2026  •  Manual dataset only')
        canv.drawRightString(PAGE_W-50,22,str(doc.page));canv.restoreState()
    def afterFlowable(self,flowable):
        if isinstance(flowable,Paragraph) and hasattr(flowable,'bookmark_key'):
            k=flowable.bookmark_key;text=flowable.getPlainText()
            self.canv.bookmarkPage(k);self.canv.addOutlineEntry(text,k,0,False)
            self.notify('TOCEntry',(0,text,self.page,k))

def para(text,style='body'):
    story.append(Paragraph(text,ST[style]))
def heading(text,newpage=True,toc_entry=True):
    if newpage: story.append(PageBreak())
    p=Paragraph(text,ST['h1'])
    if toc_entry:
        p.bookmark_key=f'section_{len(headings)+1}';headings.append(text)
    story.append(p)
def sub(text): para(text,'h2')
def table(title,headers,rows,widths=None,small=False,highlight=None,compact=False):
    number=len(tables)+1;tables.append(title)
    para(f'<b>Table {number}.</b> {escape(title)}','caption')
    st=ST['tdsmall'] if small else ST['td']
    def cell(v,style): return Paragraph(escape(str(v)).replace('\n','<br/>'),style)
    cells=[[cell(v,ST['th']) for v in headers]]+[[cell(v,st) for v in row] for row in rows]
    if widths: widths=[WIDTH*w/sum(widths) for w in widths]
    else: widths=[WIDTH/len(headers)]*len(headers)
    tb=LongTable(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
    commands=[('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),
              ('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),
              ('TOPPADDING',(0,0),(-1,-1),4 if compact else 5),('BOTTOMPADDING',(0,0),(-1,-1),4 if compact else 5),
              ('LINEBELOW',(0,0),(-1,0),.6,NAVY),('LINEBELOW',(0,1),(-1,-1),.25,LINE)]
    for i in range(1,len(cells)):
        if i%2==0:commands.append(('BACKGROUND',(0,i),(-1,i),LIGHTGREY))
    for i in (highlight or []): commands.append(('BACKGROUND',(0,i+1),(-1,i+1),PALE))
    tb.setStyle(TableStyle(commands));story.append(tb);story.append(Spacer(1,7))
def matrix_table(title,file,decimals=2):
    rows=readcsv(BEST/'data'/file);head=list(rows[0]);out=[]
    for r in rows:
        out.append([r[head[0]]]+[(str(int(float(r[k]))) if decimals==0 else fnum(r[k],decimals)) for k in head[1:]])
    table(title,['Actual / predicted']+head[1:],out,[1.6]+[1]*(len(head)-1),small=True)
def figure(name,title,caption,maxheight=550):
    path=(V_DIR/'v_channel_heatmaps.png' if name=='v_channel_heatmaps' else
          HERE/'force_diagnostics.png' if name=='force_diagnostics' else BEST/'figures'/f'{name}.png')
    iw,ih=PILImage.open(path).size;scale=min(WIDTH/iw,maxheight/ih)
    story.append(Image(str(path),width=iw*scale,height=ih*scale,hAlign='CENTER'))
    n=len(figures)+1;figures.append({'number':n,'name':name,'title':title,'path':str(path),'sha256':sha(path)})
    para(f'<b>Figure {n}. {escape(title)}.</b> {caption}','caption')
def code(text,width=91):
    # Wrap display lines visibly; the exact feature function below is kept unwrapped.
    lines=[]
    for line in text.splitlines():
        if len(line)<=width: lines.append(line)
        else: lines.extend(textwrap.wrap(line,width=width,subsequent_indent='    ',break_long_words=True,break_on_hyphens=False,replace_whitespace=False))
    for start in range(0,len(lines),35): story.append(Preformatted('\n'.join(lines[start:start+35]),ST['code']))
def param_block(title,params):
    sub(title)
    # Every parameter is retained, but one-line pairs make defaults readable.
    parts=[f'{k}={json.dumps(v,ensure_ascii=True)}' for k,v in sorted(params.items())]
    para(escape('; '.join(parts))+'.','small')

# COVER AND EXECUTIVE SUMMARY
story.append(Spacer(1,28))
para('Manual Calibration<br/>Complete Technical Report','title')
para('Force estimation, contact detection and nine-taxel localization<br/>A self-contained source document for thesis writing','subtitle')
para('<b>Prepared:</b> 18 October 2026<br/><b>Model experiments:</b> 9 September 2026<br/><b>Dataset:</b> Manual Calibration (2).zip only')
sub('Best evaluated results')
table('Recommended headline models and held-out metrics',
 ['Task','Best model','Primary result','Supporting results'],[
 ['Localization','Tuned Logistic regression','84.88% accuracy','85.00% macro F1'],
 ['Contact detection','Tuned RBF SVC','99.24% accuracy','99.54% balanced accuracy; 99.09% recall'],
 ['Force estimation','Tuned ensemble','0.4972 N MAE','0.6299 N RMSE; R² = 0.3113']],
 [1.15,1.5,1.25,1.9],highlight=[0,1,2])
para('The two classifiers have the highest observed recording-weighted accuracy among the evaluated models. The force ensemble has the lowest observed recording-weighted mean absolute error. Each task uses one winning model for all its headline metrics. [S1–S3]')
para('Predictions were generated with six complete TEST groups held out in turn. Force and localization cover 7,154 eligible frames from 54 recordings; contact detection covers 8,506 frames from 65 recordings. All reported model metrics give each recording equal total weight.')
para('Model-family ranking is retrospective on these outer cross-validation results. These are held-out fold predictions, not an untouched prospective test of a final full-data model. The report preserves all 50 evaluated comparison rows and all 178 tuning configurations.')
para('This file contains the complete methodology, exact segmentation, winning fold configurations, full model comparisons, separately labeled normalized and raw-count confusion matrices, spatial and optical heatmaps, limitations, reproducibility details, and a ready-to-use thesis-writing prompt. Existing reports and competing model artifacts remain intact.','small')

heading('Contents',toc_entry=False)
toc=TableOfContents();toc.levelStyles=[ParagraphStyle('TOC',fontName='Calibri',fontSize=10,leading=14,spaceBefore=6,textColor=NAVY,leftIndent=0,firstLineIndent=0)]
story.append(toc)
para('Percentages in metric and normalized-matrix tables are displayed on a 0–100 scale. Force errors are in newtons. Raw confusion matrices contain integer frames. Internal source IDs [S1–S16] resolve in the evidence register at the end.','small')

heading('1. Purpose, system and dataset')
para('The study estimates applied force from optical measurements, detects contact, and identifies the contacted taxel in a fixed 3 × 3 array. It compares model families under a common grouped validation design and evaluates improvements from richer optical features, hyperparameter search, causal history, threshold selection and ensembles.')
para('The SPARE application records a camera stream alongside an Arduino Nano/HX711 reference-force stream, unloaded optical baselines, timestamps and nine regions of interest (ROIs). Reference force provides supervision and evaluation targets; it is absent from optical model inputs. The separate printer-driven automatic-calibration path is excluded. Historical hardware records identify an Arducam IMX179 module, but do not establish identical camera controls or a traceable force-uncertainty budget for every archived recording. [S4, S5, S15]')
table('Task definitions and evaluation population',['Task','Target','Evaluation population'],[
 ['Force estimation','Continuous reference force, N','Eligible manual press frames'],
 ['Localization','Discrete taxel class T1–T9','Same eligible manual press frames'],
 ['Contact detection','0 = dedicated no contact; 1 = eligible press','Eligible press plus dedicated no-contact frames']],[1.2,1.7,2.4])
table('Manual archive composition',['Role','Recordings','Frames','Analysis use'],[
 ['Primary press',54,'24,453','Eligible frames supply all positive tasks'],
 ['Dedicated no contact',11,'1,352','Contact negatives; training-only optical floors'],
 ['Replay only',18,'3,513','Excluded from fitting and scoring'],
 ['Total',83,'29,318','Manual archive only']],[1.6,.9,.9,2.8])
para('Six TEST groups each contain one primary recording per taxel. Dedicated no-contact recordings remain whole and are assigned two each to TEST1–TEST5 and one to TEST6. The preserved feature store is feature-store-fa2500440adab6ca. Archive and partition provenance were checked in the training audit. [S4–S6]')
table('Primary-frame eligibility after fold-specific force alignment',['Category','Frames'],[
 ['All primary frames','24,453'],['Unpaired with valid reference force','142'],['Aligned force below 0.05 N','723'],
 ['Aligned force above 3 N','16,434'],['Eligible press frames, inclusive 0.05–3 N','7,154']],[4,1])
para('Frames outside the eligible press interval are excluded, not relabeled as no contact. The 0.05–3 N interval is an exploratory analysis restriction; it is not an established detection limit or validated full operating range. Most primary frames are outside this interval.')

heading('2. Exact image segmentation and ROI geometry')
para('The quantitative image source is session_video.mp4. Overlay, processed and motion-magnified videos are excluded. A raw 640 × 480 frame is rotated 90° clockwise and then mirrored horizontally, producing a 480 × 640 oriented frame. Already oriented frames are not transformed again. Coordinates below are oriented camera pixels; the origin is the upper-left corner. [S6, S8]')
table('Fixed taxel rectangles; ROI layout roi-9fbc67c50ee3bc7145fa',
 ['Taxel','Row','Col.','x','y','Width','Height','Area (px²)'],
 [[r['roi_id'],r['row'],r['column'],r['x'],r['y'],r['width'],r['height'],r['area']] for r in C['roi_layout']['rois']],
 [1,.7,.7,.8,.8,1,1,1.4])
para('Rectangles use the array slice image[y:y+height, x:x+width]. Taxels T1–T3 are the first row, T4–T6 the second, and T7–T9 the third. These are fixed manually configured regions, not learned segmentation masks.')
table('Pixel operations and their exact settings',['Operation','Definition / setting'],[
 ['Color conversion','BGR to OpenCV HSV; use the 8-bit V channel'],
 ['Unloaded baseline B(x,y)','Per-recording saved per-pixel median V from baseline_data.npz'],
 ['Signed change','ΔV(x,y,t) = V(x,y,t) − B(x,y)'],
 ['Positive change','ΔV+(x,y,t) = max(ΔV(x,y,t), 0), applied per pixel'],
 ['Active mask','ΔV+ ≥ 10.0 camera V levels'],
 ['Active fraction','Active-pixel count divided by fixed ROI area'],
 ['Centroid','Intensity centroid weighted by all ΔV+ values; not only active-mask pixels'],
 ['Hue-only saturation setting','Minimum saturation = 10.0; this is not the V activity threshold'],
 ['Morphology / learned segmentation','None / none']],[1.5,3.8])
para('Per-ROI measurements retain positive and signed light sums, active fractions, signed median and median absolute deviation (MAD), raw V mean/median/maximum and centroid coordinates. Signed features preserve intensity decreases. A missing centroid is represented by the normalized ROI center (0.5, 0.5) and a separate absence flag.')
para('Optical activity is an image statistic. It does not establish physical contact area, calibrated illuminance or the anatomical/mechanical boundary of contact.','small')

heading('3. Feature construction and preprocessing')
sub('Training-only normalization')
para('For each taxel, the fitted positive-light floor is the median of the within-recording medians of positive-light sums in training no-contact recordings. The positive feature is max(raw positive sum − floor, 0) / ROI area. Signed light is divided by area without clipping. Floors are refitted at each inner and outer training boundary. [S5, S8, S9]')
para('Weighted StandardScaler uses training rows only. For feature k, z_k = (x_k − μ_k) / σ_k, with weighted mean and population variance fitted on training data. Centering is disabled only for the positive-only force pack; variance scaling remains enabled. Zero-variance scale follows the library implementation. The selected best models all use centered and scaled features.')
table('Feature packs and exact dimensions',['Pack','Dimensions','Contents'],[
 ['positive',9,'Floor-corrected positive light per pixel, T1–T9'],
 ['optical',27,'positive + signed light per pixel + active fraction'],
 ['shape',90,'optical plus seven 9-channel normalized/centered pattern blocks'],
 ['spatial',180,'shape plus signed statistics, centroids, presence and intensity transforms'],
 ['invariant',117,'63 pattern channels plus six 9-channel spatial/statistical blocks'],
 ['temporal',288,'spatial plus four 27-channel causal-history/difference blocks']],[1,1,4])
para('Across the nine taxels, unit(x) = x / (Σ|x| + 10⁻⁶), and contrast(x) = x − median(x). The seven pattern blocks are unit(positive), unit(contrast(signed)), unit(active), contrast(signed), contrast(active), unit(contrast(raw V mean)), and unit(contrast(signed median)).')
para('Spatial adds signed median, signed MAD, normalized centroid x and y, centroid-presence flags, contrast(raw V mean), contrast(raw V median), raw V maximum / (raw V mean + 1), log(1 + positive), and sign(signed)·log(1 + |signed|). Invariant contains the seven pattern blocks plus unit(MAD), centroid x/y, presence, unit(contrast(raw V median)), and the maximum-to-mean ratio. Its name does not prove invariance to all illumination or geometry changes.')
sub('Causal temporal history')
para('The optical pack supplies fast and slow exponential moving averages (EMAs), with time constants 0.3 s and 1.0 s. Temporal concatenates spatial, fast, slow, optical − fast, and fast − slow. At positive time step Δt, α = 1 − exp(−Δt/τ) and h_t = h_(t−1) + α(x_t − h_(t−1)). History restarts on a new recording, nonpositive Δt, or a gap greater than 0.3 s. Output smoothing is a separate selection over τ ∈ {0, 0.3, 1.0} s.')
para('Inputs contain no reference force, true taxel, TEST number, session identity, absolute time or recording duration. Identity and relative timestamps only partition/reset history and supply time differences. The exact ordered feature-construction function is printed in Appendix C.')

heading('4. Alignment, validation and metric definitions')
sub('Reference-force alignment')
para('At optical time t, the target is reference force at t − L. Linear interpolation remains within a recording; duplicate reference timestamps are reduced by their median. Extrapolation and interpolation over gaps greater than 300 ms are prohibited. Lag candidates are 0, 100, 200, 300, 400 and 500 ms. Inner grouped NNLS MAE selects the smallest lag within 0.5% of the best error. TEST1–TEST6 use outer lags 300, 300, 200, 300, 300 and 300 ms, respectively. Tuning reuses these fold-local alignment decisions to retain identical evaluated rows and targets. [S4, S5]')
sub('Nested whole-group evaluation')
para('Each outer fold holds out one complete TEST group and its assigned no-contact recordings. The other five groups form five inner folds: four groups fit, one validates. Preprocessing, hyperparameters, feature pack, history, correction, thresholds and model choice are determined without the outer group. Fifteen possible four-group fits are cached; only the relevant inner-validation group is consumed for an outer selection. Thirty inner train/validation boundaries were audited. The final research refit uses all 15 leave-two-groups-out splits for selection, then fits the full pool. [S5, S9]')
para('Earlier optical rows from a held-out recording can initialize causal history, even if their force lies outside the scored interval. Their labels are not consumed. These are chronological stream predictions at stationary per-recording target taxels, not independent cold-start frames or demonstrated moving-contact localization.')
sub('One weighting convention for reported results')
para('For an evaluated recording s with n_s eligible rows, each row receives weight w_i = 1/n_s. Each recording therefore contributes one total unit. All headline, comparison and confusion-matrix percentages use these weights. For a force-bin subgroup, n_s is recomputed using only that bin. Raw matrix counts are deliberately unweighted integers. Training may use additional class/bin balancing; that is separate from evaluation weighting.')
table('Metric definitions; e = predicted force − reference force',['Metric','Definition'],[
 ['MAE; RMSE; bias','Σw|e|/Σw; sqrt(Σwe²/Σw); Σwe/Σw'],
 ['R²','1 − Σwe² / Σw(y − weighted mean of y)²'],
 ['Accuracy','Weighted correct predictions / total weight'],
 ['Recall; precision','TP/(TP+FN); TP/(TP+FP), using weighted outcomes'],
 ['Specificity; FPR','TN/(TN+FP); FP/(TN+FP)'],
 ['Balanced accuracy','Mean of class recalls; contact: (recall + specificity)/2'],
 ['Class F1; macro F1','2TP/(2TP+FP+FN); arithmetic mean of class F1 scores'],
 ['Row-normalized confusion matrix','100 × weighted cell / weighted actual-class row total']],[1.2,3.8])
para('Pooled macro F1 need not equal the mean of six fold macro F1 values. Nine-class accuracy equals balanced accuracy here because each taxel has six equally weighted recordings. Contact accuracy and balanced accuracy differ because there are 54 positive and 11 negative recordings. No new confidence interval or significance claim is inferred from thousands of temporally correlated frames.','small')

heading('5. Models, search and improvement strategy')
para('The fixed benchmark evaluates nine force regressors and six classifiers for each classification task. Seed 1729, 22 training subsets and 21 task-specific estimators yield 462 fits. Force uses the positive 9-feature pack; classifiers use optical 27. Force fitting balances recordings and 0.25 N bins, localization balances recordings, and contact balances classes and recordings. Fixed models use native decision rules without temporal smoothing, threshold tuning or force-output clipping. [S4, S7]')
para('The tuning run uses seed 1741 and a finite grid of 178 estimator/feature configurations: 62 force, 64 localization and 52 contact. Fifteen four-group training subsets yield 2,670 inner estimator fits. Additional output-history, correction, threshold and ensemble variants reuse cached inner predictions and are not counted as additional grid candidates. Appendix A lists every candidate, not only the winning settings. [S5, S8]')
table('Search mechanisms and exact decision rules',['Mechanism','Rule'],[
 ['Estimator and feature search','Candidate grids in Appendix A; common factory settings in Appendix B'],
 ['Output history','τ = 0, 0.3 or 1.0 s; index h = 0, 1 or 2'],
 ['Force output','Clip raw prediction to ≥0, apply selected output EMA, add inner-OOF residual offset, clip to ≥0 again'],
 ['Force offsets','None (=0), recording-weighted mean residual, or weighted median residual; select by inner MAE'],
 ['Localization','Smooth per-class scores, then argmax in class order T1–T9; select internally by macro F1'],
 ['Contact score','For SVC: sigmoid(decision_function); otherwise class-1 predict_proba; then selected output EMA'],
 ['Contact threshold','Exact weighted ROC operating points from inner OOF scores; balanced policy maximizes balanced accuracy'],
 ['Alternative contact policy','Maximize inner recall subject to inner FPR ≤5%; select family by recall, then FPR'],
 ['Ensembles','Equal mean of three best distinct tuned families; each member has its own selected history/correction'],
 ['Training weights','Recording weights, plus class balancing for contact; force for_000 alone uses bin weights in the tuning grid']],[1.35,3.9],small=True)
para('The tuned selector chooses across families using inner MAE, localization macro F1 or contact balanced accuracy; it adopts an ensemble only if the inner criterion improves. The tuned family rows instead restrict that inner search to one family. The present headline ranking follows the requested highest classification accuracy and lowest force MAE across the evaluated outer results.')
para('SVC sigmoid/softmax transformations provide score representations, not calibrated probabilities. A 1.0 s EMA time constant does not prove a measured 1.0 s event delay. The FPR ≤5% condition is an inner-selection constraint, not a guaranteed outer FPR.')

heading('6. Complete model comparisons')
para('All 50 saved comparison rows are retained below: 19 force, 15 localization and 16 contact. Rows are ordered by the requested criterion. “Tuned” identifies the expanded search, while unprefixed family names identify the fixed benchmark. “Nested selected” and “Tuned selected” are evaluated selection procedures, not new estimator families. [S2, S3]')
sub('6.1 Force estimation — rank by lowest MAE')
table('All force models on 7,154 frames / 54 recordings',['Rank','Model / procedure','MAE (N)','RMSE (N)','Bias (N)','R²'],
 [[r['rank_by_primary_metric'],r['model'],fnum(r['mae_N']),fnum(r['rmse_N']),fnum(r['bias_N']),fnum(r['r2'])] for r in COM if r['task']=='force'],
 [.55,2.5,1,1,1,1],highlight=[0])
para('The tuned ensemble reduces MAE from the strongest fixed model’s 0.6372 N to 0.4972 N: a 0.1400 N absolute reduction and 21.97% relative reduction. RMSE falls from 0.7705 N to 0.6299 N. Bias changes from −0.2894 N to +0.0827 N, and R² rises from −0.0303 to 0.3113. These describe the overall evaluation; low-force error remains substantial.')
para('No classification accuracy is assigned to a continuous force regressor. Negative fixed-model R² values mean worse squared error than the evaluation-set weighted mean reference. They do not mean negative physical accuracy.','small')

story.append(PageBreak());sub('6.2 Localization — rank by highest accuracy')
table('All localization models on 7,154 frames / 54 recordings',['Rank','Model / procedure','Accuracy (%)','Balanced accuracy (%)','Macro F1 (%)'],
 [[r['rank_by_primary_metric'],r['model'],pct(r['accuracy']),pct(r['balanced_accuracy']),pct(r['macro_f1'])] for r in COM if r['task']=='localization'],
 [.5,2.7,1.2,1.4,1.2],highlight=[0])
para('Tuned Logistic regression leads accuracy at 84.88%, compared with 73.87% for the most accurate fixed family, RBF SVC: an improvement of 11.01 percentage points. Tuned Logistic regression has 85.00% macro F1. The tuned ensemble has a slightly higher macro F1 (85.12%) but slightly lower accuracy (84.71%); Logistic regression is the headline winner under the requested accuracy criterion.')
para('The frame-only result excludes temporal features and output smoothing from its inner selection. It is an evaluated constrained selection procedure; its difference from the main winner cannot be attributed solely to one feature or one smoothing setting because selected models may also differ.')

story.append(PageBreak());sub('6.3 Contact detection — rank by highest accuracy')
table('All contact models on 8,506 frames / 65 recordings',['Rank','Model / procedure','Acc. (%)','Bal. acc. (%)','Macro F1 (%)','Recall (%)','Precision (%)','FPR (%)'],
 [[r['rank_by_primary_metric'],r['model'],pct(r['accuracy']),pct(r['balanced_accuracy']),pct(r['macro_f1']),pct(r['recall']),pct(r['precision']),pct(r['fpr'])] for r in COM if r['task']=='contact'],
 [.48,2.35,.85,.9,.95,.85,.95,.75],small=True,highlight=[0])
para('Tuned RBF SVC leads at 99.24% accuracy, compared with 91.91% for fixed Random Forest: +7.34 percentage points. Balanced accuracy rises from 91.86% to 99.54% (+7.68 points). Its contact recall is 99.09%, precision is 100.00%, specificity is 100.00%, and FPR is 0.00% on these held-out recordings.')
para('The “Tuned FPR ≤5%” procedure attains 99.57% recall but 8.76% outer FPR. Its name describes the inner constraint; the observed outer value is preserved explicitly. It is not the accuracy winner. Tuned contact AUC is not reported because adaptive fold models and uncalibrated score scales make pooled discrimination scores difficult to interpret consistently. No missing AUC is treated as zero.')

heading('7. Localization confusion matrices and spatial performance')
figure('01_best_localization_9x9_normalized','Localization: recording-weighted row-normalized 9 × 9 matrix',
 'Tuned Logistic regression. Actual taxel is the row; predicted taxel is the column. Each frame receives weight 1/n for its recording before row normalization. The diagonal is taxel recall. Six held-out TEST groups, 7,154 frames and 54 recordings. Numeric values appear in Table '+str(len(tables)+1)+'.',maxheight=555)
story.append(PageBreak())
figure('02_best_localization_9x9_raw_counts','Localization: separately labeled 9 × 9 raw frame counts',
 'The same winning-model held-out predictions, counted as integers without recording weights. Raw row totals differ because recordings contain unequal numbers of eligible frames. These counts must not be divided to reconstruct the weighted percentages.',maxheight=555)
story.append(PageBreak());sub('Machine-readable localization matrix values')
matrix_table('Localization row-normalized weighted percentages (%)','localization_row_normalized_percent.csv')
matrix_table('Localization raw counts (integer frames)','localization_raw_counts.csv',0)
para('Taxel 2 has the lowest weighted recall, 53.49%; 22.30% of its weighted predictions are assigned to T4. The next largest systematic routes include T8→T9 (18.07%), T7→T9 (16.22%) and T5→T9 (14.07%). Taxel 9 has 100.00% recall, which does not mean every prediction of T9 is correct: other taxels are also assigned to T9.')

story.append(PageBreak())
figure('05_best_models_taxel_heatmaps','Winning-model recall mapped to the nine physical image ROIs',
 'Left: Logistic-regression localization recall. Right: RBF-SVC positive-contact recall. Each taxel averages six held-out recording recalls. The rectangles retain saved pixel geometry. No-contact specificity is a separate class-level result, not a per-pressed-taxel value.',maxheight=430)
table('Exact taxel support and recall for the two winning classifiers',['Taxel','Eligible frames','Localization recall (%)','Contact recall (%)'],
 [[r['taxel'],r['frames'],fnum(r['localization_recall_percent'],2),fnum(r['contact_recall_percent'],2)] for r in TAX],[.8,1.2,1.7,1.7])

heading('8. Contact-detection confusion matrices')
figure('03_best_contact_2x2_normalized','Contact detection: recording-weighted row-normalized 2 × 2 matrix',
 'Tuned RBF SVC. Rows are actual labels and columns predicted labels. No-contact specificity is 100.00%; contact recall is 99.09%. Overall accuracy is 99.24%, while balanced accuracy is 99.54%. Six held-out groups, 8,506 frames and 65 recordings.',maxheight=535)
story.append(PageBreak())
figure('04_best_contact_2x2_raw_counts','Contact detection: separately labeled raw frame counts',
 'The 1,352 dedicated no-contact frames contain 1,352 true negatives and 0 false positives. The 7,154 eligible press frames contain 39 false negatives and 7,115 true positives. These are raw counts; the headline percentages use equal recording weights.',maxheight=535)
story.append(PageBreak());sub('Contact matrix values and full metric set')
matrix_table('Contact weighted row-normalized percentages (%)','contact_row_normalized_percent.csv')
matrix_table('Contact raw counts (integer frames)','contact_raw_counts.csv',0)
table('All headline contact metrics for Tuned RBF SVC',['Metric','Value (%)'],
 [[name,pct(M['contact'][key])] for name,key in [('Accuracy','accuracy'),('Balanced accuracy','balanced_accuracy'),
 ('Contact recall / sensitivity','recall'),('Contact precision','precision'),('No-contact specificity','specificity'),
 ('False-positive rate','fpr'),('Contact-class F1','contact_f1'),('Two-class macro F1','macro_f1')]], [3,1])
para('Contact-class F1 (99.54%) and macro F1 (98.67%) are different summaries. Macro F1 also includes the no-contact class, whose precision is reduced by missed positive frames. Reporting either simply as “F1” would be ambiguous.')
para('The positive-contact recall is 100.00% for T1–T7, 96.65% for T8 and 95.14% for T9. Zero observed false positives supports 100.00% specificity on these 11 controls; it does not establish a universal zero false-alarm rate. The dataset does not directly validate contact onset timing, intermittent releases or all excluded low-force/high-force frames.')
para(f'As a supplementary combined positive-frame measure, contact must be detected and the taxel must be correct on the same held-out frame. Its recording-weighted success is <b>{pct(D["combined_positive_detection_and_localization"])}%</b> across the 7,154 eligible press frames. This is a joint success metric, not a replacement for either task’s standalone accuracy.')

heading('9. Force errors and variation across held-out groups')
figure('force_diagnostics','Winning force ensemble: predicted force and error by reference interval',
 'Scatter: all held-out frames, with a dashed identity line; point density is descriptive and unweighted. Bars: recording-weighted MAE, with recording weights recomputed within each bin. The lowest-force intervals show marked overestimation.',maxheight=280)
table('Force ensemble errors by reference-force interval',['Interval (N)','Frames','Recordings','MAE (N)','RMSE (N)','Bias (N)'],
 [[f"[{r['lower']:g}, {r['upper']:g}"+(']' if r['upper']==3 else ')'),r['frames'],r['recordings'],fnum(r['mae_N']),fnum(r['rmse_N']),fnum(r['bias_N'])] for r in D['force_bins']],
 [1.3,.8,1,1,1,1])
para('The overall 0.4972 N MAE is not uniform over the interval. MAE is 1.2538 N below 0.5 N, 0.279 N at 2–2.5 N, and 0.530 N at 2.5–3 N. Positive low-force bias and negative high-force bias suggest compression toward intermediate force values. This pattern is a descriptive finding, not a proven causal explanation of the model behavior.')
para('A low pooled force error does not establish an accurate detection limit, calibrated linearity or acceptable error at every force. Dense upper-range coverage, weighting choices, timing, and manual loading trajectories may all affect model comparisons. A controlled matched-force experiment is needed to separate their effects.')

story.append(PageBreak());sub('Performance in each complete held-out TEST group')
foldrows=[]
for a,b,c in zip(D['folds']['force'],D['folds']['localization'],D['folds']['contact']):
    foldrows.append([a['fold'],a['frames'],c['frames'],fnum(a['mae_N']),pct(b['accuracy']),pct(b['macro_f1']),pct(c['accuracy']),pct(c['balanced_accuracy'])])
table('Winning-model performance by outer TEST group',['TEST','Press frames','Contact frames','Force MAE (N)','Loc. acc. (%)','Loc. F1 (%)','Contact acc. (%)','Contact bal. acc. (%)'],foldrows,[.55,.9,.9,1,1,1,1,1.1],small=True)
para('Localization varies from 48.41% in TEST1 to 98.20% in TEST5. Contact accuracy stays between 98.61% and 100.00%, while force MAE ranges from 0.4678 to 0.5683 N. TEST1 is the major localization weakness despite perfect observed contact detection there. Contact detection and identifying the correct taxel therefore have distinct difficulty profiles.')
para('These six groups are the relevant units for assessing generalization variability. Their training sets overlap, and frames within recordings are correlated. The displayed range is descriptive; it is not a confidence interval. A new independent collection is needed to estimate prospective performance after the final model choice.')
table('Force ensemble errors by pressed taxel',['Taxel','Frames','MAE (N)','RMSE (N)','Bias (N)','R²'],
 [[r['taxel'],r['frames'],fnum(r['mae_N']),fnum(r['rmse_N']),fnum(r['bias_N']),fnum(r['r2'])] for r in D['taxels']['force']],
 [.7,.9,1.1,1.1,1.1,1.1])
para('All subgroup values on this page were recomputed from the three winning models’ saved predictions. They are not copied from the distinct nested-selector procedure. Equal recording weighting is retained within every displayed subgroup.','small')

heading('10. Optical and light-response diagnostics')
sub('10.1 Direct HSV V brightness measurements')
para('V is the camera image brightness channel in its 8-bit 0-255 encoding. The direct metrics below quantify the recorded V values themselves: ROI mean brightness, baseline brightness, signed mean-brightness change, temporal variability, observed intensity range and peak pixel value. They are distinct from classifier accuracy and from the positive-only optical response used in the preceding feature analysis. [S16]')
para('The sample is unchanged: 7,154 eligible contact frames from 54 manual press recordings and 1,352 frames from 11 dedicated no-contact recordings. A taxel contact mean averages its six target-press recording means; its no-contact mean averages the 11 control recording means. Each recording has equal weight. These measurements describe the evaluated manual subset, not every archived frame.')
table('Direct V-channel metric definitions',['Metric','Definition'],[
 ['Raw ROI mean V','m_sjt = mean V over the fixed taxel pixels in one frame; recorded roi_j_mean_v'],
 ['Baseline mean V','b_sj = mean V across pixels and captured baseline frames, from that recording\'s baseline_summary.json mean_v'],
 ['Contact mean V','Average m_sjt over eligible contact frames within each recording, then average six recording means'],
 ['Signed mean-brightness change','For each recording, mean(m_sjt) - b_sj; then average six recordings. Negative values are retained'],
 ['Mean positive pixel change','Mean of max(V_pixel - baseline_median_pixel, 0); this existing positive-only statistic is not the signed mean-brightness change'],
 ['Temporal noise of raw V','RMS of within-control-recording sample SDs of m_sjt, ddof=1; 11 control recordings'],
 ['No-contact CV','100 x temporal noise SD / no-contact mean V; a relative temporal-stability descriptor']],[1.4,3.9],small=True)
table('Direct brightness and baseline-referenced change, in camera V levels',['Taxel','Baseline mean V','No-contact mean V','Contact mean V','Signed change V','Positive pixel change V'],
 [[r['taxel'],fnum(r['baseline_capture_mean_v'],3),fnum(r['no_contact_mean_v'],3),fnum(r['contact_mean_v'],3),
 fnum(r['baseline_referenced_mean_change_v'],3),fnum(r['mean_positive_delta_v'],3)] for r in V],
 [.6,1.2,1.3,1.2,1.2,1.35],small=True)
para('Mean raw V spans 26.091-26.755 without contact and 26.846-28.085 during eligible contact. The baseline column refers to the six press recordings\' own unloaded captures. Dedicated no-contact recordings are separate acquisitions and are not substituted for those per-recording baselines.','small')

story.append(PageBreak())
figure('v_channel_heatmaps','Direct raw-V brightness, signed baseline change and temporal noise',
 'Each 3 x 3 map follows taxel order T1-T9. Raw contact and no-contact panels share the same 25-29 V scale, so their colors are comparable. The signed-change panel retains both decreases and increases from the per-recording baseline-capture mean. Noise is the temporal SD of ROI mean V, not the SD of positive-clipped delta V.',maxheight=530)
para('A positive-only response can coexist with a negative mean-brightness change. Some pixels brighten while others darken, and the baseline may differ from the recording\'s later brightness level. Clipping negative pixel changes discards the decreases; taking an ROI mean first retains them. These two operations answer different questions and must not share one ambiguous "delta V" label.')
para('The baseline mean in the direct-V table is the saved mean over baseline frames and pixels. The positive-change feature uses the saved per-pixel median baseline. They are explicitly different reference constructions. The signs in this report are measured outcomes; a source of drift or illumination change is not established by these descriptive comparisons.','small')

story.append(PageBreak());sub('Raw-V variability, ranges and pixel peaks')
table('Temporal variation and observed contact brightness range',['Taxel','Control noise SD V','Contact temporal SD V','Control CV (%)','Min ROI mean V','Max ROI mean V','Peak pixel V'],
 [[r['taxel'],fnum(r['no_contact_temporal_noise_sd_v']),fnum(r['contact_temporal_sd_v']),fnum(r['no_contact_cv_percent'],3),
 fnum(r['contact_min_roi_mean_v'],3),fnum(r['contact_max_roi_mean_v'],3),str(int(float(r['contact_peak_pixel_v'])))] for r in V],
 [.6,1.3,1.35,1.1,1.2,1.2,1.05],small=True)
para('No-contact temporal noise of raw ROI mean V ranges from 0.1045 to 0.1246 V levels, with CV 0.399-0.466%. This quantifies short-term within-recording variability. It is not a pixel-level spatial standard deviation, a cross-recording SD, or the baseline_summary std_v field, which pools baseline pixels and frames.')
para('Contact temporal SD includes intentional force-related variation and therefore is not labeled sensor noise. Min/max ROI means are extrema over eligible frames; peak pixel V is the largest recorded ROI pixel maximum. A peak of 163 at T6, for example, does not imply an ROI mean of 163. No target peak reaches the encoded maximum of 255 in the evaluated press subset.')
table('Additional direct-V summaries',['Taxel','Median of recording medians V','Baseline change (%)','Contact-control contrast V','Contact mean /255 (%)'],
 [[r['taxel'],fnum(r['contact_median_of_recording_medians_v'],3),fnum(r['baseline_referenced_change_percent'],3),
 fnum(r['independent_control_contrast_v'],3),fnum(r['contact_mean_encoding_percent'],3)] for r in V],
 [.6,1.8,1.3,1.6,1.7],small=True)
para('Baseline-change percent averages 100 x (recording mean V - own baseline mean V) / own baseline mean V. The contact-control contrast compares independent recording groups and is not a paired causal contact effect. The /255 percentage describes the digital encoding only; it is not percent optical power, calibrated illuminance or sensor accuracy.')
para('These raw V metrics, together with positive-only response, active area and spatial distribution below, provide a direct brightness characterization. Physical sensitivity in V/N, calibrated lux, long-term drift and a detection limit require separate controlled measurements.','small')

story.append(PageBreak());sub('10.2 Positive optical response and spatial distribution')
para('Light diagnostics use the original manual acquisition frame_features.csv files matched exactly to the same 8,506 held-out frame identities. All 65 source CSVs were found; archive lineage, source hashes, unique frame joins and timestamps were checked. A stable identity combines archive hash, recording directory, zero-based row/video index and capture-frame identifier. [S10–S12]')
para('These acquisition-time CSV measurements are a companion optical analysis. Model training used video-recomputed features, so acquisition values are not claimed to be numerically identical to compressed-video measurements. The optical diagnostics are not an additional model training run.')
table('Light metrics supported by the available data',['Metric','Exact construction and aggregation'],[
 ['Positive mean ΔV: D_jt','Mean of per-pixel max(V−baseline,0) over taxel j'],
 ['Reference floor: b_j,−g','Median of recording medians of D_jt in no-contact controls outside held-out group g'],
 ['Excess response: E_jt','max(D_jt − b_j,−g, 0); mean within press recording, then equal mean over six recordings per target taxel'],
 ['Temporal noise: σ_j','Square root of the mean of within-recording sample variances (ddof=1) of D_jt across 11 no-contact recordings'],
 ['Robust noise','Per-control 1.4826 × MAD(D_jt); median across control recordings'],
 ['Response-to-noise proxy','Each press recording’s mean target E divided by RMS control SD outside its held-out group; mean over six presses'],
 ['Active-area fraction','Fraction of ROI pixels with ΔV≥10; average within recording, then over six presses; report as %'],
 ['Spatial response share','Average E_j over all eligible frames in a recording; normalize nine means to sum to 100%; average six profiles per pressed taxel'],
 ['Force–light association','Spearman correlation of target D_jt with the existing lag-aligned force within each recording; median over six records per taxel'],
 ['Drift / clipping diagnostics','No-contact raw-V last-quartile median minus first-quartile median; target raw maximum reaching 255 is a frame flag']],[1.35,3.9],small=True)
para('All 7,154 eligible press frames remain in the distribution calculation, including 1,153 with zero total excess. Each recording has a nonzero mean-response denominator. The spatial mean-then-normalize rule avoids dropping zero-response frames or implicitly weighting recordings by their length.')
para('Camera V levels are not lux or optical power. The response-to-noise ratio is an exploratory proxy, not calibrated photometric SNR. Off-target response is a spatial-spread/cross-talk proxy, not a measured mechanical transfer coefficient. Different manual force histories mean taxel averages cannot establish intrinsic sensitivity at matched force.')

story.append(PageBreak())
figure('06_light_response_distribution','Spatial distribution of excess optical response',
 'Rows identify the pressed taxel; columns identify the measured taxel. Values are recording-averaged shares of the nine mean excess responses, in percent. This is an optical response matrix, not a classifier confusion matrix. Taxel 4 spreads strongly toward T1–T3.',maxheight=555)
story.append(PageBreak())
figure('07_light_metrics_by_taxel','Optical response, temporal noise, active area and response-to-noise proxy',
 'Press measures average six recording means for each target taxel. Descriptive control noise uses all 11 controls; the response/noise proxy uses only controls outside each press group. Units and aggregation are defined in Section 10.',maxheight=555)
story.append(PageBreak())
figure('08_light_force_correlation','Within-recording force–light Spearman correlations',
 'Each cell compares the target taxel’s acquisition-time mean positive ΔV with the pre-existing aligned force in one TEST/taxel recording. No additional lag or signal threshold was optimized. The fixed −1 to +1 scale preserves negative associations; temporal dependence precludes independent-frame significance claims.',maxheight=555)

story.append(PageBreak());sub('Light measurements as searchable tables')
table('Target optical measurements by taxel',['Taxel','Mean positive ΔV','Mean excess ΔV','Noise SD ΔV','Robust σ ΔV','Active area (%)','Response / noise'],
 [[r['taxel'],fnum(r['mean_target_positive_delta_v']),fnum(r['mean_target_excess_delta_v']),fnum(r['no_contact_rms_within_recording_sd_delta_v']),
   fnum(r['no_contact_median_robust_sigma_delta_v']),fnum(r['mean_active_area_percent']),fnum(r['mean_response_to_noise_ratio'],3)] for r in LIGHT],
 [.6,1.2,1.2,1.1,1.1,1.1,1.2],small=True)
table('Response concentration and within-recording correlation summaries',['Taxel','Target share (%)','Off-target share (%)','Median ρ','Min ρ','Max ρ'],
 [[r['taxel'],fnum(r['mean_target_response_share_percent'],2),fnum(r['mean_off_target_response_share_percent'],2),fnum(r['median_force_light_spearman_rho'],3),
 fnum(r['min_recording_force_light_rho'],3),fnum(r['max_recording_force_light_rho'],3)] for r in LIGHT],[.6,1.4,1.4,1,1,1])
para('No-contact noise spans 0.0518–0.0567 camera V levels. Mean target excess spans 0.1291–0.7910 levels; response/noise proxy spans 2.43–13.98; active area spans 0.1093–1.3542%. These are observed descriptive ranges, not validated detection limits.')
para('Taxel 4 retains only 21.50% of total excess response in its own region, yet has 93.85% localization recall. The classifier can exploit the pattern across all regions; its accuracy need not track target-only optical concentration. Taxel 7 has the lowest median force–light correlation (ρ = 0.078), while T1 has the highest (ρ = 0.500).')

story.append(PageBreak());sub('Exact optical matrix values')
matrix_table('Excess-response distribution, mean recording-normalized shares (%)','light_response_distribution_percent.csv')
corr=readcsv(BEST/'data/light_force_spearman_by_group_taxel.csv')
table('Spearman ρ for every TEST group and taxel',['TEST']+[f'T{i}' for i in range(1,10)],
 [[r['outer_fold']]+[fnum(r[str(i)],3) for i in range(1,10)] for r in corr],[1]+[1]*9,small=True)
para('The correlation calculation has 5–537 paired eligible frames per recording, with different temporal dependence and force trajectories. Small-sample cells can be unstable. No p-values, causal sensitivity or linearity claims are inferred from these correlations.')
para('The recorded target maximum-V flag never reaches 255 in the evaluated press subset. This indicates no observed target-ROI raw maximum of 255 in these CSV rows; it does not prove that the complete optical system is free of saturation. Median no-contact raw-V quartile drift ranges from −0.0272 to +0.0126 levels across taxels. Neither value supplies long-term stability or recalibration intervals.')

heading('11. Exact winning model configurations')
para('The outer-fold configurations below generated the headline scores. Configuration IDs refer to the exhaustive grid in Appendix A. All members use weighted StandardScaler fitted on the corresponding training rows. Lag/floor fitting is training-only. The output-history index h maps 0→0 s, 1→0.3 s, 2→1.0 s. [S1, S8]')
table('Winning classifier configuration in each held-out fold',['TEST','Localization ID / pack','Loc. τ (s)','Contact ID / pack','Contact τ (s)','Contact threshold'],
 [[f,C['fold_model_configurations'][str(f)]['localization']['id']+' / '+C['fold_model_configurations'][str(f)]['localization']['candidate']['features'],
   C['fold_model_configurations'][str(f)]['localization']['tau'],
   C['fold_model_configurations'][str(f)]['contact']['id']+' / shape',C['fold_model_configurations'][str(f)]['contact']['tau'],
   repr(C['fold_model_configurations'][str(f)]['contact']['threshold'])] for f in range(1,7)],[.6,1.8,.9,1.6,.9,2],small=True)
para('Localization uses LogisticRegression(C=0.03, max_iter=2500, random_state=1741). TEST1 uses temporal features (288 dimensions) and τ=0.3 s. TEST2–TEST6 use invariant features (117 dimensions); their exact output time constants are listed above. Classification uses argmax of smoothed class scores.')
para('Contact uses SVC(C=1, kernel="rbf", gamma=1/90=0.011111111111111112, cache_size=256, decision_function_shape="ovr", random_state=1741) on shape features (90 dimensions). Its score is sigmoid(decision_function), followed by the listed EMA, then contact if score ≥ fold threshold. Thresholds were selected by the balanced-accuracy policy on inner OOF predictions.')
sub('Force ensemble composition')
para('Each outer prediction averages three separately tuned force families after their selected output EMA and residual correction. All winning force members use temporal features (288 dimensions). Most folds use for_050, for_056 and for_059; TEST2 uses for_055 in place of for_056. The exact folds, offsets and time constants follow on the next page.')
table('Force member estimator settings (additional defaults in Appendix B)',['ID','Estimator','Explicit settings'],[
 ['for_050','ExtraTreesRegressor','180 trees; min_samples_leaf=3; max_features=0.75; n_jobs=1; random_state=1741'],
 ['for_055','HistGradientBoostingRegressor','max_iter=180; learning_rate=0.05; min_samples_leaf=20; max_leaf_nodes=15; loss=squared_error; l2_regularization=10; early_stopping=False; random_state=1741'],
 ['for_056','HistGradientBoostingRegressor','As for_055, but max_leaf_nodes=31'],
 ['for_059','XGBRegressor','220 trees; learning_rate=0.04; min_child_weight=5; max_depth=5; reg_lambda=20; tree_method=hist; n_jobs=1; random_state=1741']],[.8,1.6,3.6],small=True)

story.append(PageBreak());sub('Exact force corrections and output history')
frows=[]
for f in range(1,7):
    for member in C['fold_model_configurations'][str(f)]['force']['members']:
        frows.append([f,member['id'],member['family'],member['tau'],member['correction'],repr(member['offset'])])
table('All 18 force-ensemble member settings used for held-out scoring',['TEST','Candidate','Family','τ (s)','Correction','Offset (N)'],frows,[.55,.9,1.15,.65,1,2.1],small=True)
para('Offsets are added after the selected EMA; the result is clipped at zero. “Median” means the weighted 0.5 quantile of inner OOF residuals y−prediction. The implementation sorts residuals and interpolates at q·Σw against cumulative weight minus half the current weight. It is not an outer-test residual correction.')
para('Training no-contact floors and scaler means/scales vary across folds and are learned preprocessing parameters rather than selected hyperparameters. Their estimator boundary is fixed by whole-recording group assignment; no held-out recording contributes. No single all-data configuration should be substituted for the six fold configurations when describing the source of these performance figures.')

story.append(PageBreak());sub('Full-pool research configurations available for inference')
para('After evaluation, full-pool research models were fitted. The available Logistic-regression component matches the winning family, while the saved localization manifest still routes the competing ensemble. This report does not change that manifest or the live GUI. These full-data settings are provided for reproducibility; their internal selection scores are not additional held-out test results.')
full=E['bundles']['models']
specforce=full['force']['saved_specification'];specloc=full['localization']['saved_specification'];speccon=full['contact']['saved_specification']
selectedfiles=['force_for_056.joblib','force_for_050.joblib','force_for_059.joblib','localization_loc_036.joblib','contact_con_022.joblib']
selectedmembers=[]
for task,v in full.items():
    if task=='contact_fpr5':continue
    for mem in v['members']:
        if mem['file'] in selectedfiles:
            choice=next(x['choice'] for x in v['saved_specification']['members'] if x['file']==mem['file'])
            selectedmembers.append((task,mem,choice))
table('Available full-pool best-family components',['File / candidate','Pack','τ (s)','Threshold or force offset'],
 [[mem['file'],mem['configuration']['features'],choice['tau'],
   ('offset='+repr(choice['offset'])) if task=='force' else ('threshold='+repr(choice['threshold']) if task=='contact' else 'argmax')]
  for task,mem,choice in selectedmembers],[2.2,1,.7,2.2],small=True)
para('Full-pool lag: 300 ms. Positive-light sum floors, in T1–T9 order: [3786, 4026, 2952, 3509, 3999, 3470, 3096, 3218, 2608]. Divide floor-corrected sums by the exact ROI areas before feature construction. Each saved estimator includes its fitted scaler; learned scalers must not be refitted on test data.')
para('Inference order: obtain correctly oriented V measurements and the saved baseline; compute ROI measurements; subtract the stored floor in the specified feature formula; update causal feature histories; apply the stored scaler; generate estimator scores; apply member-specific output history and force correction/contact threshold; average force member outputs; return force, contact and taxel. Reset state between recordings or at the specified time discontinuities.')
para('Exact scalar estimator parameters and relevant saved component hashes are printed in Appendix B. Model binary files retain learned weights/trees and scaler arrays. This document provides the complete scientific description and configuration; it does not replace the trained estimator binaries for running inference.','small')

heading('12. Findings, limitations and next experiments')
sub('Findings supported by the measurements')
para('Expanded optical patterns, causal history, hyperparameter tuning and output policies improve the pooled best results over the fixed benchmark. The most accurate localization family is regularized Logistic regression, the most accurate contact family is RBF SVC, and the lowest-MAE force model is a three-family ensemble. Increased model complexity alone is not an explanation: tree and MLP classifiers do not lead localization accuracy.')
para('The improvement is measured for the combined development strategy. The run does not contain a full factorial ablation that isolates the causal contribution of each feature, correction, weighting choice or model. Differences between the frame-only selector and the best family suggest useful temporal information, but are not a controlled estimate of a single EMA effect.')
para('Contact detection is consistently strong within the defined press/control comparison. Localization errors concentrate in TEST1 and specific taxel confusions, especially T2. Force regression remains the weakest task: overall R² is 0.3113 and low-force errors are large. Optical distributions show measurable off-target response, but classifiers can use distributed patterns successfully.')
sub('Limits that must remain in the thesis')
para('The dataset contains one archived manual collection with six TEST groups and 11 no-contact controls, not an independent multi-device or multi-day prospective trial. Family ranking uses observed outer results, so winner selection can be optimistic. Temporal smoothing benefits stationary recorded contacts; moving and multiple simultaneous contacts were not evaluated. Contact prevalence, dedicated-control design and restricted force eligibility limit transfer to continuous deployment.')
para('Reference-force uncertainty, physical taxel coordinates in millimetres, calibrated illumination, controlled matched-force sweeps, onset/release annotations and deployment latency were not established in this analysis. Accordingly, this report does not claim millimetre localization error, lux response, force detection limit, hysteresis, full-scale linearity, dynamic response time or a validated operating range.')
sub('Specific next experiments')
para('Freeze the three headline model families and all preprocessing before collecting a new manual test dataset. Repeat complete sessions across days, camera settings and mechanical reassemblies; include continuous no-contact periods, moving contacts and controlled onset/release transitions. Keep new test recordings outside all threshold and hyperparameter selection.')
para('For force, collect balanced repeated loading/unloading plateaus near 0.05–1 N and throughout 1–3 N; preserve loading direction and synchronized timing. For localization, prioritize T2 and the TEST1 acquisition conditions and record matched-force contacts to separate lighting spread from force effects. For contact, evaluate false alarms per unit time and missed events once episode annotations exist. Benchmark the exact intended winner stack with camera acquisition and feature extraction included before making latency claims.')

heading('13. Verification and computational reproducibility')
para('Training artifacts record a successful validation audit covering 114 aggregate metric comparisons (maximum absolute discrepancy approximately 1.25×10⁻¹⁵), 30 inner boundaries, source lineage, whole-recording splits, finite scalers, model checksums, refitted fold-1 predictions, label-independent inference, causal-prefix and future-invariance tests, state reset, and batch/streaming agreement. [S9]')
para('The optical analysis records 430 source validation checks and 120 analysis checks, with additional response-distribution verification. For this consolidation, the best-model prediction rows were loaded independently, all headline metrics recomputed, and both raw and weighted normalized matrices reproduced. New fold, force-bin and force-taxel diagnostics use those same winner rows. Existing artifacts were hashed before report generation and checked for preservation. [S1, S10–S13]')
table('Recorded experiment environment',['Component','Version / setting'],[
 ['Python','3.12.14; Windows 11 build 26200; 24 logical CPUs'],['NumPy / pandas','2.5.1 / 3.0.5'],
 ['scikit-learn / XGBoost','1.9.0 / 3.4.0'],['SciPy / joblib','1.18.0 / 1.5.3'],
 ['threadpoolctl / PyArrow','3.6.0 / 21.0.0'],['pytest','9.1.1'],
 ['Random seeds','1729 fixed benchmark; 1741 tuning'],['Tuned estimator execution','n_jobs=1 where explicitly set; threadpool_limits(limits=1) during fit']],[2,3])
para('A stored timing audit measured the original saved multi-task bundle, including the competing localization ensemble and alternate contact output: streaming median 41.10 ms and p95 44.46 ms, excluding camera acquisition and pixel feature extraction. That is not a new measurement of the standalone winning-family stack; it must not be cited as its deployed end-to-end latency. [S14]')
para('The immutable feature partitions were not re-read during this report update because their Windows access permissions deny access in the current session. The report relies on preserved training provenance, prediction tables, executed source snapshots and exact configuration exports; the raw archive was accessible in the optical audit. This update consolidates and verifies saved evidence without retraining or changing deployment.')
sub('Reproduction sequence')
para('1. Verify the manual archive hash and exclude automatic/replay-only lineage. 2. Extract the original-video ROI feature contract and saved baselines. 3. Preserve whole-recording TEST assignments and reproduce fold-local force alignment. 4. Fit floor/scaler and candidates only on each training boundary. 5. Apply inner selection and score each outer group once. 6. Pool predictions with recording weights and reproduce the comparison tables. 7. Rank families by the report’s stated criterion. 8. Produce confusion and optical figures from the corresponding saved rows. 9. Use independent new recordings for prospective validation.')

heading('14. Ready-to-use ChatGPT Writing instructions')
para('The following prompt can be pasted into ChatGPT Writing together with this PDF. It specifies the evidence hierarchy and prevents accidental mixing of different model scores.')
para('<b>Writing prompt</b>','h2')
para('Use the attached “Manual Calibration: Complete Technical Report” as the technical source for my thesis. Follow a standard thesis structure: Introduction and objectives, Related work, System and experimental design, Methodology, Results, Discussion, Conclusions and future work. Write formal academic prose with clear equations and numbered tables/figures. Keep methodological detail sufficient for replication.')
para('Use the following models consistently in the abstract, results, discussion and conclusion: localization = Tuned Logistic regression, 84.88% accuracy and 85.00% macro F1; contact detection = Tuned RBF SVC, 99.24% accuracy, 99.54% balanced accuracy, 99.09% recall, 100.00% precision and specificity, 99.54% contact-class F1 and 98.67% macro F1; force = Tuned ensemble, MAE 0.4972 N, RMSE 0.6299 N, bias +0.0827 N and R² 0.3113. Do not combine metrics from different models or substitute internal selection scores for held-out scores.')
para('State that only Manual Calibration (2).zip was used. Evaluation used six complete TEST groups, 7,154 eligible press frames from 54 recordings for force/localization and 8,506 frames from 65 recordings for contact. Explain equal recording weighting, the inclusive 0.05–3 N interval, train-only preprocessing, nested group selection, causal history and the retrospective final family ranking. Keep all competing models in comparison tables while emphasizing the three headline winners.')
para('Include the 9 × 9 localization and 2 × 2 contact matrices in separately labeled row-normalized and raw-count views. Rows are actual labels; columns predicted labels. The normalized matrices use recording weights, so their values cannot be reconstructed by dividing raw counts. Include ROI performance heatmaps, the optical response-distribution matrix and light diagnostics. Distinguish optical response share from classification accuracy, and camera V units from lux or calibrated optical power.')
para('Use the exact ROI coordinates, segmentation threshold, feature definitions, fold configurations, training seeds, candidate grid and estimator parameters in this report. Describe the evaluation fold configurations separately from the available full-data research fit. Do not say the winning models were deployed in the live GUI. Force is regression; do not invent a force-accuracy percentage.')
para('Report direct HSV V brightness metrics from Section 10.1: raw mean V, own baseline-capture mean V, signed mean-brightness change, raw-V temporal noise and CV, ROI-mean ranges and peak pixel V. Keep these separate from the mean positive-clipped per-pixel change and excess-response metrics in Section 10.2. Preserve negative baseline changes and distinguish temporal SD from spatial pixel SD. Do not reinterpret digital V levels or /255 percentages as lux, optical power or model accuracy.')
para('Discuss TEST1 localization weakness, T2 confusion, low-force overestimation, limited force R², dedicated control recordings, temporal dependence, the restricted force interval and the lack of untouched prospective validation. Attribute improvements to the combined search strategy; do not invent causal ablation results, statistical significance, confidence intervals, physical detection limits, calibrated sensitivity, millimetre errors or end-to-end latency.')
para('Use this report’s project source IDs as internal evidence. For the Related work chapter, obtain and verify scholarly sources separately; do not invent authors, publications, hardware specifications, citations or unrecorded experimental details. Mark genuinely missing thesis information for the researcher to supply. Preserve every supplied numeric result and its units. End with specific future experiments grounded in the reported limitations.')

heading('Appendix A. Exhaustive tuning configuration grid')
para('This appendix contains all 178 estimator/feature candidates. Each row specifies its task-local ID, family, feature pack, training-weight code and varied parameters. Common constructor settings in Appendix B and feature definitions in Section 3 complete the configuration. Grid membership does not imply that every candidate has its own reported outer test row; inner selection produces the 50 family/procedure comparisons.')
para('Weight code “session” means recording weights, with additional class balancing for contact. “bins” is force bin/recording balancing. Feature dimensions: positive=9, optical=27, shape=90, spatial=180, invariant=117, temporal=288. Parameters such as gamma_multiplier are translated by the factory: SVC gamma = multiplier / feature dimension.')
for task in ['force','localization','contact']:
    if task!='force':story.append(PageBreak())
    cand=[x for x in P['candidates'] if x['task']==task]
    sub(f'{task.capitalize()} — {len(cand)} candidates')
    table(f'Complete {task} candidate grid',['ID','Family','Features','Weights','Varied parameters'],
      [[v['id'],v['family'],v['features'],v['weights'],'; '.join(f'{k}={json.dumps(x)}' for k,x in v['params'].items())] for v in cand],
      [.8,1.25,.9,.8,3.25],small=True,compact=True)

heading('Appendix B. Exact estimator settings and saved components')
para('The following constructor is the executed tuning factory. It combines with every candidate in Appendix A. Unspecified parameters follow the recorded library versions; complete get_params exports for the best full-pool components and the fixed benchmark are printed below. Serialized null values retain the source export representation, including the XGBoost missing-value default.')
src=(TUNE/'source_snapshot/scripts/tune_manual_models.py').read_text(encoding='utf-8-sig')
factory=src[src.index('def estimator('):src.index('\ndef scores(')].strip()
factory_display='''def estimator(config, n_features):
    task, family, p = config["task"], config["family"], dict(config["params"])
    regression = task == "force"
    if family in ("Extra Trees", "Random Forest"):
        cls = {("Extra Trees", True): ExtraTreesRegressor,
               ("Extra Trees", False): ExtraTreesClassifier,
               ("Random Forest", True): RandomForestRegressor,
               ("Random Forest", False): RandomForestClassifier}[family, regression]
        return cls(n_estimators=180, n_jobs=1, random_state=SEED, **p)
    if family == "HistGB":
        cls = HistGradientBoostingRegressor if regression else HistGradientBoostingClassifier
        return cls(max_iter=180, learning_rate=.05, min_samples_leaf=20,
                   early_stopping=False, random_state=SEED, **p)
    if family == "XGBoost":
        cls = XGBRegressor if regression else XGBClassifier
        return cls(n_estimators=220, learning_rate=.04, min_child_weight=5,
                   tree_method="hist", n_jobs=1, random_state=SEED, **p)
    if family == "Logistic regression":
        return LogisticRegression(max_iter=2500, random_state=SEED, **p)
    if family == "RBF SVR":
        return SVR(cache_size=256, **p)
    if family == "RBF SVC":
        p["gamma"] = p.pop("gamma_multiplier") / n_features
        return SVC(cache_size=256, decision_function_shape="ovr", random_state=SEED, **p)
    if family == "MLP":
        cls = MLPRegressor if regression else MLPClassifier
        return cls(max_iter=350, early_stopping=False, learning_rate_init=.001,
                   random_state=SEED, **p)
    raise ValueError(family)'''
assert ast.dump(ast.parse(factory)) == ast.dump(ast.parse(factory_display))
assert max(map(len,factory_display.splitlines()))<=94
code('SEED = 1741\n'+factory_display,width=94)
sub('Best-family full-pool components: complete parameter exports')
for task,mem,choice in selectedmembers:
    param_block(mem['file'],mem['all_estimator_parameters'])
    scaler=mem['scaler']
    para(f'Scaler: with_mean={scaler["with_mean"]}; with_std={scaler["with_std"]}. Feature order and dimension follow the named pack. Learned scaler arrays and estimator weights/trees are stored together in the joblib component.','small')
    sm=next(x for x in full[task]['saved_specification']['members'] if x['file']==mem['file'])
    para('SHA256: '+sm['sha256'],'small')
para('For the TEST2 force member for_055, use the full HistGB parameter set above with max_leaf_nodes=15 instead of 31. For the TEST1 localization member loc_048, use the same Logistic-regression parameter set with temporal rather than invariant features and the fold-specific scaler/history. These are changes to the input pack and selected output history, not changes to C.')
story.append(PageBreak());sub('Fixed benchmark: complete parameters')
para('Force estimators use positive=9. Total-light linear and isotonic reduce the scaled nine channels to their sum; the fitted median baseline ignores X. Classifiers use optical=27. Fixed classifiers use native decisions (probability threshold 0.5 or SVC decision threshold 0), with no output EMA or debounce. Fixed force predictions are not clipped. Contact and localization have the same recorded constructor parameters for each family; XGBoost’s classifier resolves its multiclass objective during localization fitting. [S4, S7]')
for name,params in FIXED['force'].items():param_block('Force — '+name,params)
for name,params in FIXED['contact'].items():
    assert params==FIXED['localization'][name]
    param_block('Contact and localization — '+name,params)

heading('Appendix C. Exact feature-construction source')
para('The following function preserves the executed block order. AREA_COLUMNS, RAW_LIGHT_COLUMNS, SIGNED and ACTIVE_COLUMNS list the nine taxels in ascending order; they respectively contain ROI areas, raw positive-light sums, signed-light sums and active fractions. Frames must already be ordered chronologically within recording. The input floor is the training-only nine-vector described in Section 3.')
# Feature lines are <=106 chars; at 7.1 pt this fits the content width without changing source.
feature_style=ParagraphStyle('FeatureSource',parent=ST['code'],fontSize=7.1,leading=9.8)
flines=E['exact_feature_construction_source'].rstrip().splitlines()
for start in range(0,len(flines),32):
    story.append(Preformatted('\n'.join(flines[start:start+32]),feature_style))
    if start+32<len(flines):story.append(Spacer(1,8))
para('The feature code computes histories for all available optical frames before eligibility masking. Neither the target force nor target taxel enters the estimator feature array. No neural-network segmentation, image morphology, future-frame filtering or zero-response rejection is applied.')

heading('Appendix D. Evidence register and artifact integrity')
para('Paths below are relative to the shared SOFTWARE CALIBRATION project unless noted. They identify inspectable project evidence, not external academic literature. This PDF embeds the numbers and figures needed for thesis writing; the source files remain available for deeper replication.')
source_defs=[
 ('S1','Consolidated best metrics, matrices and fold configurations','reports/BEST_RESULTS/BEST_METRICS.json'),
 ('S2','All 50 fixed and tuned comparison rows','reports/BEST_RESULTS/reference/all_competing_models_ranked.csv'),
 ('S3','Winning-model held-out prediction rows','reports/BEST_RESULTS/data/best_models_held_out_predictions.parquet'),
 ('S4','Fixed benchmark protocol','calibration_gui/analysis_outputs/live_sensor_manual_only/model_runs/retraining_20260909/protocol.json'),
 ('S5','Tuning protocol and full 178-candidate grid','calibration_gui/analysis_outputs/live_sensor_manual_only/model_runs/tuning_20260909/protocol.json'),
 ('S6','Fixed-run dataset and feature provenance','calibration_gui/analysis_outputs/live_sensor_manual_only/model_runs/retraining_20260909/provenance.json'),
 ('S7','Fixed estimator parameter export','calibration_gui/analysis_outputs/live_sensor_manual_only/model_runs/retraining_20260909/estimator_parameters.json'),
 ('S8','Exact segmentation, model defaults and feature source','reports/manual_calibration_thesis_report_2026-10-05/Exact_Segmentation_and_Model_Configurations.json'),
 ('S9','Tuning validation audit','calibration_gui/analysis_outputs/live_sensor_manual_only/model_runs/tuning_20260909/validation_audit.json'),
 ('S10','Optical source validation','reports/manual_calibration_matrices_and_light_metrics_2026-10-18/source_validation.json'),
 ('S11','Optical analysis methods and interpretation','reports/manual_calibration_matrices_and_light_metrics_2026-10-18/Technical_Notes_for_Thesis.txt'),
 ('S12','Optical metric calculations and validation','reports/manual_calibration_matrices_and_light_metrics_2026-10-18/metrics_and_validation.json'),
 ('S13','Independent winner-metric and matrix recomputation for this report','reports/complete_thesis_report_2026-10-18/derived_evidence.json'),
 ('S14','Saved original-bundle timing audit','calibration_gui/analysis_outputs/live_sensor_manual_only/model_runs/tuning_20260909/inference_timing.json'),
 ('S15','Prior report: acquisition context and hardware evidence register','reports/manual_calibration_thesis_report_2026-10-05/Manual_Calibration_Models_Technical_Report.txt'),
 ('S16','Direct HSV V metrics, baseline provenance and calculation checks','reports/manual_v_channel_metrics_2026-10-18/v_channel_metrics.json'),
]
for sid,title,path in source_defs:
    file=ROOT/path;assert file.exists(),file
    h=sha(file);sources.append({'id':sid,'title':title,'path':path,'sha256':h})
    story.append(KeepTogether([Paragraph(sid+' — '+title,ST['h2']),
        Paragraph(escape(path),ST['small']),Paragraph('SHA256: '+h,ST['small'])]))
sub('Manual archive')
para('External original path: C:/Users/DLSU/Downloads/THESIS DATA/Data Collection/Manual Calibration (2).zip. Recorded size: 1,283,430,583 bytes. SHA256: e039dcd49f3390d34dc979490dcf46a6ecc43d9e6a2aec08e4952acc14b5006a. The report does not import automatic-calibration data.','small')
sub('Additional reproducibility files')
para('BEST_RESULTS/BEST_MODEL_CONFIGURATIONS.json provides all six winning-family fold settings; BEST_RESULTS/figure_manifest.json and Figure_Captions.txt map the eight reused figures. The tuning run’s selections_fold1.json through selections_fold6.json, final_selections.json, source_snapshot/, environment.json and models/ preserve the detailed run. The raw manual optical source-member manifest and all light CSV tables remain under BEST_RESULTS/data/.','small')
para('The complete comparison table contains all 50 evaluated family/procedure rows. The candidate appendix contains all 178 configurations. Every matrix and quantitative heatmap has its numeric values printed in searchable tables. No competing model, previous report, prediction row, or source figure is removed by this update.')

assert len(COM)==50 and len(P['candidates'])==178 and len(selectedmembers)==5
assert Counter(r['task'] for r in COM)=={'force':19,'localization':15,'contact':16}
Report(PDF).multiBuild(story)
manifest={'pdf':str(PDF),'sections':headings,'tables':tables,'figures':figures,'sources':sources,
          'model_comparison_rows':len(COM),'candidate_count':len(P['candidates']),
          'pdf_sha256':sha(PDF),'pdf_bytes':PDF.stat().st_size}
(HERE/'report_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({'pdf':str(PDF),'bytes':PDF.stat().st_size,'tables':len(tables),'figures':len(figures),'sections':len(headings)},indent=2))
