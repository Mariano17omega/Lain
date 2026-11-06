# Paleta de comandos

`Ctrl+K` (menu *Ajuda ▸ Paleta de comandos*) abre uma busca difusa (*fuzzy*) sobre **ações do menu** e **pastas** do
projeto. Digite parte do nome, setas para escolher, `Enter` executa/abre.

- As ações vêm da tabela única `ui/actions.py:ACTIONS` (id estável, menu, texto, atalho).
- As pastas vêm do índice `core/search/folder_index.py`, com busca de `core/search/fuzzy.py` (ignora acentos).
- `F1` lista todos os atalhos.
