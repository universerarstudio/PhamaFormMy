"""General evidence compiler: no formulation branch depends on a drug name.

Priority: compatible quantitative documentary example -> functional hypothesis
from the product's recovered Q1 -> explicit gaps. Curated numeric examples are
data, not a whitelist. Functional study levels are identified as this compiler's
experimental choices; they are never described as published product quantities.
"""
import json
from pathlib import Path
import re

from pharmaform_core import (Proposal, REGULATORY_GAPS, core_masses, dose_calculation,
                            norm, q, release_type, row, search_aliases, validate_rows)

MODELS = json.loads(Path(__file__).with_name("formulation_models.json").read_text(encoding="utf-8"))

# Study centres, not commercial quantities or universal acceptance limits.
# Only ingredients actually recovered for this target can be chosen here.
FUNCTIONS = [
    (r"celulose microcristalina|microcrystalline cellulose|celulose em po|powdered cellulose|lactose|manitol|mannitol|amido pre-gelatinizado|pregelatinized starch|sorbitol|dicalcium", "Diluente", 0),
    (r"crospovidona|crospovidone|croscarmelose|croscarmellose|sodium starch glycolate|glicolato de amido|amido|starch", "Desintegrante", 3.0),
    (r"(?<!cros)povidona|(?<!cros)povidone|copovidone|copovidona", "Aglutinante", 2.0),
    (r"estearato de magnesio|magnesium stearate", "Lubrificante", .75),
    (r"fumarato estearilico|sodium stearyl fumarate", "Lubrificante", 1.0),
    (r"behenato|behenate|stearic acid|acido estearico", "Lubrificante", 2.0),
    (r"silica|dioxido de silicio|silicon dioxide", "Deslizante", .5),
    (r"talco|talc", "Deslizante", 1.0),
    (r"hipromelose|hypromellose|hydroxypropyl methylcellulose", "Polímero matricial", 20.0),
    (r"goma xantana|xanthan", "Agente suspensor", .3),
    (r"benzoato de sodio|sodium benzoate", "Conservante", .05),
    (r"sacarina|saccharin|sucralose", "Edulcorante", .05),
]


def has_identity(text, aliases):
    return any(re.search(r"(?<!\w)" + re.escape(norm(a)) + r"(?!\w)", norm(text)) for a in aliases if len(norm(a)) > 3)


def function_of(name):
    for pattern, role, study_level in FUNCTIONS:
        if re.search(pattern, norm(name)):
            return role, study_level
    return "Função não estabelecida", None


def compatible_sources(sources):
    return [s for s in sources if not s.get("scope", "").startswith(("Outra", "Descartada"))
            and "múltiplas apresentações" not in s.get("scope", "")]


def choose_model(t, examples):
    aliases, release = search_aliases(t), release_type(t)
    candidates = [dict(m) for m in MODELS if t.form in m["forms"] and release == m["release"]
                  and any(has_identity(a, aliases) for a in m["identities"])]
    for e in examples:
        if not e.get("eligible"):
            continue
        candidates.append({"id": e["source_id"] + ":" + e["locator"], "forms": [t.form],
            "release": release, "route": e.get("route", "Rota documental a revisar"),
            "basis": "percent_dry", "source_id": e["source_id"], "locator": e["locator"],
            "original_api_pct": next(pct for name, pct in e["components"] if name == e["api_name"]),
            "api_name": e["api_name"], "diluent": e["diluent"],
            "components": [{"name": name, "function": function_of(name)[0], "pct": pct,
                            "why": "Percentual extraído de coluna completa; o contexto do exemplo requer revisão."}
                           for name, pct in e["components"] if name not in [e["api_name"], e["diluent"]]],
            "sources": [e["source_id"]], "steps": [], "benchmark": []})
    if t.route != "Selecionar pela evidência":
        candidates = [m for m in candidates if m["route"] == t.route]
    # Prefer a compatible real quantitative example; never borrow from another API.
    return candidates[0] if candidates else None


