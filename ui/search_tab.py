from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
                             QGroupBox, QMessageBox, QHeaderView, QComboBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from core.searcher import TorrentSearcher

class SearchWorker(QThread):
    finished = pyqtSignal(list, list)
    def __init__(self, query, mode):
        super().__init__()
        self.query = query
        self.mode = mode
        self.searcher = TorrentSearcher()
    def run(self):
        if self.mode == "Torrents (geral)":
            res = self.searcher.search_general(self.query)
        elif self.mode == "Buscar arquivos":
            res = self.searcher.search_files(self.query)
        else:
            res = []
        self.finished.emit(res, list(self.searcher.last_errors))

class GetMagnetWorker(QThread):
    finished = pyqtSignal(str)
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.searcher = TorrentSearcher()
    def run(self):
        m = self.searcher.get_magnet(self.url)
        self.finished.emit(m or "")

class SearchTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.searcher = TorrentSearcher()
        self.results = []
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        lbl = QLabel("Pesquisar direto no app")
        lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(lbl)

        top = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Digite nome do arquivo, filme, série, jogo, programa ou extensão...")
        self.tipo = QComboBox()
        self.tipo.addItems(["Torrents (geral)", "Buscar arquivos"])
        btn_search = QPushButton("Pesquisar")
        btn_search.clicked.connect(self.search)
        self.query.returnPressed.connect(self.search)
        top.addWidget(QLabel("Modo:"))
        top.addWidget(self.tipo)
        top.addWidget(self.query)
        top.addWidget(btn_search)
        layout.addLayout(top)

        group = QGroupBox("Resultados")
        gl = QVBoxLayout(group)
        self.tbl = QTableWidget(0, 6)
        self.tbl.setHorizontalHeaderLabels(["Nome", "Tamanho", "Seeds", "Leechers", "Fonte", "Link"])
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl.setColumnHidden(5, True)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        gl.addWidget(self.tbl)

        btns = QHBoxLayout()
        btn_add = QPushButton("Adicionar arquivo/torrent selecionado ao TorrentGuard (pausado)")
        btn_add.clicked.connect(self.get_magnet_add)
        btns.addWidget(btn_add)
        gl.addLayout(btns)
        layout.addWidget(group)

        self.status = QLabel("Use 'Buscar arquivos' para procurar por nome do arquivo e adicionar direto com magnet pronto.")
        layout.addWidget(self.status)

    def search(self):
        q = self.query.text().strip()
        if not q:
            QMessageBox.warning(self, "Aviso", "Digite algo para pesquisar")
            return
        mode = self.tipo.currentText()
        if mode == "Buscar arquivos":
            self.status.setText("Buscando arquivos direto no app (apibay + tpb)...")
        else:
            self.status.setText("Buscando torrents direto no app...")
        self.tbl.setRowCount(0)
        self.worker = SearchWorker(q, mode)
        self.worker.finished.connect(self.show_results)
        self.worker.start()

    def show_results(self, results, errors=None):
        self.results = results
        self.tbl.setRowCount(0)
        for r in results:
            row = self.tbl.rowCount()
            self.tbl.insertRow(row)
            self.tbl.setItem(row, 0, QTableWidgetItem(r['name']))
            self.tbl.setItem(row, 1, QTableWidgetItem(r['size']))
            self.tbl.setItem(row, 2, QTableWidgetItem(r['seeds']))
            self.tbl.setItem(row, 3, QTableWidgetItem(r['leeches']))
            self.tbl.setItem(row, 4, QTableWidgetItem(r['source']))
            self.tbl.setItem(row, 5, QTableWidgetItem(r['link']))
        mode = self.tipo.currentText()
        msg = f"{len(results)} resultado(s) com magnet pronto. Selecione e adicione direto." \
            if mode == "Buscar arquivos" else f"{len(results)} resultado(s) encontrados."
        if errors:
            msg += "\nFontes indisponiveis: " + " | ".join(errors)
        self.status.setText(msg)

    def get_magnet_add(self):
        r = self.tbl.currentRow()
        if r < 0:
            QMessageBox.warning(self, "Aviso", "Selecione um resultado da lista")
            return
        link = self.tbl.item(r, 5).text()
        nome = self.tbl.item(r, 0).text()
        if link.startswith('magnet:'):
            self.status.setText(f"Adicionando direto ao app: {nome[:60]}...")
            self.add_magnet_to_app(link)
            return
        self.status.setText(f"Obtendo magnet de: {nome[:60]}...")
        self.mw = GetMagnetWorker(link)
        self.mw.finished.connect(self.add_magnet_to_app)
        self.mw.start()

    def add_magnet_to_app(self, magnet):
        if not magnet or not magnet.startswith('magnet:'):
            QMessageBox.warning(self, "Erro", "Não foi possível obter o magnet link")
            self.status.setText("Falha ao obter magnet")
            return
        mw = self.parent()
        while mw and not hasattr(mw, 'magnet'):
            mw = mw.parent()
        if hasattr(mw, 'magnet') and hasattr(mw, 'btn_add_magnet'):
            mw.tabs.setCurrentIndex(0)
            mw.magnet.setText(magnet)
            mw.btn_add_magnet.click()
            QMessageBox.information(self, "Adicionado", "Adicionado ao TorrentGuard AI.\nAdicionado PAUSADO para análise com OpenCode antes de iniciar.")
            self.status.setText("Adicionado com sucesso na aba Torrents (pausado)")
        else:
            try:
                import pyperclip
                pyperclip.copy(magnet)
                QMessageBox.information(self, "Magnet copiado", "Magnet copiado para a área de transferência.")
            except Exception:
                QMessageBox.information(self, "Magnet", magnet)
