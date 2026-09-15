"""Componentes visuais independentes da aba de Resultados.

A janela principal mantém o estado do ensaio; este módulo concentra a UI que
não precisa conhecer DAQ, monitoramento ou o ciclo de medição.
"""

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QScrollArea,
    QWidget,
)

from PySide6.QtCore import Qt

import pyqtgraph as pg
import numpy as np
import pandas as pd

from signal_processing import FRFResult


def build_results_tab(window) -> None:
    """Constrói a aba Resultados preservando os atributos da janela."""
    layout = QVBoxLayout(window.results_tab)
    window.tl_curve_entries = []; window.current_tl_curve = None; window.tl_active_valid_range = None
    window.tl_plot = pg.PlotWidget(); window.tl_plot.setLabel("left", "TL", units="dB")
    window.tl_plot.setLabel("bottom", "Frequência", units="Hz"); window.tl_plot.showGrid(x=True, y=True)
    window.tl_legend = window.tl_plot.addLegend(); window.tl_legend.anchor(itemPos=(1,0), parentPos=(1,0), offset=(-10,10))
    layout.addWidget(window.tl_plot, stretch=1)
    group = QGroupBox("Resultado"); form = QFormLayout(group)
    window.result_range_label = QLabel("-"); window.result_points_label = QLabel("-")
    form.addRow("Faixa válida:", window.result_range_label); form.addRow("Pontos armazenados:", window.result_points_label); group.setFixedWidth(260)
    lower = QGridLayout(); lower.setHorizontalSpacing(10); lower.setVerticalSpacing(5)
    window.process_button = QPushButton("Processar TL"); window.save_button = QPushButton("Salvar Ensaio CSV...")
    window.fit_tl_button = QPushButton("Zoom to fit"); window.tl_plot_settings_button = QPushButton("Configurações Gráfico")
    window.new_model_button = QPushButton("Novo Ensaio/Modelo"); window.import_tl_button = QPushButton("Add TL CSV")
    window.save_tl_png_button = QPushButton("Salvar Gráfico PNG..."); window.save_tl_csv_button = QPushButton("Salvar Gráfico CSV...")
    buttons = (window.process_button, window.save_button, window.import_tl_button, window.save_tl_png_button, window.save_tl_csv_button, window.fit_tl_button, window.tl_plot_settings_button, window.new_model_button)
    for button in buttons: button.setFixedWidth(button.sizeHint().width() + 8)
    lower.addWidget(group,0,0,3,1); lower.addWidget(window.process_button,0,1,Qt.AlignLeft|Qt.AlignTop); lower.addWidget(window.save_button,1,1,Qt.AlignLeft|Qt.AlignTop)
    lower.addWidget(window.import_tl_button,0,2,Qt.AlignLeft|Qt.AlignTop); lower.addWidget(window.save_tl_png_button,1,2,Qt.AlignLeft|Qt.AlignTop); lower.addWidget(window.save_tl_csv_button,2,2,Qt.AlignLeft|Qt.AlignTop)
    window.tl_curve_visibility_group = QGroupBox("Curvas visíveis"); scroll = QScrollArea(); scroll.setWidgetResizable(True); widget = QWidget(); window.tl_curve_visibility_layout = QVBoxLayout(widget); window.tl_curve_visibility_layout.setContentsMargins(6,4,6,4); window.tl_curve_visibility_layout.addStretch(); scroll.setWidget(widget); QVBoxLayout(window.tl_curve_visibility_group).addWidget(scroll); window.tl_curve_visibility_group.setFixedWidth(240)
    lower.addWidget(window.tl_curve_visibility_group,0,3,3,1); lower.addWidget(window.tl_plot_settings_button,0,4,Qt.AlignRight|Qt.AlignBottom); lower.addWidget(window.fit_tl_button,0,5,Qt.AlignRight|Qt.AlignBottom); lower.setColumnStretch(4,1); layout.addLayout(lower)
    model = QHBoxLayout(); model.addStretch(); model.addWidget(window.new_model_button); layout.addLayout(model)
    window.process_button.clicked.connect(window.process_tl); window.save_button.clicked.connect(window.save_experiment); window.fit_tl_button.clicked.connect(window.fit_tl_plot); window.tl_plot_settings_button.clicked.connect(window.open_tl_plot_settings); window.new_model_button.clicked.connect(window.start_new_model_experiment); window.import_tl_button.clicked.connect(window.import_tl_csv_files); window.save_tl_png_button.clicked.connect(window.save_tl_plot_png); window.save_tl_csv_button.clicked.connect(window.save_tl_plot_csv)


