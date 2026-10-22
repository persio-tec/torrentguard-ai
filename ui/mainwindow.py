import os
import queue
import webbrowser
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit,
                             QLineEdit, QFileDialog, QMessageBox, QHeaderView, QApplication)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from core.engine import TorrentEngine
from core.scanner import PreDownloadScanner
from core.config import cfg, DOWNLOADS_DIR
from core.lt_compat import has_metadata, torrent_info_of, torrent_name
from ai.opencode_guard import OpenCodeGuard
from ui.search_plugins_tab import SearchPluginsTab
from ui.search_tab import SearchTab
from core.security import SecurityManager
from core.firewall import TorrentFirewall


class AiWorker(QThread):
    """Fila de analises com o OpenCode (uma por vez, fora da thread da UI)."""

    #: (nome do torrent, parecer)
    result = pyqtSignal(str, str)
    #: (nome do torrent, mensagem de erro)
    failed = pyqtSignal(str, str)
    #: (nome do torrent, quantidade na fila)
    started = pyqtSignal(str, int)

    def __init__(self, guard, parent=None):
        super().__init__(parent)
        self.guard = guard
        self._queue = queue.Queue()
        self._stop = False

    # ------------------------------------------------------------------
    def submit(self, name, files, report=None):
        """Enfileira uma analise."""
        self._queue.put((name, files, report))
        if not self.isRunning():
            self.start()

    def pending(self):
        return self._queue.qsize()

    def stop(self):
        self._stop = True

    def __del__(self):
        """Ultima linha de defesa: nao deixar a thread rodando no encerramento."""
        try:
            self._stop = True
            if self.isRunning():
                self.wait(2000)
                if self.isRunning():
                    self.terminate()
                    self.wait(500)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def run(self):
        while not self._stop:
            try:
                name, files, report = self._queue.get(timeout=0.4)
            except queue.Empty:
                continue
            self.started.emit(name, self._queue.qsize())
            try:
                res = self.guard.analyze_torrent(name, files, report)
            except Exception as exc:
                self.failed.emit(name, str(exc))
                continue
            if not res or not res.strip():
                res = ("Sem resposta do OpenCode.\n\n"
                       "Verifique se o CLI esta instalado e autenticado:\n"
                       "/usr/lib/opencode-desktop/opencode-cli run --model opencode/big-pickle \"teste\"")
            self.result.emit(name, res)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TorrentGuard AI - Seguro + OpenCode")
        self.setMinimumSize(1250, 780)
        try:
            self.engine = TorrentEngine()
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao iniciar engine:\n{e}")
            self.engine = None
        self.scanner = PreDownloadScanner()
        self.guard = OpenCodeGuard(
            model=cfg.get("opencode", "model", "big-pickle"),
            timeout=cfg.get("opencode", "timeout", 240))
        self.ai_worker = AiWorker(self.guard, self)
        self.ai_worker.result.connect(self.on_ai_result)
        self.ai_worker.failed.connect(self.on_ai_failed)
        self.ai_worker.started.connect(self.on_ai_started)
        self.sec = SecurityManager()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown_worker)
        self.fw = TorrentFirewall()
        self.pending = {}
        self.setup_ui()
        self.timer = QTimer(); self.timer.timeout.connect(self.refresh); self.timer.start(1000)

    def setup_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        top = QHBoxLayout()
        self.magnet = QLineEdit(); self.magnet.setPlaceholderText("Colar link magnet ou abrir arquivo .torrent")
        self.btn_add_magnet = QPushButton("Adicionar Magnet")
        self.btn_add_file = QPushButton("Abrir .torrent")
        self.btn_start = QPushButton("Iniciar")
        self.btn_pause = QPushButton("Pausar")
        self.btn_remove = QPushButton("Remover")
        self.btn_fw = QPushButton("Firewall: " + self.fw.status())
        self.btn_add_magnet.clicked.connect(self.add_magnet)
        self.btn_add_file.clicked.connect(self.add_file)
        self.btn_start.clicked.connect(self.start_sel)
        self.btn_pause.clicked.connect(self.pause_sel)
        self.btn_remove.clicked.connect(self.remove_sel)
        self.btn_fw.clicked.connect(self.toggle_fw)
        top.addWidget(self.magnet); top.addWidget(self.btn_add_magnet); top.addWidget(self.btn_add_file)
        top.addWidget(self.btn_start); top.addWidget(self.btn_pause); top.addWidget(self.btn_remove); top.addWidget(self.btn_fw)
        layout.addLayout(top)

        self.tabs = QTabWidget()
        self.tbl = QTableWidget(0,6)
        self.tbl.setHorizontalHeaderLabels(["Nome","Tamanho","Status","Progresso","Vel.Up","Vel.Down"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabs.addTab(self.tbl,"Torrents")

        sec = QWidget(); sv=QVBoxLayout(sec)
        self.sec_info = QTextEdit(); self.sec_info.setReadOnly(True)
        self.sec_ai = QTextEdit(); self.sec_ai.setReadOnly(True)
        self.sec_ai.setPlaceholderText("Análise do OpenCode aparecerá aqui...")
        sv.addWidget(QLabel("Relatório Pré-Download + Criptografia/E2E")); sv.addWidget(self.sec_info)
        sv.addWidget(QLabel("Análise com OpenCode AI")); sv.addWidget(self.sec_ai)
        self.tabs.addTab(sec,"Segurança & OpenCode")

        self.tabs.addTab(SearchTab(), "Pesquisar Torrents")
        self.tabs.addTab(SearchPluginsTab(), "Plugins de Busca")

        log = QWidget(); lv=QVBoxLayout(log)
        self.log = QTextEdit(); self.log.setReadOnly(True)
        lv.addWidget(self.log)
        self.tabs.addTab(log,"Log")
        layout.addWidget(self.tabs)

    def toggle_fw(self):
        if not self.fw.enabled:
            ok = self.fw.enable()
            self.logmsg("Firewall ativado" if ok else "Falha ao ativar firewall")
        else:
            ok = self.fw.disable()
            self.logmsg("Firewall desativado" if ok else "Falha ao desativar")
        self.btn_fw.setText("Firewall: " + self.fw.status())

    def logmsg(self,m): 
        from datetime import datetime
        self.log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {m}")

    def open_search_plugin(self, item):
        url = item.data(Qt.ItemDataRole.UserRole)
        if url: webbrowser.open(url)

    def open_search_plugin_selected(self):
        item = self.search_list.currentItem()
        if item:
            url = item.data(Qt.ItemDataRole.UserRole)
            if url: webbrowser.open(url)

    def add_magnet(self):
        if not self.engine: return
        m = self.magnet.text().strip()
        if not m.startswith('magnet:'): 
            QMessageBox.warning(self,'Erro','Link magnet inválido'); return
        try:
            ih,h = self.engine.add_magnet(m, str(DOWNLOADS_DIR), paused=True)
            self.pending[ih] = {'handle':h,'type':'magnet','magnet':m}
            self.logmsg(f"Adicionado pausado")
            self.scan_pending(ih)
        except Exception as e:
            QMessageBox.critical(self,'Erro',str(e))

    def add_file(self):
        if not self.engine: return
        path,_ = QFileDialog.getOpenFileName(self,'Abrir .torrent','','Arquivos Torrent (*.torrent)')
        if not path: return
        try:
            ih,h,info = self.engine.add_torrent_file(path,str(DOWNLOADS_DIR),paused=True)
            rep = self.scanner.analyze_info(info)
            self.pending[ih] = {'handle':h,'type':'file','info':info,'report':rep}
            self.show_report(rep)
            self.logmsg("Arquivo carregado pausado")
            self.logmsg(f"Analise pre-download concluida: risco {rep['risk']} ({len(rep['files'])} arquivos)")
            self.ai_scan(torrent_name(h, info), rep['files'], rep)
        except Exception as e:
            QMessageBox.critical(self,'Erro',str(e))

    def scan_pending(self,ih):
        try:
            h = self.pending[ih]['handle']
            if not has_metadata(h): 
                if not self.pending[ih].get('waiting_logged'):
                    self.pending[ih]['waiting_logged'] = True
                    self.logmsg("Aguardando metadados do torrent...")
                return
            info = torrent_info_of(h)
            if info is None:
                self.logmsg("Metadados indisponiveis para analise")
                return
            rep = self.scanner.analyze_info(info)
            if not rep['files']:
                self.logmsg("Torrent sem arquivos para analisar")
                return
            self.pending[ih]['info']=info; self.pending[ih]['report']=rep
            self.show_report(rep)
            self.logmsg(f"Analise pre-download concluida: risco {rep['risk']} ({len(rep['files'])} arquivos)")
            self.ai_scan(torrent_name(h, info), rep['files'], rep)
        except Exception as e:
            self.logmsg(f"Falha ao analisar torrent: {e}")
            self.show_report_error(str(e))

    def show_report(self,rep):
        txt = f"RISCO: {rep['risk']} | SCORE: {rep['score']}\n\nMOTIVOS:\n"
        for r in rep['reasons'] or ['Nenhum óbvio']: txt += f"- {r}\n"
        if rep['blocked_ext']: txt += f"\nExecutáveis: {', '.join(rep['blocked_ext'])}\n"
        txt += f"\nArquivos analisados: {len(rep['files'])}\n"
        self.sec_info.setText(txt)

    def show_report_error(self, message):
        self.sec_info.setText(f"Falha na analise pre-download:\n{message}")

    def ai_scan(self,name,files,report=None):
        self.tabs.setCurrentIndex(1)
        if not files:
            self.sec_ai.setText("Nenhum arquivo para analisar.")
            return
        self.sec_ai.setText(f"Consultando OpenCode...\n\nTorrent: {name}\nArquivos: {len(files)}\nAguarde, isso pode levar alguns segundos.")
        self.sec_ai.repaint()
        self.ai_worker.submit(name, files, report)

    def on_ai_started(self, name, waiting):
        self.logmsg(f"Analisando com OpenCode: {name}" + (f" ({waiting} na fila)" if waiting else ""))
        if waiting:
            self.sec_ai.setText(f"Consultando OpenCode...\n\nTorrent: {name}\n"
                                f"{waiting} analise(s) na fila. Aguarde...")

    def on_ai_result(self, name, text):
        self.sec_ai.setText(f"{text}\n\n--- Analisado: {name} ---")
        self.logmsg(f"Parecer do OpenCode recebido para: {name}")

    def on_ai_failed(self, name, message):
        self.sec_ai.setText(f"Erro ao chamar OpenCode:\n{message}")
        self.logmsg(f"Erro na analise OpenCode ({name}): {message}")

    def shutdown_worker(self):
        """Encerra a thread do OpenCode (evita crash ao sair)."""
        worker = getattr(self, "ai_worker", None)
        if worker is None or not worker.isRunning():
            return
        worker.stop()
        worker.wait(3000)
        if worker.isRunning():
            worker.terminate()
            worker.wait(1000)

    def closeEvent(self, event):
        """Nao deixa a thread do OpenCode morrer com a janela (evita crash)."""
        self.shutdown_worker()
        super().closeEvent(event)

    def start_sel(self):
        if not self.engine: return
        r = self.tbl.currentRow()
        if r<0: return
        ih = self.tbl.item(r,0).data(Qt.ItemDataRole.UserRole)
        if ih in self.pending and self.pending[ih].get('report'):
            rep = self.pending[ih]['report']
            if rep['risk']=='HIGH':
                if QMessageBox.question(self,'ALTO RISCO','Classificado como ALTO RISCO.\nIniciar mesmo assim?') != QMessageBox.StandardButton.Yes: return
        self.engine.resume(ih); self.logmsg('Iniciado')

    def pause_sel(self):
        if not self.engine: return
        r=self.tbl.currentRow()
        if r<0:return
        ih=self.tbl.item(r,0).data(Qt.ItemDataRole.UserRole)
        self.engine.pause(ih); self.logmsg('Pausado')

    def remove_sel(self):
        if not self.engine: return
        r=self.tbl.currentRow()
        if r<0:return
        ih=self.tbl.item(r,0).data(Qt.ItemDataRole.UserRole)
        self.engine.remove(ih); self.pending.pop(ih,None); self.tbl.removeRow(r)

    def refresh(self):
        if not self.engine: return
        self.tbl.setRowCount(0)
        for ih,h in list(self.engine.torrents.items()):
            try:
                if not h.is_valid(): continue
                s=h.status()
                if has_metadata(h):
                    name = torrent_name(h)
                    if ih not in self.pending or not self.pending[ih].get('report'):
                        self.scan_pending(ih)
                else:
                    name = ih[:16]
                row=self.tbl.rowCount(); self.tbl.insertRow(row)
                it=QTableWidgetItem(name); it.setData(Qt.ItemDataRole.UserRole,ih); self.tbl.setItem(row,0,it)
                self.tbl.setItem(row,1,QTableWidgetItem(f"{s.total_wanted/1024/1024:.1f} MB"))
                self.tbl.setItem(row,2,QTableWidgetItem(str(s.state)))
                self.tbl.setItem(row,3,QTableWidgetItem(f"{s.progress*100:.1f}%"))
                self.tbl.setItem(row,4,QTableWidgetItem(f"{s.upload_rate/1024:.1f} KB/s"))
                self.tbl.setItem(row,5,QTableWidgetItem(f"{s.download_rate/1024:.1f} KB/s"))
            except Exception as e:
                self.logmsg(f"Erro ao atualizar torrent {ih[:12]}: {e}")
