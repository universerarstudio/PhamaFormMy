"""PDF/JSON from the current reviewed data, never a stale session export."""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, KeepTogether


def payload(proposal, research, rows=None, notes=""):
    p = proposal.to_dict() if hasattr(proposal, "to_dict") else dict(proposal)
    if rows is not None:
        p["rows"] = rows
    from pharmaform_core import validate_rows
    validation = validate_rows(p["rows"], p.get("mass_total_mg"), p["calculations"].get("weighed_mg")) if p["rows"] else []
    if validation:
        p["status"] = "Composição editada com erros de dose/balanço — revisar"
    body = {"proposal": p, "research": research, "review_notes": notes}
    body["validation_errors"] = validation
    body["content_sha256"] = sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return body


def pdf_report(body):
    from pharmaform_research import REFERENCES
    p, research = body["proposal"], body["research"]
    target = p["target"]
    font, bold = "Helvetica", "Helvetica-Bold"
    font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    if font_path.exists():
        if "PF" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("PF", str(font_path)))
            pdfmetrics.registerFont(TTFont("PFB", str(font_path.with_name("DejaVuSans-Bold.ttf"))))
        font, bold = "PF", "PFB"
    styles = getSampleStyleSheet()
    for name in ["Normal", "BodyText", "Heading1", "Heading2", "Title"]:
        styles[name].fontName = bold if name.startswith("Heading") or name == "Title" else font
    styles["Normal"].fontSize = 9
    styles["Normal"].leading = 13
    styles["Heading2"].fontSize = 12
    styles["Heading2"].spaceBefore = 11
    styles["Heading2"].keepWithNext = True
    styles["Title"].fontSize = 19
    styles["Title"].textColor = colors.HexColor("#173b58")
    styles.add(ParagraphStyle("PFSmall", parent=styles["Normal"], fontSize=7.3, leading=10, wordWrap="CJK"))
    styles.add(ParagraphStyle("PFCell", parent=styles["Normal"], fontSize=7.6, leading=10.4, wordWrap="CJK"))
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=36, rightMargin=36,
                            topMargin=39, bottomMargin=38, title="PharmaForm — proposta experimental")
    story = []

    def para(text, style="Normal"):
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), styles[style])

    def add(text, style="Normal"):
        story.extend([para(text, style), Spacer(1, 5)])

    def section(title, lines):
        story.append(para(title, "Heading2"))
        for text in lines:
            add(text)

    add("PHARMAFORM | Proposta experimental", "Title")
    add(f"Versão {p['version']} • {p['created_at']} • {p['status']}", "PFSmall")
    add("Fórmula inicial para avaliação de desenvolvimento. As estimativas estão identificadas. Este relatório não é ordem de fabricação nem prova de equivalência/registro.", "PFSmall")
    section("1. Produto e objetivo", [
        f"Referência: {target['product'] or 'Não informada'} | IFA: {target['api'] or 'Resolver na pesquisa'}",
        f"Dose: {target['dose']} | Forma: {target['form']} | Liberação: {target.get('identified_release') or target.get('detected_release') or target['release']} | Mercado: {target['market']}",
        (f"Volume final: {target['volume_ml']:g} mL; teor do material: {target['potency_pct']:g}%." if target['form'] in ['Pó para suspensão oral','Solução oral'] else f"Peso solicitado: {target['mass_mg']:g} mg ({target['mass_basis']}); teor do material: {target['potency_pct']:g}%."),
    ])
    section("2. Evidências do referência", p.get("benchmark") or ["A evidência disponível não estabeleceu todos os dados do referência."])
    if p.get("q1"):
        add("Q1 documental/detectada: " + "; ".join(p["q1"]) + ". Conferir os componentes no documento integral.")
    calc_names = {"dose_mg":"Concentração (mg/unidade ou mg/mL, conforme entrada)", "base_or_material_total_mg":"Porção ativa/material por unidade ou frasco (mg)",
                  "conversion_factor":"Fator base/material", "ideal_material_mg":"Material a 100% de teor (mg)", "weighed_mg":"Material corrigido pelo teor (mg)",
                  "potency_pct":"Teor informado (%)", "source":"Fonte da conversão", "expression":"Cálculo da pesagem", "overage_pct":"Excesso de IFA (%)",
                  "core_mg":"Massa de núcleo (mg)", "coating_solids_mg":"Sólidos de revestimento (mg)", "final_mg":"Massa final (mg)",
                  "method":"Método de construção da proposta", "model_id":"Exemplo documental utilizado", "original_api_pct":"Carga original de IFA no exemplo (% do material)",
                  "new_api_pct":"Carga proposta de IFA (% do material)", "api_loading_pct":"Carga proposta de material ativo (%)", "dry_fill_mg":"Massa de pó por frasco (mg)",
                  "final_volume_ml":"Volume final (mL)", "vehicle_qsp_ml":"Veículo q.s.p. (mL finais)"}
    section("3. Cálculos e premissas", [calc_names[k] + ": " + (f"{v:.6f}".rstrip('0').rstrip('.') if isinstance(v,float) else str(v)) for k,v in p["calculations"].items() if k in calc_names])
    if p["rows"]:
        cols = ["Componente", "mg", "Função", "Origem da quantidade", "Fontes"]
        grid = [[para(c, "PFCell") for c in cols]]
        for r in p["rows"]:
            grid.append([para(r["Componente"], "PFCell"), para(f"{r['mg/unidade']:.4f}", "PFCell"),
                         para(r["Função"], "PFCell"), para(r["Origem da quantidade"], "PFCell"), para(r["Fontes"], "PFCell")])
        table = Table(grid, colWidths=[141, 54, 102, 128, 98], repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7f0f7")),
                                   ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#bfcfd9")),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                                   ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        story.extend([para(f"4. Formulação proposta - por {p['unit']}", "Heading2"), table, Spacer(1, 8)])
        add(f"Soma dos materiais listados: {sum(r['mg/unidade'] for r in p['rows']):.6f} mg/{p['unit']}.")
        if p["calculations"].get("vehicle_qsp_ml"):
            add(f"Veículo compatível q.s.p. {p['calculations']['vehicle_qsp_ml']:g} mL finais. A quantidade adicionada e eventual tampão/cossolvente ainda precisam ser estabelecidos.")
        for r in p["rows"]:
            add(f"{r['Componente']} — {r['Justificativa']} Fonte/localizador: {r['Fontes']} | {r.get('Localizador', '')}. Confiança: {r.get('Confiança', '')}.", "PFSmall")
    else:
        story.append(para("4. Formulação proposta", "Heading2"))
        add("Composição quantitativa não fechada. As lacunas impeditivas estão listadas; nenhuma receita de outro produto foi aplicada.")
    section("5. Racional da proposta", p["rationale"])
    section("6. Processo preliminar", [f"{i}. {step}" for i, step in enumerate(p["steps"], 1)])
    if p["alternative"]:
        section("Alternativas de processo", p["alternative"])
    section("7. Atributos e avaliação experimental", [" | ".join(str(v) for v in r.values()) for r in p["cqas"]])
    section("8. Lacunas e verificação brasileira", list(dict.fromkeys(p["warnings"] + p["gaps"])))
    if body.get("review_notes"):
        section("Anotações da revisão", [body["review_notes"]])
    source_map = {**REFERENCES, **{s["id"]: s for s in research.get("sources", [])}}
    used = list(dict.fromkeys(p["source_ids"] + [sid.strip() for r in p["rows"] for sid in r["Fontes"].split(",")]))
    story.append(para("9. Fontes utilizadas e estado de acesso", "Heading2"))
    for sid in used:
        s = source_map.get(sid)
        if s:
            add(f"[{sid}] {s['title']}. {s['url']} | {s.get('locator', '')} | {s.get('status', '')}. Perfil curado: {s.get('curated_on') or 'não aplicável'}. Acesso: {s.get('fetched_at') or 'não revalidado online'}. Revisão humana: {s.get('human_reviewed', False)}.", "PFSmall")
        else:
            add(f"[{sid}] Entrada/cálculo do projeto ou fonte informada manualmente; verificar rastreabilidade.", "PFSmall")
    section("10. Cobertura da pesquisa", [
        f"Fontes mantidas: {len(research.get('sources', []))}; descartadas por identidade: {len(research.get('rejected', []))}. Pesquisa online: {research.get('online', False)}.",
        *research.get("issues", []),
        "Referências citadas não significam revisão humana automática nem aplicabilidade regulatória confirmada.",
        "Identificador de conteúdo: " + body["content_sha256"],
    ])

    def footer(canvas, document):
        canvas.setFont(font, 7)
        canvas.setFillColor(colors.HexColor("#607383"))
        canvas.drawString(36, 20, "PharmaForm • estudo experimental sujeito a revisão")
        canvas.drawRightString(A4[0] - 36, 20, str(document.page))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()
