from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Event
from time import monotonic

from typing import Callable, Optional

import numpy as np

from config import (
    AppConfig,
    SensorType,
)

from daq import (
    NIDaqDevice,
    AcquisitionData,
    DAQError,
)

from signal_processing import (
    FRFProcessor,
    FRFResult,
    SignalProcessor,
    SignalProcessingError,
)


# ============================================================
# EXCEÇÕES
# ============================================================

class AcquisitionControllerError(RuntimeError):
    """
    Erro da camada de controle de aquisição.
    """

    pass


class AcquisitionCancelled(
    AcquisitionControllerError
):
    """
    Aquisição cancelada pelo usuário.
    """

    pass


# ============================================================
# STATUS DE QUALIDADE
# ============================================================

class MeasurementQualityStatus(Enum):

    VALID = "VÁLIDO"

    REVIEW = "REVISAR"


# ============================================================
# MÉTRICAS DOS CANAIS
# ============================================================

@dataclass
class ChannelMetrics:
    """
    Métricas acumuladas de um canal durante
    uma medição completa.
    """

    channel_name: str

    physical_channel: str

    rms: float

    peak: float

    spl: float | None

    clipping_detected: bool

    clipping_ratio: float | None


# ============================================================
# RELATÓRIO DE QUALIDADE
# ============================================================

@dataclass
class MeasurementQualityReport:
    """
    Resultado da avaliação automática de qualidade.
    """

    status: MeasurementQualityStatus

    coherence_threshold: float

    valid_frequency_min: float

    valid_frequency_max: float

    coherence_mean: float

    coherence_min: float

    coherence_valid_percentage: float

    clipping_detected: bool

    warnings: list[str]

    @property
    def is_valid(self) -> bool:

        return (
            self.status
            == MeasurementQualityStatus.VALID
        )


# ============================================================
# RESULTADO DA MEDIÇÃO DE FRF
# ============================================================

@dataclass
class FRFMeasurementResult:
    """
    Resultado completo de uma medição de FRF
    com várias médias.
    """

    frf: FRFResult

    requested_averages: int

    completed_averages: int

    sample_rate: float

    num_samples_per_block: int

    block_duration: float

    total_measurement_time: float

    channel_metrics: list[ChannelMetrics]

    quality: MeasurementQualityReport


# ============================================================
# CALLBACKS
# ============================================================

ProgressCallback = Callable[
    [int, int],
    None,
]

MessageCallback = Callable[
    [str],
    None,
]

FRFUpdateCallback = Callable[
    [FRFResult, int, int],
    None,
]


# ============================================================
# CONTROLLER
# ============================================================

