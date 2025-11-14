
"""
## Setup

To install the dependencies for this script, run:

``` 
pip install google-genai opencv-python pyaudio pillow mss python-dotenv pynput pyautogui
```

Before running this script, ensure the `GOOGLE_API_KEY` environment
variable is set to the api-key you obtained from Google AI Studio.

Important: **Use headphones**. This script uses the system default audio
input and output, which often won't include echo cancellation. So to prevent
the model from interrupting itself it is important that you use headphones. 

## Run

To run the script:

```
python Get_started_LiveAPI.py
```

The script takes a video-mode flag `--mode`, this can be "camera", "screen", or "none".
The default is "camera". To share your screen run:

```
python Get_started_LiveAPI.py --mode screen
```
"""

import asyncio
import base64
import io
import os
import sys
import traceback
import logging
import json
from datetime import datetime

import cv2
import pyaudio
import PIL.Image
import mss

import argparse

from google import genai
from google.genai import types
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY environment variable is not set")
from PIL import ImageDraw
import pyautogui
if sys.version_info < (3, 11, 0):
    import taskgroup, exceptiongroup

    asyncio.TaskGroup = taskgroup.TaskGroup
    asyncio.ExceptionGroup = exceptiongroup.ExceptionGroup

# Import Opik for tracing
import opik
from opik import track

# Configure Opik - it will use environment variables:
# OPIK_API_KEY (optional for cloud)
# OPIK_WORKSPACE (optional for cloud)
# OPIK_URL_OVERRIDE (optional, defaults to cloud)
try:
    opik_client = opik.Opik()
    print("✅ Opik tracing initialized successfully")
except Exception as e:
    print(f"⚠️  Opik initialization warning: {e}")
    print("Continuing without Opik tracing. Set OPIK_API_KEY to enable.")
    opik_client = None

FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024

MODEL = "gemini-2.5-flash-native-audio-preview-09-2025"

DEFAULT_MODE = "screen"
from pynput import mouse
from pynput import keyboard
import pyautogui
import mss
import numpy as np
import cv2
client = genai.Client(api_key=GOOGLE_API_KEY)

# Global mouse controller for reliability (avoids creating new instances)
_MOUSE_CONTROLLER = mouse.Controller()


class VoiceAssistantLogger:
    """
    Comprehensive logging system for the Voice Assistant.
    
    Provides structured logging for tool calls, coordinate detection,
    mouse movements, and errors with timestamps and context.
    
    Features:
    - Debug mode support for verbose output
    - Dual output to file (voice_assistant.log) and console
    - Structured JSON logging for easy parsing
    - Specialized methods for different event types
    """
    
    def __init__(self, debug_mode=False):
        """
        Initialize the logger with optional debug mode.
        
        Args:
            debug_mode: If True, enables DEBUG level logging with verbose output
        """
        self.debug_mode = debug_mode
        self.setup_logging()
    
    def setup_logging(self):
        """
        Configure logging to write to both file and console.
        
        Sets up:
        - Log level based on debug mode (DEBUG or INFO)
        - File handler for voice_assistant.log
        - Console handler for real-time output
        - Timestamp formatting
        """
        level = logging.DEBUG if self.debug_mode else logging.INFO
        
        # Create logger
        self.logger = logging.getLogger('VoiceAssistant')
        self.logger.setLevel(level)
        
        # Clear any existing handlers to avoid duplicates
        self.logger.handlers.clear()
        
        # Create formatters
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # File handler
        file_handler = logging.FileHandler('voice_assistant.log')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # Prevent propagation to root logger
        self.logger.propagate = False
        
        self.logger.info("VoiceAssistantLogger initialized" + 
                        (" (DEBUG MODE)" if self.debug_mode else ""))
    
    def log_tool_call(self, tool_name, args, result):
        """
        Log every tool execution with full details.
        
        Tracks:
        - Tool name and arguments
        - Execution result
        - Success/failure status
        - Timestamp
        
        Args:
            tool_name: Name of the tool/function called
            args: Dictionary of arguments passed to the tool
            result: Return value from the tool execution
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "tool": tool_name,
            "args": args,
            "result": result,
            "success": "error" not in str(result).lower()
        }
        
        if self.debug_mode:
            self.logger.debug(f"TOOL_CALL: {json.dumps(log_entry, indent=2)}")
        else:
            self.logger.info(f"TOOL_CALL: {tool_name} - Success: {log_entry['success']}")
    
    def log_coordinate_detection(self, prompt, coordinates, screenshot_path):
        """
        Log coordinate detection attempts.
        
        Tracks:
        - Detection prompt/description
        - Detected coordinates (or error)
        - Screenshot path for debugging
        - Timestamp
        
        Args:
            prompt: Description of the UI element being detected
            coordinates: Dict with 'x', 'y' keys or 'error' key
            screenshot_path: Path to saved screenshot for debugging
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "prompt": prompt,
            "coordinates": coordinates,
            "screenshot": screenshot_path,
            "success": "error" not in coordinates
        }
        
        if log_entry["success"]:
            self.logger.info(
                f"COORD_DETECT: Found '{prompt}' at "
                f"({coordinates.get('x')}, {coordinates.get('y')}) - "
                f"Screenshot: {screenshot_path}"
            )
        else:
            self.logger.warning(
                f"COORD_DETECT: Failed to find '{prompt}' - "
                f"Error: {coordinates.get('error')} - "
                f"Screenshot: {screenshot_path}"
            )
        
        if self.debug_mode:
            self.logger.debug(f"COORD_DETECT_DETAILS: {json.dumps(log_entry, indent=2)}")
    
    def log_mouse_movement(self, target, actual, success):
        """
        Log mouse movements with verification.
        
        Tracks:
        - Target coordinates
        - Actual final coordinates
        - Success status
        - Error distance (if available)
        - Timestamp
        
        Args:
            target: Tuple of (x, y) target coordinates
            actual: Tuple of (x, y) actual final coordinates
            success: Boolean indicating if movement was accurate
        """
        import math
        
        # Calculate error distance
        error_distance = math.sqrt(
            (actual[0] - target[0])**2 + 
            (actual[1] - target[1])**2
        )
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "target": target,
            "actual": actual,
            "error_distance": round(error_distance, 2),
            "success": success
        }
        
        if success:
            self.logger.info(
                f"MOUSE_MOVE: Target: {target}, Actual: {actual}, "
                f"Error: {error_distance:.2f}px - SUCCESS"
            )
        else:
            self.logger.warning(
                f"MOUSE_MOVE: Target: {target}, Actual: {actual}, "
                f"Error: {error_distance:.2f}px - FAILED"
            )
        
        if self.debug_mode:
            self.logger.debug(f"MOUSE_MOVE_DETAILS: {json.dumps(log_entry, indent=2)}")
    
    def log_error(self, error_type, error_message, context):
        """
        Log errors with full context.
        
        Provides detailed error information for debugging:
        - Error type/category
        - Error message
        - Contextual information (function, parameters, state, etc.)
        - Timestamp
        
        Args:
            error_type: Category or type of error (e.g., "coordinate_detection_failed")
            error_message: Detailed error message
            context: Dictionary with contextual information (function name, args, etc.)
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "error_type": error_type,
            "message": error_message,
            "context": context
        }
        
        self.logger.error(
            f"ERROR [{error_type}]: {error_message} - "
            f"Context: {json.dumps(context)}"
        )
        
        if self.debug_mode:
            self.logger.debug(f"ERROR_DETAILS: {json.dumps(log_entry, indent=2)}")


# Global logger instance (initialized with debug mode disabled by default)
# Can be re-initialized with debug mode via command-line flag
logger = VoiceAssistantLogger(debug_mode=False)


def retry_with_backoff(max_retries=3, initial_delay=0.5):
    """
    Decorator for retrying failed operations with exponential backoff.
    
    Implements automatic retry logic for functions that may fail transiently.
    Uses exponential backoff strategy: delay doubles after each failed attempt.
    
    Features:
    - Configurable maximum retry attempts
    - Exponential backoff delay (doubles each retry)
    - Detailed logging of retry attempts
    - Preserves original function metadata
    - Re-raises the last exception if all retries fail
    
    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds before first retry (default: 0.5)
    
    Returns:
        Decorator function that wraps the target function with retry logic
    
    Example:
        @retry_with_backoff(max_retries=2, initial_delay=0.5)
        def unstable_function():
            # Function that might fail
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    # Attempt to execute the function
                    result = func(*args, **kwargs)
                    
                    # Log success if this wasn't the first attempt
                    if attempt > 0:
                        logger.logger.info(
                            f"✅ {func.__name__} succeeded on attempt {attempt + 1}/{max_retries}"
                        )
                    
                    return result
                    
                except Exception as e:
                    last_exception = e
                    
                    # Log the retry attempt
                    logger.log_error(
                        error_type=f"{func.__name__}_retry",
                        error_message=str(e),
                        context={
                            "attempt": attempt + 1,
                            "max_retries": max_retries,
                            "next_delay": delay if attempt < max_retries - 1 else None,
                            "function": func.__name__,
                            "args": str(args)[:100],  # Truncate long args
                            "kwargs": str(kwargs)[:100]
                        }
                    )
                    
                    # If this wasn't the last attempt, wait before retrying
                    if attempt < max_retries - 1:
                        logger.logger.warning(
                            f"⚠️  {func.__name__} failed (attempt {attempt + 1}/{max_retries}). "
                            f"Retrying in {delay:.1f}s..."
                        )
                        time.sleep(delay)
                        delay *= 2  # Exponential backoff: double the delay
                    else:
                        # All retries exhausted
                        logger.logger.error(
                            f"❌ {func.__name__} failed after {max_retries} attempts. "
                            f"Final error: {str(last_exception)}"
                        )
            
            # All retries failed - re-raise the last exception
            raise last_exception
        
        return wrapper
    return decorator


