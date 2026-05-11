// video.js — MJPEG Video Display
// Sets/clears the MJPEG stream URL on the <img> element
// Handles stream errors with placeholder display
//
// In Tauri production builds where mixed-content blocks the direct stream
// (e.g. over Tailscale IPs), falls back to polling /snapshot via Tauri's
// Rust-side HTTP client.
'use strict';

const VideoDisplay = {
    _videoFeed: null,
    _placeholder: null,
    _active: false,
    _pollTimer: null,
    _roverIp: null,
    _usingFallback: false,
    _loadedOnce: false,

    /**
     * Initialize the video display — cache DOM elements.
     */
    init() {
        this._videoFeed = document.getElementById('video-feed');
        this._placeholder = document.getElementById('video-placeholder');
    },

    /**
     * Start displaying the MJPEG stream from the rover.
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
        this._loadedOnce = false;

        if (this._placeholder) {
            this._placeholder.style.display = 'none';
        }
        this._videoFeed.classList.add('active');

        // Bind handlers
        this._videoFeed.addEventListener('load', this._handleLoad);
        this._videoFeed.addEventListener('error', this._handleError);

        // Set the MJPEG stream URL directly
        const streamUrl = `http://${roverIp}:8081/video_feed`;
        this._videoFeed.src = streamUrl;
    },

    /**
     * The img loaded successfully at least once — stream is working.
     */
    _handleLoad: function() {
        VideoDisplay._loadedOnce = true;
    },

    /**
     * Handle img error. If the stream never loaded successfully, try the
     * Tauri HTTP fallback (for mixed-content scenarios in production builds).
     * If it loaded before, this is a transient error — show placeholder.
     */
    _handleError: function() {
        if (!VideoDisplay._active) return;

        // If we already loaded frames via direct stream, this is a disconnect
        if (VideoDisplay._loadedOnce) {
            VideoDisplay._showPlaceholder('Video feed unavailable');
            return;
        }

        // Stream never loaded — likely mixed-content block. Try Tauri fallback.
        if (!VideoDisplay._usingFallback && window.__TAURI__ && window.__TAURI__.http) {
            console.log('[video] Direct stream blocked, using Tauri HTTP fallback');
            VideoDisplay._usingFallback = true;
            VideoDisplay._videoFeed.removeEventListener('error', VideoDisplay._handleError);
            VideoDisplay._videoFeed.removeEventListener('load', VideoDisplay._handleLoad);
            VideoDisplay._startSnapshotPolling(VideoDisplay._roverIp);
        } else {
            VideoDisplay._showPlaceholder('Video feed unavailable');
        }
    },

    /**
     * Poll /snapshot endpoint using Tauri's Rust-side HTTP client.
     * @param {string} roverIp
     */
    _startSnapshotPolling(roverIp) {
        const { fetch: tauriFetch, ResponseType } = window.__TAURI__.http;
        const url = `http://${roverIp}:8081/snapshot`;

        const poll = async () => {
            if (!VideoDisplay._active) return;

            try {
                const response = await tauriFetch(url, {
                    method: 'GET',
                    timeout: 5,
                    responseType: ResponseType.Binary,
                });

                if (!VideoDisplay._active) return;

                if (response.ok && response.data) {
                    const bytes = new Uint8Array(response.data);
                    const blob = new Blob([bytes], { type: 'image/jpeg' });
                    const objectUrl = URL.createObjectURL(blob);

                    const prevSrc = VideoDisplay._videoFeed.src;
                    VideoDisplay._videoFeed.src = objectUrl;
                    if (prevSrc && prevSrc.startsWith('blob:')) {
                        URL.revokeObjectURL(prevSrc);
                    }
                }
            } catch (err) {
                console.warn('[video] Snapshot poll error:', err);
            }

            if (VideoDisplay._active) {
                VideoDisplay._pollTimer = setTimeout(poll, 50);
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
            this._videoFeed.removeEventListener('error', this._handleError);
            this._videoFeed.removeEventListener('load', this._handleLoad);
            const prevSrc = this._videoFeed.src;
            this._videoFeed.src = '';
            this._videoFeed.classList.remove('active');
            if (prevSrc && prevSrc.startsWith('blob:')) {
                URL.revokeObjectURL(prevSrc);
            }
        }

        this._roverIp = null;
        this._usingFallback = false;
        this._loadedOnce = false;
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
