from __future__ import annotations

from PySide6.QtCore import (
    QObject,
    Signal,
    Slot,
)

from acquisition_controller import (
    AcquisitionCancelled,
    AcquisitionControllerError,
)

from experiments.transmission_loss import (
    TransmissionLossError,
)


# ============================================================
# WORKER DE MEDIÇÃO
# ============================================================

class MeasurementWorker(QObject):
    """
    Executa uma medição oficial de FRF em uma thread
    separada da interface.

    A interface permanece responsiva enquanto:

        - aguarda estabilização
        - realiza médias
        - processa FRF
        - calcula coerência

    O worker não manipula widgets diretamente.
    """

    # --------------------------------------------------------
    # SINAIS
    # --------------------------------------------------------

    progress = Signal(
        int,
        int,
    )

    message = Signal(
        str,
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
    # INICIALIZAÇÃO
    # ========================================================

    def __init__(
        self,
        experiment,
    ):

        super().__init__()

        self.experiment = experiment

        self._running = False

    # ========================================================
    # EXECUÇÃO
    # ========================================================

    @Slot()
    def run(self):
        """
        Executa a medição da etapa atual.
        """

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
    # CALLBACK DE PROGRESSO
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
    # CALLBACK DE MENSAGEM
    # ========================================================

    def _message_callback(
        self,
        message: str,
    ):

        self.message.emit(
            message
        )