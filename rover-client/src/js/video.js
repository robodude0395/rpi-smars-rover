// video.js — MJPEG Video Display
// Sets/clears the MJPEG stream URL on the <img> element
// Handles stream errors with placeholder display, shows FPS counter
'use strict';

const VideoDisplay = {
    _videoFeed: null,
    _placeholder: null,
    _fpsCounter: null,
    _active: false,

    // FPS tracking via canvas pixel sampling
    _canvas: null,
    _ctx: null,
    _prevHash: 0,
    _frameCount: 0,
    _lastFpsTime: 0,
    _fpsIntervalId: null,

    /**
     * Initialize the video display — cache DOM elements and bind error handler.
     */
    init() {
        this._videoFeed = document.getElementById('video-feed');
        this._placeholder = document.getElementById('video-placeholder');
        this._fpsCounter = document.getElementById('fps-counter');

        // Offscreen canvas for frame-change detection
        this._canvas = document.createElement('canvas');
        this._canvas.width = 8;
        this._canvas.height = 8;
        this._ctx = this._canvas.getContext('2d', { willReadFrequently: true });

        if (this._videoFeed) {
            this._videoFeed.addEventListener('error', () => {
                this._showPlaceholder('Video feed unavailable');
            });
        }
    },

    /**
     * Start displaying the MJPEG stream from the rover.
     * @param {string} roverIp - The rover IP address
     */
    start(roverIp) {
        if (!this._videoFeed || !roverIp) {
            return;
        }

        const streamUrl = `http://${roverIp}:8081/video_feed`;
        this._videoFeed.src = streamUrl;
        this._videoFeed.classList.add('active');
        this._active = true;

        if (this._placeholder) {
            this._placeholder.style.display = 'none';
        }

        this._startFpsCounter();
    },

    /**
     * Stop displaying the video stream.
     */
    stop() {
        if (this._videoFeed) {
            this._videoFeed.src = '';
            this._videoFeed.classList.remove('active');
        }
        this._active = false;
        this._stopFpsCounter();
        this._showPlaceholder('No Video Feed');
    },

    /**
     * Start the FPS measurement loop.
     * Polls at high frequency to detect frame changes via canvas sampling.
     */
    _startFpsCounter() {
        this._frameCount = 0;
        this._lastFpsTime = performance.now();
        this._prevHash = 0;

        if (this._fpsCounter) {
            this._fpsCounter.style.display = '';
            this._fpsCounter.textContent = '-- fps';
        }

        // Poll at ~120Hz to catch frames reliably up to 60fps
        this._fpsIntervalId = setInterval(() => this._sampleFrame(), 8);

        // Update display every second
        this._fpsDisplayId = setInterval(() => {
            const now = performance.now();
            const elapsed = now - this._lastFpsTime;
            if (elapsed > 0) {
                const fps = Math.round((this._frameCount * 1000) / elapsed);
                if (this._fpsCounter) {
                    this._fpsCounter.textContent = fps + ' fps';
                }
            }
            this._frameCount = 0;
            this._lastFpsTime = now;
        }, 1000);
    },

    /**
     * Sample the current img content and detect if a new frame arrived.
     */
    _sampleFrame() {
        if (!this._active || !this._videoFeed) return;

        try {
            this._ctx.drawImage(this._videoFeed, 0, 0, 8, 8);
            const data = this._ctx.getImageData(0, 0, 8, 8).data;

            // Simple hash of pixel data to detect changes
            let hash = 0;
            for (let i = 0; i < data.length; i += 8) {
                hash = ((hash << 5) - hash + data[i]) | 0;
            }

            if (hash !== this._prevHash) {
                this._frameCount++;
                this._prevHash = hash;
            }
        } catch (e) {
            // Cross-origin or image not ready
        }
    },

    /**
     * Stop the FPS measurement loop.
     */
    _stopFpsCounter() {
        if (this._fpsIntervalId) {
            clearInterval(this._fpsIntervalId);
            this._fpsIntervalId = null;
        }
        if (this._fpsDisplayId) {
            clearInterval(this._fpsDisplayId);
            this._fpsDisplayId = null;
        }
        if (this._fpsCounter) {
            this._fpsCounter.style.display = 'none';
        }
        this._prevHash = 0;
    },

    /**
     * Show the placeholder with a custom message.
     * @param {string} message - The message to display in the placeholder
     */
    _showPlaceholder(message) {
        if (this._videoFeed) {
            this._videoFeed.classList.remove('active');
        }

        if (this._placeholder) {
            this._placeholder.style.display = '';
            const span = this._placeholder.querySelector('span');
            if (span) {
                span.textContent = message;
            }
        }
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    VideoDisplay.init();
});
