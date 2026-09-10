from dataclasses import dataclass

import numpy as np

from config import AppConfig

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
)


# ============================================================
# CONTROLLER FALSO
# ============================================================

class FakeController:
    """
    Simula o AcquisitionController.

    Cada chamada de acquire_frf retorna
    uma FRF fictícia válida.
    """

    def __init__(self):

        self.counter = 0

    def acquire_frf(
        self,
        reference_channel_index=0,
        response_channel_index=1,
        progress_callback=None,
        message_callback=None,
    ):

        self.counter += 1

        frequency = np.arange(
            0.0,
            6401.0,
            1.0,
        )

        H = np.ones(
            frequency.shape,
            dtype=np.complex128,
        )

        coherence = np.ones_like(
            frequency,
            dtype=np.float64,
        )

        Gxx = np.ones_like(
            frequency,
            dtype=np.float64,
        )

        Gyy = np.ones_like(
            frequency,
            dtype=np.float64,
        )

        Gxy = np.ones(
            frequency.shape,
            dtype=np.complex128,
        )

        valid_mask = np.ones_like(
            frequency,
            dtype=bool,
        )

        frf = FRFResult(
            frequency=frequency,
            H=H,
            coherence=coherence,
            Gxx=Gxx,
            Gyy=Gyy,
            Gxy=Gxy,
            valid_mask=valid_mask,
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

# O AppConfig exige dois canais ativos
# para validar ensaio de TL.
#
# Para este teste da máquina de estados,
# não precisamos de hardware real.
#
# Portanto desabilitamos temporariamente essa
# validação criando dois canais fictícios.

from config import (
    ChannelConfig,
    SensorType,
)

config.channels = [

    ChannelConfig(
        physical_channel="Fake/ai0",
        name="Referência",
        sensor_type=SensorType.MICROPHONE,
    ),

    ChannelConfig(
        physical_channel="Fake/ai1",
        name="Móvel",
        sensor_type=SensorType.MICROPHONE,
    ),
]


# ============================================================
# EXPERIMENTO
# ============================================================

controller = FakeController()

experiment = TransmissionLossExperiment(
    controller=controller,
    config=config,
)


# ============================================================
# TESTE
# ============================================================

print()
print("====================================")
print("TESTE TL 01 - MÁQUINA DE ESTADOS")
print("====================================")


# ------------------------------------------------------------
# START
# ------------------------------------------------------------

experiment.start()

assert (
    experiment.state
    == TLExperimentState.READY
)

assert (
    experiment.current_step
    == TLMeasurementStep.H31_A
)

print()
print("Estado inicial:")
print(
    experiment.state.value
)

print(
    "Etapa:",
    experiment.current_step.value,
)


# ============================================================
# CARGA A
# ============================================================

expected_a = [

    TLMeasurementStep.H31_A,

    TLMeasurementStep.H32_A,

    TLMeasurementStep.H34_A,
]


for step in expected_a:

    assert (
        experiment.current_step
        == step
    )

    print()
    print(
        "Instrução:"
    )

    print(
        experiment.get_current_instruction()
    )

    result = (
        experiment.measure_current_step()
    )

    assert (
        experiment.state
        == TLExperimentState.AWAITING_REVIEW
    )

    assert (
        result.quality.status
        == MeasurementQualityStatus.VALID
    )

    experiment.accept_measurement()

    print(
        f"{step.value} aceita."
    )


# ============================================================
# TROCA DE CARGA
# ============================================================

assert (
    experiment.state
    == TLExperimentState.WAITING_LOAD_CHANGE
)

assert (
    experiment.current_step
    == TLMeasurementStep.H31_B
)

print()
print(
    "Estado após Carga A:"
)

print(
    experiment.state.value
)

experiment.confirm_load_change()

assert (
    experiment.state
    == TLExperimentState.READY
)


# ============================================================
# CARGA B
# ============================================================

expected_b = [

    TLMeasurementStep.H31_B,

    TLMeasurementStep.H32_B,

    TLMeasurementStep.H34_B,
]


for step in expected_b:

    assert (
        experiment.current_step
        == step
    )

    experiment.measure_current_step()

    assert (
        experiment.state
        == TLExperimentState.AWAITING_REVIEW
    )

    experiment.accept_measurement()

    print(
        f"{step.value} aceita."
    )


# ============================================================
# PRONTO PARA PROCESSAR
# ============================================================

assert (
    experiment.state
    == TLExperimentState.READY_TO_PROCESS
)

assert (
    experiment.current_step
    is None
)

assert (
    len(
        experiment.measurements
    )
    == 6
)

print()
print(
    "Estado final:"
)

print(
    experiment.state.value
)

print()
print(
    "Número de medições armazenadas:",
    len(
        experiment.measurements
    ),
)

print()
print(
    "TESTE APROVADO."
)