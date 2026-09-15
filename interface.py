from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyqtgraph as pg

from PySide6.QtCore import (
    Qt,
    QThread,
    QTimer,
    QSignalBlocker,
)

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QLineEdit,
    QTextEdit,
    QProgressBar,
    QTabWidget,
    QMessageBox,
    QFileDialog,
    QSizePolicy,
    QDialog,
    QScrollArea,
)

from config import (
    AppConfig,
    ChannelConfig,
    SensorType,
    WindowType,
)

from daq import (
    NIDaqDevice,
    DAQError,
)

from acquisition_controller import (
    AcquisitionController,
    MeasurementQualityStatus,
    FRFMeasurementResult,
)

from acquisition_worker import (
    MeasurementWorker,
    MonitoringWorker,
    MonitoringData,
)

from experiments.transmission_loss import (
    TransmissionLossExperiment,
    TransmissionLossError,
    TLExperimentState,
    TLMeasurementStep,
    StoredTLMeasurement,
    MeasurementAcceptance,
)

from signal_processing import FRFResult

from exporter import (
    DataExporter,
    ExportError,
)


# ============================================================
# CORES
# ============================================================

REFERENCE_COLOR = "#00C853"
MOBILE_COLOR = "#2979FF"
COHERENCE_COLOR = "#FFB300"


# ============================================================
# POP-UP GENÉRICO DE GRÁFICO
# ============================================================

class PlotPopup(QDialog):

    def __init__(
        self,
        title: str,
        parent=None,
    ):

        super().__init__(parent)

        self.setWindowTitle(title)

        self.resize(
            1100,
            750,
        )

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            6,
            6,
            6,
            6,
        )

        layout.setSpacing(5)

        # ====================================================
        # GRÁFICO
        # ====================================================

        self.plot = pg.PlotWidget()

        self.plot.showGrid(
            x=True,
            y=True,
        )

        layout.addWidget(
            self.plot,
            stretch=1,
        )

        # ====================================================
        # BOTÕES
        # ====================================================

        button_layout = QHBoxLayout()

        button_layout.addStretch()

        self.fit_button = QPushButton(
            "Zoom to fit"
        )

        self.close_button = QPushButton(
            "Fechar"
        )

        self.fit_button.clicked.connect(
            self.fit
        )

        self.close_button.clicked.connect(
            self.close
        )

        button_layout.addWidget(
            self.fit_button
        )

        button_layout.addWidget(
            self.close_button
        )

        layout.addLayout(
            button_layout
        )

    # ========================================================

    def fit(self):

        self.plot.getViewBox().autoRange()


# ============================================================
# JANELA PRINCIPAL
# ============================================================

class MainWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        # ====================================================
        # CONFIGURAÇÃO
        # ====================================================

        self.config = AppConfig()

        # ====================================================
        # DAQ
        # ====================================================

        self.daq = NIDaqDevice()

        # ====================================================
        # CONTROLADOR
        # ====================================================

        self.controller = AcquisitionController(
            daq=self.daq,
            config=self.config,
        )

        # ====================================================
        # EXPERIMENTO
        # ====================================================

        self.experiment = TransmissionLossExperiment(
            controller=self.controller,
            config=self.config,
        )

        # ====================================================
        # RESULTADOS
        # ====================================================

        self.last_measurement = None

        self.last_monitoring_data = None

        # Antes da primeira medição oficial, a coerência vem do
        # monitor. Depois, ela representa a última FRF medida.
        self.coherence_frozen_to_measurement = False

        self.displayed_measurement_frf = None

        self.tl_result = None

        # ====================================================
        # MEDIÇÃO OFICIAL
        # ====================================================

        self.measurement_thread = None

        self.measurement_worker = None

        self.measurement_in_progress = False

        # ====================================================
        # MONITORAMENTO
        # ====================================================

        self.monitoring_thread = None

        self.monitoring_worker = None

        self.monitoring_running = False

        self.monitoring_stop_requested = False

        # Desenha no máximo 12,5 vezes por segundo, sempre com
        # o pacote mais recente produzido pelo monitoramento.
        self.monitor_update_timer = QTimer(self)

        self.monitor_update_timer.setInterval(80)

        self.monitor_update_timer.timeout.connect(
            self._flush_monitoring_data
        )

        # Indica que o usuário clicou em Medir
        # enquanto o monitor ainda estava ativo.
        self.measurement_waiting_for_monitor = False

        # ====================================================
        # POP-UPS
        # ====================================================

        self.time_popup = None

        self.spectrum_popup = None

        self.coherence_popup = None

        # ====================================================
        # JANELA
        # ====================================================

        self.setWindowTitle(
            "Sistema de Medição Acústica"
        )

        self.resize(
            1500,
            950,
        )

        # ====================================================
        # CENTRAL
        # ====================================================

        central_widget = QWidget()

        self.setCentralWidget(
            central_widget
        )

        main_layout = QVBoxLayout(
            central_widget
        )

        main_layout.setContentsMargins(
            4,
            4,
            4,
            4,
        )

        # ====================================================
        # ABAS
        # ====================================================

        self.tabs = QTabWidget()

        # O conteúdo mais largo das demais abas não deve impor uma largura
        # mínima à janela inteira. Isso permite que a aba de configuração
        # se adapte à tela e use sua área de rolagem quando necessário.
        self.tabs.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Ignored,
        )

        main_layout.addWidget(
            self.tabs
        )

        self.config_tab = QWidget()

        self.experiment_tab = QWidget()

        self.results_tab = QWidget()

        self.tabs.addTab(
            self.config_tab,
            "Configuração",
        )

        self.tabs.addTab(
            self.experiment_tab,
            "Ensaio TL",
        )

        self.tabs.addTab(
            self.results_tab,
            "Resultados",
        )

        # ====================================================
        # CONSTRUÇÃO
        # ====================================================

        self._build_config_tab()

        self._build_experiment_tab()

        self._build_results_tab()

        self._update_controls()

    # ========================================================
    # ABA CONFIGURAÇÃO
    # ========================================================

    def _build_config_tab(self):

        # Em telas menores a configuração pode exceder a área visível.
        # A rolagem preserva os grupos e a ordem atuais, sem ocultar
        # campos de preenchimento ou botões.
        tab_layout = QVBoxLayout(self.config_tab)

        tab_layout.setContentsMargins(0, 0, 0, 0)

        configuration_scroll = QScrollArea()

        configuration_scroll.setWidgetResizable(True)

        configuration_content = QWidget()

        main_layout = QVBoxLayout(configuration_content)

        main_layout.setContentsMargins(8, 8, 8, 8)

        main_layout.setSpacing(8)

        configuration_scroll.setWidget(configuration_content)

        tab_layout.addWidget(configuration_scroll)

        # ====================================================
        # GRID
        # ====================================================

        config_grid = QGridLayout()

        config_grid.setHorizontalSpacing(12)

        config_grid.setVerticalSpacing(10)

        config_grid.setColumnStretch(
            0,
            1,
        )

        config_grid.setColumnStretch(
            1,
            1,
        )

        def configure_responsive_form(form: QFormLayout) -> None:
            """Evita que rótulos longos comprimam os campos editáveis."""

            form.setFieldGrowthPolicy(
                QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
            )

            form.setRowWrapPolicy(
                QFormLayout.RowWrapPolicy.WrapLongRows
            )

        # ====================================================
        # DISPOSITIVO
        # ====================================================

        daq_group = QGroupBox(
            "Dispositivo"
        )

        daq_layout = QGridLayout(
            daq_group
        )

        self.device_combo = QComboBox()

        self.device_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self.refresh_daq_button = QPushButton(
            "Detectar DAQ"
        )

        self.refresh_daq_button.clicked.connect(
            self.refresh_devices
        )

        daq_layout.addWidget(
            QLabel("Dispositivo:"),
            0,
            0,
        )

        daq_layout.addWidget(
            self.device_combo,
            0,
            1,
        )

        daq_layout.addWidget(
            self.refresh_daq_button,
            0,
            2,
        )

        daq_layout.setColumnStretch(1, 1)

        config_grid.addWidget(
            daq_group,
            0,
            0,
        )

        # ====================================================
        # CONDIÇÕES ACÚSTICAS
        # ====================================================

        acoustic_group = QGroupBox(
            "Condições Acústicas"
        )

        acoustic_form = QFormLayout(
            acoustic_group
        )

        configure_responsive_form(acoustic_form)

        self.temperature_input = QDoubleSpinBox()

        self.temperature_input.setRange(
            -20.0,
            60.0,
        )

        self.temperature_input.setDecimals(2)

        self.temperature_input.setValue(
            self.config.acoustics.temperature_c
        )

        self.temperature_input.setSuffix(
            " °C"
        )

        self.sound_speed_label = QLabel()

        acoustic_form.addRow(
            "Temperatura:",
            self.temperature_input,
        )

        acoustic_form.addRow(
            "Velocidade do som:",
            self.sound_speed_label,
        )

        config_grid.addWidget(
            acoustic_group,
            0,
            1,
        )

        # ====================================================
        # MICROFONES
        # ====================================================

        microphone_group = QGroupBox(
            "Microfones"
        )

        microphone_layout = QGridLayout(
            microphone_group
        )

        microphone_layout.setContentsMargins(
            8,
            6,
            8,
            6,
        )

        microphone_layout.setVerticalSpacing(
            3
        )

        # Não limita a altura: em telas estreitas os rótulos podem
        # quebrar em mais de uma linha sem sobrepor os campos.
        microphone_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        self.reference_channel_combo = QComboBox()

        self.mobile_channel_combo = QComboBox()

        for combo in (
            self.reference_channel_combo,
            self.mobile_channel_combo,
        ):

            combo.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )

        self.reference_sensitivity_input = (
            QDoubleSpinBox()
        )

        self.mobile_sensitivity_input = (
            QDoubleSpinBox()
        )

        for spinbox in (
            self.reference_sensitivity_input,
            self.mobile_sensitivity_input,
        ):

            spinbox.setRange(
                0.001,
                1000.0,
            )

            spinbox.setDecimals(4)

            spinbox.setValue(50.0)

            spinbox.setSuffix(
                " mV/Pa"
            )

            spinbox.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )

        reference_microphone_label = QLabel(
            "Referência - P3"
        )

        reference_microphone_label.setWordWrap(True)

        microphone_layout.addWidget(
            QLabel(""),
            0,
            0,
        )

        microphone_layout.addWidget(
            QLabel("Canal"),
            0,
            1,
        )

        microphone_layout.addWidget(
            QLabel("Sensibilidade"),
            0,
            2,
        )

        microphone_layout.addWidget(
            reference_microphone_label,
            1,
            0,
        )

        microphone_layout.addWidget(
            self.reference_channel_combo,
            1,
            1,
        )

        microphone_layout.addWidget(
            self.reference_sensitivity_input,
            1,
            2,
        )

        microphone_layout.addWidget(
            QLabel("Móvel"),
            2,
            0,
        )

        microphone_layout.addWidget(
            self.mobile_channel_combo,
            2,
            1,
        )

        microphone_layout.addWidget(
            self.mobile_sensitivity_input,
            2,
            2,
        )

        microphone_layout.setColumnStretch(1, 1)
        microphone_layout.setColumnStretch(2, 1)

        config_grid.addWidget(
            microphone_group,
            1,
            0,
        )

        # ====================================================
        # GEOMETRIA
        # ====================================================

        geometry_group = QGroupBox(
            "Geometria do ensaio"
        )

        geometry_form = QFormLayout(
            geometry_group
        )

        configure_responsive_form(geometry_form)

        self.diameter_input = QDoubleSpinBox()

        self.spacing12_input = QDoubleSpinBox()

        self.spacing34_input = QDoubleSpinBox()

        for spinbox in (
            self.diameter_input,
            self.spacing12_input,
            self.spacing34_input,
        ):

            spinbox.setRange(
                0.1,
                1000.0,
            )

            spinbox.setDecimals(2)

            spinbox.setSuffix(
                " mm"
            )

        self.diameter_input.setValue(
            self.config
            .transmission_loss
            .tube_diameter
            * 1000.0
        )

        self.spacing12_input.setValue(
            self.config
            .transmission_loss
            .spacing_12
            * 1000.0
        )

        self.spacing34_input.setValue(
            self.config
            .transmission_loss
            .spacing_34
            * 1000.0
        )

        self.auto_range_checkbox = QCheckBox(
            "Calcular automaticamente"
        )

        self.auto_range_checkbox.setChecked(
            self.config
            .transmission_loss
            .automatic_valid_frequency_range
        )

        self.valid_range_label = QLabel(
            "-"
        )

        geometry_form.addRow(
            "Diâmetro interno:",
            self.diameter_input,
        )

        geometry_form.addRow(
            "Distância 1-2:",
            self.spacing12_input,
        )

        geometry_form.addRow(
            "Distância 3-4:",
            self.spacing34_input,
        )

        geometry_form.addRow(
            "Faixa válida:",
            self.auto_range_checkbox,
        )

        geometry_form.addRow(
            "Resultado:",
            self.valid_range_label,
        )

        config_grid.addWidget(
            geometry_group,
            1,
            1,
        )

        # ====================================================
        # AQUISIÇÃO
        # ====================================================

        acquisition_group = QGroupBox(
            "Aquisição"
        )

        acquisition_form = QFormLayout(
            acquisition_group
        )

        configure_responsive_form(acquisition_form)

        self.sample_rate_input = QDoubleSpinBox()

        self.sample_rate_input.setRange(
            100.0,
            51200.0,
        )

        self.sample_rate_input.setDecimals(2)

        self.sample_rate_input.setValue(
            self.config
            .acquisition
            .sample_rate
        )

        self.sample_rate_input.setSuffix(
            " Hz"
        )

        self.num_samples_input = QSpinBox()

        self.num_samples_input.setRange(
            128,
            1_000_000,
        )

        self.num_samples_input.setValue(
            self.config
            .acquisition
            .num_samples
        )

        self.num_averages_input = QSpinBox()

        self.num_averages_input.setRange(
            1,
            1000,
        )

        self.num_averages_input.setValue(
            self.config
            .acquisition
            .num_averages
        )

        self.stabilization_input = (
            QDoubleSpinBox()
        )

        self.stabilization_input.setRange(
            0.0,
            60.0,
        )

        self.stabilization_input.setDecimals(2)

        self.stabilization_input.setValue(
            self.config
            .acquisition
            .stabilization_time
        )

        self.stabilization_input.setSuffix(
            " s"
        )

        self.window_combo = QComboBox()

        for window in WindowType:

            self.window_combo.addItem(
                window.value,
                window,
            )

        self.duration_label = QLabel()

        self.df_label = QLabel()

        self.nyquist_label = QLabel()

        self.coherence_min_input = QDoubleSpinBox()

        self.coherence_mean_input = QDoubleSpinBox()

        for spinbox in (
            self.coherence_min_input,
            self.coherence_mean_input,
        ):

            spinbox.setRange(
                0.0,
                1.0,
            )

            spinbox.setDecimals(
                3
            )

            spinbox.setSingleStep(
                0.01
            )

        self.coherence_min_input.setValue(
            self.config.quality.coherence_threshold
        )

        self.coherence_mean_input.setValue(
            self.config.quality.coherence_mean_threshold
        )

        self.coherence_guidance_label = QLabel(
            "Orientação inicial: média ≥ 0,90 e mínima ≥ 0,80. "
            "Ajuste conforme a norma, banda e excitação usadas."
        )

        self.coherence_guidance_label.setWordWrap(
            True
        )

        self.coherence_guidance_label.setStyleSheet(
            "color: #666666;"
        )

        acquisition_form.addRow(
            "Fs:",
            self.sample_rate_input,
        )

        acquisition_form.addRow(
            "N:",
            self.num_samples_input,
        )

        acquisition_form.addRow(
            "Número de médias:",
            self.num_averages_input,
        )

        acquisition_form.addRow(
            "Janela:",
            self.window_combo,
        )

        acquisition_form.addRow(
            "Estabilização:",
            self.stabilization_input,
        )

        acquisition_form.addRow(
            "Duração do bloco:",
            self.duration_label,
        )

        acquisition_form.addRow(
            "Resolução Δf:",
            self.df_label,
        )

        acquisition_form.addRow(
            "Nyquist:",
            self.nyquist_label,
        )

        acquisition_form.addRow(
            "Coerência mínima aceita:",
            self.coherence_min_input,
        )

        acquisition_form.addRow(
            "Coerência média aceita:",
            self.coherence_mean_input,
        )

        acquisition_form.addRow(
            "Recomendação:",
            self.coherence_guidance_label,
        )

        config_grid.addWidget(
            acquisition_group,
            2,
            0,
        )

        # ====================================================
        # IDENTIFICAÇÃO
        # ====================================================

        metadata_group = QGroupBox(
            "Identificação do Ensaio"
        )

        metadata_form = QFormLayout(
            metadata_group
        )

        configure_responsive_form(metadata_form)

        self.experiment_name_input = QLineEdit()

        self.experiment_number_input = QLineEdit()

        self.operator_input = QLineEdit()

        self.notes_input = QTextEdit()

        self.notes_input.setMaximumHeight(
            90
        )

        metadata_form.addRow(
            "Nome:",
            self.experiment_name_input,
        )

        metadata_form.addRow(
            "Número:",
            self.experiment_number_input,
        )

        metadata_form.addRow(
            "Operador:",
            self.operator_input,
        )

        metadata_form.addRow(
            "Observações:",
            self.notes_input,
        )

        config_grid.addWidget(
            metadata_group,
            2,
            1,
        )

        # Em largura normal, os grupos permanecem em duas colunas. Abaixo
        # desse limite, eles passam temporariamente a uma coluna, evitando
        # que os campos de cada grupo sejam estreitados ou cortados.
        self.config_grid = config_grid

        self.config_groups = (
            daq_group,
            acoustic_group,
            microphone_group,
            geometry_group,
            acquisition_group,
            metadata_group,
        )

        self.config_grid_is_compact = None

        main_layout.addLayout(
            config_grid
        )

        # ====================================================
        # SALVAMENTO
        # ====================================================

        save_group = QGroupBox(
            "Salvamento"
        )

        save_layout = QHBoxLayout(
            save_group
        )

        self.output_directory_input = QLineEdit()

        self.output_directory_button = QPushButton(
            "Procurar..."
        )

        self.output_directory_button.clicked.connect(
            self.browse_output_directory
        )

        save_layout.addWidget(
            QLabel("Diretório:")
        )

        save_layout.addWidget(
            self.output_directory_input,
            stretch=1,
        )

        save_layout.addWidget(
            self.output_directory_button
        )

        main_layout.addWidget(
            save_group
        )

        # ====================================================
        # APLICAR
        # ====================================================

        self.apply_config_button = QPushButton(
            "Aplicar configuração"
        )

        self.apply_config_button.clicked.connect(
            lambda:
                self.apply_configuration(
                    show_message=True
                )
        )

        main_layout.addWidget(
            self.apply_config_button
        )

        main_layout.addStretch()

        # ====================================================
        # SIGNALS
        # ====================================================

        self.sample_rate_input.valueChanged.connect(
            self._update_acquisition_labels
        )

        self.num_samples_input.valueChanged.connect(
            self._update_acquisition_labels
        )

        self.temperature_input.valueChanged.connect(
            self._update_acoustic_labels
        )

        self.diameter_input.valueChanged.connect(
            self._update_valid_range_preview
        )

        self.spacing12_input.valueChanged.connect(
            self._update_valid_range_preview
        )

        self.spacing34_input.valueChanged.connect(
            self._update_valid_range_preview
        )

        # Cada dispositivo possui seus próprios canais físicos. Sem esta
        # conexão, os combos de referência e móvel continuavam mostrando os
        # canais do primeiro dispositivo detectado.
        self.device_combo.currentTextChanged.connect(
            self._device_selection_changed
        )

        # ====================================================
        # LABELS INICIAIS
        # ====================================================

        self._update_acquisition_labels()

        self._update_acoustic_labels()

        self._update_valid_range_preview()

        self._update_config_grid_layout()

        # A largura definitiva da aba só existe após o primeiro ciclo de
        # layout da janela; então reavaliamos a disposição nesse momento.
        QTimer.singleShot(
            0,
            self._update_config_grid_layout,
        )

    # ========================================================
    # LAYOUT RESPONSIVO DA CONFIGURAÇÃO
    # ========================================================

    def _update_config_grid_layout(self) -> None:
        """Alterna os grupos entre duas e uma coluna conforme a largura."""

        if not hasattr(self, "config_grid"):

            return

        compact = self.config_tab.width() < 900

        if compact == self.config_grid_is_compact:

            return

        for group in self.config_groups:

            self.config_grid.removeWidget(group)

        if compact:

            for row, group in enumerate(self.config_groups):

                self.config_grid.addWidget(
                    group,
                    row,
                    0,
                    1,
                    2,
                )

            self.config_grid.setColumnStretch(0, 1)
            self.config_grid.setColumnStretch(1, 0)

        else:

            for index, group in enumerate(self.config_groups):

                self.config_grid.addWidget(
                    group,
                    index // 2,
                    index % 2,
                )

            self.config_grid.setColumnStretch(0, 1)
            self.config_grid.setColumnStretch(1, 1)

        self.config_grid_is_compact = compact

    # ========================================================

    def resizeEvent(self, event):

        super().resizeEvent(event)

        self._update_config_grid_layout()

    # ========================================================
    # PAINEL DOS GRÁFICOS
    # ========================================================

    def _create_plot_panel(
        self,
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

    def _build_experiment_tab(self):

        main_layout = QVBoxLayout(
            self.experiment_tab
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

        self.quality_status_label = QLabel("-")

        self.coherence_mean_label = QLabel("-")

        self.coherence_min_label = QLabel("-")

        self.valid_points_label = QLabel("-")

        self.clipping_label = QLabel("-")

        quality_layout.addRow(
            "Status:",
            self.quality_status_label,
        )

        quality_layout.addRow(
            "Coerência média:",
            self.coherence_mean_label,
        )

        quality_layout.addRow(
            "Coerência mínima:",
            self.coherence_min_label,
        )

        quality_layout.addRow(
            "Pontos válidos:",
            self.valid_points_label,
        )

        quality_layout.addRow(
            "Clipping:",
            self.clipping_label,
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

        self.instruction_label = QLabel(
            "Configure o ensaio antes de iniciar."
        )

        self.instruction_label.setWordWrap(
            True
        )

        self.instruction_label.setAlignment(
            Qt.AlignCenter
        )

        self.instruction_label.setMinimumHeight(
            42
        )

        instruction_layout.addWidget(
            self.instruction_label
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

        self.status_label = QLabel(
            "AGUARDANDO"
        )

        self.status_label.setAlignment(
            Qt.AlignCenter
        )

        self._set_status_banner(
            "AGUARDANDO",
            "idle",
        )

        self.progress_bar = QProgressBar()

        self.progress_bar.setRange(
            0,
            100,
        )

        self.progress_bar.setValue(0)

        self.progress_bar.setMaximumHeight(
            22
        )

        status_layout.addWidget(
            self.status_label
        )

        status_layout.addWidget(
            self.progress_bar
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
        # BOTÃO TEMPORAL
        # ====================================================

        time_button_layout = QHBoxLayout()

        time_button_layout.addStretch()

        self.open_time_button = QPushButton(
            "Abrir sinal temporal"
        )

        self.open_time_button.clicked.connect(
            self.open_time_popup
        )

        time_button_layout.addWidget(
            self.open_time_button
        )

        main_layout.addLayout(
            time_button_layout
        )

        # ====================================================
        # ESPECTRO
        # ====================================================

        self.spectrum_plot = pg.PlotWidget()

        self.spectrum_plot.setLabel(
            "left",
            "Amplitude",
        )

        self.spectrum_plot.setLabel(
            "bottom",
            "Frequência",
            units="Hz",
        )

        self.spectrum_plot.showGrid(
            x=True,
            y=True,
        )

        self.spectrum_legend = (
            self.spectrum_plot.addLegend()
        )

        self.spectrum_legend.anchor(
            itemPos=(0, 1),
            parentPos=(0, 1),
            offset=(10, -10),
        )

        self.spectrum_reference_curve = (
            self.spectrum_plot.plot(
                [],
                [],
                name="Referência - P3",
                pen=pg.mkPen(
                    REFERENCE_COLOR,
                    width=2,
                ),
            )
        )

        self.spectrum_mobile_curve = (
            self.spectrum_plot.plot(
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
            self._create_plot_panel(
                title="Espectro",
                plot_widget=(
                    self.spectrum_plot
                ),
                fit_callback=(
                    self.fit_spectrum_plot
                ),
                popup_callback=(
                    self.open_spectrum_popup
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

        self.coherence_plot = pg.PlotWidget()

        self.coherence_plot.setLabel(
            "left",
            "Coerência",
        )

        self.coherence_plot.setLabel(
            "bottom",
            "Frequência",
            units="Hz",
        )

        self.coherence_plot.setYRange(
            0.0,
            1.05,
        )

        self.coherence_plot.showGrid(
            x=True,
            y=True,
        )

        self.coherence_curve = (
            self.coherence_plot.plot(
                [],
                [],
                pen=pg.mkPen(
                    COHERENCE_COLOR,
                    width=2,
                ),
            )
        )

        coherence_panel = (
            self._create_plot_panel(
                title="Coerência",
                plot_widget=(
                    self.coherence_plot
                ),
                fit_callback=(
                    self.fit_coherence_plot
                ),
                popup_callback=(
                    self.open_coherence_popup
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

        self.start_experiment_button = QPushButton(
            "Iniciar ensaio"
        )

        self.measure_button = QPushButton(
            "Medir"
        )

        self.cancel_button = QPushButton(
            "Cancelar"
        )

        self.repeat_button = QPushButton(
            "Repetir"
        )

        self.accept_button = QPushButton(
            "Aceitar"
        )

        self.accept_warning_button = QPushButton(
            "Aceitar com aviso"
        )

        self.confirm_load_button = QPushButton(
            "Confirmar troca de carga"
        )

        self.restart_button = QPushButton(
            "Refazer ensaio do começo"
        )

        buttons_layout.addWidget(
            self.start_experiment_button
        )

        buttons_layout.addWidget(
            self.measure_button
        )

        buttons_layout.addWidget(
            self.cancel_button
        )

        buttons_layout.addWidget(
            self.repeat_button
        )

        buttons_layout.addWidget(
            self.accept_button
        )

        buttons_layout.addWidget(
            self.accept_warning_button
        )

        buttons_layout.addWidget(
            self.confirm_load_button
        )

        buttons_layout.addStretch()

        buttons_layout.addWidget(
            self.restart_button
        )

        main_layout.addLayout(
            buttons_layout
        )

        # ====================================================
        # CONEXÕES
        # ====================================================

        self.start_experiment_button.clicked.connect(
            self.start_experiment
        )

        self.measure_button.clicked.connect(
            self.measure_current_step
        )

        self.cancel_button.clicked.connect(
            self.cancel_measurement
        )

        self.repeat_button.clicked.connect(
            self.repeat_measurement
        )

        self.accept_button.clicked.connect(
            self.accept_measurement
        )

        self.accept_warning_button.clicked.connect(
            self.accept_measurement_with_warning
        )

        self.confirm_load_button.clicked.connect(
            self.confirm_load_change
        )

        self.restart_button.clicked.connect(
            self.restart_experiment
        )

    # ========================================================
    # ABA RESULTADOS
    # ========================================================

    def _build_results_tab(self):

        layout = QVBoxLayout(
            self.results_tab
        )

        self.tl_curve_entries = []

        self.current_tl_curve = None

        self.tl_active_valid_range = None

        self.tl_plot = pg.PlotWidget()

        self.tl_plot.setLabel(
            "left",
            "TL",
            units="dB",
        )

        self.tl_plot.setLabel(
            "bottom",
            "Frequência",
            units="Hz",
        )

        self.tl_plot.showGrid(
            x=True,
            y=True,
        )

        self.tl_legend = self.tl_plot.addLegend()

        self.tl_legend.anchor(
            itemPos=(1, 0),
            parentPos=(1, 0),
            offset=(-10, 10),
        )

        layout.addWidget(
            self.tl_plot,
            stretch=1,
        )

        # ====================================================
        # RESULTADOS
        # ====================================================

        result_group = QGroupBox(
            "Resultado"
        )

        result_form = QFormLayout(
            result_group
        )

        self.result_range_label = QLabel(
            "-"
        )

        self.result_points_label = QLabel(
            "-"
        )

        result_form.addRow(
            "Faixa válida:",
            self.result_range_label,
        )

        result_form.addRow(
            "Pontos armazenados:",
            self.result_points_label,
        )

        result_group.setMaximumWidth(
            260
        )

        result_group.setFixedWidth(
            260
        )

        lower_layout = QGridLayout()

        lower_layout.setHorizontalSpacing(
            10
        )

        lower_layout.setVerticalSpacing(
            5
        )

        self.process_button = QPushButton(
            "Processar TL"
        )

        self.save_button = QPushButton(
            "Salvar Ensaio CSV..."
        )

        self.fit_tl_button = QPushButton(
            "Zoom to fit"
        )

        self.tl_plot_settings_button = QPushButton(
            "Configurações Gráfico"
        )

        self.new_model_button = QPushButton(
            "Novo Ensaio/Modelo"
        )

        self.import_tl_button = QPushButton(
            "Add TL CSV"
        )

        self.save_tl_png_button = QPushButton(
            "Salvar Gráfico PNG..."
        )

        self.save_tl_csv_button = QPushButton(
            "Salvar Gráfico CSV..."
        )

        for button in (
            self.process_button,
            self.save_button,
            self.import_tl_button,
            self.save_tl_png_button,
            self.save_tl_csv_button,
            self.fit_tl_button,
            self.tl_plot_settings_button,
            self.new_model_button,
        ):

            button.setFixedWidth(
                button.sizeHint().width() + 8
            )

        # Coluna 1: resultado do ensaio atual.
        lower_layout.addWidget(
            result_group,
            0,
            0,
            3,
            1,
        )

        # Coluna 2: processamento e salvamento do ensaio.
        lower_layout.addWidget(
            self.process_button,
            0,
            1,
            Qt.AlignLeft | Qt.AlignTop,
        )

        lower_layout.addWidget(
            self.save_button,
            1,
            1,
            Qt.AlignLeft | Qt.AlignTop,
        )

        # Coluna 3: importação e exportação da comparação.
        lower_layout.addWidget(
            self.import_tl_button,
            0,
            2,
            Qt.AlignLeft | Qt.AlignTop,
        )

        lower_layout.addWidget(
            self.save_tl_png_button,
            1,
            2,
            Qt.AlignLeft | Qt.AlignTop,
        )

        lower_layout.addWidget(
            self.save_tl_csv_button,
            2,
            2,
            Qt.AlignLeft | Qt.AlignTop,
        )

        self.tl_curve_visibility_group = QGroupBox(
            "Curvas visíveis"
        )

        curve_scroll = QScrollArea()

        curve_scroll.setWidgetResizable(
            True
        )

        curve_widget = QWidget()

        self.tl_curve_visibility_layout = QVBoxLayout(
            curve_widget
        )

        self.tl_curve_visibility_layout.setContentsMargins(
            6,
            4,
            6,
            4,
        )

        self.tl_curve_visibility_layout.addStretch()

        curve_scroll.setWidget(
            curve_widget
        )

        curve_group_layout = QVBoxLayout(
            self.tl_curve_visibility_group
        )

        curve_group_layout.addWidget(
            curve_scroll
        )

        self.tl_curve_visibility_group.setFixedWidth(
            240
        )

        # Coluna 4: seleção de curvas, deliberadamente estreita.
        lower_layout.addWidget(
            self.tl_curve_visibility_group,
            0,
            3,
            3,
            1,
        )

        # Coluna 5: ajuste de visualização.
        lower_layout.addWidget(
            self.tl_plot_settings_button,
            0,
            4,
            Qt.AlignRight | Qt.AlignBottom,
        )

        lower_layout.addWidget(
            self.fit_tl_button,
            0,
            5,
            Qt.AlignRight | Qt.AlignBottom,
        )

        lower_layout.setColumnStretch(0, 0)

        lower_layout.setColumnStretch(1, 0)

        lower_layout.setColumnStretch(2, 0)

        lower_layout.setColumnStretch(3, 0)

        lower_layout.setColumnStretch(4, 1)

        lower_layout.setColumnStretch(5, 0)

        layout.addLayout(
            lower_layout
        )

        new_model_layout = QHBoxLayout()

        new_model_layout.addStretch()

        new_model_layout.addWidget(
            self.new_model_button
        )

        layout.addLayout(
            new_model_layout
        )

        self.process_button.clicked.connect(
            self.process_tl
        )

        self.save_button.clicked.connect(
            self.save_experiment
        )

        self.fit_tl_button.clicked.connect(
            self.fit_tl_plot
        )

        self.tl_plot_settings_button.clicked.connect(
            self.open_tl_plot_settings
        )

        self.new_model_button.clicked.connect(
            self.start_new_model_experiment
        )

        self.import_tl_button.clicked.connect(
            self.import_tl_csv_files
        )

        self.save_tl_png_button.clicked.connect(
            self.save_tl_plot_png
        )

        self.save_tl_csv_button.clicked.connect(
            self.save_tl_plot_csv
        )

    # ========================================================
    # STATUS
    # ========================================================

    def _set_status_banner(
        self,
        text: str,
        status: str,
    ):

        self.status_label.setText(
            text
        )

        styles = {

            "idle":
                """
                QLabel {
                    font-size: 14px;
                    font-weight: bold;
                    padding: 6px;
                    border: 2px solid #777777;
                    border-radius: 5px;
                }
                """,

            "running":
                """
                QLabel {
                    font-size: 15px;
                    font-weight: bold;
                    padding: 6px;
                    border: 2px solid #2979FF;
                    border-radius: 5px;
                }
                """,

            "success":
                """
                QLabel {
                    font-size: 15px;
                    font-weight: bold;
                    padding: 6px;
                    border: 2px solid #00C853;
                    border-radius: 5px;
                }
                """,

            "warning":
                """
                QLabel {
                    font-size: 15px;
                    font-weight: bold;
                    padding: 6px;
                    border: 2px solid #FFB300;
                    border-radius: 5px;
                }
                """,

            "error":
                """
                QLabel {
                    font-size: 15px;
                    font-weight: bold;
                    padding: 6px;
                    border: 2px solid #D50000;
                    border-radius: 5px;
                }
                """,
        }

        self.status_label.setStyleSheet(
            styles.get(
                status,
                styles["idle"],
            )
        )

    # ========================================================
    # POP-UP TEMPORAL
    # ========================================================

    def open_time_popup(self):

        if (
            self.time_popup is not None
            and
            self.time_popup.isVisible()
        ):

            self.time_popup.raise_()

            self.time_popup.activateWindow()

            return

        popup = PlotPopup(
            "Sinal temporal",
            self,
        )

        popup.plot.setLabel(
            "left",
            "Pressão",
            units="Pa",
        )

        popup.plot.setLabel(
            "bottom",
            "Tempo",
            units="s",
        )

        popup.legend = popup.plot.addLegend()

        popup.legend.anchor(
            itemPos=(0, 1),
            parentPos=(0, 1),
            offset=(10, -10),
        )

        popup.reference_curve = (
            popup.plot.plot(
                [],
                [],
                name="Referência - P3",
                pen=pg.mkPen(
                    REFERENCE_COLOR,
                    width=2,
                ),
            )
        )

        popup.mobile_curve = (
            popup.plot.plot(
                [],
                [],
                name="Móvel",
                pen=pg.mkPen(
                    MOBILE_COLOR,
                    width=2,
                ),
            )
        )

        # ====================================================
        # ÚLTIMO BLOCO DO MONITOR
        # ====================================================

        if self.last_monitoring_data is not None:

            data = self.last_monitoring_data

            popup.reference_curve.setData(
                data.time,
                data.reference_signal,
            )

            popup.mobile_curve.setData(
                data.time,
                data.mobile_signal,
            )

        self.time_popup = popup

        popup.finished.connect(
            self._time_popup_closed
        )

        popup.show()

    # ========================================================

    def _time_popup_closed(self):

        self.time_popup = None

    # ========================================================
    # POP-UP ESPECTRO
    # ========================================================

    def open_spectrum_popup(self):

        if (
            self.spectrum_popup is not None
            and
            self.spectrum_popup.isVisible()
        ):

            self.spectrum_popup.raise_()

            self.spectrum_popup.activateWindow()

            return

        popup = PlotPopup(
            "Espectro",
            self,
        )

        popup.plot.setLabel(
            "left",
            "Amplitude",
        )

        popup.plot.setLabel(
            "bottom",
            "Frequência",
            units="Hz",
        )

        popup.legend = popup.plot.addLegend()

        popup.legend.anchor(
            itemPos=(0, 1),
            parentPos=(0, 1),
            offset=(10, -10),
        )

        popup.reference_curve = (
            popup.plot.plot(
                [],
                [],
                name="Referência - P3",
                pen=pg.mkPen(
                    REFERENCE_COLOR,
                    width=2,
                ),
            )
        )

        popup.mobile_curve = (
            popup.plot.plot(
                [],
                [],
                name="Móvel",
                pen=pg.mkPen(
                    MOBILE_COLOR,
                    width=2,
                ),
            )
        )

        # ====================================================
        # PRIORIDADE: MONITOR AO VIVO
        # ====================================================

        if self.last_monitoring_data is not None:

            data = self.last_monitoring_data

            popup.reference_curve.setData(
                data.frequency,
                data.reference_spectrum,
            )

            popup.mobile_curve.setData(
                data.frequency,
                data.mobile_spectrum,
            )

        # ====================================================
        # FALLBACK: ÚLTIMA MEDIÇÃO OFICIAL
        # ====================================================

        elif self.last_measurement is not None:

            result = self.last_measurement

            reference_spectrum = np.sqrt(
                np.maximum(
                    result.frf.Gxx,
                    0.0,
                )
            )

            mobile_spectrum = np.sqrt(
                np.maximum(
                    result.frf.Gyy,
                    0.0,
                )
            )

            popup.reference_curve.setData(
                result.frf.frequency,
                reference_spectrum,
            )

            popup.mobile_curve.setData(
                result.frf.frequency,
                mobile_spectrum,
            )

        self.spectrum_popup = popup

        popup.finished.connect(
            self._spectrum_popup_closed
        )

        popup.show()

    # ========================================================

    def _spectrum_popup_closed(self):

        self.spectrum_popup = None

    # ========================================================
    # POP-UP COERÊNCIA
    # ========================================================

    def open_coherence_popup(self):

        if (
            self.coherence_popup is not None
            and
            self.coherence_popup.isVisible()
        ):

            self.coherence_popup.raise_()

            self.coherence_popup.activateWindow()

            return

        popup = PlotPopup(
            "Coerência",
            self,
        )

        popup.plot.setLabel(
            "left",
            "Coerência",
        )

        popup.plot.setLabel(
            "bottom",
            "Frequência",
            units="Hz",
        )

        popup.plot.setYRange(
            0.0,
            1.05,
        )

        popup.coherence_curve = (
            popup.plot.plot(
                [],
                [],
                pen=pg.mkPen(
                    COHERENCE_COLOR,
                    width=2,
                ),
            )
        )

        # ====================================================
        # PRIORIDADE: ÚLTIMA MEDIÇÃO OFICIAL
        # ====================================================

        if (
            self.coherence_frozen_to_measurement
            and self.displayed_measurement_frf is not None
        ):

            popup.coherence_curve.setData(
                self.displayed_measurement_frf.frequency,
                self.displayed_measurement_frf.coherence,
            )

        # ====================================================
        # FALLBACK: MONITOR
        # ====================================================

        elif self.last_monitoring_data is not None:

            data = self.last_monitoring_data

            popup.coherence_curve.setData(
                data.coherence_frequency,
                data.coherence,
            )

        # ====================================================
        # FALLBACK
        # ====================================================

        elif self.last_measurement is not None:

            popup.coherence_curve.setData(
                self.last_measurement.frf.frequency,
                self.last_measurement.frf.coherence,
            )

        self.coherence_popup = popup

        popup.finished.connect(
            self._coherence_popup_closed
        )

        popup.show()

    # ========================================================

    def _coherence_popup_closed(self):

        self.coherence_popup = None

    # ========================================================
    # MONITORAMENTO
    # ========================================================

    def start_monitoring(self):

        # Não disputa a DAQ com medição oficial.
        if self.measurement_in_progress:

            return

        if self.measurement_waiting_for_monitor:

            return

        # Thread já existe e ainda está ativa.
        if (
            self.monitoring_thread is not None
            and
            self.monitoring_thread.isRunning()
        ):

            return

        active_channels = [
            channel
            for channel in self.config.channels
            if channel.enabled
        ]

        if len(active_channels) < 2:

            return

        # ====================================================
        # THREAD
        # ====================================================

        monitoring_thread = QThread(
            self
        )

        monitoring_worker = MonitoringWorker(
            daq=self.daq,
            config=self.config,
            monitor_num_samples=256,
            coherence_nperseg=512,
        )

        monitoring_worker.moveToThread(
            monitoring_thread
        )

        self.monitoring_thread = monitoring_thread

        self.monitoring_worker = monitoring_worker

        # ====================================================
        # CONEXÕES
        # ====================================================

        monitoring_thread.started.connect(
            monitoring_worker.run
        )

        monitoring_worker.started.connect(
            self._monitoring_started
        )

        monitoring_worker.error.connect(
            self._monitoring_error
        )

        monitoring_worker.done.connect(
            monitoring_thread.quit
        )

        monitoring_worker.done.connect(
            monitoring_worker.deleteLater
        )

        monitoring_thread.finished.connect(
            self._monitoring_thread_finished
        )

        monitoring_thread.finished.connect(
            monitoring_thread.deleteLater
        )

        self.monitoring_running = False

        self.monitoring_stop_requested = False

        monitoring_thread.start()

    # ========================================================

    def stop_monitoring(
        self,
        wait: bool = False,
    ) -> bool:

        if self.monitoring_worker is None:

            return True

        self.monitoring_stop_requested = True

        self.monitor_update_timer.stop()

        # request_stop() usa threading.Event,
        # portanto pode ser chamado daqui com segurança.
        self.monitoring_worker.request_stop()

        if (
            wait
            and
            self.monitoring_thread is not None
        ):

            self.monitoring_thread.wait(
                5000
            )

            # Permite que os sinais finished pendentes
            # sejam processados antes de uma nova thread.
            QApplication.processEvents()

            if (
                self.monitoring_thread is not None
                and self.monitoring_thread.isRunning()
            ):

                return False

        return True

    # ========================================================

    def _monitoring_started(self):

        self.monitoring_running = True

        self.monitor_update_timer.start()

    # ========================================================

    def _monitoring_thread_finished(
        self,
        finished_thread: QThread | None = None,
    ):

        # A finalização é entregue pela fila de eventos da GUI. Se uma nova
        # sessão já começou, este sinal pertence à sessão anterior e não deve
        # alterar suas referências nem iniciar uma medição pendente.
        if finished_thread is None:

            finished_thread = self.sender()

        if finished_thread is not self.monitoring_thread:

            return

        self.monitoring_running = False

        self.monitor_update_timer.stop()

        self.monitoring_stop_requested = False

        self.monitoring_thread = None

        self.monitoring_worker = None

        # ====================================================
        # MEDIÇÃO ESTAVA AGUARDANDO O MONITOR
        # ====================================================

        if self.measurement_waiting_for_monitor:

            self.measurement_waiting_for_monitor = False

            self._start_measurement_thread()

    # ========================================================

    def _monitoring_error(
        self,
        message: str,
    ):

        self.monitoring_running = False

        # Se o monitor estava sendo desligado
        # intencionalmente, não mostra erro.
        if self.monitoring_stop_requested:

            return

        QMessageBox.warning(
            self,
            "Monitoramento",
            "O monitoramento contínuo foi "
            "interrompido.\n\n"
            f"{message}",
        )

    # ========================================================

    def _clear_monitoring_data(self) -> None:
        """Remove dados e curvas pertencentes ao monitoramento ao vivo."""

        self.last_monitoring_data = None

        self.spectrum_reference_curve.setData([], [])

        self.spectrum_mobile_curve.setData([], [])

        self.coherence_curve.setData([], [])

        if self.time_popup is not None:

            self.time_popup.reference_curve.setData([], [])

            self.time_popup.mobile_curve.setData([], [])

        if self.spectrum_popup is not None:

            self.spectrum_popup.reference_curve.setData([], [])

            self.spectrum_popup.mobile_curve.setData([], [])

        if self.coherence_popup is not None:

            self.coherence_popup.coherence_curve.setData([], [])

    # ========================================================
    # ATUALIZAÇÃO DOS GRÁFICOS
    # ========================================================

    def _flush_monitoring_data(self):
        """
        Atualiza a GUI com o último pacote disponível.

        A thread de aquisição nunca enfileira atualizações de
        gráficos; pacotes intermediários são substituídos no worker.
        """

        worker = self.monitoring_worker

        if worker is None:

            return

        try:

            data = worker.take_latest_data()

        except RuntimeError:

            # O worker pode ter sido destruído enquanto a thread
            # de monitoramento estava sendo encerrada.
            return

        if data is not None:

            self._update_monitoring_plots(
                data
            )

    # ========================================================

    def _update_monitoring_plots(
        self,
        data: MonitoringData,
    ):

        self.last_monitoring_data = data

        # ====================================================
        # ESPECTRO PRINCIPAL
        # ====================================================

        self.spectrum_reference_curve.setData(
            data.frequency,
            data.reference_spectrum,
        )

        self.spectrum_mobile_curve.setData(
            data.frequency,
            data.mobile_spectrum,
        )

        # ====================================================
        # COERÊNCIA PRINCIPAL
        # ====================================================

        if not self.coherence_frozen_to_measurement:

            self.coherence_curve.setData(
                data.coherence_frequency,
                data.coherence,
            )

        # ====================================================
        # TEMPORAL
        # ====================================================

        if (
            self.time_popup is not None
            and
            self.time_popup.isVisible()
        ):

            self.time_popup.reference_curve.setData(
                data.time,
                data.reference_signal,
            )

            self.time_popup.mobile_curve.setData(
                data.time,
                data.mobile_signal,
            )

        # ====================================================
        # ESPECTRO POP-UP
        # ====================================================

        if (
            self.spectrum_popup is not None
            and
            self.spectrum_popup.isVisible()
        ):

            self.spectrum_popup.reference_curve.setData(
                data.frequency,
                data.reference_spectrum,
            )

            self.spectrum_popup.mobile_curve.setData(
                data.frequency,
                data.mobile_spectrum,
            )

        # ====================================================
        # COERÊNCIA POP-UP
        # ====================================================

        if (
            not self.coherence_frozen_to_measurement
            and
            self.coherence_popup is not None
            and
            self.coherence_popup.isVisible()
        ):

            self.coherence_popup.coherence_curve.setData(
                data.coherence_frequency,
                data.coherence,
            )

    # ========================================================
    # DIRETÓRIO
    # ========================================================

    def browse_output_directory(self):

        directory = (
            QFileDialog.getExistingDirectory(
                self,
                "Escolha a pasta de resultados",
            )
        )

        if directory:

            self.output_directory_input.setText(
                directory
            )

    # ========================================================
    # DAQ
    # ========================================================

    def _device_selection_changed(
        self,
        device_name: str,
    ) -> None:
        """Atualiza os canais físicos para o dispositivo selecionado."""

        if not device_name:

            return

        # A task de monitoramento mantém a DAQ em uso. Libera-a antes de
        # selecionar outro módulo, inclusive quando a troca é feita pelo
        # usuário diretamente no combo.
        if (
            self.monitoring_thread is not None
            and
            self.monitoring_thread.isRunning()
        ):

            if not self.stop_monitoring(wait=True):

                QMessageBox.warning(
                    self,
                    "DAQ",
                    "Não foi possível encerrar o monitoramento contínuo. "
                    "Aguarde alguns segundos e tente novamente.",
                )

                return

        try:

            self.daq.connect(
                device_name
            )

            channels = (
                self.daq
                .get_available_ai_channels()
            )

            # Evita sinais intermediários enquanto os combos são refeitos.
            with QSignalBlocker(self.reference_channel_combo):
                with QSignalBlocker(self.mobile_channel_combo):

                    self.reference_channel_combo.clear()

                    self.mobile_channel_combo.clear()

                    for channel in channels:

                        self.reference_channel_combo.addItem(
                            channel
                        )

                        self.mobile_channel_combo.addItem(
                            channel
                        )

                    if channels:

                        self.reference_channel_combo.setCurrentIndex(
                            0
                        )

                        self.mobile_channel_combo.setCurrentIndex(
                            min(1, len(channels) - 1)
                        )

        except DAQError as error:

            self.reference_channel_combo.clear()

            self.mobile_channel_combo.clear()

            QMessageBox.critical(
                self,
                "Erro DAQ",
                str(error),
            )

    def refresh_devices(self):

        # Evita mexer na DAQ enquanto o
        # monitor possui a task.
        if (
            self.monitoring_thread is not None
            and
            self.monitoring_thread.isRunning()
        ):

            self.stop_monitoring(
                wait=True
            )

        try:

            devices = (
                NIDaqDevice
                .discover_ai_devices()
            )

            if not devices:

                self.device_combo.clear()

                self.reference_channel_combo.clear()

                self.mobile_channel_combo.clear()

                QMessageBox.warning(
                    self,
                    "DAQ",
                    "Nenhum dispositivo com "
                    "entrada analógica foi encontrado.",
                )

                return

            # Bloqueia o sinal para carregar a lista uma única vez, depois
            # delega a mesma rotina usada na troca manual de dispositivo.
            with QSignalBlocker(self.device_combo):

                self.device_combo.clear()

                for device in devices:

                    self.device_combo.addItem(
                        device
                    )

                self.device_combo.setCurrentIndex(
                    0
                )

            self._device_selection_changed(
                self.device_combo.currentText()
            )

        except DAQError as error:

            QMessageBox.critical(
                self,
                "Erro DAQ",
                str(error),
            )

    # ========================================================
    # LABELS AQUISIÇÃO
    # ========================================================

    def _update_acquisition_labels(self):

        fs = self.sample_rate_input.value()

        n = self.num_samples_input.value()

        if fs <= 0 or n <= 0:

            return

        self.duration_label.setText(
            f"{n / fs:.4f} s"
        )

        self.df_label.setText(
            f"{fs / n:.4f} Hz"
        )

        self.nyquist_label.setText(
            f"{fs / 2.0:.1f} Hz"
        )

        self._update_valid_range_preview()

    # ========================================================
    # ACÚSTICA
    # ========================================================

    def _update_acoustic_labels(self):

        temperature = (
            self.temperature_input.value()
        )

        c = (
            331.3
            +
            0.606 * temperature
        )

        self.sound_speed_label.setText(
            f"{c:.2f} m/s"
        )

        self._update_valid_range_preview()

    # ========================================================
    # FAIXA VÁLIDA
    # ========================================================

    def _update_valid_range_preview(self):

        try:

            temperature = (
                self.temperature_input.value()
            )

            c = (
                331.3
                +
                0.606 * temperature
            )

            diameter = (
                self.diameter_input.value()
                / 1000.0
            )

            s12 = (
                self.spacing12_input.value()
                / 1000.0
            )

            s34 = (
                self.spacing34_input.value()
                / 1000.0
            )

            spacing_min = max(
                0.05 * c / s12,
                0.05 * c / s34,
            )

            spacing_max = min(
                0.40 * c / s12,
                0.40 * c / s34,
            )

            plane_wave = (
                1.84
                * c
                /
                (
                    np.pi
                    * diameter
                )
            )

            nyquist = (
                self.sample_rate_input.value()
                / 2.0
            )

            f_max = min(
                spacing_max,
                plane_wave,
                nyquist,
            )

            self.valid_range_label.setText(
                f"{spacing_min:.1f} - "
                f"{f_max:.1f} Hz"
            )

        except Exception:

            self.valid_range_label.setText(
                "-"
            )

    # ========================================================
    # APLICAR CONFIGURAÇÃO
    # ========================================================

    def apply_configuration(
        self,
        show_message: bool = True,
    ) -> bool:

        # Não permite alterar configuração
        # durante medição oficial.
        if self.measurement_in_progress:

            QMessageBox.warning(
                self,
                "Configuração",
                "Não é possível alterar a configuração "
                "durante uma medição.",
            )

            return False

        # ====================================================
        # LIBERA DAQ DO MONITOR
        # ====================================================

        if (
            self.monitoring_thread is not None
            and
            self.monitoring_thread.isRunning()
        ):

            if not self.stop_monitoring(wait=True):

                QMessageBox.warning(
                    self,
                    "Configuração",
                    "Não foi possível encerrar o monitoramento contínuo. "
                    "Aguarde alguns segundos e tente novamente.",
                )

                return False

        try:

            if (
                self.reference_channel_combo.count()
                == 0
            ):

                raise ValueError(
                    "Nenhum canal foi selecionado."
                )

            reference_channel = (
                self.reference_channel_combo.currentText()
            )

            mobile_channel = (
                self.mobile_channel_combo.currentText()
            )

            if (
                reference_channel
                == mobile_channel
            ):

                raise ValueError(
                    "Os microfones precisam utilizar "
                    "canais físicos diferentes."
                )

            selected_device = (
                self.device_combo.currentText()
            )

            if not selected_device:

                raise ValueError(
                    "Nenhum dispositivo DAQ foi selecionado."
                )

            self.daq.connect(
                selected_device
            )

            # =================================================
            # AQUISIÇÃO
            # =================================================

            self.config.acquisition.sample_rate = (
                self.sample_rate_input.value()
            )

            self.config.acquisition.num_samples = (
                self.num_samples_input.value()
            )

            self.config.acquisition.num_averages = (
                self.num_averages_input.value()
            )

            self.config.acquisition.stabilization_time = (
                self.stabilization_input.value()
            )

            self.config.acquisition.window = (
                self.window_combo.currentData()
            )

            self.config.quality.coherence_threshold = (
                self.coherence_min_input.value()
            )

            self.config.quality.coherence_mean_threshold = (
                self.coherence_mean_input.value()
            )

            # =================================================
            # ACÚSTICA
            # =================================================

            self.config.acoustics.temperature_c = (
                self.temperature_input.value()
            )

            # =================================================
            # GEOMETRIA
            # =================================================

            self.config.transmission_loss.tube_diameter = (
                self.diameter_input.value()
                / 1000.0
            )

            self.config.transmission_loss.spacing_12 = (
                self.spacing12_input.value()
                / 1000.0
            )

            self.config.transmission_loss.spacing_34 = (
                self.spacing34_input.value()
                / 1000.0
            )

            self.config.transmission_loss.automatic_valid_frequency_range = (
                self.auto_range_checkbox.isChecked()
            )

            # =================================================
            # CANAIS
            # =================================================

            self.config.channels = [

                ChannelConfig(
                    physical_channel=(
                        reference_channel
                    ),
                    name=(
                        "Microfone referência - P3"
                    ),
                    sensor_type=(
                        SensorType.MICROPHONE
                    ),
                    sensitivity_mv_pa=(
                        self
                        .reference_sensitivity_input
                        .value()
                    ),
                    iepe_enabled=True,
                    iepe_current_a=0.002,
                ),

                ChannelConfig(
                    physical_channel=(
                        mobile_channel
                    ),
                    name=(
                        "Microfone móvel"
                    ),
                    sensor_type=(
                        SensorType.MICROPHONE
                    ),
                    sensitivity_mv_pa=(
                        self
                        .mobile_sensitivity_input
                        .value()
                    ),
                    iepe_enabled=True,
                    iepe_current_a=0.002,
                ),
            ]

            # =================================================
            # METADADOS
            # =================================================

            self.config.metadata.experiment_name = (
                self.experiment_name_input.text()
            )

            self.config.metadata.experiment_number = (
                self.experiment_number_input.text()
            )

            self.config.metadata.operator = (
                self.operator_input.text()
            )

            self.config.metadata.notes = (
                self.notes_input.toPlainText()
            )

            self.config.metadata.output_directory = (
                self.output_directory_input
                .text()
                .strip()
            )

            # =================================================
            # VALIDAÇÃO
            # =================================================

            self.config.validate()

            # =================================================
            # MONITOR
            # =================================================

            self.start_monitoring()

            if show_message:

                QMessageBox.information(
                    self,
                    "Configuração",
                    "Configuração aplicada com sucesso.\n\n"
                    "O monitoramento contínuo foi iniciado.",
                )

            return True

        except Exception as error:

            QMessageBox.critical(
                self,
                "Erro de configuração",
                str(error),
            )

            return False

    # ========================================================
    # INICIAR ENSAIO
    # ========================================================

    def start_experiment(self):

        # Se o monitor já estiver rodando,
        # não precisamos reaplicar tudo.
        if not (
            self.monitoring_thread is not None
            and
            self.monitoring_thread.isRunning()
        ):

            if not self.apply_configuration(
                show_message=False
            ):

                return

        try:

            self.experiment.start()

            self.last_measurement = None

            self.coherence_frozen_to_measurement = False

            self.displayed_measurement_frf = None

            self.tl_result = None

            self.progress_bar.setValue(
                0
            )

            self.instruction_label.setText(
                self.experiment
                .get_current_instruction()
            )

            self._set_status_banner(
                "ENSAIO PRONTO PARA COMEÇAR",
                "success",
            )

            self.tabs.setCurrentWidget(
                self.experiment_tab
            )

            self._update_controls()

        except Exception as error:

            QMessageBox.critical(
                self,
                "Erro",
                str(error),
            )

    # ========================================================
    # SOLICITA MEDIÇÃO
    # ========================================================

    def measure_current_step(self):

        if self.measurement_in_progress:

            return

        if self.measurement_waiting_for_monitor:

            return

        # ====================================================
        # MONITOR EXISTE
        # ====================================================

        if (
            self.monitoring_thread is not None
            and
            self.monitoring_thread.isRunning()
        ):

            self.measurement_waiting_for_monitor = True

            self._set_status_banner(
                "● PREPARANDO MEDIÇÃO...",
                "running",
            )

            self._update_controls()

            self.stop_monitoring(
                wait=False
            )

            return

        # ====================================================
        # DAQ JÁ LIVRE
        # ====================================================

        self._start_measurement_thread()

    # ========================================================
    # THREAD DA MEDIÇÃO OFICIAL
    # ========================================================

    def _start_measurement_thread(self):

        if self.measurement_in_progress:

            return

        self.measurement_in_progress = True

        self.progress_bar.setValue(
            0
        )

        step = self.experiment.current_step

        step_text = (
            step.value
            if step is not None
            else ""
        )

        self._set_status_banner(
            f"● INICIANDO MEDIÇÃO — {step_text}",
            "running",
        )

        # ====================================================
        # THREAD
        # ====================================================

        self.measurement_thread = QThread(
            self
        )

        self.measurement_worker = MeasurementWorker(
            self.experiment
        )

        self.measurement_worker.moveToThread(
            self.measurement_thread
        )

        # ====================================================
        # START
        # ====================================================

        self.measurement_thread.started.connect(
            self.measurement_worker.run
        )

        # ====================================================
        # SINAIS
        # ====================================================

        self.measurement_worker.progress.connect(
            self._measurement_progress
        )

        self.measurement_worker.message.connect(
            self._measurement_message
        )

        self.measurement_worker.frf_updated.connect(
            self._measurement_frf_updated
        )

        self.measurement_worker.finished.connect(
            self._measurement_finished
        )

        self.measurement_worker.error.connect(
            self._measurement_error
        )

        self.measurement_worker.cancelled.connect(
            self._measurement_cancelled
        )

        # ====================================================
        # FINALIZAÇÃO
        # ====================================================

        self.measurement_worker.done.connect(
            self.measurement_thread.quit
        )

        self.measurement_worker.done.connect(
            self.measurement_worker.deleteLater
        )

        self.measurement_thread.finished.connect(
            self._measurement_thread_finished
        )

        self.measurement_thread.finished.connect(
            self.measurement_thread.deleteLater
        )

        self._update_controls()

        self.measurement_thread.start()

    # ========================================================
    # PROGRESSO
    # ========================================================

    def _measurement_progress(
        self,
        current: int,
        total: int,
    ):

        if total <= 0:

            return

        percentage = int(
            100
            * current
            / total
        )

        self.progress_bar.setValue(
            percentage
        )

        self._set_status_banner(
            f"● MEDINDO — média "
            f"{current} de {total}",
            "running",
        )

    # ========================================================
    # MENSAGEM
    # ========================================================

    def _measurement_message(
        self,
        message: str,
    ):

        if (
            "estabilização"
            in message.lower()
        ):

            self._set_status_banner(
                "● AGUARDANDO ESTABILIZAÇÃO",
                "running",
            )

    # ========================================================
    # FRF PARCIAL DA MEDIÇÃO OFICIAL
    # ========================================================

    def _measurement_frf_updated(
        self,
        frf,
    ):
        """
        Atualiza os gráficos após cada média acumulada.

        O monitor é interrompido durante a medição, portanto
        estes dados são exclusivamente da aquisição oficial.
        """

        reference_spectrum = np.sqrt(
            np.maximum(
                frf.Gxx,
                0.0,
            )
        )

        mobile_spectrum = np.sqrt(
            np.maximum(
                frf.Gyy,
                0.0,
            )
        )

        self.spectrum_reference_curve.setData(
            frf.frequency,
            reference_spectrum,
        )

        self.spectrum_mobile_curve.setData(
            frf.frequency,
            mobile_spectrum,
        )

        self.coherence_curve.setData(
            frf.frequency,
            frf.coherence,
        )

        self.fit_spectrum_plot()

        self.fit_coherence_plot()

        self.coherence_frozen_to_measurement = True

        self.displayed_measurement_frf = frf

        if (
            self.spectrum_popup is not None
            and self.spectrum_popup.isVisible()
        ):

            self.spectrum_popup.reference_curve.setData(
                frf.frequency,
                reference_spectrum,
            )

            self.spectrum_popup.mobile_curve.setData(
                frf.frequency,
                mobile_spectrum,
            )

            self.spectrum_popup.plot.getViewBox().autoRange()

        if (
            self.coherence_popup is not None
            and self.coherence_popup.isVisible()
        ):

            self.coherence_popup.coherence_curve.setData(
                frf.frequency,
                frf.coherence,
            )

            self.coherence_popup.plot.getViewBox().autoRange()

    # ========================================================
    # MEDIÇÃO FINALIZADA
    # ========================================================

    def _measurement_finished(
        self,
        result,
    ):

        self.last_measurement = result

        self.coherence_frozen_to_measurement = True

        self.displayed_measurement_frf = result.frf

        self._show_measurement_result(
            result
        )

        if (
            result.quality.status
            ==
            MeasurementQualityStatus.VALID
        ):

            self._set_status_banner(
                "✓ MEDIÇÃO CONCLUÍDA — VÁLIDA",
                "success",
            )

        else:

            self._set_status_banner(
                "⚠ MEDIÇÃO CONCLUÍDA — REVISAR",
                "warning",
            )

    # ========================================================
    # ERRO
    # ========================================================

    def _measurement_error(
        self,
        message: str,
    ):

        self._set_status_banner(
            "ERRO NA MEDIÇÃO",
            "error",
        )

        QMessageBox.critical(
            self,
            "Erro de medição",
            message,
        )

    # ========================================================
    # CANCELAMENTO
    # ========================================================

    def _measurement_cancelled(self):

        self._set_status_banner(
            "MEDIÇÃO CANCELADA",
            "warning",
        )

        self.progress_bar.setValue(
            0
        )

    # ========================================================
    # THREAD MEDIÇÃO FINALIZADA
    # ========================================================

    def _measurement_thread_finished(self):

        self.measurement_in_progress = False

        self.measurement_thread = None

        self.measurement_worker = None

        self._update_controls()

        # ====================================================
        # RETORNA AO MONITOR
        # ====================================================

        self.start_monitoring()

    # ========================================================
    # CANCELAR MEDIÇÃO
    # ========================================================

    def cancel_measurement(self):

        # Caso ainda estejamos apenas esperando
        # o monitor liberar a DAQ.
        if self.measurement_waiting_for_monitor:

            self.measurement_waiting_for_monitor = False

            self._set_status_banner(
                "MEDIÇÃO CANCELADA",
                "warning",
            )

            self._update_controls()

            # Monitor já estava sendo encerrado.
            # Quando terminar, ele poderá ser
            # iniciado novamente.
            return

        if not self.measurement_in_progress:

            return

        self._set_status_banner(
            "CANCELANDO MEDIÇÃO...",
            "warning",
        )

        self.controller.cancel()

    # ========================================================
    # RESULTADO DA MEDIÇÃO OFICIAL
    # ========================================================

    def _show_measurement_result(
        self,
        result,
    ):

        quality = result.quality

        # ====================================================
        # QUALIDADE
        # ====================================================

        self.quality_status_label.setText(
            quality.status.value
        )

        self.coherence_mean_label.setText(
            f"{quality.coherence_mean:.4f}"
        )

        self.coherence_min_label.setText(
            f"{quality.coherence_min:.4f}"
        )

        self.valid_points_label.setText(
            f"{quality.coherence_valid_percentage:.1f}%"
        )

        self.clipping_label.setText(
            "SIM"
            if quality.clipping_detected
            else "NÃO"
        )

        # ====================================================
        # ESPECTRO DA MEDIÇÃO
        # ====================================================

        reference_spectrum = np.sqrt(
            np.maximum(
                result.frf.Gxx,
                0.0,
            )
        )

        mobile_spectrum = np.sqrt(
            np.maximum(
                result.frf.Gyy,
                0.0,
            )
        )

        self.spectrum_reference_curve.setData(
            result.frf.frequency,
            reference_spectrum,
        )

        self.spectrum_mobile_curve.setData(
            result.frf.frequency,
            mobile_spectrum,
        )

        # ====================================================
        # COERÊNCIA OFICIAL
        # ====================================================

        self.coherence_curve.setData(
            result.frf.frequency,
            result.frf.coherence,
        )

        # ====================================================
        # POP-UP ESPECTRO
        # ====================================================

        if (
            self.spectrum_popup is not None
            and
            self.spectrum_popup.isVisible()
        ):

            self.spectrum_popup.reference_curve.setData(
                result.frf.frequency,
                reference_spectrum,
            )

            self.spectrum_popup.mobile_curve.setData(
                result.frf.frequency,
                mobile_spectrum,
            )

        # ====================================================
        # POP-UP COERÊNCIA
        # ====================================================

        if (
            self.coherence_popup is not None
            and
            self.coherence_popup.isVisible()
        ):

            self.coherence_popup.coherence_curve.setData(
                result.frf.frequency,
                result.frf.coherence,
            )

        self.fit_spectrum_plot()

        self.fit_coherence_plot()

    # ========================================================
    # FIT
    # ========================================================

    def fit_spectrum_plot(self):

        self.spectrum_plot.getViewBox().autoRange()

    # ========================================================

    def fit_coherence_plot(self):

        self.coherence_plot.getViewBox().autoRange()

    # ========================================================
    # REPETIR
    # ========================================================

    def repeat_measurement(self):

        try:

            self.experiment.repeat_measurement()

            self.last_measurement = None

            self._set_status_banner(
                "MEDIÇÃO DESCARTADA — PRONTO PARA REPETIR",
                "warning",
            )

            self._update_controls()

        except TransmissionLossError as error:

            QMessageBox.warning(
                self,
                "Repetir",
                str(error),
            )

    # ========================================================
    # ACEITAR
    # ========================================================

    def accept_measurement(self):

        if (
            self.last_measurement is not None
            and self.last_measurement.quality.status
            == MeasurementQualityStatus.REVIEW
        ):

            self.accept_measurement_with_warning()

            return

        try:

            self.experiment.accept_measurement()

            self._after_accept()

        except TransmissionLossError as error:

            QMessageBox.warning(
                self,
                "Atenção",
                str(error),
            )

    # ========================================================
    # ACEITAR COM AVISO
    # ========================================================

    def accept_measurement_with_warning(
        self,
    ):

        answer = QMessageBox.question(
            self,
            "Aceitar medição",
            "A medição possui avisos de qualidade.\n\n"
            "Deseja aceitá-la mesmo assim?",
            QMessageBox.Yes
            |
            QMessageBox.No,
        )

        if answer != QMessageBox.Yes:

            return

        try:

            self.experiment.accept_measurement(
                accept_warning=True
            )

            self._after_accept()

        except TransmissionLossError as error:

            QMessageBox.warning(
                self,
                "Atenção",
                str(error),
            )

    # ========================================================
    # APÓS ACEITAR
    # ========================================================

    def _after_accept(self):

        self.last_measurement = None

        self.instruction_label.setText(
            self.experiment
            .get_current_instruction()
        )

        if (
            self.experiment.state
            ==
            TLExperimentState.WAITING_LOAD_CHANGE
        ):

            self._set_status_banner(
                "TROQUE PARA A CARGA B",
                "warning",
            )

        elif (
            self.experiment.state
            ==
            TLExperimentState.READY_TO_PROCESS
        ):

            self._set_status_banner(
                "✓ SEIS MEDIÇÕES CONCLUÍDAS",
                "success",
            )

        else:

            self._set_status_banner(
                "✓ MEDIÇÃO ACEITA — PRONTO PARA PRÓXIMA",
                "success",
            )

        self._update_controls()

    # ========================================================
    # TROCA DE CARGA
    # ========================================================

    def confirm_load_change(self):

        try:

            self.experiment.confirm_load_change()

            self.instruction_label.setText(
                self.experiment
                .get_current_instruction()
            )

            self._set_status_banner(
                "CARGA B CONFIRMADA",
                "success",
            )

            self._update_controls()

        except TransmissionLossError as error:

            QMessageBox.warning(
                self,
                "Troca de carga",
                str(error),
            )

    # ========================================================
    # RESET
    # ========================================================

    def restart_experiment(self):

        if (
            self.measurement_in_progress
            or
            self.measurement_waiting_for_monitor
        ):

            QMessageBox.warning(
                self,
                "Refazer ensaio",
                "Cancele a medição atual antes "
                "de reiniciar o ensaio.",
            )

            return

        answer = QMessageBox.question(
            self,
            "Refazer ensaio",
            "Todas as medições já realizadas serão "
            "descartadas.\n\n"
            "Deseja refazer o ensaio desde H31_A?",
            QMessageBox.Yes
            |
            QMessageBox.No,
        )

        if answer != QMessageBox.Yes:

            return

        self.experiment.reset()

        self.last_measurement = None

        self.coherence_frozen_to_measurement = False

        self.displayed_measurement_frf = None

        self.tl_result = None

        self.progress_bar.setValue(
            0
        )

        # ====================================================
        # QUALIDADE
        # ====================================================

        self.quality_status_label.setText("-")

        self.coherence_mean_label.setText("-")

        self.coherence_min_label.setText("-")

        self.valid_points_label.setText("-")

        self.clipping_label.setText("-")

        # Não limpamos espectro/coerência do
        # monitor porque eles representam
        # a aquisição ao vivo.

        # ====================================================
        # RESULTADO TL
        # ====================================================

        self._clear_tl_curves()

        self.instruction_label.setText(
            self.experiment
            .get_current_instruction()
        )

        self._set_status_banner(
            "ENSAIO REINICIADO — PRONTO PARA H31_A",
            "success",
        )

        self._update_controls()

    # ========================================================
    # PROCESSAR TL
    # ========================================================

    def process_tl(self):

        try:

            self.tl_result = (
                self.experiment.process()
            )

            result = self.tl_result

            # Mantém toda a curva finita. A faixa válida é uma opção de
            # visualização, não um filtro que descarte o diagnóstico.
            plot_mask = np.isfinite(result.transmission_loss)

            frequency_plot = result.frequency[plot_mask]

            tl_plot = result.transmission_loss[plot_mask]

            # =================================================
            # PLOT
            # =================================================

            if self.current_tl_curve is None:

                self.current_tl_curve = (
                    self._add_tl_curve(
                        frequency=frequency_plot,
                        transmission_loss=tl_plot,
                        name="TL do ensaio atual",
                        valid_frequency_range=(
                            result.valid_frequency_range.minimum,
                            result.valid_frequency_range.maximum,
                        ),
                    )
                )

            else:

                self.current_tl_curve[
                    "curve"
                ].setData(
                    frequency_plot,
                    tl_plot,
                )

                self.current_tl_curve["valid_frequency_range"] = (
                    result.valid_frequency_range.minimum,
                    result.valid_frequency_range.maximum,
                )

                self.current_tl_curve[
                    "checkbox"
                ].setChecked(
                    True
                )

            valid_range = (
                result.valid_frequency_range
            )

            self.tl_active_valid_range = (
                valid_range.minimum,
                valid_range.maximum,
            )

            self.fit_tl_plot()

            self.result_range_label.setText(
                f"{valid_range.minimum:.1f} - "
                f"{valid_range.maximum:.1f} Hz"
            )

            self.result_points_label.setText(
                str(
                    result.frequency.size
                )
            )

            self.tabs.setCurrentWidget(
                self.results_tab
            )

            self._update_controls()

        except TransmissionLossError as error:

            QMessageBox.critical(
                self,
                "Erro de processamento",
                str(error),
            )

    # ========================================================
    # ZOOM DA TL
    # ========================================================

    def fit_tl_plot(self):

        self.tl_plot.getViewBox().autoRange()

    # ========================================================

    def open_tl_plot_settings(self):
        """Abre os controles de visualização e importação de FRFs."""

        dialog = QDialog(self)
        dialog.setWindowTitle("Configurações Gráfico")
        dialog.setMinimumWidth(430)
        layout = QVBoxLayout(dialog)

        clear_button = QPushButton("Limpar Gráfico")
        clear_button.clicked.connect(self._confirm_clear_tl_curves)
        layout.addWidget(clear_button)

        form = QFormLayout()
        inputs = {}
        for key, label in (
            ("x_min", "X mínimo (Hz):"),
            ("x_max", "X máximo (Hz):"),
            ("y_min", "Y mínimo (dB):"),
            ("y_max", "Y máximo (dB):"),
        ):
            spin = QDoubleSpinBox()
            spin.setRange(-1e12, 1e12)
            spin.setDecimals(3)
            spin.setValue(0.0)
            inputs[key] = spin
            form.addRow(label, spin)
        layout.addLayout(form)

        apply_button = QPushButton("Aplicar limites")
        apply_button.clicked.connect(
            lambda: self._set_tl_plot_range(inputs)
        )
        layout.addWidget(apply_button)

        valid_button = QPushButton("Ajustar na faixa válida")
        valid_button.clicked.connect(
            lambda: self._fit_tl_valid_range(inputs)
        )
        layout.addWidget(valid_button)

        read_frfs_button = QPushButton("Ler FRFs")
        read_frfs_button.clicked.connect(
            self.load_tl_from_frf_files
        )
        layout.addWidget(read_frfs_button)

        close_button = QPushButton("Fechar")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)
        dialog.exec()

    # ========================================================

    def _confirm_clear_tl_curves(self):
        if not self.tl_curve_entries:
            return
        answer = QMessageBox.question(self, "Limpar gráfico",
            "Todas as curvas serão removidas da interface. Deseja continuar?",
            QMessageBox.Yes | QMessageBox.No)
        if answer == QMessageBox.Yes:
            self._clear_tl_curves()
            self.tl_active_valid_range = None
            self._update_controls()

    def _set_tl_plot_range(self, inputs):
        x_min, x_max = inputs["x_min"].value(), inputs["x_max"].value()
        y_min, y_max = inputs["y_min"].value(), inputs["y_max"].value()
        if x_max <= x_min or y_max <= y_min:
            QMessageBox.warning(self, "Limites do gráfico",
                "Os limites máximos devem ser maiores que os mínimos.")
            return
        self.tl_plot.getViewBox().setRange(
            xRange=(x_min, x_max), yRange=(y_min, y_max), padding=0)

    def _fit_tl_valid_range(self, inputs):
        valid_ranges = [
            entry["valid_frequency_range"]
            for entry in self.tl_curve_entries
            if entry.get("valid_frequency_range") is not None
        ]

        if not valid_ranges:
            QMessageBox.warning(self, "Faixa válida",
                "Nenhuma curva possui informação de faixa válida.")
            return
        x_min, x_max = valid_ranges[-1]
        values = []
        for entry in self.tl_curve_entries:
            x, y = entry["curve"].getData()
            if x is not None:
                values.extend(y[(x >= x_min) & (x <= x_max) & np.isfinite(y)])
        if not values:
            return
        y_min, y_max = float(np.min(values)), float(np.max(values))
        padding = max((y_max - y_min) * 0.05, 0.1)
        inputs["x_min"].setValue(x_min); inputs["x_max"].setValue(x_max)
        inputs["y_min"].setValue(y_min - padding); inputs["y_max"].setValue(y_max + padding)
        self._set_tl_plot_range(inputs)

    def load_tl_from_frf_files(self):
        """Lê H31/H32/H34 das cargas A e B e gera uma curva de TL."""

        dialog = QDialog(self)
        dialog.setWindowTitle("Ler FRFs para calcular TL")
        dialog.setMinimumWidth(700)
        layout = QVBoxLayout(dialog)

        instruction = QLabel(
            "Associe cada arquivo CSV à FRF indicada na mesma linha. "
            "Os seis arquivos devem usar o mesmo vetor de frequência."
        )
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        form = QFormLayout()
        file_inputs = {}

        for step in TransmissionLossExperiment.MEASUREMENT_SEQUENCE:
            filepath_input = QLineEdit()
            filepath_input.setReadOnly(True)
            choose_button = QPushButton("Selecionar...")
            choose_button.clicked.connect(
                lambda _, field=filepath_input, label=step.value:
                    self._choose_frf_file(field, label)
            )
            row = QHBoxLayout()
            row.addWidget(filepath_input, stretch=1)
            row.addWidget(choose_button)
            form.addRow(f"{step.value}:", row)
            file_inputs[step] = filepath_input

        layout.addLayout(form)

        name_input = QLineEdit("TL importada")
        layout.addWidget(QLabel("Nome da curva:"))
        layout.addWidget(name_input)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_button = QPushButton("Cancelar")
        import_button = QPushButton("Ler FRFs e calcular TL")
        cancel_button.clicked.connect(dialog.reject)
        import_button.clicked.connect(dialog.accept)
        buttons.addWidget(cancel_button)
        buttons.addWidget(import_button)
        layout.addLayout(buttons)

        if dialog.exec() != QDialog.Accepted:

            return

        paths = {
            step: field.text().strip()
            for step, field in file_inputs.items()
        }

        missing = [step.value for step, path in paths.items() if not path]
        if missing:

            QMessageBox.warning(
                self,
                "Ler FRFs",
                "Selecione um arquivo para: " + ", ".join(missing),
            )

            return

        curve_name = name_input.text().strip()
        if not curve_name:

            QMessageBox.warning(
                self,
                "Ler FRFs",
                "Informe um nome para a curva de TL.",
            )

            return

        imported = {}
        for step, path in paths.items():
            try:
                data = pd.read_csv(path, sep=None, engine="python")
                required = {"frequency_Hz", "H_real", "H_imag"}
                if not required.issubset(data.columns):
                    raise ValueError("requer frequency_Hz, H_real e H_imag")
                frequency = pd.to_numeric(data["frequency_Hz"], errors="coerce").to_numpy()
                H = (pd.to_numeric(data["H_real"], errors="coerce").to_numpy()
                     + 1j * pd.to_numeric(data["H_imag"], errors="coerce").to_numpy())
                valid = (data["valid"].astype(bool).to_numpy()
                         if "valid" in data else np.isfinite(H))
                if not np.all(np.isfinite(frequency) & np.isfinite(H)):
                    raise ValueError("possui frequências ou FRFs inválidas")
                zeros = np.zeros(frequency.size)
                frf = FRFResult(frequency, H, np.ones(frequency.size), zeros, zeros,
                                np.zeros(frequency.size, dtype=complex), valid)
                result = FRFMeasurementResult(frf, 0, 0, 0, 0, 0, 0, [], None)
                imported[step] = StoredTLMeasurement(
                    step, result, MeasurementAcceptance.ACCEPTED)
            except Exception as error:
                QMessageBox.warning(self, "Ler FRFs",
                    f"Não foi possível ler {step.value}: {error}")
                return

        try:
            imported_experiment = TransmissionLossExperiment(self.controller, self.config)
            imported_experiment.measurements = imported
            imported_experiment.state = TLExperimentState.READY_TO_PROCESS
            result = imported_experiment.process()
            mask = np.isfinite(result.transmission_loss)
            self._add_tl_curve(
                result.frequency[mask], result.transmission_loss[mask], curve_name,
                (result.valid_frequency_range.minimum,
                 result.valid_frequency_range.maximum),
            )
            self.tl_active_valid_range = (result.valid_frequency_range.minimum,
                                          result.valid_frequency_range.maximum)
            self.fit_tl_plot()
            self._update_controls()
        except TransmissionLossError as error:
            QMessageBox.warning(self, "Ler FRFs", str(error))

    def _choose_frf_file(self, field: QLineEdit, step_name: str):
        """Seleciona o CSV para uma FRF já identificada no diálogo."""

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            f"Selecione a FRF {step_name}",
            "",
            "Arquivos CSV (*.csv);;Todos os arquivos (*)",
        )

        if filepath:

            field.setText(filepath)

    # ========================================================
    # CURVAS DE TL
    # ========================================================

    def _add_tl_curve(
        self,
        frequency: np.ndarray,
        transmission_loss: np.ndarray,
        name: str,
        valid_frequency_range: tuple[float, float] | None = None,
    ) -> dict:

        colors = [
            "#2979FF",
            "#D50000",
            "#00A152",
            "#AA00FF",
            "#FF6D00",
            "#00838F",
            "#6D4C41",
        ]

        color = colors[
            len(self.tl_curve_entries) % len(colors)
        ]

        curve = self.tl_plot.plot(
            frequency,
            transmission_loss,
            name=name,
            pen=pg.mkPen(
                color,
                width=2,
            ),
        )

        checkbox = QCheckBox(name)

        checkbox.setChecked(True)

        checkbox.setStyleSheet(
            f"color: {color}; font-weight: bold;"
        )

        checkbox.toggled.connect(
            lambda visible, plot_curve=curve:
                plot_curve.setVisible(visible)
        )

        entry = {
            "curve": curve,
            "checkbox": checkbox,
            "name": name,
            "valid_frequency_range": valid_frequency_range,
        }

        self.tl_curve_entries.append(entry)

        self.tl_curve_visibility_layout.insertWidget(
            self.tl_curve_visibility_layout.count() - 1,
            checkbox,
        )

        return entry

    # ========================================================

    def _clear_tl_curves(self):

        for entry in self.tl_curve_entries:

            self.tl_plot.removeItem(
                entry["curve"]
            )

            self.tl_curve_visibility_layout.removeWidget(
                entry["checkbox"]
            )

            entry["checkbox"].deleteLater()

        self.tl_curve_entries.clear()

        self.current_tl_curve = None

    # ========================================================
    # IMPORTAÇÃO DE TL
    # ========================================================

    def import_tl_csv_files(self):

        filepaths, _ = QFileDialog.getOpenFileNames(
            self,
            "Escolha arquivos CSV de TL",
            "",
            "Arquivos CSV (*.csv);;Todos os arquivos (*)",
        )

        if not filepaths:

            return

        errors = []

        imported = 0

        for filepath in filepaths:

            try:

                dataframe = pd.read_csv(
                    filepath,
                    sep=None,
                    engine="python",
                )

                required_columns = {
                    "frequency_Hz",
                    "TL_dB",
                }

                if not required_columns.issubset(
                    dataframe.columns
                ):

                    raise ValueError(
                        "O arquivo deve possuir as colunas "
                        "frequency_Hz e TL_dB."
                    )

                frequency = pd.to_numeric(
                    dataframe["frequency_Hz"],
                    errors="coerce",
                ).to_numpy()

                transmission_loss = pd.to_numeric(
                    dataframe["TL_dB"],
                    errors="coerce",
                ).to_numpy()

                valid = (
                    np.isfinite(frequency)
                    & np.isfinite(transmission_loss)
                )

                if not np.any(valid):

                    raise ValueError(
                        "O arquivo não possui valores finitos "
                        "de frequência e TL."
                    )

                valid_frequency_range = None

                # CSVs exportados pela aplicação trazem a coluna ``valid``.
                # Ela permite recuperar a faixa usada originalmente sem
                # esconder os pontos fora dela no gráfico.
                if "valid" in dataframe.columns:

                    valid_column = (
                        dataframe["valid"]
                        .astype(str)
                        .str.strip()
                        .str.lower()
                        .isin(("true", "1", "sim", "yes"))
                        .to_numpy()
                    )

                    valid_band = valid & valid_column

                    if np.any(valid_band):

                        valid_frequency_range = (
                            float(np.min(frequency[valid_band])),
                            float(np.max(frequency[valid_band])),
                        )

                self._add_tl_curve(
                    frequency=frequency[valid],
                    transmission_loss=(
                        transmission_loss[valid]
                    ),
                    name=Path(filepath).stem,
                    valid_frequency_range=valid_frequency_range,
                )

                imported += 1

            except Exception as error:

                errors.append(
                    f"{Path(filepath).name}: {error}"
                )

        if imported:

            self.fit_tl_plot()

            self._update_controls()

        if errors:

            QMessageBox.warning(
                self,
                "Importação de TL",
                "\n".join(errors),
            )

    # ========================================================
    # EXPORTAÇÃO DO GRÁFICO
    # ========================================================

    def save_tl_plot_png(self):

        if not self.tl_curve_entries:

            QMessageBox.warning(
                self,
                "Salvar gráfico",
                "Adicione ou processe ao menos uma curva de TL.",
            )

            return

        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar gráfico de TL",
            "TL_comparacao.png",
            "Imagem PNG (*.png)",
        )

        if not filepath:

            return

        if not filepath.lower().endswith(".png"):

            filepath += ".png"

        try:

            saved = self.tl_plot.grab().save(
                filepath,
                "PNG",
            )

            if not saved:

                raise OSError(
                    "Não foi possível gravar a imagem PNG."
                )

        except OSError as error:

            QMessageBox.critical(
                self,
                "Salvar gráfico",
                str(error),
            )

    # ========================================================
    # EXPORTAÇÃO DAS CURVAS ACUMULADAS
    # ========================================================

    def save_tl_plot_csv(self):

        if not self.tl_curve_entries:

            QMessageBox.warning(
                self,
                "Salvar gráfico CSV",
                "Adicione ou processe ao menos uma curva de TL.",
            )

            return

        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar curvas de TL",
            "TL_curvas_acumuladas.csv",
            "Arquivos CSV (*.csv)",
        )

        if not filepath:

            return

        if not filepath.lower().endswith(".csv"):

            filepath += ".csv"

        columns = {}

        used_names = set()

        for index, entry in enumerate(
            self.tl_curve_entries,
            start=1,
        ):

            frequency, transmission_loss = entry[
                "curve"
            ].getData()

            curve_name = entry["name"]

            safe_name = "".join(
                character
                if character.isalnum() or character in "_-"
                else "_"
                for character in curve_name
            ).strip("_") or f"curva_{index}"

            original_name = safe_name

            suffix = 2

            while safe_name in used_names:

                safe_name = f"{original_name}_{suffix}"

                suffix += 1

            used_names.add(safe_name)

            columns[
                f"frequency_Hz__{safe_name}"
            ] = pd.Series(frequency)

            columns[
                f"TL_dB__{safe_name}"
            ] = pd.Series(transmission_loss)

        try:

            pd.DataFrame(columns).to_csv(
                filepath,
                index=False,
            )

        except OSError as error:

            QMessageBox.critical(
                self,
                "Salvar gráfico CSV",
                str(error),
            )

    # ========================================================
    # SALVAR
    # ========================================================

    def save_experiment(self):

        if self.tl_result is None:

            QMessageBox.warning(
                self,
                "Salvar",
                "Processe a TL antes de salvar.",
            )

            return

        directory = (
            self.config
            .metadata
            .output_directory
            .strip()
        )

        if not directory:

            QMessageBox.warning(
                self,
                "Diretório de salvamento",
                "Defina o diretório de resultados "
                "na aba Configuração.",
            )

            self.tabs.setCurrentWidget(
                self.config_tab
            )

            return

        try:

            Path(directory).mkdir(
                parents=True,
                exist_ok=True,
            )

            saved = (
                DataExporter
                .export_complete_tl_experiment(
                    config=self.config,
                    measurements=(
                        self.experiment
                        .measurements
                    ),
                    tl_result=(
                        self.tl_result
                    ),
                    directory=directory,
                )
            )

            QMessageBox.information(
                self,
                "Salvamento",
                "Ensaio salvo com sucesso em:\n\n"
                f"{saved['root']}",
            )

        except (
            ExportError,
            OSError,
        ) as error:

            QMessageBox.critical(
                self,
                "Erro ao salvar",
                str(error),
            )

    # ========================================================
    # NOVO MODELO
    # ========================================================

    def start_new_model_experiment(self):
        """
        Prepara a mesma configuração técnica para outro modelo.

        A geometria, aquisição e canais permanecem nos campos de
        configuração. O operador apenas atualiza identificação e
        diretório, aplica a configuração e inicia a nova sequência.
        """

        if (
            self.measurement_in_progress
            or self.measurement_waiting_for_monitor
        ):

            QMessageBox.warning(
                self,
                "Novo ensaio",
                "Aguarde o término ou cancele a medição atual.",
            )

            return

        answer = QMessageBox.question(
            self,
            "Novo ensaio / modelo",
            "O resultado atual será removido da interface.\n\n"
            "Salve o ensaio atual antes de continuar, caso ainda "
            "não o tenha salvo.\n\n"
            "Deseja preparar uma nova sequência de TL?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if answer != QMessageBox.Yes:

            return

        # O monitor do modelo anterior não deve permanecer com a DAQ aberta
        # enquanto o operador revisa a configuração do próximo ensaio.
        # Os campos da aba Configuração não são alterados aqui.
        if not self.stop_monitoring(wait=True):

            QMessageBox.warning(
                self,
                "Novo ensaio",
                "Não foi possível encerrar o monitoramento contínuo. "
                "Aguarde alguns segundos e tente novamente.",
            )

            return

        self._clear_monitoring_data()

        self.experiment.reset()

        self.last_measurement = None

        self.displayed_measurement_frf = None

        self.coherence_frozen_to_measurement = False

        self.tl_result = None

        self.progress_bar.setValue(0)

        self.quality_status_label.setText("-")

        self.coherence_mean_label.setText("-")

        self.coherence_min_label.setText("-")

        self.valid_points_label.setText("-")

        self.clipping_label.setText("-")

        self._clear_tl_curves()

        self.result_range_label.setText("-")

        self.result_points_label.setText("-")

        self.instruction_label.setText(
            "Atualize a identificação e o diretório, aplique a "
            "configuração e inicie o novo ensaio."
        )

        self._set_status_banner(
            "NOVO MODELO — CONFIGURE A IDENTIFICAÇÃO",
            "idle",
        )

        self.tabs.setCurrentWidget(
            self.config_tab
        )

        self._update_controls()

    # ========================================================
    # CONTROLES
    # ========================================================

    def _update_controls(self):

        state = self.experiment.state

        acquisition_busy = (
            self.measurement_in_progress
            or
            self.measurement_waiting_for_monitor
        )

        # ====================================================
        # MEDIR
        # ====================================================

        self.measure_button.setEnabled(
            (
                state
                ==
                TLExperimentState.READY
            )
            and
            not acquisition_busy
        )

        # ====================================================
        # CANCELAR
        # ====================================================

        self.cancel_button.setEnabled(
            acquisition_busy
        )

        # ====================================================
        # REPETIR
        # ====================================================

        self.repeat_button.setEnabled(
            (
                state
                ==
                TLExperimentState.AWAITING_REVIEW
            )
            and
            not acquisition_busy
        )

        # ====================================================
        # ACEITAR
        # ====================================================

        self.accept_button.setEnabled(
            (
                state
                ==
                TLExperimentState.AWAITING_REVIEW
            )
            and
            not acquisition_busy
        )

        # ====================================================
        # ACEITAR COM AVISO
        # ====================================================

        self.accept_warning_button.setEnabled(
            (
                state
                ==
                TLExperimentState.AWAITING_REVIEW
            )
            and
            not acquisition_busy
            and
            self.last_measurement is not None
            and
            self.last_measurement
            .quality
            .status
            ==
            MeasurementQualityStatus.REVIEW
        )

        # ====================================================
        # CARGA
        # ====================================================

        self.confirm_load_button.setEnabled(
            (
                state
                ==
                TLExperimentState.WAITING_LOAD_CHANGE
            )
            and
            not acquisition_busy
        )

        # ====================================================
        # PROCESSAR
        # ====================================================

        self.process_button.setEnabled(
            (
                state
                ==
                TLExperimentState.READY_TO_PROCESS
            )
            and
            not acquisition_busy
        )

        # ====================================================
        # SALVAR
        # ====================================================

        self.save_button.setEnabled(
            self.tl_result is not None
        )

        self.import_tl_button.setEnabled(
            not acquisition_busy
        )

        self.fit_tl_button.setEnabled(
            bool(self.tl_curve_entries)
        )

        self.save_tl_png_button.setEnabled(
            bool(self.tl_curve_entries)
        )

        self.save_tl_csv_button.setEnabled(
            bool(self.tl_curve_entries)
        )

        self.new_model_button.setEnabled(
            self.tl_result is not None
            and not acquisition_busy
        )

        # ====================================================
        # REINICIAR
        # ====================================================

        self.restart_button.setEnabled(
            not acquisition_busy
        )

        # ====================================================
        # CONFIGURAÇÃO
        # ====================================================

        self.apply_config_button.setEnabled(
            not acquisition_busy
        )

        self.refresh_daq_button.setEnabled(
            not acquisition_busy
        )

    # ========================================================
    # FECHAMENTO
    # ========================================================

    def closeEvent(
        self,
        event,
    ):

        # ====================================================
        # IMPEDE NOVOS INÍCIOS
        # ====================================================

        self.measurement_waiting_for_monitor = False

        self.monitor_update_timer.stop()

        # ====================================================
        # MONITOR
        # ====================================================

        if self.monitoring_worker is not None:

            self.monitoring_worker.request_stop()

        if (
            self.monitoring_thread is not None
            and
            self.monitoring_thread.isRunning()
        ):

            self.monitoring_thread.wait(
                5000
            )

        # ====================================================
        # MEDIÇÃO OFICIAL
        # ====================================================

        if self.measurement_in_progress:

            self.controller.cancel()

            if (
                self.measurement_thread is not None
                and
                self.measurement_thread.isRunning()
            ):

                self.measurement_thread.quit()

                self.measurement_thread.wait(
                    5000
                )

        # ====================================================
        # POP-UPS
        # ====================================================

        if self.time_popup is not None:

            self.time_popup.close()

        if self.spectrum_popup is not None:

            self.spectrum_popup.close()

        if self.coherence_popup is not None:

            self.coherence_popup.close()

        # ====================================================
        # DAQ
        # ====================================================

        try:

            self.daq.disconnect()

        finally:

            event.accept()
