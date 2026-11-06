# Visualização 3D

Qualquer input do `pw.x` tem **Visualização 3D**: cada clique abre uma janela própria (duas para o mesmo arquivo =
duas janelas, cada uma com seus ajustes). Um relax mostra a geometria do *input*.

## Painel

- **Átomo clicado**: nome como no QE (`O43`), espécie, massa, pseudopotencial, posições, `if_pos`, magnetização inicial
  e vizinhos ligados.
- **Opções**: estilo, raio, fator de ligação, repetição, rótulos e tamanho, fundo, ligações, célula, perspectiva e eixos
  **x, y, z** e **a, b, c** (espessura própria).
- **Espécies** (cor, visibilidade) e **célula**.

## Controles

Arrastar gira; `Shift`+arrastar ou botão do meio move; roda dá zoom. `R` / **Resetar vista**; `X`/`Y`/`Z` (menu
*Vista*) e `A`/`B`/`C` olham ao longo de um eixo; `P` alterna perspectiva. **Rotação** (`x+ x- y+ y- z+ z-`) gira 45°
pela regra da mão direita sem mudar o zoom.

## Medidas

**Distância** (dois átomos) e **Ângulos** (três; o segundo é o vértice): cada medida vira uma linha (`O43 - H59  0.965 Å`).
**Copiar**, **Apagar** (última), **Limpar**, `Delete`.

## Outros

- **Print**: PNG com o dobro dos pixels em `plots/` da pasta (`<pastas>-<arquivo>-3d.png`, sem sobrescrever).
- **Átomos fixos**: anel em volta dos átomos com `if_pos = 0`.
- **Restaurar padrões**: volta opções e câmera ao padrão (medidas ficam).
- A vista é lembrada em `view3d.plot` (em `plots/`, uma seção por arquivo) ao fechar uma janela alterada.
- No "Criar cálculo", **Visualizar 3D** mostra o SCF e cada estrutura gerada e acompanha os campos enquanto você edita.
- Gerar **CIF** e **Abrir com XCrysDen** estão disponíveis no menu de contexto.

Código: `core/structure3d/` (modelo, ligações, câmera, medidas) e `ui/widgets/structure3d/`,
`ui/tools/structure3d_controller.py`.
