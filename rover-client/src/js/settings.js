// settings.js — Settings Panel
// Manages the settings drawer: fetches devices, populates selectors, saves config, restarts streams.
'use strict';

const SettingsPanel = {
    _overlay: null,
    _btnOpen: null,
    _btnClose: null,
    _btnSave: null,
    _resolutionSelect: null,
    _fpsSelect: null,
    _audioDeviceSelect: null,
    _devices: null,

    /**
     * Initialize the settings panel — bind UI events.
     */
    init() {
        this._overlay = document.getElementById('settings-overlay');
        this._btnOpen = document.getElementById('btn-settings');
        this._btnClose = document.getElementById('btn-settings-close');
        this._btnSave = document.getElementById('btn-settings-save');
        this._resolutionSelect = document.getElementById('setting-resolution');
        this._fpsSelect = document.getElementById('setting-fps');
        this._audioDeviceSelect = document.getElementById('setting-audio-device');

        this._btnOpen.addEventListener('click', () => this.open());
        this._btnClose.addEventListener('click', () => this.close());
        this._btnSave.addEventListener('click', () => this.save());

        // Close on overlay background click
        this._overlay.addEventListener('click', (e) => {
            if (e.target === this._overlay) {
                this.close();
            }
        });

        // Close on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this._overlay.classList.contains('open')) {
                this.close();
            }
        });
    },

    /**
     * Open the settings panel and fetch available devices from the rover.
     */
    open() {
        this._overlay.classList.add('open');
        this._fetchDevices();
    },

    /**
     * Close the settings panel.
     */
    close() {
        this._overlay.classList.remove('open');
    },

    /**
     * Fetch available devices from GET /api/devices on the connected rover.
     * Populates resolution and audio device selectors on success.
     * Falls back to sensible defaults if device detection fails.
     */
    _fetchDevices() {
        if (!RoverApp.roverIp) {
            this._setSelectPlaceholder(this._resolutionSelect, 'Connect to rover first');
            this._setSelectPlaceholder(this._audioDeviceSelect, 'Connect to rover first');
            return;
        }

        const baseUrl = `http://${RoverApp.roverIp}:8080`;

        this._setSelectPlaceholder(this._resolutionSelect, 'Loading...');
        this._setSelectPlaceholder(this._audioDeviceSelect, 'Loading...');

        fetch(`${baseUrl}/api/devices`)
            .then((response) => {
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                return response.json();
            })
            .then((devices) => {
                this._devices = devices;
                this._populateResolutions(devices);
                this._populateAudioDevices(devices);
            })
            .catch((err) => {
                console.error('Settings: Failed to fetch devices:', err);
                // Fall back to defaults instead of showing error
                this._populateResolutions({ video: [] });
                this._populateAudioDevices({ audio: [] });
            });
    },

    /**
     * Populate the resolution selector from device capabilities.
     * Always includes low-bandwidth options below the camera's native minimum,
     * since the server downscales frames via cv2.resize() before encoding.
     * @param {object} devices - The device list response from /api/devices
     */
    _populateResolutions(devices) {
        this._resolutionSelect.innerHTML = '';

        const resolutions = new Set();
        const framerates = new Set();

        // Always include low-bandwidth options (server downscales regardless of camera native res)
        ['80x60', '120x90', '160x120', '240x180'].forEach((res) => resolutions.add(res));

        if (devices.video && devices.video.length > 0) {
            devices.video.forEach((device) => {
                if (device.resolutions) {
                    device.resolutions.forEach((res) => resolutions.add(res));
                }
                if (device.framerates) {
                    device.framerates.forEach((fps) => framerates.add(fps));
                }
            });
        }

        // If no device resolutions were added beyond our defaults, add standard ones
        if (resolutions.size <= 4) {
            ['320x240', '640x480'].forEach((res) => resolutions.add(res));
        }

        // Sort resolutions by width (ascending)
        const sorted = Array.from(resolutions).sort((a, b) => {
            const aw = parseInt(a.split('x')[0], 10);
            const bw = parseInt(b.split('x')[0], 10);
            return aw - bw;
        });

        sorted.forEach((res) => {
            const option = document.createElement('option');
            option.value = res;
            option.textContent = res;
            this._resolutionSelect.appendChild(option);
        });

        // Default to 320x240 if available
        if (resolutions.has('320x240')) {
            this._resolutionSelect.value = '320x240';
        }

        // Populate FPS selector from detected framerates
        this._populateFramerates(framerates);
    },

    /**
     * Populate the FPS selector from detected device framerates.
     * @param {Set<number>} framerates - Set of detected FPS values
     */
    _populateFramerates(framerates) {
        if (!this._fpsSelect) return;

        this._fpsSelect.innerHTML = '';

        if (framerates.size === 0) {
            // Provide sensible defaults for Pi Zero
            [5, 10, 15, 20, 25, 30].forEach((fps) => framerates.add(fps));
        }

        const sorted = Array.from(framerates).sort((a, b) => a - b);

        sorted.forEach((fps) => {
            const option = document.createElement('option');
            option.value = fps;
            option.textContent = fps + ' fps';
            // Mark high FPS values with a warning for Pi Zero
            if (fps > 20) {
                option.textContent += ' (may be unstable)';
            }
            this._fpsSelect.appendChild(option);
        });

        // Default to 15fps
        const defaultFps = sorted.includes(15) ? '15' : sorted[0].toString();
        this._fpsSelect.value = defaultFps;
    },

    /**
     * Populate the audio input device selector from device capabilities.
     * @param {object} devices - The device list response from /api/devices
     */
    _populateAudioDevices(devices) {
        this._audioDeviceSelect.innerHTML = '';

        // Add a default option
        const defaultOpt = document.createElement('option');
        defaultOpt.value = '';
        defaultOpt.textContent = 'Default';
        this._audioDeviceSelect.appendChild(defaultOpt);

        if (devices.audio && devices.audio.length > 0) {
            devices.audio.forEach((device) => {
                const option = document.createElement('option');
                option.value = device.device || device.path || '';
                option.textContent = device.name || device.device || 'Unknown Device';
                this._audioDeviceSelect.appendChild(option);
            });
        }
    },

    /**
     * Save settings: POST updated config to /api/config, then restart streams.
     */
    save() {
        if (!RoverApp.roverIp) {
            console.warn('Settings: Cannot save — not connected to rover');
            return;
        }

        const resolution = this._resolutionSelect.value;
        const fps = parseInt(this._fpsSelect.value, 10);

        // Parse resolution into width and height
        let width = 320;
        let height = 240;
        if (resolution && resolution.includes('x')) {
            const parts = resolution.split('x');
            width = parseInt(parts[0], 10);
            height = parseInt(parts[1], 10);
        }

        // Disable save button during operation
        this._btnSave.disabled = true;
        this._btnSave.textContent = 'Saving...';

        // Stop video display before restarting streams
        if (typeof VideoDisplay !== 'undefined') {
            VideoDisplay.stop();
        }

        // Send video config to the video server (port 8081)
        const videoUrl = `http://${RoverApp.roverIp}:8081`;

        fetch(`${videoUrl}/video/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                resolution: [width, height],
                fps: fps
            })
        })
            .then((response) => {
                if (!response.ok) {
                    throw new Error(`Video config failed: HTTP ${response.status}`);
                }
                return response.json();
            })
            .then(() => {
                // Restart video display
                if (typeof VideoDisplay !== 'undefined') {
                    VideoDisplay.start(RoverApp.roverIp);
                }

                this._btnSave.textContent = 'Saved!';
                setTimeout(() => {
                    this._btnSave.textContent = 'Save & Apply';
                    this._btnSave.disabled = false;
                    this.close();
                }, 800);
            })
            .catch((err) => {
                console.error('Settings: Save failed:', err);
                this._btnSave.textContent = 'Error — Retry';
                this._btnSave.disabled = false;

                if (typeof VideoDisplay !== 'undefined') {
                    VideoDisplay.start(RoverApp.roverIp);
                }

                setTimeout(() => {
                    this._btnSave.textContent = 'Save & Apply';
                }, 2000);
            });
    },

    /**
     * Set a select element to show a single placeholder option.
     * @param {HTMLSelectElement} select
     * @param {string} text
     */
    _setSelectPlaceholder(select, text) {
        select.innerHTML = '';
        const option = document.createElement('option');
        option.value = '';
        option.textContent = text;
        option.disabled = true;
        option.selected = true;
        select.appendChild(option);
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    SettingsPanel.init();
});
