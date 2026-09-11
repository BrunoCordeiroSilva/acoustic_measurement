from dataclasses import dataclass, field
from enum import Enum
from typing import List


# ============================================================
# ENUMS
# ============================================================

class SensorType(Enum):
    """Tipos de sensores suportados pelo sistema."""

    MICROPHONE = "Microfone"
    VOLTAGE = "Tensão"
    ACCELEROMETER = "Acelerômetro"


class WindowType(Enum):
    """Janelas disponíveis para processamento espectral."""

    HANN = "Hann"
    RECTANGULAR = "Retangular"


class FRFEstimator(Enum):
    """Estimadores de função de transferência."""

    H1 = "H1"
    H2 = "H2"


class ExperimentType(Enum):
    """Tipos de ensaio disponíveis."""

    TRANSMISSION_LOSS = "Perda de transmissão"
    ABSORPTION = "Absorção sonora"
    GENERIC = "Aquisição genérica"


# ============================================================
# CONFIGURAÇÃO DE UM CANAL
# ============================================================

@dataclass
class ChannelConfig:

    physical_channel: str

    enabled: bool = True

    name: str = ""

    sensor_type: SensorType = SensorType.MICROPHONE

    # Sensibilidade do microfone [mV/Pa]
    sensitivity_mv_pa: float = 50.0

    # NI-9234: faixa nominal de entrada ±5 V
    min_voltage: float = -5.0
    max_voltage: float = 5.0

    # Excitação IEPE
    iepe_enabled: bool = True

    # NI-9234: corrente de excitação IEPE
    iepe_current_a: float = 0.002

    max_spl: float = 130.0

    def validate(self):

        if not self.physical_channel:
            raise ValueError(
                "O canal físico da DAQ não foi definido."
            )

        if self.sensor_type == SensorType.MICROPHONE:

            if self.sensitivity_mv_pa <= 0:
                raise ValueError(
                    f"Sensibilidade inválida no canal "
                    f"{self.physical_channel}."
                )

        if self.min_voltage >= self.max_voltage:
            raise ValueError(
                f"Faixa de tensão inválida no canal "
                f"{self.physical_channel}."
            )

        if self.iepe_current_a < 0:
            raise ValueError(
                f"Corrente IEPE inválida no canal "
                f"{self.physical_channel}."
            )


# ============================================================
# CONFIGURAÇÃO DA AQUISIÇÃO
# ============================================================

@dataclass
class AcquisitionConfig:

    sample_rate: float = 12800.0

    num_samples: int = 12800

    num_averages: int = 10

    window: WindowType = WindowType.HANN

    overlap: float = 0.50

    frf_estimator: FRFEstimator = FRFEstimator.H1

    # Tempo descartado antes de iniciar efetivamente as médias
    stabilization_time: float = 2.0

    # --------------------------------------------------------
    # Propriedades calculadas
    # --------------------------------------------------------

    @property
    def block_duration(self) -> float:
        """
        Duração de cada bloco adquirido [s].
        """
        return self.num_samples / self.sample_rate

    @property
    def frequency_resolution(self) -> float:
        """
        Resolução espectral Δf [Hz].
        """
        return self.sample_rate / self.num_samples

    @property
    def nyquist_frequency(self) -> float:
        """
        Frequência de Nyquist [Hz].
        """
        return self.sample_rate / 2.0

    def validate(self):

        if self.sample_rate <= 0:
            raise ValueError(
                "A frequência de amostragem deve ser positiva."
            )

        if self.num_samples <= 0:
            raise ValueError(
                "O número de pontos deve ser positivo."
            )

        if self.num_averages <= 0:
            raise ValueError(
                "O número de médias deve ser pelo menos 1."
            )

        if not 0 <= self.overlap < 1:
            raise ValueError(
                "O overlap deve estar entre 0 e 1."
            )

        if self.stabilization_time < 0:
            raise ValueError(
                "O tempo de estabilização não pode ser negativo."
            )


# ============================================================
# CONDIÇÕES ACÚSTICAS
# ============================================================

@dataclass
class AcousticConfig:

    # Temperatura ambiente [°C]
    temperature_c: float = 20.0

    # Pressão acústica de referência [Pa]
    reference_pressure: float = 20e-6

    # Se True, velocidade do som será estimada pela temperatura
    automatic_speed_of_sound: bool = True

    # Valor manual, usado se automatic_speed_of_sound = False
    manual_speed_of_sound: float = 343.0

    # Densidade do ar [kg/m³]
    air_density: float = 1.204

    @property
    def speed_of_sound(self) -> float:

        if self.automatic_speed_of_sound:

            # Aproximação para ar em condições ambientes
            return 331.3 + 0.606 * self.temperature_c

        return self.manual_speed_of_sound

    def validate(self):

        if self.reference_pressure <= 0:
            raise ValueError(
                "A pressão acústica de referência deve ser positiva."
            )

        if self.air_density <= 0:
            raise ValueError(
                "A densidade do ar deve ser positiva."
            )

        if not self.automatic_speed_of_sound:
            if self.manual_speed_of_sound <= 0:
                raise ValueError(
                    "A velocidade do som deve ser positiva."
                )


