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
        valid_frequency_max=3000.0,
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


config.transmission_loss.spacing_12 = (
    0.05
)

config.transmission_loss.spacing_34 = (
    0.05
)

config.transmission_loss.tube_diameter = (
    0.15
)

config.transmission_loss.automatic_valid_frequency_range = (
    True
)


# ============================================================
# FREQUÊNCIA
#
# Evitamos 0 Hz neste teste matemático porque
# sin(k*s)=0 em DC.
# ============================================================

frequency = np.arange(
    100.0,
    2001.0,
    1.0,
)


# ============================================================
# PROPRIEDADES DO AR
# ============================================================

c = (
    config.acoustics.speed_of_sound
)

rho = (
    config.acoustics.air_density
)

Z0 = (
    rho * c
)

k = (
    2.0
    * np.pi
    * frequency
    / c
)


s12 = (
    config.transmission_loss.spacing_12
)

s34 = (
    config.transmission_loss.spacing_34
)


# ============================================================
# MATRIZ ABCD CONHECIDA
#
# Usamos valores constantes com frequência
# apenas para validar as equações.
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
#
# Definimos duas velocidades normalizadas U3/P3
# suficientemente diferentes.
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
# ESTADO NA POSIÇÃO 2
#
# [P2]   [A B] [P3]
# [U2] = [C D] [U3]
#
# Com P3 = 1:
#
# P2 = A + B*U3
# U2 = C + D*U3
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
# RECONSTRÓI H31
#
# Do código:
#
# U2 =
#
# H31 - cos(ks12)*H32
# ----------------------
# j*Z0*sin(ks12)
#
# Portanto:
#
# H31 =
# cos(ks12)*H32
# +
# j*Z0*sin(ks12)*U2
# ============================================================

H31_A = (
    np.cos(
        k * s12
    )
    * H32_A
    +
    1j
    * Z0
    * np.sin(
        k * s12
    )
    * U2_A
)

H31_B = (
    np.cos(
        k * s12
    )
    * H32_B
    +
    1j
    * Z0
    * np.sin(
        k * s12
    )
    * U2_B
)


# ============================================================
# RECONSTRÓI H34
#
# Do código:
#
# U3 =
#
# cos(ks34) - H34
# -----------------
# j*Z0*sin(ks34)
#
# Portanto:
#
# H34 =
# cos(ks34)
# -
# j*Z0*sin(ks34)*U3
# ============================================================

H34_A = (
    np.cos(
        k * s34
    )
    -
    1j
    * Z0
    * np.sin(
        k * s34
    )
    * U3_A
)

H34_B = (
    np.cos(
        k * s34
    )
    -
    1j
    * Z0
    * np.sin(
        k * s34
    )
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
# ERROS
# ============================================================

error_A = np.nanmax(
    np.abs(
        result.A - A_true
    )
)

error_B = np.nanmax(
    np.abs(
        result.B - B_true
    )
)

error_C = np.nanmax(
    np.abs(
        result.C - C_true
    )
)

error_D = np.nanmax(
    np.abs(
        result.D - D_true
    )
)


# ============================================================
# TL TEÓRICA DA MATRIZ CONHECIDA
# ============================================================

transfer_true = (
    0.5
    *
    (
        A_true
        +
        B_true / Z0
        +
        Z0 * C_true
        +
        D_true
    )
)

TL_true = (
    20.0
    * np.log10(
        np.abs(
            transfer_true
        )
    )
)


error_TL = np.nanmax(
    np.abs(
        result.transmission_loss
        -
        TL_true
    )
)


# ============================================================
# RESULTADOS
# ============================================================

print()
print("====================================")
print("TESTE TL 02 - MATEMÁTICA")
print("====================================")

print()
print(
    f"Erro máximo em A: "
    f"{error_A:.3e}"
)

print(
    f"Erro máximo em B: "
    f"{error_B:.3e}"
)

print(
    f"Erro máximo em C: "
    f"{error_C:.3e}"
)

print(
    f"Erro máximo em D: "
    f"{error_D:.3e}"
)

print(
    f"Erro máximo em TL: "
    f"{error_TL:.3e} dB"
)


# ============================================================
# VALIDAÇÃO
# ============================================================

tolerance = 1e-9

abcd_ok = (
    error_A < tolerance
    and
    error_B < tolerance
    and
    error_C < tolerance
    and
    error_D < tolerance
)

tl_ok = (
    error_TL < tolerance
)


if (
    abcd_ok
    and
    tl_ok
):

    print()
    print(
        "TESTE APROVADO."
    )

else:

    print()
    print(
        "TESTE REPROVADO."
    )

#---------------------
#TESTE PARA O EXPORTER
#---------------------

from exporter import DataExporter


saved = (
    DataExporter.export_complete_tl_experiment(

        config=config,

        measurements=experiment.measurements,

        tl_result=result,

        directory="results/teste_exportador",
    )
)


print()
print("====================================")
print("ARQUIVOS SALVOS")
print("====================================")

print()

print(
    f"TL:"
)

print(
    saved["tl"]
)

print()

print(
    f"Metadados:"
)

print(
    saved["metadata"]
)

print()

print(
    "FRFs:"
)

for filepath in saved["frfs"]:

    print(
        f"  {filepath}"
    )
