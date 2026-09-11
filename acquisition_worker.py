from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from threading import Event

import numpy as np

from PySide6.QtCore import (
    QObject,
    Signal,
    Slot,
)

from acquisition_controller import (
    AcquisitionCancelled,
    AcquisitionControllerError,
)

from daq import (
    DAQError,
)

from signal_processing import (
    SignalProcessor,
    FRFProcessor,
    SignalProcessingError,
)

from experiments.transmission_loss import (
    TransmissionLossError,
)


# ============================================================
# RESULTADO DO MONITORAMENTO
# ============================================================

@dataclass
class MonitoringData:
    """
    Pacote enviado pelo MonitoringWorker para a interface.

    O monitoramento é apenas visual e não interfere
    nas medições oficiais usadas para calcular a TL.
    """

    time: np.ndarray

    reference_signal: np.ndarray

    mobile_signal: np.ndarray

    frequency: np.ndarray

    reference_spectrum: np.ndarray

    mobile_spectrum: np.ndarray

    coherence_frequency: np.ndarray

    coherence: np.ndarray

    sample_rate: float


# ============================================================
# WORKER DE MEDIÇÃO OFICIAL
# ============================================================

class MeasurementWorker(QObject):
    """
    Executa uma medição oficial de FRF em uma thread
    separada da interface.
    """

    progress = Signal(
        int,
        int,
    )

    message = Signal(
        str,
    )

    frf_updated = Signal(
        object,
    )

    finished = Signal(
        object,
    )

    error = Signal(
        str,
    )

    cancelled = Signal()

    done = Signal()

    # ========================================================

    def __init__(
        self,
        experiment,
    ):

        super().__init__()

        self.experiment = experiment

        self._running = False

    # ========================================================

    @Slot()
    def run(self):

        if self._running:

            return

        self._running = True

        try:

            result = (
                self.experiment
                .measure_current_step(
                    progress_callback=(
                        self._progress_callback
                    ),
                    message_callback=(
                        self._message_callback
                    ),
                    frf_update_callback=(
                        self._frf_update_callback
                    ),
                )
            )

            self.finished.emit(
                result
            )

        except AcquisitionCancelled:

            self.cancelled.emit()

        except (
            TransmissionLossError,
            AcquisitionControllerError,
        ) as exc:

            self.error.emit(
                str(exc)
            )

        except Exception as exc:

            self.error.emit(
                f"Erro inesperado durante "
                f"a aquisição:\n{exc}"
            )

        finally:

            self._running = False

            self.done.emit()

    # ========================================================

    def _progress_callback(
        self,
        current: int,
        total: int,
    ):

        self.progress.emit(
            current,
            total,
        )

    # ========================================================

    def _message_callback(
        self,
        message: str,
    ):

        self.message.emit(
            message
        )

    # ========================================================

    def _frf_update_callback(
        self,
        frf,
        current: int,
        total: int,
    ):

        self.frf_updated.emit(
            frf
        )


# ============================================================
# WORKER DE MONITORAMENTO CONTÍNUO
# ============================================================

