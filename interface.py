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
)

from monitoring import (
    MonitoringData,
    clear_monitoring_plots,
    finish_monitoring_session,
    mark_monitoring_started,
    report_monitoring_error,
    start_monitoring_session,
    stop_monitoring_session,
    update_monitoring_plots,
)

from experiments.transmission_loss import (
    TransmissionLossExperiment,
    TransmissionLossError,
    TLExperimentState,
    TLMeasurementStep,
    StoredTLMeasurement,
    MeasurementAcceptance,
)

from results_tab import (
    FRFFileSelectionDialog,
    ResultsTabView,
    TLPlotController,
    build_results_tab,
    build_tl_curve_dataframe,
    prepare_tl_plot_data,
    read_frf_csv,
    read_tl_csv,
    save_plot_png,
)

from plot_widgets import PlotPopup

from plot_builder import create_plot_panel

from ui_constants import (
    COHERENCE_COLOR,
    MOBILE_COLOR,
    REFERENCE_COLOR,
)

from config_tab import (
    calculate_valid_range_preview,
    format_acquisition_metrics,
    populate_channel_combos,
    populate_device_combo,
)

from config_builder import build_config_tab

from experiment_tab import clear_quality_labels, format_quality_values

from experiment_builder import build_experiment_tab

from experiment_actions import ExperimentActionsMixin

from results_actions import ResultsActionsMixin

from config_actions import ConfigActionsMixin

from monitoring_actions import MonitoringActionsMixin

from window_lifecycle import WindowLifecycleMixin

from exporter import (
    DataExporter,
    ExportError,
)


# ============================================================
# CORES
# ============================================================

# ============================================================
# JANELA PRINCIPAL
# ============================================================

class MainWindow(
    WindowLifecycleMixin,
    MonitoringActionsMixin,
    ConfigActionsMixin,
    ResultsActionsMixin,
    ExperimentActionsMixin,
    QMainWindow,
):

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

        build_config_tab(self)

        return

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

        return create_plot_panel(
            title,
            plot_widget,
            fit_callback,
            popup_callback,
        )

    def _build_experiment_tab(self):

        build_experiment_tab(self)

        return

    def _build_results_tab(self):

        build_results_tab(self)

        return
