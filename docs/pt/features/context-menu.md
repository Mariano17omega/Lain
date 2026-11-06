# Menu de contexto

Botão direito sobre um arquivo ou pasta (na grade ou árvore):

| Item | Para quê |
|---|---|
| **Abrir local de origem** | abre a pasta no gerenciador de arquivos |
| **Abrir com** | programas instalados para o tipo, ou outro qualquer |
| **Copiar** | copia o item (cole no gerenciador ou terminal) |
| **Renomear** | nunca sobrescreve; fecha abas que mostram o item |
| **Comparar** | dois inputs QE selecionados |
| **Resumo** | saídas QE: aba com estado, tempos, resultados |
| **Plotar** | saída de SCF: convergência, sem salvar |
| **Bandas com DOS** | 1 pasta de bandas + 1 de PDOS selecionadas |
| **Gerar SCF convergido** | saída de relax/vc-relax convergido: cria só o `.in` |
| **Visualização 3D** | qualquer input do pw.x |
| **Abrir com XCrysDen** | `xcrysden --pwi` (input) / `--pwo` (saída) — precisa de `paths.xcrysden_path` |
| **Calcular adsorção…** | 2+ saídas de SCF selecionadas |
| **Adicionar aos favoritos** | pastas |

No modo cluster o menu muda: **Baixar**, **Plotar**, **Copiar caminho**, **Submeter…**, **Cancelar simulação…**,
**Apagar…** — veja [Modo remoto](../remote-mode.md).

Código: ações em `ui/files/*`, `ui/tools/*` e `ui/cluster/*`; o que cada módulo oferece vem de ganchos em
`core/calculations/base.py` (a UI não conhece o tipo do módulo).
