# Fluxo de trabalho recomendado

```mermaid
flowchart TD
    A[SCF convergido<br/>cutoff, k-points] --> B[Relax / VC-Relax]
    B --> C[SCF convergido<br/>da estrutura final]
    C --> D[Bandas]
    C --> E[PDOS]
    C --> F[Carga / Diferença de carga]
    C --> G[Slab]
    G --> H[Supercélula]
    H --> I[Molécula na superfície]
    I --> J[Energia de adsorção]
```

## Ordem sugerida

1. **SCF** com cutoffs e malha k testados. É a base: quase todo tipo do "Criar cálculo" parte de um SCF.
2. **Relax** (posições) ou **VC-Relax** (posições + célula). Acompanhe `|ΔE|` e força no [gráfico de relax](plots/relax.md).
3. **SCF convergido**: do menu de contexto da saída de um relax/vc-relax convergido, "Gerar SCF convergido" cria o `.in`
   com a estrutura final.
4. A partir do SCF final:
    - **Bandas** (pw.x `bands` + `bands.x`) — [gráfico](plots/bands.md);
    - **PDOS** (NSCF + `projwfc.x`) — [gráfico](plots/pdos.md); junte os dois em **Bandas com DOS**;
    - **Carga** / **Diferença de carga** (`pp.x`) para ver em XCrySDen.
5. **Superfícies**: Slab (abre vácuo) → Supercélula (repete a célula) → Molécula na superfície → rode os SCFs e
   calcule a [energia de adsorção](features/adsorption-energy.md).

## Ciclo diário

```mermaid
sequenceDiagram
    actor U as Você
    participant L as Lain
    participant C as Cluster
    U->>L: Criar cálculo (pasta + .in + .qsub)
    U->>L: Enviar ao cluster (prévia, só arquivos novos)
    L->>C: rsync (ssh)
    U->>L: Modo cluster ▸ Submeter… (confirma)
    L->>C: cd pasta && chmod a+x && qsub
    U->>L: Fila (barra superior) acompanha o job
    U->>L: Sincronizar (prévia) ▸ baixar resultados
    U->>L: Plot / Resumo / 3D
```

!!! tip "Nunca pule o SCF"
    Bandas, PDOS e carga leem a energia de Fermi e a estrutura do SCF. Mantenha o SCF por perto: o Lain o procura em
    pastas irmãs `*scf*`.
