# PharmaForm 0.2 — protótipo testável

Aplicativo Streamlit de pesquisa documental farmacotécnica e emissão de relatório preliminar PDF.

## O que funciona
- Entrada de medicamento, IFA, dose, forma farmacêutica e apresentação.
- Pesquisa **real, online** em Europe PMC, Crossref e rótulos da FDA/openFDA (internet necessária).
- Triagem preliminar de relevância por forma farmacêutica, com aviso de incerteza.
- Tabela editável de componentes, quantidades, justificativas e fontes.
- Rota conceitual de fabricação por forma farmacêutica, editável.
- PDF de estudo e exportação JSON de evidências.

## O que ainda NÃO funciona
- Não extrai automaticamente tabelas quantitativas do texto integral de patentes.
- Não gera Q2 confiável automaticamente, nem garante identidade exata da apresentação.
- Não consulta automaticamente bases ANVISA nem certifica conformidade brasileira.
- Não hospeda o app na internet nem roda diretamente dentro da conversa.

## Como testar no Windows
1. Instale Python 3.11+.
2. Extraia o ZIP e abra um terminal na pasta.
3. Execute `pip install -r requirements.txt`.
4. Execute `python -m streamlit run app.py`.
5. Abra o endereço local informado (normalmente http://localhost:8501).

## Como testar pelo celular sem PC
É necessário publicar o repositório em um serviço de hospedagem compatível com Streamlit (por exemplo Streamlit Community Cloud), conectando uma conta GitHub. O app precisa de internet para consultar as fontes. Não existe link hospedado neste pacote.

## Segurança técnica
O conteúdo é material de pré-formulação sujeito a revisão humana. Os resultados de busca são metadados, não evidência quantitativa validada. Nenhuma formulação deve ser fabricada sem verificação de fonte primária, qualificação de materiais, avaliação regulatória e estudos experimentais.
