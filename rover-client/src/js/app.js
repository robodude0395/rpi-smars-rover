// app.js — Connection Manager
// Manages Socket.IO connections to all namespaces
// Handles connect/disconnect, reconnection with exponential backoff, and latency measurement
'use strict';

/**
 * Show a toast notification to the user.
 * @param {string} message - The message to display
 * @param {'info'|'success'|'warning'|'error'} type - Toast type for styling
 * @param {number} duration - Auto-dismiss duration in ms (default 3000)
 */
function showToast(message, type = 'info', duration = 3000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    // Trigger enter animation
    requestAnimationFrame(() => {
        toast.classList.add('toast-visible');
    });

    // Auto-dismiss
    setTimeout(() => {
        toast.classList.remove('toast-visible');
        toast.addEventListener('transitionend', () => {
            toast.remove();
        }, { once: true });
        // Fallback removal if transitionend doesn't fire
        setTimeout(() => toast.remove(), 400);
    }, duration);
}

const RoverApp = {
    connected: false,
    sockets: { control: null, audioOut: null, audioIn: null },
    roverIp: null,
    latencyInterval: null,

    // Reconnection state
    _reconnectAttempt: 0,
    _reconnectTimer: null,
    _reconnecting: false,
    _initialDelay: 1000,   // 1 second
    _maxDelay: 30000,      // 30 seconds
    _userDisconnect: false,

    /**
     * Initialize the connection manager — bind UI events.
     */
    init() {
        const btnConnect = document.getElementById('btn-connect');
        const ipInput = document.getElementById('rover-ip');

        btnConnect.addEventListener('click', () => {
            if (this.connected || this._reconnecting) {
                this.disconnect();
            } else {
                const ip = ipInput.value.trim();
                if (ip) {
                    this.connect(ip);
                }
            }
        });

        // Allow pressing Enter in the IP field to connect
        ipInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !this.connected && !this._reconnecting) {
                const ip = ipInput.value.trim();
                if (ip) {
                    this.connect(ip);
                }
            }
        });
    },

    /**
     * Establish Socket.IO connections to all namespaces on the given IP.
     * @param {string} ip - The rover IP address
     */
    connect(ip) {
        this.roverIp = ip;
        this._userDisconnect = false;
        const baseUrl = `http://${ip}:8080`;

        // Connect to /control namespace
        this.sockets.control = io(`${baseUrl}/control`, {
            transports: ['websocket'],
            reconnection: false
        });

        // Connect to /audio_out namespace
        this.sockets.audioOut = io(`${baseUrl}/audio_out`, {
            transports: ['websocket'],
            reconnection: false
        });

        // Connect to /audio_in namespace
        this.sockets.audioIn = io(`${baseUrl}/audio_in`, {
            transports: ['websocket'],
            reconnection: false
        });

        // Set up event handlers on the control socket (primary connection indicator)
        this.sockets.control.on('connect', () => {
            this._reconnecting = false;
            this._reconnectAttempt = 0;
            this._setConnected(true);
            this._startLatencyMeasurement();
            showToast('Connected to rover', 'success', 2000);

            // Start MJPEG video stream
            if (typeof VideoDisplay !== 'undefined') {
                VideoDisplay.start(this.roverIp);
            }
        });

        this.sockets.control.on('disconnect', () => {
            this._setConnected(false);
            this._stopLatencyMeasurement();
            showToast('Disconnected from rover', 'warning', 3000);

            // Stop video display on connection loss
            if (typeof VideoDisplay !== 'undefined') {
                VideoDisplay.stop();
            }

            // Only attempt reconnection if disconnect was NOT user-initiated
            if (!this._userDisconnect && this.roverIp) {
                this._scheduleReconnect();
            }
        });

        this.sockets.control.on('connect_error', (err) => {
            this._setConnected(false);
            this._stopLatencyMeasurement();

            // Show user-friendly error feedback
            const reason = err && err.message ? err.message : 'Unknown error';
            showToast(`Connection failed: ${reason}`, 'error', 4000);

            // Attempt reconnection on connection error if not user-initiated
            if (!this._userDisconnect && this.roverIp && !this._reconnecting) {
                this._scheduleReconnect();
            }
        });
    },

    /**
     * Disconnect all Socket.IO connections and stop the MJPEG stream.
     * This is a user-initiated disconnect — no reconnection will be attempted.
     */
    disconnect() {
        this._userDisconnect = true;
        this._cancelReconnect();
        this._stopLatencyMeasurement();

        if (this.sockets.control) {
            this.sockets.control.disconnect();
            this.sockets.control = null;
        }
        if (this.sockets.audioOut) {
            this.sockets.audioOut.disconnect();
            this.sockets.audioOut = null;
        }
        if (this.sockets.audioIn) {
            this.sockets.audioIn.disconnect();
            this.sockets.audioIn = null;
        }

        // Stop MJPEG video stream
        if (typeof VideoDisplay !== 'undefined') {
            VideoDisplay.stop();
        }

        this.roverIp = null;
        this._setConnected(false);
    },

    /**
     * Schedule a reconnection attempt with exponential backoff.
     * Delay formula: min(initialDelay * 2^attempt, maxDelay)
     */
    _scheduleReconnect() {
        this._reconnecting = true;
        const delay = Math.min(this._initialDelay * Math.pow(2, this._reconnectAttempt), this._maxDelay);

        this._updateReconnectDisplay(delay);

        this._reconnectTimer = setTimeout(() => {
            this._reconnectTimer = null;
            this._attemptReconnect();
        }, delay);

        this._reconnectAttempt++;
    },

    /**
     * Attempt to reconnect to the rover at the stored IP.
     * On success: resets state and resumes normal operation.
     * On failure: schedules the next reconnect attempt.
     */
    _attemptReconnect() {
        if (this._userDisconnect || !this.roverIp) {
            this._reconnecting = false;
            return;
        }

        // Clean up old sockets before reconnecting
        if (this.sockets.control) {
            this.sockets.control.disconnect();
            this.sockets.control = null;
        }
        if (this.sockets.audioOut) {
            this.sockets.audioOut.disconnect();
            this.sockets.audioOut = null;
        }
        if (this.sockets.audioIn) {
            this.sockets.audioIn.disconnect();
            this.sockets.audioIn = null;
        }

        // Attempt fresh connection (connect() sets up handlers including reconnect logic)
        this.connect(this.roverIp);
    },

    /**
     * Cancel any pending reconnection attempt and reset reconnection state.
     */
    _cancelReconnect() {
        if (this._reconnectTimer) {
            clearTimeout(this._reconnectTimer);
            this._reconnectTimer = null;
        }
        this._reconnectAttempt = 0;
        this._reconnecting = false;
    },

    /**
     * Calculate the backoff delay for a given attempt number.
     * @param {number} attempt - The attempt number (0-based)
     * @returns {number} Delay in milliseconds
     */
    calculateBackoffDelay(attempt) {
        return Math.min(this._initialDelay * Math.pow(2, attempt), this._maxDelay);
    },

    /**
     * Measure latency using Socket.IO's built-in ping/pong mechanism.
     * Uses a dedicated 'ping' event that the server echoes back as 'pong'.
     */
    measureLatency() {
        if (!this.sockets.control || !this.connected) {
            return;
        }

        const start = performance.now();

        this.sockets.control.volatile.emit('ping_latency', { t: start });
    },

    /**
     * Start periodic latency measurement (every 3 seconds).
     */
    _startLatencyMeasurement() {
        this._stopLatencyMeasurement();

        // Listen for pong responses
        if (this.sockets.control) {
            this.sockets.control.on('pong_latency', (data) => {
                if (data && data.t) {
                    const latency = Math.round(performance.now() - data.t);
                    this._updateLatencyDisplay(latency);
                }
            });
        }

        // Start measuring after a short delay to let connection stabilize
        setTimeout(() => {
            this.measureLatency();
            this.latencyInterval = setInterval(() => {
                this.measureLatency();
            }, 3000);
        }, 1000);
    },

    /**
     * Stop periodic latency measurement.
     */
    _stopLatencyMeasurement() {
        if (this.latencyInterval) {
            clearInterval(this.latencyInterval);
            this.latencyInterval = null;
        }
    },

    /**
     * Update the connection state and UI indicators.
     * @param {boolean} isConnected
     */
    _setConnected(isConnected) {
        this.connected = isConnected;

        const statusDot = document.getElementById('status-dot');
        const connectionLabel = document.getElementById('connection-label');
        const btnConnect = document.getElementById('btn-connect');
        const ipInput = document.getElementById('rover-ip');
        const latencyValue = document.getElementById('latency-value');

        if (isConnected) {
            statusDot.classList.add('connected');
            statusDot.classList.remove('disconnected', 'reconnecting');
            connectionLabel.textContent = 'Connected';
            btnConnect.textContent = 'Disconnect';
            ipInput.disabled = true;
        } else if (this._reconnecting) {
            statusDot.classList.remove('connected');
            statusDot.classList.add('disconnected', 'reconnecting');
            connectionLabel.textContent = 'Reconnecting...';
            btnConnect.textContent = 'Disconnect';
            ipInput.disabled = true;
        } else {
            statusDot.classList.remove('connected', 'reconnecting');
            statusDot.classList.add('disconnected');
            connectionLabel.textContent = 'Disconnected';
            btnConnect.textContent = 'Connect';
            ipInput.disabled = false;
            if (latencyValue) {
                latencyValue.textContent = '--';
            }
        }
    },

    /**
     * Update the UI to show reconnection countdown info.
     * @param {number} delayMs - The delay before next reconnect attempt in milliseconds
     */
    _updateReconnectDisplay(delayMs) {
        const connectionLabel = document.getElementById('connection-label');
        const statusDot = document.getElementById('status-dot');

        if (statusDot) {
            statusDot.classList.remove('connected');
            statusDot.classList.add('disconnected', 'reconnecting');
        }
        if (connectionLabel) {
            const delaySec = Math.round(delayMs / 1000);
            connectionLabel.textContent = `Reconnecting in ${delaySec}s...`;
        }
    },

    /**
     * Update the latency display value.
     * @param {number} ms - Latency in milliseconds
     */
    _updateLatencyDisplay(ms) {
        const latencyValue = document.getElementById('latency-value');
        if (latencyValue) {
            latencyValue.textContent = ms;
        }
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    RoverApp.init();
});
