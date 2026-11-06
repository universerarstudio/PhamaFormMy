"""Search vocabulary only. Synonyms never supply a formulation or salt factor."""
import re
import unicodedata

def clean(s):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD',s.lower()) if not unicodedata.combining(c)).split())

# Candidates must subsequently be confirmed by PubChem or product label evidence.
NAMES = {'atomoxetina':'atomoxetine','metformina':'metformin','paracetamol':'acetaminophen',
 'ibuprofeno':'ibuprofen','omeprazol':'omeprazole','pantoprazol':'pantoprazole','sertralina':'sertraline',
 'fluoxetina':'fluoxetine','venlafaxina':'venlafaxine','duloxetina':'duloxetine','bupropiona':'bupropion',
 'amoxicilina':'amoxicillin','azitromicina':'azithromycin','cefalexina':'cephalexin',
 'losartana':'losartan','valsartana':'valsartan','atorvastatina':'atorvastatin',
 'rosuvastatina':'rosuvastatin','sinvastatina':'simvastatin','levotiroxina':'levothyroxine',
 'clonazepam':'clonazepam','carbamazepina':'carbamazepine','lamotrigina':'lamotrigine',
 'quetiapina':'quetiapine','risperidona':'risperidone','olanzapina':'olanzapine',
 'escitalopram':'escitalopram','citalopram':'citalopram','prednisona':'prednisone',
 'prednisolona':'prednisolone','fexofenadina':'fexofenadine','loratadina':'loratadine',
 'cetirizina':'cetirizine','lisdexanfetamina':'lisdexamfetamine','metilfenidato':'methylphenidate',
 'guanfacina':'guanfacine','enalapril':'enalapril','captopril':'captopril',
 'hidroclorotiazida':'hydrochlorothiazide','furosemida':'furosemide',
 'espironolactona':'spironolactone','alopurinol':'allopurinol','sildenafila':'sildenafil',
 'tadalafila':'tadalafil','montelucaste':'montelukast','dipirona':'metamizole'}
SALTS={'cloridrato':'hydrochloride','bromidrato':'hydrobromide','fosfato':'phosphate',
 'sulfato':'sulfate','maleato':'maleate','fumarato':'fumarate','citrato':'citrate',
 'tartarato':'tartrate','succinato':'succinate','mesilato':'mesylate','besilato':'besylate'}

def international_name(name):
    s=clean(name)
    for pt,en in NAMES.items(): s=re.sub(r'\b'+re.escape(pt)+r'\b',en,s)
    for pt,en in SALTS.items():
        m=re.fullmatch(re.escape(pt)+r'\s+(?:de\s+)?(.+)',s)
        if m: s=m.group(1)+' '+en; break
    s=re.sub(r'\b(sodica|sodico)\b','sodium',s)
    s=re.sub(r'\b(potassica|potassico)\b','potassium',s)
    return s
