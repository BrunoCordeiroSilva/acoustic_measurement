"""Curvas P1–P4 compartilhadas pelos gráficos principais e pop-ups."""

import numpy as np
import pyqtgraph as pg

from ui_constants import REFERENCE_COLOR, MOBILE_COLOR, COHERENCE_COLOR


MICROPHONE_COLORS = {
    1: MOBILE_COLOR, 2: COHERENCE_COLOR, 3: REFERENCE_COLOR, 4: "#E040FB",
}


def create_microphone_curves(plot, coherence=False):
    legend = plot.addLegend()
    legend.anchor(itemPos=(0, 1), parentPos=(0, 1), offset=(10, -10))
    positions = (1, 2, 4) if coherence else (1, 2, 3, 4)
    return {
        position: plot.plot(
            [], [], pen=pg.mkPen(MICROPHONE_COLORS[position], width=2),
            name=(
                f"H3{position} (P{position}/P3)" if coherence
                else f"P{position}" + (" - referência" if position == 3 else "")
            ),
        )
        for position in positions
    }


def set_microphone_curves(curves, frequency, values):
    for position, curve in curves.items():
        curve.setData(frequency, values[position])


def spectra_from_frfs(frfs):
    reference = next(iter(frfs.values()))
    spectra = {3: np.sqrt(np.maximum(reference.Gxx, 0.0))}
    spectra.update({
        position: np.sqrt(np.maximum(frf.Gyy, 0.0))
        for position, frf in frfs.items()
    })
    return reference.frequency, spectra


def render_measurement_frfs(window, frfs):
    """Redesenha todos os pares após uma média e ajusta o zoom."""
    frequency, spectra = spectra_from_frfs(frfs)
    coherences = {position: frf.coherence for position, frf in frfs.items()}
    set_microphone_curves(window.spectrum_curves, frequency, spectra)
    set_microphone_curves(window.coherence_curves, frequency, coherences)
    window.fit_spectrum_plot()
    window.fit_coherence_plot()
    window.coherence_frozen_to_measurement = True
    window.displayed_measurement_frfs = frfs
    for popup, values in (
        (window.spectrum_popup, spectra), (window.coherence_popup, coherences),
    ):
        if popup is not None and popup.isVisible():
            set_microphone_curves(popup.curves, frequency, values)
            popup.plot.getViewBox().autoRange()
