"""Widgets de gráfico reutilizáveis da aplicação."""

import pyqtgraph as pg

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
)


class PlotPopup(QDialog):
    """Janela auxiliar com gráfico e controle de ajuste automático."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1100, 750)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True)
        layout.addWidget(self.plot, stretch=1)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        fit_button = QPushButton("Zoom to fit")
        close_button = QPushButton("Fechar")
        fit_button.clicked.connect(self.fit)
        close_button.clicked.connect(self.close)
        button_layout.addWidget(fit_button)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)

    def fit(self):
        self.plot.getViewBox().autoRange()
