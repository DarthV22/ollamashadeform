import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
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

    def test_startup_streams_progress_before_process_finishes(self):
        output = io.StringIO()

        def lines():
            yield 'Waiting for SSH...\n'
            self.assertIn('Waiting for SSH...', output.getvalue())
            yield '{"instance_id":"new-instance","active":true}\n'

        with patch('app.subprocess.Popen') as popen, contextlib.redirect_stdout(output):
            process = popen.return_value
            process.stdout = unittest.mock.MagicMock()
            process.stdout.__iter__.side_effect = lines
            process.wait.return_value = 0
            result = app.run_powershell(app.INITIALISE_SCRIPT, ['secret', 'test-model'])
        self.assertEqual(json.loads(result.splitlines()[-1])['instance_id'], 'new-instance')
        self.assertNotIn('new-instance', output.getvalue())
        self.assertNotIn('secret', popen.call_args.args[0])
        self.assertEqual(popen.call_args.kwargs['env']['SHADEFORM_API_KEY'], 'secret')
        self.assertEqual(popen.call_args.kwargs['stdin'], subprocess.DEVNULL)
        process.stdout.close.assert_called_once()

    def test_startup_streams_errors_and_returns_failure(self):
        with patch('app.subprocess.Popen') as popen:
            process = popen.return_value
            process.stdout = io.StringIO('Startup failed: SSH unavailable\n')
            process.wait.return_value = 1
            self.assertIsNone(app.run_powershell(app.INITIALISE_SCRIPT, ['secret', 'model']))

    def test_failed_start_reloads_recovery_id(self):
        self.config_file.write_text(json.dumps(dict(self.config, instance_id='recover-me')))
        with patch('app.run_powershell', return_value=None):
            self.assertFalse(app.initialise(self.config))
        self.assertEqual(self.config['instance_id'], 'recover-me')

    def test_prompt_is_not_interpreted_as_powershell_parameters(self):
        prompt = '-model "changed"; café $HOME'
        with patch('app.subprocess.Popen') as run:
            run.return_value.stdout = io.StringIO('Hello')
            run.return_value.wait.return_value = 0
            app.run_powershell(app.PROMPT_SCRIPT, ['192.0.2.1', 'test-model', prompt])
        self.assertNotIn(prompt, run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs['env']['OLLAMASHADE_PROMPT'], prompt)

    def test_chat_displays_partial_reply_before_completion(self):
        output = io.StringIO()

        def read_chunk(size):
            self.assertEqual(size, 1)
            if not output.getvalue():
                return 'H'
            if output.getvalue() == 'H':
                return 'i'
            return ''

        with patch('app.subprocess.Popen') as popen, contextlib.redirect_stdout(output):
            process = popen.return_value
            process.stdout.read.side_effect = read_chunk
            process.wait.return_value = 0
            result = app.run_powershell(app.PROMPT_SCRIPT, ['192.0.2.1', 'model', 'hello'])
        self.assertEqual(result, 'Hi')
        self.assertEqual(output.getvalue(), 'Hi')

    def test_chat_cancellation_terminates_local_process_tree(self):
        with patch('app.subprocess.Popen') as popen, patch('app.subprocess.run') as run:
            process = popen.return_value
            process.pid = 123
            process.stdout.read.side_effect = KeyboardInterrupt
            self.assertIsNone(app.run_powershell(app.PROMPT_SCRIPT, ['ip', 'model', 'hello']))
        self.assertEqual(run.call_args.args[0], ['taskkill', '/PID', '123', '/T', '/F'])

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
    def test_setup_upgrades_old_config_without_overwriting_settings(self):
        with tempfile.TemporaryDirectory(prefix='ollamashade setup ') as directory:
            root = Path(directory)
            (root / 'config').mkdir()
            shutil.copy(app.BASE_DIR / 'setup.ps1', root / 'setup.ps1')
            shutil.copy(app.BASE_DIR / 'config/config.example.json', root / 'config/config.example.json')
            original = dict(api_key='keep-secret', model='custom-model', active=False,
                            instance_id='recover-me', ip_address=None,
                            custom={'nested': 'keep-me'}, ssh_key_id='keep-key-id')
            config_path = root / 'config/config.json'
            config_path.write_text(json.dumps(original), encoding='utf-8-sig')
            subprocess.run([sys._base_executable, '-m', 'venv', '--without-pip', str(root / '.venv')],
                           check=True, capture_output=True, timeout=30)
            command = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                       '-File', str(root / 'setup.ps1')]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            upgraded = json.loads(config_path.read_text(encoding='utf-8-sig'))
            for name, value in original.items():
                self.assertEqual(upgraded[name], value)
            self.assertIn('ssh_private_key', upgraded)
            before = config_path.read_bytes()
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(config_path.read_bytes(), before)

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

    def test_missing_ssh_key_fails_before_creation_with_clear_message(self):
        result, state, events = self.run_scenario('missing-ssh-key')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Set ssh_key_id', result.stderr)
        self.assertIn('No instance was created.', result.stderr)
        self.assertNotIn('create request timed out', result.stderr)
        self.assertNotIn('create:', events)
        self.assertIsNone(state['instance_id'])

    def test_delete_api_error_exits_nonzero(self):
        result, state, events = self.run_scenario('delete-failure', 'clear.ps1')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('"deleted":true', result.stdout)

    def test_unicode_prompt_survives_remote_transport(self):
        result, state, events = self.run_scenario('success', 'prompt.ps1')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('unicode-payload', events)
        self.assertIn('Hello', result.stdout)

    def test_chat_rejects_incomplete_stream(self):
        result, state, events = self.run_scenario('incomplete-stream', 'prompt.ps1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('incomplete response', result.stderr)

    def test_chat_reports_streamed_model_error(self):
        result, state, events = self.run_scenario('stream-error', 'prompt.ps1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('simulated model error', result.stderr)


if __name__ == '__main__':
    unittest.main()
