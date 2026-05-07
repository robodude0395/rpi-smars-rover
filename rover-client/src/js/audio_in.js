// audio_in.js — Local Mic Capture
// Captures local microphone via getUserMedia + ScriptProcessorNode
// Downsamples to 16kHz and sends binary PCM frames to /audio_in namespace
'use strict';

const AudioInCapture = {
    enabled: false,
    _stream: null,
    _audioContext: null,
    _scriptNode: null,
    _sourceNode: null,
    _targetSampleRate: 16000,

    /**
     * Initialize the audio in capture — bind UI events.
     */
    init() {
        const btnMic = document.getElementById('btn-mic');
        if (btnMic) {
            btnMic.addEventListener('click', () => {
                this.toggle();
            });
        }
    },

    /**
     * Start microphone capture — request mic access, set up processing, begin sending.
     * @returns {Promise<void>}
     */
    async start() {
        if (this._audioContext) {
            return; // Already started
        }

        // Check if getUserMedia is available
        // Try multiple access paths for compatibility across Tauri/browser contexts
        let getUserMedia = null;
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            getUserMedia = (constraints) => navigator.mediaDevices.getUserMedia(constraints);
        } else if (navigator.getUserMedia || navigator.webkitGetUserMedia || navigator.mozGetUserMedia) {
            // Legacy fallback
            const legacyGetUserMedia = navigator.getUserMedia || navigator.webkitGetUserMedia || navigator.mozGetUserMedia;
            getUserMedia = (constraints) => new Promise((resolve, reject) => {
                legacyGetUserMedia.call(navigator, constraints, resolve, reject);
            });
        }

        if (!getUserMedia) {
            showToast('Microphone not available in this context', 'error', 5000);
            this.enabled = false;
            const btnMic = document.getElementById('btn-mic');
            if (btnMic) btnMic.classList.remove('active');
            return;
        }

        try {
            // Request microphone access
            this._stream = await getUserMedia({ audio: true });

            // Create AudioContext at native sample rate
            this._audioContext = new (window.AudioContext || window.webkitAudioContext)();

            // Create source node from mic stream
            this._sourceNode = this._audioContext.createMediaStreamSource(this._stream);

            // Use ScriptProcessorNode for audio processing
            // Smaller buffer = lower latency but more CPU. 2048 is a good balance.
            const bufferSize = 2048;
            this._scriptNode = this._audioContext.createScriptProcessor(bufferSize, 1, 1);

            this._scriptNode.onaudioprocess = (event) => {
                if (!this.enabled) {
                    return;
                }
                const inputData = event.inputBuffer.getChannelData(0);
                this._processAndSend(inputData);
            };

            // Connect: source → scriptProcessor → destination (required for processing to run)
            this._sourceNode.connect(this._scriptNode);
            this._scriptNode.connect(this._audioContext.destination);
        } catch (err) {
            console.error('AudioInCapture: Failed to start mic capture:', err);
            // Show user-friendly error for common mic access issues
            if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
                showToast('Microphone access denied', 'error', 4000);
            } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
                showToast('No microphone found', 'error', 4000);
            } else {
                showToast('Microphone error: ' + (err.message || 'Unknown'), 'error', 4000);
            }
            this.stop();
        }
    },

    /**
     * Stop microphone capture — release mic, close audio context.
     */
    stop() {
        // Disconnect nodes
        if (this._scriptNode) {
            this._scriptNode.onaudioprocess = null;
            this._scriptNode.disconnect();
            this._scriptNode = null;
        }

        if (this._sourceNode) {
            this._sourceNode.disconnect();
            this._sourceNode = null;
        }

        // Stop all mic tracks
        if (this._stream) {
            this._stream.getTracks().forEach(track => track.stop());
            this._stream = null;
        }

        // Close audio context
        if (this._audioContext) {
            this._audioContext.close();
            this._audioContext = null;
        }
    },

    /**
     * Toggle microphone capture on/off.
     */
    toggle() {
        this.enabled = !this.enabled;

        const btnMic = document.getElementById('btn-mic');
        if (btnMic) {
            if (this.enabled) {
                btnMic.classList.add('active');
                this.start();
            } else {
                btnMic.classList.remove('active');
                this.stop();
            }
        }
    },

    /**
     * Process a Float32 audio buffer: downsample to 16kHz, convert to Int16, and send.
     * @param {Float32Array} inputData - Raw audio samples at native sample rate
     */
    _processAndSend(inputData) {
        const socket = RoverApp.sockets.audioIn;
        if (!socket || !socket.connected) {
            return;
        }

        // Downsample from native sample rate to 16kHz
        const nativeSampleRate = this._audioContext.sampleRate;
        const downsampled = this._downsample(inputData, nativeSampleRate, this._targetSampleRate);

        // Convert Float32 to Int16 PCM (16-bit signed LE)
        const pcmData = this._float32ToInt16(downsampled);

        // Send binary PCM frame
        socket.emit('audio_data', pcmData.buffer);
    },

    /**
     * Downsample audio from source rate to target rate using nearest-neighbor decimation.
     * @param {Float32Array} inputBuffer - Input samples at source rate
     * @param {number} sourceSampleRate - Source sample rate (e.g., 44100 or 48000)
     * @param {number} targetSampleRate - Target sample rate (16000)
     * @returns {Float32Array} Downsampled audio buffer
     */
    _downsample(inputBuffer, sourceSampleRate, targetSampleRate) {
        if (sourceSampleRate === targetSampleRate) {
            return inputBuffer;
        }

        const ratio = sourceSampleRate / targetSampleRate;
        const outputLength = Math.floor(inputBuffer.length / ratio);
        const output = new Float32Array(outputLength);

        for (let i = 0; i < outputLength; i++) {
            output[i] = inputBuffer[Math.floor(i * ratio)];
        }

        return output;
    },

    /**
     * Convert Float32 audio samples to Int16 PCM (16-bit signed little-endian).
     * Clamps values to [-1, 1] before conversion.
     * @param {Float32Array} float32Array - Normalized float audio samples
     * @returns {Int16Array} PCM encoded audio data
     */
    _float32ToInt16(float32Array) {
        const int16 = new Int16Array(float32Array.length);
        for (let i = 0; i < float32Array.length; i++) {
            const s = Math.max(-1, Math.min(1, float32Array[i]));
            int16[i] = s < 0 ? s * 32768 : s * 32767;
        }
        return int16;
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    AudioInCapture.init();
});
