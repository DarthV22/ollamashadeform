import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import app


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.config_file = root / 'config.json'
        self.config = dict(api_key='test-key', model='llama3.1:8b', active=False,
                           instance_id=None, ip_address=None)
        self.config_file.write_text(json.dumps(self.config), encoding='utf-8')
        for name, value in [('CONFIG_FILE', self.config_file), ('CONFIG_DIR', root)]:
            p = patch.object(app, name, value)
            p.start()
            self.addCleanup(p.stop)
        output = contextlib.redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def test_config_rejects_invalid_shapes_and_placeholder(self):
        for data in [[], {}, dict(self.config, active='false'),
                     dict(self.config, api_key='PUT_YOUR_SHADEFORM_API_KEY_HERE'),
                     dict(self.config, active=True)]:
            self.config_file.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaises(SystemExit):
                app.load_config()

    def test_config_accepts_powershell_bom_and_saves_atomically(self):
        self.config_file.write_text(json.dumps(self.config), encoding='utf-8-sig')
        self.assertEqual(app.load_config(), self.config)
        app.save_config(dict(self.config, model='other'))
        self.assertEqual(app.load_config()['model'], 'other')
        self.assertFalse(self.config_file.with_suffix('.tmp').exists())

    def test_credentials_are_not_command_arguments(self):
        with patch('app.subprocess.run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, 'ok', '')
            app.run_powershell(app.CLEAR_SCRIPT, ['secret', 'instance-1'])
        command = run.call_args.args[0]
        self.assertNotIn('secret', command)
        self.assertEqual(run.call_args.kwargs['env']['SHADEFORM_API_KEY'], 'secret')
        self.assertEqual(command[-1], 'instance-1')

    def test_failed_start_reloads_recovery_id(self):
        self.config_file.write_text(json.dumps(dict(self.config, instance_id='recover-me')))
        with patch('app.run_powershell', return_value=None):
            self.assertFalse(app.initialise(self.config))
        self.assertEqual(self.config['instance_id'], 'recover-me')

    def test_prompt_is_not_interpreted_as_powershell_parameters(self):
        prompt = '-model "changed"; café $HOME'
        with patch('app.subprocess.run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, 'ok', '')
            app.run_powershell(app.PROMPT_SCRIPT, ['192.0.2.1', 'test-model', prompt])
        self.assertNotIn(prompt, run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs['env']['OLLAMASHADE_PROMPT'], prompt)

    def test_delete_preserves_state_on_failure_or_invalid_ack(self):
        for response in [None, '{}', 'not-json']:
            config = dict(self.config, active=True, instance_id='keep', ip_address='1.2.3.4')
            with patch('app.run_powershell', return_value=response):
                app.clear_instance(config)
            self.assertEqual(config['instance_id'], 'keep')

    def test_delete_clears_state_after_acknowledgement(self):
        config = dict(self.config, active=True, instance_id='remove', ip_address='1.2.3.4')
        with patch('app.run_powershell', return_value='{"deleted":true}'):
            app.clear_instance(config)
        self.assertIsNone(app.load_config()['instance_id'])
        self.assertFalse(config['active'])


@unittest.skipUnless(shutil.which('powershell'), 'Windows PowerShell required')
class ScriptTests(unittest.TestCase):
    def run_scenario(self, scenario, script='initialise.ps1'):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'config').mkdir()
            (root / 'test-key').write_text('fake-key')
            config = dict(api_key='test-key', model='test-model', active=False,
                          instance_id=None, ip_address=None, ssh_key_id='key-id',
                          ssh_private_key=str(root / 'test-key'))
            (root / 'config/config.json').write_text(json.dumps(config))
            for source in ['initialise.ps1', 'clear.ps1', 'prompt.ps1', 'transport.ps1']:
                shutil.copy(app.BASE_DIR / source, root / source)
            shutil.copy(app.BASE_DIR / 'tests/mock_api.ps1', root / 'mock_api.ps1')
            result = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                     '-File', str(root / 'mock_api.ps1'), scenario, script],
                                    capture_output=True, encoding='utf-8', timeout=30)
            state = json.loads((root / 'config/config.json').read_text(encoding='utf-8-sig'))
            events = (root / 'events.txt').read_text() if (root / 'events.txt').exists() else ''
            return result, state, events

    def test_start_selects_correct_type_and_uses_private_transport(self):
        result, state, events = self.run_scenario('success')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(state['active'])
        self.assertEqual(state['instance_id'], 'new-instance')
        self.assertEqual(state['ssh_port'], 2222)
        self.assertIn('create:correct-type:available-region', events)
        self.assertIn('private-binding', events)

    def test_model_failure_deletes_instance(self):
        result, state, events = self.run_scenario('pull-failure')
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(state['instance_id'])
        self.assertIn('delete', events)

    def test_cleanup_failure_preserves_recovery_id(self):
        result, state, events = self.run_scenario('cleanup-failure')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(state['instance_id'], 'new-instance')
        self.assertFalse(state['active'])

    def test_no_capacity_does_not_create(self):
        result, state, events = self.run_scenario('no-capacity')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('create:', events)

    def test_delete_api_error_exits_nonzero(self):
        result, state, events = self.run_scenario('delete-failure', 'clear.ps1')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('"deleted":true', result.stdout)

    def test_unicode_prompt_survives_remote_transport(self):
        result, state, events = self.run_scenario('success', 'prompt.ps1')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('unicode-payload', events)
        self.assertIn('Hello', result.stdout)


if __name__ == '__main__':
    unittest.main()
