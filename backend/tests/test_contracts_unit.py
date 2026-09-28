"""Real pure/Pydantic contract checks; safe without FastAPI or ML dependencies."""

import unittest
import os
from unittest.mock import patch
from uuid import uuid4

from pydantic import TypeAdapter, ValidationError

from app.contracts import JobState, require_transition
from app.config import data_root
from app.schemas import JobCreate, ProjectUpdate


class FoundationContractTests(unittest.TestCase):
    def test_cancel_and_success_race_cannot_publish_without_evidence(self):
        require_transition(JobState.QUEUED, JobState.RUNNING)
        with self.assertRaises(ValueError):
            require_transition(JobState.RUNNING, JobState.SUCCEEDED)
        with self.assertRaises(ValueError):
            require_transition(JobState.RUNNING, JobState.SUCCEEDED, evidence_verified=True)
        require_transition(JobState.RUNNING, JobState.SUCCEEDED, process_exited=True, evidence_verified=True)
        require_transition(JobState.RUNNING, JobState.CANCELLING)
        with self.assertRaises(ValueError):
            require_transition(JobState.CANCELLING, JobState.SUCCEEDED, evidence_verified=True)
        with self.assertRaises(ValueError):
            require_transition(JobState.CANCELLING, JobState.CANCELLED)
        require_transition(JobState.CANCELLING, JobState.CANCELLED, process_exited=True)
        with self.assertRaises(ValueError):
            require_transition(JobState.CANCELLED, JobState.RUNNING)

    def test_interrupted_requires_confirmed_exit(self):
        with self.assertRaises(ValueError):
            require_transition(JobState.RUNNING, JobState.INTERRUPTED)
        require_transition(JobState.RUNNING, JobState.INTERRUPTED, process_exited=True)

    def test_job_parameters_are_bound_to_kind_and_limited(self):
        good = {"kind": "train", "params": {"dataset_id": str(uuid4()), "experiment_name": "tiny", "epochs": 1, "batch": 1, "seed": 0}}
        model = TypeAdapter(JobCreate).validate_python(good)
        self.assertEqual(model.kind.value, "train")
        for bad in (
            {**good, "kind": "dataset_check"},
            {**good, "kind": "unknown"},
            {**good, "params": {**good["params"], "epochs": 101}},
            {**good, "params": {**good["params"], "device": "shell-command"}},
            {**good, "params": {**good["params"], "arbitrary": "injected"}},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                TypeAdapter(JobCreate).validate_python(bad)

    def test_empty_patch_and_unknown_fields_rejected(self):
        for bad in ({}, {"name": None}, {"name": "valid", "owner_id": str(uuid4())}):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                ProjectUpdate.model_validate(bad)

    def test_blank_data_root_rejected_before_any_write(self):
        with patch.dict(os.environ, {"PLATFORM_DATA_ROOT": "  "}):
            with self.assertRaises(ValueError):
                data_root()


if __name__ == "__main__":
    unittest.main()
