"""Ações e aplicação de configuração da interface."""

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QFileDialog, QMessageBox
from daq import NIDaqDevice, DAQError
from config import ChannelConfig, SensorType
from config_tab import calculate_valid_range_preview, format_acquisition_metrics, populate_channel_combos, populate_device_combo

class ConfigActionsMixin:
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

            populate_channel_combos(
                self.reference_channel_combo,
                self.mobile_channel_combo,
                channels,
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

            # Carrega a lista sem disparar a troca antes do término.
            selected_device = populate_device_combo(
                self.device_combo,
                devices,
            )

            self._device_selection_changed(
                selected_device
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

        duration, resolution, nyquist = format_acquisition_metrics(fs, n)
        self.duration_label.setText(duration)
        self.df_label.setText(resolution)
        self.nyquist_label.setText(nyquist)

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

            spacing_min, f_max = calculate_valid_range_preview(
                self.temperature_input.value(),
                self.diameter_input.value() / 1000.0,
                self.spacing12_input.value() / 1000.0,
                self.spacing34_input.value() / 1000.0,
                self.sample_rate_input.value(),
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

