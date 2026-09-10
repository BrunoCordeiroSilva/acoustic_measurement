from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import nidaqmx

from nidaqmx.constants import (
    AcquisitionType,
    ExcitationSource,
    SoundPressureUnits,
    TerminalConfiguration,
)

from nidaqmx.stream_readers import AnalogMultiChannelReader
from nidaqmx.system import System

from config import (
    AcquisitionConfig,
    ChannelConfig,
    SensorType,
)


# ============================================================
# EXCEÇÕES
# ============================================================

class DAQError(RuntimeError):
    """
    Exceção específica da camada de aquisição.
    """

    pass


# ============================================================
# RESULTADO DE AQUISIÇÃO
# ============================================================

@dataclass
class AcquisitionData:
    """
    Resultado de uma aquisição finita.

    time:
        vetor de tempo [s]

    data:
        matriz no formato:
            (n_amostras, n_canais)

    sample_rate:
        taxa efetiva da aquisição [Hz]

    channel_names:
        nomes lógicos dos canais

    physical_channels:
        canais físicos da NI
    """

    time: np.ndarray
    data: np.ndarray

    sample_rate: float

    channel_names: list[str]
    physical_channels: list[str]

    # --------------------------------------------------------

    @property
    def num_samples(self) -> int:
        """
        Número de amostras adquiridas.
        """

        return self.data.shape[0]

    # --------------------------------------------------------

    @property
    def num_channels(self) -> int:
        """
        Número de canais adquiridos.
        """

        return self.data.shape[1]

    # --------------------------------------------------------

    @property
    def duration(self) -> float:
        """
        Duração efetiva da aquisição [s].
        """

        return self.num_samples / self.sample_rate


# ============================================================
# INTERFACE COM NI-DAQmx
# ============================================================

