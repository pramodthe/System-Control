 # Allow system to settle
    
    # Verify final position
    actual_x, actual_y = _MOUSE_CONTROLLER.position
    error_distance = math.sqrt((actual_x - x)**2 + (actual_y - y)**2)
    
    # Corrective movement if needed
    if error_distance > 5:  # More than 5 pixels off
        _MOUSE_CONTROLLER.position = (x, y)
        time.sleep(0.05)
        actual_x, actual_y = _MOUSE_CONTROLLER.position
        error_distance = math.sqrt((actual_x - x)**2 + (actual_y - y)**2)
    
    return {
        "success": error_distance < 10,
        "target": (x, y),
        "actual": (actual_x, actual_y),
        "error_distance": round(error_distance, 2),
        "message": f"Moved to ({actual_x}, {actual_y}), target was ({x}, {y})"
    }
```

#### 2.2 Click with Position Verification
```python
def left_click_mouse_verified(count=1):
    """
    Click with pre-click position verification.
    
    Returns verification that mouse is in expected position before clicking.
    """
    pos_x, pos_y = _MOUSE_CONTROLLER.position
    
    _MOUSE_CONTROLLER.click(mouse.Button.left, count)
    
    return {
        "result": f"Clicked {count} time(s) at position ({pos_x}, {pos_y})",
        "position": (pos_x, pos_y),
        "click_count": count
    }
```

### 3. Enhanced AI System Instructions

**Current Issues:**
- Instructions are somewhat vague
- No explicit error handling guidance
- Missing validation steps

**Improvements:**

```python
ENHANCED_SYSTEM_INSTRUCTION = """You are an assistant that controls the user's mouse and keyboard based on voice commands.

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
```

### 4. Error Handling and Logging System

**Improvements:**

#### 4.1 Structured Logging
```python
import logging
import json
from datetime import datetime

class VoiceAssistantLogger:
    def __init__(self, debug_mode=False):
        self.debug_mode = debug_mode
        self.setup_logging()
    
    def setup_logging(self):
        level = logging.DEBUG if self.debug_mode else logging.INFO
        logging.basicConfig(
            level=level,
            format='%(asctime)s [%(levelname)s] %(message)s',
            handlers=[
                logging.FileHandler('voice_assistant.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger('VoiceAssistant')
    
    def log_tool_call(self, tool_name, args, result):
        """Log every tool execution with full details."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "tool": tool_name,
            "args": args,
            "result": result,
            "success": "error" not in str(result).lower()
        }
        self.logger.info(f"TOOL_CALL: {json.dumps(log_entry)}")
    
    def log_coordinate_detection(self, prompt, coordinates, screenshot_path):
        """Log coordinate detection attempts."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "prompt": prompt,
            "coordinates": coordinates,
            "screenshot": screenshot_path
        }
        self.logger.info(f"COORD_DETECT: {json.dumps(log_entry)}")
    
    def log_mouse_movement(self, target, actual, success):
        """Log mouse movements with verification."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "target": target,
            "actual": actual,
            "success": success
        }
        self.logger.info(f"MOUSE_MOVE: {json.dumps(log_entry)}")
    
    def log_error(self, error_type, error_message, context):
        """Log errors with full context."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "error_type": error_type,
            "message": error_message,
            "context": context
        }
        self.logger.error(f"ERROR: {json.dumps(log_entry)}")

# Global logger instance
logger = VoiceAssistantLogger(debug_mode=True)
```

#### 4.2 Retry Logic
```python
import time
from functools import wraps

def retry_with_backoff(max_retries=3, initial_delay=1.0):
    """Decorator for retrying failed operations with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    result = func(*args, **kwargs)
                    if attempt > 0:
                        logger.logger.info(
                            f"{func.__name__} succeeded on attempt {attempt + 1}"
                        )
                    return result
                except Exception as e:
                    last_exception = e
                    logger.log_error(
                        error_type=f"{func.__name__}_retry",
                        error_message=str(e),
                        context={"attempt": attempt + 1, "max_retries": max_retries}
                    )
                    
                    if attempt < max_retries - 1:
                        time.sleep(delay)
                        delay *= 2  # Exponential backoff
            
            # All retries failed
            raise last_exception
        
        return wrapper
    return decorator

