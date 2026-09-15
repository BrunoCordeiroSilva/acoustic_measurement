"""Construção dos painéis principais de espectro e coerência."""

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import *
from ui_constants import COHERENCE_COLOR, MOBILE_COLOR, REFERENCE_COLOR

def create_plot_panel(
    title: str,
    plot_widget: pg.PlotWidget,
    fit_callback,
    popup_callback=None,
) -> QWidget:

        panel = QWidget()

        layout = QVBoxLayout(panel)

        layout.setContentsMargins(
            2,
            2,
            2,
            2,
        )

        layout.setSpacing(2)

        header = QHBoxLayout()

        header.setContentsMargins(
            3,
            0,
            3,
            0,
        )

        header.setSpacing(4)

        title_label = QLabel(
            title
        )

        title_label.setStyleSheet(
            """
            QLabel {
                font-weight: bold;
                font-size: 12px;
            }
            """
        )

        header.addWidget(
            title_label
        )

        header.addStretch()

        # ====================================================
        # FIT
        # ====================================================

        fit_button = QPushButton(
            "Zoom to fit"
        )

        fit_button.setFixedHeight(24)

        fit_button.setFixedWidth(
            fit_button.sizeHint().width() + 8
        )

        fit_button.clicked.connect(
            fit_callback
        )

        header.addWidget(
            fit_button
        )

        # ====================================================
        # POP-UP
        # ====================================================

        if popup_callback is not None:

            popup_button = QPushButton(
                "Pop-up"
            )

            popup_button.setFixedHeight(24)

            popup_button.setMaximumWidth(75)

            popup_button.clicked.connect(
                popup_callback
            )

            header.addWidget(
                popup_button
            )

        layout.addLayout(
            header
        )

        plot_widget.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )

        layout.addWidget(
            plot_widget,
            stretch=1,
        )

        return panel

    # ========================================================
    # ABA ENSAIO TL
    # ========================================================