class NIDaqDevice:
    """
    Camada de acesso ao hardware NI-DAQmx.

    Responsabilidades:

    - detectar dispositivos NI-DAQmx
    - identificar automaticamente um NI-9234
    - listar canais analógicos
    - configurar canais
    - configurar temporização
    - iniciar aquisição
    - ler amostras
    - parar e liberar recursos

    Esta classe NÃO calcula:

    - FFT
    - FRF
    - coerência
    - H31/H32/H34
    - TL
    """

    # ========================================================
    # INICIALIZAÇÃO
    # ========================================================

    def __init__(
        self,
        device_name: Optional[str] = None,
    ):

        self.device_name = device_name

        self._system = System.local()

        self._task: Optional[nidaqmx.Task] = None

        self._reader: Optional[
            AnalogMultiChannelReader
        ] = None

        self._configured_channels: list[
            ChannelConfig
        ] = []

        self._acquisition_config: Optional[
            AcquisitionConfig
        ] = None

        self._actual_sample_rate: Optional[
            float
        ] = None

    # ========================================================
    # DETECÇÃO DE HARDWARE
    # ========================================================

    @staticmethod
    def discover_devices() -> list[str]:
        """
        Lista todos os dispositivos disponíveis
        no NI-DAQmx.

        Exemplo:

            [
                "cDAQ1",
                "cDAQ1Mod1",
            ]

        Um chassis cDAQ pode aparecer nessa lista mesmo
        sem possuir canais analógicos próprios.
        """

        try:

            system = System.local()

            devices = [
                device.name
                for device in system.devices
            ]

            return devices

        except Exception as exc:

            raise DAQError(
                "Não foi possível consultar "
                "os dispositivos NI-DAQmx."
            ) from exc

    # ========================================================

    @staticmethod
    def discover_ai_devices() -> list[str]:
        """
        Lista somente dispositivos que possuem
        canais físicos de entrada analógica.

        Exemplo:

            [
                "cDAQ1Mod1",
            ]

        Isso evita que um chassis cDAQ, como o
        cDAQ-9174, seja considerado dispositivo
        de aquisição.
        """

        try:

            system = System.local()

            devices: list[str] = []

            for device in system.devices:

                try:

                    ai_channels = list(
                        device.ai_physical_chans
                    )

                except Exception:
                    continue

                if ai_channels:
                    devices.append(
                        device.name
                    )

            return devices

        except Exception as exc:

            raise DAQError(
                "Não foi possível consultar "
                "os dispositivos de entrada analógica."
            ) from exc

    # ========================================================

    def connect(
        self,
        device_name: Optional[str] = None,
    ) -> None:
        """
        Seleciona o dispositivo NI a ser utilizado.

        Comportamento:

        1. Se um nome for fornecido explicitamente,
           utiliza esse dispositivo.

        2. Se nenhum nome for fornecido, procura
           automaticamente por um NI-9234.

        3. Um chassis cDAQ sem canais AI é ignorado.

        Exemplo esperado com dispositivo simulado:

            cDAQ1
                chassis cDAQ-9174

            cDAQ1Mod1
                NI-9234
                ai0
                ai1
                ai2
                ai3
        """

        # ----------------------------------------------------
        # Nome explicitamente informado
        # ----------------------------------------------------

        if device_name is not None:
            self.device_name = device_name

        # ----------------------------------------------------
        # Todos os dispositivos NI
        # ----------------------------------------------------

        devices = self.discover_devices()

        if not devices:

            raise DAQError(
                "Nenhum dispositivo NI-DAQmx "
                "foi encontrado."
            )

        # ----------------------------------------------------
        # Seleção automática do NI-9234
        # ----------------------------------------------------

        if not self.device_name:

            ni9234_devices: list[str] = []

            for name in devices:

                try:

                    dev = self._system.devices[name]

                    product_type = (
                        dev.product_type
                        or ""
                    )

                    ai_channels = list(
                        dev.ai_physical_chans
                    )

                except Exception:
                    continue

                # --------------------------------------------
                # O dispositivo precisa:
                #
                # 1. ser identificado como 9234
                # 2. possuir canais de entrada analógica
                # --------------------------------------------

                if (
                    "9234" in product_type.upper()
                    and len(ai_channels) > 0
                ):

                    ni9234_devices.append(
                        name
                    )

            # -----------------------------------------------
            # Nenhum NI-9234 encontrado
            # -----------------------------------------------

            if not ni9234_devices:

                available_info = []

                for name in devices:

                    try:

                        dev = self._system.devices[
                            name
                        ]

                        available_info.append(
                            f"{name} "
                            f"({dev.product_type})"
                        )

                    except Exception:

                        available_info.append(
                            name
                        )

                device_text = ", ".join(
                    available_info
                )

                raise DAQError(
                    "Nenhum módulo NI-9234 com "
                    "canais de entrada analógica "
                    "foi encontrado.\n\n"
                    "Dispositivos NI-DAQmx "
                    f"detectados: {device_text}"
                )

            # -----------------------------------------------
            # Seleciona o primeiro NI-9234 disponível
            # -----------------------------------------------

            self.device_name = (
                ni9234_devices[0]
            )

        # ----------------------------------------------------
        # Validação do dispositivo informado
        # ----------------------------------------------------

        if self.device_name not in devices:

            raise DAQError(
                f"O dispositivo "
                f"'{self.device_name}' "
                "não foi encontrado."
            )

        # ----------------------------------------------------
        # Verifica se possui canais AI
        # ----------------------------------------------------

        try:

            dev = self._system.devices[
                self.device_name
            ]

            ai_channels = list(
                dev.ai_physical_chans
            )

        except Exception as exc:

            raise DAQError(
                f"Não foi possível consultar "
                f"o dispositivo "
                f"'{self.device_name}'."
            ) from exc

        if not ai_channels:

            raise DAQError(
                f"O dispositivo "
                f"'{self.device_name}' "
                f"({dev.product_type}) "
                "não possui canais de "
                "entrada analógica."
            )

    # ========================================================
    # PROPRIEDADES DO DISPOSITIVO
    # ========================================================

    @property
    def device(self):
        """
        Retorna o objeto Device correspondente
        ao dispositivo selecionado.
        """

        if not self.device_name:

            raise DAQError(
                "Nenhum dispositivo selecionado."
            )

        try:

            return self._system.devices[
                self.device_name
            ]

        except Exception as exc:

            raise DAQError(
                f"Não foi possível acessar "
                f"o dispositivo "
                f"'{self.device_name}'."
            ) from exc

    # ========================================================

    @property
    def actual_sample_rate(
        self,
    ) -> Optional[float]:
        """
        Taxa efetivamente configurada pelo
        NI-DAQmx.
        """

        return self._actual_sample_rate

    # ========================================================
    # INFORMAÇÕES DO HARDWARE
    # ========================================================

    def get_available_ai_channels(
        self,
    ) -> list[str]:
        """
        Lista os canais analógicos físicos.

        Exemplo:

            cDAQ1Mod1/ai0
            cDAQ1Mod1/ai1
            cDAQ1Mod1/ai2
            cDAQ1Mod1/ai3
        """

        try:

            return [
                ch.name
                for ch
                in self.device.ai_physical_chans
            ]

        except Exception as exc:

            raise DAQError(
                "Não foi possível listar "
                "os canais analógicos."
            ) from exc

    # ========================================================

    def get_device_info(self) -> dict:
        """
        Retorna informações básicas do
        dispositivo selecionado.
        """

        dev = self.device

        info = {
            "name": dev.name,
            "product_type": dev.product_type,
            "serial_number": dev.dev_serial_num,
            "ai_channels": (
                self.get_available_ai_channels()
            ),
        }

        # ----------------------------------------------------
        # Amostragem simultânea
        # ----------------------------------------------------

        try:

            info[
                "simultaneous_sampling"
            ] = (
                dev.ai_simultaneous_sampling_supported
            )

        except Exception:

            info[
                "simultaneous_sampling"
            ] = None

        return info

    # ========================================================
    # GERENCIAMENTO DE TASK
    # ========================================================

    def close_task(self) -> None:
        """
        Fecha e libera a task atual.
        """

        if self._task is not None:

            try:

                self._task.close()

            finally:

                self._task = None

                self._reader = None

                self._configured_channels = []

                self._acquisition_config = None

                self._actual_sample_rate = None

    # ========================================================

    def disconnect(self) -> None:
        """
        Libera recursos do hardware.
        """

        self.close_task()

    # ========================================================
    # CONFIGURAÇÃO
    # ========================================================

    def configure(
        self,
        channels: list[ChannelConfig],
        acquisition: AcquisitionConfig,
    ) -> None:
        """
        Configura a task de aquisição.
        """

        # ----------------------------------------------------
        # Fecha task anterior
        # ----------------------------------------------------

        self.close_task()

        # ----------------------------------------------------
        # Valida aquisição
        # ----------------------------------------------------

        acquisition.validate()

        # ----------------------------------------------------
        # Apenas canais habilitados
        # ----------------------------------------------------

        active_channels = [
            channel
            for channel in channels
            if channel.enabled
        ]

        if not active_channels:

            raise DAQError(
                "Nenhum canal está habilitado."
            )

        # ----------------------------------------------------
        # Validação da quantidade de canais
        #
        # NI-9234 possui 4 canais
        # ----------------------------------------------------

        if len(active_channels) > 4:

            raise DAQError(
                "O NI-9234 suporta no máximo "
                "4 canais de entrada."
            )

        # ----------------------------------------------------
        # Canais disponíveis no hardware
        # ----------------------------------------------------

        available_channels = (
            self.get_available_ai_channels()
        )

        # ----------------------------------------------------
        # Evita canais físicos duplicados
        # ----------------------------------------------------

        physical_channels = [
            channel.physical_channel
            for channel in active_channels
        ]

        if (
            len(physical_channels)
            != len(set(physical_channels))
        ):

            raise DAQError(
                "Existem canais físicos "
                "duplicados na configuração."
            )

        # ----------------------------------------------------
        # Validação individual
        # ----------------------------------------------------

        for channel in active_channels:

            channel.validate()

            if (
                channel.physical_channel
                not in available_channels
            ):

                raise DAQError(
                    f"O canal "
                    f"'{channel.physical_channel}' "
                    "não existe no dispositivo "
                    f"'{self.device_name}'."
                )

        # ----------------------------------------------------
        # Criação da task
        # ----------------------------------------------------

        try:

            task = nidaqmx.Task()

            # ------------------------------------------------
            # Adiciona canais
            # ------------------------------------------------

            for channel in active_channels:

                self._add_channel(
                    task,
                    channel,
                )

            # ------------------------------------------------
            # Temporização
            # ------------------------------------------------

            task.timing.cfg_samp_clk_timing(
                rate=acquisition.sample_rate,
                sample_mode=(
                    AcquisitionType.FINITE
                ),
                samps_per_chan=(
                    acquisition.num_samples
                ),
            )

            # ------------------------------------------------
            # Armazena task
            # ------------------------------------------------

            self._task = task

            self._reader = (
                AnalogMultiChannelReader(
                    task.in_stream
                )
            )

            self._configured_channels = (
                active_channels.copy()
            )

            self._acquisition_config = (
                acquisition
            )

            # ------------------------------------------------
            # Consulta taxa efetiva definida
            # pelo driver
            # ------------------------------------------------

            self._actual_sample_rate = (
                task.timing.samp_clk_rate
            )

        except Exception as exc:

            self.close_task()

            raise DAQError(
                "Falha durante a configuração "
                "da task NI-DAQmx.\n\n"
                f"Tipo do erro: {type(exc).__name__}\n"
                f"Detalhes: {exc}"
            ) from exc

    # ========================================================
    # CONFIGURAÇÃO DE CANAL
    # ========================================================

    def _add_channel(
        self,
        task: nidaqmx.Task,
        channel: ChannelConfig,
    ) -> None:
        """
        Adiciona um canal à task de acordo
        com o tipo de sensor.
        """

        if (
            channel.sensor_type
            == SensorType.MICROPHONE
        ):

            self._add_microphone_channel(
                task,
                channel,
            )

        elif (
            channel.sensor_type
            == SensorType.VOLTAGE
        ):

            self._add_voltage_channel(
                task,
                channel,
            )

        else:

            raise DAQError(
                f"O sensor "
                f"'{channel.sensor_type.value}' "
                "ainda não foi implementado."
            )

    # ========================================================
    # CANAL DE TENSÃO
    # ========================================================

    @staticmethod
    def _add_voltage_channel(
        task: nidaqmx.Task,
        channel: ChannelConfig,
    ) -> None:
        """
        Configura um canal de entrada
        como tensão.
        """

        task.ai_channels.add_ai_voltage_chan(

            physical_channel=(
                channel.physical_channel
            ),

            name_to_assign_to_channel=(
                channel.name
            ),

            terminal_config=(
                TerminalConfiguration.DEFAULT
            ),

            min_val=channel.min_voltage,

            max_val=channel.max_voltage,
        )

    # ========================================================
    # CANAL DE MICROFONE
    # ========================================================

    @staticmethod
    def _add_microphone_channel(
        task: nidaqmx.Task,
        channel: ChannelConfig,
    ) -> None:
        """
        Configura canal para microfone.

        NI-9234:

        - suporta IEPE
        - aquisição simultânea
        - condicionamento integrado
        - saída configurada diretamente em Pa
        """

        # ----------------------------------------------------
        # IEPE
        # ----------------------------------------------------

        if channel.iepe_enabled:

            excitation_source = (
                ExcitationSource.INTERNAL
            )

            excitation_current = (
                channel.iepe_current_a
            )

        else:

            excitation_source = (
                ExcitationSource.NONE
            )

            excitation_current = 0.0

        # ----------------------------------------------------
        # Canal NI-DAQmx de microfone
        # ----------------------------------------------------

        task.ai_channels.add_ai_microphone_chan(

            physical_channel=(
                channel.physical_channel
            ),

            name_to_assign_to_channel=(
                channel.name
            ),

            terminal_config=(
                TerminalConfiguration.DEFAULT
            ),

            units=SoundPressureUnits.PA,

            # ------------------------------------------------
            # Sensibilidade do microfone
            #
            # unidade esperada pelo nidaqmx:
            # mV/Pa
            # ------------------------------------------------

            mic_sensitivity=(
                channel.sensitivity_mv_pa
            ),

            # ------------------------------------------------
            # SPL máximo esperado
            #
            # futuramente pode ser definido
            # na GUI
            # ------------------------------------------------

            max_snd_press_level=(
                channel.max_spl
            ),

            # ------------------------------------------------
            # Excitação IEPE
            # ------------------------------------------------

            current_excit_source=(
                excitation_source
            ),

            current_excit_val=(
                excitation_current
            ),
        )

    # ========================================================
    # AQUISIÇÃO FINITA
    # ========================================================

    def acquire(self) -> AcquisitionData:
        """
        Executa uma aquisição finita.

        O NI-DAQmx trabalha internamente com:

            buffer.shape =
                (n_canais, n_amostras)

        O padrão utilizado pelo nosso programa será:

            data.shape =
                (n_amostras, n_canais)
        """

        # ----------------------------------------------------
        # Verificações
        # ----------------------------------------------------

        if self._task is None:

            raise DAQError(
                "A DAQ não foi configurada."
            )

        if self._reader is None:

            raise DAQError(
                "O leitor da DAQ não foi criado."
            )

        if self._acquisition_config is None:

            raise DAQError(
                "Configuração de aquisição ausente."
            )

        # ----------------------------------------------------
        # Configuração
        # ----------------------------------------------------

        acquisition = (
            self._acquisition_config
        )

        sample_rate = (
            self._actual_sample_rate
            or acquisition.sample_rate
        )

        num_channels = len(
            self._configured_channels
        )

        num_samples = (
            acquisition.num_samples
        )

        # ----------------------------------------------------
        # Buffer esperado pelo NI-DAQmx:
        #
        # linhas   = canais
        # colunas  = amostras
        # ----------------------------------------------------

        buffer = np.empty(
            (
                num_channels,
                num_samples,
            ),
            dtype=np.float64,
        )

        # ----------------------------------------------------
        # Timeout
        # ----------------------------------------------------

        expected_duration = (
            num_samples
            / sample_rate
        )

        timeout = max(
            10.0,
            expected_duration * 3.0,
        )

        # ----------------------------------------------------
        # Aquisição
        # ----------------------------------------------------

        try:

            self._task.start()

            self._reader.read_many_sample(

                data=buffer,

                number_of_samples_per_channel=(
                    num_samples
                ),

                timeout=timeout,
            )

            self._task.stop()

        except Exception as exc:

            try:

                self._task.stop()

            except Exception:
                pass

            raise DAQError(
                "Erro durante a aquisição "
                "NI-DAQmx."
            ) from exc

        # ----------------------------------------------------
        # Nosso padrão:
        #
        # linhas   = amostras
        # colunas  = canais
        # ----------------------------------------------------

        data = buffer.T.copy()

        # ----------------------------------------------------
        # Vetor de tempo
        # ----------------------------------------------------

        time = (
            np.arange(
                num_samples,
                dtype=np.float64,
            )
            / sample_rate
        )

        # ----------------------------------------------------
        # Nomes lógicos
        # ----------------------------------------------------

        channel_names = [
            (
                channel.name
                or channel.physical_channel
            )
            for channel
            in self._configured_channels
        ]

        # ----------------------------------------------------
        # Canais físicos
        # ----------------------------------------------------

        physical_channels = [
            channel.physical_channel
            for channel
            in self._configured_channels
        ]

        # ----------------------------------------------------
        # Resultado
        # ----------------------------------------------------

        return AcquisitionData(

            time=time,

            data=data,

            sample_rate=sample_rate,

            channel_names=channel_names,

            physical_channels=physical_channels,
        )

    # ========================================================
    # CONTEXT MANAGER
    # ========================================================

    def __enter__(self):
        """
        Permite utilizar:

            with NIDaqDevice() as daq:
                ...
        """

        self.connect()

        return self

    # ========================================================

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        """
        Fecha a task ao sair do bloco with.
        """

        self.disconnect()