import pyautogui
import time
import random
from datetime import datetime, timedelta
import os
import subprocess
import threading
from pynput import mouse, keyboard
from rich.console import Console
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.progress import Progress, ProgressBar
from rich import box
from rich.text import Text

# Initialize Rich console
console = Console()
layout = Layout()

# Add this at the top level of your file
last_activity_time = datetime.now()
INACTIVITY_THRESHOLD = 30
ACTIVE = False
current_progress = None
current_progress_description = ""
current_progress_value = 0
current_progress_total = 0
duo_sso_last_run = None
DUO_SSO_INTERVAL = 45 * 60  # 45 minutes in seconds

def seconds_to_hhmmss(seconds):
    """
    Convert seconds to HH:MM:SS format.
    
    Args:
        seconds (float): Number of seconds
        
    Returns:
        str: Time in HH:MM:SS format
    """
    if seconds < 0:
        return "00:00:00"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def create_status_panel():
    current_time = datetime.now()
    working_hours_data = is_working_hours()
    is_working = working_hours_data["is_working_hours"]
    
    # Convert seconds to HH:MM:SS format
    last_activity_seconds = (current_time - last_activity_time).total_seconds()
    last_activity_formatted = seconds_to_hhmmss(last_activity_seconds)
    
    # Calculate duo-sso countdown
    duo_sso_status = "Never run"
    duo_sso_countdown = ""
    if duo_sso_last_run:
        time_since_last = (current_time - duo_sso_last_run).total_seconds()
        if time_since_last < DUO_SSO_INTERVAL:
            remaining_time = DUO_SSO_INTERVAL - time_since_last
            duo_sso_countdown = f"Next run in: {seconds_to_hhmmss(remaining_time)}"
            duo_sso_status = f"Last run: {duo_sso_last_run.strftime('%H:%M:%S')}"
        else:
            duo_sso_status = f"Last run: {duo_sso_last_run.strftime('%H:%M:%S')} (Ready to run)"
    else:
        duo_sso_countdown = "Ready to run"
    
    status_content = f"""[bold white]System Status[/bold white]
Current Time: [cyan]{current_time.strftime('%H:%M:%S')}[/cyan]
Working Hours: [{'green' if is_working else 'red'}]{'Yes' if is_working else 'No'}[/]
Working Hour Range: [cyan]{working_hours_data["start"]} - {working_hours_data["end"]}[/cyan]
Last Activity: [yellow]{last_activity_formatted} ago[/yellow]
Duo-SSO Status: [{'green' if duo_sso_last_run and (current_time - duo_sso_last_run).total_seconds() < DUO_SSO_INTERVAL else 'yellow'}]{duo_sso_status}[/]
Duo-SSO Countdown: [blue]{duo_sso_countdown}[/blue]"""

    # Add progress information if there's an active countdown
    if current_progress_total > 0:
        progress_percentage = (current_progress_value / current_progress_total) * 100
        progress_bar = "█" * int(progress_percentage / 2) + "░" * (50 - int(progress_percentage / 2))
        remaining_seconds = current_progress_total - current_progress_value
        remaining_formatted = seconds_to_hhmmss(remaining_seconds)
        
        status_content += f"\n\n{current_progress_description}:\n"
        status_content += f"[blue]{progress_bar}[/blue] {progress_percentage:.1f}%"
        status_content += f"\nRemaining: {remaining_formatted}"
    
    return Panel(
        status_content,
        title="Activity Monitor",
        border_style="blue",
        box=box.ROUNDED
    )

def press_caps_lock():
    pyautogui.FAILSAFE = False
    pyautogui.press('capslock')

def is_working_hours():
    current_hour = datetime.now().hour
    working_hours = {
        "start": "7 AM",
        "end": "5 PM",
        "start_hour": 7,
        "end_hour": 17,
        "is_working_hours": False
    }
    if working_hours["start_hour"] <= current_hour < working_hours["end_hour"]:
        working_hours["is_working_hours"] = True
        
    return working_hours

def run_duo_sso_command():
    """
    Run the duo-sso command and capture its output.
    This function runs in a separate thread to avoid blocking the main program.
    """
    try:
        # Run duo-sso command and capture output
        result = subprocess.run(
            ['duo-sso'], 
            capture_output=True, 
            text=True, 
            timeout=30  # 30 second timeout
        )
        
        # Display the output
        if result.stdout:
            console.print("[green]duo-sso output:[/green]")
            console.print(result.stdout)
        
        if result.stderr:
            console.print("[yellow]duo-sso stderr:[/yellow]")
            console.print(result.stderr)
        
        if result.returncode == 0:
            console.print("[green]duo-sso command completed successfully[/green]")
        else:
            console.print(f"[red]duo-sso command failed with return code: {result.returncode}[/red]")
            
    except subprocess.TimeoutExpired:
        console.print("[red]duo-sso command timed out after 30 seconds[/red]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error running duo-sso command: {e}[/red]")
        if e.stdout:
            console.print(f"stdout: {e.stdout}")
        if e.stderr:
            console.print(f"stderr: {e.stderr}")
    except FileNotFoundError:
        console.print("[red]duo-sso command not found. Please ensure it's installed and in your PATH[/red]")
    except Exception as e:
        console.print(f"[red]Unexpected error running duo-sso command: {e}[/red]")

