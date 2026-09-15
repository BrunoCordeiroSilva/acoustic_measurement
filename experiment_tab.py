"""Apresentação independente do estado da aba Ensaio."""


def format_quality_values(quality) -> dict[str, str]:
    """Converte o relatório de qualidade para os textos exibidos na UI."""

    return {
        "status": quality.status.value,
        "mean": f"{quality.coherence_mean:.4f}",
        "minimum": f"{quality.coherence_min:.4f}",
        "valid_points": f"{quality.coherence_valid_percentage:.1f}%",
        "clipping": "SIM" if quality.clipping_detected else "NÃO",
    }


def clear_quality_labels(window) -> None:
    """Restaura o painel de qualidade ao estado sem medição."""

    window.quality_status_label.setText("-")
    window.coherence_mean_label.setText("-")
    window.coherence_min_label.setText("-")
    window.valid_points_label.setText("-")
    window.clipping_label.setText("-")
