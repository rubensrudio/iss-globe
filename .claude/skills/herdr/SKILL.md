---
name: herdr
description: Skill para controle do multiplexador de terminal herdr na orquestração de sub-agentes de IA
---

## Comandos do Herdr CLI para Orquestração (herdr 0.9.x)

O `herdr` permite ao Chief of Staff gerenciar múltiplos Claude Codes concorrentes.
O binário instalado é a autoridade da sintaxe: rode `herdr <grupo>` (ex.: `herdr agent`,
`herdr pane`) para ver as opções. Nunca rode `herdr` puro (abre a TUI) nem
`herdr server stop`.

### 0. Pré-condição
```bash
test "${HERDR_ENV:-}" = 1   # se falhar, não está dentro do herdr: pare
herdr status                # versão do client/server
```
O pane atual fica em `$HERDR_PANE_ID` (ex.: `w1:p1`). IDs são opacos: sempre leia-os
do JSON retornado, nunca deduza.

### 1. Abrir um painel para o sub-agente
```bash
herdr pane layout --pane "$HERDR_PANE_ID"          # decidir right (pane largo) ou down (alto)
herdr pane split --current --direction right --cwd "$PWD" --no-focus
# novo pane em .result.pane.pane_id
```
Para muitos agentes, evite colunas estreitas: divida o pane novo com `--pane <id> --direction down`.
Uma aba separada: `herdr tab create` (retorna `.result.tab` e `.result.root_pane`).

### 2. Iniciar o Claude Code no painel
```bash
herdr agent start <nome> --kind claude --pane <pane_id> [--timeout 60000] [-- <args do claude>]
```
- `<nome>` segue `[a-z][a-z0-9_-]{0,31}` e deve ser único (ex.: `auth-users`).
- Argumentos nativos do agente vão depois de `--`.
- Retorna só quando o agente está pronto. `agent_not_ready` = travado num diálogo:
  inspecione com `agent read`.

### 3. Enviar o briefing
```bash
herdr agent prompt <nome> "$(cat briefing.md)" --wait --timeout 1800000
```
- `--wait` espera o primeiro estado estável (`idle`, `done` ou `blocked`).
- Briefings longos: grave num arquivo e mande um prompt curto como
  "Leia e execute .briefings/<nome>.md".
- `agent_blocked`: o agente está num diálogo de aprovação. Leia antes de responder.
- Timeout ou `agent_prompt_stalled` não provam que o prompt não chegou. Não reenvie às cegas.

### 4. Verificar status dos agentes
```bash
herdr agent list                       # todos os agentes e estados
herdr agent get <nome>
herdr agent wait <nome> --timeout 1800000            # espera idle/done/blocked
herdr agent wait <nome> --until blocked --timeout 600000
```
*Estados:* `idle`, `working`, `blocked` (diálogo de aprovação/pergunta), `done`, `unknown`.
`done`/`idle` com a última resposta **PRONTO** = tarefa concluída.

### 5. Capturar a saída de um agente
```bash
herdr agent read <nome> --source recent-unwrapped --lines 120
```
Fontes: `visible`, `recent`, `recent-unwrapped` (melhor para logs), `detection`.
Para confirmar o PRONTO, leia também `.status-report.md` do agente.

### 6. Responder a diálogos e interromper
```bash
herdr agent send-keys <nome> enter      # aprovar opção já selecionada
herdr agent send-keys <nome> esc
herdr agent send-keys <nome> ctrl+c
```
Sempre leia o diálogo (`agent read`) antes de responder; na dúvida, pergunte ao usuário.

### 7. Rodar comandos comuns (servidor, testes) em outro painel
```bash
herdr pane split --current --direction down --cwd "$PWD" --no-focus
herdr pane run <pane_id> ".venv/bin/python -m pytest -v"
herdr pane wait-output <pane_id> --match "passed" --timeout 300000   # ou --regex
herdr pane read <pane_id> --source recent-unwrapped --lines 120
```

### 8. Encerrar
Feche só os panes que você criou: `herdr pane close <pane_id>`.

### Regras de coordenação
- Use `--no-focus` para trabalho em background; não roube o foco do usuário.
- Mire por `--current`, por pane ID explícito ou por nome único de agente, nunca pelo pane focado.
- Erros do servidor saem em JSON no stderr com exit 1. Erro de sintaxe sai com exit 2.
