"""Sensitivity classification module.
Determines privacy sensitivity (HIGH or LOW) deterministically based on configurable rules.
"""

from typing import Optional
from src.models import (
    RecordType,
    SensitivityLevel,
    SensitivityRule,
    SensitivityRuleset,
    SensorRecord,
)


def get_default_ruleset() -> SensitivityRuleset:
    """Return default sensitivity rules based on IoT healthcare specifications."""
    return SensitivityRuleset(
        rules={
            RecordType.ECG_SUMMARY: SensitivityRule(
                record_type=RecordType.ECG_SUMMARY,
                always_high=True,
                high_reason="Diagnostic ECG rhythm summary contains high-risk electrophysiological telemetry.",
                low_reason="Standard ECG telemetry.",
            ),
            RecordType.HEART_RATE: SensitivityRule(
                record_type=RecordType.HEART_RATE,
                min_critical_value=50.0,
                max_critical_value=100.0,
                high_reason="Abnormal heart rate (< 50 or > 100 bpm) indicates potential tachycardia or bradycardia crisis.",
                low_reason="Normal resting heart rate within physiological limits (50-100 bpm).",
            ),
            RecordType.TEMPERATURE: SensitivityRule(
                record_type=RecordType.TEMPERATURE,
                min_critical_value=35.5,
                max_critical_value=38.0,
                high_reason="Critical temperature anomaly (< 35.5°C or > 38.0°C) indicates hypothermia or pyrexia.",
                low_reason="Normothermic body temperature reading (35.5°C - 38.0°C).",
            ),
            RecordType.STEP_COUNT: SensitivityRule(
                record_type=RecordType.STEP_COUNT,
                always_low=True,
                high_reason="High activity telemetry.",
                low_reason="Routine ambulatory step count telemetry is low-sensitivity activity data.",
            ),
        }
    )


class SensitivityClassifier:
    """Evaluates sensor records and assigns deterministic sensitivity and classification reasons."""

    def __init__(self, ruleset: Optional[SensitivityRuleset] = None):
        self.ruleset = ruleset or get_default_ruleset()

    def classify_record(self, record: SensorRecord) -> SensorRecord:
        """Classify a single record and attach sensitivity and reason."""
        rule = self.ruleset.rules.get(record.record_type)

        if not rule:
            # Safe fallback: unknown record types default to HIGH for confidentiality
            record.sensitivity = SensitivityLevel.HIGH
            record.classification_reason = (
                f"Unknown record type '{record.record_type}' classified as HIGH by fail-safe policy."
            )
            return record

        if rule.always_high:
            record.sensitivity = SensitivityLevel.HIGH
            record.classification_reason = rule.high_reason
        elif rule.always_low:
            record.sensitivity = SensitivityLevel.LOW
            record.classification_reason = rule.low_reason
        else:
            # Range-based evaluation
            val = record.value
            is_critical = False
            if rule.min_critical_value is not None and val < rule.min_critical_value:
                is_critical = True
            if rule.max_critical_value is not None and val > rule.max_critical_value:
                is_critical = True

            if is_critical:
                record.sensitivity = SensitivityLevel.HIGH
                record.classification_reason = rule.high_reason
            else:
                record.sensitivity = SensitivityLevel.LOW
                record.classification_reason = rule.low_reason

        return record

    def classify_batch(self, records: list[SensorRecord]) -> list[SensorRecord]:
        """Classify a list of sensor records."""
        for rec in records:
            self.classify_record(rec)
        return records
