import math
import unittest

from core.processing import FaultDetector, SensorSample, covariance_matrix
from core.schur import off_diagonal_norm, schur_decomposition, schur_health_index


class SchurTests(unittest.TestCase):
    def test_schur_decomposition_diagonalizes_symmetric_matrix(self) -> None:
        matrix = [
            [4.0, 1.0],
            [1.0, 3.0],
        ]

        _, triangular = schur_decomposition(matrix, iterations=150)

        self.assertLess(off_diagonal_norm(triangular), 1e-6)
        diagonal_values = sorted([triangular[0][0], triangular[1][1]])
        self.assertAlmostEqual(diagonal_values[0], 2.381966011, places=5)
        self.assertAlmostEqual(diagonal_values[1], 4.618033989, places=5)

    def test_health_index_is_normalized(self) -> None:
        covariance = [
            [5.0, 0.0, 0.0],
            [0.0, 3.0, 0.0],
            [0.0, 0.0, 2.0],
        ]

        health_index, triangular = schur_health_index(covariance)

        self.assertAlmostEqual(health_index, 5.0, places=6)
        self.assertLess(off_diagonal_norm(triangular), 1e-8)


class ProcessingTests(unittest.TestCase):
    def _sample(self, timestamp: str, vibration_scale: float, current: float, temperature: float) -> SensorSample:
        base = math.sin(len(timestamp))
        return SensorSample(
            timestamp=timestamp,
            vib_x=base * vibration_scale,
            vib_y=(base + 0.1) * vibration_scale,
            vib_z=(base + 0.2) * vibration_scale,
            current=current,
            temperature=temperature,
        )

    def test_covariance_matrix_is_symmetric(self) -> None:
        samples = [
            [1.0, 2.0, 3.0],
            [2.0, 4.0, 6.0],
            [3.0, 6.0, 9.0],
        ]

        covariance = covariance_matrix(samples)

        self.assertEqual(covariance[0][1], covariance[1][0])
        self.assertEqual(covariance[1][2], covariance[2][1])

    def test_fault_detector_transitions_to_stop_on_large_shift(self) -> None:
        detector = FaultDetector(
            window_size=4,
            baseline_windows=2,
            reduced_threshold_z=0.5,
            stop_threshold_z=1.0,
            normal_speed_ratio=1.0,
            reduced_speed_ratio=0.5,
        )

        stable_samples = [
            SensorSample(f"t{i}", 1.0 + i * 0.01, 1.1 + i * 0.01, 1.2 + i * 0.01, 10.0, 40.0)
            for i in range(6)
        ]
        for sample in stable_samples:
            detector.process_sample(sample)

        fault_samples = [
            SensorSample(f"f{i}", 3.0 + i, 4.0 + i, 5.0 + i, 14.0 + i, 52.0 + i)
            for i in range(4)
        ]

        assessment = None
        for sample in fault_samples:
            assessment = detector.process_sample(sample)

        self.assertIsNotNone(assessment)
        assert assessment is not None
        self.assertTrue(assessment.baseline_ready)
        self.assertEqual(assessment.state, "stop")
        self.assertEqual(assessment.motor_speed_ratio, 0.0)

    def test_fault_detector_keeps_motor_stopped_until_baseline_ready(self) -> None:
        detector = FaultDetector(
            window_size=3,
            baseline_windows=2,
            reduced_threshold_z=1.0,
            stop_threshold_z=2.0,
            normal_speed_ratio=1.0,
            reduced_speed_ratio=0.5,
        )

        samples = [
            SensorSample(f"t{i}", 1.0 + i * 0.01, 1.1 + i * 0.01, 1.2 + i * 0.01, 10.0, 40.0)
            for i in range(4)
        ]

        assessments = []
        for sample in samples:
            assessment = detector.process_sample(sample)
            if assessment is not None:
                assessments.append(assessment)

        self.assertEqual(len(assessments), 2)
        self.assertFalse(assessments[0].baseline_ready)
        self.assertEqual(assessments[0].state, "stop")
        self.assertEqual(assessments[0].motor_speed_ratio, 0.0)


if __name__ == "__main__":
    unittest.main()