def compile_proposal(t, sources, examples):
    p = Proposal(target=t.__dict__.copy())
    p.target["identified_release"] = release_type(t)
    p.gaps = list(REGULATORY_GAPS)
    p.source_ids = ["ANVISA-REG", "ANVISA-REF", "ANVISA-CONS"]
    if t.identity_conflict:
        p.gaps.append(t.identity_conflict)
        return p
    try:
        p.calculations = dose_calculation(t)
    except ValueError as exc:
        p.gaps.append(str(exc))
        p.q1 = list(dict.fromkeys(x for s in compatible_sources(sources) if s.get("target_q1") for x in s.get("q1", [])))
        return p
    p.source_ids += t.mw_source_ids
    model = choose_model(t, examples)
    if model:
        from_example(t, p, model)
    else:
        from_functions(t, p, sources)
    if p.rows:
        issues = validate_rows(p.rows, p.mass_total_mg, p.calculations["weighed_mg"])
        if issues:
            p.status = "Revisar: balanço ou dose incompatível"
            p.gaps += issues
        elif p.calculations.get("vehicle_pending"):
            p.status = "Hipótese parcial — veículo/pH ainda não quantificados"
        else:
            p.status = "Proposta experimental calculada — requer ensaios"
    p.cqas = quality_plan(t)
    p.source_ids = list(dict.fromkeys(p.source_ids + [sid.strip() for r in p.rows for sid in r["Fontes"].split(",") if sid.strip()]))
    p.gaps += ["Confirmar graus, forma sólida, PSD, umidade e compatibilidade. Quantidade calculada não significa formulação validada.",
               "Não foi aplicado excesso automático de IFA. Qualquer excesso requer dados e justificativa específicos."]
    return p


def add_api(t, p, name=None):
    p.rows.append(row(name or t.api or "IFA identificado na pesquisa", "IFA", p.calculations["weighed_mg"],
                      "Formulação", "Calculada: dose/base-sal/teor", p.calculations["expression"],
                      t.mw_source_ids or [p.calculations["source"]], "Dose informada; forma química e teor especificados",
                      "Alta para a aritmética; identidade/teor devem ser confirmados"))


def add_coating(t, p, core, coating, model=None):
    if not coating:
        return
    p.rows.append(row("Premistura de revestimento imediato (sólidos)", "Filme de acabamento", coating, "Revestimento",
                      "Hipótese: ganho informado", f"Ganho de {t.coating_gain:g}% sobre o núcleo. Qualificar código e composição da premistura; verificar impacto na dissolução.",
                      [model["source_id"]] if model else ["MÉTODO"], "Adição solicitada pelo usuário; não comprova revestimento do referência"))
    p.warnings.append("O filme calculado é uma hipótese de acabamento. Não se assume que o referência seja revestido nem que o filme produza liberação prolongada/entérica.")
    p.steps.append("Aplicar o filme de acabamento com o ganho calculado, após qualificar a premistura e estudar o impacto na dissolução. Solvente removido não integra a massa seca final.")


