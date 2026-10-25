import json
import os
import subprocess
import sys
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "config.json"

INITIALISE_SCRIPT = BASE_DIR / "initialise.ps1"
PROMPT_SCRIPT = BASE_DIR / "prompt.ps1"
CLEAR_SCRIPT = BASE_DIR / "clear.ps1"


# ============================================================
# CONFIGURATION
# ============================================================

def load_config():
    """Load configuration from config/config.json."""

    if not CONFIG_FILE.exists():
        print("\nConfig file not found.")
        print(f"Expected: {CONFIG_FILE}")
        print("\nCreate config/config.json before running OllamaShadeform.")
        sys.exit(1)

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8-sig") as file:
            config = json.load(file)
        if not isinstance(config, dict):
            raise ValueError("Configuration must be a JSON object.")
        for key in ("api_key", "model"):
            if not isinstance(config.get(key), str) or not config[key].strip():
                raise ValueError(f"Set a non-empty {key} in config.json.")
        if config["api_key"] == "PUT_YOUR_SHADEFORM_API_KEY_HERE":
            raise ValueError("Replace the example API key in config.json.")
        if type(config.get("active", False)) is not bool:
            raise ValueError("active must be true or false.")
        if config.get("active") and not (config.get("instance_id") and config.get("ip_address")):
            raise ValueError("An active instance needs instance_id and ip_address.")
        return config

    except json.JSONDecodeError:
        print("\nError: config.json contains invalid JSON.")
        sys.exit(1)
    except (OSError, ValueError) as error:
        print(f"\nCould not load config: {error}")
        sys.exit(1)


def save_config(config):
    """Save configuration back to config/config.json."""

    CONFIG_DIR.mkdir(exist_ok=True)

    temporary = CONFIG_FILE.with_suffix(".tmp")
    with open(temporary, "w", encoding="utf-8") as file:
        json.dump(config, file, indent=4)
    temporary.replace(CONFIG_FILE)


# ============================================================
# POWERSHELL
# ============================================================

def run_powershell(script, arguments=None):
    """
    Run a PowerShell script and return its output.

    arguments should be a list of strings.
    """

    if arguments is None:
        arguments = []

    environment = os.environ.copy()
    # Keep credentials off the child process command line.
    if script in (INITIALISE_SCRIPT, CLEAR_SCRIPT) and arguments:
        environment["SHADEFORM_API_KEY"] = arguments[0]
        arguments = arguments[1:]
    elif script == PROMPT_SCRIPT and len(arguments) == 3:
        environment["OLLAMASHADE_PROMPT"] = arguments[2]
        arguments = arguments[:2]
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        *arguments
    ]

    process = None
    try:
        if script in (INITIALISE_SCRIPT, PROMPT_SCRIPT):
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=environment,
            )
            lines = []
            if script == PROMPT_SCRIPT:
                while True:
                    chunk = process.stdout.read(1)
                    if not chunk:
                        break
                    lines.append(chunk)
                    print(chunk, end="", flush=True)
                process.stdout.close()
                if process.wait() != 0:
                    return None
                return "".join(lines).strip()
            for line in process.stdout:
                lines.append(line)
                try:
                    data = json.loads(line)
                except ValueError:
                    data = None
                if not (isinstance(data, dict) and "instance_id" in data):
                    print(line, end="", flush=True)
            process.stdout.close()
            if process.wait() != 0:
                print("\nPowerShell script failed.")
                return None
            return "".join(lines).strip()

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment
        )

    except FileNotFoundError:
        print("\nPowerShell could not be found.")
        print("OllamaShadeform currently requires PowerShell on Windows.")
        return None
    except KeyboardInterrupt:
        if process is not None:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
            )
            process.wait()
            process.stdout.close()
        if script == PROMPT_SCRIPT:
            print("\nResponse cancelled. Your instance is still running.")
        else:
            print("\nOperation interrupted. Check the Shadeform dashboard for running instances.")
        return None

    if result.returncode != 0:
        print("\nPowerShell script failed.")
        
        if result.stdout:
            print(result.stdout.strip())
        if result.stderr:
            print(result.stderr.strip())

        return None

    return result.stdout.strip()


# ============================================================
# INITIALISE
# ============================================================

def initialise(config):
    """Start the Shadeform instance and Ollama."""

    print("\nStarting OllamaShadeform...")
    print("Creating Shadeform instance and starting Ollama.")
    print("This may take several minutes.\n")

    output = run_powershell(
        INITIALISE_SCRIPT,
        [
            config["api_key"],
            config["model"]
        ]
    )

    if output is None:
        # The startup script checkpoints recovery details as soon as creation succeeds.
        config.update(load_config())
        return False

    try:
        # The final line is the structured JSON returned by
        # initialise.ps1.
        json_line = output.splitlines()[-1]

        data = json.loads(json_line)
        config["instance_id"] = data["instance_id"]
        config["ip_address"] = data["ip_address"]
        config["model"] = data["model"]
        config["active"] = data["active"]
        # Keep the SSH details written by the startup script.
        config.update(load_config())

    except (json.JSONDecodeError, KeyError, IndexError, TypeError, OSError) as error:

        print("\nCould not read instance information.")
        print(f"Error: {error}")
        return False

    print("\nOllamaShadeform is ready.")
    return True