class AcquisitionController:
    """
    Coordena:

        config.py
            ↓
        daq.py
            ↓
        signal_processing.py

    Responsabilidades:

    - configurar a DAQ
    - controlar tempo de estabilização
    - executar várias aquisições
    - acumular autoespectros
    - acumular espectros cruzados
    - calcular FRF média
    - calcular coerência
    - calcular RMS / SPL / pico
    - detectar possível clipping
    - avaliar qualidade da medição

    Esta classe NÃO conhece:

    - H31
    - H32
    - H34
    - Carga A
    - Carga B
    - ABCD
    - TL
    """

    def __init__(
        self,
        daq: NIDaqDevice,
        config: AppConfig,
    ):

        self.daq = daq

        self.config = config

        self._cancel_event = Event()

    # ========================================================
    # CANCELAMENTO
    # ========================================================

    def cancel(self) -> None:
        """
        Solicita cancelamento da aquisição.

        Posteriormente este método poderá ser chamado
        pelo botão "Cancelar" da interface.
        """

        self._cancel_event.set()

    # ========================================================

    def reset_cancel(self) -> None:

        self._cancel_event.clear()

    # ========================================================

    def _check_cancelled(self) -> None:

        if self._cancel_event.is_set():

            raise AcquisitionCancelled(
                "Aquisição cancelada pelo usuário."
            )

    # ========================================================
    # CONFIGURAÇÃO DA DAQ
    # ========================================================

    def configure_hardware(self) -> None:
        """
        Valida a configuração global e configura
        o hardware.
        """

        try:

            self.config.validate()

            if not self.daq.device_name:

                self.daq.connect()

            self.daq.configure(
                channels=self.config.channels,
                acquisition=self.config.acquisition,
            )

        except (
            ValueError,
            DAQError,
        ) as exc:

            raise AcquisitionControllerError(
                "Não foi possível configurar "
                "o sistema de aquisição."
            ) from exc

    # ========================================================
    # TEMPO DE ESTABILIZAÇÃO
    # ========================================================

    def _wait_stabilization(
        self,
        message_callback:
            Optional[MessageCallback] = None,
    ) -> None:
        """
        Aguarda o tempo configurado antes das médias.

        A espera é interrompível pelo método cancel().
        """

        stabilization_time = (
            self.config
            .acquisition
            .stabilization_time
        )

        if stabilization_time <= 0:

            return

        if message_callback is not None:

            message_callback(
                "Aguardando estabilização..."
            )

        start = monotonic()

        while (
            monotonic() - start
            < stabilization_time
        ):

            self._check_cancelled()

            # Event.wait permite cancelar sem
            # bloquear o programa por vários segundos.

            if self._cancel_event.wait(
                timeout=0.05
            ):

                raise AcquisitionCancelled(
                    "Aquisição cancelada "
                    "durante a estabilização."
                )

    # ========================================================
    # IDENTIFICAÇÃO DOS CANAIS ATIVOS
    # ========================================================

    def _get_active_channels(self):

        return [
            channel
            for channel
            in self.config.channels
            if channel.enabled
        ]

    # ========================================================
    # VALIDAÇÃO DO PAR DE FRF
    # ========================================================

    def _validate_frf_channels(
        self,
        reference_channel_index: int,
        response_channel_index: int,
    ) -> None:

        active_channels = (
            self._get_active_channels()
        )

        number_channels = len(
            active_channels
        )

        if (
            reference_channel_index < 0
            or
            reference_channel_index
            >= number_channels
        ):

            raise AcquisitionControllerError(
                "Índice do canal de referência "
                "inválido."
            )

        if (
            response_channel_index < 0
            or
            response_channel_index
            >= number_channels
        ):

            raise AcquisitionControllerError(
                "Índice do canal de resposta "
                "inválido."
            )

        if (
            reference_channel_index
            == response_channel_index
        ):

            raise AcquisitionControllerError(
                "Os canais de referência e resposta "
                "não podem ser iguais."
            )

    # ========================================================
    # MEDIÇÃO DE FRF
    # ========================================================

    def acquire_frf(
        self,
        reference_channel_index: int = 0,
        response_channel_index: int = 1,
        progress_callback:
            Optional[ProgressCallback] = None,
        message_callback:
            Optional[MessageCallback] = None,
        frf_update_callback:
            Optional[FRFUpdateCallback] = None,
    ) -> FRFMeasurementResult:
        """
        Executa uma medição completa de FRF.

        Para o ensaio de TL futuramente:

            referência = microfone posição 3
            resposta   = microfone móvel

        Exemplo:

            posição móvel = 1

            x = P3
            y = P1

            H = P1/P3
        """

        self.reset_cancel()

        self._validate_frf_channels(
            reference_channel_index,
            response_channel_index,
        )

        acquisition_config = (
            self.config.acquisition
        )

        number_averages = (
            acquisition_config.num_averages
        )

        if number_averages <= 0:

            raise AcquisitionControllerError(
                "O número de médias deve "
                "ser maior que zero."
            )

        # ----------------------------------------------------
        # Configuração do hardware
        # ----------------------------------------------------

        if message_callback is not None:

            message_callback(
                "Configurando a DAQ..."
            )

        self.configure_hardware()

        # ----------------------------------------------------
        # Estabilização
        # ----------------------------------------------------

        self._wait_stabilization(
            message_callback
        )

        self._check_cancelled()

        # ----------------------------------------------------
        # Acumuladores espectrais
        # ----------------------------------------------------

        Gxx_sum = None
        Gyy_sum = None
        Gxy_sum = None

        frequency = None

        # ----------------------------------------------------
        # Acumuladores das métricas temporais
        # ----------------------------------------------------

        active_channels = (
            self._get_active_channels()
        )

        number_channels = len(
            active_channels
        )

        sum_square = np.zeros(
            number_channels,
            dtype=np.float64,
        )

        total_samples = np.zeros(
            number_channels,
            dtype=np.int64,
        )

        peak_values = np.zeros(
            number_channels,
            dtype=np.float64,
        )

        clipping_detected = np.zeros(
            number_channels,
            dtype=bool,
        )

        max_clipping_ratio = np.zeros(
            number_channels,
            dtype=np.float64,
        )

        completed_averages = 0

        start_time = monotonic()

        # ====================================================
        # LOOP DAS MÉDIAS
        # ====================================================

        for average_index in range(
            number_averages
        ):

            self._check_cancelled()

            current_average = (
                average_index + 1
            )

            if message_callback is not None:

                message_callback(
                    f"Adquirindo média "
                    f"{current_average} "
                    f"de {number_averages}..."
                )

            # ------------------------------------------------
            # Aquisição temporal
            # ------------------------------------------------

            try:

                acquisition_data = (
                    self.daq.acquire()
                )

            except DAQError as exc:

                raise AcquisitionControllerError(
                    f"Erro na média "
                    f"{current_average}."
                ) from exc

            self._check_cancelled()

            # ------------------------------------------------
            # Verificações do bloco
            # ------------------------------------------------

            self._validate_acquisition_block(
                acquisition_data,
                number_channels,
            )

            # ------------------------------------------------
            # Taxa REAL da DAQ
            # ------------------------------------------------

            sample_rate = (
                acquisition_data.sample_rate
            )

            # ------------------------------------------------
            # Canal de referência
            # ------------------------------------------------

            reference_signal = (
                acquisition_data.data[
                    :,
                    reference_channel_index,
                ]
            )

            # ------------------------------------------------
            # Canal de resposta
            # ------------------------------------------------

            response_signal = (
                acquisition_data.data[
                    :,
                    response_channel_index,
                ]
            )

            # ------------------------------------------------
            # FRF do bloco
            #
            # IMPORTANTE:
            #
            # nperseg = N
            #
            # Neste estágio não fazemos Welch
            # subdividindo o bloco.
            #
            # A média será realizada ENTRE os blocos.
            # ------------------------------------------------

            try:

                block_frf = (
                    FRFProcessor.calculate_frf(
                        x=reference_signal,
                        y=response_signal,
                        sample_rate=sample_rate,
                        window_type=(
                            acquisition_config.window
                        ),
                        nperseg=(
                            acquisition_config
                            .num_samples
                        ),
                        overlap=0.0,
                        estimator=(
                            acquisition_config
                            .frf_estimator
                        ),
                        coherence_threshold=0.0,
                    )
                )

            except SignalProcessingError as exc:

                raise AcquisitionControllerError(
                    "Erro no processamento "
                    "espectral."
                ) from exc

            # ------------------------------------------------
            # Primeiro bloco
            # ------------------------------------------------

            if Gxx_sum is None:

                frequency = (
                    block_frf
                    .frequency
                    .copy()
                )

                Gxx_sum = np.zeros_like(
                    block_frf.Gxx,
                    dtype=np.float64,
                )

                Gyy_sum = np.zeros_like(
                    block_frf.Gyy,
                    dtype=np.float64,
                )

                Gxy_sum = np.zeros_like(
                    block_frf.Gxy,
                    dtype=np.complex128,
                )

            # ------------------------------------------------
            # Confere vetor de frequência
            # ------------------------------------------------

            else:

                if not np.array_equal(
                    frequency,
                    block_frf.frequency,
                ):

                    raise AcquisitionControllerError(
                        "O vetor de frequência mudou "
                        "entre as médias."
                    )

            # ------------------------------------------------
            # Acumulação espectral
            # ------------------------------------------------

            Gxx_sum += block_frf.Gxx

            Gyy_sum += block_frf.Gyy

            Gxy_sum += block_frf.Gxy

            # ------------------------------------------------
            # Métricas temporais de TODOS os canais
            # ------------------------------------------------

            self._accumulate_channel_metrics(
                acquisition_data=(
                    acquisition_data
                ),
                sum_square=sum_square,
                total_samples=total_samples,
                peak_values=peak_values,
                clipping_detected=(
                    clipping_detected
                ),
                max_clipping_ratio=(
                    max_clipping_ratio
                ),
            )

            completed_averages += 1

            # A interface recebe a FRF calculada a partir dos
            # espectros acumulados até a média atual.
            if frf_update_callback is not None:

                partial_frf = (
                    self._calculate_averaged_frf(
                        frequency=frequency,
                        Gxx=(
                            Gxx_sum
                            / completed_averages
                        ),
                        Gyy=(
                            Gyy_sum
                            / completed_averages
                        ),
                        Gxy=(
                            Gxy_sum
                            / completed_averages
                        ),
                    )
                )

                frf_update_callback(
                    partial_frf,
                    completed_averages,
                    number_averages,
                )

            # ------------------------------------------------
            # Progresso
            # ------------------------------------------------

            if progress_callback is not None:

                progress_callback(
                    completed_averages,
                    number_averages,
                )

        # ====================================================
        # FIM DAS MÉDIAS
        # ====================================================

        total_measurement_time = (
            monotonic() - start_time
        )

        if completed_averages == 0:

            raise AcquisitionControllerError(
                "Nenhuma média foi adquirida."
            )

        # ----------------------------------------------------
        # Médias dos espectros
        # ----------------------------------------------------

        Gxx = (
            Gxx_sum
            / completed_averages
        )

        Gyy = (
            Gyy_sum
            / completed_averages
        )

        Gxy = (
            Gxy_sum
            / completed_averages
        )

        # ----------------------------------------------------
        # FRF e coerência a partir dos
        # espectros MÉDIOS
        # ----------------------------------------------------

        frf = self._calculate_averaged_frf(
            frequency=frequency,
            Gxx=Gxx,
            Gyy=Gyy,
            Gxy=Gxy,
        )

        # ----------------------------------------------------
        # Métricas temporais
        # ----------------------------------------------------

        channel_metrics = (
            self._finalize_channel_metrics(
                sum_square=sum_square,
                total_samples=total_samples,
                peak_values=peak_values,
                clipping_detected=(
                    clipping_detected
                ),
                max_clipping_ratio=(
                    max_clipping_ratio
                ),
            )
        )

        # ----------------------------------------------------
        # Qualidade
        # ----------------------------------------------------

        quality = (
            self._evaluate_quality(
                frf=frf,
                channel_metrics=(
                    channel_metrics
                ),
                completed_averages=(
                    completed_averages
                ),
            )
        )

        if message_callback is not None:

            message_callback(
                f"Medição concluída: "
                f"{quality.status.value}"
            )

        return FRFMeasurementResult(
            frf=frf,
            requested_averages=(
                number_averages
            ),
            completed_averages=(
                completed_averages
            ),
            sample_rate=(
                self.daq.actual_sample_rate
                or
                self.config
                .acquisition
                .sample_rate
            ),
            num_samples_per_block=(
                acquisition_config
                .num_samples
            ),
            block_duration=(
                acquisition_config
                .num_samples
                /
                (
                    self.daq.actual_sample_rate
                    or
                    acquisition_config
                    .sample_rate
                )
            ),
            total_measurement_time=(
                total_measurement_time
            ),
            channel_metrics=(
                channel_metrics
            ),
            quality=quality,
        )

    # ========================================================
    # VALIDAÇÃO DO BLOCO
    # ========================================================

    @staticmethod
    def _validate_acquisition_block(
        acquisition_data: AcquisitionData,
        expected_channels: int,
    ) -> None:

        if (
            acquisition_data.num_channels
            != expected_channels
        ):

            raise AcquisitionControllerError(
                "A quantidade de canais recebida "
                "da DAQ é diferente da configuração."
            )

        if acquisition_data.num_samples <= 0:

            raise AcquisitionControllerError(
                "A DAQ retornou um bloco vazio."
            )

        if not np.all(
            np.isfinite(
                acquisition_data.data
            )
        ):

            raise AcquisitionControllerError(
                "A aquisição contém NaN "
                "ou infinito."
            )

    # ========================================================
    # MÉDIA DOS ESPECTROS → FRF
    # ========================================================

    def _calculate_averaged_frf(
        self,
        frequency: np.ndarray,
        Gxx: np.ndarray,
        Gyy: np.ndarray,
        Gxy: np.ndarray,
    ) -> FRFResult:
        """
        Calcula a FRF final somente DEPOIS
        da média de Gxx, Gyy e Gxy.
        """

        estimator = (
            self.config
            .acquisition
            .frf_estimator
        )

        # ----------------------------------------------------
        # H1 / H2
        # ----------------------------------------------------

        H = np.full(
            Gxy.shape,
            np.nan + 1j * np.nan,
            dtype=np.complex128,
        )

        estimator_name = (
            estimator.name
        )

        if estimator_name == "H1":

            np.divide(
                Gxy,
                Gxx,
                out=H,
                where=Gxx > 0,
            )

        elif estimator_name == "H2":

            Gyx = np.conj(
                Gxy
            )

            np.divide(
                Gyy,
                Gyx,
                out=H,
                where=np.abs(Gyx) > 0,
            )

        else:

            raise AcquisitionControllerError(
                f"Estimador não suportado: "
                f"{estimator}"
            )

        # ----------------------------------------------------
        # COERÊNCIA
        # ----------------------------------------------------

        coherence = np.zeros(
            Gxx.shape,
            dtype=np.float64,
        )

        denominator = (
            Gxx * Gyy
        )

        np.divide(
            np.abs(Gxy) ** 2,
            denominator,
            out=coherence,
            where=denominator > 0,
        )

        coherence = np.clip(
            coherence,
            0.0,
            1.0,
        )

        # ----------------------------------------------------
        # Máscara baseada APENAS na coerência.
        #
        # A faixa de frequência é tratada
        # separadamente.
        # ----------------------------------------------------

        coherence_threshold = (
            self.config
            .quality
            .coherence_threshold
        )

        valid_mask = (
            np.isfinite(H.real)
            &
            np.isfinite(H.imag)
            &
            np.isfinite(coherence)
            &
            (
                coherence
                >= coherence_threshold
            )
        )

        return FRFResult(
            frequency=frequency,
            H=H,
            coherence=coherence,
            Gxx=Gxx,
            Gyy=Gyy,
            Gxy=Gxy,
            valid_mask=valid_mask,
        )

    # ========================================================
    # ACUMULA MÉTRICAS TEMPORAIS
    # ========================================================

    def _accumulate_channel_metrics(
        self,
        acquisition_data: AcquisitionData,
        sum_square: np.ndarray,
        total_samples: np.ndarray,
        peak_values: np.ndarray,
        clipping_detected: np.ndarray,
        max_clipping_ratio: np.ndarray,
    ) -> None:

        active_channels = (
            self._get_active_channels()
        )

        for channel_index, channel in enumerate(
            active_channels
        ):

            signal_data = (
                acquisition_data.data[
                    :,
                    channel_index,
                ]
            )

            # ------------------------------------------------
            # Remove DC para métricas acústicas
            # ------------------------------------------------

            signal_ac = (
                signal_data
                -
                np.mean(signal_data)
            )

            sum_square[channel_index] += (
                np.sum(
                    signal_ac ** 2
                )
            )

            total_samples[channel_index] += (
                signal_ac.size
            )

            block_peak = float(
                np.max(
                    np.abs(signal_ac)
                )
            )

            peak_values[channel_index] = max(
                peak_values[channel_index],
                block_peak,
            )

            # ------------------------------------------------
            # Estimativa de clipping
            # ------------------------------------------------

            ratio = (
                self._calculate_clipping_ratio(
                    signal_data,
                    channel,
                )
            )

            if ratio is not None:

                max_clipping_ratio[
                    channel_index
                ] = max(
                    max_clipping_ratio[
                        channel_index
                    ],
                    ratio,
                )

                if (
                    ratio
                    >= self.config
                    .quality
                    .clipping_threshold
                ):

                    clipping_detected[
                        channel_index
                    ] = True

    # ========================================================
    # ESTIMATIVA DE CLIPPING
    # ========================================================

    @staticmethod
    def _calculate_clipping_ratio(
        signal_data: np.ndarray,
        channel,
    ) -> float | None:
        """
        Estima a fração da faixa de entrada utilizada.

        Para canal de tensão:
            usa diretamente V.

        Para microfone:
            converte Pa aproximadamente para V
            usando a sensibilidade [mV/Pa].

        Isso será usado como indicador preventivo,
        não como diagnóstico absoluto do ADC.
        """

        if (
            channel.sensor_type
            == SensorType.VOLTAGE
        ):

            voltage_peak = float(
                np.max(
                    np.abs(signal_data)
                )
            )

        elif (
            channel.sensor_type
            == SensorType.MICROPHONE
        ):

            sensitivity_v_pa = (
                channel.sensitivity_mv_pa
                / 1000.0
            )

            if sensitivity_v_pa <= 0:

                return None

            pressure_peak = float(
                np.max(
                    np.abs(signal_data)
                )
            )

            voltage_peak = (
                pressure_peak
                *
                sensitivity_v_pa
            )

        else:

            return None

        input_limit = max(
            abs(channel.min_voltage),
            abs(channel.max_voltage),
        )

        if input_limit <= 0:

            return None

        return (
            voltage_peak
            / input_limit
        )

    # ========================================================
    # FINALIZA MÉTRICAS DOS CANAIS
    # ========================================================

    def _finalize_channel_metrics(
        self,
        sum_square: np.ndarray,
        total_samples: np.ndarray,
        peak_values: np.ndarray,
        clipping_detected: np.ndarray,
        max_clipping_ratio: np.ndarray,
    ) -> list[ChannelMetrics]:

        active_channels = (
            self._get_active_channels()
        )

        metrics: list[
            ChannelMetrics
        ] = []

        reference_pressure = (
            self.config
            .acoustics
            .reference_pressure
        )

        for index, channel in enumerate(
            active_channels
        ):

            if total_samples[index] > 0:

                rms = float(
                    np.sqrt(
                        sum_square[index]
                        /
                        total_samples[index]
                    )
                )

            else:

                rms = 0.0

            # ------------------------------------------------
            # SPL apenas para microfone
            # ------------------------------------------------

            if (
                channel.sensor_type
                == SensorType.MICROPHONE
            ):

                if rms > 0:

                    spl = float(
                        20.0
                        *
                        np.log10(
                            rms
                            /
                            reference_pressure
                        )
                    )

                else:

                    spl = -np.inf

            else:

                spl = None

            clipping_ratio = float(
                max_clipping_ratio[index]
            )

            metrics.append(
                ChannelMetrics(
                    channel_name=(
                        channel.name
                        or
                        channel.physical_channel
                    ),
                    physical_channel=(
                        channel.physical_channel
                    ),
                    rms=rms,
                    peak=float(
                        peak_values[index]
                    ),
                    spl=spl,
                    clipping_detected=bool(
                        clipping_detected[index]
                    ),
                    clipping_ratio=(
                        clipping_ratio
                    ),
                )
            )

        return metrics

    # ========================================================
    # AVALIAÇÃO DE QUALIDADE
    # ========================================================

    def _evaluate_quality(
        self,
        frf: FRFResult,
        channel_metrics:
            list[ChannelMetrics],
        completed_averages: int,
    ) -> MeasurementQualityReport:

        tl_config = (
            self.config.transmission_loss
        )

        quality_config = (
            self.config.quality
        )

        # ----------------------------------------------------
        # Faixa válida solicitada
        # ----------------------------------------------------

        f_min = (
            tl_config.valid_frequency_min
        )

        f_max = min(
            tl_config.valid_frequency_max,
            float(
                frf.frequency[-1]
            ),
        )

        band_mask = (
            (frf.frequency >= f_min)
            &
            (frf.frequency <= f_max)
        )

        if not np.any(
            band_mask
        ):

            raise AcquisitionControllerError(
                "A faixa válida configurada não "
                "possui pontos no espectro adquirido."
            )

        coherence_band = (
            frf.coherence[
                band_mask
            ]
        )

        coherence_mean = float(
            np.mean(
                coherence_band
            )
        )

        coherence_min = float(
            np.min(
                coherence_band
            )
        )

        valid_points = (
            coherence_band
            >=
            quality_config
            .coherence_threshold
        )

        coherence_valid_percentage = float(
            100.0
            *
            np.mean(
                valid_points
            )
        )

        # ----------------------------------------------------
        # Clipping
        # ----------------------------------------------------

        has_clipping = any(
            metric.clipping_detected
            for metric
            in channel_metrics
        )

        # ----------------------------------------------------
        # Avisos
        # ----------------------------------------------------

        warnings: list[str] = []

        if has_clipping:

            warnings.append(
                "Possível clipping detectado "
                "em pelo menos um canal."
            )

        if coherence_min < (
            quality_config
            .coherence_threshold
        ):

            warnings.append(
                "Existem frequências com coerência "
                "abaixo do limite configurado."
            )

        if coherence_mean < (
            quality_config
            .coherence_mean_threshold
        ):

            warnings.append(
                "A coerência média está abaixo do "
                "limite configurado."
            )

        # Com uma única realização, a estimativa
        # de coerência não é estatisticamente útil.

        if completed_averages < 2:

            warnings.append(
                "A coerência possui confiabilidade "
                "limitada com apenas uma média."
            )

        # ----------------------------------------------------
        # Status
        # ----------------------------------------------------

        if warnings:

            status = (
                MeasurementQualityStatus.REVIEW
            )

        else:

            status = (
                MeasurementQualityStatus.VALID
            )

        return MeasurementQualityReport(
            status=status,
            coherence_threshold=(
                quality_config
                .coherence_threshold
            ),
            valid_frequency_min=f_min,
            valid_frequency_max=f_max,
            coherence_mean=(
                coherence_mean
            ),
            coherence_min=(
                coherence_min
            ),
            coherence_valid_percentage=(
                coherence_valid_percentage
            ),
            clipping_detected=(
                has_clipping
            ),
            warnings=warnings,
        )
