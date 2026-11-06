# Relax e VC-Relax

**Detecção (`RELAX`)**: saída do `pw.x` com `calculation = 'relax'` ou `'vc-relax'`.

Mostra o progresso do BFGS por passo, contra os limiares de convergência do input:

- Painel de **energia/entalpia** (|ΔE|) e painel de **força total**; **Painéis**: *Ambos*, *Energia / entalpia*, *Força*
  ou *Todos*.
- **Escala Y**: log ou linear; **Limiares** (linhas de `etot_conv_thr`/`forc_conv_thr`); janela de passos
  (`Passo mín.`/`Passo máx.`).
- Legenda com os limiares.

Depois de um relax convergido, o menu de contexto da saída oferece **Gerar SCF convergido** (só o `.in`, com a
estrutura final — veja [fluxo de trabalho](../workflow.md)).

Código: `core/calculations/relax.py`, `relax_panels.py`; parser `core/qe/relax.py`, estrutura final em
`core/qe/final_structure.py`, SCF a partir do relax em `core/qe/scf_from_relax.py`.
