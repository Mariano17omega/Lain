# Energia de adsorção (tipo do Criar cálculo)

Reúne **SCFs já preparados** (complexo, superfície limpa, molécula isolada…) numa pasta e roda um depois do outro por
um único script.

- **Etapa 1** recebe uma **lista** de dois ou mais SCFs. Cada um vira `scf_<prefix>.in`, copiado como está — só mudam
  `outdir = './tmp/'` e `jobs.pseudo_dir` — na ordem da lista. Nomes repetidos ganham `_2`, `_3`…
- **Script**: `ads_energy.qsub` executa os SCFs em ordem.
- **Bloqueio**: dois SCFs com o mesmo `prefix` impedem **Criar** (compartilhariam `<prefix>.EXIT` e `<prefix>.save`);
  mude o `prefix` à mão no modo Avançado.
- As energias e a equação são calculadas depois, na janela [Calcular adsorção…](../features/adsorption-energy.md).

Código: `core/calc_create/types/ads_energy.py`.
