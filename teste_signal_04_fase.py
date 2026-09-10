import numpy as np

from config import (
    WindowType,
    FRFEstimator,
)

from signal_processing import (
    FRFProcessor,
    SignalProcessingError,
)


print()
print("====================================")
print("TESTE 4 - FASE DA FRF")
print("====================================")


try:

    fs = 12800.0

    duration = 8.0

    frequency_signal = 1000.0

    gain = 2.0

    phase_expected_deg = 45.0

    phase_expected_rad = np.deg2rad(
        phase_expected_deg
    )

    n = int(
        fs * duration
    )

    time = (
        np.arange(n)
        / fs
    )

    # ========================================================
    # REFERÊNCIA
    # ========================================================

    x = np.sin(
        2.0
        * np.pi
        * frequency_signal
        * time
    )

    # ========================================================
    # RESPOSTA
    #
    # ganho = 2
    # fase = +45°
    # ========================================================

    y = (
        gain
        * np.sin(
            2.0
            * np.pi
            * frequency_signal
            * time
            + phase_expected_rad
        )
    )

    # ========================================================
    # FRF
    # ========================================================

    result = (
        FRFProcessor.calculate_frf(

            x=x,

            y=y,

            sample_rate=fs,

            window_type=(
                WindowType.HANN
            ),

            nperseg=12800,

            overlap=0.0,

            estimator=(
                FRFEstimator.H1
            ),

            coherence_threshold=0.90,
        )
    )

    # ========================================================
    # LOCALIZA 1000 Hz
    # ========================================================

    index = np.argmin(
        np.abs(
            result.frequency
            - frequency_signal
        )
    )

    magnitude = (
        result.magnitude[index]
    )

    phase_deg = (
        result.phase_deg[index]
    )

    coherence = (
        result.coherence[index]
    )

    print()
    print(
        f"Frequência: "
        f"{result.frequency[index]:.2f} Hz"
    )

    print()

    print(
        f"Ganho esperado: "
        f"{gain:.4f}"
    )

    print(
        f"Ganho calculado: "
        f"{magnitude:.4f}"
    )

    print()

    print(
        f"Fase esperada: "
        f"{phase_expected_deg:.2f}°"
    )

    print(
        f"Fase calculada: "
        f"{phase_deg:.2f}°"
    )

    print()

    print(
        f"Coerência: "
        f"{coherence:.6f}"
    )

    magnitude_ok = np.isclose(
        magnitude,
        gain,
        rtol=0.01,
    )

    phase_ok = np.isclose(
        phase_deg,
        phase_expected_deg,
        atol=1.0,
    )

    if (
        magnitude_ok
        and phase_ok
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


except SignalProcessingError as error:

    print()
    print("ERRO:")
    print(error)