from daq import (
    NIDaqDevice,
    DAQError,
)


print()
print("====================================")
print("TESTE 2 - INFORMAÇÕES DA DAQ")
print("====================================")


daq = None


try:

    daq = NIDaqDevice()

    daq.connect()

    print()
    print(
        f"Dispositivo selecionado: "
        f"{daq.device_name}"
    )

    info = daq.get_device_info()

    print()
    print("Produto:")
    print(
        f"  {info['product_type']}"
    )

    print()
    print("Número de série:")
    print(
        f"  {info['serial_number']}"
    )

    print()
    print("Amostragem simultânea:")

    print(
        f"  "
        f"{info['simultaneous_sampling']}"
    )

    print()
    print("Canais de entrada analógica:")

    for channel in info["ai_channels"]:

        print(
            f"  - {channel}"
        )


except DAQError as error:

    print()
    print("ERRO:")
    print(error)


finally:

    if daq is not None:
        daq.disconnect()