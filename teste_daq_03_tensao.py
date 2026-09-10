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
    # CONECTA AUTOMATICAMENTE AO NI-9234
    # ========================================================

    daq = NIDaqDevice()

    daq.connect()

    print()
    print(
        f"Dispositivo selecionado: "
        f"{daq.device_name}"
    )

    # ========================================================
    # DESCOBRE OS CANAIS FÍSICOS
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

    if len(available_channels) < 2:

        raise DAQError(
            "São necessários pelo menos "
            "2 canais analógicos."
        )

    # ========================================================
    # CONFIGURAÇÃO DOS CANAIS
    # ========================================================

    channels = [

        ChannelConfig(

            physical_channel=(
                available_channels[0]
            ),

            name="Canal 0",

            sensor_type=(
                SensorType.VOLTAGE
            ),

            min_voltage=-5.0,

            max_voltage=5.0,

            iepe_enabled=False,
        ),

        ChannelConfig(

            physical_channel=(
                available_channels[1]
            ),

            name="Canal 1",

            sensor_type=(
                SensorType.VOLTAGE
            ),

            min_voltage=-5.0,

            max_voltage=5.0,

            iepe_enabled=False,
        ),
    ]

    # ========================================================
    # CONFIGURA A TASK
    # ========================================================

    daq.configure(

        channels=channels,

        acquisition=acquisition,
    )

    print()
    print("====================================")
    print("TESTE - AQUISIÇÃO EM TENSÃO")
    print("====================================")

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
        f"N: "
        f"{acquisition.num_samples}"
    )

    # ========================================================
    # AQUISIÇÃO
    # ========================================================

    print()
    print("Iniciando aquisição...")

    result = daq.acquire()

    print("Aquisição concluída.")

    # ========================================================
    # INFORMAÇÕES
    # ========================================================

    print()
    print(
        f"Formato da matriz: "
        f"{result.data.shape}"
    )

    print(
        f"Duração: "
        f"{result.duration:.6f} s"
    )

    # ========================================================
    # ESTATÍSTICAS
    # ========================================================

    for i in range(
        result.num_channels
    ):

        signal = result.data[:, i]

        rms = np.sqrt(
            np.mean(signal ** 2)
        )

        peak = np.max(
            np.abs(signal)
        )

        mean = np.mean(signal)

        print()
        print(
            f"{result.channel_names[i]}"
        )

        print(
            f"  Canal físico: "
            f"{result.physical_channels[i]}"
        )

        print(
            f"  Média: "
            f"{mean:.6f} V"
        )

        print(
            f"  RMS: "
            f"{rms:.6f} V"
        )

        print(
            f"  Pico: "
            f"{peak:.6f} V"
        )


except DAQError as error:

    print()
    print("ERRO:")
    print(error)


finally:

    if daq is not None:

        daq.disconnect()

        print()
        print("DAQ desconectada.")