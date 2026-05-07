# SMARS Rover Client

Tauri desktop application for controlling the SMARS Telepresence Rover. Provides live video, bidirectional audio, and WASD keyboard control over WiFi.

## Prerequisites

- [Node.js](https://nodejs.org/) 18+
- [Rust toolchain](https://rustup.rs/) (required by Tauri)
- Platform-specific Tauri dependencies (see below)

### Platform Dependencies

**macOS:**
```bash
xcode-select --install
```

**Ubuntu/Debian:**
```bash
sudo apt-get install -y libwebkit2gtk-4.0-dev build-essential curl wget \
    libssl-dev libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev
```

**Windows:**
- Install [Microsoft Visual Studio C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
- Install [WebView2](https://developer.microsoft.com/en-us/microsoft-edge/webview2/)

## Installation

```bash
cd rover-client
npm install
```

## Development

Run in development mode with hot-reload:

```bash
npm run dev
```

This opens the Tauri window pointing at the local `src/` directory. Changes to HTML, CSS, and JS files are reflected immediately.

## Building for Production

Build a standalone binary for your platform:

```bash
npm run build
```

The output binary is located in `src-tauri/target/release/`. Platform-specific installers are generated in `src-tauri/target/release/bundle/`.

## Usage

1. Start the rover server on the Raspberry Pi (see `rover-server/README.md`)
2. Launch the SMARS Rover client
3. Enter the rover's IP address in the connection field (e.g., `192.168.1.50`)
4. Click **Connect**
5. Use keyboard controls to drive the rover

### Keyboard Controls

| Key | Action |
|-----|--------|
| W | Drive forward |
| S | Drive backward |
| A | Turn left |
| D | Turn right |
| Space | Emergency stop |

Hold multiple keys for combined movement. The speed slider (0-100%) scales motor output.

### Audio Controls

- **Speaker toggle** — Enable/disable rover microphone playback
- **Mic toggle** — Enable/disable local microphone transmission to rover

The browser will prompt for microphone permission on first use.

### Settings

Click the settings button in the header to access:

- Video resolution selection (from rover's camera capabilities)
- Frame rate (5, 10, 15, 20, 30 fps)
- Audio input device selection (rover-side)

Changes are applied immediately and restart affected streams.

## Project Structure

```
rover-client/
├── package.json          # Node dependencies and scripts
├── src/
│   ├── index.html        # Main UI layout
│   ├── css/
│   │   └── styles.css    # Application styles
│   └── js/
│       ├── app.js        # Connection management
│       ├── motor.js      # Keyboard capture and motor commands
│       ├── video.js      # MJPEG video display
│       ├── audio_out.js  # Rover mic → client speaker
│       ├── audio_in.js   # Client mic → rover speaker
│       └── settings.js   # Settings panel logic
└── src-tauri/
    ├── tauri.conf.json   # Tauri configuration
    ├── Cargo.toml        # Rust dependencies
    └── src/
        └── main.rs       # Tauri entry point
```
