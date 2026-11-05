"""PharmaForm 0.2: pesquisa real + relatório revisável; não presume Q2."""
import io, json, os, re, unicodedata
from datetime import datetime
from urllib.parse import quote
import pandas as pd
import requests
import streamlit as st
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from xml.sax.saxutils import escape

st.set_page_config(page_title='PharmaForm',page_icon='💊',layout='wide')
st.title('PharmaForm')
st.caption('Pesquisa documental → proposta revisável → relatório PDF | Protótipo 0.2')
st.info('O aplicativo pesquisa fontes públicas reais. Não inventa fórmula quantitativa: Q2 e processo só são fechados quando houver evidências e revisão técnica.')

FORMS=['Pó para suspensão oral','Comprimido revestido','Comprimido simples','Cápsula dura','Solução oral','Comprimido sublingual']
PROCESS={
'Pó para suspensão oral':['Caracterizar IFA, excipientes e embalagem; verificar necessidade de classificação','Definir a estratégia de mistura/granulação com base nas propriedades dos materiais','Preparar as frações de pó/grânulos e controlar granulometria e umidade','Realizar mistura final e avaliar uniformidade/segregação','Envasar a massa-alvo por frasco e avaliar uniformidade entre frascos','Reconstituir conforme volume definido; avaliar pH, viscosidade, redispersão, teor e estabilidade'],
'Comprimido revestido':['Caracterizar materiais e necessidade de classificação','Escolher compressão direta ou granulação conforme evidências de fluxo e compactabilidade','Realizar mistura/granulação e secagem, quando aplicável','Mistura final, lubrificação e controle de uniformidade','Compressão e controles de massa, dureza, friabilidade e desintegração','Aplicar revestimento e avaliar ganho de massa, dissolução e estabilidade'],
'Comprimido simples':['Caracterizar matérias-primas e granulometria','Selecionar rota: compressão direta ou granulação conforme dados','Mistura, granulação/secagem se aplicável e lubrificação','Compressão e controles em processo','Avaliar dissolução, uniformidade e estabilidade'],
'Cápsula dura':['Caracterizar materiais e necessidade de classificação','Estudar mistura, fluidez e segregação','Selecionar cápsula e ajustar massa de enchimento','Encapsular e controlar massa e uniformidade','Avaliar desintegração, dissolução e estabilidade'],
'Solução oral':['Verificar solubilidade e compatibilidade dos componentes','Definir ordem de solubilização, veículo e ajuste de pH','Preparar solução e ajustar volume','Filtrar se tecnicamente aplicável e envasar','Avaliar teor, pH, qualidade microbiológica e estabilidade'],
'Comprimido sublingual':['Caracterizar materiais e palatabilidade','Selecionar excipientes e rota compatíveis com desintegração rápida','Mistura e lubrificação','Compressão com monitoramento de resistência mecânica','Avaliar desintegração, uniformidade e estabilidade']}

def get(url,params=None):
    try:
        r=requests.get(url,params=params,timeout=18,headers={'User-Agent':'PharmaForm/0.2 (technical research prototype)'})
        r.raise_for_status(); return r.json(),None
    except Exception as e:return None,str(e)

def normalized(t):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(t).lower()) if not unicodedata.combining(c))

def relevance(text,drug,form,dose):
    s=normalized(text); term=normalized(drug).strip(); tokens=[x for x in re.split(r'\W+',term) if len(x)>3]
    if not tokens or not any(x in s for x in tokens):return 'Não relacionada'
    aliases={'Pó para suspensão oral':['oral suspension','powder for oral suspension','powder for suspension','suspensao oral','dry syrup','reconstitution'], 'Cápsula dura':['capsule','capsula'], 'Comprimido revestido':['film coated','film-coated','coated tablet','comprimido revestido'], 'Comprimido simples':['tablet','comprimido'], 'Solução oral':['oral solution','solucao oral'], 'Comprimido sublingual':['sublingual']}
    relevant=any(x in s for x in aliases.get(form,[]))
    others=[x for f,vals in aliases.items() if f!=form for x in vals if x not in ['tablet','comprimido']]
    wrong=any(x in s for x in others)
    if relevant and not wrong:return 'Candidata: forma compatível'
    if wrong and not relevant:return 'Outra apresentação: não usar como Q2'
    return 'Indeterminada: revisão necessária'

