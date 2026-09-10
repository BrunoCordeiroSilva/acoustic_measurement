from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from scipy import signal

from config import (
    WindowType,
    FRFEstimator,
)


# ============================================================
# EXCEÇÕES
# ============================================================

class SignalProcessingError(RuntimeError):
    """
    Exceção específica da camada de processamento de sinais.
    """

    pass


# ============================================================
# RESULTADO DE FFT
# ============================================================

@dataclass
class FFTResult:
    """
    Resultado de uma FFT unilateral.

    frequency:
        Frequências [Hz].

    spectrum:
        Espectro complexo unilateral.

    magnitude:
        Amplitude unilateral.

    phase:
        Fase [rad].
    """

    frequency: np.ndarray

    spectrum: np.ndarray

    magnitude: np.ndarray

    phase: np.ndarray


# ============================================================
# RESULTADO DE PSD
# ============================================================

@dataclass
class PSDResult:
    """
    Resultado de uma densidade espectral de potência.

    frequency:
        Frequência [Hz].

    psd:
        PSD.
    """

    frequency: np.ndarray

    psd: np.ndarray


# ============================================================
# RESULTADO DA FRF
# ============================================================

@dataclass
class FRFResult:
    """
    Resultado de uma medição de FRF.

    frequency:
        Frequências [Hz].

    H:
        FRF complexa.

    coherence:
        Coerência entre 0 e 1.

    Gxx:
        Autoespectro do canal de referência.

    Gyy:
        Autoespectro do canal de resposta.

    Gxy:
        Espectro cruzado entre referência e resposta.

    valid_mask:
        Máscara booleana indicando pontos que atendem
        ao critério de coerência.
    """

    frequency: np.ndarray

    H: np.ndarray

    coherence: np.ndarray

    Gxx: np.ndarray

    Gyy: np.ndarray

    Gxy: np.ndarray

    valid_mask: np.ndarray

    # --------------------------------------------------------

    @property
    def magnitude(self) -> np.ndarray:
        """
        Módulo da FRF.
        """

        return np.abs(self.H)

    # --------------------------------------------------------

    @property
    def phase_rad(self) -> np.ndarray:
        """
        Fase da FRF [rad].
        """

        return np.angle(self.H)

    # --------------------------------------------------------

    @property
    def phase_deg(self) -> np.ndarray:
        """
        Fase da FRF [graus].
        """

        return np.rad2deg(
            np.angle(self.H)
        )


# ============================================================
# PROCESSAMENTO GERAL
# ============================================================

