# Slab

Abre **vácuo** num eixo do SCF do bulk, como um `relax` (ou um `vc-relax`, se escolhido). Nenhum plano de Miller é cortado: a célula do bulk fica com
sua camada e um eixo cresce até o vácuo pedido (o mínimo, mais a altura de uma molécula e a distância de adsorção se o
SCF da molécula for informado).

- **Cálculo** (`calculation`, aparece também no modo Padrão):
    - `relax` (padrão): a célula fica fixa e o plano no parâmetro de rede do bulk. É o certo para a **superfície de um
      cristal**: o slab representa um sólido semi-infinito, e deixar o plano relaxar faria a tensão de superfície de um
      slab fino contraí-lo (e as energias de adsorção carregariam esse artefato).
    - `vc-relax`: o plano também relaxa (`cell_dofree`, padrão `2Dxy`), para um **material 2D isolado**.
- **Campo em dente de serra e correção de dipolo** (duas caixas, também no modo Padrão): **`tefield`** e
  **`dipfield`**, cada uma escreve a sua chave e as duas nascem como no SCF de origem (desligadas num SCF de bulk,
  que nunca as tem). As duas ligadas dão a correção de Bengtsson; `dipfield` sem `tefield` é ignorado pelo pw.x, e a
  janela avisa.
    - Com `tefield` ligado aparecem, no modo Avançado, **`edir`** (padrão 3: o vácuo fica ao longo de c),
      **`emaxpos`**, **`eopreg`** e **`eamp`** (padrão 0: só a correção, sem campo externo). `emaxpos` e `eopreg`
      vêm preenchidos com o valor calculado para a rampa do potencial ficar no meio do vácuo do slab gerado; um
      valor digitado é escrito como está, e o campo esvaziado volta ao calculado. Fora de `(0, 1)`, ou `edir` fora
      de 1 a 3, o campo marca o erro.
    - **Avisos sob o campo, que não bloqueiam "Criar"**: num slab assimétrico (camada inferior fixa, ou sem
      simetria que inverta c) sem a correção, o aviso sob `dipfield` explica que o dipolo interage com as imagens
      periódicas e a energia passa a depender do vácuo, e pede para ligar as duas caixas. Há avisos também para a
      rampa a menos de 3 Å de um átomo (ou com átomos dentro dela), `eamp ≠ 0`, `edir ≠ 3` e `tefield` sem efeito.
      Os mesmos textos ficam na aba "Arquivos".
    - Com `tefield` o pw.x não usa simetria; num `vc-relax`, `tstress` é removido (com ele o pw.x desligaria a
      tensão) e a tensão não inclui o termo do campo. O `geracao.md` diz as chaves, onde a rampa ficou e a que
      distância do átomo mais próximo. O complexo e a superfície limpa de uma adsorção precisam da mesma escolha.
- **Arquivos**: `relax_<prefix>.in` ou `vc-relax_<prefix>.in` (`prefix = '<prefix>-slab-<hkl>'`), o `.qsub` e
  `geracao.md` (relatório do que foi feito, com o cálculo escolhido). Se a estrutura não puder ser construída, o input
  sai como o SCF com as edições do relaxamento e o relatório diz por quê.
- **Campos**: **Superfície (eixo empilhado)**, **Inverter a superfície** (os átomos continuam dentro da caixa),
  **Vácuo mínimo (Å)**, **Distância de adsorção (Å)** (aparece e é somada só com molécula), **SCF da molécula
  (opcional)**, **Completar poliedros de borda (O + H)** com **Metais da borda** (aparece só com a opção marcada) e
  **Reconectar H cortados**, **Rede de k-points** (vazio = a do SCF reescalada), **Graus de liberdade da célula**
  (`cell_dofree`, só no vc-relax; `2Dxy` relaxa só o plano) e **Átomos fixos** (`if_pos 0 0 0`; os parâmetros de cada regra aparecem
  só quando ela é escolhida).
- **Passos máximos** (`nstep`, padrão 100, também no modo Padrão) e a linha `! restart_mode = 'restart'` comentada em
  `&CONTROL` são os do [Relaxamento](relax.md): se o relax não convergir, descomente a linha e rode de novo.

Código: `core/calc_create/types/slab.py`, `slab_fields.py`, geometria em `core/calc_create/surface/`
(`slab.py`, `fixing.py`, `kmesh.py`, `report.py`, `dipole.py`); os campos do campo e da correção em `types/dipole_fields.py`.
