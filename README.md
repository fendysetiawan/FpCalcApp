# FpCalc
# 📐 FpCalc: Seismic Design Force (Fp) Calculator

**FpCalc** is an interactive Streamlit application for calculating seismic design forces (Fp) per **ASCE/SEI 7-22 Chapter 13**. It supports structural and nonstructural components, automatically derives relevant coefficients and parameters, and optionally fetches spectral acceleration values from the USGS Design Maps API.

---

## 🔧 Features

- **Fp Calculation** using the equation:
  $$
  F_p = 0.4 \cdot S_{DS} \cdot I_p \cdot W_p \cdot \left( \frac{H_f}{R_{\mu}} \cdot \frac{C_{AR}}{R_{po}} \right)
  $$

- 📦 Supports both **Architectural** and **Mechanical/Electrical** components  
- 🧱 Derives **Response Modification Coefficient (R)** and **Overstrength Factor (Ω₀)** from SFRS or user entry  
- 📊 Computes approximate period (Tₐ) based on structure type or manual input  
- 🌐 Pulls **SDS** (short period spectral acceleration) using **USGS API**  
- ✏️ Real-time display of all sub-calculations and coefficients  
- 📄 JSON-based component and structural data for easy updates

---

## 🗂 Directory Structure

```
FpCalc/
├── app.py               # Main Streamlit app
├── fpcalc.py            # Backend calculation logic
├── data/
│   ├── arch.json        # Architectural components and factors
│   ├── mech.json        # Mechanical/Electrical components and factors
│   ├── building.json    # SFRS systems with R and Ω₀
│   └── period.json      # Ct and x for Tₐ by structure type
└── README.md
```

---

## 🚀 Getting Started

### 1. Clone this repository

```bash
git clone https://github.com/Degenkolb-Internal/FpCalc.git
cd FpCalc
```

### 2. Install dependencies

Make sure you have Python 3.8+ and run:

```bash
pip install -r requirements.txt
```

### 3. Launch the app

```bash
streamlit run app.py
```

---

## 🌐 USGS API Support

You can fetch `SDS` values based on:

- **Latitude & Longitude**
- **Site Class** (A–E or "Default")
- **Risk Category** (I–IV)

The app queries the following API:

```
https://earthquake.usgs.gov/ws/designmaps/asce7-22.json
```

---

## 🧮 Calculation Parameters

| Symbol | Meaning                             | Source/Input                        |
|--------|-------------------------------------|-------------------------------------|
| SDS    | Spectral Acceleration               | User input / USGS API               |
| Ip     | Importance Factor                   | User selection                      |
| Ie     | Risk Category → Importance Factor   | User selection                      |
| Hf     | Height Amplification Factor         | Based on z/h and Ta                 |
| Rmu    | Effective Ductility Factor          | Based on R, Ω₀, Ie                  |
| CAR    | Component Amplification Factor      | Table 13.5-1 or 13.6-1              |
| Rpo    | Component Overstrength Factor       | Table 13.5-1 or 13.6-1              |

---

## 📌 Notes

- Weight (Wp) must be entered to calculate final Fp.
- All coefficients are calculated regardless of Wp.
- Includes detailed LaTeX-rendered calculation breakdown for transparency.

---

## 📄 License

© 2025 **Degenkolb Engineers**. All rights reserved.

---

## 👷 Authors

- Fendy Setiawan ([@fsetiawan](mailto:fsetiawan@degenkolb.com))

---

## 💬 Feedback

Open an issue or contact the team at [degenkolb.com](https://www.degenkolb.com).