def capture_screen_sync():
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            return np.array(sct.grab(monitor))
    except Exception as e:
        raise RuntimeError(
            "❌ Screen capture failed! On macOS, grant Screen Recording permission:\n"
            "  → System Settings → Privacy & Security → Screen Recording\n"
            "  → Add Terminal (or your IDE)\n"
            f"Original error: {e}"
        )

import os
import time
import cv2
import numpy as np
import threading
import mss
from google import genai
from google.genai import types
from functools import wraps
import math


def show_quiz_modal(quiz_text):
    """
    Display quiz in a translucent modal window that can be closed.
    Must be called from the main thread (macOS requirement).
    """
    import tkinter as tk
    from tkinter import font as tkfont

    # Create the main window
    root = tk.Tk()
    root.title("🎯 Quiz Time!")

    # Get screen dimensions
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()

    # Set window size (60% of screen)
    window_width = int(screen_width * 0.6)
    window_height = int(screen_height * 0.6)

    # Center window
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")

    # Make window translucent and always on top
    root.attributes('-alpha', 0.95)
    root.attributes('-topmost', True)

    # Colors
    bg_color = "#2C3E50"
    text_color = "#ECF0F1"
    accent_color = "#3498DB"

    root.configure(bg=bg_color)
    content_frame = tk.Frame(root, bg=bg_color, padx=30, pady=20)
    content_frame.pack(fill=tk.BOTH, expand=True)

    # Title
    title_font = tkfont.Font(family="Helvetica", size=24, weight="bold")
    title_label = tk.Label(content_frame, text="🎯 Quiz Time! 🎯",
                           font=title_font, bg=bg_color, fg=accent_color)
    title_label.pack(pady=(0, 20))

    # Quiz text box
    quiz_font = tkfont.Font(family="Helvetica", size=14)
    quiz_text_widget = tk.Text(content_frame, font=quiz_font, bg="#34495E",
                               fg=text_color, wrap=tk.WORD, padx=20, pady=20,
                               relief=tk.FLAT, highlightthickness=0)
    quiz_text_widget.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
    quiz_text_widget.insert(1.0, quiz_text)
    quiz_text_widget.config(state=tk.DISABLED)

    # Close button
    def close_window():
        root.destroy()

    button_font = tkfont.Font(family="Helvetica", size=12, weight="bold")
    close_button = tk.Button(content_frame, text="✖ Close Quiz",
                             command=close_window, font=button_font,
                             bg="#E74C3C", fg="white",
                             activebackground="#C0392B",
                             activeforeground="white",
                             relief=tk.FLAT, padx=20, pady=10, cursor="hand2")
    close_button.pack()

    root.bind('<Escape>', lambda e: close_window())
    root.mainloop()


def generate_quiz_from_screen():
    """
    Capture the current screen and generate a fun quiz with:
    - 2 questions about what's visible on screen
    - 1 fun/creative question for entertainment

    Displays in a translucent modal window if on main thread,
    otherwise prints to console (safe for async/threaded contexts).
    """
    import inspect

    try:
        print("[LOG] Starting quiz generation...")

        # Capture screen
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            img = np.array(sct.grab(monitor))
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

            # Save screenshot
            save_dir = f"quiz_screens_{int(time.time())}"
            os.makedirs(save_dir, exist_ok=True)
            screenshot_path = f"{save_dir}/screen.jpg"
            cv2.imwrite(screenshot_path, img)

        print(f"[LOG] Screenshot saved at: {screenshot_path}")

        # Read image for Gemini
        with open(screenshot_path, "rb") as f:
            image_bytes = f.read()

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("Missing GOOGLE_API_KEY environment variable.")

        print("[LOG] Connecting to Gemini API...")
        quiz_client = genai.Client(api_key=api_key)

        # Generate quiz using Gemini
        response = quiz_client.models.generate_content(
            model="models/gemini-2.5-pro",
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                types.Part.from_text(
                    text="""Analyze this screenshot and create a fun quiz with exactly 3 questions:

1. SCREEN QUESTION 1: Ask about something specific visible in the screenshot (text, UI element, content, etc.)
2. SCREEN QUESTION 2: Ask another question about different content visible in the screenshot
3. FUN QUESTION: Ask a creative, humorous, or thought-provoking question inspired by what you see (can be playful!)

Format each question clearly with:
Question 1: [Your question here]
Question 2: [Your question here]  
Question 3 (Fun): [Your question here]

Make the questions engaging and fun!"""
                )
            ]
        )

        quiz_text = response.text.strip()

        # Print to console
        print("\n" + "=" * 60)
        print("🎯 QUIZ TIME! 🎯")
        print("=" * 60)
        print(quiz_text)
        print("=" * 60 + "\n")

        # Only show GUI if on main thread
        if threading.current_thread() is threading.main_thread():
            print("[LOG] On main thread — showing Tkinter modal.")
            show_quiz_modal(quiz_text)
        else:
            print("[LOG] Not on main thread — skipping GUI, printing to console only.")

        return {
            "result": "Quiz generated successfully!",
            "quiz": quiz_text,
            "screenshot": screenshot_path
        }

    except Exception as e:
        import traceback
        print("[ERROR] Quiz generation failed:", e)
        print(traceback.format_exc())
        return {"error": f"Failed to generate quiz: {str(e)}"}

