"""PharmaForm: one input, source-linked proposal, one report."""
from dataclasses import asdict
from hashlib import sha256
import json
import os

import pandas as pd
import streamlit as st

from pharmaform_core import FORMS, VERSION, Target, build_proposal, release_type, validate_rows
from pharmaform_report import payload, pdf_report
from pharmaform_research import REFERENCES, research


@st.cache_data(ttl=3600, show_spinner=False)
def cached_research(serialized, online):
    return research(Target(**json.loads(serialized)), online=online)


def main():
    st.set_page_config(page_title="PharmaForm", page_icon="💊", layout="wide")
    st.title("PharmaForm")
    st.caption(f"Referência e IFA → evidências → proposta inicial → relatório | v{VERSION}")
    st.info("Pesquisa o produto informado e propõe uma formulação inicial com dose, balanço, justificativas e processo. Quantidades documentadas, calculadas e experimentais aparecem identificadas.")
    if st.button("Atualizar fontes na próxima busca"):
        cached_research.clear()
        st.info("Cache limpo. Envie a busca para consultar as fontes novamente.")
    with st.form("research"):
        left, right = st.columns(2)
        with left:
            product = st.text_input("Medicamento de referência", key="product", placeholder="Nome comercial; pode ficar vazio se o IFA estiver informado")
            api = st.text_input("IFA / sal", key="api", placeholder="Nome do princípio ativo e forma química")
            label_url = st.text_input("URL da bula oficial (opcional)", key="label_url", placeholder="Link do fabricante ou autoridade regulatória")
            dose = st.text_input("Concentração", key="dose", placeholder="Dose e unidade; indique se expressa na base ou no sal")
            basis = st.selectbox("A concentração é expressa em", ["Identificar pela bula", "Base / porção ativa", "Material informado (sal/IFA)"], key="dose_basis")
        with right:
            form = st.selectbox("Forma farmacêutica", FORMS, key="form")
            release = st.selectbox("Liberação", ["Identificar pela referência", "Convencional", "Prolongada", "Retardada", "Sublingual"], key="release")
            st.text_input("Mercado regulatório", value="Brasil", disabled=True)
        left, right = st.columns(2)
        mass = left.number_input("Peso unitário pretendido (mg)", min_value=.01, value=200.0, step=10.0, key="mass", help="Para comprimidos e conteúdo de cápsulas. Não é aplicado como massa de um frasco de suspensão.")
        volume = right.number_input("Volume final, quando aplicável (mL)", min_value=.1, value=60.0, step=5.0, key="volume")
        with st.expander("Opções técnicas"):
            l, r = st.columns(2)
            potency = r.number_input("Teor do material na base de pesagem (%)", min_value=.01, max_value=100.0, value=100.0, step=.1,
                                     help="Usar o teor e a base de cálculo do certificado. Água/solventes não são corrigidos duas vezes.")
            mass_basis = l.selectbox("O peso informado corresponde a", ["Produto acabado", "Núcleo / conteúdo"], key="mass_basis")
            gain = r.number_input("Ganho de revestimento sobre o núcleo (%)", min_value=.1, max_value=15.0, value=3.0, step=.1,
                                  help="Usado apenas para comprimido revestido; é uma hipótese de acabamento, não um mecanismo de liberação.")
            route = l.selectbox("Rota de fabricação", ["Selecionar pela evidência", "Compressão direta", "Granulação úmida"])
            dry_mass = r.number_input("Massa de pó por frasco (g; 0 = usar exemplo documental)", min_value=0.0, value=0.0, step=1.0)
            st.caption("A conversão base/sal é resolvida por identidade e propriedades moleculares. Se não houver dados suficientes, informe abaixo as massas molares e a relação estequiométrica.")
            mw_base = l.number_input("Massa molar da base/porção ativa (g/mol)", min_value=0.0, value=0.0)
            mw_material = r.number_input("Massa molar do material (g/mol)", min_value=0.0, value=0.0)
            ratio = l.number_input("Porções ativas por fórmula do sal", min_value=.1, value=1.0, step=.5)
            allow_new = l.checkbox("Permitir excipientes sugeridos com justificativa", value=True,
                                   help="Quando a Q1 não atende uma função/peso, pode sugerir um material documentado. Cada introdução é marcada como sugerida.")
            online = r.checkbox("Consultar fontes online", value=os.environ.get("PHARMAFORM_OFFLINE") != "1")
        submit = st.form_submit_button("Pesquisar e gerar proposta", type="primary", use_container_width=True)
    if submit:
        st.session_state.pop("result", None)
        try:
            t = Target(product, api, dose, form, release, mass, mass_basis, volume, gain, potency, basis, route,
                       mw_base=mw_base, mw_material=mw_material, molar_ratio=ratio, dry_mass_g=dry_mass, allow_new_excipients=allow_new, label_url=label_url)
            t.validate()
            with st.spinner("Identificando o produto, consultando fontes e calculando a proposta..."):
                bundle = cached_research(json.dumps(asdict(t), sort_keys=True), online)
                if bundle.get("resolved_target"):
                    t = Target(**bundle["resolved_target"])
                p = build_proposal(t, bundle["sources"], bundle["examples"])
            st.session_state["result"] = (p, bundle)
        except (ValueError, KeyError) as exc:
            st.error(str(exc))
    if "result" not in st.session_state:
        st.caption("A pesquisa aceita novos nomes de referência/IFA. Exemplo quantitativo é priorizado; na ausência dele, a proposta pode usar funções comprovadas na Q1. Lacunas impeditivas são exibidas.")
        return
    p, bundle = st.session_state["result"]
    st.subheader(p.title)
    st.write(f"**{p.status}**")
    st.caption("Mercado Brasil: registro e comparador nacional ainda precisam ser verificados. As referências estrangeiras são benchmarks técnicos.")
    metrics = st.columns(3)
    metrics[0].metric("Material ativo calculado", f"{p.calculations['weighed_mg']:.4f} mg/{p.unit}" if "weighed_mg" in p.calculations else "A estabelecer")
    if p.calculations.get("final_volume_ml"):
        metrics[1].metric("Volume final", f"{p.calculations['final_volume_ml']:g} mL")
    elif p.mass_total_mg is not None:
        metrics[1].metric("Massa total calculada", f"{p.mass_total_mg:.4f} mg")
    metrics[2].metric("Fontes mantidas", len(bundle["sources"]))
    for warning in p.warnings:
        st.warning(warning)
    current_rows = p.rows
    if p.rows:
        st.subheader("Formulação inicial")
        st.caption(f"Quantidades por {p.unit}. Os níveis experimentais não são quantidades confirmadas da referência comercial.")
        editor_key = "q2_" + sha256((p.created_at + json.dumps(p.target, sort_keys=True)).encode()).hexdigest()[:12]
        edited = st.data_editor(pd.DataFrame(p.rows), hide_index=True, use_container_width=True, num_rows="dynamic", key=editor_key,
            column_config={"mg/unidade": st.column_config.NumberColumn(f"mg/{p.unit}", min_value=0.0, format="%.4f"),
                           "Justificativa": st.column_config.TextColumn(width="large"), "Localizador": st.column_config.TextColumn(width="large")})
        current_rows = json.loads(edited.to_json(orient="records", force_ascii=False, double_precision=12))
        if current_rows != p.rows:
            # Preserve the original evidence classification but make manual quantity changes explicit.
            for i, r in enumerate(current_rows):
                if i >= len(p.rows) or r != p.rows[i]:
                    r["Origem da quantidade"] = "Edição manual — revisão necessária"
        issues = validate_rows(current_rows, p.mass_total_mg, p.calculations.get("weighed_mg"))
        if issues:
            st.error(" | ".join(issues))
        else:
            st.success(f"Dose e balanço verificados: {sum(r['mg/unidade'] for r in current_rows):.6f} mg de materiais listados por {p.unit}.")
        if p.calculations.get("vehicle_qsp_ml"):
            st.warning(f"Veículo compatível q.s.p. {p.calculations['vehicle_qsp_ml']:g} mL finais. Composição ainda parcial enquanto veículo/pH não forem definidos.")
    else:
        issues = []
        st.warning("Q2 não fechada para esta busca. Veja as lacunas concretas abaixo.")
    with st.expander("Justificativas, evidências e lacunas", expanded=not bool(p.rows)):
        if p.benchmark:
            st.markdown("**O que foi localizado sobre a referência**")
            for line in p.benchmark:
                st.write(line)
        if p.q1:
            st.write("**Q1 documental/detectada:** " + "; ".join(p.q1))
        for line in p.rationale:
            st.write(line)
        st.json(p.calculations, expanded=False)
        st.markdown("**Pendências do desenvolvimento**")
        for line in dict.fromkeys(p.gaps):
            st.write("• " + line)
    with st.expander("Rota de fabricação e avaliação experimental", expanded=True):
        for i, step in enumerate(p.steps, 1):
            st.write(f"{i}. {step}")
        for line in p.alternative:
            st.info(line)
        if p.cqas:
            st.dataframe(pd.DataFrame(p.cqas), hide_index=True, use_container_width=True)
    with st.expander("Fontes da pesquisa e cobertura"):
        rows = [{"ID": s["id"], "Fonte": s["source"], "Documento": s["title"], "Escopo": s["scope"], "Acesso": s["status"], "URL": s["url"]} for s in bundle["sources"]]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                     column_config={"URL": st.column_config.LinkColumn("Documento original")})
        st.caption("Acesso automático, leitura do documento e revisão humana são estados diferentes. Fontes curadas têm data explícita.")
        for issue in bundle["issues"]:
            st.warning(issue)
        st.write(f"Resultados descartados por outra identidade: {len(bundle['rejected'])}")
        if bundle["rejected"]:
            st.dataframe(pd.DataFrame(bundle["rejected"])[["title", "scope", "url"]], hide_index=True)
        st.json(bundle["queries"], expanded=False)
    notes = st.text_area("Anotações de revisão (incluídas no relatório)")
    body = payload(p, bundle, current_rows, notes)
    st.subheader("Relatório único")
    left, right = st.columns(2)
    if not issues:
        left.download_button("Baixar relatório PDF", pdf_report(body), file_name="PharmaForm_proposta_experimental.pdf", mime="application/pdf", type="primary", use_container_width=True)
    else:
        left.warning("Corrija a composição antes de exportar a proposta em PDF.")
    right.download_button("Baixar proposta e evidências JSON", json.dumps(body, ensure_ascii=False, indent=2).encode(),
                          file_name="PharmaForm_proposta_e_evidencias.json", mime="application/json", use_container_width=True)


if __name__ == "__main__":
    main()
