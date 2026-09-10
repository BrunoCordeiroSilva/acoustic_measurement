import numpy as np

from config import WindowType

from signal_processing import (
    SignalProcessor,
    SignalProcessingError,
)


print()
print("====================================")
print("TESTE 1 - FFT")
print("====================================")


try:

    # ========================================================
    # SINAL SINTÉTICO
    # ========================================================

    fs = 12800.0

    duration = 1.0

    frequency_signal = 1000.0

    amplitude = 2.0

    n = int(
        fs * duration
    )

    time = (
        np.arange(n)
        / fs
    )

    x = (
        amplitude
        * np.sin(
            2.0
            * np.pi
            * frequency_signal
            * time
        )
    )

    # ========================================================
    # FFT
    # ========================================================

    result = SignalProcessor.fft(

        x=x,

        sample_rate=fs,

        window_type=WindowType.HANN,
    )

    # ========================================================
    # PICO ESPECTRAL
    # ========================================================

    peak_index = np.argmax(
        result.magnitude
    )

    detected_frequency = (
        result.frequency[
            peak_index
        ]
    )

    detected_amplitude = (
        result.magnitude[
            peak_index
        ]
    )

    print()
    print(
        f"Frequência esperada: "
        f"{frequency_signal:.2f} Hz"
    )

    print(
        f"Frequência detectada: "
        f"{detected_frequency:.2f} Hz"
    )

    print()
    print(
        f"Amplitude esperada: "
        f"{amplitude:.4f}"
    )

    print(
        f"Amplitude detectada: "
        f"{detected_amplitude:.4f}"
    )

    print()

    # ========================================================
    # VALIDAÇÃO
    # ========================================================

    frequency_ok = np.isclose(
        detected_frequency,
        frequency_signal,
        atol=1.0,
    )

    amplitude_ok = np.isclose(
        detected_amplitude,
        amplitude,
        rtol=0.01,
    )

    if (
        frequency_ok
        and amplitude_ok
    ):

        print(
            "TESTE APROVADO."
        )

    else:

        print(
            "TESTE REPROVADO."
        )


except SignalProcessingError as error:

    print()
    print("ERRO:")
    print(error)