def from_example(t, p, model):
    powder = t.form == "Pó para suspensão oral"
    if powder:
        total = q(t.dry_mass_g * 1000 if t.dry_mass_g > 0 else p.calculations["ideal_material_mg"] / (model["original_api_pct"] / 100))
        core, coating, final = total, 0, total
        p.unit = "frasco"
        p.calculations.update(final_volume_ml=t.volume_ml, dry_fill_mg=total)
    else:
        core, coating, final = core_masses(t)
        p.calculations.update(core_mg=core, coating_solids_mg=coating, final_mg=final)
    p.mass_total_mg = final
    p.title = f"{t.product or t.api}: proposta a partir de exemplo quantitativo"
    p.source_ids += model.get("sources", [])
    p.benchmark += model.get("benchmark", [])
    p.q1 = model.get("q1", [])
    p.steps = list(model.get("steps") or process_plan(t, model["route"]))
    add_api(t, p, model["api_name"])
    for c in model["components"]:
        p.rows.append(row(c["name"], c["function"], core * c["pct"] / 100, c.get("phase", "Núcleo"),
                          "Hipótese: adaptação de exemplo", c["why"], [model["source_id"]], model["locator"]))
    rest = q(core - sum(r["mg/unidade"] for r in p.rows))
    if rest <= 0:
        p.rows.clear()
        p.gaps.append("A dose/teor excede a massa disponível ao diluente no exemplo. Aumentar massa ou escolher outro desenho, sem reduzir polímeros arbitrariamente.")
        return
    p.rows.append(row(model["diluent"], "Diluente q.s.p.", rest, "Núcleo" if not powder else "Pó seco",
                      "Calculada: balanço de massa", "Completa o balanço após a nova dose e o teor. Novo nível exige confirmar comportamento tecnológico.",
                      [model["source_id"]], model["locator"]))
    p.rationale = [f"Base quantitativa: {model['id']} — {model['locator']}. Rota: {model['route']}.",
                   "Preservam-se os percentuais dos excipientes funcionais do exemplo. O IFA é recalculado pela dose/teor e o diluente é ajustado por diferença. Toda a composição resultante é uma hipótese nova, não Q2 comercial."]
    p.calculations["method"] = "Adaptação de exemplo quantitativo do mesmo IFA"
    p.calculations["model_id"] = model["id"]
    if not powder:
        new_pct = p.calculations["ideal_material_mg"] / core * 100
        p.calculations["original_api_pct"] = model["original_api_pct"]
        p.calculations["new_api_pct"] = new_pct
        p.gaps.append(f"Carga de IFA do exemplo: {model['original_api_pct']:g}% do sal; carga proposta: {new_pct:.4f}%. Confirmar efeito na uniformidade, compactação e liberação.")
    else:
        p.rationale.append(f"A formulação seca é por frasco de {t.volume_ml:g} mL finais. A quantidade de água adicionada deve ser medida por deslocamento, não igualada ao volume final.")
        p.gaps.append("Definir volume de água para reconstituição, exposição aos excipientes por dose, pH e eficácia conservante.")
    add_coating(t, p, core, coating, model)
    p.alternative = [f"Alternativa documental disponível: {m['route']} — {m['source_id']}, {m['locator']}. Requer composição/processo próprios."
                     for m in MODELS if m["id"] != model["id"] and t.form in m["forms"]
                     and m["release"] == release_type(t)
                     and any(has_identity(a, search_aliases(t)) for a in m["identities"])]


def from_functions(t, p, sources):
    compatible = compatible_sources(sources)
    q1_sources = [s for s in compatible if s.get("q1") and s.get("target_q1", False)]
    p.q1 = list(dict.fromkeys(x for s in q1_sources for x in s["q1"]))
    p.benchmark += [s["finding"] for s in compatible if s.get("finding")]
    if not q1_sources:
        p.gaps.append("Q1 específica da apresentação não recuperada. Não se transplantou formulação de outro medicamento. É necessário documento primário compatível ou um exemplo quantitativo do mesmo IFA.")
        return
    release = release_type(t)
    context = " ".join(s.get("architecture", "") for s in q1_sources)
    if release in ["Retardada", "Não determinada"] or re.search(r"osmotic|osmotico|pellet|multiparticul", norm(context)):
        p.gaps.append("A arquitetura de liberação precisa de um exemplo quantitativo e processo próprios (entérico, osmótico ou multiparticulado). A receita convencional/matricial não foi aplicada.")
        return
    if release == "Prolongada" and not re.search(r"matrix|matriz|matric", norm(context)):
        p.gaps.append("O mecanismo matricial não foi comprovado no documento. A presença de hipromelose na Q1 pode corresponder ao filme; não basta para projetar uma matriz LP.")
        return
    source_ids = [s["id"] for s in q1_sources]
    p.source_ids += source_ids + ["BASF", "MÉTODO"]
    p.calculations["method"] = "Inferência funcional sobre a Q1 recuperada para esta apresentação"
    p.title = f"{t.product or t.api}: hipótese funcional de desenvolvimento"
    p.rationale = ["Os componentes elegíveis vêm da Q1 recuperada para este produto/apresentação. As quantidades de excipientes abaixo são escolhas experimentais do motor, não dados publicados do produto.",
                   "A escolha considera função, forma/liberação e fração de IFA. O diluente fecha o balanço; dose, teor e espécie química são calculados separadamente. Não se usa uma fórmula fixa por nome comercial."]
    if t.form in ["Comprimido simples", "Comprimido revestido", "Comprimido sublingual", "Cápsula dura"]:
        functional_solid(t, p, source_ids, release)
    elif t.form in ["Pó para suspensão oral", "Solução oral"]:
        functional_liquid(t, p, source_ids)


