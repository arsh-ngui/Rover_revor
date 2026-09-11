# MineSweeper – Mine Safety & Rescue Rover

Sensor node firmware and circuit design for an AI-powered mine safety and
rescue rover, built for underground coal mine environments (Jharkhand).
This repo covers the gas/environment sensing sub-system: an Arduino Nano
reads MQ-4, MQ-7, DHT22, and BMP180, and forwards the readings as JSON to
an ESP32 over UART.

---

## 1. Circuit design – Fritzing setup

The schematic/breadboard files in this repo were built in **Fritzing** and
use a few custom parts that aren't in Fritzing's default parts bin. You'll
need to install those before the `.fzz` file will open without missing-part
errors.

### 1.1 Custom parts libraries used in this project

> **TODO:** fill in the actual libraries/sources you used below (name,
> where you got it, and what part(s) it adds). Replace this table before
> publishing the repo.

| Library / part source | Link | Parts it adds |
|---|---|---|
| _e.g. "MQ Gas Sensors – Fritzing Part"_ | _link here_ | MQ-4, MQ-7 |
| _e.g. "BMP180 Fritzing Part"_ | _link here_ | BMP180 breakout |
| _e.g. "RioRand LM2596 Buck Converter"_ | _link here_ | Buck converter module |
| _e.g. "DHT22 Fritzing Part"_ | _link here_ | DHT22 |

### 1.2 How to install a custom Fritzing library (general steps)

Fritzing custom parts usually come either as a single `.fzpz` file (a
packaged part) or as a folder of `.fzp`/`.svg` files (a parts bin). Use
whichever method matches what you downloaded:

**Method A — Installing a `.fzpz` file (most common, easiest)**
1. Download the `.fzpz` file from the source link above.
2. Open Fritzing.
3. Simply **drag and drop** the `.fzpz` file onto the Fritzing window
   (anywhere on the canvas or parts bin works).
4. Fritzing will install it automatically and it'll appear under
   **MY PARTS** in the parts bin panel on the right.

*(Alternative: Parts bin panel → click the "+" / import icon at the
bottom → select the `.fzpz` file → Open.)*

**Method B — Installing a full parts bin / folder**
1. Download and unzip the parts library folder.
2. In Fritzing, go to **Window → Parts** (or the parts bin panel on the
   right side).
3. Right-click inside the **MY PARTS** bin → **Import**.
4. Navigate to the unzipped folder and select it.
5. The parts should now show up in your **MY PARTS** bin, ready to drag
   onto the canvas.

**Method C — Manual copy (only if A/B don't work)**
1. Locate your Fritzing user parts directory:
   - **Windows:** `Documents\Fritzing\parts`
   - **macOS:** `~/Documents/Fritzing/parts`
   - **Linux:** `~/Documents/Fritzing/parts` (or wherever your Documents
     folder is)
2. Copy the library folder into this directory.
3. Restart Fritzing. The parts should appear under **MY PARTS**.

### 1.3 Opening this repo's Fritzing file

1. Install all libraries listed in section 1.1 first (using the steps
   above) — otherwise Fritzing will show the affected parts as generic
   red/gray placeholder boxes with a "missing part" warning.
2. Open the `.fzz` file included in this repo.
3. If any part still shows as missing after installing its library,
   double-check you installed the *exact* version linked above — some
   custom parts are updated over time and older project files can
   reference an older version's internal part ID.

---

## 2. Firmware – libraries to install

This project has two separate microcontrollers, each with their own
sketch and their own library requirements.

### 2.1 Arduino IDE Board Manager

| Board package | Needed for | Notes |
|---|---|---|
| **Arduino AVR Boards** | Arduino Nano | Comes pre-installed with the Arduino IDE by default — nothing to add manually. Select via **Tools → Board → Arduino AVR Boards → Arduino Nano**. |
| **esp32 by Espressif Systems** | ESP32 Dev Module | Install via **Boards Manager** (search "esp32"). If you haven't added the Espressif boards index URL yet, see the [official install guide](https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html). |

> **Nano upload note:** some Nano clone boards need
> **Tools → Processor → "ATmega328P (Old Bootloader)"** instead of the
> default option, or uploads will fail. Try this if you get an upload
> error.

### 2.2 Libraries for the Arduino Nano sketch (`nano_sensor_uart.ino`)

Install all of these via **Sketch → Include Library → Manage Libraries**:

| Library | Publisher | Used for |
|---|---|---|
| DHT sensor library | Adafruit | Reading the DHT22 |
| Adafruit Unified Sensor | Adafruit | Required dependency of the DHT library (Arduino IDE will usually prompt to install this automatically) |
| Adafruit BMP085 Library | Adafruit | Reading the BMP180 (this library also covers the BMP085) |

`Wire` (I2C) and `SoftwareSerial` are used too, but both ship built into
the Arduino IDE core — no installation needed.

> Make sure you install the versions published by **Adafruit**
> specifically — there are similarly-named third-party libraries that can
> conflict or behave differently.

### 2.3 Libraries for the ESP32 sketch (`esp32_receiver.ino`)

| Library | Publisher | Used for |
|---|---|---|
| ArduinoJson | Benoit Blanchon | Parsing the JSON line sent by the Nano (6.x or 7.x both work) |

`HardwareSerial` is part of the ESP32 board core — no installation
needed.

---

## 3. Wiring summary (Nano ↔ ESP32 link)

- Nano **A3** (TX, SoftwareSerial) → voltage divider (5V → ~3.3V) → ESP32 **RX** (Pin 4)
- Nano **A2** (RX, SoftwareSerial) ← ESP32 **TX** pin (no divider needed this direction) (Pin 2)
- Nano **GND** ↔ ESP32 **GND** (common ground — required)

Both sketches communicate at **9600 baud**.

---

## 4. Repo contents

- `nanoJson2ino` — reads MQ-4, MQ-7, DHT22, BMP180 and sends
  readings as a JSON line over UART
- `esp32RecPinChange.ino` — receives and parses the JSON line from the Nano
- Fritzing circuit file(s) — schematic/breadboard design
