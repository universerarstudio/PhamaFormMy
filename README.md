# PharmaForm 0.3

Compilador farmacotécnico para pesquisa de referências/IFAs e geração de uma proposta inicial Q1/Q2 com cálculos, racional, fontes, lacunas e processo em um relatório.

## Uso

1. Informe referência ou IFA, concentração, forma e liberação.
2. Para sólidos, informe o peso e se ele corresponde ao núcleo/conteúdo ou ao produto acabado. Para líquidos, informe o volume final.
3. Confirme a base da dose: base/porção ativa ou o próprio material (sal/IFA). O teor é aplicado uma única vez à pesagem.
4. Clique em **Pesquisar e gerar proposta**. A pesquisa e a resolução da identidade ocorrem nos bastidores.
5. Revise a formulação, as hipóteses, os componentes sugeridos, as fontes e as lacunas. Edite a tabela se necessário e exporte PDF/JSON.

## Motor geral

O motor não contém uma decisão de formulação por nome de medicamento. Ele aceita novos produtos e usa três níveis de evidência:

- **Exemplo quantitativo compatível do mesmo IFA:** adapta percentuais documentados, recalcula o material ativo e ajusta o diluente. Dados de exemplos específicos ficam em `formulation_models.json`, com documento e localizador. Podem ser acrescentados sem modificar o algoritmo.
- **Q1 recuperada para a apresentação:** planeja níveis experimentais por função, forma/liberação e carga de IFA. O peso é fechado por balanço. Os centros de estudo são escolhas explícitas do motor, nunca apresentados como quantidades comerciais publicadas. Quando permitido, funções ausentes podem receber excipientes sugeridos, marcados individualmente e com documentação funcional.
- **Dados insuficientes ou arquitetura incompatível:** informa o motivo e as pendências concretas. Não transfere a fórmula de outro IFA, uma apresentação de cápsulas para suspensão, ou um desenho convencional para liberação entérica/osmótica.

`formulation_models.json` inclui exemplos documentais de matrizes por compressão direta/granulação e pó para suspensão. São evidências de regressão e ponto de partida, não uma lista dos únicos produtos aceitos. As buscas de Tylenol, Advil e Glucophage exercitam o motor funcional sem modelos quantitativos cadastrados para esses medicamentos.

## Fontes e rastreabilidade

- openFDA: metadados de identidade e texto de rotulagem; detecção de Q1 e apresentação.
- PubChem: sinônimos e propriedades moleculares; conferência de identidade e conversão base/material. Relações estequiométricas ambíguas não são adivinhadas.
- Europe PMC e Crossref: artigos/resumos e metadados com filtro obrigatório de identidade.
- Google Patents: pesquisa real, texto HTML e colunas quantitativas completas; intervalos, Q.S. e colunas incompletas não são tratados como fórmula fechada.
- EMA e documentos técnicos de fabricantes: perfis curados com data explícita, fonte e localizador. Acesso online e revisão do perfil são estados diferentes; falhas de conexão são mantidas no relatório.
- ANVISA: páginas oficiais de registro e referência são incluídas. O app **não confirma automaticamente registro/comparador brasileiro** nem certifica conformidade pela presença do campo Brasil.

A pesquisa tem cache de uma hora. O modo sem internet usa somente evidências curadas identificadas como tais; não simula busca online. O JSON registra consultas, fontes mantidas/descartadas, falhas e o alvo resolvido.

## Cálculos e limites técnicos

- Dose em mg, g ou µg por unidade; mg/mL para soluções e pós para suspensão. Associações, UI e outros denominadores exigem modelos específicos.
- Massa do material = porção ativa × fator molecular ÷ fração de teor; sem excesso automático.
- Peso acabado com revestimento: núcleo = peso acabado ÷ (1 + ganho sobre o núcleo).
- Materiais coprocessados não são somados novamente como componentes independentes.
- A massa de cápsula vazia depende de especificação própria; o cálculo de enchimento não a presume.
- Volume de água de reconstituição não é igualado ao volume final. Solução com veículo/pH pendentes fica identificada como hipótese parcial.
- Editar a dose do IFA na tabela sem mudar a entrada, deixar massas negativas/não finitas ou perder o fechamento bloqueia o PDF da proposta. O JSON registra erros de validação.
- O relatório é produzido a partir dos dados atuais; nova pesquisa não reutiliza PDF antigo.

O resultado é uma formulação inicial de desenvolvimento. Fechamento matemático e fontes documentais não demonstram desempenho farmacêutico, bioequivalência ou validação de processo. A formulação deve ser avaliada experimentalmente.

## Executar

Python 3.11 ou superior:

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

No Streamlit Community Cloud, use `app.py` como arquivo principal, mantendo todos os módulos e `formulation_models.json` no mesmo diretório. Não é necessária chave de modelo de IA para o motor determinístico.

## Verificação

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python tests/run_acceptance.py ../acceptance_output
```

Os testes automatizados verificam conversão, teor, balanço com/sem filme, identidades conflitantes, fórmulas de produtos não cadastrados, separação entre apresentações, associações em rotulagem, colunas de patentes, PDF e fluxo Streamlit. Os casos online são separados do CI offline e registram o que foi realmente recuperado. Consulte `TEST_RESULTS.md`.
