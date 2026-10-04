"""The "Criar cálculo" window (spec 26): ``dialog`` (the two steps), ``setup_page`` (step 1),
``tabs_page`` (step 2: a tab per file, "Arquivos", "Descrição"), ``form`` / ``kmesh`` (the fields),
``preview`` (the files as they will be written) and ``labels`` (message lines)."""

from .dialog import CalcCreateDialog, CreateRequest

__all__ = ["CalcCreateDialog", "CreateRequest"]
