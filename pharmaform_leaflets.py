"""Read strength-specific sections from official Brazilian leaflets.

Manufacturer routes are discovery adapters, not product/formula profiles.
Unsupported structures stay documentary evidence; no guessed percentages.
"""
import re
from urllib.parse import urlparse, quote
from hashlib import sha256
from bs4 import BeautifulSoup
from pharmaform_core import norm, parse_dose
from pharmaform_identity import international_name

ALLOWED_HOSTS={'produtos.apsen.com.br','statics.apsen.com.br','www.apsen.com.br','apsen.com.br',
 'bula.medicamentos.anvisa.gov.br','consultas.anvisa.gov.br','www.anvisa.gov.br'}


def safe_url(url):
    p=urlparse(url)
    return p.scheme=='https' and p.hostname in ALLOWED_HOSTS and p.port in (None,443) and not p.username and not p.password


def parse_leaflet(text, target, url):
    from pharmaform_research import record
    dose, per_ml=parse_dose(target.dose)
    if per_ml or target.form not in ['Cápsula dura','Comprimido simples','Comprimido revestido']: return None
    s=norm(text)
    if not target.product or not re.search(r'(?<!\w)'+re.escape(norm(target.product))+r'(?!\w)',s[:3000]): return None
    form=r'capsula' if target.form=='Cápsula dura' else r'comprimido'
    pattern=rf'cada {form}(?:\s+revestido)?\s+de\s+(\d+(?:[.,]\d+)?)\s*mg\s*contem\s*:?'
    sections=list(re.finditer(pattern,s))
    matching=[(i,m) for i,m in enumerate(sections) if abs(float(m.group(1).replace(',','.'))-dose)<1e-8]
    if not matching: return None
    i,m=matching[0]
    block=s[m.end():sections[i+1].start() if i+1<len(sections) else m.end()+1500]
    # Read only an explicit equivalence statement and its adjacent material amount.
    pair=re.search(r'^\s*([a-z][a-z /-]+?)\s*\(\s*equivalente a\s*(\d+(?:[.,]\d+)?)\s*mg\s+de\s+([a-z -]+?)\s*\)\s*[.\s|:…_-]*(\d+(?:[.,]\d+)?)\s*mg',block)
    if not pair: return None
    material,base_amount,base_name,mat_amount=pair.groups()
    base_amount=float(base_amount.replace(',','.'));mat_amount=float(mat_amount.replace(',','.'))
    if base_amount!=dose or not .1 <= mat_amount/base_amount <= 10: return None
    if target.api and international_name(target.api)!=international_name(material.strip()):
        # A different salt or unrelated API must not be silently replaced.
        target.identity_conflict='A bula oficial e o IFA informado não coincidem. Confira a espécie química.'
        return None
    ingredient_match=re.search(r'excipientes\s*:\s*([^\n]+?)(?:\.\s|$)',block)
    if not ingredient_match: return None
    ingredients=ingredient_match.group(1)
    # Shell components cannot be assigned to capsule fill. Keep the complete Q1 in finding.
    names={'amido':'Amido (grau a conferir)','amido pre-gelatinizado':'Amido pré-gelatinizado',
      'estearato de magnesio':'Estearato de magnésio','celulose microcristalina':'Celulose microcristalina',
      'lactose':'Lactose','crospovidona':'Crospovidona','croscarmelose sodica':'Croscarmelose',
      'dioxido de silicio':'Dióxido de silício','povidona':'Povidona','talco':'Talco','manitol':'Manitol'}
    q1=[v for k,v in names.items() if re.search(r'(?<!\w)'+re.escape(k)+r'(?!\w)',ingredients)]
    if 'Amido pré-gelatinizado' in q1: q1=[x for x in q1 if x!='Amido (grau a conferir)']
    r=record('Bula oficial do fabricante',target.product+' — '+f'{dose:g} mg',url,'Bula da apresentação solicitada',locator=m.group(0))
    release='Retardada' if re.search(r'gastro.?resistent|liberacao retardada',block) else 'Prolongada' if 'liberacao prolongada' in block else 'Convencional'
    r.update(q1=q1,target_q1=bool(q1),reference_match=True,dose_matches=True,detected_release=release,
       architecture=target.form+' '+release,substance_names=[international_name(material.strip())],
       generic_names=[international_name(material.strip())],status='Composição da dose extraída da bula oficial',
       finding=f'{base_amount:g} mg de {base_name.strip()} equivalem a {mat_amount:g} mg de {material.strip()}. Q1 publicada: {ingredients}.',
       excerpt=block[:1500],document_sha256=sha256(text.encode()).hexdigest())
    target.api=material.strip()
    target.identity_terms += [international_name(material.strip()),international_name(base_name.strip())]
    target.label_factor=mat_amount/base_amount
    target.label_factor_source=r['id']
    target.mw_source_ids=[r['id']]
    if target.release=='Identificar pela referência': target.detected_release=release
    return r


def official_leaflet(target):
    from pharmaform_research import get_url
    urls=[target.label_url] if target.label_url else []
    if not urls and target.product and re.fullmatch(r'[a-z0-9 -]+',norm(target.product)):
        # One public manufacturer adapter; no assertion that every brand belongs to Apsen.
        urls=['https://produtos.apsen.com.br/'+quote(norm(target.product).replace(' ','-'))]
    issues=[]
    for url in urls:
        if not safe_url(url):
            issues.append('Bula: endereço não suportado. Use HTTPS de fabricante/autoridade habilitado.');continue
        response,error=get_url(url)
        if error:
            issues.append('Bula oficial: '+error);continue
        if not safe_url(response.url):
            issues.append('Bula: redirecionamento para domínio não habilitado.');continue
        if response.content[:4]==b'%PDF':
            from pypdf import PdfReader
            from io import BytesIO
            text='\n'.join(p.extract_text() or '' for p in PdfReader(BytesIO(response.content)).pages[:15])
        else:
            soup=BeautifulSoup(response.text,'html.parser')
            for e in soup(['script','style','nav','footer']): e.decompose()
            text=soup.get_text(' ',strip=True)
        r=parse_leaflet(text,target,url)
        if r: return [r],issues,[{'source':'Bula oficial','query':url}],[]
        issues.append('Bula oficial: identidade, forma ou seção da dose não confirmada no documento recebido.')
    return [],issues,[],[]
