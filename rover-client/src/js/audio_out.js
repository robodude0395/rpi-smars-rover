// audio_out.js — Rover Audio Playback
// Receives binary PCM frames from /audio_out namespace
// Plays audio via Web Audio API at 16kHz
'use strict';

const AudioOutPlayer = {
    audioContext: null,
    enabled: false,
    _nextPlayTime: 0,
    _boundOnAudioData: null,
    _sampleRate: 16000,
    _bufferAheadTime: 0.05, // 50ms buffer ahead for gapless playback

    /**
     * Initialize the audio out player — bind UI events.
     */
    init() {
        const btnSpeaker = document.getElementById('btn-speaker');
        if (btnSpeaker) {
            btnSpeaker.addEventListener('click', () => {
                this.toggle();
            });
        }

        this._boundOnAudioData = (data) => this._onAudioData(data);
    },

    /**
     * Start audio playback — create AudioContext and listen for audio_data events.
     * Called when the speaker is enabled and connection is active.
     */
    start() {
        if (this.audioContext) {
            return; // Already started
        }

        try {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: this._sampleRate
            });

            this._nextPlayTime = 0;

            // Listen for audio data from the /audio_out namespace
            const socket = RoverApp.sockets.audioOut;
            if (socket) {
                socket.on('audio_data', this._boundOnAudioData);
            }
        } catch (err) {
            console.error('AudioOutPlayer: Failed to start audio playback:', err);
            showToast('Speaker error: ' + (err.message || 'Audio playback unavailable'), 'error', 4000);
            this.audioContext = null;
        }
    },

    /**
     * Stop audio playback — close AudioContext and remove event listener.
     */
    stop() {
        // Remove listener from socket
        const socket = RoverApp.sockets.audioOut;
        if (socket) {
            socket.off('audio_data', this._boundOnAudioData);
        }

        // Close audio context
        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }

        this._nextPlayTime = 0;
    },

    /**
     * Toggle speaker playback on/off.
     */
    toggle() {
        this.enabled = !this.enabled;

        const btnSpeaker = document.getElementById('btn-speaker');
        if (btnSpeaker) {
            if (this.enabled) {
                btnSpeaker.classList.add('active');
                this.start();
            } else {
                btnSpeaker.classList.remove('active');
                this.stop();
            }
        }
    },

    /**
     * Handle incoming binary PCM audio data.
     * Decodes 16-bit signed LE mono PCM and schedules playback via Web Audio API.
     * @param {ArrayBuffer} data - Raw PCM audio data (16-bit signed LE, mono, 16kHz)
     */
    _onAudioData(data) {
        if (!this.enabled || !this.audioContext) {
            return;
        }

        // Resume AudioContext if it's in suspended state (browser autoplay policy)
        if (this.audioContext.state === 'suspended') {
            this.audioContext.resume();
        }

        // Convert binary data to ArrayBuffer if needed
        const arrayBuffer = data instanceof ArrayBuffer ? data : data.buffer || data;

        // Decode 16-bit signed LE PCM to Float32
        const int16View = new Int16Array(arrayBuffer);
        const numSamples = int16View.length;

        if (numSamples === 0) {
            return;
        }

        // Create an AudioBuffer and fill with normalized float samples
        const audioBuffer = this.audioContext.createBuffer(1, numSamples, this._sampleRate);
        const channelData = audioBuffer.getChannelData(0);

        for (let i = 0; i < numSamples; i++) {
            channelData[i] = int16View[i] / 32768;
        }

        // Schedule playback for gapless audio
        const currentTime = this.audioContext.currentTime;

        // If _nextPlayTime has fallen behind currentTime, reset with a small buffer
        if (this._nextPlayTime < currentTime) {
            this._nextPlayTime = currentTime + this._bufferAheadTime;
        }

        // Create a buffer source node and schedule it
        const source = this.audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(this.audioContext.destination);
        source.start(this._nextPlayTime);

        // Advance _nextPlayTime by the duration of this buffer
        this._nextPlayTime += audioBuffer.duration;
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    AudioOutPlayer.init();
});
