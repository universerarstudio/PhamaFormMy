"""Evidence-linked formulation hypotheses. No commercial Q2 is reconstructed.

Quantitative profiles are transcriptions of identified patent examples, adapted
by deterministic mass balance. Other products require an eligible documented
example; a list of excipients alone never becomes a quantitative formulation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
import math
import re
import unicodedata
from zoneinfo import ZoneInfo

VERSION = "0.3.0"
SNAPSHOT_DATE = "2026-11-04"
FORMS = ["Comprimido revestido", "Comprimido simples", "Cápsula dura",
         "Pó para suspensão oral", "Solução oral", "Comprimido sublingual"]


def norm(value):
    s = unicodedata.normalize("NFKD", str(value).lower()).replace("µ", "u").replace("μ", "u")
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).split())


def now():
    return datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="seconds")


def q(value):
    return float(Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


@dataclass
class Target:
    product: str
    api: str
    dose: str
    form: str = "Comprimido revestido"
    release: str = "Identificar pela referência"
    mass_mg: float = 200.0
    mass_basis: str = "Produto acabado"
    volume_ml: float = 60.0
    coating_gain: float = 3.0
    potency_pct: float = 100.0
    dose_basis: str = "Base / porção ativa"
    route: str = "Selecionar pela evidência"
    market: str = "Brasil"
    mw_base: float = 0.0
    mw_material: float = 0.0
    molar_ratio: float = 1.0
    dry_mass_g: float = 0.0
    identity_terms: list = field(default_factory=list)
    detected_release: str = ""
    mw_source_ids: list = field(default_factory=list)
    identity_conflict: str = ""
    allow_new_excipients: bool = True

    def validate(self):
        if not self.product.strip() and not self.api.strip():
            raise ValueError("Informe o medicamento ou o IFA.")
        if self.form not in FORMS:
            raise ValueError("Forma farmacêutica não reconhecida.")
        parse_dose(self.dose)
        for name in ["mass_mg", "volume_ml", "potency_pct", "molar_ratio"]:
            v = getattr(self, name)
            if not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
                raise ValueError(f"Valor inválido em {name}.")
        if self.potency_pct > 100 or not math.isfinite(self.coating_gain) or not 0 <= self.coating_gain <= 15:
            raise ValueError("Teor deve estar entre 0 e 100%; ganho de revestimento entre 0 e 15%.")
        if self.form != "Comprimido revestido" and self.coating_gain != 0:
            self.coating_gain = 0.0
        if self.form == "Comprimido revestido" and self.coating_gain <= 0:
            raise ValueError("Para comprimido revestido, informe ganho de massa maior que zero.")
        _, per_ml = parse_dose(self.dose)
        if per_ml != (self.form in ["Pó para suspensão oral", "Solução oral"]):
            raise ValueError("Use mg/mL para líquidos/pós para suspensão e mg por unidade para sólidos unitários.")
        identify(self)  # detects brand/API mismatch before research


def parse_dose(text):
    s = norm(text).replace(",", ".")
    if re.search(r"-\s*\d", s):
        raise ValueError("A concentração não pode ser negativa.")
    matches = list(re.finditer(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(mcg|ug|mg|g)(?!\w)", s))
    if len(matches) != 1:
        raise ValueError("Informe uma concentração de massa única: por exemplo 4 mg ou 6 mg/mL. Associações e UI exigem modelo próprio.")
    m = matches[0]
    value = float(m.group(1)) * {"mcg": .001, "ug": .001, "mg": 1, "g": 1000}[m.group(2)]
    tail = s[m.end():].strip()
    per_ml = bool(re.match(r"^(?:/|por\s+)\s*(?:1\s*)?ml\b", tail))
    if re.match(r"^(?:/|por\s+)", tail) and not per_ml:
        if not re.match(r"^(?:/|por\s+)\s*(?:unidade|comprimido|capsula)\b", tail):
            raise ValueError("Denominador não suportado. Converta a concentração para mg/mL ou mg/unidade.")
    if value <= 0 or not math.isfinite(value):
        raise ValueError("A concentração deve ser maior que zero.")
    return value, per_ml


PROFILES = {
    "guanfacine": {
        "brands": ["intuniv"], "aliases": ["guanfacine", "guanfacina"],
        "material": "Cloridrato de guanfacina", "base": "Guanfacina",
        "mw_base": 246.09, "mw_material": 282.55, "release": "Prolongada",
        "sources": ["EMA-GUA", "EMA-AR", "FDA-GUA", "CHEM-GUA", "PAT-GUA", "PAT-GUA-WET", "BASF"],
    },
    "oseltamivir": {
        "brands": ["tamiflu"], "aliases": ["oseltamivir"],
        "material": "Fosfato de oseltamivir", "base": "Oseltamivir",
        "mw_base": 312.4, "mw_material": 410.4, "release": "Convencional",
        "sources": ["EMA-OSE", "FDA-OSE", "CHEM-OSE", "PAT-OSE"],
    },
}


def identify(target):
    product, api = norm(target.product), norm(target.api)
    for key, p in PROFILES.items():
        branded = any(re.search(r"\b" + re.escape(b) + r"\b", product) for b in p["brands"])
        matched = any(re.search(r"\b" + re.escape(a) + r"\b", api or product) for a in p["aliases"])
        if branded and api and not matched:
            raise ValueError(f"O IFA informado não corresponde a {target.product}. Corrija a identidade antes de calcular.")
        if branded or matched:
            # No silent substitution of another salt/free base by the profile material.
            if api:
                if any(x in api for x in ["hydrate", "hidrato", "hidratad", "solvate", "solvato"]):
                    raise ValueError("O perfil curado não estabelece uma forma hidratada/solvatada. Confirme a espécie química antes da conversão.")
                foreign_salts = ["sulfato", "sulfate", "fosfato", "phosphate", "cloridrato", "hydrochloride", "hcl", "maleato", "citrato", "bromidrato"]
                expected = ["cloridrato", "hydrochloride", "hcl"] if key == "guanfacine" else ["fosfato", "phosphate"]
                if any(re.search(r"\b" + x + r"\b", api) for x in foreign_salts if x not in expected):
                    raise ValueError(f"O perfil documentado usa {p['material']}; o sal informado é diferente.")
                if "base livre" in api or "free base" in api:
                    raise ValueError(f"Este perfil usa {p['material']}. Não é possível substituir por base livre sem novo desenvolvimento.")
            return key
    return None


def search_aliases(target):
    key = identify(target)
    values = [target.product.strip(), target.api.strip(), *target.identity_terms]
    if key:
        p = PROFILES[key]
        values += p["aliases"] + p["brands"]
        values += ["guanfacine hydrochloride"] if key == "guanfacine" else ["oseltamivir phosphate"]
    # Translate common salts; do not erase the actual API identity.
    translations = {"cloridrato de ": "", "fosfato de ": "", "hydrochloride": "", "phosphate": ""}
    if not key:
        for value in values[:]:
            translated = norm(value)
            for old, new in translations.items():
                translated = translated.replace(old, new)
            if len(translated.strip()) >= 4:
                values.append(translated.strip())
    return list(dict.fromkeys(x for x in values if x))


def release_type(target):
    if target.form == "Comprimido sublingual":
        return "Sublingual"
    if target.release != "Identificar pela referência":
        return target.release
    if target.detected_release:
        return target.detected_release
    key = identify(target)
    return PROFILES[key]["release"] if key else "Não determinada"


def dose_calculation(target):
    dose, per_ml = parse_dose(target.dose)
    amount = dose * (target.volume_ml if per_ml else 1)
    key = identify(target)
    if target.dose_basis == "Material informado (sal/IFA)":
        factor = 1.0
        source = "Entrada: dose expressa no próprio material"
    elif key:
        p = PROFILES[key]
        factor = p["mw_material"] / p["mw_base"]
        source = "FDA-GUA, CHEM-GUA" if key == "guanfacine" else "FDA-OSE, CHEM-OSE"
    elif target.mw_base > 0 and target.mw_material > 0:
        factor = target.mw_material / (target.mw_base * target.molar_ratio)
        source = ", ".join(target.mw_source_ids) or "Massas molares e estequiometria informadas pelo usuário; confirmar fonte/forma sólida"
    else:
        raise ValueError("Conversão base/sal não estabelecida. Informe as massas molares e a estequiometria ou expresse a dose no material informado.")
    ideal = amount * factor
    weighed = ideal / (target.potency_pct / 100)
    return {"dose_mg": dose, "per_ml": per_ml, "base_or_material_total_mg": q(amount),
            "conversion_factor": factor, "ideal_material_mg": q(ideal), "weighed_mg": q(weighed),
            "potency_pct": target.potency_pct, "source": source,
            "expression": f"{amount:g} × {factor:.8f} ÷ ({target.potency_pct:g}/100) = {weighed:.6f} mg de material",
            "overage_pct": 0.0}


def core_masses(target):
    gain = target.coating_gain / 100 if target.form == "Comprimido revestido" else 0
    core = target.mass_mg / (1 + gain) if target.mass_basis == "Produto acabado" else target.mass_mg
    return q(core), q(core * gain), q(core * (1 + gain))


def row(name, function, amount, phase, nature, why, sources, locator="", confidence="Experimental"):
    return {"Componente": name, "Função": function, "mg/unidade": q(amount),
            "Fase": phase, "Origem da quantidade": nature, "Justificativa": why,
            "Fontes": ", ".join(sources), "Localizador": locator, "Confiança": confidence}


@dataclass
class Proposal:
    target: dict
    title: str = "Levantamento documental"
    status: str = "Evidência insuficiente para fechar Q2"
    rows: list = field(default_factory=list)
    benchmark: list = field(default_factory=list)
    calculations: dict = field(default_factory=dict)
    rationale: list = field(default_factory=list)
    steps: list = field(default_factory=list)
    alternative: list = field(default_factory=list)
    cqas: list = field(default_factory=list)
    gaps: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    source_ids: list = field(default_factory=list)
    created_at: str = field(default_factory=now)
    mass_total_mg: float | None = None
    unit: str = "comprimido"
    q1: list = field(default_factory=list)
    version: str = VERSION

    def to_dict(self):
        return asdict(self)


REGULATORY_GAPS = [
    "Brasil: registro, detentor e comparador nacional ainda não verificados. Aprovação FDA/EMA não comprova registro ANVISA nem status de referência no Brasil.",
    "Definir categoria regulatória, estratégia de equivalência/bioequivalência e estabilidade no enquadramento brasileiro vigente. As páginas oficiais consultadas são orientação, não certificação de conformidade.",
]


def build_proposal(target, sources=None, examples=None):
    from pharmaform_engine import compile_proposal
    target.validate()
    return compile_proposal(target, sources or [], examples or [])


def validate_rows(rows, expected_mass=None, expected_api=None):
    issues, total, api_sum, api_count = [], 0.0, 0.0, 0
    if not rows:
        return ["Não há composição quantitativa."]
    for index, r in enumerate(rows, 1):
        if not str(r.get("Componente", "")).strip():
            issues.append(f"Linha {index}: componente vazio.")
        v = r.get("mg/unidade")
        if not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            issues.append(f"Linha {index}: quantidade deve ser positiva e finita.")
            continue
        total += v
        if r.get("Função") == "IFA":
            api_sum += v
            api_count += 1
        if not str(r.get("Fontes", "")).strip() or not str(r.get("Justificativa", "")).strip():
            issues.append(f"Linha {index}: informe fonte e justificativa.")
    if api_count != 1:
        issues.append("Esta versão exige uma única linha de IFA com a função 'IFA'.")
    if expected_mass is not None and abs(total - expected_mass) > .0001:
        issues.append(f"Balanço de massa: soma {total:.6f} mg; alvo {expected_mass:.6f} mg. Ajuste o diluente q.s.p.")
    if expected_api is not None and abs(api_sum - expected_api) > .0001:
        issues.append("A massa de IFA difere da conversão dose/base-sal/teor. Atualize a entrada para mudar a dose.")
    return issues
