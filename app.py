#!/usr/bin/env python3

import os
import sys
import signal
import subprocess
import threading
import time
import shutil
import json
import asyncio
import pty
import select
import struct
import fcntl
import termios
import logging

from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn


# ============================================================
# CONFIGURATION
# ============================================================

APP_DIR = Path("/app")
DATA_DIR = Path("/data")

HERMES_HOME = DATA_DIR / "hermes"
HERMES_DIR = HERMES_HOME / "hermes-agent"

INSTALLER = APP_DIR / "install.sh"

PORT = int(os.environ.get("PORT", "7860"))

SCREEN_NAME = "hermes"

HERMES_EXECUTABLE = HERMES_DIR / "venv" / "bin" / "hermes"

# Processes started by this app.
CHILD_PROCESSES = []

shutdown_event = threading.Event()


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(f"[app.py] {message}", flush=True)


def log_error(message):
    print(f"[app.py] ERROR: {message}", flush=True)


def log_warning(message):
    print(f"[app.py] WARNING: {message}", flush=True)


# ============================================================
# ENVIRONMENT
# ============================================================

def build_environment():
    env = os.environ.copy()

    env["HERMES_HOME"] = str(HERMES_HOME)

    hermes_bin = HERMES_HOME / "bin"
    node_bin = HERMES_HOME / "node" / "bin"
    venv_bin = HERMES_DIR / "venv" / "bin"

    paths = [
        str(hermes_bin),
        str(node_bin),
        str(venv_bin),
        "/root/.local/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
    ]

    old_path = env.get("PATH", "")

    env["PATH"] = ":".join(paths) + ":" + old_path

    env["TERM"] = "xterm-256color"
    env["COLORTERM"] = "truecolor"

    # Prevent interactive programs from trying to use
    # terminal features that don't work in the installer.
    env["DEBIAN_FRONTEND"] = "noninteractive"

    # Hermes setup/other prompts fall back to defaults instead of blocking
    # (see hermes_cli/setup.py is_noninteractive()).
    env["HERMES_NONINTERACTIVE"] = "1"

    return env


# ============================================================
# COMMAND HELPERS
# ============================================================

def command_exists(command):
    return shutil.which(command, path=build_environment()["PATH"]) is not None


def run_command(command, timeout=None, cwd=None, env=None):
    if env is None:
        env = build_environment()

    log(f"Running: {command}")

    try:
        process = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )

        if process.stdout:
            print(process.stdout, end="", flush=True)

        return process.returncode

    except subprocess.TimeoutExpired:
        log_error(f"Command timed out: {command}")
        return 124

    except Exception as exc:
        log_error(f"Command failed: {exc}")
        return 1


# ============================================================
# HERMES DETECTION
# ============================================================

def find_hermes():
    """
    Find Hermes executable.

    Priority:
      1. /data/hermes/hermes-agent/venv/bin/hermes
      2. PATH
    """

    candidates = [
        HERMES_EXECUTABLE,

        HERMES_DIR / "venv" / "bin" / "hermes",

        HERMES_HOME / "bin" / "hermes",

        Path("/root/.local/bin/hermes"),
    ]

    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate

    env = build_environment()

    found = shutil.which("hermes", path=env["PATH"])

    if found:
        return Path(found)

    return None


# ============================================================
# INSTALLATION
# ============================================================

def hermes_is_installed():
    executable = find_hermes()

    if executable:
        log(f"Hermes found: {executable}")
        return True

    log("Hermes not found")
    return False


def install_hermes():
    """
    Run the existing Hermes installer from inside app.py.

    The installer itself becomes a child process of app.py.
    """

    if not INSTALLER.exists():
        log_error(f"Installer not found: {INSTALLER}")
        return False

    log("Hermes is not installed.")
    log("Starting Hermes installer...")
    log(f"Installer command: /bin/bash {INSTALLER}")

    env = build_environment()

    command = [
        "/bin/bash",
        str(INSTALLER),
    ]

    try:
        process = subprocess.Popen(
            command,
            cwd=str(APP_DIR),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=None,
            stderr=None,
        )

        CHILD_PROCESSES.append(process)

        log(f"Starting process: hermes-installer")
        log(f"PID: {process.pid}")

        return_code = process.wait()

        try:
            CHILD_PROCESSES.remove(process)
        except ValueError:
            pass

        if return_code != 0:
            log_error(
                f"Hermes installer exited with code {return_code}"
            )
            return False

        log("Hermes installer completed successfully.")

        time.sleep(1)

        executable = find_hermes()

        if executable:
            log(f"Hermes executable: {executable}")
            return True

        log_error(
            "Installer completed but Hermes executable was not found."
        )

        return False

    except Exception as exc:
        log_error(f"Installer failed: {exc}")
        return False


