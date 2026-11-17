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
  **Átomos fixos** (só os da superfície, ou uma tabela; os parâmetros de cada regra aparecem só quando ela é
  escolhida) e `etot_conv_thr`.
- **Campo em dente de serra e correção de dipolo** (as caixas `tefield` e `dipfield` aparecem também no modo
  Padrão), como no [Slab](slab.md): nascem como no SCF da superfície. A rampa é recolocada no meio do vácuo que sobra
  acima da molécula (a da superfície pode cair sobre ela), salvo `emaxpos`/`eopreg` digitados; o `geracao.md` mostra
  o `emaxpos` antigo quando muda. Sem a correção, o aviso sob `dipfield` explica por que ligá-la (a molécula fica de
  um lado só); outro aparece quando a escolha difere da do SCF da superfície: para a energia de adsorção, o complexo
  e a superfície limpa precisam da mesma. Nenhum deles bloqueia "Criar".
- A janela tem abas (Superfície / Molécula / Átomos fixos) e a **Visualização 3D** realça os átomos fixos.
- **Passos máximos** (`nstep`, padrão 100, também no modo Padrão) e a linha `! restart_mode = 'restart'` comentada em
  `&CONTROL` são os do [Relaxamento](relax.md): se o relax não convergir, descomente a linha e rode de novo.

Código: `core/calc_create/types/adsorption.py`, `adsorption_fields.py`, `adsorption_fixed.py`;
`core/calc_create/surface/` (`candidates.py`, `adsorb.py`, `merge.py`, `molecule.py`, `fixing.py`).
