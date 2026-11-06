"""Product/API resolution from primary label metadata and PubChem properties."""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from urllib.parse import quote
from pharmaform_core import identify, norm, now


def properties(name):
    return _properties(norm(name))


@lru_cache(maxsize=256)
def _properties(name):
    from pharmaform_research import get_url, record
    url = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/" + quote(name, safe="") + "/property/MolecularFormula,MolecularWeight,Title/JSON"
    data, error = get_url(url, as_json=True)
    if error:
        return None, None
    items = (data or {}).get("PropertyTable", {}).get("Properties", [])
    if not items:
        return None, None
    x = items[0]
    sid = "PUBCHEM-" + str(x["CID"])
    s = record("PubChem / NCBI", x.get("Title", name) + " — propriedades moleculares",
               f"https://pubchem.ncbi.nlm.nih.gov/compound/{x['CID']}", "Identidade química; não comprova formulação")
    s.update(id=sid, status="Propriedades estruturadas recuperadas", locator="MolecularWeight; MolecularFormula; CID",
             molecular_weight=float(x["MolecularWeight"]), molecular_formula=x.get("MolecularFormula", ""))
    return x, s


def material_to_base(name):
    s = norm(name)
    translations = {"cloridrato de ": "", "fosfato de ": "", "sulfato de ": "", "bromidrato de ": ""}
    for old, new in translations.items():
        s = s.replace(old, new)
    import re
    s = re.sub(r"\b(hydrochloride|hydrobromide|phosphate|sulfate|sodium|potassium|maleate|fumarate|citrate|tartrate|mesylate|besylate)\b", "", s)
    return " ".join(s.split())


def resolve_initial(target):
    if identify(target):
        return [], []
    query = target.api.strip() or target.product.strip()
    x, s = properties(query)
    if not x:
        return [], ["PubChem: identidade inicial não resolvida; a pesquisa documental continua."]
    title = x.get("Title", query)
    target.identity_terms = list(dict.fromkeys(target.identity_terms + [title, material_to_base(title)]))
    if target.api and material_to_base(title) == norm(title) and target.mw_material <= 0 and target.mw_base <= 0:
        # The input itself resolved to an unsalted compound: no salt factor is needed.
        target.mw_material = target.mw_base = float(x["MolecularWeight"])
        target.mw_source_ids = [s["id"]]
    if target.api and target.product:
        branded, brand_source = properties(target.product)
        if branded and branded["CID"] != x["CID"] and material_to_base(branded.get("Title", "")) != material_to_base(title):
            target.identity_conflict = "Referência e IFA resolveram para compostos diferentes no PubChem. Verifique nome, sal e apresentação."
            return [z for z in [s, brand_source] if z], [target.identity_conflict]
    return [s], []


def resolve_from_labels(target, rows):
    if identify(target):
        return [], []
    candidates = [r for r in rows if r.get("target_q1")]
    if not candidates:
        return [], ["Não foi recuperada Q1 de rotulagem compatível para resolver a apresentação."]
    chosen = candidates[0]
    # Do not union ingredient lists from different reference variants.
    for other in candidates[1:]:
        other["target_q1"] = False
    names = chosen.get("substance_names") or chosen.get("generic_names") or []
    if not names:
        return [], ["Rotulagem sem identidade estruturada do IFA; revisar o documento."]
    material = names[0]
    base = material_to_base(material)
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [pool.submit(properties, n) for n in [material, base, target.api.strip() or material]]
        (mat, sm), (bas, sb), (given, sg) = [f.result() for f in jobs]
    sources = list({s["id"]: s for s in [sm, sb, sg] if s}.values())
    if not mat and given and norm(given.get("Title", "")) == norm(material) and material_to_base(material) == norm(material):
        mat, bas, sm, sb = given, given, sg, sg
    if given and mat:
        # Synonyms are resolved by CID; different counterion-free titles are a conflict.
        if given["CID"] != mat["CID"] and material_to_base(given.get("Title", "")) != material_to_base(mat.get("Title", "")):
            chosen["target_q1"] = False
            return sources, ["Conflito de identidade: o IFA informado e a substância da referência têm identidades PubChem diferentes. Q2 não foi gerada com essa Q1."]
        if given["CID"] != mat["CID"] and material_to_base(given.get("Title", "")) != norm(given.get("Title", "")):
            chosen["target_q1"] = False
            target.identity_conflict = "O sal informado difere do material da referência. Não houve substituição automática de contraíon/forma sólida."
            return sources, [target.identity_conflict]
    elif target.api and not any(material_to_base(a) in [material_to_base(target.api), material_to_base(given.get("Title", "")) if given else ""] for a in names + target.identity_terms):
        chosen["target_q1"] = False
        return sources, ["Não foi possível verificar a correspondência entre IFA e referência. Q1 fica apenas como documento candidato."]
    if not target.api:
        target.api = material
    target.identity_terms = list(dict.fromkeys(target.identity_terms + names + [base]))
    if target.release == "Identificar pela referência":
        target.detected_release = chosen.get("detected_release", "")
    # Multivalent/ambiguous stoichiometries must be supplied explicitly rather than guessed.
    ambiguous = any(x in norm(material) for x in ["sulfate", "hemifumarate", "sesqui", "hemitartrate", "citrate", "tartrate"])
    if mat and bas and target.mw_material <= 0 and target.mw_base <= 0 and not ambiguous:
        target.mw_material = float(mat["MolecularWeight"])
        target.mw_base = float(bas["MolecularWeight"])
        target.mw_source_ids = list(dict.fromkeys([sm["id"], sb["id"]]))
    notes = []
    if ambiguous:
        notes.append("Estequiometria do sal potencialmente ambígua; informar massas molares/relação molar ou dose no próprio material.")
    return sources, notes
