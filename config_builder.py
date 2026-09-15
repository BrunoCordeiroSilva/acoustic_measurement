"""Construção visual da aba Configurar."""

import pyqtgraph as pg
from config import WindowType
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import *


def build_config_tab(window):

        # Em telas menores a configuração pode exceder a área visível.
        # A rolagem preserva os grupos e a ordem atuais, sem ocultar
        # campos de preenchimento ou botões.
        tab_layout = QVBoxLayout(window.config_tab)

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

        window.device_combo = QComboBox()

        window.device_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        window.refresh_daq_button = QPushButton(
            "Detectar DAQ"
        )

        window.refresh_daq_button.clicked.connect(
            window.refresh_devices
        )

        daq_layout.addWidget(
            QLabel("Dispositivo:"),
            0,
            0,
        )

        daq_layout.addWidget(
            window.device_combo,
            0,
            1,
        )

        daq_layout.addWidget(
            window.refresh_daq_button,
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

        window.temperature_input = QDoubleSpinBox()

        window.temperature_input.setRange(
            -20.0,
            60.0,
        )

        window.temperature_input.setDecimals(2)

        window.temperature_input.setValue(
            window.config.acoustics.temperature_c
        )

        window.temperature_input.setSuffix(
            " °C"
        )

        window.sound_speed_label = QLabel()

        acoustic_form.addRow(
            "Temperatura:",
            window.temperature_input,
        )

        acoustic_form.addRow(
            "Velocidade do som:",
            window.sound_speed_label,
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

        window.reference_channel_combo = QComboBox()

        window.mobile_channel_combo = QComboBox()

        for combo in (
            window.reference_channel_combo,
            window.mobile_channel_combo,
        ):

            combo.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )

        window.reference_sensitivity_input = (
            QDoubleSpinBox()
        )

        window.mobile_sensitivity_input = (
            QDoubleSpinBox()
        )

        for spinbox in (
            window.reference_sensitivity_input,
            window.mobile_sensitivity_input,
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
            window.reference_channel_combo,
            1,
            1,
        )

        microphone_layout.addWidget(
            window.reference_sensitivity_input,
            1,
            2,
        )

        microphone_layout.addWidget(
            QLabel("Móvel"),
            2,
            0,
        )

        microphone_layout.addWidget(
            window.mobile_channel_combo,
            2,
            1,
        )

        microphone_layout.addWidget(
            window.mobile_sensitivity_input,
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

        window.diameter_input = QDoubleSpinBox()

        window.spacing12_input = QDoubleSpinBox()

        window.spacing34_input = QDoubleSpinBox()

        for spinbox in (
            window.diameter_input,
            window.spacing12_input,
            window.spacing34_input,
        ):

            spinbox.setRange(
                0.1,
                1000.0,
            )

            spinbox.setDecimals(2)

            spinbox.setSuffix(
                " mm"
            )

        window.diameter_input.setValue(
            window.config
            .transmission_loss
            .tube_diameter
            * 1000.0
        )

        window.spacing12_input.setValue(
            window.config
            .transmission_loss
            .spacing_12
            * 1000.0
        )

        window.spacing34_input.setValue(
            window.config
            .transmission_loss
            .spacing_34
            * 1000.0
        )

        window.auto_range_checkbox = QCheckBox(
            "Calcular automaticamente"
        )

        window.auto_range_checkbox.setChecked(
            window.config
            .transmission_loss
            .automatic_valid_frequency_range
        )

        window.valid_range_label = QLabel(
            "-"
        )

        geometry_form.addRow(
            "Diâmetro interno:",
            window.diameter_input,
        )

        geometry_form.addRow(
            "Distância 1-2:",
            window.spacing12_input,
        )

        geometry_form.addRow(
            "Distância 3-4:",
            window.spacing34_input,
        )

        geometry_form.addRow(
            "Faixa válida:",
            window.auto_range_checkbox,
        )

        geometry_form.addRow(
            "Resultado:",
            window.valid_range_label,
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

        window.sample_rate_input = QDoubleSpinBox()

        window.sample_rate_input.setRange(
            100.0,
            51200.0,
        )

        window.sample_rate_input.setDecimals(2)

        window.sample_rate_input.setValue(
            window.config
            .acquisition
            .sample_rate
        )

        window.sample_rate_input.setSuffix(
            " Hz"
        )

        window.num_samples_input = QSpinBox()

        window.num_samples_input.setRange(
            128,
            1_000_000,
        )

        window.num_samples_input.setValue(
            window.config
            .acquisition
            .num_samples
        )

        window.num_averages_input = QSpinBox()

        window.num_averages_input.setRange(
            1,
            1000,
        )

        window.num_averages_input.setValue(
            window.config
            .acquisition
            .num_averages
        )

        window.stabilization_input = (
            QDoubleSpinBox()
        )

        window.stabilization_input.setRange(
            0.0,
            60.0,
        )

        window.stabilization_input.setDecimals(2)

        window.stabilization_input.setValue(
            window.config
            .acquisition
            .stabilization_time
        )

        window.stabilization_input.setSuffix(
            " s"
        )

        window.window_combo = QComboBox()

        for window_type in WindowType:

            window.window_combo.addItem(
                window_type.value,
                window_type,
            )

        window.duration_label = QLabel()

        window.df_label = QLabel()

        window.nyquist_label = QLabel()

        window.coherence_min_input = QDoubleSpinBox()

        window.coherence_mean_input = QDoubleSpinBox()

        for spinbox in (
            window.coherence_min_input,
            window.coherence_mean_input,
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

        window.coherence_min_input.setValue(
            window.config.quality.coherence_threshold
        )

        window.coherence_mean_input.setValue(
            window.config.quality.coherence_mean_threshold
        )

        window.coherence_guidance_label = QLabel(
            "Orientação inicial: média ≥ 0,90 e mínima ≥ 0,80. "
            "Ajuste conforme a norma, banda e excitação usadas."
        )

        window.coherence_guidance_label.setWordWrap(
            True
        )

        window.coherence_guidance_label.setStyleSheet(
            "color: #666666;"
        )

        acquisition_form.addRow(
            "Fs:",
            window.sample_rate_input,
        )

        acquisition_form.addRow(
            "N:",
            window.num_samples_input,
        )

        acquisition_form.addRow(
            "Número de médias:",
            window.num_averages_input,
        )

        acquisition_form.addRow(
            "Janela:",
            window.window_combo,
        )

        acquisition_form.addRow(
            "Estabilização:",
            window.stabilization_input,
        )

        acquisition_form.addRow(
            "Duração do bloco:",
            window.duration_label,
        )

        acquisition_form.addRow(
            "Resolução Δf:",
            window.df_label,
        )

        acquisition_form.addRow(
            "Nyquist:",
            window.nyquist_label,
        )

        acquisition_form.addRow(
            "Coerência mínima aceita:",
            window.coherence_min_input,
        )

        acquisition_form.addRow(
            "Coerência média aceita:",
            window.coherence_mean_input,
        )

        acquisition_form.addRow(
            "Recomendação:",
            window.coherence_guidance_label,
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

        window.experiment_name_input = QLineEdit()

        window.experiment_number_input = QLineEdit()

        window.operator_input = QLineEdit()

        window.notes_input = QTextEdit()

        window.notes_input.setMaximumHeight(
            90
        )

        metadata_form.addRow(
            "Nome:",
            window.experiment_name_input,
        )

        metadata_form.addRow(
            "Número:",
            window.experiment_number_input,
        )

        metadata_form.addRow(
            "Operador:",
            window.operator_input,
        )

        metadata_form.addRow(
            "Observações:",
            window.notes_input,
        )

        config_grid.addWidget(
            metadata_group,
            2,
            1,
        )

        # Em largura normal, os grupos permanecem em duas colunas. Abaixo
        # desse limite, eles passam temporariamente a uma coluna, evitando
        # que os campos de cada grupo sejam estreitados ou cortados.
        window.config_grid = config_grid

        window.config_groups = (
            daq_group,
            acoustic_group,
            microphone_group,
            geometry_group,
            acquisition_group,
            metadata_group,
        )

        window.config_grid_is_compact = None

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

        window.output_directory_input = QLineEdit()

        window.output_directory_button = QPushButton(
            "Procurar..."
        )

        window.output_directory_button.clicked.connect(
            window.browse_output_directory
        )

        save_layout.addWidget(
            QLabel("Diretório:")
        )

        save_layout.addWidget(
            window.output_directory_input,
            stretch=1,
        )

        save_layout.addWidget(
            window.output_directory_button
        )

        main_layout.addWidget(
            save_group
        )

        # ====================================================
        # APLICAR
        # ====================================================

        window.apply_config_button = QPushButton(
            "Aplicar configuração"
        )

        window.apply_config_button.clicked.connect(
            lambda:
                window.apply_configuration(
                    show_message=True
                )
        )

        main_layout.addWidget(
            window.apply_config_button
        )

        main_layout.addStretch()

        # ====================================================
        # SIGNALS
        # ====================================================

        window.sample_rate_input.valueChanged.connect(
            window._update_acquisition_labels
        )

        window.num_samples_input.valueChanged.connect(
            window._update_acquisition_labels
        )

        window.temperature_input.valueChanged.connect(
            window._update_acoustic_labels
        )

        window.diameter_input.valueChanged.connect(
            window._update_valid_range_preview
        )

        window.spacing12_input.valueChanged.connect(
            window._update_valid_range_preview
        )

        window.spacing34_input.valueChanged.connect(
            window._update_valid_range_preview
        )

        # Cada dispositivo possui seus próprios canais físicos. Sem esta
        # conexão, os combos de referência e móvel continuavam mostrando os
        # canais do primeiro dispositivo detectado.
        window.device_combo.currentTextChanged.connect(
            window._device_selection_changed
        )

        # ====================================================
        # LABELS INICIAIS
        # ====================================================

        window._update_acquisition_labels()

        window._update_acoustic_labels()

        window._update_valid_range_preview()

        window._update_config_grid_layout()

        # A largura definitiva da aba só existe após o primeiro ciclo de
        # layout da janela; então reavaliamos a disposição nesse momento.
        QTimer.singleShot(
            0,
            window._update_config_grid_layout,
        )

    # ========================================================
    # LAYOUT RESPONSIVO DA CONFIGURAÇÃO
    # ========================================================
