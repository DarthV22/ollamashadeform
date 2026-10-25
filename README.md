# OllamaShadeform

A small Windows command-line launcher for running an [Ollama](https://ollama.com/) model on an on-demand [Shadeform](https://www.shadeform.ai/) A6000 GPU instance. Start an instance, send prompts, view saved instance details, and delete it when finished. The project runs in its own Python virtual environment (`.venv`) and uses only Python's standard library.

## Requirements

- Windows 10/11 with Windows PowerShell 5.1 and Python 3.10 or later.
- Windows OpenSSH Client (`ssh -V`). Enable it in Windows Optional Features if missing.
- A funded Shadeform account, an API key, and an SSH public key registered in Shadeform.
- The matching private key on your computer. The client uses noninteractive SSH: use a key available without a passphrase prompt, or load your passphrase-protected key in `ssh-agent` first.
- Available A6000 capacity with Docker, NVIDIA Container Toolkit, `curl`, and `base64` on the remote host. The launch script uses `sudo docker` without an interactive password prompt. Provider images must support these tools.

## Setup

```powershell
git clone https://github.com/DarthV22/ollamashadeform.git
cd ollamashadeform
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

Setup creates `.venv` and copies the example configuration to `config/config.json` if it does not already exist. On later runs it adds any missing fields from the example while preserving existing values, credentials, and instance recovery details. Review added placeholder values before starting AI. Each person who clones the repository creates their own environment locally. There are no third-party Python dependencies to install.

Edit `config/config.json`:

- `api_key`: your Shadeform API key.
- `model`: an Ollama model name, such as `llama3.1:8b`. Choose one that fits the GPU memory.
- `ssh_key_id`: the ID of your registered public key in Shadeform.
- `ssh_private_key`: the absolute local path to its matching private key. Use forward slashes in JSON paths, for example `C:/Users/Alex/.ssh/id_ed25519`.

Edit your actual settings in `config/config.json`; `config/config.example.json` is the shared template. `ssh_key_id` is Shadeform's ID for a registered public key, not the public key text or its fingerprint. `ssh_private_key` points to the matching private key file without the `.pub` extension. Register only the public key with Shadeform when using a locally generated key, and keep the private file outside this repository. If the private key has a passphrase, start Windows `ssh-agent` and load it with `ssh-add` before starting AI: the app uses noninteractive SSH and cannot ask for a passphrase. Restart the app after changing configuration because its menu keeps settings in memory.

If you use a Shadeform managed key, download its matching private key from your account and save it in your Windows user profile's `.ssh` directory with file access restricted to your account. Set `ssh_private_key` to that file's absolute path. The key ID alone cannot authenticate SSH. Shadeform documents [SSH key details](https://docs.shadeform.ai/api-reference/sshkeys/sshkeys-info) and [registering your own public key](https://docs.shadeform.ai/api-reference/sshkeys/sshkeys-add).

Leave `instance_id`, `ip_address`, and `active` at their example values. Then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1
```

The launcher always uses `.venv\Scripts\python.exe`, so you do not need to activate the environment first. These commands apply the execution policy only to that PowerShell process.

If your PowerShell execution policy already allows local scripts, you can use `./setup.ps1` and `./run.ps1` directly. To activate the environment manually in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python app.py
deactivate
```

Activation only changes which Python your current terminal uses. You can also run `.\.venv\Scripts\python.exe app.py` directly. The virtual environment isolates Python packages; PowerShell and OpenSSH are still required on Windows.

The menu provides Start AI, Chat with AI, Check status, Delete instance, and Exit. Chat displays replies as they are generated and uses an 8192-token context window. The first reply can take several minutes while the model loads; text appears once generation begins. Later replies are usually faster while the model remains loaded. Ctrl+C cancels the current reply and leaves the instance running. Chat sends independent prompts; it does not maintain conversation history. Status displays saved local details, rather than querying cloud health.

## Instance lifecycle and cost

Start selects the cheapest available on-demand A6000 instance type and an available region, creates the instance, waits up to 20 minutes for activation, waits for SSH/Ollama readiness, and downloads the model. Model downloads can take up to one hour. The price displayed is in cents per instance-hour as returned by Shadeform.

Startup displays progress and SSH readiness errors as they happen. An instance marked active in Shadeform may still be preparing Docker, Ollama, or the model; the app reports ready only after those steps finish. SSH commands disconnect from keyboard input so background readiness checks cannot wait on the menu's console input.

**Instances incur charges until deleted. Exiting the app does not delete the instance.** Use Delete instance when finished and confirm its deletion in the Shadeform dashboard. Keep only one copy of the app running against a configuration file.

The instance ID is saved immediately after creation. Failed startup attempts request deletion; if cleanup fails, the ID is retained for recovery. After an interrupted startup, restart the app and delete the recorded instance before creating another. If creation times out before an ID is returned, check the dashboard before retrying: the remote request may have succeeded. API deletion acceptance is not a guarantee that cloud teardown has finished.

## Security

Ollama is bound to `127.0.0.1:11434` on the GPU host. Requests travel through authenticated SSH and do not expose the Ollama HTTP API publicly. SSH uses `StrictHostKeyChecking=accept-new`: the first host key is trusted and later changes are rejected. For stricter verification, verify the host fingerprint through your provider and populate your SSH `known_hosts` file before connecting. If an IP is reused and the key changes, verify it before updating that entry.

`config/config.json`, temporary configuration files, private key files, and the historical `scrap/` directory are excluded from Git. Never share your configuration or private key. API credentials are passed to PowerShell through the child environment rather than command-line arguments.

## Troubleshooting

- **No capacity:** try again later; no instance is created.
- **Name already in use after deletion:** cloud teardown can take time after the deletion request is accepted. Confirm the old instance has disappeared in Shadeform before retrying Start AI.
- **Chat initially shows no text:** allow time for the model to load. Reply streaming starts when generation begins. Repeatedly cancelling requests can prevent the first reply from completing.
- **Python is missing or setup cannot find it:** install Python 3.10 or later with its launcher, reopen PowerShell, and rerun setup. To choose a specific installation, use `powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -Python "C:\path\to\python.exe"`.
- **Environment stopped working after moving the project or upgrading Python:** close terminals using it, remove only the project's `.venv` directory, and rerun setup. Virtual environments should be recreated locally rather than copied between computers. Your settings remain in `config/config.json`.
- **Activation is blocked by execution policy:** use the `powershell ... -File .\run.ps1` command above, which does not require activation.
- **SSH fails:** check the registered key, private key path, SSH agent, and provider network access. The instance's SSH username and port come from Shadeform.
- **Ollama never becomes ready:** check the launch logs and the remote Docker/GPU prerequisites. Startup attempts to delete the instance when it fails.
- **Deletion fails:** local recovery details remain intact. Retry or delete the instance directly in Shadeform.
- **Recorded instance already deleted manually:** confirm deletion in the dashboard, then reset `instance_id` and `ip_address` to `null` and `active` to `false` in your local config.

## Development checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests exercise Python configuration handling and PowerShell startup, model download, SSH payload handling, deletion, and failure recovery with mocked APIs. They do not create billable cloud resources. GitHub Actions runs the suite on Windows. A live deployment still requires a funded Shadeform account and suitable provider capacity; mocked checks cannot verify a provider image or actual GPU provisioning.

API references: [create an instance](https://docs.shadeform.ai/api-reference/instances/instances-create), [instance types](https://docs.shadeform.ai/api-reference/instances/instances-types), and [instance information](https://docs.shadeform.ai/api-reference/instances/instances-info).

## License

MIT; see [LICENSE](LICENSE).
