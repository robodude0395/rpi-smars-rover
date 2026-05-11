// video.js — MJPEG Video Display
// Sets/clears the MJPEG stream URL on the <img> element
// Handles stream errors with placeholder display, shows server-reported FPS
'use strict';

const VideoDisplay = {
    _videoFeed: null,
    _placeholder: null,
    _fpsCounter: null,
    _active: false,
    _fpsIntervalId: null,
    _roverIp: null,

    /**
     * Initialize the video display — cache DOM elements and bind error handler.
     */
    init() {
        this._videoFeed = document.getElementById('video-feed');
        this._placeholder = document.getElementById('video-placeholder');
        this._fpsCounter = document.getElementById('fps-counter');

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

        this._roverIp = roverIp;
        const streamUrl = `http://${roverIp}:8081/video_feed`;
        this._videoFeed.src = streamUrl;
        this._videoFeed.classList.add('active');
        this._active = true;

        if (this._placeholder) {
            this._placeholder.style.display = 'none';
        }

        this._startFpsPolling();
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
        this._roverIp = null;
        this._stopFpsPolling();
        this._showPlaceholder('No Video Feed');
    },

    /**
     * Poll the server's /video/fps endpoint every second.
     */
    _startFpsPolling() {
        this._stopFpsPolling();

        if (this._fpsCounter) {
            this._fpsCounter.style.display = '';
            this._fpsCounter.textContent = '-- fps';
        }

        this._fpsIntervalId = setInterval(() => {
            if (!this._roverIp) return;

            fetch(`http://${this._roverIp}:8081/video/fps`)
                .then(r => r.json())
                .then(data => {
                    if (this._fpsCounter) {
                        this._fpsCounter.textContent = data.fps + ' fps';
                    }
                })
                .catch(() => {});
        }, 1000);
    },

    /**
     * Stop FPS polling.
     */
    _stopFpsPolling() {
        if (this._fpsIntervalId) {
            clearInterval(this._fpsIntervalId);
            this._fpsIntervalId = null;
        }
        if (this._fpsCounter) {
            this._fpsCounter.style.display = 'none';
        }
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
