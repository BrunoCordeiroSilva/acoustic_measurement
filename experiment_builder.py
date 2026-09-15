"""Construção visual da aba Ensaio."""

import pyqtgraph as pg
from ui_constants import COHERENCE_COLOR, MOBILE_COLOR, REFERENCE_COLOR
from PySide6.QtCore import Qt
from PySide6.QtWidgets import *

def build_experiment_tab(window):

        main_layout = QVBoxLayout(
            window.experiment_tab
        )

        main_layout.setContentsMargins(
            5,
            5,
            5,
            5,
        )

        main_layout.setSpacing(5)

        # ====================================================
        # TOPO
        # ====================================================

        top_layout = QHBoxLayout()

        top_layout.setSpacing(8)

        # ====================================================
        # QUALIDADE
        # ====================================================

        quality_group = QGroupBox(
            "Qualidade da última medição"
        )

        quality_group.setMinimumWidth(300)

        quality_group.setMaximumWidth(380)

        quality_layout = QFormLayout(
            quality_group
        )

        quality_layout.setContentsMargins(
            8,
            8,
            8,
            8,
        )

        quality_layout.setVerticalSpacing(5)

        window.quality_status_label = QLabel("-")

        window.coherence_mean_label = QLabel("-")

        window.coherence_min_label = QLabel("-")

        window.valid_points_label = QLabel("-")

        window.clipping_label = QLabel("-")

        quality_layout.addRow(
            "Status:",
            window.quality_status_label,
        )

        quality_layout.addRow(
            "Coerência média:",
            window.coherence_mean_label,
        )

        quality_layout.addRow(
            "Coerência mínima:",
            window.coherence_min_label,
        )

        quality_layout.addRow(
            "Pontos válidos:",
            window.valid_points_label,
        )

        quality_layout.addRow(
            "Clipping:",
            window.clipping_label,
        )

        top_layout.addWidget(
            quality_group,
            stretch=1,
        )

        # ====================================================
        # DIREITA DO TOPO
        # ====================================================

        right_top_layout = QVBoxLayout()

        right_top_layout.setSpacing(5)

        # ====================================================
        # ETAPA ATUAL
        # ====================================================

        instruction_group = QGroupBox(
            "Etapa atual"
        )

        instruction_layout = QVBoxLayout(
            instruction_group
        )

        instruction_layout.setContentsMargins(
            8,
            6,
            8,
            6,
        )

        window.instruction_label = QLabel(
            "Configure o ensaio antes de iniciar."
        )

        window.instruction_label.setWordWrap(
            True
        )

        window.instruction_label.setAlignment(
            Qt.AlignCenter
        )

        window.instruction_label.setMinimumHeight(
            42
        )

        instruction_layout.addWidget(
            window.instruction_label
        )

        right_top_layout.addWidget(
            instruction_group
        )

        # ====================================================
        # STATUS
        # ====================================================

        status_group = QGroupBox()

        status_layout = QVBoxLayout(
            status_group
        )

        status_layout.setContentsMargins(
            6,
            4,
            6,
            4,
        )

        status_layout.setSpacing(3)

        window.status_label = QLabel(
            "AGUARDANDO"
        )

        window.status_label.setAlignment(
            Qt.AlignCenter
        )

        window._set_status_banner(
            "AGUARDANDO",
            "idle",
        )

        window.progress_bar = QProgressBar()

        window.progress_bar.setRange(
            0,
            100,
        )

        window.progress_bar.setValue(0)

        window.progress_bar.setMaximumHeight(
            22
        )

        status_layout.addWidget(
            window.status_label
        )

        status_layout.addWidget(
            window.progress_bar
        )

        right_top_layout.addWidget(
            status_group
        )

        top_layout.addLayout(
            right_top_layout,
            stretch=2,
        )

        main_layout.addLayout(
            top_layout
        )

        # ====================================================
        # ESPECTRO
        # ====================================================

        window.spectrum_plot = pg.PlotWidget()

        window.spectrum_plot.setLabel(
            "left",
            "Amplitude",
        )

        window.spectrum_plot.setLabel(
            "bottom",
            "Frequência",
            units="Hz",
        )

        window.spectrum_plot.showGrid(
            x=True,
            y=True,
        )

        window.spectrum_legend = (
            window.spectrum_plot.addLegend()
        )

        window.spectrum_legend.anchor(
            itemPos=(0, 1),
            parentPos=(0, 1),
            offset=(10, -10),
        )

        window.spectrum_reference_curve = (
            window.spectrum_plot.plot(
                [],
                [],
                name="Referência - P3",
                pen=pg.mkPen(
                    REFERENCE_COLOR,
                    width=2,
                ),
            )
        )

        window.spectrum_mobile_curve = (
            window.spectrum_plot.plot(
                [],
                [],
                name="Móvel",
                pen=pg.mkPen(
                    MOBILE_COLOR,
                    width=2,
                ),
            )
        )

        spectrum_panel = (
            window._create_plot_panel(
                title="Espectro",
                plot_widget=(
                    window.spectrum_plot
                ),
                fit_callback=(
                    window.fit_spectrum_plot
                ),
                popup_callback=(
                    window.open_spectrum_popup
                ),
            )
        )

        main_layout.addWidget(
            spectrum_panel,
            stretch=1,
        )

        # ====================================================
        # COERÊNCIA
        # ====================================================

        window.coherence_plot = pg.PlotWidget()

        window.coherence_plot.setLabel(
            "left",
            "Coerência",
        )

        window.coherence_plot.setLabel(
            "bottom",
            "Frequência",
            units="Hz",
        )

        window.coherence_plot.setYRange(
            0.0,
            1.05,
        )

        window.coherence_plot.showGrid(
            x=True,
            y=True,
        )

        window.coherence_curve = (
            window.coherence_plot.plot(
                [],
                [],
                pen=pg.mkPen(
                    COHERENCE_COLOR,
                    width=2,
                ),
            )
        )

        coherence_panel = (
            window._create_plot_panel(
                title="Coerência",
                plot_widget=(
                    window.coherence_plot
                ),
                fit_callback=(
                    window.fit_coherence_plot
                ),
                popup_callback=(
                    window.open_coherence_popup
                ),
            )
        )

        main_layout.addWidget(
            coherence_panel,
            stretch=1,
        )

        # ====================================================
        # BOTÕES DO ENSAIO
        # ====================================================

        buttons_layout = QHBoxLayout()

        buttons_layout.setSpacing(5)

        window.start_experiment_button = QPushButton(
            "Iniciar ensaio"
        )

        window.measure_button = QPushButton(
            "Medir"
        )

        window.cancel_button = QPushButton(
            "Cancelar"
        )

        window.repeat_button = QPushButton(
            "Repetir"
        )

        window.accept_button = QPushButton(
            "Aceitar"
        )

        window.accept_warning_button = QPushButton(
            "Aceitar com aviso"
        )

        window.confirm_load_button = QPushButton(
            "Confirmar troca de carga"
        )

        window.restart_button = QPushButton(
            "Refazer ensaio do começo"
        )

        buttons_layout.addWidget(
            window.start_experiment_button
        )

        buttons_layout.addWidget(
            window.measure_button
        )

        buttons_layout.addWidget(
            window.cancel_button
        )

        buttons_layout.addWidget(
            window.repeat_button
        )

        buttons_layout.addWidget(
            window.accept_button
        )

        buttons_layout.addWidget(
            window.accept_warning_button
        )

        buttons_layout.addWidget(
            window.confirm_load_button
        )

        buttons_layout.addStretch()

        buttons_layout.addWidget(
            window.restart_button
        )

        main_layout.addLayout(
            buttons_layout
        )

        # ====================================================
        # CONEXÕES
        # ====================================================

        window.start_experiment_button.clicked.connect(
            window.start_experiment
        )

        window.measure_button.clicked.connect(
            window.measure_current_step
        )

        window.cancel_button.clicked.connect(
            window.cancel_measurement
        )

        window.repeat_button.clicked.connect(
            window.repeat_measurement
        )

        window.accept_button.clicked.connect(
            window.accept_measurement
        )

        window.accept_warning_button.clicked.connect(
            window.accept_measurement_with_warning
        )

        window.confirm_load_button.clicked.connect(
            window.confirm_load_change
        )

        window.restart_button.clicked.connect(
            window.restart_experiment
        )

    # ========================================================
    # ABA RESULTADOS
    # ========================================================
