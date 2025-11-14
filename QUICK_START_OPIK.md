# 🚀 Opik Quick Start

## ✅ Your Setup is Complete!

Your voice assistant now has **Opik tracing** enabled for complete observability.

## Run the Application

```bash
python main_file.py --mode screen
```

You should see:
```
✅ Opik tracing initialized successfully
```

## View Your Traces

🌐 **Dashboard:** https://www.comet.com/

Look for the "Default Project" to see all your traces.

## What Gets Logged

Every time you interact with the voice assistant:

### 📝 Conversation Turns
- Your voice commands (as audio metadata)
- AI responses (text)
- Model used and settings

### 🛠️ Tool Executions
- Function name (e.g., `smart_detect_screen_coordinates`)
- Input parameters (e.g., `{prompt: "Chrome icon"}`)
- Output results (e.g., `{x: 450, y: 320}`)
- Execution time (e.g., `2.3 seconds`)

### 📸 Screenshots
- Saved paths for coordinate detection
- Grid overlays for debugging

### 🎯 Mouse Movements
- Target vs actual positions
- Accuracy metrics (error distance)

### ❌ Errors
- Full error messages
- Stack traces
- Context (what was being attempted)

## Example Commands to Try

```
"Click on Chrome"
→ See coordinate detection + mouse movement + click

"Type hello world"
→ See keyboard tool execution

"Generate a quiz"
→ See screen capture + AI analysis

"What's on my screen?"
→ See vision AI processing
```

## Verify It's Working

After running a command, check the Opik dashboard:
1. Go to https://www.comet.com/
2. Navigate to your project
3. You should see a new trace for each interaction

## Troubleshooting

### Not seeing traces?
```bash
# Test the connection
python test_opik_integration.py
```

### Want to disable tracing?
```bash
# In .env, comment out:
# OPIK_API_KEY=...
```

The app will work normally without tracing.

## Learn More

- **Full Setup Guide:** [OPIK_SETUP.md](./OPIK_SETUP.md)
- **Implementation Details:** [OPIK_IMPLEMENTATION_SUMMARY.md](./OPIK_IMPLEMENTATION_SUMMARY.md)
- **Opik Docs:** https://www.comet.com/docs/opik/

---

**Ready to go!** Start the voice assistant and watch your traces appear in real-time. 🎉
