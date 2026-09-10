from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np

from acquisition_controller import (
    AcquisitionController,
    AcquisitionCancelled,
    FRFMeasurementResult,
    MeasurementQualityStatus,
)

from config import AppConfig

from signal_processing import FRFResult


# ============================================================
# EXCEÇÕES
# ============================================================

class TransmissionLossError(RuntimeError):
    """
    Erro específico do ensaio de perda de transmissão.
    """

    pass


# ============================================================
# ETAPAS DAS MEDIÇÕES
# ============================================================

class TLMeasurementStep(Enum):

    H31_A = "H31_A"
    H32_A = "H32_A"
    H34_A = "H34_A"

    H31_B = "H31_B"
    H32_B = "H32_B"
    H34_B = "H34_B"


# ============================================================
# ESTADO DO EXPERIMENTO
# ============================================================

class TLExperimentState(Enum):

    CONFIGURING = "CONFIGURANDO"

    READY = "PRONTO"

    MEASURING = "MEDINDO"

    AWAITING_REVIEW = "AGUARDANDO_REVISÃO"

    WAITING_LOAD_CHANGE = "AGUARDANDO_TROCA_DE_CARGA"

    READY_TO_PROCESS = "PRONTO_PARA_PROCESSAR"

    PROCESSED = "PROCESSADO"

    ERROR = "ERRO"


# ============================================================
# DECISÃO DO OPERADOR
# ============================================================

class MeasurementAcceptance(Enum):

    ACCEPTED = "ACEITO"

    ACCEPTED_WITH_WARNING = "ACEITO_COM_AVISO"


# ============================================================
# MEDIÇÃO ARMAZENADA
# ============================================================

@dataclass
class StoredTLMeasurement:

    step: TLMeasurementStep

    result: FRFMeasurementResult

    acceptance: MeasurementAcceptance


# ============================================================
# FAIXA DE FREQUÊNCIA
# ============================================================

@dataclass
class ValidFrequencyRange:

    minimum: float

    maximum: float

    microphone_spacing_minimum: float

    microphone_spacing_maximum: float

    plane_wave_cutoff: float

    nyquist_frequency: float


# ============================================================
# RESULTADO FINAL
# ============================================================

@dataclass
class TLResult:

    frequency: np.ndarray

    A: np.ndarray

    B: np.ndarray

    C: np.ndarray

    D: np.ndarray

    transmission_loss: np.ndarray

    valid_mask: np.ndarray

    valid_frequency_range: ValidFrequencyRange

    two_load_separation: np.ndarray

    @property
    def valid_frequency(self) -> np.ndarray:

        return self.frequency[
            self.valid_mask
        ]

    @property
    def valid_tl(self) -> np.ndarray:

        return self.transmission_loss[
            self.valid_mask
        ]


# ============================================================
# EXPERIMENTO
# ============================================================

