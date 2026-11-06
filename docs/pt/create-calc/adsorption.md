# Molécula na superfície

Coloca uma molécula **sobre um átomo da superfície ou entre dois**, como `relax`.

- **Entradas**: o SCF de uma superfície **relaxada** (um bulk é recusado) e um segundo SCF para a **molécula** (lido,
  nunca alterado).
- **Arquivos**: `relax_<prefix>.in` (`prefix = '<superfície>-<fórmula>-<sítio>'`), `.qsub`, `geracao.md`. Sem estrutura
  possível, o input é o SCF da superfície com as edições de relax e o relatório explica.
- **Campos**: **Átomo âncora da molécula** (automático: o mais pesado), **Coordenação** (*monodentado* ou
  *bidentado*, no ponto médio), **Escolher o sítio por** *lista de candidatos* (tabela com letras de sítios
  equivalentes via `spglib`, **tolerância de simetria**) ou *coordenadas* (frações x y z, tolerância em Å),
  **Distância de adsorção relativa**, **Δx/Δy/Δz**, **Folga mínima**, **Vácuo mínimo**, **Janela da superfície**,
  **Átomos fixos** (só os da superfície, ou uma tabela) e `etot_conv_thr`.
- A janela tem abas (Superfície / Molécula / Átomos fixos) e a **Visualização 3D** realça os átomos fixos.

Código: `core/calc_create/types/adsorption.py`, `adsorption_fields.py`, `adsorption_fixed.py`;
`core/calc_create/surface/` (`candidates.py`, `adsorb.py`, `merge.py`, `molecule.py`, `fixing.py`).