def functional_solid(t, p, source_ids, release):
    core, coating, final = core_masses(t)
    choices = {}
    for name in p.q1:
        role, level = function_of(name)
        if role not in choices and level is not None:
            choices[role] = (name, level)
    required = ["Diluente", "Lubrificante"]
    if release == "Prolongada":
        required += ["Polímero matricial"]
    elif t.form != "Cápsula dura":
        required += ["Desintegrante"]
    missing = [x for x in required if x not in choices]
    introduced = set()
    if missing and t.allow_new_excipients:
        additions = {"Diluente": ("Celulose microcristalina", 0, "JRS"),
                     "Desintegrante": ("Crospovidona", 2.5, "BASF"),
                     "Lubrificante": ("Fumarato estearílico de sódio", 1.0, "JRS-PRUV")}
        for role in missing:
            if role in additions:
                name, level, sid = additions[role]
                choices[role] = (name, level)
                introduced.add(role)
                p.source_ids.append(sid)
                p.warnings.append(f"{name} foi sugerido para a função {role.lower()}; não foi confirmado na Q1 da referência selecionada. Justificar compatibilidade e impacto no produto.")
        missing = [x for x in required if x not in choices]
    if missing:
        p.gaps.append("Q1 recuperada não permite selecionar todas as funções necessárias sem introduzir materiais sem base: " + ", ".join(missing))
        return
    if t.form == "Comprimido sublingual" and not any("manitol" in norm(x) or "mannitol" in norm(x) for x in p.q1):
        p.gaps.append("O desenho sublingual exige justificar palatabilidade, dissolução rápida e absorção; não se reutilizou a formulação de deglutição.")
        return
    add_api(t, p)
    roles = ["Lubrificante", "Deslizante"]
    roles += ["Polímero matricial"] if release == "Prolongada" else ["Desintegrante", "Aglutinante"]
    if t.form == "Cápsula dura":
        roles = ["Lubrificante", "Deslizante"]
        p.unit = "conteúdo de cápsula"
        p.warnings.append("O peso calculado é o conteúdo. Cápsula vazia e seu tamanho requerem densidade aparente/compactada e especificação separada.")
    for role in roles:
        if role not in choices:
            continue
        name, level = choices[role]
        p.rows.append(row(name, role, core * level / 100, "Conteúdo" if t.form == "Cápsula dura" else "Núcleo",
                          "Sugerida: função ausente na Q1" if role in introduced else "Hipótese: nível experimental do motor",
                          f"Centro de estudo {level:g}% m/m para a função {role.lower()}; não consta como quantidade confirmada da referência. Variar e medir resposta.",
                          (["JRS-PRUV", "BASF"] if role in introduced else source_ids) + ["MÉTODO", "BASF"], "Q1 e/ou documentação funcional; nível escolhido para estudo"))
    rest = q(core - sum(r["mg/unidade"] for r in p.rows))
    if rest <= 0:
        p.rows.clear()
        p.gaps.append("Carga de IFA e funções selecionadas excedem o núcleo. É necessário outro peso/desenho; não houve quantidade negativa ou redução arbitrária de funções críticas.")
        return
    p.rows.append(row(choices["Diluente"][0], "Diluente q.s.p.", rest, "Conteúdo" if t.form == "Cápsula dura" else "Núcleo",
                      "Sugerida e calculada: balanço" if "Diluente" in introduced else "Calculada: balanço de massa",
                      "Diluente sugerido, ausente na Q1; quantidade por diferença, com compatibilidade/desempenho a demonstrar." if "Diluente" in introduced else "Diluente confirmado na Q1, com quantidade experimental por diferença; estudar fluxo e compactação.",
                      (["JRS"] if "Diluente" in introduced else source_ids) + ["MÉTODO"], "Balanço determinístico"))
    p.mass_total_mg = final
    p.calculations.update(core_mg=core, coating_solids_mg=coating, final_mg=final,
                          api_loading_pct=q(p.calculations["weighed_mg"] / core * 100))
    route = t.route if t.route != "Selecionar pela evidência" else "Compressão direta"
    if t.form == "Cápsula dura":
        route = "Mistura e encapsulação"
    p.rationale.append(f"Rota inicial: {route}. É uma hipótese tecnológica, apoiada nas funções da Q1; fluxo/compactabilidade e compatibilidade devem confirmar a escolha.")
    p.rationale.append(f"Carga de material ativo: {p.calculations['api_loading_pct']:.4f}% da massa de núcleo/conteúdo; isso orienta o estudo de uniformidade e segregação.")
    p.steps = process_plan(t, route)
    add_coating(t, p, core, coating)
    p.alternative = ["Se fluxo, segregação ou compactação impedirem a rota inicial, estudar granulação seca/úmida com ensaios de compatibilidade e perfis comparativos; não tratar as rotas como intercambiáveis."]
    p.gaps.append("Níveis experimentais precisam ser otimizados em desenho de experimentos; não são uma reprodução quantitativa do referência.")


