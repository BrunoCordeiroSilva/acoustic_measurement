"""Pop-ups, estado e wrappers do monitoramento."""

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QMessageBox
from monitoring import *
from plot_widgets import PlotPopup
from ui_constants import COHERENCE_COLOR, MOBILE_COLOR, REFERENCE_COLOR

class MonitoringActionsMixin:
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

        start_monitoring_session(self)

        return

    def stop_monitoring(
        self,
        wait: bool = False,
    ) -> bool:

        return stop_monitoring_session(self, wait)

    # ========================================================

    def _monitoring_started(self):
        mark_monitoring_started(self)

    # ========================================================

    def _monitoring_thread_finished(
        self,
        finished_thread: QThread | None = None,
    ):

        if finished_thread is None:
            finished_thread = self.sender()
        finish_monitoring_session(self, finished_thread)

    # ========================================================

    def _monitoring_error(
        self,
        message: str,
    ):

        report_monitoring_error(self, message)

    # ========================================================

    def _clear_monitoring_data(self) -> None:
        """Remove dados e curvas pertencentes ao monitoramento ao vivo."""
        clear_monitoring_plots(self)

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
        update_monitoring_plots(self, data)

    # ========================================================
    # DIRETÓRIO
    # ========================================================

