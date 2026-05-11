#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <SPI.h>

/* ---------- OLED Display ---------- */
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
#define OLED_ADDRESS 0x3C
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

/* ---------- Motor Driver Pins (L293D) ----------  */
#define EN1 9   // Motor 1 Enable (PWM)
#define IN1 6   // Motor 1 Direction A
#define IN2 7   // Motor 1 Direction B
#define EN2 3   // Motor 2 Enable (PWM)
#define IN3 8   // Motor 2 Direction A
#define IN4 4   // Motor 2 Direction B

/* ---------- SPI Pins ---------- */
#define SPI_CS 2    // Custom chip select
// Pin 10 (hardware SS) must remain INPUT for SPI slave mode
// MOSI = 11, MISO = 12, SCK = 13 (hardware SPI)

/* ---------- Communication Protocol ---------- */
#define SYNC_BYTE 0xAA
#define CMD_BUFFER_SIZE 3       // [SYNC, left, right]
volatile byte spiBuffer[CMD_BUFFER_SIZE];
volatile byte spiIndex = 0;
volatile bool newCommand = false;

/* ---------- Safety Timeout ---------- */
#define TIMEOUT_MS 1000
unsigned long lastCommandTime = 0;

/* ---------- Display Update ---------- */
#define DISPLAY_UPDATE_MS 100
unsigned long lastDisplayUpdate = 0;

/* ---------- Motor Ramping ---------- */
#define RAMP_UPDATE_MS 2        // Update ramp every 5ms
#define RAMP_STEP 5             // Speed change per update
unsigned long lastRampUpdate = 0;

/* ---------- Current Motor State ---------- */
int currentLeftSpeed = 0;
int currentRightSpeed = 0;
int targetLeftSpeed = 0;
int targetRightSpeed = 0;

/* ---------- Motor Control Functions ---------- */

void setMotor(int en, int in1, int in2, int speed) {
    speed = constrain(speed, -255, 255);
    if (speed > 0) {
        digitalWrite(in1, HIGH);
        digitalWrite(in2, LOW);
        analogWrite(en, speed);
    } else if (speed < 0) {
        digitalWrite(in1, LOW);
        digitalWrite(in2, HIGH);
        analogWrite(en, abs(speed));
    } else {
        digitalWrite(in1, LOW);
        digitalWrite(in2, LOW);
        analogWrite(en, 0);
    }
}

void setLeftMotor(int speed) {
    currentLeftSpeed = speed;
    setMotor(EN1, IN1, IN2, speed);
}

void setRightMotor(int speed) {
    currentRightSpeed = speed;
    setMotor(EN2, IN3, IN4, speed);
}

void stopMotors() {
    targetLeftSpeed = 0;
    targetRightSpeed = 0;
}

/* ---------- Motor Ramping ---------- */

void updateMotorRamping() {
    unsigned long now = millis();
    if (now - lastRampUpdate < RAMP_UPDATE_MS) return;
    lastRampUpdate = now;

    // Ramp left motor
    if (currentLeftSpeed != targetLeftSpeed) {
        int diff = targetLeftSpeed - currentLeftSpeed;
        if (abs(diff) <= RAMP_STEP) {
            currentLeftSpeed = targetLeftSpeed;
        } else {
            currentLeftSpeed += (diff > 0) ? RAMP_STEP : -RAMP_STEP;
        }
        setMotor(EN1, IN1, IN2, currentLeftSpeed);
    }

    // Ramp right motor
    if (currentRightSpeed != targetRightSpeed) {
        int diff = targetRightSpeed - currentRightSpeed;
        if (abs(diff) <= RAMP_STEP) {
            currentRightSpeed = targetRightSpeed;
        } else {
            currentRightSpeed += (diff > 0) ? RAMP_STEP : -RAMP_STEP;
        }
        setMotor(EN2, IN3, IN4, currentRightSpeed);
    }
}

/* ---------- SPI Interrupt Handler ---------- */

ISR(SPI_STC_vect) {
    byte received = SPDR;

    if (spiIndex == 0) {
        // First byte must be sync byte, otherwise discard and wait
        if (received == SYNC_BYTE) {
            spiBuffer[0] = received;
            spiIndex = 1;
        }
        // If not sync byte, stay at index 0 (self-correcting)
    } else {
        spiBuffer[spiIndex] = received;
        spiIndex++;
        if (spiIndex >= CMD_BUFFER_SIZE) {
            newCommand = true;
            spiIndex = 0;
        }
    }
    SPDR = 0;
}

/* ---------- Process SPI Command ---------- */

void processCommand() {
    if (!newCommand) return;

    // Buffer is [SYNC_BYTE, leftByte, rightByte]
    byte leftByte = spiBuffer[1];
    byte rightByte = spiBuffer[2];

    // Convert from offset encoding (128 = stop)
    int leftSpeed = (int)leftByte - 128;
    int rightSpeed = (int)rightByte - 128;

    // Scale to -255 to 255 range
    leftSpeed = map(leftSpeed, -128, 127, -255, 255);
    rightSpeed = map(rightSpeed, -128, 127, -255, 255);

    // Set target speeds (ramping will handle gradual change)
    targetLeftSpeed = leftSpeed;
    targetRightSpeed = rightSpeed;

    lastCommandTime = millis();
    newCommand = false;
}

/* ---------- Display Update ---------- */

void updateDisplay() {
    unsigned long now = millis();
    if (now - lastDisplayUpdate < DISPLAY_UPDATE_MS) return;
    lastDisplayUpdate = now;

    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);

    // L motor — top half (y 4..28), text size 3 = 21px tall
    display.setTextSize(3);
    display.setCursor(4, 4);
    display.print("L:");
    if (currentLeftSpeed > 0) {
        display.print("FWD");
    } else if (currentLeftSpeed < 0) {
        display.print("REV");
    } else {
        display.print("---");
    }

    // R motor — bottom half (y 36..60), text size 3 = 21px tall
    display.setCursor(4, 38);
    display.print("R:");
    if (currentRightSpeed > 0) {
        display.print("FWD");
    } else if (currentRightSpeed < 0) {
        display.print("REV");
    } else {
        display.print("---");
    }

    display.display();
}

/* ---------- Safety Check ---------- */

void checkTimeout() {
    if (millis() - lastCommandTime > TIMEOUT_MS) {
        if (targetLeftSpeed != 0 || targetRightSpeed != 0) {
            stopMotors();
        }
    }
}

/* ---------- Setup ---------- */

void setup() {
    // Motor pins
    pinMode(EN1, OUTPUT);
    pinMode(EN2, OUTPUT);
    pinMode(IN1, OUTPUT);
    pinMode(IN2, OUTPUT);
    pinMode(IN3, OUTPUT);
    pinMode(IN4, OUTPUT);

    // Safe startup - motors off
    stopMotors();

    // SPI slave setup
    pinMode(MISO, OUTPUT);
    pinMode(SPI_CS, INPUT);
    pinMode(10, INPUT); // Hardware SS must be INPUT for slave mode
    SPCR |= _BV(SPE);   // Enable SPI in slave mode
    SPCR |= _BV(SPIE);  // Enable SPI interrupt
    SPI.attachInterrupt();

    // I2C and OLED
    Wire.begin();
    if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDRESS)) {
        // OLED init failed - continue anyway
    }
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(0, 0);
    display.println("ROVER READY");
    display.println("Waiting for SPI...");
    display.display();

    lastCommandTime = millis();
}

/* ---------- Main Loop ---------- */

void loop() {
    processCommand();
    updateMotorRamping();
    checkTimeout();
    updateDisplay();
}