# ============================================================
# PROMPT
# ============================================================

def prompt_model(config):
    """Send user prompts to the running Ollama model."""

    if not config.get("active"):
        print("\nNo active AI instance.")
        print("Use 'Start AI' first.")
        return

    print("\n========================================")
    print("OLLAMASHADEFORM CHAT".center(40))
    print("========================================")
    print("Type 'exit' to return to the main menu.\n")

    while True:

        try:
            user_prompt = input("You: ").strip()

        except (KeyboardInterrupt, EOFError):
            print("\n")
            return

        if not user_prompt:
            continue

        if user_prompt.lower() in {"exit", "quit", "/exit"}:
            print()
            return

        print("\nWaiting for the model; the first reply can take several minutes to load.", flush=True)
        print("AI: ", end="", flush=True)
        output = run_powershell(
            PROMPT_SCRIPT,
            [
                config["ip_address"],
                config["model"],
                user_prompt
            ]
        )

        if output is None:
            print("Failed to get a response from the model.\n")
            continue

        print("\n")


# ============================================================
# CLEAR
# ============================================================

def clear_instance(config):
    """Delete the active Shadeform instance."""

    if not config.get("active") and not config.get("instance_id"):
        print("\nThere is no active instance to delete.")
        return

    print("\nDeleting Shadeform instance...")

    output = run_powershell(
        CLEAR_SCRIPT,
        [
            config["api_key"],
            config.get("instance_id", "")
        ]
    )

    if output is None:
        return

    print(output)

    try:
        if json.loads(output.splitlines()[-1]).get("deleted") is not True:
            raise ValueError("Deletion was not acknowledged.")
    except (ValueError, IndexError, AttributeError) as error:
        print(f"Could not confirm deletion: {error}")
        return

    # Clear runtime information only after a successful API response.
    config["instance_id"] = None
    config["ip_address"] = None
    config["active"] = False

    try:
        save_config(config)
    except OSError as error:
        print(f"Instance deleted, but local config could not be saved: {error}")

    print("\nInstance cleared.")


# ============================================================
# STATUS
# ============================================================

def show_status(config):

    print("\n========================================")
    print("OLLAMASHADEFORM STATUS".center(40))
    print("========================================")

    if config.get("active"):
        print("Status:       ACTIVE")
        print(f"Instance ID:  {config.get('instance_id', 'Unknown')}")
        print(f"IP address:   {config.get('ip_address', 'Unknown')}")
        print(f"Model:        {config.get('model', 'Unknown')}")
    else:
        if config.get("instance_id"):
            print("Saved status: STARTUP INCOMPLETE; instance may still incur charges")
            print(f"Instance ID:  {config['instance_id']}")
            print("Use Delete instance or check the Shadeform dashboard.")
        else:
            print("Saved status: NOT RUNNING")

    print()


# ============================================================
# MAIN MENU
# ============================================================

def main():

    config = load_config()

    while True:

        print("========================================")
        print("OLLAMASHADEFORM".center(40))
        print("========================================")

        if config.get("active"):
            print("Status: ACTIVE")
            print(f"Model:  {config.get('model', 'Unknown')}")
        else:
            if config.get("instance_id"):
                print("Status: STARTUP INCOMPLETE; delete the recorded instance")
            else:
                print("Status: NOT RUNNING")

        print("----------------------------------------")
        print("1. Start AI")
        print("2. Chat with AI")
        print("3. Check status")
        print("4. Delete instance")
        print("5. Exit")
        print("========================================")

        try:
            choice = input("Select an option: ").strip()

        except (KeyboardInterrupt, EOFError):
            print("\n")
            break

        if choice == "1":

            if config.get("active") or config.get("instance_id"):
                print("\nAn instance is already recorded. Delete it before starting another.")
                continue

            initialise(config)

        elif choice == "2":

            prompt_model(config)

        elif choice == "3":

            show_status(config)

        elif choice == "4":

            clear_instance(config)

        elif choice == "5":

            print("\nExiting OllamaShadeform.")
            if config.get("instance_id"):
                print("Your instance is still running and may incur charges. Use Delete instance to stop it.")
            break

        else:

            print("\nInvalid option.")

    sys.exit(0)


# ============================================================
# PROGRAM ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
