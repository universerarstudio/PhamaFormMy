# PharmaForm 0.3.1 — ensaio de estresse

Data: 06/11/2026 (São Paulo). Escopo: comportamento de software, rastreabilidade e aritmética. Não é validação farmacêutica.

## Amostras e resultados

| Rodada | Unidade de contagem | Resultado |
|---|---|---|
| Amostra geral | 1.000 pares distintos marca/IFA, selecionados em 1.500 rotulagens orais openFDA | 205 hipóteses calculadas; 109 bloqueios documentais; 686 associações/formas não suportadas |
| Amostra de sólidos unitários | 1.000 produtos distintos por marca + IFA + fabricante, com 490 pares marca/IFA; coletados em 3.500 rotulagens de prescrição oral | 756 hipóteses calculadas; 244 bloqueios documentais/tecnológicos; nenhuma exceção ou balanço inválido nos controles executados |
| Regressões unitárias/interface | 214 testes | 214 passaram |
| Controles negativos na amostra de sólidos | 2.000 verificações: dose inexistente e IFA conflitante | nenhuma composição aceita nesses controles |

As duas amostras podem se sobrepor. Não somar como 2.000 moléculas diferentes. Os 1.000 sólidos não são 1.000 IFAs: fabricantes diferentes contam como produtos distintos.

## Método

Rotulagens reais foram obtidas em lotes pela API pública openFDA. Cada registro retido tem id, marca, IFA, fabricante e URL. O parser de produção, motor de composição e gerador de PDF foram executados localmente sobre esses documentos. Foram gerados 756 PDFs em memória na amostra de sólidos. Não houve 1.000 navegações individuais no Streamlit ou 1.000 buscas completas por patentes/PubChem.

O teste de composição usa dose explicitamente no material e massa de enchimento hipotética, escolhida para testar os cálculos. O número extraído da rotulagem não foi tratado como comprovação da base clínica da dose. A rodada não certifica identidade farmacêutica de cada produto, valores comerciais de Q2 ou dose clínica. Bloqueios são contados separadamente, não classificados como formulação aprovada.

## Comparação com a versão anterior

No mesmo corpus de 1.000 sólidos, 930 controles de dose propositalmente inexistente falharam na versão anterior: o documento ainda era elegível para Q1. Isso é falha de seleção de evidência, não 930 crashes em uso normal. A revisão exige coincidência da dose e rejeitou todos esses controles.

## Falhas corrigidas

- Remoção de botões e preenchimentos de medicamentos de exemplo da interface.
- Normalização de vocabulário químico português/inglês, sem tabela de receitas por marca.
- Conversão base/sal independente de recuperar Q1; fórmula molecular verificada para HCl 1:1.
- Título comercial retornado pelo PubChem não é usado para declarar composto livre de sal.
- Sais de cálcio/magnésio e hidratos não assumem fator 1.
- Confirmação explícita da base da dose quando a bula não resolve; opção visível no formulário.
- Dose não encontrada impede usar a Q1; resultados de buscas repetidas são deduplicados.
- Troca de fabricante é identificada como benchmark.
- Leitura da composição por concentração em bula brasileira, incluindo equivalência material/base.
- Separação entre excipientes do enchimento e da cápsula; amido reconhecido como diluente do conteúdo.
- Valores negativos/não finitos e massas molares incompletas são rejeitados.
- Botão para limpar cache de pesquisa e repetir consultas após falha de rede.

## Casos online de desenvolvimento

Foram executados 22 cenários completos, incluindo Atentah em três entradas, Intuniv, Tylenol, Advil, Glucophage, Zoloft, Prozac, Ritalin, Concerta, Prilosec, Nexium, Seroquel, Lipitor, Claritin, Zyrtec, Wellbutrin XL, Tamiflu, produto inexistente e conflitos de IFA. Estes cenários ocorreram durante a correção: os resultados originais incluem falhas que motivaram alterações e não devem ser apresentados como resultados finais aprovados.

Reverificações após as correções usam documentos já recuperados e novas consultas de identidade/bula. Atentah sem IFA voltou a recuperar 68,567 mg de cloridrato para 60 mg de base da bula Apsen; Prozac deixou de usar fator 1 (22,358 mg calculados para 20 mg de base com as massas molares recuperadas); Glucophage com dose expressa no material calculou 500 mg; Nexium e Lipitor permaneceram bloqueados por espécie química/estequiometria, e Zyrtec por conversão não estabelecida. Esses são casos de teste, não instruções de fabricação.

## Limitações remanescentes

- A cobertura de bulas nacionais é parcial: adaptador inicial Apsen e URLs de domínios habilitados, sem raspagem universal da ANVISA.
- Nomes comerciais novos podem exigir IFA e/ou link oficial. Ortografia aproximada não é automaticamente aceita como identidade.
- Sais multivalentes, hidratos, associações e tecnologias osmóticas/entéricas precisam de evidência e modelos próprios.
- 244 de 1.000 sólidos não geraram Q2. Não é cobertura universal.
- Quantidades de excipientes geradas por funções são hipóteses experimentais, mesmo quando dose e balanço fecham.
- Ocorreram timeouts e respostas 403/503 nas fontes. Não foram escondidos nem contornados.
- Não houve revisão científica manual de 1.000 bulas, ensaio experimental, bioequivalência ou certificação ANVISA.

## Reprodução

Extraia `test_suite.zip` na raiz. Execute `python -m pytest -q tests`. O arquivo `audit_1000/run.py` aceita o JSON de entrada e a pasta de saída como argumentos; defina PHARMAFORM_SOURCE para a raiz do código. Os snapshots e as tabelas detalhadas acompanham o pacote.
