import json
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
        print("\nCreate config/config.json before running OllamaShade.")
        sys.exit(1)

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as file:
            return json.load(file)

    except json.JSONDecodeError:
        print("\nError: config.json contains invalid JSON.")
        sys.exit(1)


def save_config(config):
    """Save configuration back to config/config.json."""

    CONFIG_DIR.mkdir(exist_ok=True)

    with open(CONFIG_FILE, "w", encoding="utf-8") as file:
        json.dump(config, file, indent=4)


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

    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        *arguments
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True
        )

    except FileNotFoundError:
        print("\nPowerShell could not be found.")
        print("Zircon currently requires PowerShell on Windows.")
        return None

    if result.returncode != 0:
        print("\nPowerShell script failed.")
        
        if result.stderr:
            print(result.stderr.strip())

        return None

    return result.stdout.strip()


# ============================================================
# INITIALISE
# ============================================================

def initialise(config):
    """Start the Shadeform instance and Ollama."""

    print("\nStarting OllamaShade...")
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
        return False

    print(output)

    try:
        # The final line is the structured JSON returned by
        # initialise.ps1.
        json_line = output.splitlines()[-1]

        data = json.loads(json_line)

        config["instance_id"] = data["instance_id"]
        config["ip_address"] = data["ip_address"]
        config["model"] = data["model"]
        config["active"] = data["active"]

        save_config(config)

    except (json.JSONDecodeError, KeyError, IndexError) as error:

        print("\nCould not read instance information.")
        print(f"Error: {error}")
        return False

    print("\nOllamaShade is ready.")
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
    print("             OLLAMASHADE CHAT")
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

        print(f"\nAI: {output}\n")


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

    # Clear runtime information.
    config["instance_id"] = None
    config["ip_address"] = None
    config["active"] = False

    save_config(config)

    print("\nInstance cleared.")


# ============================================================
# STATUS
# ============================================================

def show_status(config):

    print("\n========================================")
    print("             OLLAMASHADE STATUS")
    print("========================================")

    if config.get("active"):
        print("Status:       ACTIVE")
        print(f"Instance ID:  {config.get('instance_id', 'Unknown')}")
        print(f"IP address:   {config.get('ip_address', 'Unknown')}")
        print(f"Model:        {config.get('model', 'Unknown')}")
    else:
        print("Status:       NOT RUNNING")

    print()


# ============================================================
# MAIN MENU
# ============================================================

def main():

    config = load_config()

    while True:

        print("========================================")
        print("              OLLAMASHADE")
        print("========================================")

        if config.get("active"):
            print("Status: ACTIVE")
            print(f"Model:  {config.get('model', 'Unknown')}")
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

            if config.get("active"):
                print("\nAn instance is already active.")
                continue

            initialise(config)

        elif choice == "2":

            prompt_model(config)

        elif choice == "3":

            show_status(config)

        elif choice == "4":

            clear_instance(config)

        elif choice == "5":

            print("\nExiting OllamaShade.")
            break

        else:

            print("\nInvalid option.")

    sys.exit(0)


# ============================================================
# PROGRAM ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