class MonitoringWorker(QObject):
    """
    Realiza aquisições sucessivas para visualização.

    IMPORTANTE:

    Este worker NÃO gera nenhuma das seis FRFs oficiais
    H31/H32/H34.

    Ele existe somente para:

        - sinal temporal em tempo real
        - espectro em tempo real
        - coerência em tempo real

    Quando uma medição oficial começa, este worker deve
    ser encerrado para liberar a NI-9234.
    """

    data_ready = Signal(
        object
    )

    error = Signal(
        str
    )

    started = Signal()

    done = Signal()

    # ========================================================

    def __init__(
        self,
        daq,
        config,
        monitor_num_samples: int = 2048,
        coherence_nperseg: int = 512,
    ):

        super().__init__()

        self.daq = daq

        self.config = config

        self.monitor_num_samples = (
            monitor_num_samples
        )

        self.coherence_nperseg = (
            coherence_nperseg
        )

        self._stop_event = Event()

        self._running = False

        # ========================================================
        # BUFFER TEMPORAL
        # ========================================================

        self.time_window_seconds = 2.0

        self._reference_buffer = np.array(
            [],
            dtype=np.float64,
        )

        self._mobile_buffer = np.array(
            [],
            dtype=np.float64,
)
        # Número total de amostras adquiridas
        # desde o início deste monitoramento.
        self._total_samples_acquired = 0

    # ========================================================
    # SOLICITA PARADA
    # ========================================================

    def request_stop(self):

        """
        Thread-safe.

        Pode ser chamado diretamente pela interface.
        """

        self._stop_event.set()

    # ========================================================
    # EXECUÇÃO
    # ========================================================

    @Slot()
    def run(self):

        if self._running:

            return

        self._running = True

        self._stop_event.clear()

        try:

            # =================================================
            # CONFIGURAÇÃO ESPECÍFICA DO MONITOR
            # =================================================

            monitor_acquisition = deepcopy(
                self.config.acquisition
            )

            # Não queremos esperar N grande do ensaio
            # para atualizar a interface.

            monitor_acquisition.num_samples = min(
                self.monitor_num_samples,
                self.config.acquisition.num_samples,
            )

            if monitor_acquisition.num_samples < 256:

                monitor_acquisition.num_samples = 256

            # O número de médias não importa no monitor.

            monitor_acquisition.num_averages = 1

            # Não utilizamos tempo de estabilização
            # no monitoramento visual.

            monitor_acquisition.stabilization_time = 0.0

            # =================================================
            # CONFIGURA A DAQ
            # =================================================

            if not self.daq.device_name:

                self.daq.connect()

            self.daq.configure(
                channels=self.config.channels,
                acquisition=monitor_acquisition,
            )

            self.started.emit()

            # =================================================
            # LOOP CONTÍNUO
            # =================================================

            while not self._stop_event.is_set():

                acquisition_data = (
                    self.daq.acquire()
                )

                if self._stop_event.is_set():

                    break

                data = np.asarray(
                    acquisition_data.data
                )

                # ---------------------------------------------
                # Precisamos de dois canais
                # ---------------------------------------------

                if (
                    data.ndim != 2
                    or data.shape[1] < 2
                ):

                    raise RuntimeError(
                        "O monitoramento necessita "
                        "de pelo menos dois canais."
                    )

                sample_rate = float(
                    acquisition_data.sample_rate
                )

                reference_signal = (
                    data[:, 0].copy()
                )

                mobile_signal = (
                    data[:, 1].copy()
                )

                # =================================================
                # TEMPO TOTAL ADQUIRIDO
                # =================================================

                self._total_samples_acquired += (
                    reference_signal.size
                )

                # =================================================
                # BUFFER TEMPORAL CONTÍNUO
                # =================================================

                max_samples = int(
                    sample_rate
                    * self.time_window_seconds
                )

                self._reference_buffer = np.concatenate(
                    (
                        self._reference_buffer,
                        reference_signal,
                    )
                )

                self._mobile_buffer = np.concatenate(
                    (
                        self._mobile_buffer,
                        mobile_signal,
                    )
                )

                # Mantém apenas os últimos 2 segundos

                if self._reference_buffer.size > max_samples:

                    self._reference_buffer = (
                        self._reference_buffer[
                            -max_samples:
                        ]
                    )

                if self._mobile_buffer.size > max_samples:

                    self._mobile_buffer = (
                        self._mobile_buffer[
                            -max_samples:
                        ]
                    )

                # =================================================
                # EIXO DE TEMPO CONTÍNUO
                # =================================================

                num_points = (
                    self._reference_buffer.size
                )

                end_sample = (
                    self._total_samples_acquired
                )

                start_sample = (
                    end_sample
                    -
                    num_points
                )

                time = (
                    np.arange(
                        start_sample,
                        end_sample,
                        dtype=np.float64,
                    )
                    / sample_rate
                )
                # =================================================
                # FFT
                # =================================================

                fft_reference = (
                    SignalProcessor.fft(
                        x=reference_signal,
                        sample_rate=sample_rate,
                        window_type=(
                            monitor_acquisition.window
                        ),
                        remove_dc=True,
                    )
                )

                fft_mobile = (
                    SignalProcessor.fft(
                        x=mobile_signal,
                        sample_rate=sample_rate,
                        window_type=(
                            monitor_acquisition.window
                        ),
                        remove_dc=True,
                    )
                )

                # =================================================
                # COERÊNCIA
                #
                # Aqui usamos vários segmentos dentro de cada
                # bloco. Isso é diferente da medição oficial.
                # =================================================

                nperseg = min(
                    self.coherence_nperseg,
                    reference_signal.size,
                )

                # Evita tamanho muito pequeno.

                nperseg = max(
                    128,
                    nperseg,
                )

                frf_monitor = (
                    FRFProcessor.calculate_frf(
                        x=reference_signal,
                        y=mobile_signal,
                        sample_rate=sample_rate,
                        window_type=(
                            monitor_acquisition.window
                        ),
                        nperseg=nperseg,
                        overlap=0.50,
                        estimator=(
                            monitor_acquisition
                            .frf_estimator
                        ),
                        coherence_threshold=0.0,
                    )
                )

                # =================================================
                # ENVIA PARA GUI
                # =================================================

                monitor_data = MonitoringData(
                    time=time,

                    reference_signal=(
                        self._reference_buffer.copy()
                    ),

                    mobile_signal=(
                        self._mobile_buffer.copy()
                    ),

                    frequency=(
                        fft_reference.frequency
                    ),

                    reference_spectrum=(
                        fft_reference.magnitude
                    ),

                    mobile_spectrum=(
                        fft_mobile.magnitude
                    ),

                    coherence_frequency=(
                        frf_monitor.frequency
                    ),

                    coherence=(
                        frf_monitor.coherence
                    ),

                    sample_rate=sample_rate,
                )

                self.data_ready.emit(
                    monitor_data
                )

        except (
            DAQError,
            SignalProcessingError,
            RuntimeError,
            ValueError,
        ) as exc:

            if not self._stop_event.is_set():

                self.error.emit(
                    str(exc)
                )

        except Exception as exc:

            if not self._stop_event.is_set():

                self.error.emit(
                    f"Erro inesperado no "
                    f"monitoramento:\n{exc}"
                )

        finally:

            self._running = False

            self.done.emit()