# ============================================================
# SCREEN
# ============================================================

def screen_available():
    return shutil.which("screen") is not None


def screen_exists():
    """
    Check whether our Hermes screen session exists.
    """

    if not screen_available():
        return False

    env = build_environment()

    result = subprocess.run(
        [
            "screen",
            "-S",
            SCREEN_NAME,
            "-Q",
            "select",
            ".",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return result.returncode == 0


def list_screens():
    env = build_environment()

    try:
        result = subprocess.run(
            ["screen", "-ls"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        return result.stdout

    except Exception as exc:
        return str(exc)


def create_hermes_screen(hermes_executable):
    """
    Create detached screen and launch Hermes inside it.

    Important:
    screen is spawned by app.py.
    """

    if not screen_available():
        log_error("screen command is not installed.")
        return False

    if screen_exists():
        log("Hermes screen session already exists.")
        return True

    env = build_environment()

    log("screen -ls output:")
    print(list_screens(), flush=True)

    log(f"Creating screen session '{SCREEN_NAME}'...")

    # Use bash as the screen shell.
    #
    # Hermes is executed directly inside this shell.
    #
    # When Hermes exits, keep the terminal alive so the user can
    # inspect the result instead of screen immediately disappearing.
    shell_command = (
        f'export HERMES_HOME="{HERMES_HOME}"; '
        f'export PATH="{HERMES_HOME}/bin:'
        f'{HERMES_HOME}/node/bin:'
        f'{HERMES_DIR}/venv/bin:'
        f'/root/.local/bin:'
        f'/usr/local/bin:'
        f'/usr/bin:'
        f'/bin:$PATH"; '
        f'export TERM=xterm-256color; '
        f'export HERMES_NONINTERACTIVE=1; '
        f'export DEBIAN_FRONTEND=noninteractive; '
        f'echo ""; '
        f'echo "========================================"; '
        f'echo " Hermes Agent"; '
        f'echo "========================================"; '
        f'echo ""; '
        f'echo "Starting Hermes..."; '
        f'echo ""; '
        f'exec "{hermes_executable.parent.parent}/python" -m hermes'
    )

    log("Screen command:")
    log(shell_command)

    try:
        process = subprocess.Popen(
            [
                "screen",
                "-dmS",
                SCREEN_NAME,
                "bash",
                "-lc",
                shell_command,
            ],
            cwd=str(HERMES_HOME),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

        CHILD_PROCESSES.append(process)

        log(f"screen process PID: {process.pid}")

        # Give screen a moment to create its socket.
        time.sleep(1)

        # screen -dm returns after creating the detached session.
        #
        # We don't need to keep the Popen object around as the actual
        # Hermes process is now owned by screen.
        try:
            CHILD_PROCESSES.remove(process)
        except ValueError:
            pass

        time.sleep(1)

        if screen_exists():
            log(
                f"SUCCESS: screen session '{SCREEN_NAME}' "
                f"created successfully."
            )

            log("Current screen sessions:")
            print(list_screens(), flush=True)

            return True

        log_error("screen process started but session was not found.")

        return False

    except Exception as exc:
        log_error(f"Failed to create screen: {exc}")
        return False


def ensure_hermes_screen():
    executable = find_hermes()

    if not executable:
        log_error("Cannot start screen: Hermes executable not found.")
        return False

    log(f"Hermes executable: {executable}")

    if screen_exists():
        log(
            f"Screen session '{SCREEN_NAME}' "
            f"is already running."
        )
        return True

    return create_hermes_screen(executable)


# ============================================================
# SCREEN COMMAND
# ============================================================

def attach_command():
    """
    Command used by the web terminal.

    User can manually execute:

        screen -r hermes

    This function is only here for diagnostics.
    """

    return [
        "screen",
        "-r",
        SCREEN_NAME,
    ]


# ============================================================
# WEB TERMINAL HTML
# ============================================================

HTML = (Path(__file__).parent / "templates" / "terminal.html").read_text(encoding="utf-8")

# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="Hermes Docker Terminal"
)


@app.get("/")
async def index():

    return HTMLResponse(
        HTML
    )


@app.get("/health")
async def health():

    return {

        "status": "ok",

        "hermes_installed":
            hermes_is_installed(),

        "screen_running":
            screen_exists(),

        "hermes_home":
            str(HERMES_HOME),

        "hermes_directory":
            str(HERMES_DIR),

    }


@app.get("/status")
async def status():

    executable = find_hermes()

    return {

        "hermes": (
            str(executable)
            if executable
            else None
        ),

        "screen":
            screen_exists(),

        "screen_name":
            SCREEN_NAME,

        "screens":
            list_screens(),

    }


# ============================================================
# REAL PTY WEB TERMINAL
# ============================================================

def spawn_shell():

    """
    Create a real PTY.

    The shell is a child of app.py.

    This is NOT subprocess.PIPE.

    It behaves like a real Linux terminal.
    """

    master_fd, slave_fd = pty.openpty()

    env = build_environment()

    env["HOME"] = "/root"
    env["SHELL"] = "/bin/bash"
    env["TERM"] = "xterm-256color"
    
    # Create temporary bashrc to override PS1
    bashrc_override = "/root/.bashrc_webterm"
    with open(bashrc_override, "w") as f:
        f.write(
            "export PS1='\\u@\\h:\\w\\$ '\n"
            "export PS2='> '\n"
            "export TERM=xterm-256color\n"
        )
    
    # Set terminal size before spawning
    set_pty_size(master_fd, 24, 80)
    
    # Use -c to setup environment, then exec interactive bash
    startup_script = "PS1='\\u@\\h:\\w\\$ '; PS2='> '; TERM=xterm-256color; exec /bin/bash -i"
    
    process = subprocess.Popen(
        [
            "/bin/bash",
            "-i",
            "-c",
            startup_script,
        ],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=env,
        cwd=str(HERMES_HOME),
        start_new_session=True,
    )
    
    os.close(slave_fd)
    
    CHILD_PROCESSES.append(process)
    
    return process, master_fd


def set_pty_size(fd, rows, cols):

    size = struct.pack(
        "HHHH",
        rows,
        cols,
        0,
        0
    )

    fcntl.ioctl(
        fd,
        termios.TIOCSWINSZ,
        size
    )


async def pty_reader(websocket, master_fd):
    """
    Read terminal output without blocking FastAPI.
    Uses non-blocking I/O for real-time terminal output.
    """
    # Set master_fd to non-blocking mode
    fl = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

    while True:
        if shutdown_event.is_set():
            break

        try:
            # Non-blocking read — returns immediately
            data = os.read(master_fd, 8192)

            if not data:
                # EOF — shell exited
                await websocket.send_bytes(b"\r\n[SHELL_EXIT]\r\n")
                break

            # Send raw binary data to websocket (no JSON encoding)
            await websocket.send_bytes(data)

        except BlockingIOError:
            # No data available — yield to event loop
            await asyncio.sleep(0.01)

        except OSError as exc:
            if exc.errno == 11:  # EAGAIN
                await asyncio.sleep(0.01)
            else:
                break

        except asyncio.CancelledError:
            break

        except Exception as exc:
            log_error(f"PTY reader error: {exc}")
            break



@app.websocket("/ws/terminal")
async def terminal_websocket(websocket: WebSocket):

    await websocket.accept()

    process = None
    master_fd = None

    try:

        log(
            "Web terminal client connected."
        )

        process, master_fd = spawn_shell()

        log(
            f"Terminal shell PID: {process.pid}"
        )

        reader_task = asyncio.create_task(

            pty_reader(
                websocket,
                master_fd
            )

        )

        # Allow PTY reader + bash to initialize
        await asyncio.sleep(0.5)
        
        # Trigger bash prompt by sending a newline
        os.write(master_fd, b"\n")
        
        # Brief pause for prompt to render
        await asyncio.sleep(0.3)

        while True:
            message = await websocket.receive_text()

            try:

                payload = json.loads(
                    message
                )

            except json.JSONDecodeError:

                payload = {

                    "type": "input",

                    "data": message

                }


            message_type = payload.get(
                "type"
            )


            if message_type == "input":

                data = payload.get(
                    "data",
                    ""
                )

                if data:

                    os.write(
                        master_fd,
                        data.encode(
                            "utf-8",
                            errors="replace"
                        )
                    )


            elif message_type == "resize":

                rows = int(
                    payload.get(
                        "rows",
                        24
                    )
                )

                cols = int(
                    payload.get(
                        "cols",
                        80
                    )
                )

                set_pty_size(
                    master_fd,
                    rows,
                    cols
                )


    except WebSocketDisconnect:

        log(
            "Web terminal client disconnected."
        )

    except Exception as exc:

        log_error(
            f"Web terminal error: {exc}"
        )

    finally:

        if master_fd is not None:

            try:
                os.close(
                    master_fd
                )
            except Exception:
                pass


        if process is not None:

            # Kill only this web-terminal shell.
            #
            # Do NOT kill the Hermes screen session.
            try:

                if process.poll() is None:

                    os.killpg(
                        os.getpgid(
                            process.pid
                        ),
                        signal.SIGHUP
                    )

            except Exception:
                pass


            try:

                CHILD_PROCESSES.remove(
                    process
                )

            except ValueError:
                pass


        log(
            "Web terminal session closed."
        )


# ============================================================
# STARTUP
# ============================================================

def initialize():

    log("Starting initialization...")
    log("=" * 70)
    log("Hermes Docker Web Terminal")
    log("=" * 70)

    log(f"APP_DIR     = {APP_DIR}")
    log(f"DATA_DIR    = {DATA_DIR}")
    log(f"HERMES_HOME = {HERMES_HOME}")
    log(f"HERMES_DIR  = {HERMES_DIR}")
    log(f"PORT        = {PORT}")

    HERMES_HOME.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Check screen
    # --------------------------------------------------------

    if screen_available():

        log(
            f"screen found: "
            f"{shutil.which('screen')}"
        )

    else:

        log_error(
            "screen is NOT installed."
        )

        return False


    # --------------------------------------------------------
    # Hermes (installed + configured by /app/entrypoint.sh)
    # --------------------------------------------------------

    if not hermes_is_installed():

        log_warning(
            "Hermes executable not found. "
            "Expected /app/entrypoint.sh to install it — "
            "the web server will still start."
        )

        return False


    executable = find_hermes()

    if not executable:

        log_error(
            "Hermes executable still not found."
        )

        return False


    log(
        f"Hermes executable: {executable}"
    )


    # --------------------------------------------------------
    # Screen
    # --------------------------------------------------------

    if ensure_hermes_screen():

        log(
            "Hermes screen is READY."
        )

        log("")
        log(
            "To attach manually:"
        )
        log(
            "    screen -r hermes"
        )
        log("")
        log(
            "Detach:"
        )
        log(
            "    Ctrl+A then D"
        )
        log("")

        # Keep Hermes alive across crashes while the container runs.
        monitor = threading.Thread(
            target=monitor_hermes,
            daemon=True,
            name="hermes-screen-monitor",
        )
        monitor.start()
        log("Hermes screen monitor thread started (checks every 30s).")

        return True


    log_warning(
        "Could not start Hermes screen."
    )

    return False


# ============================================================
# HERMES MONITOR
# ============================================================

def monitor_hermes():
    """
    Periodically check that the Hermes screen session is alive.

    If Hermes (inside the screen session) dies, recreate the screen so the
    container keeps a working agent without requiring a manual restart.
    """

    while not shutdown_event.is_set():

        time.sleep(30)

        try:

            if not screen_exists():

                log_warning(
                    "Hermes screen session not found — recreating."
                )

                ensure_hermes_screen()

        except Exception as exc:

            log_warning(
                f"Hermes monitor error: {exc}"
            )


# ============================================================
# SIGNAL HANDLING
# ============================================================

def shutdown_handler(signum, frame):

    log(
        f"Received signal {signum}. "
        f"Shutting down..."
    )

    shutdown_event.set()

    # --------------------------------------------------------
    # IMPORTANT
    #
    # Do NOT blindly kill screen here with
    #
    #   screen -X quit
    #
    # because we want app.py to control cleanup.
    #
    # Kill process groups we directly created.
    # --------------------------------------------------------

    for process in list(
        CHILD_PROCESSES
    ):

        try:

            if process.poll() is None:

                log(
                    f"Stopping child PID "
                    f"{process.pid}"
                )

                try:

                    os.killpg(
                        os.getpgid(
                            process.pid
                        ),
                        signal.SIGTERM
                    )

                except Exception:

                    process.terminate()

        except Exception:
            pass


    time.sleep(0.5)

    for process in list(
        CHILD_PROCESSES
    ):

        try:

            if process.poll() is None:

                process.kill()

        except Exception:
            pass


    sys.exit(0)


signal.signal(
    signal.SIGTERM,
    shutdown_handler
)

signal.signal(
    signal.SIGINT,
    shutdown_handler
)


# ============================================================
# MAIN
# ============================================================

def main():

    initialize()

    log(
        f"Starting web server on "
        f"0.0.0.0:{PORT}"
    )

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
    )


if __name__ == "__main__":

    main()