# Apply to critical functions
@retry_with_backoff(max_retries=2, initial_delay=0.5)
def smart_detect_screen_coordinates_with_retry(prompt):
    """Coordinate detection with automatic retry."""
    return smart_detect_screen_coordinates(prompt)
```

### 5. Enhanced Tool Declarations

Update tool declarations to include validation and feedback:

```python
types.FunctionDeclaration(
    name="move_mouse_absolute",
    description="""Move the mouse to exact screen coordinates with validation.
    
    IMPORTANT: 
    - Always call get_screen_size() first to know screen dimensions
    - Always call smart_detect_screen_coordinates() to get coordinates before using this
    - This function validates coordinates and verifies final position
    - Returns success status and actual final position
    - If movement fails, the response will contain error details
    
    Workflow: detect coordinates → move mouse → verify position → click
    """,
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "x": types.Schema(
                type=types.Type.NUMBER,
                description="X coordinate (horizontal, from left edge)"
            ),
            "y": types.Schema(
                type=types.Type.NUMBER,
                description="Y coordinate (vertical, from top edge)"
            )
        },
        required=["x", "y"]
    )
),

types.FunctionDeclaration(
    name="smart_detect_screen_coordinates",
    description="""Detect UI element coordinates using AI vision with enhanced accuracy.
    
    This function:
    - Captures screen with multiple grid overlays (10px fine, 50px coarse)
    - Uses Gemini 2.5 Pro to analyze and locate the element
    - Returns precise coordinates with validation
    - Saves screenshots for debugging
    
    ALWAYS use this before clicking on any UI element. Never guess coordinates.
    
    Tips for better accuracy:
    - Be specific: "Chrome icon in dock" not just "Chrome"
    - Include position hints: "search box at top right"
    - Mention visual features: "blue button with white text"
    """,
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "prompt": types.Schema(
                type=types.Type.STRING,
                description="Detailed description of the UI element to find"
            )
        },
        required=["prompt"]
    )
),
```

## Data Models

### Coordinate Detection Result
```python
{
    "x": int,
    "y": int,
    "valid": bool,
    "confidence": float,  # 0.0 to 1.0
    "screenshot_path": str,
    "grid_size": int,
    "detection_time": float
}
```

### Mouse Movement Result
```python
{
    "success": bool,
    "target": (int, int),
    "actual": (int, int),
    "error_distance": float,
    "movement_time": float,
    "corrective_action_taken": bool
}
```

### Tool Execution Log
```python
{
    "timestamp": str,  # ISO format
    "tool_name": str,
    "arguments": dict,
    "result": dict,
    "success": bool,
    "execution_time": float,
    "retry_count": int
}
```

## Error Handling

### Coordinate Detection Failures
- **Invalid response format**: Retry with clearer prompt
- **Out of bounds coordinates**: Reject and request new detection
- **Ambiguous element**: Ask user for more specific description
- **API timeout**: Retry with exponential backoff

### Mouse Movement Failures
- **Position verification failed**: Attempt corrective movement
- **Out of bounds target**: Reject movement and report error
- **System permission denied**: Report to user with permission instructions

### Tool Execution Failures
- **Function not found**: Log error and report to user
- **Invalid arguments**: Validate before execution
- **Exception during execution**: Catch, log, and return error response

## Testing Strategy

### Unit Testing
1. Test coordinate parsing with various formats
2. Test coordinate validation with edge cases
3. Test mouse movement with different screen sizes
4. Test easing functions for smooth movement
5. Test retry logic with simulated failures

### Integration Testing
1. Test full click workflow (detect → move → verify → click)
2. Test error recovery scenarios
3. Test with different UI elements (buttons, links, icons)
4. Test with multiple monitors
5. Test logging system captures all events

### Accuracy Testing
1. Measure coordinate detection accuracy (target vs actual)
2. Measure mouse movement precision (error distance)
3. Test with small UI elements (< 20px)
4. Test with elements at screen edges
5. Compare 10px grid vs 25px grid accuracy

### Performance Testing
1. Measure coordinate detection latency
2. Measure end-to-end click latency
3. Test with high-resolution screens
4. Test retry overhead
5. Test logging performance impact

## Implementation Notes

- All changes should be backward compatible
- Existing tool names should remain unchanged
- Add new validated versions alongside existing functions
- Use feature flags to enable/disable enhancements
- Maintain detailed logs for debugging
- Consider adding a calibration mode for first-time setup
