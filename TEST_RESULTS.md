# Verificação da versão 0.3

32 testes automatizados passaram, incluindo o fluxo de entrada → proposta → PDF com Streamlit AppTest.

## Casos com fontes online

| Referência | Entrada | Resultado observado |
|---|---|---|
| Intuniv | 4 mg de guanfacina base · Comprimido revestido | Proposta experimental: 4.592629 mg de material; soma 200.000000 mg; sem erros de dose/balanço. |
| Advil | 200 mg · Comprimido revestido | Proposta experimental: 200.000000 mg de material; soma 350.000000 mg; sem erros de dose/balanço. |
| Glucophage | 500 mg · Comprimido revestido | Proposta experimental: 500.000000 mg de material; soma 700.000000 mg; sem erros de dose/balanço. |
| Tamiflu | 6 mg/mL · Pó para suspensão oral | Proposta experimental: 472.932138 mg de material; soma 11912.648312 mg; sem erros de dose/balanço. |
| Tylenol | 500 mg · Comprimido revestido | Proposta experimental: 500.000000 mg de material; soma 700.000000 mg; sem erros de dose/balanço. |
| Prilosec | 20 mg · Cápsula dura | Q2 não fechada: não foi recuperada Q1 compatível com a apresentação solicitada; lacuna exibida, sem aplicar fórmula convencional. |

Tylenol, Advil e Glucophage não têm exemplos quantitativos próprios no catálogo; as composições foram geradas pelo motor geral sobre a Q1 recuperada, com níveis experimentais e eventuais componentes sugeridos explicitamente rotulados.

Todas as cinco propostas calculadas fecharam na massa alvo. Tamiflu foi calculado por frasco de 60 mL finais; a massa é de pó seco. A apresentação Prilosec foi testada como cápsula de liberação retardada e permaneceu documentalmente incompleta.

Falhas de acesso a fontes foram expostas na pesquisa/exportação, incluindo indisponibilidade do catálogo BASF. Perfis curados conservam data e localizador; sua presença não é descrita como uma nova confirmação online.

Estes testes verificam comportamento de software e cálculos. Não validam desempenho farmacêutico, formulação comercial, processo, bioequivalência ou registro ANVISA.
