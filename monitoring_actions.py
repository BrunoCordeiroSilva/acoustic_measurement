"""Pop-ups, estado e wrappers do monitoramento."""

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QMessageBox
from monitoring import *
from plot_widgets import PlotPopup
from microphone_plots import create_microphone_curves, set_microphone_curves, spectra_from_frfs

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

        popup.curves = create_microphone_curves(popup.plot)
        if self.measurement_in_progress and self.displayed_measurement_frfs is not None:
            frequency, spectra = spectra_from_frfs(self.displayed_measurement_frfs)
            set_microphone_curves(popup.curves, frequency, spectra)
        elif self.last_monitoring_data is not None:
            data = self.last_monitoring_data
            set_microphone_curves(popup.curves, data.frequency, data.spectra)
        elif self.displayed_measurement_frfs is not None:
            frequency, spectra = spectra_from_frfs(self.displayed_measurement_frfs)
            set_microphone_curves(popup.curves, frequency, spectra)

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

        popup.curves = create_microphone_curves(popup.plot, coherence=True)
        if self.coherence_frozen_to_measurement and self.displayed_measurement_frfs is not None:
            frfs = self.displayed_measurement_frfs
            frequency = next(iter(frfs.values())).frequency
            set_microphone_curves(
                popup.curves, frequency,
                {position: frf.coherence for position, frf in frfs.items()},
            )
        elif self.last_monitoring_data is not None:
            data = self.last_monitoring_data
            set_microphone_curves(popup.curves, data.coherence_frequency, data.coherences)

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

