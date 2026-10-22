import os
import queue
import webbrowser
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit,
                             QLineEdit, QFileDialog, QMessageBox, QHeaderView, QApplication,
                             QMenu)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QEvent
from PyQt6.QtGui import QColor
from core.engine import TorrentEngine
from core.scanner import PreDownloadScanner
from core.config import cfg, DOWNLOADS_DIR
from core.lt_compat import has_metadata, torrent_info_of, torrent_name
from core.risk import (LEVEL_COLORS, LEVEL_LABELS, parse_verdict, summary_of,
                       worst)
from ai.opencode_guard import OpenCodeGuard
from ui.search_plugins_tab import SearchPluginsTab
from ui.search_tab import SearchTab
from core.security import SecurityManager
from core.firewall import TorrentFirewall


class AiWorker(QThread):
    """Fila de analises com o OpenCode (uma por vez, fora da thread da UI)."""

    #: (info hash, nome do torrent, parecer)
    result = pyqtSignal(str, str, str)
    #: (info hash, nome do torrent, mensagem de erro)
    failed = pyqtSignal(str, str, str)
    #: (info hash, nome do torrent, quantidade na fila)
    started = pyqtSignal(str, str, int)

    def __init__(self, guard, parent=None):
        super().__init__(parent)
        self.guard = guard
        self._queue = queue.Queue()
        self._stop = False

    # ------------------------------------------------------------------
    def submit(self, ih, name, files, report=None):
        """Enfileira uma analise."""
        self._queue.put((ih, name, files, report))
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
                ih, name, files, report = self._queue.get(timeout=0.4)
            except queue.Empty:
                continue
            self.started.emit(ih, name, self._queue.qsize())
            try:
                res = self.guard.analyze_torrent(name, files, report)
            except Exception as exc:
                self.failed.emit(ih, name, str(exc))
                continue
            if not res or not res.strip():
                res = ("Sem resposta do OpenCode.\n\n"
                       "Verifique se o CLI esta instalado e autenticado:\n"
                       "/usr/lib/opencode-desktop/opencode-cli run --model opencode/big-pickle \"teste\"")
            self.result.emit(ih, name, res)

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
        #: nivel de risco por torrent (info hash)
        self.risk = {}
        #: torrents que ja geraram aviso na tela
        self._warned = set()
        self._row_map = {}
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
        self.btn_remove.clicked.connect(lambda: self.remove_sel(False))
        self.btn_fw.clicked.connect(self.toggle_fw)
        top.addWidget(self.magnet); top.addWidget(self.btn_add_magnet); top.addWidget(self.btn_add_file)
        top.addWidget(self.btn_start); top.addWidget(self.btn_pause); top.addWidget(self.btn_remove); top.addWidget(self.btn_fw)
        layout.addLayout(top)

        self.tabs = QTabWidget()
        self.tbl = QTableWidget(0,7)
        self.tbl.setHorizontalHeaderLabels(["Nome","Tamanho","Status","Progresso","Vel.Up","Vel.Down","Risco"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tbl.customContextMenuRequested.connect(self.show_context_menu)
        self.tbl.installEventFilter(self)
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
            self.register_risk(ih, rep['risk'], rep['reasons'], source='scanner')
            self.logmsg("Arquivo carregado pausado")
            self.logmsg(f"Analise pre-download concluida: risco {rep['risk']} ({len(rep['files'])} arquivos)")
            self.ai_scan(ih, torrent_name(h, info), rep['files'], rep)
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
            self.register_risk(ih, rep['risk'], rep['reasons'], source='scanner')
            self.logmsg(f"Analise pre-download concluida: risco {rep['risk']} ({len(rep['files'])} arquivos)")
            self.ai_scan(ih, torrent_name(h, info), rep['files'], rep)
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

    # ------------------------------------------------------------------
    # risco
    # ------------------------------------------------------------------
    def register_risk(self, ih, level, reasons, source='scanner'):
        """Guarda (e combina) o nivel de risco de um torrent."""
        current = self.risk.get(ih) or {'level': 'LOW', 'reasons': [], 'source': ''}
        new_level = worst(current['level'], level)
        merged = list(current.get('reasons') or [])
        for reason in reasons or []:
            if reason not in merged:
                merged.append(reason)
        self.risk[ih] = {'level': new_level, 'reasons': merged, 'source': source}
        if new_level in ("MEDIUM", "HIGH"):
            self.logmsg(f"Risco {LEVEL_LABELS[new_level]}: {ih[:12]} ({source}) - "
                        + "; ".join(merged[:4]))
        return new_level

    def risk_level(self, ih):
        entry = self.risk.get(ih)
        return entry['level'] if entry else 'LOW'

    def confirm_start(self, ih):
        """Pede confirmacao antes de baixar um arquivo de risco."""
        entry = self.risk.get(ih)
        if not entry or entry['level'] == 'LOW':
            return True

        h = self.engine.torrents.get(ih) if self.engine else None
        nome = torrent_name(h) if h is not None else ih[:16]
        report = (self.pending.get(ih) or {}).get('report')
        details = summary_of(report)
        motivos = "\n".join(f"- {r}" for r in (entry.get('reasons') or []))

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Arquivo suspeito - risco " + LEVEL_LABELS[entry['level']])
        box.setText(f"'{nome}' foi classificado com risco "
                    f"{LEVEL_LABELS[entry['level']]}.\nDeseja baixar mesmo assim?")
        box.setInformativeText(motivos or "Nenhum motivo detalhado disponivel.")
        if details:
            box.setDetailedText(details)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        if box.exec() == QMessageBox.StandardButton.Yes:
            self.logmsg(f"Usuario confirmou o download de um arquivo de risco: {nome}")
            return True
        self.logmsg(f"Download cancelado pelo usuario (risco): {nome}")
        return False

    def warn_risk(self, ih, name, text):
        """Aviso na tela assim que a analise aponta risco alto."""
        if ih in self._warned:
            return
        self._warned.add(ih)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("Alerta de segurança")
        box.setText(f"A analise classificou '{name}' como PERIGOSO.\n"
                    f"Nao inicie o download sem ler o parecer.")
        box.setDetailedText(text)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    def ai_scan(self, ih, name, files, report=None):
        self.tabs.setCurrentIndex(1)
        if not files:
            self.sec_ai.setText("Nenhum arquivo para analisar.")
            return
        self.sec_ai.setText(f"Consultando OpenCode...\n\nTorrent: {name}\nArquivos: {len(files)}\nAguarde, isso pode levar alguns segundos.")
        self.sec_ai.repaint()
        self.ai_worker.submit(ih, name, files, report)

    def on_ai_started(self, ih, name, waiting):
        self.logmsg(f"Analisando com OpenCode: {name}" + (f" ({waiting} na fila)" if waiting else ""))
        if waiting:
            self.sec_ai.setText(f"Consultando OpenCode...\n\nTorrent: {name}\n"
                                f"{waiting} analise(s) na fila. Aguarde...")

    def on_ai_result(self, ih, name, text):
        self.sec_ai.setText(f"{text}\n\n--- Analisado: {name} ---")
        self.logmsg(f"Parecer do OpenCode recebido para: {name}")
        level, recommendation = parse_verdict(text)
        if level:
            self.register_risk(ih, level, [f"OpenCode: {recommendation}" if recommendation
                                           else f"OpenCode classificou como {level}"],
                               source='opencode')
            if level == "HIGH":
                self.warn_risk(ih, name, text)

    def on_ai_failed(self, ih, name, message):
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

    def current_ih(self):
        """Info hash do torrent selecionado (ou None)."""
        row = self.tbl.currentRow()
        if row < 0:
            return None
        item = self.tbl.item(row, 0)
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def start_sel(self):
        if not self.engine: return
        ih = self.current_ih()
        if not ih:
            self.logmsg("Selecione um torrent na lista")
            return
        if not self.confirm_start(ih):
            return
        self.engine.resume(ih); self.logmsg('Iniciado')

    def pause_sel(self):
        if not self.engine: return
        ih = self.current_ih()
        if not ih:
            self.logmsg("Selecione um torrent na lista")
            return
        self.engine.pause(ih); self.logmsg('Pausado')

    def remove_sel(self, delete_files=False):
        if not self.engine: return
        ih = self.current_ih()
        if not ih:
            self.logmsg("Selecione um torrent na lista")
            return
        h = self.engine.torrents.get(ih)
        nome = torrent_name(h) if h is not None else ih[:16]
        if delete_files:
            resp = QMessageBox.question(
                self, 'Remover e apagar',
                f"Remover '{nome}' e APAGAR os arquivos baixados do disco?")
            if resp != QMessageBox.StandardButton.Yes:
                return
        ok = self.engine.remove(ih, delete_files=delete_files)
        self.pending.pop(ih, None)
        self.risk.pop(ih, None)
        self._warned.discard(ih)
        if ok:
            self.logmsg(f"Removido e arquivos apagados: {nome}" if delete_files
                        else f"Removido (arquivos mantidos): {nome}")
        else:
            self.logmsg("Falha ao remover o torrent")
        # limpa a linha na hora, sem esperar o proximo refresh
        row = self.tbl.currentRow()
        if row >= 0:
            self.tbl.removeRow(row)
        self.tbl.clearSelection()

    def show_context_menu(self, pos):
        row = self.tbl.rowAt(pos.y())
        if row < 0:
            return
        self.tbl.selectRow(row)
        menu = QMenu(self)
        menu.addAction("Iniciar", self.start_sel)
        menu.addAction("Pausar", self.pause_sel)
        menu.addSeparator()
        menu.addAction("Remover (manter arquivos)", self.remove_sel)
        menu.addAction("Remover e apagar arquivos", lambda: self.remove_sel(True))
        menu.exec(self.tbl.viewport().mapToGlobal(pos))

    def refresh(self):
        """Atualiza a tabela sem recriar as linhas (preserva a selecao)."""
        if not self.engine:
            return
        alive = []
        for ih, h in list(self.engine.torrents.items()):
            try:
                if not h.is_valid():
                    continue
                alive.append((ih, h))
            except Exception:
                continue
        alive_ih = {ih for ih, _ in alive}

        # remove as linhas dos torrents que nao existem mais
        for row in range(self.tbl.rowCount() - 1, -1, -1):
            item = self.tbl.item(row, 0)
            ih = item.data(Qt.ItemDataRole.UserRole) if item else None
            if ih not in alive_ih:
                self.tbl.removeRow(row)

        # remapeia as linhas restantes
        self._row_map = {}
        for row in range(self.tbl.rowCount()):
            item = self.tbl.item(row, 0)
            ih = item.data(Qt.ItemDataRole.UserRole) if item else None
            if ih:
                self._row_map[ih] = row

        for ih, h in alive:
            row = self._row_map.get(ih)
            if row is None:
                row = self.tbl.rowCount()
                self.tbl.insertRow(row)
                self._row_map[ih] = row
                item = QTableWidgetItem("")
                item.setData(Qt.ItemDataRole.UserRole, ih)
                self.tbl.setItem(row, 0, item)
            self._update_row(row, ih, h)

    def eventFilter(self, obj, event):
        """Atalhos de teclado na tabela de torrents."""
        if obj is self.tbl and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self.remove_sel(False)
                return True
        return super().eventFilter(obj, event)

    def _update_row(self, row, ih, h):
        try:
            s = h.status()
            if has_metadata(h):
                name = torrent_name(h)
                if ih not in self.pending or not self.pending[ih].get('report'):
                    self.scan_pending(ih)
            else:
                name = ih[:16]
            # o item da coluna 0 guarda o info hash: atualiza so o texto
            item = self.tbl.item(row, 0)
            if item is None:
                item = QTableWidgetItem(name)
                item.setData(Qt.ItemDataRole.UserRole, ih)
                self.tbl.setItem(row, 0, item)
            else:
                item.setText(name)
            self._set_cell(row, 1, f"{s.total_wanted/1024/1024:.1f} MB")
            self._set_cell(row, 2, str(s.state))
            self._set_cell(row, 3, f"{s.progress*100:.1f}%")
            self._set_cell(row, 4, f"{s.upload_rate/1024:.1f} KB/s")
            self._set_cell(row, 5, f"{s.download_rate/1024:.1f} KB/s")
            self._update_risk_cell(row, ih, item)
        except Exception as e:
            self.logmsg(f"Erro ao atualizar torrent {ih[:12]}: {e}")

    def _update_risk_cell(self, row, ih, name_item):
        """Mostra o risco do torrent (coluna 'Risco' + cor do nome)."""
        level = self.risk_level(ih)
        label = LEVEL_LABELS.get(level, level)
        cell = self.tbl.item(row, 6)
        if cell is None:
            cell = QTableWidgetItem(label)
            self.tbl.setItem(row, 6, cell)
        elif cell.text() != label:
            cell.setText(label)
        cell.setForeground(QColor(LEVEL_COLORS.get(level, "#000000")))
        if name_item is not None:
            name_item.setForeground(QColor(LEVEL_COLORS.get(level, "#000000")))

    def _set_cell(self, row, col, text):
        item = self.tbl.item(row, col)
        if item is None:
            item = QTableWidgetItem(text)
            self.tbl.setItem(row, col, item)
        elif item.text() != text:
            item.setText(text)
