import sys
from PyQt6.QtWidgets import QApplication
from ui.mainwindow import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("TorrentGuard AI")
    app.setStyle("Fusion")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
