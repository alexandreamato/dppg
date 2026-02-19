# D-PPG Manager

**Open-source, cross-platform software for the Elcat Vasoquant 1000 digital photoplethysmography device.**

*Dr. Alexandre Amato — [Instituto Amato de Medicina Avancada](https://software.amato.com.br)*

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey)

---

## Overview

The Elcat Vasoquant 1000 is a digital photoplethysmography (D-PPG) device used for non-invasive venous function assessment. The original Vasoview/Vasoscreen software only runs on legacy Windows systems and is no longer maintained.

**D-PPG Manager** is a complete replacement built through reverse engineering of the proprietary communication protocol and signal processing algorithms. It runs on macOS, Windows, and Linux.

### Key Features

- **Full protocol support** — communicates with the Vasoquant 1000 via serial or WiFi bridge
- **5 standard parameters** — To, Th, Ti, Vo, Fo (validated against 226 official reports)
- **3 novel analyses** — exponential time constant (tau), bilateral asymmetry index, quantified tourniquet effect
- **Patient management** — SQLite database with exam history
- **PDF reports** — automated diagnostic reports with waveforms, parameter tables, radar charts, and clinical interpretation
- **Standalone executable** — ~88 MB, no Python required

### Diagnostic Parameters

| Parameter | Description | Unit |
|-----------|-------------|------|
| **To** | Venous refilling time | seconds |
| **Th** | Half-amplitude time | seconds |
| **Ti** | Initial inflow time (adaptive linear extrapolation) | seconds |
| **Vo** | Venous pump power | % |
| **Fo** | Venous pump capacity (curve integral) | %*s |
| **tau** | Exponential time constant (recovery curve fit) | seconds |

### Venous Function Classification

| Grade | To | Interpretation |
|-------|:--:|----------------|
| Normal | > 25 s | Normal venous function |
| Grade I | 20-25 s | Mild insufficiency |
| Grade II | 10-20 s | Moderate insufficiency |
| Grade III | <= 10 s | Severe insufficiency |

## Screenshots

*Coming soon*

## Installation

### From Source

```bash
git clone https://github.com/alexandreamato/dppg.git
cd dppg
pip install -r requirements.txt
python3 dppg_manager.py
```

### Requirements

- Python 3.10+
- numpy >= 1.20
- scipy >= 1.7
- matplotlib >= 3.5
- reportlab >= 4.0
- sqlalchemy >= 2.0
- Pillow
- tkinter (included with Python)

### Standalone Executable

```bash
# macOS
pip install pyinstaller
pyinstaller dppg_manager.spec --clean --noconfirm
open "dist/DPPG Manager.app"

# Windows
build_windows.bat
```

The executable (~88 MB) includes all dependencies. The database is stored in `~/Documents/DPPG Manager/`.

## Hardware Setup

### Vasoquant 1000

The device communicates via RS-232 serial at 9600 baud, 8N2 (8 data bits, no parity, **2 stop bits**).

### WiFi Bridge (Optional)

A serial-to-WiFi bridge (e.g., TGY Cyber WS1C) enables wireless connectivity:

| Setting | Value |
|---------|-------|
| IP | 192.168.0.234 |
| TCP Port | 1100 |
| Baud | 9600 |
| Config | 8N2 |

## How It Works

### Communication Protocol

The software uses a printer-emulation protocol reverse-engineered from the original Vasoview driver (`vl320hw.dll`):

1. Device sends **DLE** (0x10) to check if "printer" is online
2. Software responds with **ACK** (0x06)
3. User exports exam on the device
4. Device transmits binary packet: channel label + raw PPG samples (4 Hz, 16-bit LE) + hardware-computed metadata
5. Software responds with **ACK** to confirm receipt

### Signal Processing

Algorithms were reverse-engineered from `dppg 2.dll` via disassembly with radare2. Key findings:

- All calculations use **integer arithmetic** (no FPU)
- **Ti** uses adaptive linear extrapolation (3s or 6s window), not threshold crossing
- **Fo** is a true curve integral with trapezoidal correction, not Vo x Th
- The floating-point constants (0.125, 0.50, 3.0) found in the DLL are for **print layout only**

### Validation

Validated against 226 official Vasoscreen reports from 57 patients:

| Mode | Mean Error | Grade Agreement |
|------|:----------:|:---------------:|
| Hardware-assisted | 4.2% | 97% |
| Software-only | 30.0% | 89% |

## Novel Analyses

### Exponential Time Constant (tau)

Fits `V(t) = A * exp(-t/tau) + C` to the recovery curve. Larger tau = slower refilling = better venous function.

### Bilateral Asymmetry Index

Quantifies inter-limb differences: `A = |P_left - P_right| / max(P_left, P_right) * 100%`

- \> 20% = significant asymmetry
- \> 40% = highly significant

### Quantified Tourniquet Effect

Expresses tourniquet response as percentage change:

- Positive (improvement) = superficial venous reflux
- Negative (worsening) = deep venous insufficiency

## Project Structure

```
dppg/
├── dppg_manager.py              # Main application entry point
├── dppg_manager.spec             # PyInstaller build spec
├── requirements.txt              # Python dependencies
├── src/
│   ├── analysis.py               # Signal processing & parameter calculation
│   ├── models.py                 # Data models (PPGBlock, PPGParameters)
│   ├── protocol.py               # Vasoquant binary protocol parser
│   ├── config.py                 # Constants & configuration
│   ├── exporters.py              # CSV/JSON export
│   ├── gui/
│   │   ├── app.py                # Main GUI application
│   │   ├── exam_view.py          # Exam visualization
│   │   ├── capture_view.py       # Live data capture
│   │   ├── patient_list.py       # Patient management
│   │   ├── report_editor.py      # Report editing
│   │   └── widgets.py            # Custom widgets (ParametersTable, etc.)
│   ├── diagnosis/
│   │   ├── classifier.py         # Venous function grading
│   │   └── text_generator.py     # Automated diagnostic text
│   ├── report/
│   │   ├── pdf_generator.py      # PDF report generation
│   │   ├── chart_renderer.py     # Matplotlib charts for reports
│   │   └── templates.py          # Report text templates
│   └── db/
│       └── schema.py             # SQLAlchemy database schema
├── dppg_reader.py                # Legacy standalone reader
├── CLAUDE.md                     # Technical documentation
└── PROTOCOL.md                   # Complete protocol documentation
```

## Citation

If you use this software in your research, please cite:

> Amato A. Open-Source Digital Photoplethysmography Software with Novel Bilateral Asymmetry Analysis: Reverse Engineering and Validation of the Elcat Vasoquant 1000. 2026.

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

## Author

**Dr. Alexandre Amato, MD, PhD**
Instituto Amato de Medicina Avancada
Sao Paulo, Brazil
[software.amato.com.br](https://software.amato.com.br)

## Disclaimer

This software is provided for research and clinical support purposes. It is not a certified medical device. Clinical decisions should always be made by qualified healthcare professionals using validated diagnostic tools. The authors assume no liability for clinical outcomes resulting from the use of this software.