def run_duo_sso_if_needed():
    """
    Check if duo-sso should be run during working hours.
    Runs every 50 minutes during working hours.
    """
    global duo_sso_last_run
    
    current_time = datetime.now()
    
    # Check if it's working hours and enough time has passed since last run
    if (is_working_hours()["is_working_hours"] and 
        (duo_sso_last_run is None or (current_time - duo_sso_last_run).total_seconds() >= DUO_SSO_INTERVAL)):
        
        # Run duo-sso in a separate thread
        duo_thread = threading.Thread(target=run_duo_sso_command, daemon=True)
        duo_thread.start()
        
        duo_sso_last_run = current_time
        console.print("[yellow]duo-sso command scheduled to run[/yellow]")

def reset_daily_flags():
    """
    Reset daily flags at the start of each new day.
    This ensures duo-sso can run again the next day.
    """
    global duo_sso_last_run
    
    current_time = datetime.now()
    
    # Reset flags at midnight (00:00)
    if current_time.hour == 0 and current_time.minute == 0:
        duo_sso_last_run = None # Reset last run
        console.print("[cyan]Daily flags reset - duo-sso can run again today[/cyan]")

def check_no_activity():
    global last_activity_time
    current_time = datetime.now()
    time_difference = (current_time - last_activity_time).total_seconds()
    if time_difference >= INACTIVITY_THRESHOLD:
        last_activity_time = current_time - timedelta(seconds=INACTIVITY_THRESHOLD)
        return True
    return False

def on_activity():
    global last_activity_time
    last_activity_time = datetime.now()
    return True

def on_mouse_move(x, y):
    return on_activity()

def on_mouse_click(x, y, button, pressed):
    return on_activity()

def on_key_press(key):
    try:
        # Check for Ctrl+D to manually trigger duo-sso
        if hasattr(key, 'char') and key.char == 'd':
            # Check if Ctrl is pressed (you might need to adjust this based on your system)
            # For now, we'll use a simple approach
            pass
        
        return on_activity()
    except AttributeError:
        return on_activity()

def setup_activity_listeners():
    keyboard_listener = keyboard.Listener(on_press=on_key_press)
    keyboard_listener.start()
    
    mouse_listener = mouse.Listener(
        on_move=on_mouse_move,
        on_click=on_mouse_click
    )
    mouse_listener.start()
    
    return keyboard_listener, mouse_listener

def countdown_with_live_display(target_end_time, description, live):
    global current_progress_description, current_progress_total, current_progress_value
    
    current_progress_description = description
    current_progress_total = (target_end_time - datetime.now()).total_seconds()
    current_progress_value = 0
    
    while datetime.now() < target_end_time:
        current_time = datetime.now()
        elapsed = (current_time - (target_end_time - timedelta(seconds=current_progress_total))).total_seconds()
        current_progress_value = max(0, current_progress_total - (target_end_time - current_time).total_seconds())
        
        live.update(create_status_panel())
        time.sleep(1)

    current_progress_total = 0
    current_progress_value = 0
    current_progress_description = ""

if __name__ == "__main__":
    console.clear()
    console.print("[bold blue]Activity Monitor Started[/bold blue]")
    
    keyboard_listener, mouse_listener = setup_activity_listeners()
    console.print("[green]Activity listeners set up successfully[/green]")

    try:
        with Live(create_status_panel(), refresh_per_second=1) as live:
            while True:
                # Reset daily flags if needed
                reset_daily_flags()
                
                # Check if duo-sso should be run
                run_duo_sso_if_needed()
                
                if not is_working_hours()["is_working_hours"]:
                    # When outside working hours, immediately sleep until next working day
                    # Calculate the target end time for next working day
                    current_time = datetime.now()
                    working_hours = is_working_hours()
                    start_hour = working_hours["start_hour"]
                    
                    # Calculate tomorrow's date
                    next_day = current_time + timedelta(days=1)
                    target_end_time = next_day.replace(hour=start_hour, minute=0, second=0, microsecond=0)
                    
                    countdown_with_live_display(target_end_time, "Sleeping until next working day", live)
                else:
                    # During working hours, wait for inactivity then do random activity
                    if check_no_activity():
                        # Calculate random sleep duration and target end time
                        sleep_duration = random.randint(1, 300)
                        target_end_time = datetime.now() + timedelta(seconds=sleep_duration)
                        
                        countdown_with_live_display(target_end_time, "Next activity in", live)
                        press_caps_lock()
                
                live.update(create_status_panel())
                
    except KeyboardInterrupt:
        console.print("[red]Program terminated by user[/red]")
        keyboard_listener.stop()
        mouse_listener.stop()