# ============================================================
# CONFIGURAÇÃO DE QUALIDADE
# ============================================================

@dataclass
class QualityConfig:

    # Coerência mínima desejada
    coherence_threshold: float = 0.90

    # Percentual máximo do range permitido antes de alertar
    # sobre clipping
    clipping_threshold: float = 0.95

    def validate(self):

        if not 0 <= self.coherence_threshold <= 1:
            raise ValueError(
                "O limite de coerência deve estar entre 0 e 1."
            )

        if not 0 < self.clipping_threshold <= 1:
            raise ValueError(
                "O limite de clipping deve estar entre 0 e 1."
            )


# ============================================================
# CONFIGURAÇÃO DO ENSAIO DE TL
# ============================================================

@dataclass
class TransmissionLossConfig:

    # ========================================================
    # GEOMETRIA
    # ========================================================

    # Diâmetro interno do tubo [m]
    tube_diameter: float = 30e-3

    # Distância entre as posições 1 e 2 [m]
    spacing_12: float = 50e-3

    # Distância entre as posições 3 e 4 [m]
    spacing_34: float = 50e-3

    # ========================================================
    # FAIXA VÁLIDA
    # ========================================================

    # Se True, a faixa válida será calculada
    # automaticamente a partir da geometria,
    # velocidade do som e Nyquist.
    automatic_valid_frequency_range: bool = True

    # Estes valores são usados quando
    # automatic_valid_frequency_range = False
    valid_frequency_min: float = 343.0
    valid_frequency_max: float = 2744.0

    # ========================================================
    # CARGAS
    # ========================================================

    load_a_name: str = "Carga A"
    load_b_name: str = "Carga B"

    # ========================================================
    # POSIÇÕES DOS MICROFONES
    # ========================================================

    reference_position: int = 3

    mobile_positions: List[int] = field(
        default_factory=lambda: [1, 2, 4]
    )

    # ========================================================
    # VALIDAÇÃO
    # ========================================================

    def validate(self):

        if self.tube_diameter <= 0:

            raise ValueError(
                "O diâmetro do tubo deve ser positivo."
            )

        if self.spacing_12 <= 0:

            raise ValueError(
                "A distância entre as posições 1 e 2 "
                "deve ser positiva."
            )

        if self.spacing_34 <= 0:

            raise ValueError(
                "A distância entre as posições 3 e 4 "
                "deve ser positiva."
            )

        # ----------------------------------------------------
        # Só valida a faixa manual quando ela estiver ativa
        # ----------------------------------------------------

        if not self.automatic_valid_frequency_range:

            if self.valid_frequency_min < 0:

                raise ValueError(
                    "A frequência mínima válida não "
                    "pode ser negativa."
                )

            if (
                self.valid_frequency_max
                <= self.valid_frequency_min
            ):

                raise ValueError(
                    "A frequência máxima válida deve "
                    "ser maior que a frequência mínima."
                )

# ============================================================
# INFORMAÇÕES DO ENSAIO
# ============================================================

@dataclass
class ExperimentMetadata:

    experiment_name: str = ""

    experiment_number: str = ""

    operator: str = ""

    notes: str = ""

    # Diretório escolhido pelo usuário
    # para armazenamento dos resultados
    output_directory: str = ""


# ============================================================
# CONFIGURAÇÃO GLOBAL
# ============================================================

@dataclass
class AppConfig:

    experiment_type: ExperimentType = (
        ExperimentType.TRANSMISSION_LOSS
    )

    acquisition: AcquisitionConfig = field(
        default_factory=AcquisitionConfig
    )

    acoustics: AcousticConfig = field(
        default_factory=AcousticConfig
    )

    quality: QualityConfig = field(
        default_factory=QualityConfig
    )

    transmission_loss: TransmissionLossConfig = field(
        default_factory=TransmissionLossConfig
    )

    metadata: ExperimentMetadata = field(
        default_factory=ExperimentMetadata
    )

    channels: List[ChannelConfig] = field(
        default_factory=list
    )

    def validate(self):

        self.acquisition.validate()
        self.acoustics.validate()
        self.quality.validate()

        for channel in self.channels:

            if channel.enabled:
                channel.validate()

        if (
            self.experiment_type
            == ExperimentType.TRANSMISSION_LOSS
        ):
            self.transmission_loss.validate()

            active_channels = [
                ch
                for ch in self.channels
                if ch.enabled
            ]

            if len(active_channels) < 2:
                raise ValueError(
                    "O ensaio de TL requer pelo menos "
                    "dois canais ativos."
                )