class SignalProcessor:
    """
    Funções gerais para processamento dos sinais temporais.
    """

    # ========================================================
    # VALIDAÇÃO
    # ========================================================

    @staticmethod
    def _validate_signal(
        x: np.ndarray,
    ) -> np.ndarray:
        """
        Converte o sinal para ndarray float64
        e realiza validações básicas.
        """

        x = np.asarray(
            x,
            dtype=np.float64,
        )

        if x.ndim != 1:

            raise SignalProcessingError(
                "O sinal deve ser unidimensional."
            )

        if x.size == 0:

            raise SignalProcessingError(
                "O sinal está vazio."
            )

        if not np.all(
            np.isfinite(x)
        ):

            raise SignalProcessingError(
                "O sinal contém NaN ou infinito."
            )

        return x

    # ========================================================
    # REMOÇÃO DE DC
    # ========================================================

    @staticmethod
    def remove_dc(
        x: np.ndarray,
    ) -> np.ndarray:
        """
        Remove o valor médio do sinal.
        """

        x = SignalProcessor._validate_signal(
            x
        )

        return x - np.mean(x)

    # ========================================================
    # RMS
    # ========================================================

    @staticmethod
    def rms(
        x: np.ndarray,
        remove_dc: bool = True,
    ) -> float:
        """
        Calcula o valor RMS.

        Para sinais acústicos normalmente usamos
        remove_dc=True.
        """

        x = SignalProcessor._validate_signal(
            x
        )

        if remove_dc:

            x = x - np.mean(x)

        return float(
            np.sqrt(
                np.mean(
                    x ** 2
                )
            )
        )

    # ========================================================
    # PICO
    # ========================================================

    @staticmethod
    def peak(
        x: np.ndarray,
        remove_dc: bool = True,
    ) -> float:
        """
        Calcula o maior valor absoluto do sinal.
        """

        x = SignalProcessor._validate_signal(
            x
        )

        if remove_dc:

            x = x - np.mean(x)

        return float(
            np.max(
                np.abs(x)
            )
        )

    # ========================================================
    # SPL
    # ========================================================

    @staticmethod
    def spl(
        pressure: np.ndarray,
        reference_pressure: float = 20e-6,
        remove_dc: bool = True,
    ) -> float:
        """
        Calcula o nível de pressão sonora global.

        SPL = 20 log10(p_rms / p_ref)

        pressure:
            pressão acústica [Pa].

        reference_pressure:
            pressão de referência [Pa].
            Para o ar: 20 µPa.
        """

        if reference_pressure <= 0:

            raise SignalProcessingError(
                "A pressão de referência deve "
                "ser positiva."
            )

        pressure_rms = SignalProcessor.rms(
            pressure,
            remove_dc=remove_dc,
        )

        if pressure_rms <= 0:

            return -np.inf

        return float(
            20.0
            * np.log10(
                pressure_rms
                / reference_pressure
            )
        )

    # ========================================================
    # JANELA
    # ========================================================

    @staticmethod
    def get_window(
        window_type: WindowType,
        num_samples: int,
    ) -> np.ndarray:
        """
        Retorna a janela desejada.
        """

        if num_samples <= 0:

            raise SignalProcessingError(
                "O número de amostras deve "
                "ser positivo."
            )

        if window_type == WindowType.HANN:

            return signal.windows.hann(
                num_samples,
                sym=False,
            )

        if (
            window_type
            == WindowType.RECTANGULAR
        ):

            return np.ones(
                num_samples,
                dtype=np.float64,
            )

        raise SignalProcessingError(
            f"Janela não implementada: "
            f"{window_type}"
        )

    # ========================================================
    # FFT
    # ========================================================

    @staticmethod
    def fft(
        x: np.ndarray,
        sample_rate: float,
        window_type: WindowType = WindowType.HANN,
        remove_dc: bool = True,
    ) -> FFTResult:
        """
        Calcula a FFT unilateral do sinal.

        A amplitude é corrigida pelo ganho coerente
        da janela para permitir interpretação física
        da magnitude de componentes senoidais.
        """

        x = SignalProcessor._validate_signal(
            x
        )

        if sample_rate <= 0:

            raise SignalProcessingError(
                "A frequência de amostragem deve "
                "ser positiva."
            )

        if remove_dc:

            x = x - np.mean(x)

        n = x.size

        window = SignalProcessor.get_window(
            window_type,
            n,
        )

        windowed = x * window

        # ----------------------------------------------------
        # FFT unilateral
        # ----------------------------------------------------

        spectrum_raw = np.fft.rfft(
            windowed
        )

        frequency = np.fft.rfftfreq(
            n,
            d=1.0 / sample_rate,
        )

        # ----------------------------------------------------
        # Correção de amplitude da janela
        # ----------------------------------------------------

        coherent_gain = np.sum(
            window
        )

        if coherent_gain == 0:

            raise SignalProcessingError(
                "Ganho coerente da janela é zero."
            )

        spectrum = (
            spectrum_raw
            / coherent_gain
        )

        magnitude = np.abs(
            spectrum
        )

        # ----------------------------------------------------
        # Conversão para espectro unilateral.
        #
        # DC não é multiplicado por 2.
        # Nyquist também não deve ser multiplicado
        # por 2 quando N é par.
        # ----------------------------------------------------

        if n % 2 == 0:

            if magnitude.size > 2:

                magnitude[
                    1:-1
                ] *= 2.0

        else:

            if magnitude.size > 1:

                magnitude[
                    1:
                ] *= 2.0

        phase = np.angle(
            spectrum
        )

        return FFTResult(
            frequency=frequency,
            spectrum=spectrum,
            magnitude=magnitude,
            phase=phase,
        )

    # ========================================================
    # PSD - PERIODOGRAMA
    # ========================================================

    @staticmethod
    def psd(
        x: np.ndarray,
        sample_rate: float,
        window_type: WindowType = WindowType.HANN,
        remove_dc: bool = True,
    ) -> PSDResult:
        """
        Calcula PSD utilizando periodograma.
        """

        x = SignalProcessor._validate_signal(
            x
        )

        if sample_rate <= 0:

            raise SignalProcessingError(
                "A frequência de amostragem deve "
                "ser positiva."
            )

        if remove_dc:

            detrend = "constant"

        else:

            detrend = False

        window = SignalProcessor.get_window(
            window_type,
            x.size,
        )

        frequency, psd = signal.periodogram(
            x,
            fs=sample_rate,
            window=window,
            detrend=detrend,
            scaling="density",
            return_onesided=True,
        )

        return PSDResult(
            frequency=frequency,
            psd=psd,
        )

    # ========================================================
    # PSD - WELCH
    # ========================================================

    @staticmethod
    def welch(
        x: np.ndarray,
        sample_rate: float,
        window_type: WindowType = WindowType.HANN,
        nperseg: int | None = None,
        overlap: float = 0.50,
        remove_dc: bool = True,
    ) -> PSDResult:
        """
        Calcula PSD utilizando o método de Welch.
        """

        x = SignalProcessor._validate_signal(
            x
        )

        if sample_rate <= 0:

            raise SignalProcessingError(
                "A frequência de amostragem deve "
                "ser positiva."
            )

        if not 0 <= overlap < 1:

            raise SignalProcessingError(
                "O overlap deve estar entre "
                "0 e 1."
            )

        if nperseg is None:

            nperseg = x.size

        nperseg = min(
            nperseg,
            x.size,
        )

        if nperseg <= 0:

            raise SignalProcessingError(
                "nperseg deve ser positivo."
            )

        noverlap = int(
            nperseg * overlap
        )

        window = SignalProcessor.get_window(
            window_type,
            nperseg,
        )

        if remove_dc:

            detrend = "constant"

        else:

            detrend = False

        frequency, psd = signal.welch(
            x,
            fs=sample_rate,
            window=window,
            nperseg=nperseg,
            noverlap=noverlap,
            detrend=detrend,
            scaling="density",
            return_onesided=True,
        )

        return PSDResult(
            frequency=frequency,
            psd=psd,
        )


