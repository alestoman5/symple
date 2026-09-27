"""Autocompletion of built-ins, keywords and the user's own variables."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QCompleter

from ..catalog import CATALOG
from ..lang.tokens import KEYWORDS

NAME_ROLE = Qt.ItemDataRole.UserRole
KIND_ROLE = Qt.ItemDataRole.UserRole + 1

# Block keywords that are worth completing (short operators like 'or' are not).
_KEYWORD_COMPLETIONS = sorted(k for k in KEYWORDS if len(k) > 2)


class Completer(QCompleter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = QStandardItemModel(self)
        self.setModel(self._model)
        self.setCompletionRole(NAME_ROLE)
        self.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setModelSorting(QCompleter.ModelSorting.UnsortedModel)
        self.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        self.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.setMaxVisibleItems(10)
        self.popup().setObjectName("completer")
        self._user_names: list[str] = []
        self._rebuild()

    def set_user_names(self, names) -> None:
        names = sorted(n for n in names if n.isidentifier() and n not in CATALOG)
        if names != self._user_names:
            self._user_names = names
            self._rebuild()

    def _rebuild(self) -> None:
        self._model.clear()
        rows = []
        for name in self._user_names:
            rows.append((name, name, "your variable", "user"))
        for e in CATALOG.values():
            label = e.signature if e.kind == "function" else f"{e.name}    constant"
            rows.append((e.name, label, e.doc, e.kind))
        for k in _KEYWORD_COMPLETIONS:
            rows.append((k, f"{k}    keyword", "language keyword", "keyword"))
        rows.sort(key=lambda r: (r[0].lower(), r[0]))
        for name, label, doc, kind in rows:
            item = QStandardItem(label)
            item.setData(name, NAME_ROLE)
            item.setData(kind, KIND_ROLE)
            item.setToolTip(doc)
            item.setEditable(False)
            self._model.appendRow(item)

    def doc_for(self, name: str) -> str:
        e = CATALOG.get(name)
        return f"{e.signature} — {e.doc}" if e else ""
