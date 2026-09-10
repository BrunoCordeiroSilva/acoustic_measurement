import numpy as np

from config import (
    AppConfig,
    ChannelConfig,
    SensorType,
)

from signal_processing import FRFResult

from acquisition_controller import (
    FRFMeasurementResult,
    MeasurementQualityReport,
    MeasurementQualityStatus,
)

from experiments.transmission_loss import (
    TransmissionLossExperiment,
    TLExperimentState,
    TLMeasurementStep,
    StoredTLMeasurement,
    MeasurementAcceptance,
)


# ============================================================
# FUNÇÃO AUXILIAR
# ============================================================

def create_measurement(
    frequency,
    H,
):

    coherence = np.ones_like(
        frequency,
        dtype=np.float64,
    )

    frf = FRFResult(
        frequency=frequency,
        H=H,
        coherence=coherence,
        Gxx=np.ones_like(
            frequency,
            dtype=np.float64,
        ),
        Gyy=np.ones_like(
            frequency,
            dtype=np.float64,
        ),
        Gxy=H.copy(),
        valid_mask=np.ones_like(
            frequency,
            dtype=bool,
        ),
    )

    quality = MeasurementQualityReport(
        status=MeasurementQualityStatus.VALID,
        coherence_threshold=0.90,
        valid_frequency_min=300.0,
        valid_frequency_max=2000.0,
        coherence_mean=1.0,
        coherence_min=1.0,
        coherence_valid_percentage=100.0,
        clipping_detected=False,
        warnings=[],
    )

    return FRFMeasurementResult(
        frf=frf,
        requested_averages=5,
        completed_averages=5,
        sample_rate=12800.0,
        num_samples_per_block=12800,
        block_duration=1.0,
        total_measurement_time=5.0,
        channel_metrics=[],
        quality=quality,
    )


# ============================================================
# CONFIGURAÇÃO
# ============================================================

config = AppConfig()

config.channels = [

    ChannelConfig(
        physical_channel="Fake/ai0",
        sensor_type=SensorType.MICROPHONE,
    ),

    ChannelConfig(
        physical_channel="Fake/ai1",
        sensor_type=SensorType.MICROPHONE,
    ),
]


config.transmission_loss.spacing_12 = 0.05
config.transmission_loss.spacing_34 = 0.05
config.transmission_loss.tube_diameter = 0.15

config.transmission_loss.automatic_valid_frequency_range = True


# ============================================================
# FREQUÊNCIA
#
# DESTA VEZ COMEÇAMOS EXATAMENTE EM ZERO
# ============================================================

frequency = np.arange(
    0.0,
    2001.0,
    1.0,
)


# ============================================================
# PROPRIEDADES ACÚSTICAS
# ============================================================

c = config.acoustics.speed_of_sound

rho = config.acoustics.air_density

Z0 = rho * c

k = (
    2.0
    * np.pi
    * frequency
    / c
)


s12 = config.transmission_loss.spacing_12
s34 = config.transmission_loss.spacing_34


# ============================================================
# MATRIZ ABCD SINTÉTICA
# ============================================================

A_true = np.full(
    frequency.shape,
    1.2 + 0.10j,
    dtype=np.complex128,
)

B_true = np.full(
    frequency.shape,
    50.0 + 10.0j,
    dtype=np.complex128,
)

C_true = np.full(
    frequency.shape,
    0.002 + 0.001j,
    dtype=np.complex128,
)

D_true = np.full(
    frequency.shape,
    0.90 - 0.05j,
    dtype=np.complex128,
)


# ============================================================
# DUAS CARGAS
# ============================================================

U3_A = (
    0.001
    + 0.0003j
    + 1e-7 * frequency
)

U3_B = (
    0.004
    - 0.0005j
    + 2e-7 * frequency
)


# ============================================================
# H32
# ============================================================

H32_A = (
    A_true
    +
    B_true * U3_A
)

H32_B = (
    A_true
    +
    B_true * U3_B
)


# ============================================================
# U2
# ============================================================

U2_A = (
    C_true
    +
    D_true * U3_A
)

U2_B = (
    C_true
    +
    D_true * U3_B
)


# ============================================================
# H31
# ============================================================

H31_A = (
    np.cos(k * s12)
    * H32_A
    +
    1j
    * Z0
    * np.sin(k * s12)
    * U2_A
)

H31_B = (
    np.cos(k * s12)
    * H32_B
    +
    1j
    * Z0
    * np.sin(k * s12)
    * U2_B
)


# ============================================================
# H34
# ============================================================

H34_A = (
    np.cos(k * s34)
    -
    1j
    * Z0
    * np.sin(k * s34)
    * U3_A
)

H34_B = (
    np.cos(k * s34)
    -
    1j
    * Z0
    * np.sin(k * s34)
    * U3_B
)


# ============================================================
# EXPERIMENTO
# ============================================================

class DummyController:
    pass


experiment = TransmissionLossExperiment(
    controller=DummyController(),
    config=config,
)


# ============================================================
# ARMAZENA AS SEIS FRFs
# ============================================================

synthetic_data = {

    TLMeasurementStep.H31_A:
        H31_A,

    TLMeasurementStep.H32_A:
        H32_A,

    TLMeasurementStep.H34_A:
        H34_A,

    TLMeasurementStep.H31_B:
        H31_B,

    TLMeasurementStep.H32_B:
        H32_B,

    TLMeasurementStep.H34_B:
        H34_B,
}


for step, H in synthetic_data.items():

    experiment.measurements[
        step
    ] = StoredTLMeasurement(

        step=step,

        result=create_measurement(
            frequency,
            H,
        ),

        acceptance=(
            MeasurementAcceptance.ACCEPTED
        ),
    )


experiment.state = (
    TLExperimentState.READY_TO_PROCESS
)


# ============================================================
# PROCESSAMENTO
# ============================================================

result = experiment.process()


# ============================================================
# VERIFICAÇÕES EM ZERO HZ
# ============================================================

print()
print("====================================")
print("TESTE TL 03 - FREQUÊNCIA ZERO")
print("====================================")

print()

print(
    f"Primeira frequência: "
    f"{result.frequency[0]:.1f} Hz"
)

print(
    f"TL em 0 Hz: "
    f"{result.transmission_loss[0]}"
)

print(
    f"Válido em 0 Hz: "
    f"{result.valid_mask[0]}"
)


# ============================================================
# TESTES
# ============================================================

frequency_zero_ok = (
    result.frequency[0]
    == 0.0
)

invalid_zero_ok = (
    not result.valid_mask[0]
)

tl_zero_not_finite_ok = (
    not np.isfinite(
        result.transmission_loss[0]
    )
)


# ============================================================
# CONFERE QUE O RESTANTE DA CURVA EXISTE
# ============================================================

size_ok = (
    result.frequency.size
    == 2001
)

last_frequency_ok = (
    result.frequency[-1]
    == 2000.0
)


# ============================================================
# RESULTADO
# ============================================================

print()

print(
    f"Quantidade de pontos: "
    f"{result.frequency.size}"
)

print(
    f"Última frequência: "
    f"{result.frequency[-1]:.1f} Hz"
)

print()


if (
    frequency_zero_ok
    and
    invalid_zero_ok
    and
    tl_zero_not_finite_ok
    and
    size_ok
    and
    last_frequency_ok
):

    print(
        "TESTE APROVADO."
    )

else:

    print(
        "TESTE REPROVADO."
    )