# ============================================================
# PROCESSAMENTO DE FRF
# ============================================================

class FRFProcessor:
    """
    Processamento de função resposta em frequência
    entre dois canais.

    Convenção:

        x = canal de referência
        y = canal de resposta

    O estimador H1 é:

        H1 = Gxy / Gxx

    onde:

        Gxx = X* X
        Gyy = Y* Y
        Gxy = X* Y

    Portanto:

        H1 ~= Y / X
    """

    # ========================================================
    # VALIDAÇÃO
    # ========================================================

    @staticmethod
    def _validate_pair(
        x: np.ndarray,
        y: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:

        x = SignalProcessor._validate_signal(
            x
        )

        y = SignalProcessor._validate_signal(
            y
        )

        if x.size != y.size:

            raise SignalProcessingError(
                "Os dois sinais devem possuir "
                "o mesmo número de amostras."
            )

        return x, y

    # ========================================================
    # PARÂMETROS DE WELCH
    # ========================================================

    @staticmethod
    def _prepare_welch_parameters(
        num_samples: int,
        window_type: WindowType,
        nperseg: int | None,
        overlap: float,
    ) -> tuple[
        int,
        int,
        np.ndarray,
    ]:

        if not 0 <= overlap < 1:

            raise SignalProcessingError(
                "O overlap deve estar entre "
                "0 e 1."
            )

        if nperseg is None:

            nperseg = num_samples

        nperseg = min(
            nperseg,
            num_samples,
        )

        if nperseg <= 0:

            raise SignalProcessingError(
                "nperseg deve ser positivo."
            )

        noverlap = int(
            nperseg * overlap
        )

        window = SignalProcessor.get_window(
            window_type,
            nperseg,
        )

        return (
            nperseg,
            noverlap,
            window,
        )

    # ========================================================
    # AUTOESPECTRO
    # ========================================================

    @staticmethod
    def auto_spectrum(
        x: np.ndarray,
        sample_rate: float,
        window_type: WindowType = WindowType.HANN,
        nperseg: int | None = None,
        overlap: float = 0.50,
    ) -> tuple[
        np.ndarray,
        np.ndarray,
    ]:
        """
        Calcula o autoespectro Gxx através
        do método de Welch.
        """

        x = SignalProcessor._validate_signal(
            x
        )

        (
            nperseg,
            noverlap,
            window,
        ) = FRFProcessor._prepare_welch_parameters(
            num_samples=x.size,
            window_type=window_type,
            nperseg=nperseg,
            overlap=overlap,
        )

        frequency, Gxx = signal.welch(
            x,
            fs=sample_rate,
            window=window,
            nperseg=nperseg,
            noverlap=noverlap,
            detrend="constant",
            scaling="density",
            return_onesided=True,
        )

        return (
            frequency,
            Gxx,
        )

    # ========================================================
    # ESPECTRO CRUZADO
    # ========================================================

    @staticmethod
    def cross_spectrum(
        x: np.ndarray,
        y: np.ndarray,
        sample_rate: float,
        window_type: WindowType = WindowType.HANN,
        nperseg: int | None = None,
        overlap: float = 0.50,
    ) -> tuple[
        np.ndarray,
        np.ndarray,
    ]:
        """
        Calcula o espectro cruzado Gxy.

        Pela convenção do scipy.signal.csd:

            Gxy = conj(X) * Y
        """

        x, y = (
            FRFProcessor._validate_pair(
                x,
                y,
            )
        )

        (
            nperseg,
            noverlap,
            window,
        ) = FRFProcessor._prepare_welch_parameters(
            num_samples=x.size,
            window_type=window_type,
            nperseg=nperseg,
            overlap=overlap,
        )

        frequency, Gxy = signal.csd(
            x,
            y,
            fs=sample_rate,
            window=window,
            nperseg=nperseg,
            noverlap=noverlap,
            detrend="constant",
            scaling="density",
            return_onesided=True,
        )

        return (
            frequency,
            Gxy,
        )

    # ========================================================
    # FRF COMPLETA
    # ========================================================

    @staticmethod
    def calculate_frf(
        x: np.ndarray,
        y: np.ndarray,
        sample_rate: float,
        window_type: WindowType = WindowType.HANN,
        nperseg: int | None = None,
        overlap: float = 0.50,
        estimator: FRFEstimator = FRFEstimator.H1,
        coherence_threshold: float = 0.90,
    ) -> FRFResult:
        """
        Calcula:

            Gxx
            Gyy
            Gxy
            FRF
            coerência

        Convenção:

            x = referência
            y = resposta

        Para nosso ensaio:

            x = microfone fixo
                posição 3

            y = microfone móvel
                posição 1, 2 ou 4

        Assim:

            H31 = P1 / P3
            H32 = P2 / P3
            H34 = P4 / P3
        """

        x, y = (
            FRFProcessor._validate_pair(
                x,
                y,
            )
        )

        if sample_rate <= 0:

            raise SignalProcessingError(
                "A frequência de amostragem deve "
                "ser positiva."
            )

        if not (
            0
            <= coherence_threshold
            <= 1
        ):

            raise SignalProcessingError(
                "O limite de coerência deve "
                "estar entre 0 e 1."
            )

        (
            nperseg,
            noverlap,
            window,
        ) = FRFProcessor._prepare_welch_parameters(
            num_samples=x.size,
            window_type=window_type,
            nperseg=nperseg,
            overlap=overlap,
        )

        # ----------------------------------------------------
        # AUTOESPECTRO DO CANAL DE REFERÊNCIA
        # ----------------------------------------------------

        frequency, Gxx = signal.welch(
            x,
            fs=sample_rate,
            window=window,
            nperseg=nperseg,
            noverlap=noverlap,
            detrend="constant",
            scaling="density",
            return_onesided=True,
        )

        # ----------------------------------------------------
        # AUTOESPECTRO DO CANAL DE RESPOSTA
        # ----------------------------------------------------

        frequency_y, Gyy = signal.welch(
            y,
            fs=sample_rate,
            window=window,
            nperseg=nperseg,
            noverlap=noverlap,
            detrend="constant",
            scaling="density",
            return_onesided=True,
        )

        # ----------------------------------------------------
        # ESPECTRO CRUZADO
        #
        # scipy:
        #
        #     Gxy = conj(X) * Y
        # ----------------------------------------------------

        frequency_xy, Gxy = signal.csd(
            x,
            y,
            fs=sample_rate,
            window=window,
            nperseg=nperseg,
            noverlap=noverlap,
            detrend="constant",
            scaling="density",
            return_onesided=True,
        )

        # ----------------------------------------------------
        # Segurança
        # ----------------------------------------------------

        if not (
            np.array_equal(
                frequency,
                frequency_y,
            )
            and np.array_equal(
                frequency,
                frequency_xy,
            )
        ):

            raise SignalProcessingError(
                "Os vetores de frequência dos "
                "espectros não coincidem."
            )

        # ----------------------------------------------------
        # FRF
        # ----------------------------------------------------

        H = np.full(
            Gxy.shape,
            np.nan + 1j * np.nan,
            dtype=np.complex128,
        )

        if estimator == FRFEstimator.H1:

            # H1 = Gxy / Gxx

            denominator = Gxx

            np.divide(
                Gxy,
                denominator,
                out=H,
                where=denominator > 0,
            )

        elif estimator == FRFEstimator.H2:

            # H2 = Gyy / Gyx
            #
            # Gyx = conj(Gxy)

            Gyx = np.conj(
                Gxy
            )

            np.divide(
                Gyy,
                Gyx,
                out=H,
                where=np.abs(Gyx) > 0,
            )

        else:

            raise SignalProcessingError(
                f"Estimador FRF não implementado: "
                f"{estimator}"
            )

        # ----------------------------------------------------
        # COERÊNCIA
        #
        # gamma² =
        #
        # |Gxy|²
        # ----------
        # Gxx Gyy
        # ----------------------------------------------------

        coherence = np.zeros(
            Gxx.shape,
            dtype=np.float64,
        )

        coherence_denominator = (
            Gxx * Gyy
        )

        np.divide(
            np.abs(Gxy) ** 2,
            coherence_denominator,
            out=coherence,
            where=(
                coherence_denominator > 0
            ),
        )

        # Pequenos erros numéricos podem gerar
        # valores como 1.0000000002.

        coherence = np.clip(
            coherence,
            0.0,
            1.0,
        )

        # ----------------------------------------------------
        # VALIDADE
        # ----------------------------------------------------

        valid_mask = (
            np.isfinite(H.real)
            & np.isfinite(H.imag)
            & np.isfinite(coherence)
            & (
                coherence
                >= coherence_threshold
            )
        )

        return FRFResult(
            frequency=frequency,
            H=H,
            coherence=coherence,
            Gxx=Gxx,
            Gyy=Gyy,
            Gxy=Gxy,
            valid_mask=valid_mask,
        )