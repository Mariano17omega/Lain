# Detecção automática

Cada arquivo é classificado pelo que **contém** (`core/sniff.py`), nunca pelo nome: `bands.in` pode ser input do
`pw.x` ou do `bands.x`. Em seguida cada módulo de cálculo declara os **papéis** (`FileRole`) de que precisa e
`core/detection.py` roda todos os módulos do `REGISTRY` sobre a pasta.

| Selo | Módulo | Precisa de |
|---|---|---|
| `BANDS` | bandas | pw.x `bands`, saída do bands.x, energia de Fermi (SCF) |
| `PDOS` | PDOS | arquivos `pdos_atm#*` (na pasta ou em `orbitals/`), SCF/NSCF |
| `RELAX` | relax / vc-relax | saída do pw.x com `calculation` relax/vc-relax |
| `SCF` | convergência do SCF | saída do pw.x |
| `CALC` | genérico | qualquer saída/entrada QE (habilita Resumo e 3D) |

- SCF ausente: procurado em pastas irmãs `*scf*`. Qualquer papel faltando pode ser mapeado à mão
  (diálogo de mapeamento, lembrado por pasta em `.lain/`).
- Spin-polarizado: bandas de dois `bands.x` (`spin_component` 1 e 2) e PDOS com dois canais são reconhecidos.
- Cache por `(caminho, mtime, tamanho)`; o `sniff` lê só cabeça e cauda de arquivos grandes.

Veja o diagrama em [Arquitetura ▸ Detecção](../architecture/detection.md).