def smart_detect_screen_coordinates(prompt):
    """
    Enhanced coordinate detection with finer grid and robust parsing.
    Captures multiple grid perspectives (10px fine, 50px coarse, pure grid)
    and uses robust coordinate parsing with validation.
    
    Returns: dict with 'x', 'y' coordinates or 'error' message with suggestions
    """
    import os
    import time
    import cv2
    import numpy as np
    import re
    from google import genai
    from google.genai import types

    try:
        # === Setup ===
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            error_msg = "Google API key is not configured"
            logger.log_error(
                error_type="configuration_error",
                error_message=error_msg,
                context={"function": "smart_detect_screen_coordinates", "prompt": prompt}
            )
            return {
                "error": error_msg,
                "user_message": "❌ API key not found. Please set GOOGLE_API_KEY environment variable.",
                "suggestion": "Check your .env file or environment variables to ensure GOOGLE_API_KEY is set correctly."
            }

        client = genai.Client(api_key=api_key)
        save_dir = f"screens_{int(time.time())}"
        os.makedirs(save_dir, exist_ok=True)

        # === Capture Screen ===
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]  # Full primary screen
                img = np.array(sct.grab(monitor))
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        except Exception as screen_error:
            error_msg = f"Screen capture failed: {str(screen_error)}"
            logger.log_error(
                error_type="screen_capture_failed",
                error_message=error_msg,
                context={"function": "smart_detect_screen_coordinates", "prompt": prompt}
            )
            return {
                "error": error_msg,
                "user_message": "❌ Unable to capture screen. Please check screen recording permissions.",
                "suggestion": "On macOS: System Settings → Privacy & Security → Screen Recording → Enable for your terminal/IDE"
            }
            
        height, width, _ = img.shape
        
        # Save original
        original_path = f"{save_dir}/screen_original.jpg"
        cv2.imwrite(original_path, img)

        def draw_grid(base_img, step, color=(90, 90, 90), label_color=(255, 255, 255)):
            """Draws grid lines and coordinate labels."""
            result = base_img.copy()
            h, w, _ = result.shape
            
            # Draw vertical lines
            for x in range(0, w, step):
                cv2.line(result, (x, 0), (x, h), color, 1)
                # Label at top and bottom
                cv2.putText(result, str(x), (x + 2, 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, label_color, 1)
                cv2.putText(result, str(x), (x + 2, h - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, label_color, 1)
            
            # Draw horizontal lines
            for y in range(0, h, step):
                cv2.line(result, (0, y), (w, y), color, 1)
                # Label at left and right
                cv2.putText(result, str(y), (5, y + 12),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, label_color, 1)
                cv2.putText(result, str(y), (w - 40, y + 12),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, label_color, 1)
            
            return result

        # === Create Multiple Grid Images ===
        
        # 1. Fine grid (10px) - for precision
        fine_grid_path = f"{save_dir}/screen_fine_grid_10px.jpg"
        fine_grid = draw_grid(img, step=10, color=(70, 70, 70))
        cv2.imwrite(fine_grid_path, fine_grid)
        
        # 2. Coarse grid (50px) - for context
        coarse_grid_path = f"{save_dir}/screen_coarse_grid_50px.jpg"
        coarse_grid = draw_grid(img, step=50, color=(100, 100, 100))
        cv2.imwrite(coarse_grid_path, coarse_grid)
        
        # 3. Pure grid only (10px on white background)
        pure_grid_path = f"{save_dir}/grid_pure_10px.jpg"
        pure_grid = np.ones_like(img, dtype=np.uint8) * 255
        pure_grid = draw_grid(pure_grid, step=10, color=(0, 0, 0), label_color=(0, 0, 0))
        cv2.imwrite(pure_grid_path, pure_grid)

        print(f"📸 Saved images:")
        print(f"  • Original: {original_path}")
        print(f"  • Fine grid (10px): {fine_grid_path}")
        print(f"  • Coarse grid (50px): {coarse_grid_path}")
        print(f"  • Pure grid: {pure_grid_path}")

        # === Send to Gemini with Enhanced Prompt ===
        with open(original_path, "rb") as f1, \
             open(fine_grid_path, "rb") as f2, \
             open(coarse_grid_path, "rb") as f3, \
             open(pure_grid_path, "rb") as f4:
            original_bytes = f1.read()
            fine_grid_bytes = f2.read()
            coarse_grid_bytes = f3.read()
            pure_grid_bytes = f4.read()

        enhanced_prompt = f"""Analyze these images to find the EXACT coordinates of: "{prompt}"

Images provided:
1. Original screen (no grid)
2. Fine grid overlay (10px spacing) - use this for PRECISE coordinate detection
3. Coarse grid overlay (50px spacing) - use this for general location context
4. Pure grid reference (10px) - use this to understand the coordinate system

INSTRUCTIONS:
- Locate the CENTER POINT of the target element "{prompt}"
- Use the 10px fine grid for maximum precision
- Read the coordinate labels on the grid axes carefully
- The screen dimensions are {width}x{height} pixels

RESPONSE FORMAT (CRITICAL):
You MUST respond with coordinates in this EXACT format:
x=NUMBER, y=NUMBER

Example: x=450, y=320

Do not include any other text, explanations, or formatting. Just the coordinates."""

        # === Send to Gemini with Enhanced Prompt ===
        try:
            response = client.models.generate_content(
                model="models/gemini-2.5-pro",
                contents=[
                    types.Part.from_bytes(data=original_bytes, mime_type="image/jpeg"),
                    types.Part.from_bytes(data=fine_grid_bytes, mime_type="image/jpeg"),
                    types.Part.from_bytes(data=coarse_grid_bytes, mime_type="image/jpeg"),
                    types.Part.from_bytes(data=pure_grid_bytes, mime_type="image/jpeg"),
                    types.Part.from_text(text=enhanced_prompt)
                ]
            )
        except Exception as api_error:
            error_msg = f"Gemini API call failed: {str(api_error)}"
            logger.log_error(
                error_type="api_call_failed",
                error_message=error_msg,
                context={
                    "function": "smart_detect_screen_coordinates",
                    "prompt": prompt,
                    "error_type": type(api_error).__name__
                }
            )
            
            # Provide user-friendly error messages for common API errors
            if "quota" in str(api_error).lower() or "rate limit" in str(api_error).lower():
                return {
                    "error": error_msg,
                    "user_message": "❌ API quota exceeded or rate limit reached.",
                    "suggestion": "Wait a few moments and try again. Consider upgrading your API plan if this happens frequently."
                }
            elif "timeout" in str(api_error).lower():
                return {
                    "error": error_msg,
                    "user_message": "❌ API request timed out.",
                    "suggestion": "Check your internet connection and try again. The retry mechanism will automatically attempt this."
                }
            elif "authentication" in str(api_error).lower() or "unauthorized" in str(api_error).lower():
                return {
                    "error": error_msg,
                    "user_message": "❌ API authentication failed.",
                    "suggestion": "Verify your GOOGLE_API_KEY is valid and has the necessary permissions."
                }
            else:
                return {
                    "error": error_msg,
                    "user_message": f"❌ API error: {str(api_error)}",
                    "suggestion": "Try again in a moment. If the problem persists, check the Gemini API status."
                }

        try:
            text = response.text.strip()
            print(f"🔍 Model output: {text}")
        except Exception as response_error:
            error_msg = f"Failed to extract text from API response: {str(response_error)}"
            logger.log_error(
                error_type="response_parsing_failed",
                error_message=error_msg,
                context={"function": "smart_detect_screen_coordinates", "prompt": prompt}
            )
            return {
                "error": error_msg,
                "user_message": "❌ Received invalid response from API.",
                "suggestion": "Try again with a more specific description of the element you're looking for."
            }

        # === Robust Coordinate Parsing ===
        x, y = None, None
        
        # Try multiple regex patterns
        patterns = [
            r'x\s*=\s*(\d+)\s*,\s*y\s*=\s*(\d+)',  # x=123, y=456
            r'x\s*:\s*(\d+)\s*,\s*y\s*:\s*(\d+)',  # x:123, y:456
            r'\((\d+)\s*,\s*(\d+)\)',               # (123, 456)
            r'(\d+)\s*,\s*(\d+)',                   # 123, 456
            r'x\s*=\s*(\d+).*y\s*=\s*(\d+)',       # x=123 ... y=456
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                x, y = int(match.group(1)), int(match.group(2))
                print(f"✅ Parsed coordinates: x={x}, y={y}")
                break
        
        if x is None or y is None:
            error_msg = f"Could not parse coordinates from response: {text}"
            logger.log_error(
                error_type="coordinate_parsing_failed",
                error_message=error_msg,
                context={
                    "function": "smart_detect_screen_coordinates",
                    "prompt": prompt,
                    "raw_response": text
                }
            )
            
            # Check if the AI couldn't find the element
            if any(word in text.lower() for word in ["cannot", "can't", "unable", "not found", "don't see", "couldn't"]):
                return {
                    "error": error_msg,
                    "user_message": f"❌ Could not locate '{prompt}' on screen.",
                    "suggestion": "Try:\n  • Being more specific (e.g., 'blue Submit button in top-right corner')\n  • Describing visual features (color, size, text)\n  • Mentioning nearby elements for context\n  • Checking if the element is actually visible on screen",
                    "raw_response": text
                }
            else:
                return {
                    "error": error_msg,
                    "user_message": "❌ AI response did not contain valid coordinates.",
                    "suggestion": "The AI may have misunderstood. Try rephrasing your description to be more specific about what you want to click.",
                    "raw_response": text
                }
        
        # === Coordinate Validation ===
        if x < 0 or x >= width or y < 0 or y >= height:
            error_msg = f"Coordinates ({x}, {y}) are out of screen bounds (0-{width}, 0-{height})"
            logger.log_error(
                error_type="coordinates_out_of_bounds",
                error_message=error_msg,
                context={
                    "function": "smart_detect_screen_coordinates",
                    "prompt": prompt,
                    "x": x,
                    "y": y,
                    "screen_width": width,
                    "screen_height": height
                }
            )
            return {
                "error": error_msg,
                "user_message": f"❌ Detected coordinates ({x}, {y}) are outside screen bounds.",
                "suggestion": "This is unusual. Try again with a clearer description. The element might be partially off-screen.",
                "x": x,
                "y": y,
                "screen_width": width,
                "screen_height": height
            }
        
        # === Success! ===
        logger.logger.info(f"✅ Successfully detected '{prompt}' at ({x}, {y})")
        return {
            "x": x,
            "y": y,
            "result": f"Found '{prompt}' at coordinates x={x}, y={y}",
            "screen_width": width,
            "screen_height": height,
            "screenshot_dir": save_dir
        }
        
    except Exception as e:
        # Catch-all for any unexpected errors
        error_msg = f"Unexpected error during coordinate detection: {str(e)}"
        logger.log_error(
            error_type="coordinate_detection_unexpected_error",
            error_message=error_msg,
            context={
                "function": "smart_detect_screen_coordinates",
                "prompt": prompt,
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc()
            }
        )
        return {
            "error": error_msg,
            "user_message": f"❌ Unexpected error: {str(e)}",
            "suggestion": "This is an unexpected error. Try again, and if it persists, check the logs for details.",
            "prompt": prompt
        }

@retry_with_backoff(max_retries=2, initial_delay=0.5)
def smart_detect_screen_coordinates_with_retry(prompt):
    """
    Coordinate detection with automatic retry logic.
    
    Wraps smart_detect_screen_coordinates with retry logic to handle
    transient failures (API timeouts, network issues, etc.).
    
    Features:
    - Automatic retry on failure (up to 2 retries)
    - Exponential backoff (0.5s, 1.0s)
    - Detailed logging of retry attempts
    - Returns same format as smart_detect_screen_coordinates
    
    Args:
        prompt: Description of the UI element to find
    
    Returns:
        dict with 'x', 'y' coordinates or 'error' message
    
    Raises:
        Exception: If all retry attempts fail
    """
    result = smart_detect_screen_coordinates(prompt)
    
    # Check if the result contains an error
    if "error" in result:
        # Raise an exception to trigger retry
        raise Exception(result["error"])
    
    return result


def get_screen_size():
    """Get the screen size."""
    return {"width": pyautogui.size()[0], "height": pyautogui.size()[1]}

def get_mouse_position():
    """Get the mouse position."""
    return {"x": _MOUSE_CONTROLLER.position[0], "y": _MOUSE_CONTROLLER.position[1]}

def move_mouse_relative(x: int, y: int):
    """Move the mouse relative to the current position. x is the horizontal distance to move and y is the vertical distance to move.
    x is the distance from the left edge of the screen and y is the distance from the top edge of the screen.
    So get the current mouse position first, then add the x and y to the current position.
    """
    current_x, current_y = _MOUSE_CONTROLLER.position
    _MOUSE_CONTROLLER.position = (int(current_x + x), int(current_y + y))
    return {"result": f"mouse current position is {_MOUSE_CONTROLLER.position}"}
def move_mouse_absolute(x, y):
    """
    Move mouse to absolute coordinates with basic error handling.
    
    Args:
        x: Target x coordinate
        y: Target y coordinate
    
    Returns:
        dict with result message or error details
    """
    import time
    
    try:
        # Validate coordinates are reasonable
        screen_width, screen_height = pyautogui.size()
        
        if x < 0 or x >= screen_width or y < 0 or y >= screen_height:
            error_msg = f"Coordinates ({x}, {y}) are out of screen bounds (0-{screen_width}, 0-{screen_height})"
            logger.log_error(
                error_type="mouse_movement_out_of_bounds",
                error_message=error_msg,
                context={"function": "move_mouse_absolute", "x": x, "y": y}
            )
            return {
                "error": error_msg,
                "user_message": f"❌ Cannot move mouse to ({x}, {y}) - outside screen bounds.",
                "suggestion": f"Screen size is {screen_width}x{screen_height}. Use coordinates within these bounds."
            }
        
        start_x, start_y = _MOUSE_CONTROLLER.position
        steps = 20
        delay = 0.005
        
        for i in range(1, steps + 1):
            nx = int(start_x + (x - start_x) * i / steps)
            ny = int(start_y + (y - start_y) * i / steps)
            _MOUSE_CONTROLLER.position = (nx, ny)
            time.sleep(delay)
        
        return {"result": f"Mouse moved smoothly to {(x, y)}"}
        
    except Exception as e:
        error_msg = f"Mouse movement failed: {str(e)}"
        logger.log_error(
            error_type="mouse_movement_failed",
            error_message=error_msg,
            context={
                "function": "move_mouse_absolute",
                "target_x": x,
                "target_y": y,
                "error_type": type(e).__name__
            }
        )
        return {
            "error": error_msg,
            "user_message": f"❌ Failed to move mouse: {str(e)}",
            "suggestion": "Check system permissions for controlling the mouse. On macOS: System Settings → Privacy & Security → Accessibility"
        }

def smoothstep(t):
    """
    Smoothstep easing function for natural movement.
    Returns a value between 0 and 1 with smooth acceleration and deceleration.
    Formula: 3t² - 2t³
    """
    return t * t * (3.0 - 2.0 * t)

def move_mouse_absolute_validated(x, y):
    """
    Move mouse to absolute coordinates with validation and position verification.
    
    Features:
    - Bounds checking to ensure coordinates are within screen dimensions
    - Smoothstep easing for natural movement trajectory
    - Position verification after movement completion
    - Corrective movement if position is off by more than 5 pixels
    - Detailed feedback with success status and error metrics
    - Comprehensive error handling with user-friendly messages
    
    Args:
        x: Target x coordinate (horizontal, from left edge)
        y: Target y coordinate (vertical, from top edge)
    
    Returns:
        dict with:
        - success: bool indicating if movement was accurate (within 10px)
        - target: tuple of target coordinates (x, y)
        - actual: tuple of actual final coordinates
        - error_distance: float distance in pixels from target
        - message: string description of the result
        - error: (optional) error message if something went wrong
        - user_message: (optional) user-friendly error explanation
        - suggestion: (optional) suggestion for fixing the issue
    """
    import time
    import math
    
    try:
        # Get screen dimensions for bounds checking
        screen_width, screen_height = pyautogui.size()
        
        # Validate coordinates are within screen bounds
        if x < 0 or x >= screen_width or y < 0 or y >= screen_height:
            error_msg = f"Coordinates ({x}, {y}) are out of bounds. Screen size: {screen_width}x{screen_height}"
            logger.log_error(
                error_type="validated_mouse_movement_out_of_bounds",
                error_message=error_msg,
                context={"function": "move_mouse_absolute_validated", "x": x, "y": y}
            )
            return {
                "success": False,
                "target": (x, y),
                "actual": _MOUSE_CONTROLLER.position,
                "error_distance": -1,
                "message": error_msg,
                "error": error_msg,
                "user_message": f"❌ Cannot move to ({x}, {y}) - coordinates are outside screen bounds.",
                "suggestion": f"Use coordinates within screen bounds: 0-{screen_width} (width), 0-{screen_height} (height). Call get_screen_size() first to check dimensions."
            }
    
        # Get starting position
        start_x, start_y = _MOUSE_CONTROLLER.position
        
        # Movement parameters
        steps = 30  # More steps for smoother movement
        delay = 0.003  # Slightly faster per-step delay
        
        # Perform smooth movement with easing
        for i in range(1, steps + 1):
            # Calculate progress (0.0 to 1.0)
            t = i / steps
            
            # Apply smoothstep easing
            eased_t = smoothstep(t)
            
            # Calculate intermediate position
            nx = int(start_x + (x - start_x) * eased_t)
            ny = int(start_y + (y - start_y) * eased_t)
            
            # Move to intermediate position
            _MOUSE_CONTROLLER.position = (nx, ny)
            time.sleep(delay)
        
        # Allow system to settle
        time.sleep(0.05)
        
        # Verify final position
        actual_x, actual_y = _MOUSE_CONTROLLER.position
        error_distance = math.sqrt((actual_x - x)**2 + (actual_y - y)**2)
        
        # Corrective movement if needed (more than 5 pixels off)
        if error_distance > 5:
            # Direct movement to exact target
            _MOUSE_CONTROLLER.position = (x, y)
            time.sleep(0.05)
            
            # Re-verify position
            actual_x, actual_y = _MOUSE_CONTROLLER.position
            error_distance = math.sqrt((actual_x - x)**2 + (actual_y - y)**2)
        
        # Determine success (within 10 pixels is acceptable)
        success = error_distance < 10
        
        # Log if movement was not fully accurate
        if not success:
            logger.log_error(
                error_type="mouse_movement_accuracy_warning",
                error_message=f"Mouse movement to ({x}, {y}) was not fully accurate. Final position: ({actual_x}, {actual_y}), error: {error_distance:.2f}px",
                context={
                    "function": "move_mouse_absolute_validated",
                    "target": (x, y),
                    "actual": (actual_x, actual_y),
                    "error_distance": error_distance
                }
            )
        
        return {
            "success": success,
            "target": (x, y),
            "actual": (actual_x, actual_y),
            "error_distance": round(error_distance, 2),
            "message": f"Moved to ({actual_x}, {actual_y}), target was ({x}, {y}), error: {round(error_distance, 2)}px"
        }
        
    except Exception as e:
        # Catch-all for any unexpected errors during mouse movement
        error_msg = f"Unexpected error during validated mouse movement: {str(e)}"
        logger.log_error(
            error_type="validated_mouse_movement_unexpected_error",
            error_message=error_msg,
            context={
                "function": "move_mouse_absolute_validated",
                "target_x": x,
                "target_y": y,
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc()
            }
        )
        return {
            "success": False,
            "target": (x, y),
            "actual": _MOUSE_CONTROLLER.position,
            "error_distance": -1,
            "message": error_msg,
            "error": error_msg,
            "user_message": f"❌ Mouse movement failed unexpectedly: {str(e)}",
            "suggestion": "Check system permissions for mouse control. On macOS: System Settings → Privacy & Security → Accessibility"
        }
    
def left_click_mouse(count: int = 1):
    """
    Left click the mouse button with error handling.
    
    Args:
        count: Number of times to click (default: 1)
    
    Returns:
        dict with result message or error details
    """
    try:
        _MOUSE_CONTROLLER.click(mouse.Button.left, count)
        return {"result": f"left clicked the mouse button {count} times"}
    except Exception as e:
        error_msg = f"Left click failed: {str(e)}"
        logger.log_error(
            error_type="left_click_failed",
            error_message=error_msg,
            context={
                "function": "left_click_mouse",
                "count": count,
                "error_type": type(e).__name__
            }
        )
        return {
            "error": error_msg,
            "user_message": f"❌ Failed to click: {str(e)}",
            "suggestion": "Check system permissions for mouse control. On macOS: System Settings → Privacy & Security → Accessibility"
        }

def left_click_mouse_verified(count: int = 1):
    """
    Click with pre-click position verification and error handling.
    
    Captures and returns the mouse position at the time of click,
    providing detailed feedback on click execution.
    
    Args:
        count: Number of times to click (default: 1)
    
    Returns:
        dict with:
        - result: string description of the click action
        - position: tuple of (x, y) coordinates where click occurred
        - click_count: number of clicks performed
        - error: (optional) error message if click failed
        - user_message: (optional) user-friendly error explanation
        - suggestion: (optional) suggestion for fixing the issue
    """
    try:
        # Capture position before clicking
        pos_x, pos_y = _MOUSE_CONTROLLER.position
        
        # Perform the click
        _MOUSE_CONTROLLER.click(mouse.Button.left, count)
        
        # Return detailed feedback
        return {
            "result": f"Clicked {count} time(s) at position ({pos_x}, {pos_y})",
            "position": (pos_x, pos_y),
            "click_count": count
        }
    except Exception as e:
        error_msg = f"Verified click failed: {str(e)}"
        logger.log_error(
            error_type="verified_click_failed",
            error_message=error_msg,
            context={
                "function": "left_click_mouse_verified",
                "count": count,
                "error_type": type(e).__name__
            }
        )
        return {
            "error": error_msg,
            "user_message": f"❌ Failed to perform verified click: {str(e)}",
            "suggestion": "Check system permissions for mouse control. On macOS: System Settings → Privacy & Security → Accessibility",
            "click_count": 0
        }

def right_click_mouse(count: int = 1):
    """Right click the mouse button once."""
    _MOUSE_CONTROLLER.click(mouse.Button.right, count)
    return {"result": f"right clicked the mouse button {count} times"}

def scroll_mouse_by(dx: int, dy: int):
    """
    Scroll the mouse by the given amounts with error handling.
    
    Args:
        dx: horizontal scroll steps (positive -> right)
        dy: vertical scroll steps (positive -> up)
    
    Returns:
        dict with result message or error details
    """
    try:
        mouse.Controller().scroll(dx, dy)
        return {"result": f"scrolled by dx={dx}, dy={dy}"}
    except Exception as e:
        error_msg = f"Scroll failed: {str(e)}"
        logger.log_error(
            error_type="scroll_failed",
            error_message=error_msg,
            context={
                "function": "scroll_mouse_by",
                "dx": dx,
                "dy": dy,
                "error_type": type(e).__name__
            }
        )
        return {
            "error": error_msg,
            "user_message": f"❌ Failed to scroll: {str(e)}",
            "suggestion": "Check system permissions for mouse control. On macOS: System Settings → Privacy & Security → Accessibility"
        }


def press_key(key: str):
    """
    Press the given key with error handling.
    
    Args:
        key: String name of the key to press (special keys or regular characters)
    
    Returns:
        dict with result message or error details
    """
    special_keys = {
        "space": keyboard.Key.space,
        "enter": keyboard.Key.enter,
        "shift": keyboard.Key.shift,
        "ctrl": keyboard.Key.ctrl,
        "alt": keyboard.Key.alt,
        "cmd": keyboard.Key.cmd,
        "tab": keyboard.Key.tab,
        "esc": keyboard.Key.esc,
        "up": keyboard.Key.up,
        "down": keyboard.Key.down,
        "left": keyboard.Key.left,
        "right": keyboard.Key.right,
        "backspace": keyboard.Key.backspace,
        "delete": keyboard.Key.delete,
    }
    
    try:
        if key in special_keys:
            keyboard.Controller().press(special_keys[key])
        else:
            keyboard.Controller().press(key)
        return {"result": f"pressed the key {key}"}
    except Exception as e:
        error_msg = f"Key press failed: {str(e)}"
        logger.log_error(
            error_type="key_press_failed",
            error_message=error_msg,
            context={
                "function": "press_key",
                "key": key,
                "error_type": type(e).__name__
            }
        )
        return {
            "error": error_msg,
            "user_message": f"❌ Failed to press key '{key}': {str(e)}",
            "suggestion": "Check system permissions for keyboard control. On macOS: System Settings → Privacy & Security → Accessibility"
        }

import platform
import time
from pynput import keyboard

def type_text(text: str, select_all_first: bool = False):
    """
    Type text at the current cursor position with comprehensive error handling.
    If select_all_first is True, will select all existing text (Cmd/Ctrl+A, Delete) before typing.
    
    Args:
        text: The text to type
        select_all_first: If True, select and replace existing text
    
    Returns:
        dict with result message or error details with suggestions
    """
    _keyboard = keyboard.Controller()
    system = platform.system().lower()

    try:
        if select_all_first:
            modifier = keyboard.Key.cmd if system == "darwin" else keyboard.Key.ctrl

            # Select all (Cmd/Ctrl + A)
            with _keyboard.pressed(modifier):
                _keyboard.press('a')
                _keyboard.release('a')
            time.sleep(0.05)

            # Delete selected text
            _keyboard.press(keyboard.Key.delete)
            _keyboard.release(keyboard.Key.delete)
            time.sleep(0.05)

        # Type new text
        _keyboard.type(text)

        return {
            "result": f"Typed: '{text}'" + (" (replaced existing text)" if select_all_first else "")
        }

    except Exception as e:
        error_msg = f"Failed to type text: {str(e)}"
        logger.log_error(
            error_type="type_text_failed",
            error_message=error_msg,
            context={
                "function": "type_text",
                "text_length": len(text),
                "select_all_first": select_all_first,
                "error_type": type(e).__name__
            }
        )
        
        # Provide specific suggestions based on error type
        if "permission" in str(e).lower() or "access" in str(e).lower():
            suggestion = "Check system permissions for keyboard control. On macOS: System Settings → Privacy & Security → Accessibility"
        elif "character" in str(e).lower() or "unicode" in str(e).lower():
            suggestion = "The text contains characters that cannot be typed. Try using simpler characters or check keyboard layout."
        else:
            suggestion = "Ensure the cursor is in a text input field and the application has focus."
        
        return {
            "error": error_msg,
            "user_message": f"❌ Failed to type text: {str(e)}",
            "suggestion": suggestion
        }


def select_all_and_replace(text: str):
    """
    Select all text in the current field (Cmd/Ctrl+A) and replace it with new text.
    Works on macOS, Windows, and Linux.
    """
    return type_text(text, select_all_first=True)

def press_key_combination(keys: list):
    """
    Press a combination of keys simultaneously with comprehensive error handling.
    
    Args:
        keys: list of key names to press together
        Example: ["cmd", "c"] for copy, ["cmd", "v"] for paste
    
    Returns:
        dict with result message or error details with suggestions
    """
    _keyboard = keyboard.Controller()
    special_keys = {
        "space": keyboard.Key.space,
        "enter": keyboard.Key.enter,
        "shift": keyboard.Key.shift,
        "ctrl": keyboard.Key.ctrl,
        "alt": keyboard.Key.alt,
        "cmd": keyboard.Key.cmd,
        "tab": keyboard.Key.tab,
        "esc": keyboard.Key.esc,
        "backspace": keyboard.Key.backspace,
        "delete": keyboard.Key.delete,
    }
    
    try:
        # Validate input
        if not keys or len(keys) == 0:
            error_msg = "No keys provided for key combination"
            logger.log_error(
                error_type="key_combination_invalid_input",
                error_message=error_msg,
                context={"function": "press_key_combination", "keys": keys}
            )
            return {
                "error": error_msg,
                "user_message": "❌ No keys specified for key combination.",
                "suggestion": "Provide at least one key. Example: ['cmd', 'c'] for copy"
            }
        
        # Convert string keys to Key objects
        key_objects = []
        for key in keys:
            if key in special_keys:
                key_objects.append(special_keys[key])
            else:
                key_objects.append(key)
        
        # Press all keys
        for key in key_objects[:-1]:
            _keyboard.press(key)
        
        # Press and release the last key
        _keyboard.press(key_objects[-1])
        _keyboard.release(key_objects[-1])
        
        # Release all modifier keys in reverse order
        for key in reversed(key_objects[:-1]):
            _keyboard.release(key)
        
        return {"result": f"Pressed key combination: {' + '.join(keys)}"}
        
    except Exception as e:
        error_msg = f"Failed to press key combination: {str(e)}"
        logger.log_error(
            error_type="key_combination_failed",
            error_message=error_msg,
            context={
                "function": "press_key_combination",
                "keys": keys,
                "error_type": type(e).__name__
            }
        )
        
        # Provide specific suggestions
        if "permission" in str(e).lower() or "access" in str(e).lower():
            suggestion = "Check system permissions for keyboard control. On macOS: System Settings → Privacy & Security → Accessibility"
        else:
            suggestion = f"Verify the key combination is valid. Available special keys: {', '.join(special_keys.keys())}"
        
        return {
            "error": error_msg,
            "user_message": f"❌ Failed to press key combination {' + '.join(keys)}: {str(e)}",
            "suggestion": suggestion
        }

def hold_left_mouse_button():
    """Hold the left mouse button down."""
    mouse.Controller().press(mouse.Button.left)
    return {"result": f"held the left mouse button down"}
def release_left_mouse_button():
    """Release the left mouse button."""
    mouse.Controller().release(mouse.Button.left)
    return {"result": f"released the left mouse button"}
def hold_right_mouse_button():
    """Hold the right mouse button down."""
    mouse.Controller().press(mouse.Button.right)
    return {"result": f"held the right mouse button down"}
def release_right_mouse_button():
    """Release the right mouse button."""
    mouse.Controller().release(mouse.Button.right)
    return {"result": f"released the right mouse button"}
# def get_screen_with_grid():
#     """Capture the screen, draw a 25px grid, and mark coordinates."""
#     sct = mss.mss()
#     monitor = sct.monitors[0]
#     screenshot = sct.grab(monitor)
#     img = PIL.Image.frombytes("RGB", screenshot.size, screenshot.rgb)
#     draw = ImageDraw.Draw(img)

#     width, height = img.size
#     step = 25
#     font_color = (0, 255, 0)
#     grid_color = (50, 255, 50)
#     text_offset = 5

#     # Draw vertical and horizontal grid lines every 50px
#     for x in range(0, width, step):
#         draw.line([(x, 0), (x, height)], fill=grid_color, width=1)
#         if (x // step) % 2 == 0:  # Label every alternate vertical line
#             draw.text((x + text_offset, 5), str(x), fill=font_color)

#     for y in range(0, height, step):
#         draw.line([(0, y), (width, y)], fill=grid_color, width=1)
#         if (y // step) % 2 == 0:  # Label every alternate horizontal line
#             draw.text((5, y + text_offset), str(y), fill=font_color)

#     # Optional: highlight current mouse cursor
#     mx, my = pyautogui.position()
#     cursor_color = (255, 80, 0)
#     draw.ellipse(
#         (mx - 6, my - 6, mx + 6, my + 6),
#         fill=cursor_color,
#         outline=(255, 200, 0),
#         width=2,
#     )

#     # Save for debugging (optional)
#     import time
#     img.save(f"screen_grid_{int(time.time())}.jpeg", format="JPEG", quality=70, optimize=True)

#     # Prepare for streaming
#     image_io = io.BytesIO()
#     img.save(image_io, format="jpeg", quality=65, optimize=True)
#     image_io.seek(0)
#     return {
#         "mime_type": "image/jpeg",
#         "data": base64.b64encode(image_io.read()).decode(),
#     }


func_names_dict = {
    "move_mouse_relative": move_mouse_relative,
    "move_mouse_absolute": move_mouse_absolute,
    "move_mouse_absolute_validated": move_mouse_absolute_validated,
    "left_click_mouse": left_click_mouse,
    "left_click_mouse_verified": left_click_mouse_verified,
    "right_click_mouse": right_click_mouse,
    "hold_left_mouse_button": hold_left_mouse_button,
    "release_left_mouse_button": release_left_mouse_button,
    "hold_right_mouse_button": hold_right_mouse_button,
    "release_right_mouse_button": release_right_mouse_button,
    "scroll_mouse_by": scroll_mouse_by,
    "press_key": press_key,
    "type_text": type_text,
    "select_all_and_replace": select_all_and_replace,
    "press_key_combination": press_key_combination,
    "get_screen_size": get_screen_size,
    "get_mouse_position": get_mouse_position,
    "generate_quiz_from_screen": generate_quiz_from_screen,
    # "get_screen_with_grid": get_screen_with_grid
    "smart_detect_screen_coordinates": smart_detect_screen_coordinates,
    "smart_detect_screen_coordinates_with_retry": smart_detect_screen_coordinates_with_retry
}



tools = [
   types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="move_mouse_relative",
            description="Move the mouse to the given coordinates.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={"x": types.Schema(type=types.Type.NUMBER), "y": types.Schema(type=types.Type.NUMBER)})
        ),
        types.FunctionDeclaration(
            name="hold_left_mouse_button",
            description="Hold the left mouse button down.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),
        types.FunctionDeclaration(
            name="release_left_mouse_button",
            description="Release the left mouse button.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),
        types.FunctionDeclaration(
            name="hold_right_mouse_button",
            description="Hold the right mouse button down.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),
        types.FunctionDeclaration(
            name="release_right_mouse_button",
            description="Release the right mouse button.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),
        types.FunctionDeclaration(
            name="move_mouse_absolute",
            description="""Move the mouse to exact screen coordinates with validation.
    
IMPORTANT: 
- Always call get_screen_size() first to know screen dimensions
- Always call smart_detect_screen_coordinates() to get coordinates before using this
- This function validates coordinates and verifies final position
- Returns success status and actual final position
- If movement fails, the response will contain error details

WORKFLOW: 
1. detect coordinates → 2. move mouse → 3. verify position → 4. click

The function performs:
- Bounds checking to ensure coordinates are within screen dimensions
- Smooth movement with easing for natural cursor trajectory
- Position verification after movement completion
- Corrective movement if position is off by more than 5 pixels
- Detailed feedback with success status and error distance metrics

Use this for precise mouse positioning before clicking UI elements.""",
            parameters=types.Schema(
                type=types.Type.OBJECT, 
                properties={
                    "x": types.Schema(
                        type=types.Type.NUMBER,
                        description="X coordinate (horizontal, from left edge of screen). Must be within screen bounds."
                    ), 
                    "y": types.Schema(
                        type=types.Type.NUMBER,
                        description="Y coordinate (vertical, from top edge of screen). Must be within screen bounds."
                    )
                },
                required=["x", "y"]
            )
        ),
        types.FunctionDeclaration(
            name="left_click_mouse",
            description= "Left click the mouse button once. count is the number of times to click the mouse button. count is an optional parameter and default is 1.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={"count": types.Schema(type=types.Type.NUMBER)})
        ),
        types.FunctionDeclaration(
            name="left_click_mouse_verified",
            description="Left click with position verification. Captures and returns the exact mouse position at the time of click, providing detailed feedback on click execution. Use this when you need confirmation of where the click occurred.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={"count": types.Schema(type=types.Type.NUMBER, description="Number of times to click (default: 1)")})
        ),
        types.FunctionDeclaration(
            name="right_click_mouse",
            description="Right click the mouse button once.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={"count": types.Schema(type=types.Type.NUMBER)})
        ),
        types.FunctionDeclaration(
            name="scroll_mouse_by",
            description="Scroll the mouse by the given amounts. dx is the horizontal scroll steps (positive -> right) and dy is the vertical scroll steps (positive -> up).",
            parameters=types.Schema(type=types.Type.OBJECT, properties={"dx": types.Schema(type=types.Type.NUMBER), "dy": types.Schema(type=types.Type.NUMBER)})
        ),
        types.FunctionDeclaration(
            name="press_key",
            description="Press the given key. key is a string of the key to press. key is a special key or a regular key. special keys are space, enter, shift, ctrl, alt, cmd, tab, esc, up, down, left, right, backspace, delete. regular keys are the keys on the keyboard.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={"key": types.Schema(type=types.Type.STRING)})
        ),
        types.FunctionDeclaration(
            name="type_text",
            description="Type text at the current cursor position. If select_all_first is True, will select all existing text (Cmd+A) before typing to replace it. Very useful for filling forms or replacing text in input fields.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={
                "text": types.Schema(type=types.Type.STRING, description="The text to type"),
                "select_all_first": types.Schema(type=types.Type.BOOLEAN, description="If True, select all text before typing (replaces existing text). Default is False.")
            }, required=["text"])
        ),
        types.FunctionDeclaration(
            name="select_all_and_replace",
            description="Select all text in the current field (Cmd+A) and replace it with new text. Perfect for replacing text in input fields, text boxes, or editors.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={
                "text": types.Schema(type=types.Type.STRING, description="The new text to replace with")
            }, required=["text"])
        ),
        types.FunctionDeclaration(
            name="press_key_combination",
            description="Press a combination of keys simultaneously. Useful for keyboard shortcuts like Cmd+C (copy), Cmd+V (paste), Cmd+S (save), etc. Keys are pressed in order and released in reverse order.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={
                "keys": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING), description="List of keys to press together. Example: ['cmd', 'c'] for copy, ['cmd', 'v'] for paste, ['cmd', 'shift', 's'] for save as.")
            }, required=["keys"])
        ),
        types.FunctionDeclaration(
            name="get_screen_size",
            description="Get the screen size.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),
        types.FunctionDeclaration(
            name="get_mouse_position",
            description="Get the mouse position.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),
        # types.FunctionDeclaration(
        #     name="get_screen_with_grid",
        #     description="Get the screen with a custom visible cursor overlay and a 25px grid. This function is used to help the screen capture and the mouse position. Call this function before decideding on coordinates to move the mouse to.",
        #     parameters=types.Schema(type=types.Type.OBJECT, properties={})
        # )
        types.FunctionDeclaration(
            name="smart_detect_screen_coordinates",
            description="""Detect UI element coordinates using AI vision with enhanced accuracy.

CRITICAL: ALWAYS use this before clicking on any UI element. Never guess coordinates.

This function:
- Captures screen with multiple grid overlays (10px fine grid, 50px coarse grid)
- Uses Gemini 2.5 Pro to analyze and locate the element with high precision
- Returns precise coordinates with validation
- Validates coordinates are within screen bounds
- Saves screenshots for debugging

WORKFLOW POSITION:
This is ALWAYS step 1 before any click operation:
1. smart_detect_screen_coordinates() ← YOU ARE HERE
2. move_mouse_absolute()
3. verify position
4. click

TIPS FOR BETTER ACCURACY:
- Be specific: "Chrome icon in dock" not just "Chrome"
- Include position hints: "search box at top right corner"
- Mention visual features: "blue button with white text saying Submit"
- Describe context: "the second item in the dropdown menu"
- For small elements, describe surrounding context

EXAMPLES:
✓ Good: "the red close button in the top-left corner of the Safari window"
✓ Good: "the search input field with placeholder text 'Search...' in the navigation bar"
✗ Bad: "button" (too vague)
✗ Bad: "the thing" (not descriptive)

Returns: Dictionary with 'x' and 'y' coordinates, or 'error' message if detection fails.""",
            parameters=types.Schema(
                type=types.Type.OBJECT, 
                properties={
                    "prompt": types.Schema(
                        type=types.Type.STRING,
                        description="Detailed description of the UI element to find. Be specific about visual appearance, position, text content, and surrounding context for best accuracy."
                    )
                },
                required=["prompt"]
            )
        ),
        types.FunctionDeclaration(
            name="generate_quiz_from_screen",
            description="Generate a fun quiz based on what's currently visible on screen! Creates 2 questions about screen content and 1 creative/fun question. Perfect for entertainment, learning, or testing knowledge about what's displayed. The AI will analyze the screen and create engaging questions.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        )
    ]
   )
]




