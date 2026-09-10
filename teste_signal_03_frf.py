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
print("TESTE 3 - FRF")
print("====================================")


try:

    # ========================================================
    # CONFIGURAÇÃO
    # ========================================================

    fs = 12800.0

    duration = 8.0

    gain_expected = 2.5

    rng = np.random.default_rng(
        seed=12345
    )

    n = int(
        fs * duration
    )

    # ========================================================
    # SINAL DE REFERÊNCIA
    #
    # Ruído branco é adequado para testar uma FRF
    # em uma ampla faixa de frequência.
    # ========================================================

    x = rng.normal(
        loc=0.0,
        scale=1.0,
        size=n,
    )

    # ========================================================
    # RESPOSTA
    # ========================================================

    y = (
        gain_expected
        * x
    )

    # Pequeno ruído independente
    y += rng.normal(
        loc=0.0,
        scale=0.01,
        size=n,
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

            nperseg=4096,

            overlap=0.50,

            estimator=(
                FRFEstimator.H1
            ),

            coherence_threshold=0.90,
        )
    )

    # ========================================================
    # FAIXA DE TESTE
    #
    # Ignoramos DC e extremidades.
    # ========================================================

    band = (
        (result.frequency >= 100.0)
        &
        (result.frequency <= 5000.0)
    )

    valid = (
        band
        & result.valid_mask
    )

    magnitude_mean = np.mean(
        result.magnitude[
            valid
        ]
    )

    coherence_mean = np.mean(
        result.coherence[
            valid
        ]
    )

    print()
    print(
        f"Ganho esperado: "
        f"{gain_expected:.4f}"
    )

    print(
        f"Ganho médio calculado: "
        f"{magnitude_mean:.4f}"
    )

    print()
    print(
        f"Coerência média: "
        f"{coherence_mean:.6f}"
    )

    print()

    gain_ok = np.isclose(
        magnitude_mean,
        gain_expected,
        rtol=0.02,
    )

    coherence_ok = (
        coherence_mean
        >= 0.99
    )

    if (
        gain_ok
        and coherence_ok
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