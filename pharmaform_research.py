"""Live primary sources, identity filtering, structured patent candidates.

Bundled references remain explicitly dated curated references if an endpoint
fails. An accessible document is not described as human-approved or as proof
of Brazilian registration. Network failures and discarded results are retained.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
from io import BytesIO
import re
import time
from urllib.parse import quote, urlencode

from bs4 import BeautifulSoup
from pypdf import PdfReader
import requests

from pharmaform_core import SNAPSHOT_DATE, PROFILES, Target, identify, norm, now, release_type, search_aliases


def reference(sid, title, url, locator, scope, finding=""):
    return {"id": sid, "source": "Patente" if sid.startswith("PAT-") else "Fonte primária",
            "title": title, "url": url, "locator": locator, "scope": scope,
            "status": "Referência curada; atualização online não verificada",
            "curated_on": SNAPSHOT_DATE, "fetched_at": None, "finding": finding,
            "q1": [], "supports_q2": sid.startswith("PAT-"), "human_reviewed": False}


REFERENCES = {
    "EMA-GUA": reference("EMA-GUA", "EMA — Intuniv, informações do produto",
        "https://www.ema.europa.eu/en/documents/product-information/intuniv-epar-product-information_en.pdf",
        "§2, §3, §6.1 e §6.5", "Benchmark europeu: identidade, Q1 e Q2 parcial"),
    "EMA-AR": reference("EMA-AR", "EMA — Intuniv, relatório público de avaliação",
        "https://www.ema.europa.eu/en/documents/assessment-report/intuniv-epar-public-assessment-report_en.pdf",
        "§2.2.3, páginas impressas 10–12", "Processo do referência: matriz e compressão direta"),
    "FDA-GUA": reference("FDA-GUA", "DailyMed/FDA — Intuniv, rotulagem",
        "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=b972af81-3a37-40be-9fe1-3ddf59852528",
        "§11: material, dose em base e massa molar do cloridrato", "Identidade e conversão de dose"),
    "PAT-GUA": reference("PAT-GUA", "WO2007016350A2 — Modified release tablet formulations with enhanced mechanical properties",
        "https://patents.google.com/patent/WO2007016350A2/en",
        "Exemplo 1, Tabela 1, composição 1; PDF p.14, página impressa 13; §32–33",
        "Exemplo experimental; não comprova Q2 comercial",
        "Tabela experimental: 0,76% cloridrato, 13,34% K4M, 33,33% L100-55, 5% ácido fumárico, 13,33% Compritol, 16,91% Ludipress, 17,33% Prosolv. Nova dose implica nova hipótese."),
    "PAT-GUA-WET": reference("PAT-GUA-WET", "US20110217373A1 — Extended release pharmaceutical compositions of guanfacine hydrochloride",
        "https://patents.google.com/patent/US20110217373A1/en", "Exemplo 8, formulação/procedimento A",
        "Alternativa experimental por via úmida; contém HPMCP, Q1 diferente do referência"),
    "BASF": reference("BASF", "BASF — Pharma Solutions Product Overview 2024",
        "https://pharma.basf.com/files/brochures/BASF-Pharma-Solutions-Main_Product_Catalog_web_MarComm-2024-00310.pdf",
        "Overview by Chemistry: Ludipress", "Composição de matéria-prima coprocessada: lactose/povidona/crospovidona"),
    "EMA-OSE": reference("EMA-OSE", "EMA — Tamiflu, informações do produto",
        "https://www.ema.europa.eu/en/documents/product-information/tamiflu-epar-product-information_en.pdf",
        "Tamiflu 6 mg/mL, §2 e §6.1", "Benchmark europeu de pó para suspensão; não usar a formulação de cápsulas"),
    "FDA-OSE": reference("FDA-OSE", "DailyMed/FDA — Tamiflu, rotulagem",
        "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=ee3c9555-60f2-4f82-a760-11983c86e97b",
        "§11: oseltamivir base/fosfato, massas molares 312,4 e 410,4", "Documento com cápsulas e suspensão; conferir apresentação"),
    "PAT-OSE": reference("PAT-OSE", "US20170258749A1 — Oseltamivir Compositions",
        "https://patents.google.com/patent/US20170258749A1/en", "Exemplo 2: duas populações e procedimento",
        "Exemplo experimental de pó para suspensão; não é Q2 comercial"),
    "ANVISA-REG": reference("ANVISA-REG", "ANVISA — Registro de genéricos",
        "https://www.gov.br/anvisa/pt-br/setorregulado/regularizacao/medicamentos/genericos/registro-de-genericos",
        "Marco legal e requisitos de registro", "Orientação geral brasileira; não confirma registro do produto"),
    "ANVISA-REF": reference("ANVISA-REF", "ANVISA — Medicamentos de referência",
        "https://www.gov.br/anvisa/pt-br/acessoainformacao/perguntasfrequentes/medicamentos/medicamentos-de-referencia",
        "Definição e acesso à lista de referência", "Confirmar designação do comparador para o Brasil"),
    "ANVISA-CONS": reference("ANVISA-CONS", "ANVISA — Consulta de registro de medicamentos",
        "https://www.gov.br/anvisa/pt-br/sistemas/consulta-a-registro-de-medicamentos",
        "Consulta oficial do produto, registro e situação", "Registro específico não consultado automaticamente"),
}
REFERENCES["MÉTODO"] = reference("MÉTODO", "PharmaForm 0.3 — método de hipótese funcional",
    "", "Algoritmo deste pacote: pharmaform_engine.py; regras, centros de estudo e balanço",
    "Método de planejamento experimental; não é dado quantitativo do medicamento comercial")
REFERENCES["MÉTODO"]["status"] = "Escolhas experimentais explícitas do compilador"
REFERENCES["JRS"] = reference("JRS", "JRS Pharma — VIVAPUR, celulose microcristalina",
    "https://www.jrspharma.com/pharma_en/products/excipients/vivapur.php", "Graus e aplicações em compressão direta",
    "Função/seleção de grau; não estabelece a quantidade do novo medicamento")
REFERENCES["JRS-PRUV"] = reference("JRS-PRUV", "JRS Pharma — Technical Information PROSOLV/PRUV",
    "https://www.jrspharma.com/pharma-wAssets/docs/technical-information/ti_prosolv_pruv.pdf", "Funções dos excipientes; PRUV = fumarato estearílico de sódio",
    "Documentação de excipientes; quantidade na nova fórmula é experimental")
REFERENCES["CHEM-GUA"] = reference("CHEM-GUA", "PubChem — Guanfacine (CID 3519)",
    "https://pubchem.ncbi.nlm.nih.gov/compound/3519", "Molecular Weight: 246,09 g/mol", "Massa molar da base; complemento à massa do cloridrato na rotulagem")
REFERENCES["CHEM-OSE"] = reference("CHEM-OSE", "PubChem — Oseltamivir (CID 65028)",
    "https://pubchem.ncbi.nlm.nih.gov/compound/65028", "Molecular Weight: 312,4 g/mol", "Massa molar da base; complemento à massa do fosfato na rotulagem")


def get_url(url, params=None, as_json=False):
    """One bounded retry for transient errors, no retries on denied endpoints."""
    for attempt in range(2):
        try:
            r = requests.get(url, params=params, timeout=(4, 10),
                             headers={"User-Agent": "PharmaForm/0.3 pharmaceutical-document-research",
                                      "Accept": "application/json" if as_json else "*/*"})
            if r.status_code in [429, 500, 502, 503, 504] and attempt == 0:
                time.sleep(.4)
                continue
            if r.status_code == 404 and as_json:
                try:
                    data = r.json()
                    if data.get("error", {}).get("code") == "NOT_FOUND":
                        return {"results": []}, None
                except (ValueError, AttributeError):
                    pass
            r.raise_for_status()
            if len(r.content) > 12_000_000:
                return None, "Documento maior que o limite de leitura (12 MB)"
            return (r.json() if as_json else r), None
        except (requests.RequestException, ValueError) as exc:
            if attempt == 0 and isinstance(exc, (requests.Timeout, requests.ConnectionError)):
                continue
            return None, f"{type(exc).__name__}: {str(exc)[:260]}"
    return None, "Falha de conexão"


def identity_matches(text, aliases):
    s = norm(text)
    return any(len(norm(a)) >= 4 and re.search(r"(?<!\w)" + re.escape(norm(a)) + r"(?!\w)", s)
               for a in aliases)


def classify(text, target):
    if not identity_matches(text, search_aliases(target)):
        return "Descartada: outra identidade"
    s, requested = norm(text), release_type(target)
    er = bool(re.search(r"extended[ -]release|prolonged[ -]release|sustained[ -]release|liberacao prolongada|controlled[ -]release", s))
    ir = bool(re.search(r"immediate[ -]release|liberacao imediata|liberacao convencional", s))
    if requested == "Convencional" and er and not ir:
        return "Outra liberação: não usar como Q2"
    if requested == "Prolongada" and ir and not er:
        return "Outra liberação: não usar como Q2"
    suspension = bool(re.search(r"suspension|suspensao|reconstitut", s))
    capsule = bool(re.search(r"capsul", s))
    tablet = bool(re.search(r"tablet|comprimid|caplet", s))
    solution = bool(re.search(r"oral solution|solucao oral", s))
    if target.form == "Pó para suspensão oral" and (tablet or capsule or solution) and not suspension:
        return "Outra forma: não usar como Q2"
    if target.form.startswith("Comprimido") and (suspension or capsule or solution) and not tablet:
        return "Outra forma: não usar como Q2"
    if target.form == "Cápsula dura" and (tablet or suspension or solution) and not capsule:
        return "Outra forma: não usar como Q2"
    if requested == "Prolongada" and er and tablet:
        return "Candidata: matriz/LP; revestimento deve ser conferido"
    if sum([suspension, capsule, tablet, solution]) > 1:
        return "Documento com múltiplas apresentações: revisão necessária"
    return "Candidata documental; dose/forma devem ser conferidas"


def record(source, title, url, scope, text="", locator="Título/metadados"):
    return {"id": "LIVE-" + sha256(url.encode()).hexdigest()[:10], "source": source,
            "title": title, "url": url, "scope": scope, "locator": locator,
            "status": "Metadados recuperados; texto integral não analisado", "fetched_at": now(),
            "curated_on": None, "finding": "", "q1": [], "supports_q2": False,
            "human_reviewed": False, "summary": text[:450]}


EXCIPIENTS = {
    "hypromellose": "Hipromelose", "hydroxypropyl methylcellulose": "Hipromelose",
    "methacrylic acid": "Copolímero de ácido metacrílico (grau a conferir)",
    "lactose": "Lactose", "povidone": "Povidona", "crospovidone": "Crospovidona",
    "microcrystalline cellulose": "Celulose microcristalina", "fumaric acid": "Ácido fumárico",
    "glyceryl behenate": "Behenato de glicerila", "glycerol dibehenate": "Dibehenato de glicerila",
    "silicon dioxide": "Dióxido de silício", "silica": "Sílica", "polysorbate 80": "Polissorbato 80",
    "sodium lauryl sulfate": "Laurilsulfato de sódio", "magnesium stearate": "Estearato de magnésio",
    "croscarmellose": "Croscarmelose", "pregelatinized starch": "Amido pré-gelatinizado",
    "sodium stearyl fumarate": "Fumarato estearílico de sódio", "sorbitol": "Sorbitol",
    "xanthan": "Goma xantana", "sodium benzoate": "Benzoato de sódio", "monosodium citrate": "Citrato monossódico",
    "saccharin sodium": "Sacarina sódica", "mannitol": "Manitol", "talc": "Talco",
    "sodium starch glycolate": "Glicolato de amido sódico", "powdered cellulose": "Celulose em pó",
    "stearic acid": "Ácido esteárico", "polyethylene glycol": "Polietilenoglicol",
    "starch": "Amido (grau a conferir)", "sodium citrate": "Citrato de sódio",
}


def extract_q1(description):
    s = norm(description)
    # Restrict to explicit ingredient context; matches in clinical sections are not Q1.
    anchors = ["inactive ingredients", "tablets also contain", "tablets contain", "capsules contain", "powder for oral suspension contains"]
    starts = [s.find(x) for x in anchors if x in s]
    if not starts:
        return []
    s = s[min(starts):]
    s = re.split(r"12\s+clinical|clinical pharmacology|mechanism of action", s)[0]
    return list(dict.fromkeys(value for key, value in EXCIPIENTS.items()
                              if re.search(r"(?<!\w)" + re.escape(key) + r"(?!\w)", s)))


def fetch_reference(s):
    item = dict(s)
    response, error = get_url(item["url"])
    if error:
        item["status"] = f"Referência curada em {SNAPSHOT_DATE}; acesso online falhou"
        return item, f"{item['id']}: {error}"
    content_type = response.headers.get("Content-Type", "")
    try:
        if "pdf" in content_type or response.content[:4] == b"%PDF":
            reader = PdfReader(BytesIO(response.content))
            indices = [9, 10, 11] if item["id"] == "EMA-AR" else list(range(min(3, len(reader.pages))))
            text = " ".join(reader.pages[i].extract_text() or "" for i in indices if i < len(reader.pages))
        else:
            soup = BeautifulSoup(response.text, "html.parser")
            text = soup.get_text(" ", strip=True)
            if item["id"].startswith("PAT-"):
                desc = soup.find(itemprop="description")
                if desc and len(desc.get_text(" ", strip=True)) > 120:
                    text = desc.get_text(" ", strip=True)
        item["fetched_at"] = now()
        item["document_sha256"] = sha256(response.content).hexdigest()
        # Verification is access/identity only. The curated numeric profile has its own date.
        expected = "guanfacin" if "GUA" in item["id"] or item["id"] == "EMA-AR" else "oseltamivir" if "OSE" in item["id"] else None
        if expected and expected not in norm(text):
            item["status"] = "Documento recebido; identidade/texto não confirmado. Perfil curado não revalidado"
            return item, f"{item['id']}: conteúdo extraído não confirmou a identidade esperada"
        item["status"] = f"Documento acessível; perfil quantitativo curado em {SNAPSHOT_DATE}"
        return item, None
    except Exception as exc:
        item["status"] = f"Documento recebido; extração falhou. Perfil curado em {SNAPSHOT_DATE}"
        return item, f"{item['id']}: {type(exc).__name__} ao extrair documento"


def literature(target):
    aliases = search_aliases(target)
    key = identify(target)
    primary = key if key else (target.api.strip() or target.product.strip())
    terms = list(dict.fromkeys([primary, target.product.strip()]))
    terms = [x for x in terms if x]
    query = "(" + " OR ".join('"' + x.replace('"', '') + '"' for x in terms) + ") AND (formulation OR excipient OR matrix OR manufacturing)"
    rows, issues, log = [], [], [{"source": "Europe PMC", "query": query}]
    data, error = get_url("https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                          {"query": query, "format": "json", "pageSize": 12, "resultType": "core"}, True)
    if error:
        issues.append("Europe PMC: " + error)
    for x in (data or {}).get("resultList", {}).get("result", []):
        title = x.get("title", "")
        abstract = BeautifulSoup(x.get("abstractText", ""), "html.parser").get_text(" ")
        url = "https://doi.org/" + x["doi"] if x.get("doi") else "https://europepmc.org/article/MED/" + str(x.get("id", ""))
        r = record("Europe PMC", title, url, classify(title + " " + abstract, target), abstract, "Título e resumo; não prova Q2")
        rows.append(r)
    cq = f'"{primary}" pharmaceutical formulation'
    if release_type(target) == "Prolongada":
        cq += " extended release matrix"
    log.append({"source": "Crossref", "query": cq})
    data, error = get_url("https://api.crossref.org/works", {"query.bibliographic": cq, "rows": 12, "select": "DOI,title,published,URL"}, True)
    if error:
        issues.append("Crossref: " + error)
    for x in (data or {}).get("message", {}).get("items", []):
        title = " ".join(x.get("title", []))
        rows.append(record("Crossref", title, x.get("URL", "https://doi.org/" + x.get("DOI", "")), classify(title, target)))
    return rows, issues, log, []


def fda_labels(target):
    name = target.product.strip() or target.api.strip()
    queries = [f'openfda.brand_name:"{name.replace(chr(34), "")}"'] if target.product.strip() else []
    key = identify(target)
    generic = key if key else next((a for a in target.identity_terms if a), target.api.strip())
    if generic:
        queries.append(f'openfda.generic_name:"{generic.replace(chr(34), "")}"')
    results, issues, log = [], [], []
    for query in queries:
        log.append({"source": "openFDA", "query": query})
        data, error = get_url("https://api.fda.gov/drug/label.json", {"search": query, "limit": 15}, True)
        if error:
            issues.append("openFDA: " + error)
            continue
        items = (data or {}).get("results", [])
        for item in items:
            substances = item.get("openfda", {}).get("substance_name", [])
            generic_names = item.get("openfda", {}).get("generic_name", [])
            if len(substances) > 1 or any(re.search(r"\band\b|,|;|\bwith\b", s, re.I) for s in generic_names):
                continue  # Associations require a separate mass/dose model.
            desc = " ".join(item.get("description", []))
            dosage = " ".join(item.get("dosage_forms_and_strengths", []) + item.get("dosage_forms", []))
            ingredients = " ".join(item.get("inactive_ingredient", []))
            presentation = " ".join(item.get("spl_product_data_elements", []) + item.get("package_label_principal_display_panel", []))
            brands = ", ".join(item.get("openfda", {}).get("brand_name", []))
            generics = ", ".join(item.get("openfda", {}).get("generic_name", []))
            rid = item.get("id", "")
            url = "https://api.fda.gov/drug/label.json?" + urlencode({"search": f'id:"{rid}"'})
            title = f"{brands or generics} — rotulagem FDA ({item.get('effective_time', '')})"
            r = record("FDA / openFDA", title, url, classify(" ".join([brands, generics, desc, dosage, presentation]), target), locator="description; dosage_forms_and_strengths; inactive_ingredient; spl_product_data_elements")
            r["status"] = "Texto de rotulagem recuperado; apresentação requer revisão"
            r["q1"] = extract_q1(desc + " inactive ingredients " + ingredients) if ingredients else extract_q1(desc)
            r["substance_names"] = substances
            r["generic_names"] = generic_names
            r["architecture"] = desc[:3000]
            primary_form = dosage + " " + desc[:700] + " " + presentation
            if re.search(r"delayed[ -]release|gastro.?resistant|enteric", primary_form, re.I):
                r["detected_release"] = "Retardada"
            elif re.search(r"extended[ -]release|prolonged[ -]release|sustained[ -]release", primary_form, re.I):
                r["detected_release"] = "Prolongada"
            else:
                r["detected_release"] = "Convencional"
            form_patterns = {"Comprimido simples": r"tablet|caplet|comprimid", "Comprimido revestido": r"tablet|caplet|comprimid", "Comprimido sublingual": r"sublingual", "Cápsula dura": r"capsul", "Pó para suspensão oral": r"suspension|suspensao", "Solução oral": r"oral solution|solucao oral"}
            form_found = bool(re.search(form_patterns[target.form], norm(primary_form)))
            r["target_q1"] = bool(r["q1"]) and form_found and not r["scope"].startswith(("Outra", "Descartada")) and "múltiplas" not in r["scope"]
            from pharmaform_core import parse_dose
            dose, _ = parse_dose(target.dose)
            active_section = " ".join(item.get("active_ingredient", []) + item.get("dosage_forms_and_strengths", []))
            r["dose_matches"] = bool(re.search(r"(?<![\d.])" + re.escape(f"{dose:g}") + r"\s*mg\b", active_section, re.I))
            if r["q1"]:
                r["finding"] = f"[{r['id']}] Excipientes detectados na descrição da rotulagem; conferir a apresentação: " + ", ".join(r["q1"])
            results.append(r)
        if results:
            break
    return results, issues, log, []


def numeric_examples(html, source_id, target, scope):
    """Conservative extraction of a *complete* percentage column only.

    Ranges, QS, mg without a unit basis, mixed dosage forms and release controls
    are not auto-completed. Unknown products are limited to conventional tablets.
    """
    if release_type(target) != "Convencional" or target.form not in ["Comprimido simples", "Comprimido revestido"]:
        return []
    if scope.startswith(("Outra", "Descartada")) or "múltiplas" in scope:
        return []
    soup = BeautifulSoup(html, "html.parser")
    aliases = search_aliases(target)
    examples = []
    for table_index, table in enumerate(soup.find_all("table")[:60], 1):
        table_text = table.get_text(" ", strip=True)
        context = table_text + " " + " ".join(x.get_text(" ", strip=True) for x in list(table.previous_siblings)[:4] if hasattr(x, "get_text"))
        if not re.search(r"%\s*(?:w\s*/\s*w|by weight|m\s*/\s*m)|weight\s*%", context, re.I):
            continue
        if not identity_matches(table_text, aliases):
            continue
        grid = [[c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"], recursive=False)] for tr in table.find_all("tr")]
        max_columns = max((len(x) for x in grid), default=0)
        for column in range(1, max_columns):
            ingredients, complete = [], True
            for cells in grid:
                if len(cells) <= column:
                    continue
                name = cells[0]
                if re.fullmatch(r"\d+[.)]?", name) and len(cells) > 2:
                    name = cells[1]
                    if column == 1:
                        continue
                value = cells[column].strip().replace(",", ".")
                if re.fullmatch(r"ingredients?|quantity|example\s*\d*|composition\s*\d*|total|s\.?\s*n\.?|.*%.*|core|coating", name, re.I):
                    continue
                if re.search(r"time|release|dissolution|impurit|pH|medium", name, re.I):
                    complete = False
                    break
                if not value or not name:
                    continue
                if re.fullmatch(r"\d+(?:\.\d+)?", value):
                    ingredients.append((name, float(value)))
                elif re.search(r"\d|q\.?\s*s\.?|—|-", value, re.I):
                    complete = False
                    break
            if not complete or not 4 <= len(ingredients) <= 20 or abs(sum(x[1] for x in ingredients) - 100) > .5:
                continue
            apis = [name for name, _ in ingredients if identity_matches(name, aliases)]
            diluents = [name for name, _ in ingredients if re.search(r"lactose|microcrystalline cellulose|mannitol|dicalcium|starch", name, re.I)]
            if len(apis) != 1 or not diluents:
                continue
            if target.api and not identity_matches(apis[0], [target.api]):
                # For an unknown molecule the actual material must match, not merely its brand.
                continue
            examples.append({"source_id": source_id, "locator": f"Tabela HTML {table_index}, coluna {column + 1} (% m/m); revisar título/contexto",
                             "components": ingredients, "api_name": apis[0], "diluent": diluents[-1], "eligible": True})
            break
    return examples


def patents(target):
    key = identify(target)
    # Known examples are curated above; retrieve actual additional results as candidates.
    term = key or target.api.strip() or target.product.strip()
    query = f'"{term}" pharmaceutical formulation'
    if release_type(target) == "Prolongada":
        query += ' "extended release"'
    rows, issues, examples = [], [], []
    data, error = get_url("https://patents.google.com/xhr/query", {"url": urlencode({"q": query, "num": 5}), "exp": ""}, True)
    log = [{"source": "Google Patents", "query": query}]
    if error:
        return rows, ["Google Patents: " + error], log, examples
    clusters = (data or {}).get("results", {}).get("cluster", [])
    candidates = []
    for cluster in clusters:
        for result in cluster.get("result", []):
            x = result.get("patent", {})
            pub = x.get("publication_number", "")
            if re.fullmatch(r"[A-Z]{2}\d+[A-Z]\d?", pub):
                title = BeautifulSoup(x.get("title", ""), "html.parser").get_text(" ")
                abstract = BeautifulSoup(x.get("snippet", ""), "html.parser").get_text(" ")
                r = record("Google Patents", title, f"https://patents.google.com/patent/{pub}/en", classify(title + " " + abstract, target), abstract)
                candidates.append(r)
    for r in candidates[:3]:
        if not r["scope"].startswith(("Descartada", "Outra")):
            response, error = get_url(r["url"])
            if error:
                issues.append(r["id"] + ": " + error)
            else:
                r["status"] = "Texto e tabelas HTML recuperados; contexto requer revisão"
                r["locator"] = "Descrição e tabelas do documento"
                examples += numeric_examples(response.text, r["id"], target, r["scope"])
                r["supports_q2"] = any(e["source_id"] == r["id"] for e in examples)
        rows.append(r)
    return rows, issues, log, examples


def research(target, online=True):
    target.validate()
    key = identify(target)
    ids = ([*PROFILES[key]["sources"]] if key else ["BASF", "JRS", "JRS-PRUV"]) + ["ANVISA-REG", "ANVISA-REF", "ANVISA-CONS"]
    source_map = {sid: dict(REFERENCES[sid]) for sid in ids}
    result = {"sources": [], "issues": [], "rejected": [], "queries": [], "examples": [],
              "searched_at": now(), "online": online, "aliases": search_aliases(target),
              "brazil_registration": "Não verificado; consulta específica pendente"}
    if not online:
        result["issues"].append("Pesquisa online desativada: usando somente perfis documentais curados, com data explícita. Não é uma busca ao vivo.")
        result["sources"] = list(source_map.values())
        return result
    from pharmaform_resolver import resolve_initial, resolve_from_labels
    identity_sources, identity_issues = resolve_initial(target)
    result["issues"] += identity_issues
    for s in identity_sources:
        source_map[s["id"]] = s
    label_rows, label_issues, label_log, _ = fda_labels(target)
    result["issues"] += label_issues
    result["queries"] += label_log
    label_rows.sort(key=lambda r: (not r.get("dose_matches"), not r.get("target_q1"), r["title"]))
    extra_sources, extra_issues = resolve_from_labels(target, label_rows)
    result["issues"] += extra_issues
    for s in extra_sources + label_rows:
        source_map[s["id"]] = s
    result["resolved_target"] = target.__dict__.copy()
    result["aliases"] = search_aliases(target)
    with ThreadPoolExecutor(max_workers=8) as pool:
        pending = {pool.submit(fetch_reference, s): ("reference", sid) for sid, s in source_map.items() if s.get("curated_on") and sid != "MÉTODO"}
        pending.update({pool.submit(fn, target): ("search", fn.__name__) for fn in [literature, patents]})
        for future in as_completed(pending):
            kind, name = pending[future]
            try:
                value = future.result()
                if kind == "reference":
                    s, issue = value
                    source_map[name] = s
                    if issue:
                        result["issues"].append(issue)
                else:
                    rows, issues, log, examples = value
                    result["issues"] += issues
                    result["queries"] += log
                    result["examples"] += examples
                    for r in rows:
                        if r["scope"].startswith("Descartada"):
                            result["rejected"].append(r)
                        else:
                            source_map.setdefault(r["id"], r)
            except Exception as exc:
                result["issues"].append(f"{name}: {type(exc).__name__}: {str(exc)[:160]}")
    # URL deduplication preserves curated references/locators over search metadata.
    seen = set()
    for s in source_map.values():
        url = s["url"].rstrip("/")
        if url not in seen:
            result["sources"].append(s)
            seen.add(url)
    result["sources"].sort(key=lambda s: (s["id"].startswith("LIVE-"), s["id"]))
    return result
