import sys
from PyQt6.QtWidgets import QApplication
from ui.mainwindow import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("TorrentGuard AI")
    app.setStyle("Fusion")
    w = MainWindow()
    w.show()
    code = app.exec()
    # garante o encerramento limpo da thread do OpenCode
    w.close()
    return code

if __name__ == "__main__":
    sys.exit(main())
