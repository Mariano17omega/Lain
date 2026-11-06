# Glossário

| Termo | Significado |
|---|---|
| **QE** | Quantum ESPRESSO (7.1 ou mais novo) |
| **pw.x** | programa de ondas planas do QE: SCF, NSCF, bands, relax, vc-relax |
| **bands.x** | pós-processa as bandas do `pw.x` (`.gnu`/`.dat`) |
| **projwfc.x** | projeta estados em orbitais atômicos → arquivos `pdos_atm#*` |
| **pp.x** | pós-processamento (densidade de carga, XSF) |
| **SCF / NSCF** | ciclo autoconsistente / cálculo não autoconsistente numa malha |
| **relax / vc-relax** | otimização de posições / de posições e célula |
| **BFGS** | algoritmo de otimização usado no relax |
| **PDOS** | densidade de estados projetada |
| **E_F, VBM, CBM, HOMO/LUMO** | energia de Fermi, topo da valência, fundo da condução, orbitais de fronteira |
| **`prefix`, `outdir`, `pseudo_dir`** | chaves do `&CONTROL` do `pw.x` |
| **`.qsub`** | script de job (SGE) |
| **SGE / `qsub` / `qstatus` / `qdel`** | gerenciador de filas, submissão, consulta, remoção |
| **`#$ -N`** | nome do job |
| **`<prefix>.EXIT`** | arquivo que faz o `pw.x` parar com limpeza |
| **NP / NK (pools)** | núcleos do job / `-nk` do `pw.x` |
| **Selo (badge)** | etiqueta do tipo detectado: BANDS, PDOS, RELAX, SCF, CALC |
| **Projeto** | pasta de primeiro nível de `local_root` |
| **Unidade de simulação** | pasta com inputs e saídas de um cálculo |
| **`.lain/`, `.plot`, `tmp_remote/`, `trash/`** | veja [Organização de pastas](folders.md) |
| **Modo cluster** | navegação nos arquivos remotos — [Modo remoto](remote-mode.md) |
| **Slab / supercélula** | célula com vácuo / célula repetida |
| **Monodentado / bidentado** | adsorvato ligado a um / a dois átomos |

## Interface: português ↔ inglês

| Português | English |
|---|---|
| Criar cálculo | Create calculation |
| Sincronizar / Baixar / Enviar ao cluster | Sync / Download / Send to cluster |
| Modo cluster (Ver arquivos do cluster) | Cluster mode |
| Submeter… / Cancelar simulação… / Apagar… | Submit… / Cancel simulation… / Delete… |
| Gerar gráfico / Exportar gráfico | Generate plot / Export plot |
| Bandas com DOS | Bands with DOS |
| Visualização 3D | 3D view |
| Resumo / Comparar com… | Summary / Compare with… |
| Recarregar config.yaml | Reload config.yaml |
| Padrão / Avançado | Standard / Advanced |
