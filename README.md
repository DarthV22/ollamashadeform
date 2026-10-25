# OllamaShade

A small Windows command-line launcher for running an [Ollama](https://ollama.com/) model on an on-demand [Shadeform](https://www.shadeform.ai/) A6000 GPU instance. Start an instance, send prompts, view saved instance details, and delete it when finished. No Python packages are required.

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
Copy-Item config/config.example.json config/config.json
```

Edit `config/config.json`:

- `api_key`: your Shadeform API key.
- `model`: an Ollama model name, such as `llama3.1:8b`. Choose one that fits the GPU memory.
- `ssh_key_id`: the ID of your registered public key in Shadeform.
- `ssh_private_key`: the absolute local path to its matching private key. Use forward slashes in JSON paths, for example `C:/Users/Alex/.ssh/id_ed25519`.

Leave `instance_id`, `ip_address`, and `active` at their example values. Then run:

```powershell
py app.py
```

The menu provides Start AI, Chat with AI, Check status, Delete instance, and Exit. Chat sends independent prompts; it does not maintain conversation history. Status displays saved local details, rather than querying cloud health.

## Instance lifecycle and cost

Start selects the cheapest available on-demand A6000 instance type and an available region, creates the instance, waits up to 20 minutes for activation, waits for SSH/Ollama readiness, and downloads the model. Model downloads can take up to one hour. The price displayed is in cents per instance-hour as returned by Shadeform.

**Instances incur charges until deleted. Exiting the app does not delete the instance.** Use Delete instance when finished and confirm its deletion in the Shadeform dashboard. Keep only one copy of the app running against a configuration file.

The instance ID is saved immediately after creation. Failed startup attempts request deletion; if cleanup fails, the ID is retained for recovery. After an interrupted startup, restart the app and delete the recorded instance before creating another. If creation times out before an ID is returned, check the dashboard before retrying: the remote request may have succeeded. API deletion acceptance is not a guarantee that cloud teardown has finished.

## Security

Ollama is bound to `127.0.0.1:11434` on the GPU host. Requests travel through authenticated SSH and do not expose the Ollama HTTP API publicly. SSH uses `StrictHostKeyChecking=accept-new`: the first host key is trusted and later changes are rejected. For stricter verification, verify the host fingerprint through your provider and populate your SSH `known_hosts` file before connecting. If an IP is reused and the key changes, verify it before updating that entry.

`config/config.json`, temporary configuration files, private key files, and the historical `scrap/` directory are excluded from Git. Never share your configuration or private key. API credentials are passed to PowerShell through the child environment rather than command-line arguments.

## Troubleshooting

- **No capacity:** try again later; no instance is created.
- **SSH fails:** check the registered key, private key path, SSH agent, and provider network access. The instance's SSH username and port come from Shadeform.
- **Ollama never becomes ready:** check the launch logs and the remote Docker/GPU prerequisites. Startup attempts to delete the instance when it fails.
- **Deletion fails:** local recovery details remain intact. Retry or delete the instance directly in Shadeform.
- **Recorded instance already deleted manually:** confirm deletion in the dashboard, then reset `instance_id` and `ip_address` to `null` and `active` to `false` in your local config.

## Development checks

```powershell
py -m unittest discover -s tests -v
```

The tests exercise Python configuration handling and PowerShell startup, model download, SSH payload handling, deletion, and failure recovery with mocked APIs. They do not create billable cloud resources. GitHub Actions runs the suite on Windows. A live deployment still requires a funded Shadeform account and suitable provider capacity; mocked checks cannot verify a provider image or actual GPU provisioning.

API references: [create an instance](https://docs.shadeform.ai/api-reference/instances/instances-create), [instance types](https://docs.shadeform.ai/api-reference/instances/instances-types), and [instance information](https://docs.shadeform.ai/api-reference/instances/instances-info).

## License

MIT; see [LICENSE](LICENSE).