class TLPlotController:
    """Operações de curvas da TL, isoladas do ciclo de aquisição."""

    COLORS = (
        "#2979FF", "#D50000", "#00A152", "#AA00FF",
        "#FF6D00", "#00838F", "#6D4C41",
    )

    @classmethod
    def fit(cls, window) -> None:
        window.tl_plot.getViewBox().autoRange()

    @classmethod
    def add_curve(
        cls,
        window,
        frequency,
        transmission_loss,
        name: str,
        valid_frequency_range=None,
    ) -> dict:
        color = cls.COLORS[len(window.tl_curve_entries) % len(cls.COLORS)]
        curve = window.tl_plot.plot(
            frequency, transmission_loss, name=name,
            pen=pg.mkPen(color, width=2),
        )
        checkbox = QCheckBox(name)
        checkbox.setChecked(True)
        checkbox.setStyleSheet(f"color: {color}; font-weight: bold;")
        checkbox.toggled.connect(curve.setVisible)
        entry = {
            "curve": curve,
            "checkbox": checkbox,
            "name": name,
            "valid_frequency_range": valid_frequency_range,
        }
        window.tl_curve_entries.append(entry)
        window.tl_curve_visibility_layout.insertWidget(
            window.tl_curve_visibility_layout.count() - 1,
            checkbox,
        )
        return entry

    @classmethod
    def clear_curves(cls, window) -> None:
        for entry in window.tl_curve_entries:
            window.tl_plot.removeItem(entry["curve"])
            window.tl_curve_visibility_layout.removeWidget(entry["checkbox"])
            entry["checkbox"].deleteLater()
        window.tl_curve_entries.clear()
        window.current_tl_curve = None


def read_tl_csv(filepath):
    """Lê uma curva TL CSV e recupera sua faixa válida, quando disponível."""

    dataframe = pd.read_csv(filepath, sep=None, engine="python")
    required_columns = {"frequency_Hz", "TL_dB"}
    if not required_columns.issubset(dataframe.columns):
        raise ValueError(
            "O arquivo deve possuir as colunas frequency_Hz e TL_dB."
        )

    frequency = pd.to_numeric(
        dataframe["frequency_Hz"], errors="coerce"
    ).to_numpy()
    transmission_loss = pd.to_numeric(
        dataframe["TL_dB"], errors="coerce"
    ).to_numpy()
    finite = np.isfinite(frequency) & np.isfinite(transmission_loss)
    if not np.any(finite):
        raise ValueError("O arquivo não possui valores finitos de frequência e TL.")

    valid_frequency_range = None
    if "valid" in dataframe.columns:
        valid_column = (
            dataframe["valid"].astype(str).str.strip().str.lower()
            .isin(("true", "1", "sim", "yes")).to_numpy()
        )
        valid_band = finite & valid_column
        if np.any(valid_band):
            valid_frequency_range = (
                float(np.min(frequency[valid_band])),
                float(np.max(frequency[valid_band])),
            )

    return (
        frequency[finite],
        transmission_loss[finite],
        valid_frequency_range,
    )


def read_frf_csv(filepath) -> FRFResult:
    """Lê uma FRF exportada pelo aplicativo para o cálculo de TL."""

    data = pd.read_csv(filepath, sep=None, engine="python")
    required = {"frequency_Hz", "H_real", "H_imag"}
    if not required.issubset(data.columns):
        raise ValueError("requer frequency_Hz, H_real e H_imag")

    frequency = pd.to_numeric(
        data["frequency_Hz"], errors="coerce"
    ).to_numpy()
    H = (
        pd.to_numeric(data["H_real"], errors="coerce").to_numpy()
        + 1j * pd.to_numeric(data["H_imag"], errors="coerce").to_numpy()
    )
    if not np.all(np.isfinite(frequency) & np.isfinite(H)):
        raise ValueError("possui frequências ou FRFs inválidas")

    valid = (
        data["valid"].astype(str).str.strip().str.lower()
        .isin(("true", "1", "sim", "yes")).to_numpy()
        if "valid" in data
        else np.isfinite(H)
    )
    zeros = np.zeros(frequency.size)
    return FRFResult(
        frequency, H, np.ones(frequency.size), zeros, zeros,
        np.zeros(frequency.size, dtype=complex), valid,
    )


