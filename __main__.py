import sys

from PyQt5.QtWidgets import QApplication

from validate.gui.main_window import MainWindow
from validate.gui import theme


def main():
    app = QApplication(sys.argv)
    theme.apply(app)
    window = MainWindow()
    if len(sys.argv) > 1:
        window.setCohortDir(sys.argv[1])
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
