"""Aba de plugins de busca (espelha a UI de search-plugins do qBittorrent).

Os plugins sao arquivos .py guardados na pasta de plugins do qBittorrent.
O estado (habilitado/desabilitado, instalados, removidos) fica salvo em
``~/.config/torrentguard-ai/search_plugins.json``.
"""

import json
import os
import shutil
import webbrowser
from pathlib import Path

import requests
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QListWidget, QListWidgetItem, QMessageBox,
                             QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
                             QFileDialog, QInputDialog)
from PyQt6.QtCore import Qt

from core.config import CONFIG_DIR

PLUGINS_DIR = Path.home() / ".config" / "qBittorrent" / "nova" / "searchengine" / "searchplugins"
PLUGINS_DIR_ALT = Path.home() / ".local" / "share" / "qBittorrent" / "nova" / "searchengine" / "searchplugins"
STATE_FILE = CONFIG_DIR / "search_plugins.json"

PLUGIN_BASE = "https://raw.githubusercontent.com/qbittorrent/search-plugins/master/"

OFFICIAL_PLUGINS = [
    {"name": "1337x", "url": PLUGIN_BASE + "1337x.py", "version": "1.0"},
    {"name": "eztv", "url": PLUGIN_BASE + "eztv.py", "version": "1.0"},
    {"name": "lime_torrents", "url": PLUGIN_BASE + "lime_torrents.py", "version": "1.0"},
    {"name": "nyaa", "url": PLUGIN_BASE + "nyaa.py", "version": "1.0"},
    {"name": "piratebay", "url": PLUGIN_BASE + "piratebay.py", "version": "1.0"},
    {"name": "rarbg", "url": PLUGIN_BASE + "rarbg.py", "version": "1.0"},
    {"name": "rockbox", "url": PLUGIN_BASE + "rockbox.py", "version": "1.0"},
    {"name": "solidtorrents", "url": PLUGIN_BASE + "solidtorrents.py", "version": "1.0"},
    {"name": "tgx", "url": PLUGIN_BASE + "tgx.py", "version": "1.0"},
    {"name": "torlock", "url": PLUGIN_BASE + "torlock.py", "version": "1.0"},
    {"name": "torrentscsv", "url": PLUGIN_BASE + "torrentscsv.py", "version": "1.0"},
    {"name": "torrentproject", "url": PLUGIN_BASE + "torrentproject.py", "version": "1.0"},
    {"name": "yts", "url": PLUGIN_BASE + "yts.py", "version": "1.0"},
]

WIKI_URL = "https://github.com/qbittorrent/search-plugins/wiki/Unofficial-search-plugins"


class SearchPluginsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        for p in (PLUGINS_DIR, PLUGINS_DIR_ALT):
            p.mkdir(parents=True, exist_ok=True)
        self.state = self.load_state()
        self.setup_ui()
        self.reload_table()

    # ------------------------------------------------------------------
    # estado
    # ------------------------------------------------------------------
    @staticmethod
    def load_state():
        default = {"disabled": [], "removed": [], "custom": []}
        try:
            if STATE_FILE.exists():
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                for key in default:
                    data.setdefault(key, default[key])
                return data
        except Exception:
            pass
        return default

    def save_state(self):
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps(self.state, indent=2, ensure_ascii=False),
                                  encoding="utf-8")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # plugins instalados na pasta do qBittorrent
    # ------------------------------------------------------------------
    def installed_files(self):
        """Mapa nome -> arquivo .py encontrado nas pastas de plugins."""
        found = {}
        for folder in (PLUGINS_DIR, PLUGINS_DIR_ALT):
            if not folder.exists():
                continue
            for file in folder.glob("*.py"):
                found.setdefault(file.stem, file)
        return found

    def plugin_rows(self):
        """Lista de plugins para exibir (oficiais + customizados + instalados)."""
        rows = []
        installed = self.installed_files()
        seen = set()

        for pl in OFFICIAL_PLUGINS:
            name = pl["name"]
            if name in self.state["removed"]:
                continue
            seen.add(name)
            rows.append({
                "name": name,
                "url": pl["url"],
                "version": pl.get("version", "1.0"),
                "file": installed.get(name),
                "enabled": name not in self.state["disabled"],
            })

        for pl in self.state["custom"]:
            name = pl.get("name", "?")
            if name in self.state["removed"]:
                continue
            seen.add(name)
            rows.append({
                "name": name,
                "url": pl.get("url", ""),
                "version": pl.get("version", "1.0"),
                "file": installed.get(name),
                "enabled": name not in self.state["disabled"],
            })

        for name, file in installed.items():
            if name in seen:
                continue
            rows.append({
                "name": name,
                "url": file.as_uri(),
                "version": "local",
                "file": file,
                "enabled": name not in self.state["disabled"],
            })
        return rows

    # ------------------------------------------------------------------
    # interface
    # ------------------------------------------------------------------
    def setup_ui(self):
        layout = QVBoxLayout(self)
        info = QLabel("Search plugins")
        info.setStyleSheet("font-weight: bold; font-size: 14px;")
        info2 = QLabel("Only one website per plugin. If more than one is needed, use multiple plugins.")
        layout.addWidget(info)
        layout.addWidget(info2)

        group = QGroupBox("Installed search plugins")
        gl = QVBoxLayout(group)
        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(["Enabled", "Name", "Version", "URL"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        gl.addWidget(self.tbl)

        btns = QHBoxLayout()
        self.btn_enable = QPushButton("Enable")
        self.btn_disable = QPushButton("Disable")
        self.btn_uninstall = QPushButton("Uninstall")
        self.btn_update = QPushButton("Update")
        self.btn_enable.clicked.connect(self.enable_selected)
        self.btn_disable.clicked.connect(self.disable_selected)
        self.btn_uninstall.clicked.connect(self.uninstall_selected)
        self.btn_update.clicked.connect(self.update_plugins)
        for btn in (self.btn_enable, self.btn_disable, self.btn_uninstall, self.btn_update):
            btns.addWidget(btn)
        gl.addLayout(btns)
        layout.addWidget(group)

        group2 = QGroupBox("Search plugins")
        g2l = QVBoxLayout(group2)
        lbl3 = QLabel("Find more search plugins at: " + WIKI_URL)
        lbl3.setWordWrap(True)
        btn_open_wiki = QPushButton("Open link")
        btn_open_wiki.clicked.connect(lambda: webbrowser.open(WIKI_URL))
        btn_install_local = QPushButton("Install plugin from local file...")
        btn_install_local.clicked.connect(self.install_local)
        btn_install_url = QPushButton("Install plugin from URL...")
        btn_install_url.clicked.connect(self.install_url)
        btns2 = QHBoxLayout()
        btns2.addWidget(btn_open_wiki)
        btns2.addWidget(btn_install_local)
        btns2.addWidget(btn_install_url)
        g2l.addWidget(lbl3)
        g2l.addLayout(btns2)
        layout.addWidget(group2)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        btn_folder = QPushButton("Open plugins folder")
        btn_folder.clicked.connect(self.open_folder)
        layout.addWidget(btn_folder)

    # ------------------------------------------------------------------
    def reload_table(self):
        self.tbl.setRowCount(0)
        for pl in self.plugin_rows():
            row = self.tbl.rowCount()
            self.tbl.insertRow(row)
            self.tbl.setItem(row, 0, QTableWidgetItem("Yes" if pl["enabled"] else "No"))
            self.tbl.setItem(row, 1, QTableWidgetItem(pl["name"]))
            self.tbl.setItem(row, 2, QTableWidgetItem(pl["version"]))
            self.tbl.setItem(row, 3, QTableWidgetItem(pl["url"]))

    def selected_names(self):
        rows = {idx.row() for idx in self.tbl.selectedIndexes()}
        names = []
        for row in sorted(rows):
            item = self.tbl.item(row, 1)
            if item:
                names.append(item.text())
        return names

    # ------------------------------------------------------------------
    # acoes
    # ------------------------------------------------------------------
    def enable_selected(self):
        names = self.selected_names()
        if not names:
            self.status.setText("Selecione um plugin na lista.")
            return
        for name in names:
            if name in self.state["disabled"]:
                self.state["disabled"].remove(name)
        self.save_state()
        self.reload_table()
        self.status.setText("Habilitados: " + ", ".join(names))

    def disable_selected(self):
        names = self.selected_names()
        if not names:
            self.status.setText("Selecione um plugin na lista.")
            return
        for name in names:
            if name not in self.state["disabled"]:
                self.state["disabled"].append(name)
        self.save_state()
        self.reload_table()
        self.status.setText("Desabilitados: " + ", ".join(names))

    def uninstall_selected(self):
        names = self.selected_names()
        if not names:
            self.status.setText("Selecione um plugin na lista.")
            return
        installed = self.installed_files()
        for name in names:
            file = installed.get(name)
            if file:
                try:
                    file.unlink()
                except Exception:
                    pass
            if name not in self.state["removed"]:
                self.state["removed"].append(name)
            if name in self.state["disabled"]:
                self.state["disabled"].remove(name)
        self.save_state()
        self.reload_table()
        self.status.setText("Removidos: " + ", ".join(names))

    def update_plugins(self):
        """Baixa novamente os plugins oficiais que ainda estao instalados."""
        installed = self.installed_files()
        updated = []
        failed = []
        for pl in OFFICIAL_PLUGINS:
            name = pl["name"]
            if name in self.state["removed"]:
                continue
            if name not in installed:
                continue
            try:
                resp = requests.get(pl["url"], timeout=20)
                if resp.status_code == 200:
                    (PLUGINS_DIR / f"{name}.py").write_bytes(resp.content)
                    updated.append(name)
                else:
                    failed.append(f"{name} (HTTP {resp.status_code})")
            except Exception as exc:
                failed.append(f"{name} ({exc})")
        self.reload_table()
        msg = "Atualizados: " + (", ".join(updated) if updated else "nenhum")
        if failed:
            msg += " | Falhas: " + ", ".join(failed)
        self.status.setText(msg)

    def install_local(self):
        path, _ = QFileDialog.getOpenFileName(self, "Instalar plugin", "",
                                              "Plugins Python (*.py)")
        if not path:
            return
        try:
            source = Path(path)
            target = PLUGINS_DIR / source.name
            shutil.copy2(source, target)
            name = source.stem
            self.state["removed"] = [n for n in self.state["removed"] if n != name]
            self.state["disabled"] = [n for n in self.state["disabled"] if n != name]
            self.add_custom(name, target.as_uri())
            self.save_state()
            self.reload_table()
            self.status.setText(f"Plugin instalado: {name}")
        except Exception as exc:
            QMessageBox.warning(self, "Erro", f"Falha ao instalar o plugin:\n{exc}")

    def install_url(self):
        url, ok = QInputDialog.getText(self, "Instalar plugin por URL",
                                       "URL do plugin (.py):")
        if not ok or not url.strip():
            return
        url = url.strip()
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}")
            name = url.rstrip("/").split("/")[-1]
            if not name.endswith(".py"):
                name += ".py"
            (PLUGINS_DIR / name).write_bytes(resp.content)
            stem = Path(name).stem
            self.state["removed"] = [n for n in self.state["removed"] if n != stem]
            self.add_custom(stem, url)
            self.save_state()
            self.reload_table()
            self.status.setText(f"Plugin instalado: {stem}")
        except Exception as exc:
            QMessageBox.warning(self, "Erro", f"Falha ao instalar o plugin:\n{exc}")

    def add_custom(self, name, url):
        for pl in self.state["custom"]:
            if pl.get("name") == name:
                pl["url"] = url
                return
        self.state["custom"].append({"name": name, "url": url, "version": "1.0"})

    def open_folder(self):
        try:
            os.makedirs(PLUGINS_DIR, exist_ok=True)
            webbrowser.open(f"file://{PLUGINS_DIR}")
        except Exception:
            try:
                os.makedirs(PLUGINS_DIR_ALT, exist_ok=True)
                webbrowser.open(f"file://{PLUGINS_DIR_ALT}")
            except Exception:
                pass
