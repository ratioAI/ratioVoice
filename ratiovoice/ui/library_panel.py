"""Linke Seite: Stimmenbibliothek, Favoriten und eigene Profile."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QMenu, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ..profiles import library
from ..profiles.store import ProfileStore

FAVORITES = "★  Favoriten"
OWN = "Eigene Profile"


class LibraryPanel(QWidget):
    profile_chosen = Signal(dict)  # Einstellungen des angeklickten Profils

    def __init__(self, store: ProfileStore, parent=None):
        super().__init__(parent, objectName="panel")
        self._store = store
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 8, 8)
        layout.addWidget(QLabel("STIMMENBIBLIOTHEK", objectName="section"))
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(14)
        self._tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._context_menu)
        self._tree.itemClicked.connect(self._on_click)
        layout.addWidget(self._tree)
        layout.addWidget(QLabel("Rechtsklick: Favorit setzen / löschen", objectName="muted"))
        self.refresh()

    def _all_profiles(self) -> dict[str, dict]:
        profiles = {p["name"]: p["settings"] for p in library.PROFILES}
        profiles.update(self._store.presets)
        return profiles

    def refresh(self) -> None:
        collapsed = {
            self._tree.topLevelItem(i).text(0)
            for i in range(self._tree.topLevelItemCount())
            if not self._tree.topLevelItem(i).isExpanded()
        }
        self._tree.clear()
        everything = self._all_profiles()
        groups = [(FAVORITES, [n for n in self._store.favorites if n in everything])]
        groups += [(c, [p["name"] for p in library.by_category(c)]) for c in library.CATEGORIES]
        groups.append((OWN, list(self._store.presets)))
        for title, names in groups:
            group = QTreeWidgetItem([title])
            font = group.font(0)
            font.setBold(True)
            group.setFont(0, font)
            group.setFlags(Qt.ItemIsEnabled)
            self._tree.addTopLevelItem(group)
            for name in names:
                star = "★ " if name in self._store.favorites and title != FAVORITES else ""
                item = QTreeWidgetItem([star + name])
                item.setData(0, Qt.UserRole, name)
                group.addChild(item)
            if not names:
                hint = QTreeWidgetItem(["(noch leer)"])
                hint.setFlags(Qt.NoItemFlags)
                group.addChild(hint)
            group.setExpanded(title not in collapsed)

    def _on_click(self, item: QTreeWidgetItem):
        name = item.data(0, Qt.UserRole)
        if name:
            self.profile_chosen.emit(self._all_profiles()[name])

    def _context_menu(self, point):
        item = self._tree.itemAt(point)
        name = item.data(0, Qt.UserRole) if item else None
        if not name:
            return
        menu = QMenu(self)
        is_favorite = name in self._store.favorites
        favorite = menu.addAction("Aus Favoriten entfernen" if is_favorite else "Zu Favoriten hinzufügen")
        delete = menu.addAction("Eigenes Profil löschen") if name in self._store.presets else None
        chosen = menu.exec(self._tree.viewport().mapToGlobal(point))
        if chosen is favorite:
            self._store.toggle_favorite(name)
        elif delete is not None and chosen is delete:
            self._store.delete_preset(name)
        self.refresh()
