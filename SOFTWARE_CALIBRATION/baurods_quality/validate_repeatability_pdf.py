"""Check the revised PDF's evidence and render every page for visual review."""
from pathlib import Path
import csv, hashlib, json, re, subprocess
from pypdf import PdfReader
import pdfplumber
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parent
WORK=ROOT.parent
PDF=WORK/'output/pdf/BAURods_Manual_Calibration_Technical_Report.pdf'
OUT=ROOT/'outputs/repeatability_20261018'
QA=WORK/'tmp/pdfs/manual_calibration_repeatability_v1_1'
QA.mkdir(parents=True,exist_ok=True)
reader=PdfReader(PDF)
texts=[p.extract_text() or '' for p in reader.pages]
text='\n'.join(texts)
required=['Part VIII','Table R1.','Table R2.','Table R3.','Table R4.','Table R5.','Table R6.',
          '0.0811','-0.0087','0.1708','0.1946','0.1597','0.2352','CV3J','50,000',
          'simultaneous two-way clustering','not electrical volts','no acceptance threshold']
for token in required:assert token in text,token
assert 38<=len(reader.pages)<=42
assert len(text)>100000
assert all(len(t.strip())>100 for t in texts)
assert '\u25a0' not in text
embedded={hashlib.sha256(im.image.convert('RGB').tobytes()).hexdigest() for p in reader.pages for im in p.images}
for p in (OUT/'figures').glob('*.png'):
    assert hashlib.sha256(Image.open(p).convert('RGB').tobytes()).hexdigest() in embedded,('PDF does not contain latest chart',p.name)
with (OUT/'tables/repeatability_intervals.csv').open(newline='') as f:
    for r in csv.DictReader(f):
        if r['statistic'] in ['optical_cv_percent','force_cv_percent']:
            for k in ['estimate','ci95_lower','ci95_upper']:
                assert f"{float(r[k]):.2f}" in text,(r['taxel'],r['statistic'],k)
bad=[]
with pdfplumber.open(PDF) as doc:
    for i,p in enumerate(doc.pages,1):
        for word in p.extract_words():
            if word['x0']<30 or word['x1']>p.width-30 or word['top']<10 or word['bottom']>p.height-10:
                bad.append({'page':i,'word':word})
assert not bad,bad[:5]
poppler=Path('C:/Users/DLSU/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe')
subprocess.run([str(poppler),'-r','75','-png',str(PDF),str(QA/'page')],check=True,capture_output=True)
images=sorted(QA.glob('page-*.png'))
assert len(images)==len(reader.pages)
font=ImageFont.truetype('C:/Windows/Fonts/calibri.ttf',19)
for start in range(0,len(images),12):
    canvas=Image.new('RGB',(1320,1960),'#dce3e8');draw=ImageDraw.Draw(canvas)
    for j,path in enumerate(images[start:start+12]):
        im=Image.open(path).convert('RGB');im.thumbnail((410,450))
        x=(j%3)*440+15;y=(j//3)*490+31
        draw.text((x,y-25),f'Page {start+j+1}',font=font,fill='#18354b')
        canvas.paste(im,(x,y))
    canvas.save(QA/f'contact_sheet_{start//12+1}.png')
receipt={'pdf':str(PDF),'pdf_sha256':hashlib.sha256(PDF.read_bytes()).hexdigest(),
         'pages':len(reader.pages),'all_key_statistics_present':True,'all_pages_nonblank':True,'latest_chart_pixels_match':True,
         'text_within_page_bounds':True,'rendered_pages':len(images),'contact_sheets':(len(images)+11)//12,
         'visual_inspection':'pending','render_directory':str(QA)}
(WORK/'output/pdf/repeatability_pdf_verification.json').write_text(json.dumps(receipt,indent=2))
for i,t in enumerate(texts,1):
    if i==1 or 'Part VIII' in t or i>=31:print(f'PAGE {i}: '+t[:230].replace('\n',' | '))
print(json.dumps(receipt,indent=2))
