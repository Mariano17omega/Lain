# Organização de pastas

O Lain não exige nomes de arquivos, mas segue convenções de **estrutura**. Seguindo-as, a detecção, o sync e o
"Criar cálculo" funcionam sem configuração extra.

## Projetos e unidades de simulação

- `paths.local_root` é a raiz. **Cada pasta de primeiro nível é um projeto** (um sistema/composto de estudo).
- Dentro do projeto, as **unidades de simulação** (uma pasta com inputs e saídas de um cálculo) ficam em qualquer
  profundidade; não precisam de marca.
- `trash` é nome reservado na raiz (não pode ser nome de projeto).

```text
~/qe_simulations/                  ← paths.local_root
└── Pt111/                         ← projeto
    ├── 0_SCF/                     ← unidade: scf_Pt.in, scf.out, scf.qsub
    ├── 1_Relax/                   ← relax_Pt.in, relax.out, relax.qsub
    ├── 2_Bands/                   ← bands pw.x + bands.x (band_up/band_dw se houver spin)
    ├── 3_PDOS/                    ← scf, nscf e projwfc.x
    │   └── orbitals/              ← arquivos *pdos_atm#* (ou direto na pasta)
    └── plots/                     ← criado pelo Lain
```

## Regras que a detecção usa

- **Bandas**: um `pw.x` de `calculation='bands'`, a saída do `bands.x` (`.gnu`/`.dat`) e a energia de Fermi vinda do
  SCF. Se o SCF não está na pasta, o Lain procura em pastas irmãs com `scf` no nome (`*scf*`); o que faltar pode ser
  mapeado à mão (lembrado por pasta).
- **PDOS**: arquivos `*pdos_atm#*` direto na pasta ou em `orbitals/`.
- **Relax / vc-relax**: a saída do `pw.x` com `calculation` correspondente.
- Tudo é reconhecido pelo **conteúdo** (`bands.in` pode ser de `pw.x` ou `bands.x`).

## Numeração das pastas do "Criar cálculo"

O "Criar cálculo" prefixa a nova pasta com um número crescente: `0_Relax`, `1_Bands`, `2_PDOS`… (próximo = maior
número presente + 1; lacunas não são reaproveitadas). Você pode acrescentar sufixos (sítio, tag). Uma pasta existente
nunca é sobrescrita (`_2`, `_3`…).

## No cluster

Espelhe a árvore local sob `paths.remote_root`:

```text
/home/usuario/qe_simulations/      ← paths.remote_root
├── Pt111/…                        ← mesmas subpastas do local
└── trash/                         ← criada por "Apagar…" (nunca esvaziada pelo Lain)
```

- O sync espelha `local_root/<sub>` ⇄ `remote_root/<sub>`. Use nomes de pasta e arquivo com letras, dígitos, `.`, `_`,
  `+` e `-` se quiser submeter, cancelar ou apagar pelo modo cluster (nomes com espaço são recusados).
- Cada pasta de job deve ter o `.qsub`; o nome do job (`#$ -N`) deve coincidir com o da fila (`qstatus`).

## O que o Lain grava (e onde)

| O quê | Onde |
|---|---|
| Mapeamentos de pasta, grids, átomos da PDOS, favoritos/recentes | `<local_root>/.lain/` |
| Ajustes de gráfico `<tipo>.plot`, figuras exportadas, `view3d.plot` | `<simulação>/plots/` |
| Cópia local de um gráfico remoto + exportações | `<pasta>/tmp_remote/` e `tmp_remote/plots_remote/` |
| Estado da interface (QSettings) | `<paths.data>/settings.ini` ou `~/.config/qe-studio/` |
| Log, trava de instância, `submitted_jobs.log` | `<paths.data>` ou `~/.local/share/qe-studio/` |
| Lixeira do cluster | `<remote_root>/trash/` |

`.lain/`, `tmp_remote/` e `trash/` (na raiz) **nunca** são sincronizados; `plots/` e `*.plot` nunca sobem ao
cluster. Nada além disso é escrito dentro das pastas de simulação.
