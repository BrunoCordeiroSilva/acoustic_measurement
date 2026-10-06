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


@dataclass
class MultiFRFMeasurementResult:
    """Três FRFs simultâneas e decisão de qualidade conjunta da terminação."""

    measurements: dict[int, FRFMeasurementResult]
    quality: MeasurementQualityReport

    @property
    def frfs(self) -> dict[int, FRFResult]:
        return {position: measurement.frf for position, measurement in self.measurements.items()}


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

    A aquisição TL associa P3 às respostas P1/P2/P4, mas não calcula:

    - separação entre Carga A e Carga B
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
        progress_callback: Optional[ProgressCallback] = None,
        message_callback: Optional[MessageCallback] = None,
        frf_update_callback: Optional[FRFUpdateCallback] = None,
    ) -> FRFMeasurementResult:
        """Aquisição genérica de um par, pelo mesmo motor multicanal."""
        def update(frfs, current, total):
            if frf_update_callback is not None:
                frf_update_callback(frfs[0], current, total)

        return self.acquire_frf_set(
            reference_channel_index, {0: response_channel_index},
            progress_callback, message_callback,
            update if frf_update_callback is not None else None,
        ).measurements[0]

    def acquire_tl_load(
        self, progress_callback=None, message_callback=None, frf_update_callback=None,
    ) -> MultiFRFMeasurementResult:
        """Adquire P1–P4 simultaneamente para uma única terminação."""
        self.config.validate()
        indices = self.config.tl_channel_indices()
        return self.acquire_frf_set(
            indices[3], {position: indices[position] for position in (1, 2, 4)},
            progress_callback, message_callback, frf_update_callback,
        )

    def acquire_frf_set(
        self,
        reference_channel_index: int,
        response_channel_indices: dict[int, int],
        progress_callback=None,
        message_callback=None,
        frf_update_callback=None,
    ) -> MultiFRFMeasurementResult:
        """Uma leitura por média: todos os pares usam o MESMO bloco e relógio."""
        self.reset_cancel()
        if not response_channel_indices:
            raise AcquisitionControllerError("Nenhum canal de resposta foi definido.")
        for index in response_channel_indices.values():
            self._validate_frf_channels(reference_channel_index, index)
        if len(set(response_channel_indices.values())) != len(response_channel_indices):
            raise AcquisitionControllerError("Os canais de resposta devem ser diferentes.")
        acquisition = self.config.acquisition
        number_averages = acquisition.num_averages
        if number_averages <= 0:
            raise AcquisitionControllerError("O número de médias deve ser maior que zero.")
        if message_callback is not None:
            message_callback("Configurando a DAQ...")
        self.configure_hardware()
        self._wait_stabilization(message_callback)
        self._check_cancelled()

        count = len(self._get_active_channels())
        sum_square = np.zeros(count)
        total_samples = np.zeros(count, dtype=np.int64)
        peak_values = np.zeros(count)
        clipping_detected = np.zeros(count, dtype=bool)
        max_clipping_ratio = np.zeros(count)
        sums = {}
        frequency = None
        start_time = monotonic()
        frfs = {}

        for current in range(1, number_averages + 1):
            self._check_cancelled()
            if message_callback is not None:
                message_callback(f"Adquirindo média {current} de {number_averages}...")
            try:
                block = self.daq.acquire()
            except DAQError as exc:
                raise AcquisitionControllerError(f"Erro na média {current}.") from exc
            self._check_cancelled()
            self._validate_acquisition_block(block, count)
            sample_rate = float(block.sample_rate)
            if block.num_samples != acquisition.num_samples:
                raise AcquisitionControllerError("A DAQ retornou um bloco com tamanho diferente do configurado.")
            for position, index in response_channel_indices.items():
                try:
                    pair = FRFProcessor.calculate_frf(
                        x=block.data[:, reference_channel_index],
                        y=block.data[:, index],
                        sample_rate=sample_rate,
                        window_type=acquisition.window,
                        nperseg=acquisition.num_samples,
                        overlap=0.0, estimator=acquisition.frf_estimator,
                        coherence_threshold=0.0,
                    )
                except SignalProcessingError as exc:
                    raise AcquisitionControllerError("Erro no processamento espectral.") from exc
                if frequency is None:
                    frequency = pair.frequency.copy()
                elif not np.array_equal(frequency, pair.frequency):
                    raise AcquisitionControllerError("O vetor de frequência mudou entre as médias ou canais.")
                if position not in sums:
                    sums[position] = [
                        np.zeros_like(pair.Gxx), np.zeros_like(pair.Gyy),
                        np.zeros_like(pair.Gxy),
                    ]
                for accumulator, spectrum in zip(sums[position], (pair.Gxx, pair.Gyy, pair.Gxy)):
                    accumulator += spectrum
                gxx, gyy, gxy = sums[position]
                frfs[position] = self._calculate_averaged_frf(
                    frequency=frequency.copy(),
                    Gxx=gxx / current, Gyy=gyy / current, Gxy=gxy / current,
                )

            self._accumulate_channel_metrics(
                acquisition_data=block, sum_square=sum_square,
                total_samples=total_samples, peak_values=peak_values,
                clipping_detected=clipping_detected,
                max_clipping_ratio=max_clipping_ratio,
            )
            if frf_update_callback is not None:
                # Dicionário novo: nenhum callback recebe acumuladores mutáveis.
                frf_update_callback(dict(frfs), current, number_averages)
            if progress_callback is not None:
                progress_callback(current, number_averages)

        self._check_cancelled()
        duration = monotonic() - start_time
        metrics = self._finalize_channel_metrics(
            sum_square=sum_square, total_samples=total_samples,
            peak_values=peak_values, clipping_detected=clipping_detected,
            max_clipping_ratio=max_clipping_ratio,
        )
        measurements = {}
        for position, frf in frfs.items():
            quality = self._evaluate_quality(frf, metrics, number_averages)
            measurements[position] = FRFMeasurementResult(
                frf=frf, requested_averages=number_averages,
                completed_averages=number_averages, sample_rate=sample_rate,
                num_samples_per_block=acquisition.num_samples,
                block_duration=acquisition.num_samples / sample_rate,
                total_measurement_time=duration, channel_metrics=metrics, quality=quality,
            )
        quality = self._combine_quality(measurements)
        if message_callback is not None:
            message_callback(f"Medição concluída: {quality.status.value}")
        return MultiFRFMeasurementResult(measurements=measurements, quality=quality)

    @staticmethod
    def _combine_quality(measurements: dict[int, FRFMeasurementResult]) -> MeasurementQualityReport:
        """A pior FRF governa a revisão; pontos válidos são a interseção dos pares."""
        first = next(iter(measurements.values()))
        reports = [measurement.quality for measurement in measurements.values()]
        band = (
            (first.frf.frequency >= first.quality.valid_frequency_min)
            & (first.frf.frequency <= first.quality.valid_frequency_max)
        )
        valid = np.logical_and.reduce([
            np.isfinite(measurement.frf.coherence)
            & (measurement.frf.coherence >= measurement.quality.coherence_threshold)
            for measurement in measurements.values()
        ])
        warnings = [
            f"H3{position}: {warning}"
            for position, measurement in measurements.items()
            for warning in measurement.quality.warnings
        ]
        return MeasurementQualityReport(
            status=MeasurementQualityStatus.REVIEW if warnings else MeasurementQualityStatus.VALID,
            coherence_threshold=first.quality.coherence_threshold,
            valid_frequency_min=first.quality.valid_frequency_min,
            valid_frequency_max=first.quality.valid_frequency_max,
            coherence_mean=min(report.coherence_mean for report in reports),
            coherence_min=min(report.coherence_min for report in reports),
            coherence_valid_percentage=float(100 * np.mean(valid[band])),
            clipping_detected=any(report.clipping_detected for report in reports),
            warnings=warnings,
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

    def _get_quality_frequency_range(
        self,
        frequency: np.ndarray,
    ) -> tuple[float, float]:
        """Retorna a faixa válida efetiva para avaliar a qualidade."""

        if frequency.size == 0:

            raise AcquisitionControllerError(
                "O espectro adquirido não possui pontos de frequência."
            )

        tl_config = self.config.transmission_loss

        nyquist = float(frequency[-1])

        if not tl_config.automatic_valid_frequency_range:

            f_min = tl_config.valid_frequency_min

            f_max = min(
                tl_config.valid_frequency_max,
                nyquist,
            )

        else:

            speed_of_sound = self.config.acoustics.speed_of_sound

            spacing_minimum = max(
                0.05 * speed_of_sound / tl_config.spacing_12,
                0.05 * speed_of_sound / tl_config.spacing_34,
            )

            spacing_maximum = min(
                0.40 * speed_of_sound / tl_config.spacing_12,
                0.40 * speed_of_sound / tl_config.spacing_34,
            )

            plane_wave_cutoff = (
                1.84
                * speed_of_sound
                / (np.pi * tl_config.tube_diameter)
            )

            f_min = spacing_minimum

            f_max = min(
                spacing_maximum,
                plane_wave_cutoff,
                nyquist,
            )

        if f_max <= f_min:

            raise AcquisitionControllerError(
                "A geometria e a aquisição não produzem uma "
                "faixa válida de frequências para avaliar a qualidade."
            )

        return float(f_min), float(f_max)

    def _evaluate_quality(
        self,
        frf: FRFResult,
        channel_metrics:
            list[ChannelMetrics],
        completed_averages: int,
    ) -> MeasurementQualityReport:

        quality_config = (
            self.config.quality
        )

        # ----------------------------------------------------
        # Faixa válida solicitada
        # ----------------------------------------------------

        f_min, f_max = self._get_quality_frequency_range(
            frf.frequency
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