def build_tl_curve_dataframe(entries) -> pd.DataFrame:
    """Converte as curvas plotadas em colunas CSV com nomes únicos."""

    columns = {}
    used_names = set()
    for index, entry in enumerate(entries, start=1):
        frequency, transmission_loss = entry["curve"].getData()
        curve_name = entry["name"]
        safe_name = "".join(
            character if character.isalnum() or character in "_-" else "_"
            for character in curve_name
        ).strip("_") or f"curva_{index}"
        original_name = safe_name
        suffix = 2
        while safe_name in used_names:
            safe_name = f"{original_name}_{suffix}"
            suffix += 1
        used_names.add(safe_name)
        columns[f"frequency_Hz__{safe_name}"] = pd.Series(frequency)
        columns[f"TL_dB__{safe_name}"] = pd.Series(transmission_loss)
    return pd.DataFrame(columns)


def prepare_tl_plot_data(result):
    """Prepara a curva integral e os metadados visuais de um resultado TL."""

    finite = np.isfinite(result.transmission_loss)
    valid_range = result.valid_frequency_range
    return (
        result.frequency[finite],
        result.transmission_loss[finite],
        (valid_range.minimum, valid_range.maximum),
        int(result.frequency.size),
    )


def save_plot_png(plot, filepath: str) -> None:
    """Grava o conteúdo visual de um PlotWidget como PNG."""

    if not plot.grab().save(filepath, "PNG"):
        raise OSError("Não foi possível gravar a imagem PNG.")


class ResultsTabView:
    """Fábrica de diálogos usados pelo painel de resultados."""

    @staticmethod
    def open_plot_settings(window) -> None:
        """Exibe controles de visualização, sem possuir dados do ensaio."""

        dialog = QDialog(window)
        dialog.setWindowTitle("Configurações Gráfico")
        dialog.setMinimumWidth(430)
        layout = QVBoxLayout(dialog)

        clear_button = QPushButton("Limpar Gráfico")
        clear_button.clicked.connect(window._confirm_clear_tl_curves)
        layout.addWidget(clear_button)

        form = QFormLayout()
        inputs = {}
        for key, label in (
            ("x_min", "X mínimo (Hz):"),
            ("x_max", "X máximo (Hz):"),
            ("y_min", "Y mínimo (dB):"),
            ("y_max", "Y máximo (dB):"),
        ):
            spin = QDoubleSpinBox()
            spin.setRange(-1e12, 1e12)
            spin.setDecimals(3)
            inputs[key] = spin
            form.addRow(label, spin)
        layout.addLayout(form)

        apply_button = QPushButton("Aplicar limites")
        apply_button.clicked.connect(
            lambda: window._set_tl_plot_range(inputs)
        )
        layout.addWidget(apply_button)

        valid_button = QPushButton("Ajustar na faixa válida")
        valid_button.clicked.connect(
            lambda: window._fit_tl_valid_range(inputs)
        )
        layout.addWidget(valid_button)

        read_frfs_button = QPushButton("Ler FRFs")
        read_frfs_button.clicked.connect(window.load_tl_from_frf_files)
        layout.addWidget(read_frfs_button)

        close_button = QPushButton("Fechar")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)
        dialog.exec()


class FRFFileSelectionDialog(QDialog):
    """Associa explicitamente cada arquivo à FRF do método de duas cargas."""

    def __init__(self, parent, steps):
        super().__init__(parent)
        self.setWindowTitle("Ler FRFs para calcular TL")
        self.setMinimumWidth(700)
        self._fields = {}

        layout = QVBoxLayout(self)
        instruction = QLabel(
            "Associe cada arquivo CSV à FRF indicada na mesma linha. "
            "Os seis arquivos devem usar o mesmo vetor de frequência."
        )
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        form = QFormLayout()
        for step in steps:
            field = QLineEdit()
            field.setReadOnly(True)
            choose = QPushButton("Selecionar...")
            choose.clicked.connect(
                lambda _, target=field, label=step.value:
                    self._choose_file(target, label)
            )
            row = QHBoxLayout()
            row.addWidget(field, stretch=1)
            row.addWidget(choose)
            form.addRow(f"{step.value}:", row)
            self._fields[step] = field
        layout.addLayout(form)

        self.name_input = QLineEdit("TL importada")
        layout.addWidget(QLabel("Nome da curva:"))
        layout.addWidget(self.name_input)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        accept = QPushButton("Ler FRFs e calcular TL")
        cancel.clicked.connect(self.reject)
        accept.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(accept)
        layout.addLayout(buttons)

    def selection(self):
        return (
            self.name_input.text().strip(),
            {step: field.text().strip() for step, field in self._fields.items()},
        )

    def _choose_file(self, field, step_name: str) -> None:
        filepath, _ = QFileDialog.getOpenFileName(
            self, f"Selecione a FRF {step_name}", "",
            "Arquivos CSV (*.csv);;Todos os arquivos (*)",
        )
        if filepath:
            field.setText(filepath)
