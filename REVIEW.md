# Catálogo de Revisão de Código (REVIEW.md)

Este arquivo serve como "colinha" para os sub-agentes revisores e para o orquestrador identificarem code smells e falhas frequentes em Python.

## 1. Tipos de Falhas por Categoria

### A. Documentação e Especificação
- **Mentira / Inconsistência:** O README, o `--help` do argparse ou uma docstring afirma que algo se comporta de certa forma (ex.: valor padrão, unidade, fuso horário), mas o código faz o oposto.
- **Exemplo incorreto:** Exemplos de uso no README ou em docstrings que não rodam ou usam flags/assinaturas que não existem mais.

### B. Configurações e Variáveis de Ambiente
- **Redirecionamento Incorreto:** URLs de TLE ou endpoints apontando para fontes de teste/espelhos em vez da fonte oficial ou de um valor configurável.
- **Segredos no Código:** Chaves de API, tokens ou credenciais em hardcode.
- **Rede Insegura:** Download sem `certifi`/verificação TLS, sem timeout ou sem tratamento de falha de rede.

### C. Contratos e Tipagem
- **Bypass de Tipos:** Uso injustificado de `typing.Any`, `typing.cast`, `# type: ignore` ou funções públicas sem type hints em código novo.
- **Quebra de Contrato:** Alteração de assinatura de função, `Protocol`, `dataclass` ou `TypedDict` em `src/contracts/` sem atualizar todos os consumidores e testes.
- **Unidades e Tempo:** Mistura de graus/radianos ou km/m, `datetime` sem fuso (naive) onde se espera UTC, ou longitude fora de [-180, 180].

### D. Execução e Lógica Retida
- **Imports Desnecessários / Mortos:** Imports não usados, ou dependências novas não declaradas em `requirements.txt`.
- **Efeitos Colaterais Escondidos:** Modificação de estado global, escrita em disco ou acesso à rede em funções que deveriam ser puras ou no import do módulo.
- **Perda de Vetorização:** Laços Python sobre tempos/posições onde o código usava `sat.at(times)` ou operações NumPy vetorizadas.
- **Exceções Engolidas:** `except:` ou `except Exception: pass` que escondem falhas reais.
- **Testes Frágeis:** Testes que dependem de rede, do relógio atual (`now`) ou da ordem de execução.

---

## 2. Regras para o Revisor de IA
1. **Verificação Baseada em Evidências:** Todo comentário de bug no PR/diff DEVE citar o caminho do arquivo e o número exato da linha.
2. **Limite de Nitpicks:** Reporte no máximo 3 sugestões de estilo (PEP 8, nomes) por revisão para evitar barulho. Foque em bugs de lógica, cálculo e segurança.
3. **Filtro Social:** Apenas confirme um erro se houver certeza razoável de que a mudança quebra a intenção declarada do código.
