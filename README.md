# OllamaShade

OllamaShade is a Windows command-line launcher for running an [Ollama](https://ollama.com/) model on an on-demand [Shadeform](https://www.shadeform.ai/) GPU instance.

It can create an A6000-backed instance, install the requested model, provide an interactive chat session, report its status, and delete the instance when you are finished.

## Requirements

- Windows PowerShell
- Python 3
- A Shadeform API key

## Setup

1. Copy `config/config.example.json` to `config/config.json`.
2. Set `api_key` to your Shadeform API key and choose an Ollama model (for example, `llama3.1:8b`).
3. Run:

   ```powershell
   python app.py
   ```

`config/config.json` is excluded from Git because it contains your API key and runtime instance details.

## Commands

The interactive menu lets you:

- Start an OllamaShade instance.
- Chat with the selected model.
- View the active instance status.
- Delete the active instance and clear local runtime details.

## Cost and security

Creating an instance incurs Shadeform usage charges. Delete the instance when it is no longer needed. Do not commit or share your `config/config.json` file.
