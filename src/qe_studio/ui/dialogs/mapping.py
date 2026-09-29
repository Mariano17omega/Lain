"""Manual file mapping when automatic detection fails (PRD §3.2)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.calculations import CalculationModule, DetectionResult
from ..widgets.common import set_variant


class ManualMappingDialog(QDialog):
    """Pick the calculation type and the file for each role; prefilled with what was found."""

    def __init__(
        self,
        folder: Path,
        modules: list[CalculationModule],
        results: list[DetectionResult],
        parent: QWidget | None = None,
        message: str = "",
    ):
        super().__init__(parent)
        self.setWindowTitle("Mapear arquivos manualmente")
        self.setModal(True)
        self.setMinimumWidth(620)
        self.folder = folder
        self.modules = modules
        self.results = {r.kind: r for r in results}
        self.edits: dict[str, QLineEdit] = {}

        layout = QVBoxLayout(self)
        title = set_variant(QLabel("Não foi possível identificar todos os arquivos"), "dialogTitle")
        text = message or (
            "Indique o tipo de cálculo e os arquivos de cada papel. "
            "Campos marcados com * são obrigatórios."
        )
        layout.addWidget(title)
        layout.addWidget(set_variant(QLabel(text), "dialogText"))
        layout.addWidget(set_variant(QLabel(str(folder)), "mono"))

        kind_row = QHBoxLayout()
        kind_row.addWidget(QLabel("Tipo de cálculo:"))
        self.kind = QComboBox()
        for module in modules:
            self.kind.addItem(module.display_name, module.kind)
        preferred = next((r.kind for r in results if r.kind in {m.kind for m in modules}), None)
        if preferred:
            self.kind.setCurrentIndex(self.kind.findData(preferred))
        kind_row.addWidget(self.kind, 1)
        layout.addLayout(kind_row)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 8, 0, 8)
        layout.addWidget(self.grid_host)
        self.remember = QCheckBox("Lembrar este mapeamento para esta pasta")
        self.remember.setChecked(True)
        layout.addWidget(self.remember)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Plotar")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.kind.currentIndexChanged.connect(self._build_rows)
        self._build_rows()

    @property
    def module(self) -> CalculationModule:
        kind = self.kind.currentData()
        return next(m for m in self.modules if m.kind == kind)

    def mapping(self) -> dict[str, list[Path]]:
        out = {}
        for role_id, edit in self.edits.items():
            paths = [Path(p.strip()) for p in edit.text().split(";") if p.strip()]
            if paths:
                out[role_id] = paths
        return out

    def _build_rows(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.edits.clear()
        module = self.module
        found = self.results.get(module.kind)
        for row, role in enumerate(module.roles):
            label = QLabel(role.label + (" *" if role.required else ""))
            edit = set_variant(QLineEdit(), "mono")
            if role.multiple:
                edit.setPlaceholderText("vários arquivos separados por ;")
            if found and role.id in found.files:
                edit.setText(";".join(str(p) for p in found.files[role.id]))
            browse = QPushButton("…")
            browse.setFixedWidth(32)
            browse.clicked.connect(lambda _c=False, r=role, e=edit: self._browse(r, e))
            edit.textChanged.connect(self._validate)
            self.grid.addWidget(label, row, 0)
            self.grid.addWidget(edit, row, 1)
            self.grid.addWidget(browse, row, 2)
            self.edits[role.id] = edit
        self._validate()

    def _browse(self, role, edit: QLineEdit) -> None:
        if role.multiple:
            paths, _ = QFileDialog.getOpenFileNames(self, role.label, str(self.folder))
            if paths:
                edit.setText(";".join(paths))
        else:
            path, _ = QFileDialog.getOpenFileName(self, role.label, str(self.folder))
            if path:
                edit.setText(path)

    def _validate(self) -> None:
        mapping = self.mapping()
        ok = all(
            role.id in mapping and all(p.is_file() for p in mapping[role.id])
            for role in self.module.roles
            if role.required
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ok)


def ask_mapping(
    parent: QWidget,
    folder: Path,
    modules: list[CalculationModule],
    results: list[DetectionResult],
    message: str = "",
) -> tuple[str, dict[str, list[Path]], bool] | None:
    """(kind, mapping, remember) or None if cancelled."""
    dialog = ManualMappingDialog(folder, modules, results, parent, message)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.module.kind, dialog.mapping(), dialog.remember.isChecked()