CONFIG = {"response_modalities": ["AUDIO"], "tools": tools
,
    "system_instruction": """You are an assistant that controls the user's mouse and keyboard based on voice commands.

=== CRITICAL WORKFLOW FOR CLICKING UI ELEMENTS ===

When the user asks to click on something, ALWAYS follow this EXACT sequence:

1. DETECT COORDINATES:
   - Call: smart_detect_screen_coordinates(prompt="clear description of the element")
   - Wait for response with coordinates
   - Verify coordinates are valid (within screen bounds)
   - If detection fails, ask user for clarification

2. VERIFY DETECTION:
   - Confirm you received valid coordinates (x=NUMBER, y=NUMBER format)
   - If coordinates seem wrong (e.g., x=0, y=0), retry detection with better description
   - Announce coordinates to user: "I found it at position x, y"

3. MOVE MOUSE:
   - Call: move_mouse_absolute(x, y) using the detected coordinates
   - Wait for movement completion
   - Check the response for success confirmation
   - If movement failed, report error and stop

4. VERIFY POSITION:
   - Call: get_mouse_position() to confirm mouse is at target
   - Compare actual position with target position
   - If position is off by more than 10 pixels, retry movement
   - Announce: "Mouse is now at the target position"

5. CLICK:
   - Call: left_click_mouse()
   - Confirm click was executed
   - Announce: "Clicked on [element name]"

=== ERROR HANDLING ===

If ANY step fails:
- Stop the workflow immediately
- Explain what went wrong to the user
- Suggest alternatives (e.g., "I couldn't find that element. Can you describe it differently?")
- Do NOT proceed to the next step

If coordinates seem incorrect:
- Values like (0, 0) or coordinates at screen edges are suspicious
- Ask user: "I detected coordinates at x, y. Does that seem right?"
- Offer to retry with a better description

=== GENERAL RULES ===

- NEVER guess coordinates - always use smart_detect_screen_coordinates
- NEVER skip the movement step - mouse must move before clicking
- ALWAYS verify each step completed successfully
- ALWAYS provide verbal feedback at each step
- Break complex tasks into simple, sequential steps
- If unsure, ask the user for clarification
- Use get_screen_size() at the start of a session to know screen dimensions

=== TOOL USAGE PATTERNS ===

For "Click on X":
1. smart_detect_screen_coordinates(prompt="X")
2. move_mouse_absolute(x, y)
3. get_mouse_position() [verify]
4. left_click_mouse()

For "Type in the search box":
1. smart_detect_screen_coordinates(prompt="search box")
2. move_mouse_absolute(x, y)
3. left_click_mouse()
4. type_text(text="...")

For "Scroll down":
1. scroll_mouse_by(dx=0, dy=-5)  [negative dy = scroll down]

For "Copy this text":
1. press_key_combination(keys=["cmd", "c"])

=== VALIDATION ===

Before executing any action:
- Confirm you have all required information
- Verify coordinates are within screen bounds
- Check that the previous step succeeded

After executing any action:
- Verify the action completed
- Check for error messages in the response
- Confirm the system state is as expected

Remember: Accuracy is more important than speed. Take time to verify each step.
"""
}

