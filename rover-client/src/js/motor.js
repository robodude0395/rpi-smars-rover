// motor.js — Motor Control
// Listens for WASD keydown/keyup events
// Sends motor commands at 20Hz while movement keys are held
'use strict';

const MotorControl = {
    // Key state tracking
    keys: { w: false, a: false, s: false, d: false },

    // Incrementing sequence number for each command
    seq: 0,

    // Interval handle for 20Hz command sending
    sendInterval: null,

    // Base speed value (max motor value)
    BASE_SPEED: 127,

    // Command send rate: 20Hz = 50ms interval (matches Arduino's processing capacity)
    SEND_RATE_MS: 50,

    /**
     * Initialize motor control — bind keyboard events and speed slider.
     */
    init() {
        document.addEventListener('keydown', (e) => this._onKeyDown(e));
        document.addEventListener('keyup', (e) => this._onKeyUp(e));

        // Speed slider display update
        const slider = document.getElementById('speed-slider');
        const display = document.getElementById('speed-value');
        if (slider && display) {
            slider.addEventListener('input', () => {
                display.textContent = slider.value + '%';
            });
        }
    },

    /**
     * Handle keydown events for W, A, S, D, Space.
     * @param {KeyboardEvent} e
     */
    _onKeyDown(e) {
        // Ignore repeated keydown events (key held)
        if (e.repeat) return;

        const key = e.key.toLowerCase();

        if (key === ' ') {
            // Space = immediate stop
            e.preventDefault();
            this._sendStop();
            return;
        }

        if (!this.keys.hasOwnProperty(key)) return;

        e.preventDefault();
        this.keys[key] = true;
        this._updateKeyIndicator(key, true);

        // Start sending commands if not already sending
        this._startSending();
    },

    /**
     * Handle keyup events for W, A, S, D.
     * @param {KeyboardEvent} e
     */
    _onKeyUp(e) {
        const key = e.key.toLowerCase();

        if (!this.keys.hasOwnProperty(key)) return;

        e.preventDefault();
        this.keys[key] = false;
        this._updateKeyIndicator(key, false);

        // If no movement keys are held, stop sending and issue stop command
        if (!this._anyKeyHeld()) {
            this._stopSending();
            this._sendStop();
        }
    },

    /**
     * Check if any movement key is currently held.
     * @returns {boolean}
     */
    _anyKeyHeld() {
        return this.keys.w || this.keys.a || this.keys.s || this.keys.d;
    },

    /**
     * Get the current speed value from the slider, scaled to 0-127.
     * @returns {number} Speed value 0-127
     */
    _getSpeed() {
        const slider = document.getElementById('speed-slider');
        if (!slider) return this.BASE_SPEED;
        const percent = parseInt(slider.value, 10) / 100;
        return Math.round(this.BASE_SPEED * percent);
    },

    /**
     * Calculate motor values based on current key state.
     * Combines contributions from all held keys.
     *
     * Key contributions:
     *   W: left += speed, right += speed
     *   S: left -= speed, right -= speed
     *   A: left -= speed, right += speed
     *   D: left += speed, right -= speed
     *
     * Results are clamped to -127..127.
     *
     * @returns {{left: number, right: number}}
     */
    _getMotorValues() {
        const speed = this._getSpeed();
        let left = 0;
        let right = 0;

        if (this.keys.w) {
            left += speed;
            right += speed;
        }
        if (this.keys.s) {
            left -= speed;
            right -= speed;
        }
        if (this.keys.a) {
            left -= speed;
            right += speed;
        }
        if (this.keys.d) {
            left += speed;
            right -= speed;
        }

        // Clamp to -127..127
        left = Math.max(-127, Math.min(127, left));
        right = Math.max(-127, Math.min(127, right));

        return { left, right };
    },

    /**
     * Send a motor command on the control socket.
     * Uses volatile emit so commands are dropped rather than queued if busy.
     */
    _sendCommand() {
        if (!RoverApp.sockets.control || !RoverApp.connected) return;

        const { left, right } = this._getMotorValues();
        this.seq++;

        RoverApp.sockets.control.volatile.emit('command', {
            type: 'motor',
            left: left,
            right: right,
            seq: this.seq
        });
    },

    /**
     * Send a stop command (left=0, right=0).
     * Sends multiple times to ensure delivery through any buffering.
     */
    _sendStop() {
        if (!RoverApp.sockets.control || !RoverApp.connected) return;

        this.seq++;

        // Send stop command 3 times rapidly to ensure it arrives
        for (let i = 0; i < 3; i++) {
            RoverApp.sockets.control.volatile.emit('command', {
                type: 'motor',
                left: 0,
                right: 0,
                seq: this.seq + i
            });
        }
        this.seq += 2;
    },

    /**
     * Start the command sending interval at high frequency.
     */
    _startSending() {
        if (this.sendInterval !== null) return;

        // Send immediately on key press for instant response
        this._sendCommand();
        this.sendInterval = setInterval(() => {
            this._sendCommand();
        }, this.SEND_RATE_MS);
    },

    /**
     * Stop the command sending interval.
     */
    _stopSending() {
        if (this.sendInterval !== null) {
            clearInterval(this.sendInterval);
            this.sendInterval = null;
        }
    },

    /**
     * Update the visual key indicator (active/inactive state).
     * @param {string} key - The key letter (w, a, s, d)
     * @param {boolean} active - Whether the key is pressed
     */
    _updateKeyIndicator(key, active) {
        const el = document.getElementById('key-' + key);
        if (el) {
            if (active) {
                el.classList.add('active');
            } else {
                el.classList.remove('active');
            }
        }
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    MotorControl.init();
});
