import numpy as np

from signal_processing import (
    SignalProcessor,
    SignalProcessingError,
)


print()
print("====================================")
print("TESTE 2 - RMS E SPL")
print("====================================")


try:

    fs = 12800.0

    duration = 1.0

    frequency = 1000.0

    # ========================================================
    # Queremos exatamente 1 Pa RMS
    #
    # seno:
    #
    # RMS = A / sqrt(2)
    #
    # portanto:
    #
    # A = sqrt(2) Pa
    # ========================================================

    amplitude_peak = np.sqrt(
        2.0
    )

    n = int(
        fs * duration
    )

    time = (
        np.arange(n)
        / fs
    )

    pressure = (
        amplitude_peak
        * np.sin(
            2.0
            * np.pi
            * frequency
            * time
        )
    )

    pressure_rms = (
        SignalProcessor.rms(
            pressure
        )
    )

    spl = (
        SignalProcessor.spl(
            pressure,
            reference_pressure=20e-6,
        )
    )

    print()
    print(
        f"RMS esperado: "
        f"1.000000 Pa"
    )

    print(
        f"RMS calculado: "
        f"{pressure_rms:.6f} Pa"
    )

    print()

    print(
        f"SPL esperado: "
        f"aproximadamente 93.98 dB"
    )

    print(
        f"SPL calculado: "
        f"{spl:.3f} dB"
    )

    if (
        np.isclose(
            pressure_rms,
            1.0,
            rtol=1e-3,
        )
        and np.isclose(
            spl,
            93.9794,
            atol=0.01,
        )
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