def research(drug,form,dose):
    records=[]; errors=[]
    query=f'{drug} AND (FORMULATION OR EXCIPIENT OR {form})'
    data,err=get('https://www.ebi.ac.uk/europepmc/webservices/rest/search',{'query':query,'format':'json','pageSize':15,'sort':'RELEVANCE'})
    if err:errors.append('Europe PMC: '+err)
    for item in (data or {}).get('resultList',{}).get('result',[]):
        title=item.get('title',''); pmid=item.get('pmid'); doi=item.get('doi')
        url=('https://doi.org/'+doi) if doi else ('https://europepmc.org/article/MED/'+pmid if pmid else 'https://europepmc.org')
        records.append(dict(fonte='Europe PMC',titulo=title,ano=item.get('pubYear',''),url=url,escopo=relevance(title,drug,form,dose),tipo='Artigo / resumo',evidencia='Título e metadados; texto integral não verificado'))
    data,err=get('https://api.crossref.org/works',{'query.bibliographic':f'{drug} {form} formulation','rows':12,'select':'DOI,title,published,URL'})
    if err:errors.append('Crossref: '+err)
    for item in (data or {}).get('message',{}).get('items',[]):
        title=' '.join(item.get('title',[])); yr=(item.get('published',{}).get('date-parts') or [['']])[0][0]
        records.append(dict(fonte='Crossref',titulo=title,ano=yr,url=item.get('URL',''),escopo=relevance(title,drug,form,dose),tipo='Publicação / metadados',evidencia='Metadados; conteúdo integral não verificado'))
    data,err=get('https://api.fda.gov/drug/label.json',{'search':f'openfda.brand_name:"{drug}"','limit':15})
    if err:errors.append('openFDA: '+err)
    for item in (data or {}).get('results',[]):
        desc=' '.join(item.get('description',[])[:2]); dosage=' '.join(item.get('dosage_forms',[])[:2]); ingredients=' '.join(item.get('inactive_ingredient',[])[:2]); blob=' '.join([desc,dosage,ingredients]);
        app=', '.join(item.get('openfda',{}).get('application_number',[])); rid=item.get('id','')
        records.append(dict(fonte='FDA / openFDA',titulo=f'{drug} | {app} | '+(desc[:120] or 'Bula FDA'),ano=item.get('effective_time','')[:4],url='https://api.fda.gov/drug/label.json?search='+quote(f'id:"{rid}"') if rid else 'https://open.fda.gov/apis/drug/label/',escopo=relevance(blob+' '+drug,drug,form,dose),tipo='Rotulagem',evidencia=('Excipientes citados: '+ingredients[:700]) if ingredients else 'Verificar a apresentação no documento integral'))
    seen=set(); unique=[]
    for r in records:
        key=r['url'] or r['titulo']
        if key not in seen:seen.add(key);unique.append(r)
    return unique,errors

def pdf_report(info,rows,steps,notes,refs):
    buf=io.BytesIO(); doc=SimpleDocTemplate(buf,pagesize=A4,leftMargin=40,rightMargin=40,topMargin=40,bottomMargin=40)
    styles=getSampleStyleSheet(); styles.add(ParagraphStyle(name='TinyPF',parent=styles['Normal'],fontSize=8,leading=11,spaceAfter=5)); styles.add(ParagraphStyle(name='TitlePF',parent=styles['Title'],textColor=colors.HexColor('#163a5b'),fontSize=18))
    story=[]
    def p(t,style='Normal'):
        story.append(Paragraph(escape(str(t)).replace('\n','<br/>'),styles[style]));story.append(Spacer(1,5))
    p('PHARMAFORM — PROPOSTA INICIAL','TitlePF');p('ESTUDO DOCUMENTAL NÃO VALIDADO | NÃO É ORDEM DE FABRICAÇÃO','TinyPF')
    p('1. Identificação','Heading2');p(f"{info['produto']} | {info['ifa']} | {info['dose']} | {info['forma']} | {info['apresentacao']} | Mercado: Brasil")
    p('2. Fundamentação e delimitação','Heading2');p('As fontes foram coletadas automaticamente e classificadas preliminarmente por apresentação. A classificação baseada em metadados requer revisão do texto integral. Documentos de outras formas farmacêuticas não comprovam a composição do produto-alvo.')
    p('3. Formulação proposta / quadro de evidências','Heading2')
    tabledata=[[Paragraph(escape(x),styles['TinyPF']) for x in ['Componente','Função','Quantidade','Evidência / justificativa']]]
    for _,r in rows.iterrows():tabledata.append([Paragraph(escape(str(r.get(k,''))),styles['TinyPF']) for k in ['Componente','Função','Quantidade','Justificativa e fonte']])
    if len(tabledata)==1:tabledata.append([Paragraph(x,styles['TinyPF']) for x in ['Pendente','—','Não estabelecida','Não há evidência suficiente']])
    tab=Table(tabledata,colWidths=[105,85,90,230],repeatRows=1,hAlign='LEFT');tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e6eef6')),('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#bbc6d0')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),7)]));story.append(tab);story.append(Spacer(1,10))
    p('4. Justificativa e limitações','Heading2');p(notes or 'Não foram inseridas justificativas adicionais. As quantidades pendentes não devem ser inferidas automaticamente.')
    p('5. Rota de fabricação preliminar','Heading2')
    for i,s in enumerate(steps,1):p(f'{i}. {s}','TinyPF')
    p('6. Controles e avaliação experimental','Heading2');p('Definir atributos críticos e ensaios conforme forma farmacêutica, compêndios aplicáveis, dados de estabilidade, via de administração e estratégia regulatória brasileira. Nenhum parâmetro operacional foi validado neste documento.')
    p('7. Referências pesquisadas','Heading2')
    for i,r in enumerate(refs,1):p(f"[{i}] {r['fonte']} — {r['titulo']} ({r['ano']}). {r['url']} | Escopo: {r['escopo']}",'TinyPF')
    if not refs:p('Nenhuma referência foi coletada ou aprovada para inclusão.','TinyPF')
    p('8. Status','Heading2');p('Rascunho para revisão farmacotécnica. A composição quantitativa e a rota precisam de fundamentação específica, ensaios de bancada e verificação dos requisitos brasileiros vigentes.','TinyPF')
    doc.build(story);return buf.getvalue()

