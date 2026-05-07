// video.js — MJPEG Video Display
// Sets/clears the MJPEG stream URL on the <img> element
// Handles stream errors with placeholder display
'use strict';

const VideoDisplay = {
    _videoFeed: null,
    _placeholder: null,
    _active: false,

    /**
     * Initialize the video display — cache DOM elements and bind error handler.
     */
    init() {
        this._videoFeed = document.getElementById('video-feed');
        this._placeholder = document.getElementById('video-placeholder');

        if (this._videoFeed) {
            this._videoFeed.addEventListener('error', () => {
                this._showPlaceholder('Video feed unavailable');
            });
        }
    },

    /**
     * Start displaying the MJPEG stream from the rover.
     * Sets the img src to the rover's video server on port 8081.
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
    },

    /**
     * Stop displaying the video stream.
     * Clears the img src and shows the placeholder.
     */
    stop() {
        if (this._videoFeed) {
            this._videoFeed.src = '';
            this._videoFeed.classList.remove('active');
        }
        this._active = false;
        this._showPlaceholder('No Video Feed');
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
