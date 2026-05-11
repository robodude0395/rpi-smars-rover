// video.js — Video Display via Socket.IO
// Receives JPEG frames over the existing Socket.IO connection (port 8080),
// bypassing WebKit's cross-origin and mixed-content restrictions entirely.
'use strict';

const VideoDisplay = {
    _videoFeed: null,
    _placeholder: null,
    _socket: null,
    _active: false,

    /**
     * Initialize the video display — cache DOM elements.
     */
    init() {
        this._videoFeed = document.getElementById('video-feed');
        this._placeholder = document.getElementById('video-placeholder');
    },

    /**
     * Start displaying video by connecting to the /video Socket.IO namespace.
     * @param {string} roverIp - The rover IP address
     */
    start(roverIp) {
        if (!this._videoFeed || !roverIp) {
            return;
        }

        this.stop();
        this._active = true;

        if (this._placeholder) {
            this._placeholder.style.display = 'none';
        }
        this._videoFeed.classList.add('active');

        // Connect to the /video namespace on the same server
        const baseUrl = `http://${roverIp}:8080`;
        this._socket = io(`${baseUrl}/video`, {
            transports: ['websocket'],
            reconnection: false
        });

        this._socket.on('frame', (data) => {
            if (!this._active) return;

            const blob = new Blob([data], { type: 'image/jpeg' });
            const objectUrl = URL.createObjectURL(blob);

            const prevSrc = this._videoFeed.src;
            this._videoFeed.src = objectUrl;
            if (prevSrc && prevSrc.startsWith('blob:')) {
                URL.revokeObjectURL(prevSrc);
            }
        });

        this._socket.on('connect_error', () => {
            this._showPlaceholder('Video feed unavailable');
        });
    },

    /**
     * Stop displaying the video stream.
     */
    stop() {
        this._active = false;

        if (this._socket) {
            this._socket.disconnect();
            this._socket = null;
        }

        if (this._videoFeed) {
            const prevSrc = this._videoFeed.src;
            this._videoFeed.src = '';
            this._videoFeed.classList.remove('active');
            if (prevSrc && prevSrc.startsWith('blob:')) {
                URL.revokeObjectURL(prevSrc);
            }
        }

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
