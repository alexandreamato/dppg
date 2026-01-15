# GEMINI Project Context: D-PPG Vasoquant 1000 Reader

This document provides a comprehensive overview of the `dppg-reader` project for AI-driven development. It synthesizes information from the project's source code and documentation.

## 1. Project Overview

This project is a Python application designed to interface with an **Elcat Vasoquant 1000 D-PPG**, a medical device used for vascular diagnosis (photoplethysmography). The original software for this device is outdated, and this project provides a modern alternative that runs on macOS, Linux, and Windows.

The application, built with **Python 3** and its standard **Tkinter** library, presents a graphical user interface (GUI) to manage the connection, visualize data in real-time, and save it for analysis.

**Hardware & Connectivity:**
- The Vasoquant 1000 device communicates via a serial (RS-232) interface at 9600 baud (8N1).
- A **TGY Cyber WS1C Serial-to-WiFi converter** is used to bridge this connection to a TCP/IP network.
- The application connects to this converter, typically at `192.168.0.234:1100`.

## 2. Key Files

- **`dppg_reader.py`**: The main and only executable script. It contains all logic for the GUI (Tkinter), TCP socket communication, binary protocol parsing, data plotting, and file export functions.
- **`PROTOCOL.md`**: The definitive technical documentation. It details the reverse-engineered communication protocol of the Vasoquant 1000, including handshake procedures, data packet structure, label mappings, and a history of discoveries. This is the most critical document for understanding the data layer.
- **`AGENTS.md` / `CLAUDE.md`**: Guides for developers and AI agents, outlining project structure, conventions, and operational steps.
- **`ppg_data_*.csv` / `ppg_data_*.json`**: Sample data files captured and exported by the application. These serve as examples of the expected output. The JSON format is more structured and includes richer metadata.

## 3. Core Logic & Communication Protocol

The application's core function is to parse a proprietary binary protocol that was originally intended for a serial printer.

**Key Protocol Features:**
1.  **Handshake:** The Vasoquant device periodically sends a `DLE` (Data Link Escape, `0x10`) byte to check if the "printer" is online. The application must respond with an `ACK` (Acknowledge, `0x06`) to maintain a "printer online" status on the device.
2.  **Continuous ACK:** A crucial discovery was that the device expects an `ACK` response after **any** data it sends, not just the `DLE` poll. The application implements this to ensure a stable connection during data transfer.
3.  **Data Blocks:** When a user exports an exam, the data is sent in blocks. Each block starts with a specific header (`ESC` + `'L'`) and contains:
    - A **Label Byte**: Identifies the measurement type (e.g., `0xE2` for "Right Leg w/ Tourniquet").
    - **Sample Count**: The number of data points in the block.
    - **PPG Data**: A series of 16-bit little-endian integer values representing the photoplethysmography signal.
    - **Metadata**: A footer section that includes the **Exam Number**.
4.  **Data Processing:** The application parses these blocks, trims trailing artifacts from the raw samples, and can convert the raw ADC values into a clinical metric (`%PPG`) for visualization, based on formulas derived from official medical reports.

## 4. How to Build and Run

This is a single-file Python application with no external dependencies.

**To run the application:**
```bash
python3 dppg_reader.py
```
This will launch the Tkinter GUI.

**Typical Workflow:**
1.  Launch the application.
2.  Click **"Conectar"** to establish a TCP connection with the converter.
3.  Wait for the status on the Vasoquant device to show "printer online".
4.  On the Vasoquant device, select and export an exam.
5.  The application will automatically detect, parse, and plot the incoming data blocks.
6.  Use **"Salvar CSV"** or **"Salvar JSON"** to store the captured data.

## 5. Development Conventions

- **Style:** The code follows PEP 8 style, with snake_case for variables/functions and CapWords for classes.
- **Dependencies:** The project intentionally sticks to the Python standard library to maximize portability. Avoid adding new dependencies unless absolutely necessary.
- **Testing:** There is no automated test suite. Changes to the parsing logic in `dppg_reader.py` must be manually validated by:
    1. Running the application against a live device.
    2. Verifying the correct parsing of data blocks and extraction of exam numbers.
    3. Ensuring the generated CSV and JSON files are well-formed.
- **Commits:** Use short, imperative commit summaries (e.g., "Add JSON export functionality").
- **Security:** Be aware that the data files may contain sensitive medical information. Sanitize any data before sharing or committing.
