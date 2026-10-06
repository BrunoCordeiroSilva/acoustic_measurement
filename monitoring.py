"""Contratos e componentes compartilhados do monitoramento contínuo."""

from dataclasses import dataclass
from microphone_plots import set_microphone_curves

import numpy as np

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QMessageBox


@dataclass
class MonitoringData:
    """Pacote espectral mais recente produzido pelo monitoramento visual."""

    frequency: np.ndarray
    spectra: dict[int, np.ndarray]
    coherence_frequency: np.ndarray
    coherences: dict[int, np.ndarray]
    sample_rate: float


def update_monitoring_plots(window, data: MonitoringData) -> None:
    """Atualiza espectro e coerência, incluindo pop-ups visíveis."""

    window.last_monitoring_data = data
    set_microphone_curves(window.spectrum_curves, data.frequency, data.spectra)
    if not window.coherence_frozen_to_measurement:
        set_microphone_curves(window.coherence_curves, data.coherence_frequency, data.coherences)
    if window.spectrum_popup is not None and window.spectrum_popup.isVisible():
        set_microphone_curves(window.spectrum_popup.curves, data.frequency, data.spectra)
    if (
        not window.coherence_frozen_to_measurement
        and window.coherence_popup is not None
        and window.coherence_popup.isVisible()
    ):
        set_microphone_curves(window.coherence_popup.curves, data.coherence_frequency, data.coherences)


def clear_monitoring_plots(window) -> None:
    """Limpa os dados visuais do monitor sem afetar resultados de TL."""
    window.last_monitoring_data = None
    groups = [window.spectrum_curves, window.coherence_curves]
    for popup in (window.spectrum_popup, window.coherence_popup):
        if popup is not None:
            groups.append(popup.curves)
    for curves in groups:
        for curve in curves.values():
            curve.setData([], [])


def stop_monitoring_session(window, wait: bool = False) -> bool:
    """Solicita parada do worker e, opcionalmente, aguarda sua thread."""

    if window.monitoring_worker is None:
        return True
    window.monitoring_stop_requested = True
    window.monitor_update_timer.stop()
    window.monitoring_worker.request_stop()
    if wait and window.monitoring_thread is not None:
        window.monitoring_thread.wait(5000)
        QApplication.processEvents()
        if (
            window.monitoring_thread is not None
            and window.monitoring_thread.isRunning()
        ):
            return False
    return True


def start_monitoring_session(window) -> None:
    """Cria e conecta a sessão de monitoramento visual da janela."""

    if window.measurement_in_progress or window.measurement_waiting_for_monitor:
        return
    if window.monitoring_thread is not None and window.monitoring_thread.isRunning():
        return
    try:
        window.config.tl_channel_indices()
    except ValueError:
        return

    # Importação tardia evita ciclo: o worker também consome MonitoringData.
    from acquisition_worker import MonitoringWorker

    thread = QThread(window)
    worker = MonitoringWorker(
        daq=window.daq,
        config=window.config,
        monitor_num_samples=256,
        coherence_nperseg=512,
    )
    worker.moveToThread(thread)
    window.monitoring_thread = thread
    window.monitoring_worker = worker
    thread.started.connect(worker.run)
    worker.started.connect(window._monitoring_started)
    worker.error.connect(window._monitoring_error)
    worker.done.connect(thread.quit)
    worker.done.connect(worker.deleteLater)
    thread.finished.connect(window._monitoring_thread_finished)
    thread.finished.connect(thread.deleteLater)
    window.monitoring_running = False
    window.monitoring_stop_requested = False
    thread.start()


def mark_monitoring_started(window) -> None:
    """Atualiza o estado visual após o worker iniciar."""

    window.monitoring_running = True
    window.monitor_update_timer.start()


def finish_monitoring_session(window, finished_thread) -> bool:
    """Finaliza somente a sessão que emitiu o sinal de término."""

    if finished_thread is not window.monitoring_thread:
        return False
    window.monitoring_running = False
    window.monitor_update_timer.stop()
    window.monitoring_stop_requested = False
    window.monitoring_thread = None
    window.monitoring_worker = None
    if window.measurement_waiting_for_monitor:
        window.measurement_waiting_for_monitor = False
        window._start_measurement_thread()
    return True


def report_monitoring_error(window, message: str) -> None:
    """Exibe erro somente quando a parada não foi solicitada pela interface."""

    window.monitoring_running = False
    if window.monitoring_stop_requested:
        return
    QMessageBox.warning(
        window,
        "Monitoramento",
        "O monitoramento contínuo foi interrompido.\n\n" + message,
    )
