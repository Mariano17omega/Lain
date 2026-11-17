# Energia de adsorção

Com **dois ou mais** SCFs selecionados, o menu de contexto oferece **Calcular adsorção…**.

1. A janela lista a energia total final de cada saída, pelo `prefix` (mais átomos primeiro), e o nível de teoria lido
   do cabeçalho: **Cutoffs (Ry)** (`ecutwfc/ecutrho`), **Funcional** (com a correção de dispersão, se houver; o tooltip
   lista os pseudopotenciais), **Ocupações**, **Spin** e **Malha k** (a do input de mesmo nome; o tooltip dá os
   k-pontos irredutíveis).
2. A equação é editável e vem preenchida como `E_ads = E(complexo) - E(substrato) - E(adsorvato)`; botões inserem
   `E(<prefix>)`. Valem `+ - * /`, parênteses e números.
3. O resultado aparece em Ry, eV e kJ/mol enquanto você digita.
4. Abaixo do resultado, **avisos** conferem as saídas que a equação usa: cutoffs, funcional (pelos códigos que o pw.x
   imprime, não pelo nome), dispersão, pseudopotencial de cada elemento, ocupações e spin; célula, correção de dipolo e malha k
   entre o complexo e o substrato; e o **balanço de átomos** por elemento (Σ coeficiente × átomos = 0), que acusa, por
   exemplo, o H que falta numa desprotonação (some ½ E(H₂) ou a sua referência). Os avisos **não bloqueiam**: o
   resultado e o botão de salvar continuam disponíveis.
5. **Salvar resultado** grava `energia_ads_<prefixes>.md` ao lado das saídas (nunca sobrescreve), com a tabela, a
   equação, o resultado, os avisos e notas para a revisão: a energia é eletrônica (sem ZPE nem contribuição
   térmica), sem dispersão a fisissorção sai subestimada, e uma molécula isolada só precisa de Γ.

Para gerar os cálculos que alimentam esta janela, use **Criar cálculo ▸ Energia de adsorção**
([guia](../create-calc/adsorption-energy.md)).

Código: `core/analysis/adsorption_energy.py`, `core/analysis/expression.py` (avaliador seguro),
`core/analysis/level_of_theory.py`, `core/analysis/consistency.py` (avisos e notas),
`core/analysis/adsorption_report.py`, `ui/dialogs/adsorption_energy.py`, `ui/tools/adsorption_energy_controller.py`.
