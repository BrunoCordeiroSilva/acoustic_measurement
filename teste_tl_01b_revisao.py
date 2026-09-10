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
    TransmissionLossError,
    TLExperimentState,
    MeasurementAcceptance,
)


class ReviewController:

    def acquire_frf(
        self,
        **kwargs,
    ):

        frequency = np.arange(
            0.0,
            6401.0,
            1.0,
        )

        H = np.ones(
            frequency.shape,
            dtype=np.complex128,
        )

        frf = FRFResult(
            frequency=frequency,
            H=H,
            coherence=np.full(
                frequency.shape,
                0.80,
            ),
            Gxx=np.ones_like(
                frequency
            ),
            Gyy=np.ones_like(
                frequency
            ),
            Gxy=np.ones(
                frequency.shape,
                dtype=np.complex128,
            ),
            valid_mask=np.zeros(
                frequency.shape,
                dtype=bool,
            ),
        )

        quality = MeasurementQualityReport(
            status=MeasurementQualityStatus.REVIEW,
            coherence_threshold=0.90,
            valid_frequency_min=300.0,
            valid_frequency_max=3000.0,
            coherence_mean=0.80,
            coherence_min=0.80,
            coherence_valid_percentage=0.0,
            clipping_detected=False,
            warnings=[
                "Coerência abaixo do limite."
            ],
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


experiment = TransmissionLossExperiment(
    controller=ReviewController(),
    config=config,
)


print()
print("====================================")
print("TESTE TL 01B - REVISÃO")
print("====================================")


experiment.start()

experiment.measure_current_step()

assert (
    experiment.state
    == TLExperimentState.AWAITING_REVIEW
)


# ------------------------------------------------------------
# TENTA ACEITAR SEM AUTORIZAÇÃO
# ------------------------------------------------------------

try:

    experiment.accept_measurement()

    raise AssertionError(
        "A medição com aviso foi aceita "
        "sem confirmação."
    )

except TransmissionLossError:

    print()
    print(
        "Bloqueio de medição com aviso: OK"
    )


# ------------------------------------------------------------
# REPETE
# ------------------------------------------------------------

experiment.repeat_measurement()

assert (
    experiment.state
    == TLExperimentState.READY
)

print(
    "Função repetir: OK"
)


# ------------------------------------------------------------
# MEDE NOVAMENTE E ACEITA COM AVISO
# ------------------------------------------------------------

experiment.measure_current_step()

experiment.accept_measurement(
    accept_warning=True
)

stored = list(
    experiment.measurements.values()
)[0]

assert (
    stored.acceptance
    == MeasurementAcceptance
       .ACCEPTED_WITH_WARNING
)

print(
    "Aceitar com aviso: OK"
)

print()
print(
    "TESTE APROVADO."
)