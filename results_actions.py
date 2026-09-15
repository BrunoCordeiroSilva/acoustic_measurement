"""Fluxo operacional da aba Resultados."""

import numpy as np
import pandas as pd
from pathlib import Path
from PySide6.QtWidgets import QFileDialog, QMessageBox, QDialog, QLineEdit
from experiments.transmission_loss import TransmissionLossExperiment, TransmissionLossError, TLExperimentState, TLMeasurementStep, StoredTLMeasurement, MeasurementAcceptance
from acquisition_controller import FRFMeasurementResult
from experiment_tab import clear_quality_labels
from results_tab import *
from exporter import DataExporter, ExportError

class ResultsActionsMixin:
    def process_tl(self):

        try:

            self.tl_result = (
                self.experiment.process()
            )

            result = self.tl_result

            (
                frequency_plot,
                tl_plot,
                valid_range_values,
                total_points,
            ) = prepare_tl_plot_data(result)

            # =================================================
            # PLOT
            # =================================================

            if self.current_tl_curve is None:

                self.current_tl_curve = (
                    self._add_tl_curve(
                        frequency=frequency_plot,
                        transmission_loss=tl_plot,
                        name="TL do ensaio atual",
                        valid_frequency_range=(
                            valid_range_values
                        ),
                    )
                )

            else:

                self.current_tl_curve[
                    "curve"
                ].setData(
                    frequency_plot,
                    tl_plot,
                )

                self.current_tl_curve["valid_frequency_range"] = (
                    valid_range_values
                )

                self.current_tl_curve[
                    "checkbox"
                ].setChecked(
                    True
                )

            valid_range = (
                result.valid_frequency_range
            )

            self.tl_active_valid_range = (
                valid_range_values
            )

            self.fit_tl_plot()

            self.result_range_label.setText(
                f"{valid_range.minimum:.1f} - "
                f"{valid_range.maximum:.1f} Hz"
            )

            self.result_points_label.setText(
                str(
                    total_points
                )
            )

            self.tabs.setCurrentWidget(
                self.results_tab
            )

            self._update_controls()

        except TransmissionLossError as error:

            QMessageBox.critical(
                self,
                "Erro de processamento",
                str(error),
            )

    # ========================================================
    # ZOOM DA TL
    # ========================================================

    def fit_tl_plot(self):
        TLPlotController.fit(self)

    # ========================================================

    def open_tl_plot_settings(self):
        ResultsTabView.open_plot_settings(self)

    # ========================================================

    def _confirm_clear_tl_curves(self):
        if not self.tl_curve_entries:
            return
        answer = QMessageBox.question(self, "Limpar gráfico",
            "Todas as curvas serão removidas da interface. Deseja continuar?",
            QMessageBox.Yes | QMessageBox.No)
        if answer == QMessageBox.Yes:
            self._clear_tl_curves()
            self.tl_active_valid_range = None
            self._update_controls()

    def _set_tl_plot_range(self, inputs):
        x_min, x_max = inputs["x_min"].value(), inputs["x_max"].value()
        y_min, y_max = inputs["y_min"].value(), inputs["y_max"].value()
        if x_max <= x_min or y_max <= y_min:
            QMessageBox.warning(self, "Limites do gráfico",
                "Os limites máximos devem ser maiores que os mínimos.")
            return
        self.tl_plot.getViewBox().setRange(
            xRange=(x_min, x_max), yRange=(y_min, y_max), padding=0)

    def _fit_tl_valid_range(self, inputs):
        valid_ranges = [
            entry["valid_frequency_range"]
            for entry in self.tl_curve_entries
            if entry.get("valid_frequency_range") is not None
        ]

        if not valid_ranges:
            QMessageBox.warning(self, "Faixa válida",
                "Nenhuma curva possui informação de faixa válida.")
            return
        x_min, x_max = valid_ranges[-1]
        values = []
        for entry in self.tl_curve_entries:
            x, y = entry["curve"].getData()
            if x is not None:
                values.extend(y[(x >= x_min) & (x <= x_max) & np.isfinite(y)])
        if not values:
            return
        y_min, y_max = float(np.min(values)), float(np.max(values))
        padding = max((y_max - y_min) * 0.05, 0.1)
        inputs["x_min"].setValue(x_min); inputs["x_max"].setValue(x_max)
        inputs["y_min"].setValue(y_min - padding); inputs["y_max"].setValue(y_max + padding)
        self._set_tl_plot_range(inputs)

    def load_tl_from_frf_files(self):
        """Lê H31/H32/H34 das cargas A e B e gera uma curva de TL."""

        dialog = FRFFileSelectionDialog(
            self,
            TransmissionLossExperiment.MEASUREMENT_SEQUENCE,
        )

        if dialog.exec() != QDialog.Accepted:

            return

        curve_name, paths = dialog.selection()

        missing = [step.value for step, path in paths.items() if not path]
        if missing:

            QMessageBox.warning(
                self,
                "Ler FRFs",
                "Selecione um arquivo para: " + ", ".join(missing),
            )

            return

        if not curve_name:

            QMessageBox.warning(
                self,
                "Ler FRFs",
                "Informe um nome para a curva de TL.",
            )

            return

        imported = {}
        for step, path in paths.items():
            try:
                frf = read_frf_csv(path)
                result = FRFMeasurementResult(frf, 0, 0, 0, 0, 0, 0, [], None)
                imported[step] = StoredTLMeasurement(
                    step, result, MeasurementAcceptance.ACCEPTED)
            except Exception as error:
                QMessageBox.warning(self, "Ler FRFs",
                    f"Não foi possível ler {step.value}: {error}")
                return

        try:
            imported_experiment = TransmissionLossExperiment(self.controller, self.config)
            imported_experiment.measurements = imported
            imported_experiment.state = TLExperimentState.READY_TO_PROCESS
            result = imported_experiment.process()
            mask = np.isfinite(result.transmission_loss)
            self._add_tl_curve(
                result.frequency[mask], result.transmission_loss[mask], curve_name,
                (result.valid_frequency_range.minimum,
                 result.valid_frequency_range.maximum),
            )
            self.tl_active_valid_range = (result.valid_frequency_range.minimum,
                                          result.valid_frequency_range.maximum)
            self.fit_tl_plot()
            self._update_controls()
        except TransmissionLossError as error:
            QMessageBox.warning(self, "Ler FRFs", str(error))

    # ========================================================
    # CURVAS DE TL
    # ========================================================

    def _add_tl_curve(
        self,
        frequency: np.ndarray,
        transmission_loss: np.ndarray,
        name: str,
        valid_frequency_range: tuple[float, float] | None = None,
    ) -> dict:

        return TLPlotController.add_curve(
            self, frequency, transmission_loss, name,
            valid_frequency_range,
        )

    # ========================================================

    def _clear_tl_curves(self):
        TLPlotController.clear_curves(self)

    # ========================================================
    # IMPORTAÇÃO DE TL
    # ========================================================

    def import_tl_csv_files(self):

        filepaths, _ = QFileDialog.getOpenFileNames(
            self,
            "Escolha arquivos CSV de TL",
            "",
            "Arquivos CSV (*.csv);;Todos os arquivos (*)",
        )

        if not filepaths:

            return

        errors = []

        imported = 0

        for filepath in filepaths:

            try:
                (
                    frequency,
                    transmission_loss,
                    valid_frequency_range,
                ) = read_tl_csv(filepath)

                self._add_tl_curve(
                    frequency=frequency,
                    transmission_loss=transmission_loss,
                    name=Path(filepath).stem,
                    valid_frequency_range=valid_frequency_range,
                )

                imported += 1

            except Exception as error:

                errors.append(
                    f"{Path(filepath).name}: {error}"
                )

        if imported:

            self.fit_tl_plot()

            self._update_controls()

        if errors:

            QMessageBox.warning(
                self,
                "Importação de TL",
                "\n".join(errors),
            )

    # ========================================================
    # EXPORTAÇÃO DO GRÁFICO
    # ========================================================

    def save_tl_plot_png(self):

        if not self.tl_curve_entries:

            QMessageBox.warning(
                self,
                "Salvar gráfico",
                "Adicione ou processe ao menos uma curva de TL.",
            )

            return

        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar gráfico de TL",
            "TL_comparacao.png",
            "Imagem PNG (*.png)",
        )

        if not filepath:

            return

        if not filepath.lower().endswith(".png"):

            filepath += ".png"

        try:

            save_plot_png(self.tl_plot, filepath)

        except OSError as error:

            QMessageBox.critical(
                self,
                "Salvar gráfico",
                str(error),
            )

    # ========================================================
    # EXPORTAÇÃO DAS CURVAS ACUMULADAS
    # ========================================================

    def save_tl_plot_csv(self):

        if not self.tl_curve_entries:

            QMessageBox.warning(
                self,
                "Salvar gráfico CSV",
                "Adicione ou processe ao menos uma curva de TL.",
            )

            return

        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar curvas de TL",
            "TL_curvas_acumuladas.csv",
            "Arquivos CSV (*.csv)",
        )

        if not filepath:

            return

        if not filepath.lower().endswith(".csv"):

            filepath += ".csv"

        try:

            build_tl_curve_dataframe(self.tl_curve_entries).to_csv(
                filepath,
                index=False,
            )

        except OSError as error:

            QMessageBox.critical(
                self,
                "Salvar gráfico CSV",
                str(error),
            )

    # ========================================================
    # SALVAR
    # ========================================================

    def save_experiment(self):

        if self.tl_result is None:

            QMessageBox.warning(
                self,
                "Salvar",
                "Processe a TL antes de salvar.",
            )

            return

        directory = (
            self.config
            .metadata
            .output_directory
            .strip()
        )

        if not directory:

            QMessageBox.warning(
                self,
                "Diretório de salvamento",
                "Defina o diretório de resultados "
                "na aba Configuração.",
            )

            self.tabs.setCurrentWidget(
                self.config_tab
            )

            return

        try:

            Path(directory).mkdir(
                parents=True,
                exist_ok=True,
            )

            saved = (
                DataExporter
                .export_complete_tl_experiment(
                    config=self.config,
                    measurements=(
                        self.experiment
                        .measurements
                    ),
                    tl_result=(
                        self.tl_result
                    ),
                    directory=directory,
                )
            )

            QMessageBox.information(
                self,
                "Salvamento",
                "Ensaio salvo com sucesso em:\n\n"
                f"{saved['root']}",
            )

        except (
            ExportError,
            OSError,
        ) as error:

            QMessageBox.critical(
                self,
                "Erro ao salvar",
                str(error),
            )

    # ========================================================
    # NOVO MODELO
    # ========================================================

    def start_new_model_experiment(self):
        """
        Prepara a mesma configuração técnica para outro modelo.

        A geometria, aquisição e canais permanecem nos campos de
        configuração. O operador apenas atualiza identificação e
        diretório, aplica a configuração e inicia a nova sequência.
        """

        if (
            self.measurement_in_progress
            or self.measurement_waiting_for_monitor
        ):

            QMessageBox.warning(
                self,
                "Novo ensaio",
                "Aguarde o término ou cancele a medição atual.",
            )

            return

        answer = QMessageBox.question(
            self,
            "Novo ensaio / modelo",
            "O resultado atual será removido da interface.\n\n"
            "Salve o ensaio atual antes de continuar, caso ainda "
            "não o tenha salvo.\n\n"
            "Deseja preparar uma nova sequência de TL?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if answer != QMessageBox.Yes:

            return

        # O monitor do modelo anterior não deve permanecer com a DAQ aberta
        # enquanto o operador revisa a configuração do próximo ensaio.
        # Os campos da aba Configuração não são alterados aqui.
        if not self.stop_monitoring(wait=True):

            QMessageBox.warning(
                self,
                "Novo ensaio",
                "Não foi possível encerrar o monitoramento contínuo. "
                "Aguarde alguns segundos e tente novamente.",
            )

            return

        self._clear_monitoring_data()

        self.experiment.reset()

        self.last_measurement = None

        self.displayed_measurement_frf = None

        self.coherence_frozen_to_measurement = False

        self.tl_result = None

        self.progress_bar.setValue(0)

        clear_quality_labels(self)

        self._clear_tl_curves()

        self.result_range_label.setText("-")

        self.result_points_label.setText("-")

        self.instruction_label.setText(
            "Atualize a identificação e o diretório, aplique a "
            "configuração e inicie o novo ensaio."
        )

        self._set_status_banner(
            "NOVO MODELO — CONFIGURE A IDENTIFICAÇÃO",
            "idle",
        )

        self.tabs.setCurrentWidget(
            self.config_tab
        )

        self._update_controls()

    # ========================================================
    # CONTROLES
    # ========================================================