class TransmissionLossExperiment:
    """
    Gerencia o ensaio de perda de transmissão
    pelo método das duas cargas.

    Sequência:

        H31_A
        H32_A
        H34_A

        TROCA DE CARGA

        H31_B
        H32_B
        H34_B

        ↓

        A, B, C, D

        ↓

        TL(f)
    """

    # ========================================================
    # ORDEM DAS MEDIÇÕES
    # ========================================================

    MEASUREMENT_SEQUENCE = [

        TLMeasurementStep.H31_A,

        TLMeasurementStep.H32_A,

        TLMeasurementStep.H34_A,

        TLMeasurementStep.H31_B,

        TLMeasurementStep.H32_B,

        TLMeasurementStep.H34_B,
    ]

    # ========================================================
    # INICIALIZAÇÃO
    # ========================================================

    def __init__(
        self,
        controller: AcquisitionController,
        config: AppConfig,
    ):

        self.controller = controller

        self.config = config

        self.state = (
            TLExperimentState.CONFIGURING
        )

        self.current_index = 0

        self.measurements: dict[
            TLMeasurementStep,
            StoredTLMeasurement,
        ] = {}

        self.pending_measurement: Optional[
            FRFMeasurementResult
        ] = None

        self.result: Optional[
            TLResult
        ] = None

    # ========================================================
    # MEDIÇÃO ATUAL
    # ========================================================

    @property
    def current_step(
        self,
    ) -> Optional[TLMeasurementStep]:

        if (
            self.current_index
            >= len(
                self.MEASUREMENT_SEQUENCE
            )
        ):

            return None

        return self.MEASUREMENT_SEQUENCE[
            self.current_index
        ]

    # ========================================================
    # INICIAR EXPERIMENTO
    # ========================================================

    def start(self) -> None:

        try:

            self.config.validate()

        except ValueError as exc:

            self.state = (
                TLExperimentState.ERROR
            )

            raise TransmissionLossError(
                "Configuração inválida para "
                "o ensaio de TL."
            ) from exc

        self.current_index = 0

        self.measurements.clear()

        self.pending_measurement = None

        self.result = None

        self.state = (
            TLExperimentState.READY
        )

    # ========================================================
    # INSTRUÇÃO AO OPERADOR
    # ========================================================

    def get_current_instruction(
        self,
    ) -> str:

        step = self.current_step

        if step is None:

            if (
                self.state
                == TLExperimentState.READY_TO_PROCESS
            ):

                return (
                    "Todas as medições foram "
                    "concluídas. O ensaio está pronto "
                    "para processamento."
                )

            return (
                "Nenhuma medição pendente."
            )

        instructions = {

            TLMeasurementStep.H31_A:
                (
                    f"H31_A - {self.config.transmission_loss.load_a_name}: "
                    "mantenha o microfone de referência "
                    "na posição 3 e coloque o microfone "
                    "móvel na posição 1."
                ),

            TLMeasurementStep.H32_A:
                (
                    f"H32_A - {self.config.transmission_loss.load_a_name}: "
                    "mantenha o microfone de referência "
                    "na posição 3 e mova o segundo "
                    "microfone para a posição 2."
                ),

            TLMeasurementStep.H34_A:
                (
                    f"H34_A - {self.config.transmission_loss.load_a_name}: "
                    "mantenha o microfone de referência "
                    "na posição 3 e mova o segundo "
                    "microfone para a posição 4."
                ),

            TLMeasurementStep.H31_B:
                (
                    f"H31_B - {self.config.transmission_loss.load_b_name}: "
                    "mantenha o microfone de referência "
                    "na posição 3 e coloque o microfone "
                    "móvel na posição 1."
                ),

            TLMeasurementStep.H32_B:
                (
                    f"H32_B - {self.config.transmission_loss.load_b_name}: "
                    "mantenha o microfone de referência "
                    "na posição 3 e mova o segundo "
                    "microfone para a posição 2."
                ),

            TLMeasurementStep.H34_B:
                (
                    f"H34_B - {self.config.transmission_loss.load_b_name}: "
                    "mantenha o microfone de referência "
                    "na posição 3 e mova o segundo "
                    "microfone para a posição 4."
                ),
        }

        return instructions[step]

    # ========================================================
    # REALIZA MEDIÇÃO ATUAL
    # ========================================================

    def measure_current_step(
        self,
        progress_callback=None,
        message_callback=None,
    ) -> FRFMeasurementResult:

        if (
            self.state
            != TLExperimentState.READY
        ):

            raise TransmissionLossError(
                "O experimento não está pronto "
                "para iniciar uma medição."
            )

        if self.current_step is None:

            raise TransmissionLossError(
                "Não existe medição pendente."
            )

        self.state = (
            TLExperimentState.MEASURING
        )

        try:

            result = (
                self.controller.acquire_frf(
                    reference_channel_index=0,
                    response_channel_index=1,
                    progress_callback=progress_callback,
                    message_callback=message_callback,
                )
            )

        except AcquisitionCancelled:

            # Cancelar uma medição não significa
            # erro do experimento.
            self.pending_measurement = None

            self.state = (
                TLExperimentState.READY
            )

            raise

        except Exception:

            self.state = (
                TLExperimentState.ERROR
            )

            raise
        self.pending_measurement = result

        self.state = (
            TLExperimentState.AWAITING_REVIEW
        )

        return result

    # ========================================================
    # REPETIR
    # ========================================================

    def repeat_measurement(
        self,
    ) -> None:

        if (
            self.state
            != TLExperimentState.AWAITING_REVIEW
        ):

            raise TransmissionLossError(
                "Não existe medição aguardando revisão."
            )

        self.pending_measurement = None

        self.state = (
            TLExperimentState.READY
        )

    # ========================================================
    # ACEITAR
    # ========================================================

    def accept_measurement(
        self,
        accept_warning: bool = False,
    ) -> None:

        if (
            self.state
            != TLExperimentState.AWAITING_REVIEW
        ):

            raise TransmissionLossError(
                "Não existe medição aguardando decisão."
            )

        if self.pending_measurement is None:

            raise TransmissionLossError(
                "Medição pendente inexistente."
            )

        step = self.current_step

        if step is None:

            raise TransmissionLossError(
                "Etapa atual inválida."
            )

        quality_status = (
            self.pending_measurement
            .quality
            .status
        )

        # ----------------------------------------------------
        # Medição com aviso
        # ----------------------------------------------------

        if (
            quality_status
            == MeasurementQualityStatus.REVIEW
        ):

            if not accept_warning:

                raise TransmissionLossError(
                    "A medição possui avisos de "
                    "qualidade. Use accept_warning=True "
                    "para aceitá-la conscientemente "
                    "ou repita a medição."
                )

            acceptance = (
                MeasurementAcceptance
                .ACCEPTED_WITH_WARNING
            )

        else:

            acceptance = (
                MeasurementAcceptance.ACCEPTED
            )

        # ----------------------------------------------------
        # Armazena
        # ----------------------------------------------------

        self.measurements[
            step
        ] = StoredTLMeasurement(
            step=step,
            result=self.pending_measurement,
            acceptance=acceptance,
        )

        self.pending_measurement = None

        # ----------------------------------------------------
        # Avança sequência
        # ----------------------------------------------------

        self.current_index += 1

        # ----------------------------------------------------
        # Terminou Carga A
        # ----------------------------------------------------

        if (
            step
            == TLMeasurementStep.H34_A
        ):

            self.state = (
                TLExperimentState
                .WAITING_LOAD_CHANGE
            )

            return

        # ----------------------------------------------------
        # Terminou tudo
        # ----------------------------------------------------

        if (
            self.current_index
            >= len(
                self.MEASUREMENT_SEQUENCE
            )
        ):

            self.state = (
                TLExperimentState
                .READY_TO_PROCESS
            )

            return

        self.state = (
            TLExperimentState.READY
        )

    # ========================================================
    # CONFIRMAÇÃO DA TROCA DE CARGA
    # ========================================================

    def confirm_load_change(
        self,
    ) -> None:

        if (
            self.state
            != TLExperimentState
            .WAITING_LOAD_CHANGE
        ):

            raise TransmissionLossError(
                "O experimento não está aguardando "
                "troca de carga."
            )

        self.state = (
            TLExperimentState.READY
        )

    # ========================================================
    # CÁLCULO DA FAIXA VÁLIDA
    # ========================================================

    def calculate_valid_frequency_range(
        self,
        frequency: np.ndarray,
    ) -> ValidFrequencyRange:
        """
        Calcula uma faixa recomendada considerando:

        1. espaçamento entre microfones;
        2. primeiro modo não plano do tubo;
        3. Nyquist.

        Para espaçamento de microfones é utilizado:

            0.1*pi < k*s < 0.8*pi

        que corresponde aproximadamente a:

            0.05*c/s < f < 0.40*c/s
        """

        tl = (
            self.config.transmission_loss
        )

        acoustics = (
            self.config.acoustics
        )

        c = acoustics.speed_of_sound

        s12 = tl.spacing_12
        s34 = tl.spacing_34

        # ----------------------------------------------------
        # Limites por espaçamento
        # ----------------------------------------------------

        lower_12 = (
            0.05 * c / s12
        )

        lower_34 = (
            0.05 * c / s34
        )

        upper_12 = (
            0.40 * c / s12
        )

        upper_34 = (
            0.40 * c / s34
        )

        spacing_minimum = max(
            lower_12,
            lower_34,
        )

        spacing_maximum = min(
            upper_12,
            upper_34,
        )

        # ----------------------------------------------------
        # Primeiro modo transversal do tubo circular
        #
        # fc ~= 1.84*c/(pi*D)
        # ----------------------------------------------------

        plane_wave_cutoff = (
            1.84
            * c
            /
            (
                np.pi
                * tl.tube_diameter
            )
        )

        # ----------------------------------------------------
        # Nyquist real do vetor recebido
        # ----------------------------------------------------

        nyquist = float(
            frequency[-1]
        )

        # ----------------------------------------------------
        # Automático
        # ----------------------------------------------------

        if (
            tl.automatic_valid_frequency_range
        ):

            f_min = spacing_minimum

            f_max = min(
                spacing_maximum,
                plane_wave_cutoff,
                nyquist,
            )

        # ----------------------------------------------------
        # Manual
        # ----------------------------------------------------

        else:

            f_min = (
                tl.valid_frequency_min
            )

            f_max = min(
                tl.valid_frequency_max,
                nyquist,
            )

        if f_max <= f_min:

            raise TransmissionLossError(
                "A geometria e a aquisição não "
                "produzem uma faixa válida de "
                "frequências."
            )

        return ValidFrequencyRange(
            minimum=float(f_min),
            maximum=float(f_max),
            microphone_spacing_minimum=float(
                spacing_minimum
            ),
            microphone_spacing_maximum=float(
                spacing_maximum
            ),
            plane_wave_cutoff=float(
                plane_wave_cutoff
            ),
            nyquist_frequency=float(
                nyquist
            ),
        )

    # ========================================================
    # VALIDAÇÃO DAS SEIS FRFs
    # ========================================================

    def _validate_measurements(
        self,
    ) -> np.ndarray:

        for step in (
            self.MEASUREMENT_SEQUENCE
        ):

            if step not in self.measurements:

                raise TransmissionLossError(
                    f"A medição "
                    f"{step.value} "
                    "não foi realizada."
                )

        reference_frequency = (
            self.measurements[
                TLMeasurementStep.H31_A
            ]
            .result
            .frf
            .frequency
        )

        for step in (
            self.MEASUREMENT_SEQUENCE[1:]
        ):

            frequency = (
                self.measurements[
                    step
                ]
                .result
                .frf
                .frequency
            )

            if not np.array_equal(
                reference_frequency,
                frequency,
            ):

                raise TransmissionLossError(
                    "Os vetores de frequência das "
                    "seis medições não são iguais."
                )

        return reference_frequency

    # ========================================================
    # OBTÉM FRF
    # ========================================================

    def _get_H(
        self,
        step: TLMeasurementStep,
    ) -> np.ndarray:

        return (
            self.measurements[
                step
            ]
            .result
            .frf
            .H
        )

    # ========================================================
    # PROCESSAMENTO FINAL
    # ========================================================

    def process(
        self,
    ) -> TLResult:

        if (
            self.state
            != TLExperimentState
            .READY_TO_PROCESS
        ):

            raise TransmissionLossError(
                "As seis medições precisam ser "
                "concluídas antes do processamento."
            )

        frequency = (
            self._validate_measurements()
        )

        # ----------------------------------------------------
        # Valor sentinela para resultados complexos inválidos
        # ----------------------------------------------------

        complex_nan = np.nan + 1j * np.nan

        # ----------------------------------------------------
        # FRFs
        # ----------------------------------------------------

        H31_A = self._get_H(
            TLMeasurementStep.H31_A
        )

        H32_A = self._get_H(
            TLMeasurementStep.H32_A
        )

        H34_A = self._get_H(
            TLMeasurementStep.H34_A
        )

        H31_B = self._get_H(
            TLMeasurementStep.H31_B
        )

        H32_B = self._get_H(
            TLMeasurementStep.H32_B
        )

        H34_B = self._get_H(
            TLMeasurementStep.H34_B
        )

        # ----------------------------------------------------
        # Propriedades acústicas
        # ----------------------------------------------------

        c = (
            self.config
            .acoustics
            .speed_of_sound
        )

        rho = (
            self.config
            .acoustics
            .air_density
        )

        Z0 = rho * c

        # ----------------------------------------------------
        # Geometria
        # ----------------------------------------------------

        s12 = (
            self.config
            .transmission_loss
            .spacing_12
        )

        s34 = (
            self.config
            .transmission_loss
            .spacing_34
        )

        # ----------------------------------------------------
        # Número de onda
        # ----------------------------------------------------

        k = (
            2.0
            * np.pi
            * frequency
            / c
        )

        # ====================================================
        # ESTADOS NORMALIZADOS
        #
        # Como todas as grandezas são divididas por P3:
        #
        # P3/P3 = 1
        #
        # H31 = P1/P3
        # H32 = P2/P3
        # H34 = P4/P3
        # ====================================================

        sin_12 = np.sin(
            k * s12
        )

        cos_12 = np.cos(
            k * s12
        )

        sin_34 = np.sin(
            k * s34
        )

        cos_34 = np.cos(
            k * s34
        )

        # ----------------------------------------------------
        # Velocidade na seção 2:
        #
        # U2/P3 =
        #
        # H31 - cos(ks12)*H32
        # ------------------------
        # j*rho*c*sin(ks12)
        # ----------------------------------------------------

        U2_A = np.full(
            frequency.shape,
            complex_nan,
            dtype=np.complex128,
        )

        U2_B = np.full_like(
            U2_A,
            complex_nan,
        )

        denominator_12 = (
            1j
            * Z0
            * sin_12
        )

        good_12 = (
            np.abs(denominator_12)
            > 1e-12
        )

        np.divide(
            H31_A
            -
            cos_12 * H32_A,
            denominator_12,
            out=U2_A,
            where=good_12,
        )

        np.divide(
            H31_B
            -
            cos_12 * H32_B,
            denominator_12,
            out=U2_B,
            where=good_12,
        )

        # ----------------------------------------------------
        # Velocidade na seção 3:
        #
        # U3/P3 =
        #
        # cos(ks34) - H34
        # ------------------
        # j*rho*c*sin(ks34)
        # ----------------------------------------------------

        U3_A = np.full_like(
            U2_A,
            complex_nan,
        )

        U3_B = np.full_like(
            U2_A,
            complex_nan,
        )

        denominator_34 = (
            1j
            * Z0
            * sin_34
        )

        good_34 = (
            np.abs(denominator_34)
            > 1e-12
        )

        np.divide(
            cos_34 - H34_A,
            denominator_34,
            out=U3_A,
            where=good_34,
        )

        np.divide(
            cos_34 - H34_B,
            denominator_34,
            out=U3_B,
            where=good_34,
        )

        # ====================================================
        # MATRIZ DE TRANSFERÊNCIA
        #
        # [P2]   [A B] [P3]
        # [U2] = [C D] [U3]
        #
        # Como P3 está normalizado para 1:
        #
        # H32 = A + B*U3
        # U2  = C + D*U3
        # ====================================================

        difference_U3 = (
            U3_A - U3_B
        )

        good_load_separation = (
            np.abs(
                difference_U3
            )
            > 1e-12
        )

        A = np.full_like(
            U3_A,
            complex_nan,
        )

        B = np.full_like(
            U3_A,
            complex_nan,
        )

        C = np.full_like(
            U3_A,
            complex_nan,
        )

        D = np.full_like(
            U3_A,
            complex_nan,
        )

        # ----------------------------------------------------
        # B
        # ----------------------------------------------------

        np.divide(
            H32_A - H32_B,
            difference_U3,
            out=B,
            where=good_load_separation,
        )

        # ----------------------------------------------------
        # A
        # ----------------------------------------------------

        A = (
            H32_A
            -
            B * U3_A
        )

        # ----------------------------------------------------
        # D
        # ----------------------------------------------------

        np.divide(
            U2_A - U2_B,
            difference_U3,
            out=D,
            where=good_load_separation,
        )

        # ----------------------------------------------------
        # C
        # ----------------------------------------------------

        C = (
            U2_A
            -
            D * U3_A
        )

        # ====================================================
        # TRANSMISSION LOSS
        #
        # Para mesma impedância característica
        # nas seções de entrada e saída:
        #
        # TL =
        #
        # 20 log10 |
        # 0.5 *
        # (A + B/Z0 + Z0*C + D)
        # |
        # ====================================================

        transfer_term = (
            0.5
            *
            (
                A
                +
                B / Z0
                +
                Z0 * C
                +
                D
            )
        )

        transmission_loss = (
            20.0
            *
            np.log10(
                np.abs(
                    transfer_term
                )
            )
        )

        # ====================================================
        # FAIXA VÁLIDA
        # ====================================================

        valid_range = (
            self.calculate_valid_frequency_range(
                frequency
            )
        )

        geometry_mask = (
            (frequency >= valid_range.minimum)
            &
            (frequency <= valid_range.maximum)
        )

        # ====================================================
        # COERÊNCIA DAS SEIS MEDIÇÕES
        # ====================================================

        coherence_mask = np.ones(
            frequency.shape,
            dtype=bool,
        )

        for step in (
            self.MEASUREMENT_SEQUENCE
        ):

            coherence_mask &= (
                self.measurements[
                    step
                ]
                .result
                .frf
                .valid_mask
            )

        # ====================================================
        # VALIDADE MATEMÁTICA
        # ====================================================

        finite_mask = (
            np.isfinite(A.real)
            &
            np.isfinite(A.imag)
            &
            np.isfinite(B.real)
            &
            np.isfinite(B.imag)
            &
            np.isfinite(C.real)
            &
            np.isfinite(C.imag)
            &
            np.isfinite(D.real)
            &
            np.isfinite(D.imag)
            &
            np.isfinite(
                transmission_loss
            )
        )

        # ====================================================
        # MÁSCARA FINAL
        # ====================================================

        valid_mask = (
            geometry_mask
            &
            coherence_mask
            &
            good_12
            &
            good_34
            &
            good_load_separation
            &
            finite_mask
        )

        # ----------------------------------------------------
        # Indicador simples da diferença entre
        # as duas cargas.
        #
        # Quanto mais próximo H34_A e H34_B,
        # pior condicionado fica o método.
        # ----------------------------------------------------

        two_load_separation = (
            np.abs(
                H34_A - H34_B
            )
        )

        self.result = TLResult(
            frequency=frequency.copy(),
            A=A,
            B=B,
            C=C,
            D=D,
            transmission_loss=(
                transmission_loss
            ),
            valid_mask=valid_mask,
            valid_frequency_range=(
                valid_range
            ),
            two_load_separation=(
                two_load_separation
            ),
        )

        self.state = (
            TLExperimentState.PROCESSED
        )

        return self.result

    # ========================================================
    # RESET DO EXPERIMENTO
    # ========================================================

    def reset(self) -> None:
        """
        Descarta todas as medições realizadas e
        reinicia o ensaio desde H31_A.

        Não altera as configurações do usuário.
        """

        self.current_index = 0

        self.measurements.clear()

        self.pending_measurement = None

        self.result = None

        self.state = (
            TLExperimentState.READY
        )