from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json

import numpy as np
import pandas as pd

from acquisition_controller import (
    FRFMeasurementResult,
)

from experiments.transmission_loss import (
    TLResult,
    StoredTLMeasurement,
    TLMeasurementStep,
)

from config import AppConfig


# ============================================================
# EXCEÇÕES
# ============================================================

class ExportError(RuntimeError):
    """
    Erro específico da camada de exportação.
    """

    pass


# ============================================================
# EXPORTADOR
# ============================================================

class DataExporter:
    """
    Responsável por salvar:

    - FRF
    - TL
    - metadados
    - informações das medições

    Não realiza processamento.
    """

    # ========================================================
    # DIRETÓRIO
    # ========================================================

    @staticmethod
    def ensure_directory(
        directory: str | Path,
    ) -> Path:

        path = Path(directory)

        try:

            path.mkdir(
                parents=True,
                exist_ok=True,
            )

        except Exception as exc:

            raise ExportError(
                f"Não foi possível criar "
                f"o diretório '{path}'."
            ) from exc

        return path

    # ========================================================
    # EXPORTAÇÃO DE FRF
    # ========================================================

    @staticmethod
    def export_frf(
        result: FRFMeasurementResult,
        filepath: str | Path,
    ) -> Path:
        """
        Salva uma FRF completa em CSV.

        Colunas:

        frequency_Hz
        H_real
        H_imag
        H_magnitude
        H_phase_deg
        coherence
        Gxx
        Gyy
        Gxy_real
        Gxy_imag
        valid
        """

        filepath = Path(filepath)

        try:

            filepath.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            frf = result.frf

            dataframe = pd.DataFrame(
                {
                    "frequency_Hz":
                        frf.frequency,

                    "H_real":
                        np.real(
                            frf.H
                        ),

                    "H_imag":
                        np.imag(
                            frf.H
                        ),

                    "H_magnitude":
                        np.abs(
                            frf.H
                        ),

                    "H_phase_deg":
                        np.angle(
                            frf.H,
                            deg=True,
                        ),

                    "coherence":
                        frf.coherence,

                    "Gxx":
                        frf.Gxx,

                    "Gyy":
                        frf.Gyy,

                    "Gxy_real":
                        np.real(
                            frf.Gxy
                        ),

                    "Gxy_imag":
                        np.imag(
                            frf.Gxy
                        ),

                    "valid":
                        frf.valid_mask,
                }
            )

            dataframe.to_csv(
                filepath,
                index=False,
            )

            return filepath

        except Exception as exc:

            raise ExportError(
                f"Não foi possível salvar "
                f"a FRF em '{filepath}'."
            ) from exc

    # ========================================================
    # EXPORTAÇÃO DE TL
    # ========================================================

    @staticmethod
    def export_tl(
        result: TLResult,
        filepath: str | Path,
    ) -> Path:
        """
        Salva a curva completa de TL.

        IMPORTANTE:

        O vetor é salvo desde 0 Hz, quando
        disponível.

        Frequências fora da faixa válida não
        são removidas.
        """

        filepath = Path(filepath)

        try:

            filepath.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            dataframe = pd.DataFrame(
                {
                    "frequency_Hz":
                        result.frequency,

                    "TL_dB":
                        result.transmission_loss,

                    "valid":
                        result.valid_mask,

                    "A_real":
                        np.real(
                            result.A
                        ),

                    "A_imag":
                        np.imag(
                            result.A
                        ),

                    "B_real":
                        np.real(
                            result.B
                        ),

                    "B_imag":
                        np.imag(
                            result.B
                        ),

                    "C_real":
                        np.real(
                            result.C
                        ),

                    "C_imag":
                        np.imag(
                            result.C
                        ),

                    "D_real":
                        np.real(
                            result.D
                        ),

                    "D_imag":
                        np.imag(
                            result.D
                        ),

                    "two_load_separation":
                        result.two_load_separation,
                }
            )

            dataframe.to_csv(
                filepath,
                index=False,
            )

            return filepath

        except Exception as exc:

            raise ExportError(
                f"Não foi possível salvar "
                f"a TL em '{filepath}'."
            ) from exc

    # ========================================================
    # EXPORTA AS SEIS FRFs
    # ========================================================

    @staticmethod
    def export_tl_measurements(
        measurements: dict[
            TLMeasurementStep,
            StoredTLMeasurement,
        ],
        directory: str | Path,
    ) -> list[Path]:
        """
        Salva as seis FRFs utilizadas no
        cálculo da TL.
        """

        directory = (
            DataExporter.ensure_directory(
                directory
            )
        )

        saved_files: list[Path] = []

        try:

            for step, stored in (
                measurements.items()
            ):

                filepath = (
                    directory
                    /
                    f"{step.value}.csv"
                )

                saved_path = (
                    DataExporter.export_frf(
                        stored.result,
                        filepath,
                    )
                )

                saved_files.append(
                    saved_path
                )

            return saved_files

        except Exception as exc:

            raise ExportError(
                "Não foi possível salvar "
                "as medições do ensaio."
            ) from exc

    # ========================================================
    # METADADOS
    # ========================================================

    @staticmethod
    def export_metadata(
        config: AppConfig,
        tl_result: TLResult | None,
        filepath: str | Path,
    ) -> Path:
        """
        Salva os metadados em JSON.
        """

        filepath = Path(filepath)

        try:

            filepath.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            metadata = (
                DataExporter._build_metadata(
                    config=config,
                    tl_result=tl_result,
                )
            )

            with filepath.open(
                "w",
                encoding="utf-8",
            ) as file:

                json.dump(
                    metadata,
                    file,
                    indent=4,
                    ensure_ascii=False,
                )

            return filepath

        except Exception as exc:

            raise ExportError(
                f"Não foi possível salvar "
                f"os metadados em '{filepath}'."
            ) from exc

    # ========================================================
    # MONTA METADADOS
    # ========================================================

    @staticmethod
    def _build_metadata(
        config: AppConfig,
        tl_result: TLResult | None,
    ) -> dict:
        """
        Converte as configurações em estrutura
        serializável.
        """

        acquisition = config.acquisition
        acoustics = config.acoustics
        tl = config.transmission_loss
        quality = config.quality
        metadata_config = config.metadata

        channels = []

        for channel in config.channels:

            channels.append(
                {
                    "physical_channel":
                        channel.physical_channel,

                    "enabled":
                        channel.enabled,

                    "name":
                        channel.name,

                    "sensor_type":
                        channel.sensor_type.value,

                    "sensitivity_mv_pa":
                        channel.sensitivity_mv_pa,

                    "min_voltage":
                        channel.min_voltage,

                    "max_voltage":
                        channel.max_voltage,

                    "iepe_enabled":
                        channel.iepe_enabled,

                    "iepe_current_a":
                        channel.iepe_current_a,
                }
            )

        result = {
            "experiment": {
                "name":
                    metadata_config.experiment_name,

                "number":
                    metadata_config.experiment_number,

                "operator":
                    metadata_config.operator,

                "notes":
                    metadata_config.notes,

                "output_directory":
                    metadata_config.output_directory,
            },

            "acquisition": {
                "sample_rate_requested_Hz":
                    acquisition.sample_rate,

                "num_samples":
                    acquisition.num_samples,

                "num_averages":
                    acquisition.num_averages,

                "window":
                    acquisition.window.value,

                "overlap":
                    acquisition.overlap,

                "frf_estimator":
                    acquisition.frf_estimator.value,

                "stabilization_time_s":
                    acquisition.stabilization_time,

                "frequency_resolution_Hz":
                    acquisition.frequency_resolution,

                "block_duration_s":
                    acquisition.block_duration,

                "nyquist_requested_Hz":
                    acquisition.nyquist_frequency,
            },

            "acoustics": {
                "temperature_C":
                    acoustics.temperature_c,

                "speed_of_sound_m_s":
                    acoustics.speed_of_sound,

                "air_density_kg_m3":
                    acoustics.air_density,

                "reference_pressure_Pa":
                    acoustics.reference_pressure,
            },

            "transmission_loss": {
                "tube_diameter_m":
                    tl.tube_diameter,

                "spacing_12_m":
                    tl.spacing_12,

                "spacing_34_m":
                    tl.spacing_34,

                "reference_position":
                    tl.reference_position,

                "mobile_positions":
                    tl.mobile_positions,

                "load_A":
                    tl.load_a_name,

                "load_B":
                    tl.load_b_name,

                "automatic_valid_frequency_range":
                    tl.automatic_valid_frequency_range,
            },

            "quality": {
                "coherence_threshold":
                    quality.coherence_threshold,

                "clipping_threshold":
                    quality.clipping_threshold,
            },

            "channels":
                channels,
        }

        # ----------------------------------------------------
        # RESULTADO DA FAIXA VÁLIDA
        # ----------------------------------------------------

        if tl_result is not None:

            valid_range = (
                tl_result.valid_frequency_range
            )

            result[
                "transmission_loss"
            ][
                "calculated_valid_range_Hz"
            ] = {
                "minimum":
                    valid_range.minimum,

                "maximum":
                    valid_range.maximum,
            }

            result[
                "transmission_loss"
            ][
                "spacing_frequency_range_Hz"
            ] = {
                "minimum":
                    valid_range
                    .microphone_spacing_minimum,

                "maximum":
                    valid_range
                    .microphone_spacing_maximum,
            }

            result[
                "transmission_loss"
            ][
                "plane_wave_cutoff_Hz"
            ] = (
                valid_range
                .plane_wave_cutoff
            )

            result[
                "transmission_loss"
            ][
                "nyquist_actual_Hz"
            ] = (
                valid_range
                .nyquist_frequency
            )

            result[
                "transmission_loss"
            ][
                "stored_frequency_range_Hz"
            ] = {
                "minimum":
                    float(
                        tl_result
                        .frequency[0]
                    ),

                "maximum":
                    float(
                        tl_result
                        .frequency[-1]
                    ),
            }

        return result

    # ========================================================
    # SALVA ENSAIO COMPLETO
    # ========================================================

    @staticmethod
    def export_complete_tl_experiment(
        config: AppConfig,
        measurements: dict[
            TLMeasurementStep,
            StoredTLMeasurement,
        ],
        tl_result: TLResult,
        directory: str | Path,
    ) -> dict[str, Path | list[Path]]:
        """
        Salva todo o ensaio em uma estrutura
        organizada de diretórios.
        """

        root = (
            DataExporter.ensure_directory(
                directory
            )
        )

        frf_directory = (
            root
            / "frf"
        )

        # ----------------------------------------------------
        # TL
        # ----------------------------------------------------

        tl_path = (
            root
            / "transmission_loss.csv"
        )

        DataExporter.export_tl(
            result=tl_result,
            filepath=tl_path,
        )

        # ----------------------------------------------------
        # FRFs
        # ----------------------------------------------------

        frf_paths = (
            DataExporter
            .export_tl_measurements(
                measurements=measurements,
                directory=frf_directory,
            )
        )

        # ----------------------------------------------------
        # Metadados
        # ----------------------------------------------------

        metadata_path = (
            root
            / "metadata.json"
        )

        DataExporter.export_metadata(
            config=config,
            tl_result=tl_result,
            filepath=metadata_path,
        )

        return {
            "root":
                root,

            "tl":
                tl_path,

            "frfs":
                frf_paths,

            "metadata":
                metadata_path,
        }