"""Atualização de controles e encerramento seguro da janela."""

from experiments.transmission_loss import TLExperimentState

class WindowLifecycleMixin:
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
