# Diretrizes do Repositório: Metodologia REA + Anthropic Code Review

## 0. Stack e Comandos do Projeto
- **Linguagem:** Python 3.10+ (CI testa 3.10 e 3.12). Script principal: `iss_globe.py`.
- **Ambiente:** venv em `.venv/` com `pip`. Dependências em `requirements.txt` (runtime) e `requirements-dev.txt` (dev, inclui pytest).
- **Testes (gate oficial, igual ao CI):** `.venv/bin/python -m pytest -v`
- **Checagem de sintaxe/import:** `.venv/bin/python -m compileall -q <arquivo_ou_pasta>`
- **Execução real offline (sem rede):** `.venv/bin/python iss_globe.py --offline --timestamp 2014-01-20T23:00:00 --out <saida>.html`
- Não há typechecker nem linter configurado. Não adicione um sem autorização.

## 1. Visão Geral e Papéis
- **Orquestrador (Chief of Staff / Sargento):**
  - Define arquitetura, escreve contratos tipados prévios em `src/contracts/` (módulos Python com `typing.Protocol`, `dataclass(frozen=True)`, `TypedDict` e type hints), lança e monitora agentes via `herdr`, executa a validação real (seção 3) e consolida commits na branch integradora.
- **Sub-Agente de Código (Exército de Implementação):**
  - Implementa funcionalidades em escopos/arquivos estritamente isolados.
- **Sub-Agente Revisor (Contexto Limpo):**
  - Executa a revisão estática do `git diff` sem memória prévia do processo de geração para evitar viés.

---

## 2. Regras Estritas do Quartel (Para Sub-Agentes)
1. **Isolamento de Escopo:** Edite APENAS os arquivos e pastas atribuídos no seu briefing.
2. **Proibição de Instalação:** NUNCA execute `pip install`, `uv add`/`uv pip install` ou `poetry add`, nem altere `requirements.txt`, `requirements-dev.txt`, `pytest.ini` ou o venv sem autorização.
3. **Proibição de Execução em Background e Rede:** NUNCA inicie servidores ou processos em background. NUNCA rode `iss_globe.py` sem `--offline` (o modo online baixa TLE da CelesTrak e grava `iss.tle`).
4. **Proibição de Commits:** NUNCA execute `git commit`, `git push` ou altere branches.
5. **Solicitações de Mudança Compartilhada:** Se precisar alterar um contrato em `src/contracts/` ou arquivo global (`iss_globe.py`, `requirements*.txt`, `pytest.ini`, `.github/`), crie um arquivo `.change-request.md` na raiz detalhando o motivo e o diff sugerido.
6. **Protocolo de Conclusão:**
   - Rode `.venv/bin/python -m compileall -q` nos arquivos que você alterou.
   - Rode `.venv/bin/python -m pytest -v` (ou só os testes do seu escopo, se o briefing indicar) e confirme que passa.
   - Escreva um relatório de alterações em `.status-report.md`, incluindo a saída resumida do pytest.
   - Responda no terminal APENAS com a palavra: **PRONTO**.

---

## 3. Diretrizes Anti-Regressão e Governança de Code Review
- **Teto de Rodadas de Correção (Máximo 3 Iterações):** Se um sub-agente não resolver um bug/apontamento após 3 interações, interrompa os nitpicks. O orquestrador deve solicitar a reavaliação completa da abordagem para evitar loops infinitos de tokens e pequenos ajustes.
- **Contexto Limpo na Revisão:** A revisão de PRs/diffs deve ser feita por um sub-agente zerado que lê apenas o `git diff`, a intenção da tarefa e as regras do `REVIEW.md`.
- **Testes Offline:** Testes não podem depender de rede. Use o TLE embutido ou fixtures; nunca chame a CelesTrak em `tests/`.
- **Validação Real e Não-Confiança em Testes Sintéticos:** Como agentes de IA frequentemente geram suítes de teste que não capturam regressões complexas (cobertura de mutação fraca), o Orquestrador DEVE executar o script de verdade antes do merge: rodar o comando offline da seção 0, conferir lat/lon/altitude impressos e abrir o HTML gerado (screenshot do globo).