def functional_liquid(t, p, source_ids):
    powder = t.form == "Pó para suspensão oral"
    if powder and t.dry_mass_g <= 0:
        p.gaps.append("Não se recuperou massa total de pó ou exemplo quantitativo. Informe a massa de pó por frasco nas opções técnicas para fechar o q.s.p. sem inventar densidade ou deslocamento.")
        return
    roles = {}
    for name in p.q1:
        role, level = function_of(name)
        if role not in roles and level is not None:
            roles[role] = (name, level)
    if powder and ("Agente suspensor" not in roles or "Diluente" not in roles):
        p.gaps.append("Faltam funções de suspensão/diluição documentadas para esta apresentação.")
        return
    add_api(t, p)
    p.unit = "frasco"
    for role in (["Agente suspensor", "Conservante", "Edulcorante"] if powder else ["Conservante", "Edulcorante"]):
        if role not in roles:
            continue
        name, pct_wv = roles[role]
        p.rows.append(row(name, role, t.volume_ml * pct_wv * 10, "Pó seco" if powder else "Solução",
                          "Hipótese: nível experimental do motor",
                          f"Centro de estudo {pct_wv:g}% m/v no volume final; confirmar pH, compatibilidade, segurança dos excipientes e desempenho.",
                          source_ids + ["MÉTODO"], "Q1 específica + escolha de planejamento, não quantidade comercial"))
    if powder:
        p.mass_total_mg = q(t.dry_mass_g * 1000)
        rest = q(p.mass_total_mg - sum(r["mg/unidade"] for r in p.rows))
        if rest <= 0:
            p.rows.clear()
            p.gaps.append("Massa de pó insuficiente para a dose e os excipientes selecionados.")
            return
        p.rows.append(row(roles["Diluente"][0], "Diluente q.s.p.", rest, "Pó seco", "Calculada: balanço de massa",
                          "Completa a massa de pó informada. Água de reconstituição é definida por deslocamento.", source_ids + ["MÉTODO"]))
        p.calculations["dry_fill_mg"] = p.mass_total_mg
    else:
        # Do not silently design a cosolvent system or claim solubility at an arbitrary dose.
        # The reference oral solution proves a dosage-form precedent, not solubility at this new concentration.
        p.warnings.append("Veículo e ajuste de pH exigem comprovar solubilidade na concentração solicitada. Se houver necessidade de cossolventes/tampões não quantificados, a composição permanece preliminar.")
        p.calculations["vehicle_qsp_ml"] = t.volume_ml
        p.calculations["vehicle_pending"] = True
        p.rationale.append(f"Água purificada/veículo compatível q.s.p. {t.volume_ml:g} mL finais; quantidade adicionada a determinar, sem converter mL em mg por densidade presumida.")
    p.calculations["final_volume_ml"] = t.volume_ml
    p.steps = process_plan(t, "Mistura de pó" if powder else "Dissolução")
    p.gaps += ["Comprovar solubilidade/dispersão, pH, exposição por dose e sistema conservante; quantificar tampão/cossolvente quando necessário.",
               "Definir volume de reconstituição/veículo por medição e avaliar estabilidade após abertura ou reconstituição."]


