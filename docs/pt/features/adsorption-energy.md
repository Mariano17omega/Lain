# Energia de adsorção

Com **dois ou mais** SCFs selecionados, o menu de contexto oferece **Calcular adsorção…**.

1. A janela lista a energia total final de cada saída, pelo `prefix` (mais átomos primeiro).
2. A equação é editável e vem preenchida como `E_ads = E(complexo) - E(substrato) - E(adsorvato)`; botões inserem
   `E(<prefix>)`. Valem `+ - * /`, parênteses e números.
3. O resultado aparece em Ry e eV enquanto você digita.
4. **Salvar resultado** grava `energia_ads_<prefixes>.md` ao lado das saídas (nunca sobrescreve).

Para gerar os cálculos que alimentam esta janela, use **Criar cálculo ▸ Energia de adsorção**
([guia](../create-calc/adsorption-energy.md)).

Código: `core/analysis/adsorption_energy.py`, `core/analysis/expression.py` (avaliador seguro),
`ui/dialogs/adsorption_energy.py`, `ui/tools/adsorption_energy_controller.py`.
