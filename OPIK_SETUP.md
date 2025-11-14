# Opik Tracing Setup Guide

This voice assistant now includes **Opik tracing** for comprehensive observability of all LLM interactions and tool calls.

## What is Opik?

Opik is an open-source LLM evaluation and observability platform that helps you:
- Track all LLM calls and tool executions
- Monitor performance and costs
- Debug issues with detailed traces
- Evaluate and improve your AI applications

## Setup Options

### Option 1: Opik Cloud (Recommended for Quick Start)

1. **Create a free account** at [Comet.com](https://www.comet.com/signup?from=llm)

2. **Get your API key**:
   - Go to your Comet account settings
   - Navigate to API Keys section
   - Copy your API key

3. **Configure environment variables** in your `.env` file:
   ```bash
   OPIK_API_KEY=your_api_key_here
   OPIK_WORKSPACE=your_workspace_name
   OPIK_URL_OVERRIDE=https://www.comet.com/opik/api
   ```

4. **Run the application** - Opik tracing will be automatically enabled!

### Option 2: Self-Hosted Opik

1. **Install Docker** (if not already installed)

2. **Run Opik locally**:
   ```bash
   docker run -d -p 5173:5173 --name opik comet-ml/opik:latest
   ```

3. **Configure environment variables** in your `.env` file:
   ```bash
   OPIK_URL_OVERRIDE=http://localhost:5173/api
   ```

4. **Access the UI** at http://localhost:5173

### Option 3: Run Without Opik

If you don't want to use Opik tracing, simply don't set the `OPIK_API_KEY` environment variable. The application will run normally without tracing.

## What Gets Traced?

With Opik enabled, you'll see:

### 1. **Conversation Turns**
- Each voice interaction creates a trace
- Input: Audio conversation metadata
- Output: AI responses and actions taken
- Metadata: Model used, video mode, completion status

### 2. **Tool Calls**
- Every tool execution is logged as a span
- Function name and arguments
- Execution results
- Performance metrics (execution time)
- Success/failure status

### 3. **Special Tool Tracking**

**Coordinate Detection:**
- Screenshot paths for debugging
- Detected coordinates (x, y)
- Detection success/failure
- Error messages if detection fails

**Mouse Movements:**
- Target coordinates
- Actual final position
- Movement accuracy (error distance)
- Success status

### 4. **Error Tracking**
- All errors are logged with full context
- Error type and message
- Stack traces
- Function arguments at time of failure

## Viewing Your Traces

### Opik Cloud
1. Log in to [Comet.com](https://www.comet.com)
2. Navigate to your Opik project
3. View traces in the dashboard

### Self-Hosted
1. Open http://localhost:5173
2. Browse your traces and spans
3. Analyze performance and debug issues

## Example Trace Structure

```
Voice Assistant Turn (Trace)
├── Tool: smart_detect_screen_coordinates (Span)
│   ├── Input: {function: "smart_detect_screen_coordinates", arguments: {prompt: "Chrome icon"}}
│   ├── Output: {result: {x: 450, y: 320}}
│   └── Metadata: {execution_time: 2.3s, screenshot_path: "screens_123/", coordinates: {x: 450, y: 320}}
│
├── Tool: move_mouse_absolute (Span)
│   ├── Input: {function: "move_mouse_absolute", arguments: {x: 450, y: 320}}
│   ├── Output: {result: "Mouse moved to (450, 320)"}
│   └── Metadata: {execution_time: 0.1s, target: [450, 320], actual: [450, 321], error_distance: 1.0}
│
└── Tool: left_click_mouse (Span)
    ├── Input: {function: "left_click_mouse", arguments: {count: 1}}
    ├── Output: {result: "Clicked 1 time(s)"}
    └── Metadata: {execution_time: 0.05s}
```

## Benefits

1. **Debugging**: See exactly what the AI is doing and why
2. **Performance**: Track execution times for each tool
3. **Reliability**: Monitor success rates and error patterns
4. **Optimization**: Identify slow operations and bottlenecks
5. **Audit Trail**: Complete history of all AI actions

## Documentation

- [Opik Documentation](https://www.comet.com/docs/opik/)
- [Opik GitHub](https://github.com/comet-ml/opik)
- [Tracing Guide](https://www.comet.com/docs/opik/tracing/log_traces)

## Troubleshooting

**"Opik initialization warning"**
- Check that your API key is correct
- Verify network connectivity
- For self-hosted: ensure Docker container is running

**Traces not appearing**
- Wait a few seconds for traces to sync
- Check your workspace name is correct
- Verify the OPIK_URL_OVERRIDE is set correctly

**Performance impact**
- Opik tracing has minimal overhead (~10-50ms per trace)
- Traces are sent asynchronously
- No impact on real-time voice interaction
