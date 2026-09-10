import numpy as np

from config import (
    AcquisitionConfig,
    ChannelConfig,
    SensorType,
)

from daq import (
    NIDaqDevice,
    DAQError,
)


# ============================================================
# IMPORTANTE
#
# TROQUE ESTES VALORES PELAS SENSIBILIDADES
# REAIS DOS MICROFONES QUANDO USAR O HARDWARE FÍSICO
# ============================================================

sensibilidade_mic_0 = 50.0  # mV/Pa
sensibilidade_mic_1 = 50.0  # mV/Pa


# ============================================================
# AQUISIÇÃO
# ============================================================

acquisition = AcquisitionConfig(

    sample_rate=12800,

    num_samples=12800,

    num_averages=1,
)


# ============================================================
# TESTE
# ============================================================

daq = None


try:

    # ========================================================
    # 1. CONECTA AUTOMATICAMENTE AO NI-9234
    # ========================================================

    daq = NIDaqDevice()

    daq.connect()

    print()
    print("====================================")
    print("TESTE 4 - MICROFONES")
    print("====================================")

    print()
    print(
        f"Dispositivo selecionado: "
        f"{daq.device_name}"
    )

    # ========================================================
    # 2. DESCOBRE OS CANAIS DISPONÍVEIS
    # ========================================================

    available_channels = (
        daq.get_available_ai_channels()
    )

    print()
    print("Canais disponíveis:")

    for channel in available_channels:

        print(
            f"  - {channel}"
        )

    # ========================================================
    # 3. VERIFICA SE HÁ PELO MENOS 2 CANAIS
    # ========================================================

    if len(available_channels) < 2:

        raise DAQError(
            "São necessários pelo menos "
            "2 canais analógicos para este teste."
        )

    # ========================================================
    # 4. CONFIGURA OS MICROFONES
    #
    # Os canais físicos são obtidos diretamente da DAQ.
    #
    # Virtual:
    #   cDAQ1Mod1/ai0
    #   cDAQ1Mod1/ai1
    #
    # Físico:
    #   pode ser Dev1/ai0, Dev1/ai1, etc.
    # ========================================================

    channels = [

        ChannelConfig(

            physical_channel=(
                available_channels[0]
            ),

            name=(
                "Microfone referência - "
                "Posição 3"
            ),

            sensor_type=(
                SensorType.MICROPHONE
            ),

            sensitivity_mv_pa=(
                sensibilidade_mic_0
            ),

            iepe_enabled=True,

            iepe_current_a=0.002,
        ),

        ChannelConfig(

            physical_channel=(
                available_channels[1]
            ),

            name="Microfone móvel",

            sensor_type=(
                SensorType.MICROPHONE
            ),

            sensitivity_mv_pa=(
                sensibilidade_mic_1
            ),

            iepe_enabled=True,

            iepe_current_a=0.002,
        ),
    ]

    # ========================================================
    # 5. MOSTRA A CONFIGURAÇÃO
    # ========================================================

    print()
    print("Configuração dos microfones:")

    for channel in channels:

        print()
        print(
            f"  Nome: "
            f"{channel.name}"
        )

        print(
            f"  Canal físico: "
            f"{channel.physical_channel}"
        )

        print(
            f"  Sensibilidade: "
            f"{channel.sensitivity_mv_pa:.3f} mV/Pa"
        )

        print(
            f"  IEPE: "
            f"{channel.iepe_enabled}"
        )

        print(
            f"  Corrente IEPE: "
            f"{channel.iepe_current_a * 1000:.3f} mA"
        )

    # ========================================================
    # 6. CONFIGURA A TASK
    # ========================================================

    daq.configure(
        channels=channels,
        acquisition=acquisition,
    )

    print()
    print(
        f"Fs solicitada: "
        f"{acquisition.sample_rate:.3f} Hz"
    )

    print(
        f"Fs efetiva: "
        f"{daq.actual_sample_rate:.3f} Hz"
    )

    print(
        f"N por canal: "
        f"{acquisition.num_samples}"
    )

    # ========================================================
    # 7. AQUISIÇÃO
    # ========================================================

    print()
    print(
        "Iniciando aquisição..."
    )

    result = daq.acquire()

    print(
        "Aquisição concluída."
    )

    # ========================================================
    # 8. INFORMAÇÕES GERAIS
    # ========================================================

    print()
    print(
        f"Formato da matriz: "
        f"{result.data.shape}"
    )

    print(
        f"Número de canais: "
        f"{result.num_channels}"
    )

    print(
        f"Número de amostras: "
        f"{result.num_samples}"
    )

    print(
        f"Duração: "
        f"{result.duration:.6f} s"
    )

    print(
        f"Fs efetiva: "
        f"{result.sample_rate:.3f} Hz"
    )

    # ========================================================
    # 9. ESTATÍSTICAS ACÚSTICAS
    # ========================================================

    p_ref = 20e-6

    for i in range(
        result.num_channels
    ):

        pressure = (
            result.data[:, i]
        )

        # ----------------------------------------------------
        # Remove componente DC somente para
        # as estatísticas acústicas
        # ----------------------------------------------------

        pressure_ac = (
            pressure
            - np.mean(pressure)
        )

        # ----------------------------------------------------
        # RMS
        # ----------------------------------------------------

        rms = np.sqrt(
            np.mean(
                pressure_ac ** 2
            )
        )

        # ----------------------------------------------------
        # Pico
        # ----------------------------------------------------

        peak = np.max(
            np.abs(
                pressure_ac
            )
        )

        # ----------------------------------------------------
        # SPL
        #
        # Lp = 20 log10(prms / pref)
        # pref = 20 µPa
        # ----------------------------------------------------

        if rms > 0:

            spl = (
                20.0
                * np.log10(
                    rms / p_ref
                )
            )

        else:

            spl = -np.inf

        # ----------------------------------------------------
        # Impressão
        # ----------------------------------------------------

        print()
        print(
            "------------------------------------"
        )

        print(
            result.channel_names[i]
        )

        print(
            f"  Canal físico: "
            f"{result.physical_channels[i]}"
        )

        print(
            f"  RMS: "
            f"{rms:.6f} Pa"
        )

        print(
            f"  Pico: "
            f"{peak:.6f} Pa"
        )

        print(
            f"  SPL: "
            f"{spl:.2f} dB"
        )


except DAQError as error:

    print()
    print("ERRO DAQ:")
    print(error)


except Exception as error:

    print()
    print("ERRO INESPERADO:")
    print(error)


finally:

    if daq is not None:

        daq.disconnect()

        print()
        print("DAQ desconectada.")