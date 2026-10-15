# rover-client

Browser-based control UI for the SMARS Rover. Communicates with the rover-server over Socket.IO (WebSocket) — no build step, no compilation.

## Prerequisites

- Python 3 (standard library only — nothing to install)

## Run

```bash
# Auto-opens the browser:
python3 serve.py

# Or serve manually (no auto-open):
python3 -m http.server 1430 --directory src
```

Then open http://localhost:1430 in your browser.

## Connecting to the rover

Make sure `rover-server` is running on the Raspberry Pi. In the UI, enter the rover's IP address and click Connect. The client sends motor commands and mic audio over Socket.IO and receives video and audio streams from the rover directly in the browser.