pya = pyaudio.PyAudio()

class AudioLoop:
    def __init__(self, video_mode=DEFAULT_MODE):
        self.video_mode = video_mode

        self.audio_in_queue = None
        self.out_queue = None

        self.session = None

        self.send_text_task = None
        self.receive_audio_task = None
        self.play_audio_task = None

    async def send_text(self):
        while True:
            text = await asyncio.to_thread(
                input,
                "message > ",
            )
            if text.lower() == "q":
                break
            await self.session.send_client_content(
    turns=[{'role': 'user', 'parts': [{'text': text or "."}]}],
    turn_complete=True
)

    def _get_frame(self, cap):
        # Read the frameq
        ret, frame = cap.read()
        # Check if the frame was read successfully
        if not ret:
            return None
        # Fix: Convert BGR to RGB color space
        # OpenCV captures in BGR but PIL expects RGB format
        # This prevents the blue tint in the video feed
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = PIL.Image.fromarray(frame_rgb)  # Now using RGB frame
        img.thumbnail([1024, 1024])
        
        image_io = io.BytesIO()
        img.save(image_io, format="jpeg", quality=85)
        image_io.seek(0)

        mime_type = "image/jpeg"
        image_bytes = image_io.read()
        return {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode()}

    async def get_frames(self):
        # This takes about a second, and will block the whole program
        # causing the audio pipeline to overflow if you don't to_thread it.
        cap = await asyncio.to_thread(
            cv2.VideoCapture, 0
        )  # 0 represents the default camera

        while True:
            frame = await asyncio.to_thread(self._get_frame, cap)
            if frame is None:
                break

            await asyncio.sleep(0.1)

            await self.out_queue.put(frame)

        # Release the VideoCapture object
        cap.release()



    def _get_screen(self):
        """Capture screen and draw a custom visible cursor overlay."""
        with mss.mss() as sct:
            monitor = sct.monitors[0]

            # Grab the screen
            screenshot = sct.grab(monitor)

            # Convert to a Pillow image
            img = PIL.Image.frombytes("RGB", screenshot.size, screenshot.rgb)

            # === Draw the cursor overlay ===
            mx, my = pyautogui.position()
            draw = ImageDraw.Draw(img)

            # Choose cursor style
            cursor_color = (255, 80, 0)  # Orange-red
            ring_radius = 12
            inner_radius = 4

            # Glowing ring effect
            for r in range(ring_radius + 6, ring_radius, -2):
                draw.ellipse(
                    (mx - r, my - r, mx + r, my + r),
                    outline=(255, 120, 0),
                    width=1
                )

            # Main cursor circle
            draw.ellipse(
                (mx - inner_radius, my - inner_radius, mx + inner_radius, my + inner_radius),
                fill=cursor_color
            )

            # Optional: crosshair center
            draw.line((mx - 6, my, mx + 6, my), fill=(255, 200, 0), width=2)
            draw.line((mx, my - 6, mx, my + 6), fill=(255, 200, 0), width=2)

            # === Optimize for streaming ===
            image_io = io.BytesIO()
            img.save(image_io, format="JPEG", quality=85)
            image_io.seek(0)

            return {
                "mime_type": "image/jpeg",
                "data": base64.b64encode(image_io.read()).decode(),
            }

    async def get_screen(self):

        while True:
            frame = await asyncio.to_thread(self._get_screen)
            if frame is None:
                break

            await asyncio.sleep(2.0)

            await self.out_queue.put(frame)

    async def send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def listen_audio(self):
        mic_info = pya.get_default_input_device_info()
        self.audio_stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=SEND_SAMPLE_RATE,
            input=True,
            input_device_index=mic_info["index"],
            frames_per_buffer=CHUNK_SIZE,
        )
        if __debug__:
            kwargs = {"exception_on_overflow": False}
        else:
            kwargs = {}
        while True:
            data = await asyncio.to_thread(self.audio_stream.read, CHUNK_SIZE, **kwargs)
            await self.out_queue.put({"data": data, "mime_type": "audio/pcm"})

    async def receive_audio(self,tg: asyncio.TaskGroup,session):
        "Background task to reads from the websocket and write pcm chunks to the output queue"
        while True:
            turn = self.session.receive()
            response = None
            
            # Start a new Opik trace for each conversation turn (if Opik is available)
            trace = None
            if opik_client:
                try:
                    trace = opik_client.trace(
                        name="Voice Assistant Turn",
                        input={"type": "audio_conversation"},
                        metadata={
                            "model": MODEL,
                            "video_mode": self.video_mode
                        }
                    )
                except Exception as e:
                    print(f"⚠️  Failed to create Opik trace: {e}")
            
            try:
                async for response in turn:
                    if data := response.data:
                        self.audio_in_queue.put_nowait(data)
                        continue
                    elif text := response.text:
                        print(text, end="")
                        # Log text responses to Opik
                        if trace:
                            try:
                                trace.update(
                                    output={"text": text},
                                    metadata={"response_type": "text"}
                                )
                            except Exception as e:
                                print(f"⚠️  Failed to update Opik trace: {e}")
                    elif tool_call := response.tool_call:
                        await self.handle_tool_call(session, tool_call, trace)
                    elif setup_complete := response.setup_complete:
                        print(response)
                    elif turn_complete := response.server_content.turn_complete:
                        print(response)
                        if trace:
                            try:
                                trace.update(metadata={"turn_complete": True})
                            except Exception as e:
                                print(f"⚠️  Failed to update Opik trace: {e}")
                    elif generation_complete := response.server_content.generation_complete:
                        print(response)
                    elif response_complete := response.server_content.interrupted:
                        print(response)
                    elif len(response.server_content.model_turn.parts) > 0:
                        print(response)
                    
                    else:
                        print('>>> ', response)
            except Exception as e:
                print("Response: ", response)
                print('>>> Error: ', e)
                # Log errors to Opik
                if trace:
                    try:
                        trace.update(
                            output={"error": str(e)},
                            metadata={"error_type": type(e).__name__}
                        )
                    except Exception as opik_error:
                        print(f"⚠️  Failed to log error to Opik: {opik_error}")
            finally:
                # End the trace
                if trace:
                    try:
                        trace.end()
                    except Exception as e:
                        print(f"⚠️  Failed to end Opik trace: {e}")
                        
            while not self.audio_in_queue.empty():
                self.audio_in_queue.get_nowait()

    async def play_audio(self):
        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=RECEIVE_SAMPLE_RATE,
            output=True,
        )
        while True:
            bytestream = await self.audio_in_queue.get()
            await asyncio.to_thread(stream.write, bytestream)

        
    async def handle_tool_call(self, session, tool_call, trace=None):
        """
        Handle tool calls from the AI with comprehensive logging.
        
        Logs:
        - All tool calls with parameters and results
        - Errors with full context
        - Timestamps for all operations
        - Special handling for coordinate detection and mouse movements
        - Opik tracing for observability
        """
        print("Tool call: ", tool_call)
        function_responses = []
        
        for fc in tool_call.function_calls:
            # Record start time for execution duration tracking
            start_time = time.time()
            
            # Create an Opik span for this tool call
            span = None
            if trace:
                span = trace.span(
                    name=f"Tool: {fc.name}",
                    input={"function": fc.name, "arguments": fc.args},
                    type="tool"
                )
            
            try:
                # Execute the tool function
                result = func_names_dict[fc.name](**fc.args)
                
                # Calculate execution time
                execution_time = time.time() - start_time
                
                # Log to Opik span
                if span:
                    span.update(
                        output={"result": result},
                        metadata={
                            "execution_time_seconds": execution_time,
                            "success": "error" not in result if isinstance(result, dict) else True
                        }
                    )
                
                # Log the successful tool call
                logger.log_tool_call(
                    tool_name=fc.name,
                    args=fc.args,
                    result=result
                )
                
                # Special logging for specific tool types
                
                # Log coordinate detection with screenshot path
                if fc.name in ["smart_detect_screen_coordinates", "smart_detect_screen_coordinates_with_retry"]:
                    screenshot_path = result.get("screenshot_dir", "unknown")
                    if "error" in result:
                        logger.log_coordinate_detection(
                            prompt=fc.args.get("prompt", ""),
                            coordinates={"error": result["error"]},
                            screenshot_path=screenshot_path
                        )
                        if span:
                            span.update(metadata={"screenshot_path": screenshot_path, "detection_failed": True})
                    else:
                        logger.log_coordinate_detection(
                            prompt=fc.args.get("prompt", ""),
                            coordinates={"x": result.get("x"), "y": result.get("y")},
                            screenshot_path=screenshot_path
                        )
                        if span:
                            span.update(metadata={
                                "screenshot_path": screenshot_path,
                                "coordinates": {"x": result.get("x"), "y": result.get("y")}
                            })
                
                # Log mouse movements with verification
                elif fc.name in ["move_mouse_absolute", "move_mouse_absolute_validated"]:
                    target = (fc.args.get("x"), fc.args.get("y"))
                    actual = result.get("actual", target)
                    success = result.get("success", True)
                    
                    logger.log_mouse_movement(
                        target=target,
                        actual=actual,
                        success=success
                    )
                    
                    if span:
                        span.update(metadata={
                            "target_position": target,
                            "actual_position": actual,
                            "movement_success": success,
                            "error_distance": result.get("error_distance", 0)
                        })
                
                # Log execution time for performance monitoring
                if logger.debug_mode:
                    logger.logger.debug(
                        f"Tool '{fc.name}' executed in {execution_time:.3f}s"
                    )
                
                # End the span successfully
                if span:
                    span.end()
                
                # Create function response
                function_responses.append(types.FunctionResponse(
                    id=fc.id,
                    name=fc.name,
                    response=result,
                ))
                
            except Exception as e:
                # Calculate execution time even for failures
                execution_time = time.time() - start_time
                
                # Log to Opik span
                if span:
                    span.update(
                        output={"error": str(e)},
                        metadata={
                            "execution_time_seconds": execution_time,
                            "error_type": type(e).__name__,
                            "success": False
                        }
                    )
                    span.end()
                
                # Log the error with full context
                logger.log_error(
                    error_type=f"tool_execution_failed_{fc.name}",
                    error_message=str(e),
                    context={
                        "tool_name": fc.name,
                        "arguments": fc.args,
                        "execution_time": execution_time,
                        "error_type": type(e).__name__,
                        "traceback": traceback.format_exc()
                    }
                )
                
                # Print error to console for immediate visibility
                print(f"❌ Tool {fc.name} failed: {e}")
                
                # Create error response
                error_result = {"error": str(e)}
                function_responses.append(types.FunctionResponse(
                    id=fc.id,
                    name=fc.name,
                    response=error_result,
                ))
        
        # Send all function responses back to the session
        await session.send_tool_response(function_responses=function_responses)
        
        # Small delay to prevent race conditions
        await asyncio.sleep(0.05)
        # await session.send_client_event(event_type="turn_complete")
    async def run(self):
        try:
            async with (
                client.aio.live.connect(model=MODEL, config=CONFIG) as session,
                asyncio.TaskGroup() as tg,
            ):
                self.session = session

                self.audio_in_queue = asyncio.Queue()
                self.out_queue = asyncio.Queue(maxsize=5)

                send_text_task = tg.create_task(self.send_text())
                tg.create_task(self.send_realtime())
                tg.create_task(self.listen_audio())
                if self.video_mode == "camera":
                    tg.create_task(self.get_frames())
                elif self.video_mode == "screen":
                    tg.create_task(self.get_screen())

                tg.create_task(self.receive_audio(tg,session))
                tg.create_task(self.play_audio())

                await send_text_task
                raise asyncio.CancelledError("User requested exit")

        except asyncio.CancelledError:
            pass
        except ExceptionGroup as EG:
            self.audio_stream.close()
            traceback.print_exception(EG)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        type=str,
        default=DEFAULT_MODE,
        help="pixels to stream from",
        choices=["camera", "screen", "none"],
    )
    args = parser.parse_args()
    main = AudioLoop(video_mode=args.mode)
    asyncio.run(main.run())