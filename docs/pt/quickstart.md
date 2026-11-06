# Início rápido

1. **Configure** `config.yaml` com pelo menos `paths.local_root` (onde ficam suas simulações). Para usar o cluster,
   preencha também `paths.remote_root` e a seção `cluster:` — veja [Configuração](config.md) e [SSH](ssh.md).
2. Rode `uv run lain` (ou `lain`).
3. Na árvore à esquerda, escolha uma pasta de simulação. Os **selos** mostram o que foi detectado: `BANDS`, `PDOS`,
   `RELAX`, `SCF`, `CALC`; saídas mostram `OK` / `INCOMPLETO`.
4. Clique em **Plot** na barra de atividades (ou **Ctrl+G**). O gráfico abre numa aba e o painel esquerdo troca para
   os ajustes; **Árvore** volta à árvore.
5. Ajuste e exporte com **Exportar** (**Ctrl+E**): as figuras vão para `plots/` da simulação.
6. Para gerar um novo cálculo, use **Criar cálculo** ([guia](create-calc/index.md)).
7. Para baixar resultados do cluster, use **Sincronizar** (menu *Cluster*) — sempre com prévia.

## Atalhos úteis

| Atalho | Ação |
|---|---|
| `F1` | Atalhos de teclado |
| `Ctrl+K` | Paleta de comandos |
| `Ctrl+G` / `Ctrl+E` | Gerar / exportar gráfico |
| `Ctrl+T` | Alternar tema |
| `Ctrl+1..4` | Ir para árvore, grade, área de abas, ajustes |
| `Alt+←` / `Alt+→` | Voltar / avançar nas pastas visitadas |
| `F5` | Atualizar |
| `Ctrl+W` / `Ctrl+Q` | Fechar aba / sair |
