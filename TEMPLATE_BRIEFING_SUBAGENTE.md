Você é o sub-agente especialista responsável pelo módulo: **[NOME_DO_MODULO]**.

### 1. Escopo de Trabalho
- **Seus Arquivos/Pastas Exclusivos:** `[CAMINHOS]` (código) e `[CAMINHOS_DE_TESTE]` (testes em `tests/`)
- **Contratos Globais (Leitura):** `src/contracts/`

### 2. Tarefa Atribuída
[DESCREVER A FUNCIONALIDADE E META DE TEMPO DE 20-25 MINUTOS]

### 3. Regras Estritas do Quartel
- Trabalhe APENAS nos arquivos atribuídos.
- NÃO execute `pip install` nem altere `requirements*.txt`, `pytest.ini` ou o venv.
- NÃO rode `iss_globe.py` sem `--offline` e NÃO inicie processos em background.
- NÃO escreva testes que acessem a rede.
- NÃO faça `git commit`.
- Se precisar alterar arquivos globais ou contratos, crie um arquivo `.change-request.md`.

### 4. Finalização
Ao concluir a implementação:
1. Rode `.venv/bin/python -m compileall -q [CAMINHOS]`.
2. Rode `.venv/bin/python -m pytest -v [CAMINHOS_DE_TESTE]` e garanta que passa.
3. Crie um resumo no arquivo `.status-report.md`, com a saída resumida do pytest.
4. Responda no terminal estritamente com a palavra: **PRONTO**.
