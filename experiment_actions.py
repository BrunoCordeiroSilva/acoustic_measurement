"""Fluxo operacional do ensaio de perda de transmissão."""

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QMessageBox
from acquisition_worker import MeasurementWorker
from acquisition_controller import MeasurementQualityStatus
from experiment_tab import format_quality_values
from experiments.transmission_loss import TransmissionLossError, TLExperimentState, MeasurementAcceptance
from ui_constants import COHERENCE_COLOR, MOBILE_COLOR, REFERENCE_COLOR

class ExperimentActionsMixin:
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

        quality_values = format_quality_values(quality)

        self.quality_status_label.setText(quality_values["status"])
        self.coherence_mean_label.setText(quality_values["mean"])
        self.coherence_min_label.setText(quality_values["minimum"])
        self.valid_points_label.setText(quality_values["valid_points"])
        self.clipping_label.setText(quality_values["clipping"])

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

        clear_quality_labels(self)

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
