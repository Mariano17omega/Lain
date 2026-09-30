# Relax-Viewer

Aplicativo desktop em Python/Qt6 para avaliar o progresso de relaxamentos `relax` e `vc-relax` do Quantum ESPRESSO a partir de um arquivo `relax.out`.

O app filtra apenas passos completos do relaxamento, gera gráficos em PNG e mostra um status simples:

- `Relaxado`
- `Não relaxado`

## Requisitos

- Python 3.10+
- uv

## Instalação

```bash
uv sync
```

## Execução

### Modo Geral
```bash
uv run relax-viewer
```
Na janela principal, clique em **Selecionar output** e escolha o arquivo `.out`.

### Abrindo um arquivo diretamente via terminal
```bash
uv run relax-viewer caminho/para/relax.out
```

## Interface Interativa

Os gráficos e estruturas são renderizados dinamicamente na tela do aplicativo de forma totalmente interativa:
- **Energia e Força:** Suporte a escala Linear e Logarítmica via botão na aba correspondente.
- **Estrutura 3D:** Suporte a rotação 3D ilimitada (horizontal/vertical) e zoom dinâmico via painel lateral esquerdo. Legenda de cores CPK exibida no painel lateral direito.

Os gráficos não são mais salvos automaticamente no disco.

## Critério de relaxamento

O app marca o cálculo como `Relaxado` quando encontra a mensagem `bfgs converged` no output. Se essa mensagem não existir, usa o último passo completo como fallback:

- último `|ΔE| <= etot_conv_thr`
- última força total `<= forc_conv_thr`

Caso contrário, o cálculo é marcado como `Não relaxado`.

## Integração com o Sistema (Linux)

Para abrir arquivos `.out` com o Relax-Viewer diretamente pelo gerenciador de arquivos (dois cliques), siga os passos abaixo:

1. **Instale o executável globalmente no seu usuário:**
   ```bash
   uv tool install --force .
   ```

2. **Crie a entrada de desktop no sistema:**
   ```bash
   cat << 'EOF' > ~/.local/share/applications/relax-viewer.desktop
   [Desktop Entry]
   Name=Relax Viewer
   Comment=Visualizador de relaxamentos do Quantum ESPRESSO
   Exec=relax-viewer %f
   Terminal=false
   Type=Application
   Categories=Science;Physics;Chemistry;
   Icon=utilities-system-monitor
   MimeType=text/plain;
   EOF
   ```

3. **Atualize o banco de dados do sistema desktop:**
   ```bash
   update-desktop-database ~/.local/share/applications
   ```

4. **Associe a extensão `.out`:**
   Clique com o botão direito sobre um arquivo `.out` no seu gerenciador de arquivos, escolha **Abrir com...**, escolha **Relax Viewer** e marque a opção para definir como aplicativo padrão.

## Testes

```bash
uv run pytest
```
