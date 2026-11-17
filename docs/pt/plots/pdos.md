# PDOS

**Detecção (`PDOS`)**: arquivos `*pdos_atm#*` do `projwfc.x` (na pasta ou em `orbitals/`), mais saída do SCF/NSCF
(Fermi, HOMO/LUMO).

## Recursos

- **Fonte do Fermi** (SCF ou NSCF), deslocar para E_F, janela `E mín`/`E máx`, `dos_max`, **orientação** (energia no
  eixo x ou y). Em isolantes, o E_F é o meio do gap: veja [Nível de Fermi em isolantes](index.md#fermi-em-isolantes).
- **Agrupamento**: *Espécie + orbital*, *Espécie* ou *Orbital*; DOS total (cor própria); preencher estados ocupados.
- **Átomos…**: escolhe quais átomos entram; a seleção é lembrada por composto (fórmula + ordem das espécies) em
  `.lain/compounds.json`.
- **Séries** ocultáveis e com cor própria; mapas de cores por orbital e por espécie.
- **Spin** (se há dois canais): *Espelhado (↓ negativo)*, *Sobreposto*, *Só ↑*, *Só ↓*, *Soma (↑+↓)*.
- **Gap na legenda** (`legend_gap`) pelo HOMO/LUMO ou pela curva de DOS.
- **Spilling** (lido da saída do projwfc.x) na linha de status: a fração da carga ocupada que a base atômica deixa de
  fora, e por isso a soma das projeções fica abaixo da DOS total (`pdos_tot`). Acima de 5 % vira aviso.
- Com **Átomos…**, a linha de status soma as **cargas de Löwdin** dos átomos escolhidos (`Löwdin = … e`, com `↑−↓`
  quando há spin): a carga de um adsorvato, por exemplo.
- CSV dos dados na exportação.

Código: `core/calculations/pdos/` (`atoms.py`, `data.py`, `gap.py`, `params.py`, `render.py`, `table.py`),
parser em `core/qe/projwfc.py` e `core/qe/lowdin.py`, seleção em `core/project/compounds.py`.
