from daq import (
    NIDaqDevice,
    DAQError,
)


print()
print("====================================")
print("TESTE 1 - DISPOSITIVOS NI")
print("====================================")


try:

    devices = (
        NIDaqDevice.discover_devices()
    )

    if not devices:

        print(
            "Nenhum dispositivo NI-DAQmx "
            "foi encontrado."
        )

    else:

        print(
            f"{len(devices)} dispositivo(s) "
            "encontrado(s):"
        )

        print()

        for device in devices:

            print(
                f"  - {device}"
            )


except DAQError as error:

    print()
    print("ERRO:")
    print(error)