# Relax e VC-Relax

**Detecção (`RELAX`)**: saída do `pw.x` com `calculation = 'relax'` ou `'vc-relax'`.

Mostra o progresso da otimização por passo, contra os limiares de convergência do input. Lê o BFGS e também a
**dinâmica amortecida** (`ion_dynamics = 'damp'`; `cell_dynamics = 'damp-pr'` ou `'damp-w'`): cada SCF é um passo e o
eixo X fica "Passo da dinâmica". A dinâmica amortecida não imprime entalpia, então um vc-relax dela mostra |ΔE|. A
dinâmica `fire` não é lida:

- Painel de **energia/entalpia** (|ΔE|) e painel de **força total**; **Painéis**: *Ambos*, *Energia / entalpia*, *Força*
  ou *Todos*.
- **Escala Y**: log ou linear; **Limiares** (linhas de `etot_conv_thr`/`forc_conv_thr`); janela de passos
  (`Passo mín.`/`Passo máx.`).
- Legenda com os limiares.

Depois de um relax convergido por BFGS, o menu de contexto da saída oferece **Gerar SCF convergido** (só o `.in`, com
a estrutura final — veja [fluxo de trabalho](../workflow.md)); a saída da dinâmica amortecida ainda não o oferece.

Código: `core/calculations/relax.py`, `relax_panels.py`; parser `core/qe/relax.py`, estrutura final em
`core/qe/final_structure.py`, SCF a partir do relax em `core/qe/scf_from_relax.py`.
