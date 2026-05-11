// video.js — MJPEG Video Display
//
// Primary: direct MJPEG stream via <img src> (works in dev mode and production
// with local IPs). Fallback: if the img errors (mixed-content block in production
// over Tailscale), switch to polling /snapshot via Tauri's Rust HTTP client.
'use strict';

const VideoDisplay = {
    _videoFeed: null,
    _placeholder: null,
    _active: false,
    _pollTimer: null,
    _roverIp: null,
    _usingFallback: false,

    /**
     * Initialize the video display — cache DOM elements.
     */
    init() {
        this._videoFeed = document.getElementById('video-feed');
        this._placeholder = document.getElementById('video-placeholder');
    },

    /**
     * Start displaying the video stream from the rover.
     * @param {string} roverIp - The rover IP address
     */
    start(roverIp) {
        if (!this._videoFeed || !roverIp) {
            return;
        }

        this.stop();
        this._roverIp = roverIp;
        this._active = true;
        this._usingFallback = false;

        if (this._placeholder) {
            this._placeholder.style.display = 'none';
        }
        this._videoFeed.classList.add('active');

        // Try direct MJPEG stream first
        const streamUrl = `http://${roverIp}:8081/video_feed`;
        this._videoFeed.src = streamUrl;

        // If the img fails to load, try the Tauri HTTP fallback
        this._videoFeed.addEventListener('error', this._onStreamError);
    },

    /**
     * Handle img load error — switch to Tauri HTTP polling if available.
     */
    _onStreamError: function() {
        // Only attempt fallback once, and only if Tauri API is available
        if (VideoDisplay._usingFallback || !VideoDisplay._active) {
            return;
        }

        if (window.__TAURI__ && window.__TAURI__.http) {
            console.log('[video] Direct stream failed, switching to Tauri HTTP polling');
            VideoDisplay._usingFallback = true;
            VideoDisplay._videoFeed.removeEventListener('error', VideoDisplay._onStreamError);
            VideoDisplay._startSnapshotPolling(VideoDisplay._roverIp);
        } else {
            VideoDisplay._showPlaceholder('Video feed unavailable');
        }
    },

    /**
     * Poll /snapshot endpoint using Tauri's Rust-side HTTP client.
     * Bypasses WebKit's mixed-content restrictions entirely.
     * @param {string} roverIp
     */
    _startSnapshotPolling(roverIp) {
        const { fetch: tauriFetch, ResponseType } = window.__TAURI__.http;
        const url = `http://${roverIp}:8081/snapshot`;

        const poll = async () => {
            if (!this._active) return;

            try {
                const response = await tauriFetch(url, {
                    method: 'GET',
                    timeout: 5,
                    responseType: ResponseType.Binary,
                });

                if (!this._active) return;

                if (response.ok && response.data) {
                    const bytes = new Uint8Array(response.data);
                    const blob = new Blob([bytes], { type: 'image/jpeg' });
                    const objectUrl = URL.createObjectURL(blob);

                    const prevSrc = this._videoFeed.src;
                    this._videoFeed.src = objectUrl;
                    if (prevSrc && prevSrc.startsWith('blob:')) {
                        URL.revokeObjectURL(prevSrc);
                    }
                }
            } catch (err) {
                console.warn('[video] Snapshot poll error:', err);
            }

            if (this._active) {
                this._pollTimer = setTimeout(poll, 50);
            }
        };

        poll();
    },

    /**
     * Stop displaying the video stream.
     */
    stop() {
        this._active = false;

        if (this._pollTimer) {
            clearTimeout(this._pollTimer);
            this._pollTimer = null;
        }

        if (this._videoFeed) {
            this._videoFeed.removeEventListener('error', this._onStreamError);
            const prevSrc = this._videoFeed.src;
            this._videoFeed.src = '';
            this._videoFeed.classList.remove('active');
            if (prevSrc && prevSrc.startsWith('blob:')) {
                URL.revokeObjectURL(prevSrc);
            }
        }

        this._roverIp = null;
        this._usingFallback = false;
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
