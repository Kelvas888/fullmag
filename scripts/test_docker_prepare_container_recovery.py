"""Publication fencing for read-only abrupt-stop preparation."""
import contextlib
import copy
import unittest
from unittest.mock import patch

import docker_prepare_container_recovery as module
from docker_build_control import BuildControlError


class Control:
    project = 'fullmag-master'

    def __init__(self):
        self.records = {}
        self.events = []
        self.leased = False

    def prepare(self):
        self.events.append('control-prepare')

    @contextlib.contextmanager
    def operation(self, phase, inputs):
        self.events.append('lease-acquired')
        self.leased = True
        try:
            yield {'root': 'container-recovery-preparation/attempts/' + 'a' * 32,
                   'receipt': {'attempt': 'a' * 32}}
        finally:
            self.leased = False
            self.events.append('lease-released')

    def read_bytes(self, relative, optional=False):
        return self.records.get(relative)

    def write_bytes(self, relative, raw):
        if not self.leased:
            raise AssertionError('publication outside group lease')
        self.events.append(relative)
        self.records[relative] = raw


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.control = Control()
        self.pins = {'request_id': 'a80357af-97c4-436e-8773-841bd20e5b72',
                     'source_root': '/registered/source', 'development_attempt': 'b' * 32}
        self.proof = {'schema': 'test-fixture', 'bytes': 'frozen'}
        self.builder = patch.object(module.recovery, 'prepare_abrupt_stop_proof', return_value=self.proof).start()
        self.validator = patch.object(module.recovery, 'validate_operator_authorization', side_effect=lambda value: value).start()
        self.proof_validator = patch.object(module.recovery, 'validate_abrupt_stop_proof').start()
        self.addCleanup(patch.stopall)

    def test_default_dryrun_never_prepares_control_or_writes(self):
        result = module.prepare(self.control, self.pins, {})
        self.assertEqual(result['state'], 'validated-read-only')
        self.assertFalse(result['application_started'])
        self.assertFalse(result['compute_started'])
        self.assertEqual(self.control.events, [])
        self.assertEqual(self.control.records, {})
        self.assertEqual(self.builder.call_count, 1)

    def test_publication_revalidates_under_lease_and_evidence_precedes_capability(self):
        def observe(*args, **kwargs):
            if self.builder.call_count == 2:
                self.assertTrue(self.control.leased)
            return self.proof
        self.builder.side_effect = observe
        result = module.prepare(self.control, self.pins, {}, publish=True)
        self.assertEqual(self.builder.call_count, 2)
        self.assertEqual(result['state'], 'prepared-awaiting-explicit-start')
        self.assertLess(self.control.events.index(result['proof_path']), self.control.events.index(result['operator_authorization_path']))
        self.proof_validator.assert_called_once()
        self.assertFalse(result['application_started'])

    def test_drift_after_admission_does_not_publish(self):
        self.builder.side_effect = [self.proof, {**self.proof, 'bytes': 'changed'}]
        with self.assertRaisesRegex(BuildControlError, 'changed before publication'):
            module.prepare(self.control, self.pins, {}, publish=True)
        self.assertEqual(self.control.records, {})
        self.assertFalse(self.control.leased)

    def test_same_request_cannot_replace_archived_proof(self):
        preview = module.prepare(self.control, self.pins, {})
        self.control.records[preview['proof_path']] = b'older evidence'
        with self.assertRaisesRegex(BuildControlError, 'already contains different'):
            module.prepare(self.control, self.pins, {}, publish=True)
        self.assertEqual(self.control.records, {preview['proof_path']: b'older evidence'})

    def test_duplicate_operator_keys_fail_closed(self):
        with self.assertRaisesRegex(BuildControlError, 'duplicate'):
            module._unique_object([('request_id', 'first'), ('request_id', 'second')])


if __name__ == '__main__':
    unittest.main()
