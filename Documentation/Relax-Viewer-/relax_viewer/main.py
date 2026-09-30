from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication

from .ui import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    
    # Se um arquivo for passado como argumento de linha de comando, abra-o
    if len(sys.argv) > 1:
        file_path = Path(sys.argv[1])
        if file_path.exists() and file_path.is_file():
            window.load_output(file_path)
            
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
