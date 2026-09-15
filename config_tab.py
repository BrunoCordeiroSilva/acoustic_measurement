"""Cálculos independentes usados pela aba Configurar."""

import math

from PySide6.QtCore import QSignalBlocker


def calculate_valid_range_preview(
    temperature_c: float,
    diameter_m: float,
    spacing_12_m: float,
    spacing_34_m: float,
    sample_rate: float,
) -> tuple[float, float]:
    """Calcula os limites visuais da banda recomendada de TL."""

    if min(diameter_m, spacing_12_m, spacing_34_m, sample_rate) <= 0:
        raise ValueError("Geometria e taxa de amostragem devem ser positivas.")

    speed_of_sound = 331.3 + 0.606 * temperature_c
    spacing_minimum = max(
        0.05 * speed_of_sound / spacing_12_m,
        0.05 * speed_of_sound / spacing_34_m,
    )
    spacing_maximum = min(
        0.40 * speed_of_sound / spacing_12_m,
        0.40 * speed_of_sound / spacing_34_m,
    )
    plane_wave_cutoff = 1.84 * speed_of_sound / (math.pi * diameter_m)
    return spacing_minimum, min(
        spacing_maximum,
        plane_wave_cutoff,
        sample_rate / 2.0,
    )


def populate_channel_combos(reference_combo, mobile_combo, channels) -> None:
    """Reconstrói os seletores de canal para o dispositivo ativo."""

    with QSignalBlocker(reference_combo), QSignalBlocker(mobile_combo):
        reference_combo.clear()
        mobile_combo.clear()
        for channel in channels:
            reference_combo.addItem(channel)
            mobile_combo.addItem(channel)
        if channels:
            reference_combo.setCurrentIndex(0)
            mobile_combo.setCurrentIndex(min(1, len(channels) - 1))


def populate_device_combo(device_combo, devices) -> str:
    """Carrega dispositivos detectados e retorna o primeiro selecionado."""

    with QSignalBlocker(device_combo):
        device_combo.clear()
        for device in devices:
            device_combo.addItem(device)
        if devices:
            device_combo.setCurrentIndex(0)
    return device_combo.currentText()


def format_acquisition_metrics(sample_rate: float, samples: int) -> tuple[str, str, str]:
    """Formata duração, resolução e Nyquist exibidos na configuração."""

    if sample_rate <= 0 or samples <= 0:
        raise ValueError("Taxa de amostragem e número de amostras devem ser positivos.")
    return (
        f"{samples / sample_rate:.4f} s",
        f"{sample_rate / samples:.4f} Hz",
        f"{sample_rate / 2.0:.1f} Hz",
    )
