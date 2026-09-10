from config import (
    AppConfig,
    ChannelConfig
)


# ============================================================
# CRIA CONFIGURAÇÃO
# ============================================================

config = AppConfig()

# Dois microfones iniciais
config.channels = [

    ChannelConfig(
        physical_channel="Dev1/ai0",
        name="Microfone referência - Posição 3",
        sensitivity_mv_pa=50.0
    ),

    ChannelConfig(
        physical_channel="Dev1/ai1",
        name="Microfone móvel",
        sensitivity_mv_pa=50.0
    )
]


# ============================================================
# VALIDA CONFIGURAÇÃO
# ============================================================

try:

    config.validate()

    print("Configuração válida!")

except ValueError as erro:

    print("Erro na configuração:")
    print(erro)


# ============================================================
# INFORMAÇÕES DA AQUISIÇÃO
# ============================================================

print()
print("====================================")
print("AQUISIÇÃO")
print("====================================")

print(
    f"Fs = "
    f"{config.acquisition.sample_rate:.0f} Hz"
)

print(
    f"N = "
    f"{config.acquisition.num_samples}"
)

print(
    f"Duração = "
    f"{config.acquisition.block_duration:.3f} s"
)

print(
    f"Resolução = "
    f"{config.acquisition.frequency_resolution:.3f} Hz"
)

print(
    f"Nyquist = "
    f"{config.acquisition.nyquist_frequency:.1f} Hz"
)


# ============================================================
# INFORMAÇÕES ACÚSTICAS
# ============================================================

print()
print("====================================")
print("ACÚSTICA")
print("====================================")

print(
    f"Temperatura = "
    f"{config.acoustics.temperature_c:.1f} °C"
)

print(
    f"Velocidade do som = "
    f"{config.acoustics.speed_of_sound:.2f} m/s"
)


# ============================================================
# ENSAIO DE TL
# ============================================================

print()
print("====================================")
print("PERDA DE TRANSMISSÃO")
print("====================================")

print(
    f"Microfone fixo: posição "
    f"{config.transmission_loss.reference_position}"
)

print(
    f"Posições móveis: "
    f"{config.transmission_loss.mobile_positions}"
)

print(
    f"Distância 1-2 = "
    f"{config.transmission_loss.spacing_12 * 1000:.1f} mm"
)

print(
    f"Distância 3-4 = "
    f"{config.transmission_loss.spacing_34 * 1000:.1f} mm"
)

print(
    f"Faixa válida = "
    f"{config.transmission_loss.valid_frequency_min:.1f}"
    f" - "
    f"{config.transmission_loss.valid_frequency_max:.1f} Hz"
)