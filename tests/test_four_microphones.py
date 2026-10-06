"""Regressões do ensaio com quatro microfones, sem usar hardware NI."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import json
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
from PySide6.QtWidgets import QApplication, QMessageBox

from config import AppConfig, ChannelConfig, FRFEstimator, SensorType, WindowType
from daq import AcquisitionData, DAQError
from acquisition_controller import AcquisitionController, AcquisitionCancelled, AcquisitionControllerError
from experiments.transmission_loss import (
    MeasurementAcceptance, TLExperimentState, TLLoadStep, TLMeasurementStep,
    TransmissionLossError, TransmissionLossExperiment,
)
from exporter import DataExporter
from acquisition_worker import MonitoringWorker
from interface import MainWindow
from monitoring import MonitoringData
from results_tab import read_frf_csv


def make_config(positions=(1, 2, 3, 4)):
    config = AppConfig()
    config.channels = [
        ChannelConfig(f"Fake/ai{index}", name=f"P{position}", microphone_position=position)
        for index, position in enumerate(positions)
    ]
    config.acquisition.num_samples = 512
    config.acquisition.num_averages = 3
    config.acquisition.stabilization_time = 0
    config.acquisition.window = WindowType.RECTANGULAR
    return config


class FakeDAQ:
    """Gera quatro pressões coerentes em uma única matriz por leitura."""

    device_name = "Fake"

    def __init__(self, config):
        self.config = config
        self.calls = 0
        self.configure_calls = 0
        self.actual_sample_rate = config.acquisition.sample_rate
        self.random = np.random.default_rng(42)
        self.load = "A"
        self.physics = False
        self.noisy_position = None
        self.clipped_position = None
        self.fail = False
        self.last_block = None
        self.acquisition = config.acquisition

    def connect(self, name=None):
        self.device_name = name or "Fake"

    def get_available_ai_channels(self):
        return [f"Fake/ai{index}" for index in range(4)]

    def configure(self, channels, acquisition):
        self.configure_calls += 1
        self.acquisition = acquisition
        self.actual_sample_rate = acquisition.sample_rate

    def disconnect(self):
        pass

    def acquire(self):
        if self.fail:
            raise DAQError("Erro simulado")
        self.calls += 1
        n = self.acquisition.num_samples
        fs = self.actual_sample_rate
        frequency = np.fft.rfftfreq(n, 1 / fs)
        source = self.random.normal(0, 0.02, n)
        source_spectrum = np.fft.rfft(source)
        if self.physics:
            z0 = self.config.acoustics.air_density * self.config.acoustics.speed_of_sound
            k = 2 * np.pi * frequency / self.config.acoustics.speed_of_sound
            # Elemento resistivo conhecido: A=D=1, B=0.8*Z0, C=0.
            admittance = ((0.7 + 0.3j) if self.load == "A" else (1.5 - 0.4j)) / z0
            p2 = np.full_like(frequency, 1 + 0.8 * z0 * admittance, dtype=complex)
            u2 = np.full_like(frequency, admittance, dtype=complex)
            p1 = np.cos(k * self.config.transmission_loss.spacing_12) * p2 + (
                1j * z0 * np.sin(k * self.config.transmission_loss.spacing_12) * u2
            )
            p4 = np.cos(k * self.config.transmission_loss.spacing_34) - (
                1j * z0 * np.sin(k * self.config.transmission_loss.spacing_34) * admittance
            )
            transfers = {1: p1, 2: p2, 3: np.ones_like(frequency), 4: p4}
        else:
            transfers = {
                position: gain * np.exp(-2j * np.pi * frequency * delay / fs)
                for position, gain, delay in ((1, 2, 3), (2, 0.5, 7), (3, 1, 0), (4, 1.5, 11))
            }
        signals = {
            position: np.fft.irfft(source_spectrum * transfer, n=n)
            for position, transfer in transfers.items()
        }
        if self.noisy_position:
            signals[self.noisy_position] = self.random.normal(0, 0.02, n)
        if self.clipped_position:
            signals[self.clipped_position] *= 10000
        active = [channel for channel in self.config.channels if channel.enabled]
        data = np.column_stack([signals[channel.microphone_position] for channel in active])
        self.last_block = AcquisitionData(
            np.arange(n) / fs, data, fs,
            [channel.name for channel in active], [channel.physical_channel for channel in active],
        )
        return self.last_block


def finish_experiment(experiment, daq):
    experiment.start()
    experiment.measure_current_step()
    experiment.accept_measurement()
    experiment.confirm_load_change()
    daq.load = "B"
    experiment.measure_current_step()
    experiment.accept_measurement()
    return experiment.process()


class ConfigurationTests(unittest.TestCase):
    def test_explicit_mapping_and_disabled_channels(self):
        config = make_config((4, 3, 1, 2))
        config.channels.insert(0, ChannelConfig("Unused", enabled=False))
        config.validate()
        self.assertEqual(config.tl_channel_indices(), {4: 0, 3: 1, 1: 2, 2: 3})

    def test_reject_invalid_tl_channels(self):
        for mutation in (
            lambda c: c.channels.pop(),
            lambda c: setattr(c.channels[3], "microphone_position", 1),
            lambda c: setattr(c.channels[3], "microphone_position", None),
            lambda c: setattr(c.channels[3], "physical_channel", c.channels[0].physical_channel),
            lambda c: setattr(c.channels[0], "sensor_type", SensorType.VOLTAGE),
            lambda c: setattr(c.channels[3], "enabled", False),
            lambda c: setattr(c.channels[0], "sensitivity_mv_pa", 0),
            lambda c: setattr(c.transmission_loss, "reference_position", 1),
        ):
            with self.subTest(mutation=mutation):
                config = make_config()
                mutation(config)
                with self.assertRaises(ValueError):
                    config.validate()


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.config = make_config((4, 3, 1, 2))
        self.daq = FakeDAQ(self.config)
        self.controller = AcquisitionController(self.daq, self.config)

    def test_same_blocks_and_reference_mapping_h1_h2(self):
        for estimator in (FRFEstimator.H1, FRFEstimator.H2):
            with self.subTest(estimator=estimator):
                self.config.acquisition.frf_estimator = estimator
                callbacks, progress = [], []
                initial_calls = self.daq.calls
                result = self.controller.acquire_tl_load(
                    progress_callback=lambda n, total: progress.append((n, total)),
                    frf_update_callback=lambda frfs, n, total: callbacks.append((frfs, n, total)),
                )
                self.assertEqual(self.daq.calls - initial_calls, 3)  # não 9 leituras
                self.assertEqual(set(result.measurements), {1, 2, 4})
                self.assertEqual(progress, [(1, 3), (2, 3), (3, 3)])
                self.assertEqual(len(callbacks), 3)
                self.assertIsNot(callbacks[0][0], callbacks[1][0])
                self.assertIsNot(callbacks[0][0][1].Gxx, callbacks[1][0][1].Gxx)
                self.assertTrue(result.quality.is_valid)
                for position, gain, delay in ((1, 2, 3), (2, 0.5, 7), (4, 1.5, 11)):
                    measurement = result.measurements[position]
                    f = measurement.frf.frequency
                    band = (f > 350) & (f < 2700)
                    expected = gain * np.exp(-2j * np.pi * f * delay / measurement.sample_rate)
                    np.testing.assert_allclose(measurement.frf.H[band], expected[band], atol=1e-10)
                    np.testing.assert_allclose(measurement.frf.coherence[band], 1, atol=1e-12)
                    self.assertEqual(len(measurement.channel_metrics), 4)
                    self.assertEqual(measurement.completed_averages, 3)
                    np.testing.assert_array_equal(measurement.frf.Gxx, result.frfs[1].Gxx)

    def test_averages_are_spectral_not_average_of_ratios(self):
        frames = []
        def capture(*args, **kwargs):
            from signal_processing import FRFProcessor
            value = original(*args, **kwargs)
            frames.append(value)
            return value
        from signal_processing import FRFProcessor
        original = FRFProcessor.calculate_frf
        self.daq.noisy_position = 2
        with patch.object(FRFProcessor, "calculate_frf", side_effect=capture):
            result = self.controller.acquire_tl_load()
        position2_frames = frames[1::3]
        gxx = np.mean([f.Gxx for f in position2_frames], axis=0)
        gxy = np.mean([f.Gxy for f in position2_frames], axis=0)
        np.testing.assert_allclose(result.frfs[2].H[1:], (gxy / gxx)[1:], atol=1e-12)

    def test_any_bad_pair_requires_review(self):
        self.daq.noisy_position = 2
        result = self.controller.acquire_tl_load()
        self.assertFalse(result.quality.is_valid)
        self.assertTrue(result.measurements[1].quality.is_valid)
        self.assertTrue(any("H32:" in warning for warning in result.quality.warnings))
        self.assertAlmostEqual(result.quality.coherence_mean, result.measurements[2].quality.coherence_mean)

    def test_clipping_in_any_of_four_channels(self):
        for position in (1, 2, 3, 4):
            with self.subTest(position=position):
                self.daq.clipped_position = position
                result = self.controller.acquire_tl_load()
                self.assertTrue(result.quality.clipping_detected)
                self.assertFalse(result.quality.is_valid)
                clipped = [m.channel_name for m in result.measurements[1].channel_metrics if m.clipping_detected]
                self.assertEqual(clipped, [f"P{position}"])

    def test_one_average_requires_warning(self):
        self.config.acquisition.num_averages = 1
        result = self.controller.acquire_tl_load()
        self.assertFalse(result.quality.is_valid)
        self.assertTrue(any("uma média" in warning for warning in result.quality.warnings))

    def test_generic_single_pair_api_remains_available(self):
        result = self.controller.acquire_frf(reference_channel_index=1, response_channel_index=2)
        self.assertEqual(result.completed_averages, 3)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.config = make_config()
        self.daq = FakeDAQ(self.config)
        self.controller = AcquisitionController(self.daq, self.config)
        self.experiment = TransmissionLossExperiment(self.controller, self.config)

    def test_two_loads_six_frfs_and_known_tl(self):
        self.daq.physics = True
        result = finish_experiment(self.experiment, self.daq)
        self.assertEqual(self.daq.calls, 6)  # 2 cargas x 3 médias
        self.assertEqual(self.daq.configure_calls, 2)
        self.assertEqual(set(self.experiment.measurements), set(TLMeasurementStep))
        self.assertIsNone(self.experiment.current_step)
        self.assertTrue(np.any(result.valid_mask))
        mask = result.valid_mask
        np.testing.assert_allclose(result.A[mask], 1, atol=1e-10)
        np.testing.assert_allclose(result.D[mask], 1, atol=1e-10)
        np.testing.assert_allclose(result.C[mask], 0, atol=1e-10)
        z0 = self.config.acoustics.air_density * self.config.acoustics.speed_of_sound
        np.testing.assert_allclose(result.B[mask], 0.8 * z0, atol=1e-10)
        np.testing.assert_allclose(result.valid_tl, 20 * np.log10(1.4), atol=1e-10)
        for load_steps in self.experiment.LOAD_FRF_STEPS.values():
            times = [self.experiment.measurements[step].result.total_measurement_time for step in load_steps.values()]
            self.assertEqual(len(set(times)), 1)

    def test_atomic_accept_and_repeat_per_load(self):
        e = self.experiment
        e.start()
        self.assertEqual(e.current_step, TLLoadStep.LOAD_A)
        self.assertNotIn("móvel", e.get_current_instruction())
        e.measure_current_step()
        self.assertEqual(len(e.measurements), 0)
        e.repeat_measurement()
        self.assertIsNone(e.pending_measurement)
        e.measure_current_step()
        e.accept_measurement()
        self.assertEqual(len(e.measurements), 3)
        self.assertEqual(e.state, TLExperimentState.WAITING_LOAD_CHANGE)
        with self.assertRaises(TransmissionLossError):
            e.measure_current_step()
        self.assertIn("Troque", e.get_current_instruction())
        e.confirm_load_change()
        self.assertEqual(e.current_step, TLLoadStep.LOAD_B)
        e.measure_current_step()
        e.accept_measurement()
        self.assertEqual(len(e.measurements), 6)
        self.assertEqual(e.state, TLExperimentState.READY_TO_PROCESS)

    def test_warning_confirmation_is_atomic(self):
        e = self.experiment
        self.daq.noisy_position = 4
        e.start()
        e.measure_current_step()
        with self.assertRaises(TransmissionLossError) as caught:
            e.accept_measurement()
        self.assertNotIn("accept_warning=True", str(caught.exception))
        self.assertEqual(len(e.measurements), 0)
        e.accept_measurement(accept_warning=True)
        self.assertEqual(len(e.measurements), 3)
        self.assertTrue(all(m.acceptance == MeasurementAcceptance.ACCEPTED_WITH_WARNING for m in e.measurements.values()))

    def test_cancel_does_not_store_partial_load(self):
        e = self.experiment
        e.start()
        with self.assertRaises(AcquisitionCancelled):
            e.measure_current_step(progress_callback=lambda n, total: self.controller.cancel())
        self.assertEqual(e.state, TLExperimentState.READY)
        self.assertEqual(e.current_step, TLLoadStep.LOAD_A)
        self.assertIsNone(e.pending_measurement)
        self.assertEqual(len(e.measurements), 0)
        self.assertEqual(self.daq.calls, 1)
        e.measure_current_step()
        self.assertEqual(e.state, TLExperimentState.AWAITING_REVIEW)

    def test_daq_error_and_processing_guard(self):
        self.experiment.start()
        self.daq.fail = True
        with self.assertRaises(AcquisitionControllerError):
            self.experiment.measure_current_step()
        self.assertEqual(self.experiment.state, TLExperimentState.ERROR)
        with self.assertRaises(TransmissionLossError):
            self.experiment.process()

    def test_final_mask_requires_all_six_coherences(self):
        self.daq.physics = True
        finish_experiment(self.experiment, self.daq)
        frf = self.experiment.measurements[TLMeasurementStep.H34_B].result.frf
        index = np.flatnonzero(self.experiment.result.valid_mask)[2]
        frf.valid_mask[index] = False
        self.experiment.state = TLExperimentState.READY_TO_PROCESS
        result = self.experiment.process()
        self.assertFalse(result.valid_mask[index])

    def test_export_and_import_keep_six_frf_format(self):
        self.daq.physics = True
        result = finish_experiment(self.experiment, self.daq)
        self.config.metadata.experiment_name = "Modelo A"
        self.config.metadata.experiment_number = "007"
        with tempfile.TemporaryDirectory() as directory:
            exported = DataExporter.export_complete_tl_experiment(
                self.config, self.experiment.measurements, result, directory,
            )
            self.assertEqual(exported["tl"].name, "TL_Modelo A_007.csv")
            self.assertEqual({p.name for p in exported["frfs"]}, {f"{step.value}.csv" for step in TLMeasurementStep})
            metadata = json.loads(exported["metadata"].read_text(encoding="utf-8"))
            self.assertEqual(metadata["transmission_loss"]["acquisition_mode"], "four_static_microphones")
            self.assertEqual([c["microphone_position"] for c in metadata["channels"]], [1, 2, 3, 4])
            self.assertNotIn("mobile_positions", metadata["transmission_loss"])
            for step in TLMeasurementStep:
                imported = read_frf_csv(Path(directory) / "frf" / f"{step.value}.csv")
                np.testing.assert_allclose(imported.H, self.experiment.measurements[step].result.frf.H, equal_nan=True)

    def test_reset_allows_another_model(self):
        self.daq.physics = True
        finish_experiment(self.experiment, self.daq)
        self.experiment.reset()
        self.assertEqual(self.experiment.current_step, TLLoadStep.LOAD_A)
        self.assertEqual(self.experiment.measurements, {})
        self.assertIsNone(self.experiment.result)
        self.config.metadata.experiment_name = "Modelo B"
        self.daq.load = "A"
        finish_experiment(self.experiment, self.daq)
        self.assertEqual(self.daq.calls, 12)


class MonitoringTests(unittest.TestCase):
    def test_monitor_publishes_all_four_and_latest_only(self):
        config = make_config((4, 3, 1, 2))
        daq = FakeDAQ(config)
        worker = MonitoringWorker(daq, config, monitor_num_samples=256)
        published, errors = [], []
        worker.error.connect(errors.append)
        original = worker._publish_latest_data
        def publish(data):
            published.append(data)
            original(data)
            if len(published) == 3:
                worker.request_stop()
        worker._publish_latest_data = publish
        worker.run()
        self.assertEqual(errors, [])
        self.assertEqual(daq.calls, 3)
        self.assertEqual(len(published), 3)
        latest = worker.take_latest_data()
        self.assertIs(latest, published[-1])
        self.assertIsNone(worker.take_latest_data())
        self.assertEqual(set(latest.spectra), {1, 2, 3, 4})
        self.assertEqual(set(latest.coherences), {1, 2, 4})
        self.assertEqual(latest.coherence_frequency.size, 65)  # nperseg=128: múltiplos segmentos


class InterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        with patch.object(MainWindow, "refresh_devices"), patch("interface.NIDaqDevice"):
            self.window = MainWindow()
        self.config = make_config()
        self.daq = FakeDAQ(self.config)
        self.controller = AcquisitionController(self.daq, self.config)
        self.window.config = self.config
        self.window.controller = self.controller
        self.window.daq = self.daq
        self.window.experiment = TransmissionLossExperiment(self.controller, self.config)
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def test_four_selectors_and_plot_legends(self):
        self.assertEqual(set(self.window.microphone_channel_combos), {1, 2, 3, 4})
        self.assertEqual(set(self.window.microphone_sensitivity_inputs), {1, 2, 3, 4})
        self.assertEqual(set(self.window.spectrum_curves), {1, 2, 3, 4})
        self.assertEqual(set(self.window.coherence_curves), {1, 2, 4})
        self.assertEqual(self.window.monitor_update_timer.interval(), 80)

    def test_initial_channel_mapping_preserves_reference_on_ai0(self):
        self.window.device_combo.addItem("Fake")
        self.assertEqual(
            {p: combo.currentText() for p, combo in self.window.microphone_channel_combos.items()},
            {1: "Fake/ai1", 2: "Fake/ai2", 3: "Fake/ai0", 4: "Fake/ai3"},
        )

    def test_apply_configuration_reads_individual_sensitivities_and_channel_mapping(self):
        w = self.window
        channels = [f"Fake/ai{index}" for index in range(4)]
        w.device_combo.addItem("Fake")
        for position, channel in zip((1, 2, 3, 4), (3, 2, 0, 1)):
            combo = w.microphone_channel_combos[position]
            combo.clear()
            combo.addItems(channels)
            combo.setCurrentIndex(channel)
            w.microphone_sensitivity_inputs[position].setValue(40 + position)
        with patch.object(w, "start_monitoring"):
            self.assertTrue(w.apply_configuration(show_message=False))
        self.assertEqual([c.physical_channel for c in w.config.channels], [
            "Fake/ai3", "Fake/ai2", "Fake/ai0", "Fake/ai1",
        ])
        self.assertEqual([c.sensitivity_mv_pa for c in w.config.channels], [41, 42, 43, 44])
        self.assertEqual(w.config.tl_channel_indices()[3], 2)

    def test_coherence_freezes_but_four_spectra_resume(self):
        w = self.window
        result = self.controller.acquire_tl_load()
        w._measurement_finished(result)
        w.open_spectrum_popup()
        w.open_coherence_popup()
        before = {p: curve.getData()[1].copy() for p, curve in w.coherence_curves.items()}
        frequency = result.frfs[1].frequency
        monitor = MonitoringData(
            frequency, {p: np.full_like(frequency, p) for p in (1, 2, 3, 4)},
            frequency, {p: np.full_like(frequency, 0.2) for p in (1, 2, 4)}, 12800,
        )
        w._update_monitoring_plots(monitor)
        for p in (1, 2, 4):
            np.testing.assert_array_equal(w.coherence_curves[p].getData()[1], before[p])
            np.testing.assert_array_equal(w.coherence_popup.curves[p].getData()[1], before[p])
        for p in (1, 2, 3, 4):
            np.testing.assert_array_equal(w.spectrum_curves[p].getData()[1], monitor.spectra[p])
            np.testing.assert_array_equal(w.spectrum_popup.curves[p].getData()[1], monitor.spectra[p])
        w.coherence_frozen_to_measurement = False
        w._update_monitoring_plots(monitor)
        np.testing.assert_array_equal(w.coherence_curves[2].getData()[1], monitor.coherences[2])
        w.spectrum_popup.close()
        w.coherence_popup.close()
        self.app.processEvents()
        self.assertIsNone(w.spectrum_popup)
        self.assertIsNone(w.coherence_popup)

    def test_each_average_fits_graphs_and_partial_popup_uses_official_data(self):
        w = self.window
        with patch.object(w, "fit_spectrum_plot") as spectrum_fit, patch.object(w, "fit_coherence_plot") as coherence_fit:
            self.controller.acquire_tl_load(frf_update_callback=lambda frfs, n, total: w._measurement_frf_updated(frfs))
            self.assertEqual(spectrum_fit.call_count, 3)
            self.assertEqual(coherence_fit.call_count, 3)
        w.measurement_in_progress = True
        w.open_spectrum_popup()
        for p, frf in w.displayed_measurement_frfs.items():
            np.testing.assert_allclose(w.spectrum_popup.curves[p].getData()[1], np.sqrt(frf.Gyy))
        w.measurement_in_progress = False

    def test_controls_warning_and_configuration_lock(self):
        w = self.window
        w.experiment.start()
        self.daq.noisy_position = 2
        result = w.experiment.measure_current_step()
        w._measurement_finished(result)
        w._update_controls()
        self.assertTrue(w.accept_warning_button.isEnabled())
        self.assertFalse(w.apply_config_button.isEnabled())
        self.assertFalse(w.start_experiment_button.isEnabled())
        with patch.object(QMessageBox, "warning"):
            self.assertFalse(w.apply_configuration(show_message=False))
        w.experiment.accept_measurement(accept_warning=True)
        w._after_accept()
        self.assertTrue(w.confirm_load_button.isEnabled())
        self.assertFalse(w.process_button.isEnabled())
        w.experiment.reset()
        w._update_controls()
        self.assertTrue(w.apply_config_button.isEnabled())
        self.assertTrue(w.start_experiment_button.isEnabled())

    def test_official_worker_thread_finishes_with_three_frfs(self):
        w = self.window
        w.experiment.start()
        with patch.object(w, "start_monitoring") as monitoring:
            w._start_measurement_thread()
            deadline = time.monotonic() + 5
            while w.measurement_in_progress and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.005)
            self.assertFalse(w.measurement_in_progress)
            self.assertEqual(w.experiment.state, TLExperimentState.AWAITING_REVIEW)
            self.assertEqual(set(w.last_measurement.frfs), {1, 2, 4})
            self.assertTrue(w.accept_button.isEnabled())
            monitoring.assert_called_once()


if __name__ == "__main__":
    unittest.main()