with st.form('novo'):
    a,b=st.columns(2)
    with a:produto=st.text_input('Medicamento de referência',placeholder='Ex.: Tamiflu'); ifa=st.text_input('IFA / sal (se conhecido)',placeholder='Ex.: fosfato de oseltamivir');dose=st.text_input('Concentração',placeholder='Ex.: 6 mg/mL')
    with b:forma=st.selectbox('Forma farmacêutica',FORMS);apresentacao=st.text_input('Apresentação / volume',placeholder='Ex.: 60 mL');mercado=st.text_input('Mercado regulatório',value='Brasil',disabled=True)
    buscar=st.form_submit_button('Pesquisar fontes reais',type='primary',use_container_width=True)
if buscar:
    if not produto.strip() or not dose.strip():st.error('Informe produto e concentração.');st.stop()
    with st.spinner('Consultando Europe PMC, Crossref e FDA...'):
        records,errors=research(produto.strip(),forma,dose.strip())
    st.session_state['info']=dict(produto=produto,ifa=ifa,dose=dose,forma=forma,apresentacao=apresentacao)
    st.session_state['records']=records;st.session_state['errors']=errors
    st.session_state['rows']=pd.DataFrame([{'Componente':'','Função':'','Quantidade':'A definir','Justificativa e fonte':''} for _ in range(3)])
    st.session_state['steps']=PROCESS[forma][:]
if 'info' in st.session_state:
    info=st.session_state['info']; records=st.session_state['records'];errors=st.session_state['errors']
    st.subheader('1 · Evidências encontradas')
    st.caption('A busca é online. O rótulo de escopo é uma triagem automática pelo título/trechos, NÃO confirmação de aplicabilidade. Leia o documento antes de utilizar dados.')
    if errors:st.warning('Algumas fontes não responderam: '+' | '.join(errors))
    st.write(f'{len(records)} registros coletados')
    if records:
        st.dataframe(pd.DataFrame(records)[['fonte','titulo','ano','escopo','url']],use_container_width=True,hide_index=True, column_config={'url':st.column_config.LinkColumn('Documento')})
    else:st.error('Não foram recuperadas fontes. Verifique a conexão ou altere o nome do produto.')
    st.markdown('**Pesquisar também (links de investigação, não resultados validados):**')
    st.markdown(' · '.join([f'[Google Patents](https://patents.google.com/xhr/query?url=q%3D{quote(produto + " " + forma)})',f'[ANVISA — consultas](https://consultas.anvisa.gov.br/)',f'[PubMed](https://pubmed.ncbi.nlm.nih.gov/?term={quote(produto+" formulation "+forma)})']))
    st.subheader('2 · Formulação proposta (edição técnica)')
    st.warning('Nenhuma quantidade é calculada a partir de título/resumo. Insira Q2 somente com fonte, apresentação compatível, unidade e justificativa. A definição automática de Q2 requer motor de inferência ainda não implementado.')
    rows=st.data_editor(st.session_state['rows'],num_rows='dynamic',hide_index=True,use_container_width=True,key='editor_q2')
    st.subheader('3 · Processo preliminar')
    steps_txt=st.text_area('Etapas (uma por linha; revisar conforme evidências)',value='\n'.join(st.session_state['steps']),height=190)
    notes=st.text_area('Racional técnico, limites brasileiros e lacunas verificadas',height=140,placeholder='Citar documento, seção, apresentação e motivo da escolha. Requisitos ANVISA devem ser conferidos na versão vigente.')
    st.subheader('4 · Emitir relatório')
    include=st.multiselect('Fontes que você revisou e deseja citar',options=list(range(len(records))),format_func=lambda i:f"{records[i]['fonte']} | {records[i]['titulo'][:90]}")
    if st.button('Gerar relatório PDF',type='primary'):
        st.session_state['pdf']=pdf_report(info,rows,[x.strip() for x in steps_txt.splitlines() if x.strip()],notes,[records[i] for i in include]);st.success('PDF gerado para revisão.')
    if 'pdf' in st.session_state:
        st.download_button('Baixar relatório PDF',st.session_state['pdf'],file_name='PharmaForm_relatorio_preliminar.pdf',mime='application/pdf')
    st.download_button('Exportar evidências JSON',json.dumps({'produto':info,'evidencias':records,'erros':errors},ensure_ascii=False,indent=2).encode(),file_name='pharmaform_evidencias.json',mime='application/json')