def process_plan(t, route):
    if t.form == "Pó para suspensão oral":
        return ["Caracterizar IFA/excipientes, PSD, umidade e compatibilidade.", "Preparar pré-mistura do IFA e distribuir componentes de baixa dose por diluição geométrica.",
                "Misturar/envasar a massa calculada; estudar fluxo, recuperação e segregação.", f"Determinar a água necessária para {t.volume_ml:g} mL finais por medição de deslocamento.",
                "Avaliar teor por dose retirada, pH, viscosidade, redispersão, conservação e estabilidade após reconstituição."]
    if t.form == "Solução oral":
        return ["Demonstrar solubilidade/compatibilidade na concentração alvo e selecionar veículo/pH a partir de evidências.",
                "Solubilizar separadamente componentes conforme compatibilidade e incorporá-los sob condições estudadas.",
                f"Ajustar pH e completar experimentalmente a {t.volume_ml:g} mL finais; não usar densidade presumida.",
                "Envasar e avaliar teor, impurezas, pH, conservação e estabilidade."]
    steps = ["Qualificar identidade, forma sólida, teor, PSD, umidade, fluxo e compatibilidade dos materiais.",
             "Preparar pré-mistura do IFA por diluição geométrica; investigar recuperação e uniformidade."]
    if route == "Granulação úmida":
        steps += ["Granular usando aglutinante documentado e líquido compatível; estudar ponto final e exposição.", "Secar e calibrar; estabelecer umidade residual e PSD por dados."]
    steps += ["Incorporar os demais componentes e avaliar mistura/segregação durante transferência.", "Adicionar lubrificante em etapa final controlada."]
    steps += ["Encapsular e verificar massa/uniformidade; selecionar cápsula pela densidade medida."] if t.form == "Cápsula dura" else ["Comprimir e estudar massa, resistência, friabilidade, porosidade e dissolução."]
    steps += ["Qualificar embalagem e programa de estabilidade; comparar desempenho com o comparador definido."]
    return steps


def quality_plan(t):
    attrs = [("Teor e uniformidade", "Confirmar dose, teor e distribuição; avaliar risco de segregação."),
             ("Impurezas e estabilidade", "Avaliar compatibilidade, processo, embalagem e condições aplicáveis ao Brasil.")]
    if t.form in ["Pó para suspensão oral", "Solução oral"]:
        attrs += [("pH e conservação", "Validar compatibilidade e eficácia conservante no produto final."),
                  ("Dose medida e volume final", "Verificar reconstituição/preenchimento, dispositivo e doses retiradas.")]
        if t.form == "Pó para suspensão oral":
            attrs += [("Viscosidade e redispersão", "Relacionar granulometria, sedimentação e uniformidade da dose.")]
    else:
        attrs += [("Perfil de dissolução", "Definir método discriminativo, meios e pontos compatíveis com o mecanismo."),
                  ("Integridade mecânica", "Relacionar compressão, porosidade, resistência/friabilidade e dissolução.")]
        if release_type(t) == "Prolongada":
            attrs += [("Liberação modificada", "Investigar robustez em diferentes pHs e risco de dose dumping; desintegração não substitui dissolução LP.")]
    return [{"Atributo": a, "Estudo necessário": b} for a, b in attrs]
