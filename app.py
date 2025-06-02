import streamlit as st
import io
import requests
import json
from geopy.geocoders import Nominatim
from streamlit_folium import st_folium
import folium
from auth import get_users_from_secrets, login_ui
from fpcalc import (
    calculate_ta, calculate_fp_coeff, calculate_hf, calculate_rmu,
    get_component_factors, get_sfrs_factors
)
from report import generate_pdf_report

st.set_page_config(page_title="FpCalc", layout="centered")

# ---------------- Authenticate User ----------------
users = get_users_from_secrets()
login_ui(users)

# -------------------- Load Data --------------------
def load_json(file):
    with open(file, "r") as f:
        return json.load(f)

arch_components = load_json("data/arch.json")
mech_components = load_json("data/mech.json")
sfrs_data = load_json("data/building.json")
period_data = load_json("data/period.json")

# -------------------- UI Setup --------------------
st.title("📐 FpCalc: Seismic Design Force (Fp) Calculator")
st.markdown("Based on **ASCE/SEI 7-22**, Chapter 13")

# -------------------- Component Information --------------------
st.header("🧩 :blue[Component Parameters]")

component_category = st.radio("Component Category", ["Architectural", "Mechanical/Electrical"])
component_data = arch_components if component_category == "Architectural" else mech_components
component_list = [item.get("Component") or item.get("Components") for item in component_data]
component_name = st.selectbox("Select Component", options=component_list, index=None, placeholder="Type to filter...")

Ip = st.selectbox("Importance Factor (Ip)", [1.0, 1.5])
Wp = st.number_input("Component Operating Weight (Wp) [kips]", min_value=0.0, format="%.2f")

# -------------------- Building Parameters --------------------
st.header("🏢 :blue[Building Parameters]")

risk_category = st.selectbox("Risk Category", ["I", "II", "III", "IV"], index=1)
Ie = {"I": 1.0, "II": 1.0, "III": 1.25, "IV": 1.5}[risk_category]
st.caption(f"Assigned Importance Factor (Ie): **{Ie}**")

h = st.number_input("Roof Height (h) [ft]", min_value=1.0)
z = st.number_input("Attachment Height (z) [ft]", min_value=0.0)
location = "Supported Above Grade" if z > 0 else "Supported At or Below Grade"

# ---------------- Structural System (R & Ω₀) ----------------
st.subheader("Structural System Parameters")
r_mode = st.radio("Define R and Ω₀", ["Use SFRS", "Manual input"])

if r_mode == "Use SFRS":
    sfrs_list = [s["SFRS"] for s in sfrs_data]
    selected_sfrs = st.selectbox("SFRS", options=sfrs_list, index=None, placeholder="Type to filter...")
    R, Omega_0 = get_sfrs_factors(sfrs_data, selected_sfrs)
    if R is not None: st.info(f"R = {R}, Ω₀ = {Omega_0}")
else:
    selected_sfrs = "Manual Input"
    R = st.number_input("Response Modification Coefficient (R)", min_value=1.0, value=8.0, step=0.25)
    Omega_0 = st.number_input("Overstrength Factor (Ω₀)", min_value=1.0, value=3.0, step=0.25)

# -------------------- Period Input (Ta) --------------------
st.subheader("Approximate Period (Tₐ)")

ta_mode = st.radio("Tₐ Method", ["Calculate from structure type", "Manual input", "Unknown"])

if ta_mode == "Calculate from structure type":
    structure_list = [p["Structure Type "] for p in period_data]
    selected_structure_type = st.selectbox("Structure Type", options=structure_list, index=None, placeholder="Type to filter...")
    Ta, Ct, x = calculate_ta(period_data, selected_structure_type, h)
    if Ta is not None: st.info(f"Tₐ = {Ta:.3f} sec  |  Cₜ = {Ct}, x = {x}")
elif ta_mode == "Manual input":
    Ta = st.number_input("Enter Tₐ [sec]", min_value=0.01)
    selected_structure_type = "Manual Input"
    Ct, x = "-", "-"
else:
    Ta = None
    selected_structure_type = "Unknown"
    Ct, x = "-", "-"

# ---------------------- SDS Input ----------------------
st.header("♒︎ :blue[Seismic Parameters]")
sds_mode = st.radio("SDS Input", ["Fetch from USGS", "Manual input"])
SDS = None
lat, lon = None, None
default_lat, default_lon = 37.80423914364421, -122.27615639197262
default_address = "601 12th Street, Oakland 94607"

if sds_mode == "Fetch from USGS":
    coord_mode = st.radio("Location Input Method",
                ["Manual Lat/Lon", "Address"],
                index=0)

    col_inputs, col_map = st.columns([1,1])

    with col_inputs:
        if coord_mode == "Manual Lat/Lon":
            lat = st.number_input("Latitude", value=default_lat, format="%.8f")
            lon = st.number_input("Longitude", value=default_lon, format="%.8f")

        elif coord_mode == "Address":
            @st.cache_data(show_spinner=False)
            def geocode(addr: str):
                if not addr:
                    return None
                geolocator = Nominatim(user_agent="FpCalc")
                return geolocator.geocode(addr)
            
            address = st.text_input(
                "Enter Address (e.g. 601 12th Street, Oakland 94607)",
                value=default_address,
                placeholder="601 12th Street, Oakland 94607"
            )
            location = geocode(address.strip())
            if location:
                lat, lon = location.latitude, location.longitude
                st.info(f"🔍 {location.address}\n Latitude: {lat:.6f}, Longitude: {lon:.6f}")
            else:
                if address:
                    st.warning("Unable to geocode that address. Try refining it.")

        site_class = st.selectbox("Site Class", ["A","B","BC","C","CD","D","DE","E","Default"], index=8)

        # Fetch‐SDS button
        if lat is not None and lon is not None and st.button("Fetch SDS"):
            try:
                url = (
                    f"https://earthquake.usgs.gov/ws/designmaps/asce7-22.json"
                    f"?latitude={lat}&longitude={lon}"
                    f"&riskCategory={risk_category}"
                    f"&siteClass={site_class}&title=FpCalc"
                )
                r = requests.get(url); r.raise_for_status()
                SDS = float(r.json()["response"]["data"]["sds"])
                st.info(f"SDS = {SDS:.3f} g")
            except Exception as e:
                st.error(f"Error fetching SDS: {e}")
    
    with col_map:
        # Map display
        if lat is not None and lon is not None:
            m = folium.Map(location=[lat, lon], zoom_start=16)
            tooltip = folium.Tooltip(f"<strong>Selected Site</strong><br>"
                                     f"Lat: {lat:.6f}<br>Lon: {lon:.6f}", parse_html=True)
            folium.Marker([lat, lon], tooltip=tooltip, icon=folium.Icon(icon="map-pin", prefix="fa")).add_to(m)
            st_folium(m, width=350, height=300)

    

else:
    # Manual SDS input unchanged
    SDS = st.number_input("SDS [g]", min_value=0.0, format="%.3f")


# ------------ Check for required parameters ------------
if component_name is None:
    st.warning("Please select a component before proceeding.")
    st.stop()

if selected_sfrs is None:
    st.warning("Please select a SFRS before proceeding.")
    st.stop()

if ta_mode != "Unknown" and Ta is None:
    st.warning("Please select structural type or provide approximate period before proceeding.")
    st.stop()

if SDS is None:
    st.warning("Please provide seismic parameters before proceeding.")
    st.stop()

# -------------------- Calculations --------------------
CAR, Rpo = get_component_factors(component_data, component_name, location)
Hf, a1, a2 = calculate_hf(z, h, Ta)
Rmu = calculate_rmu(R, Ie, Omega_0)
Fp_coeff, Fp_calc_coeff, Fp_min_coeff, Fp_max_coeff = calculate_fp_coeff(SDS, Ip, Wp, Hf, Rmu, CAR, Rpo)
Fp = Fp_coeff * Wp

# ------------------  Display Results ------------------ 
st.subheader("Results")
st.write(f"### ✅ Fp coeff = **{Fp_coeff:.3f}**")
if Wp > 0:
    st.write(f"### 🧮 Fp = **{Fp:.0f} lb** (with Wp = {Wp:.2f} kips)")
else:
    st.warning("Enter a non-zero Wp to compute the seismic design force Fp.")

with st.expander("Calculation Details"):
    st.markdown("#### 🔢 Equations and Calculations")

    calc_text = r"""
**Base Equation:**

$$
F_p = 0.4 \cdot S_{DS} \cdot I_p \cdot W_p \cdot \left( \frac{H_f}{R_{\mu}} \cdot \frac{C_{AR}}{R_{po}} \right)
$$

**Subcomponent Values:**

- Approximate Fundamental Period (Tₐ):

  Structure Type: _{selected_structure_type}_

  {ta_section}

- Component Amplification Factor:

  Component Type: _{selected_component_type}_

  $$
  C_{AR} = {CAR}, \quad R_{po} = {Rpo}
  $$

- Structure Ductility Factor:

  SFRS Type: _{selected_sfrs_type}_
  
  $$
  R = {R}, \quad \Omega_0 = {Omega_0}
  $$

  $$
  R_{\mu} = \sqrt{ \frac{1.1 \cdot R}{I_e \cdot \Omega_0} } = \sqrt{ \frac{{1.1} \cdot {R}}{{Ie} \cdot {Omega_0}} } = {Rmu}
  $$

- Height Amplification Factor:

  location: _{location}_

  $$
  \frac{{z}}{{h}} = \frac{{{z}}}{{{h}}} = {z_over_h}
  $$

  {Hf_case}

  $$
  H_f = {Hf_expr} = {Hf}
  $$

**Fp Coefficient:**

$$
F_{p,coeff} = 0.4 \cdot {SDS} \cdot {Ip} \cdot \left( \frac{{Hf}}{{Rmu}} \cdot \frac{{CAR}}{{Rpo}} \right) = {Fp_calc_coeff}
$$

$$
F_{p,min,coeff} = 0.3 \cdot S_{DS} \cdot I_p = 0.3 \cdot {SDS} \cdot {Ip} = {Fp_min_coeff}
$$

$$
F_{p,max,coeff} = 1.6 \cdot S_{DS} \cdot I_p = 1.6 \cdot {SDS} \cdot {Ip} = {Fp_max_coeff}
$$

$$
F_{p,coeff} = \text{{clamp}}(F_{p,calc}, F_{p,min,coeff}, F_{p,max,coeff}) = {Fp_coeff}
$$

{Fp_force_case}
"""

    if ta_mode == "Calculate from structure type and height":
        ta_section = (
            f"Structure Type: _{selected_structure_type}_  \n\n"
            f"$$ T_a = C_t \\cdot h_n^x = {Ct} \\cdot {h:.1f}^{{{x}}} = {Ta:.3f} \\text{{ sec}} $$"
        )
    elif ta_mode == "Manual input":
        ta_section = f"Manually entered:  \n\n$$ T_a = {Ta:.3f} \\text{{ sec}} $$"
    else:
        ta_section = f"Not specified" 

    # Hf case description and math
    z_over_h = z / h if h > 0 else 1
    if ta_mode != "Unknown":
        Hf_expr = f"1 + {a1:.3f} · ({z_over_h:.3f}) + {a2:.3f} · ({z_over_h:.3f})^{{10}}"
        Hf_case = r"**Since $T_a$ is specified, use:**"
    else:
        Hf_expr = f"1 + 2.5 · ({z_over_h:.3f})"
        Hf_case = r"**Since $T_a$ is not specified, use:**"
    
    if Wp > 0:
        Fp_force_case = (
            f"**Fp Force:**\n\n"
            f"$$\n"
            f"F_p = F_{{p,coeff}} \\cdot W_p = {Fp_coeff:.3f} \\cdot {Wp:.0f} = {Fp:.0f} \\text{{ lb}}\n"
            f"$$"
        )
    else:
        Fp_force_case = "**Fp Force:**\n\n_(Not shown. Enter a non-zero Wp to compute Fp)_"

    st.markdown(calc_text
        .replace("{SDS}", f"{SDS:.3f}")
        .replace("{ta_section}", ta_section)
        .replace("{location}", str(location))
        .replace("{selected_component_type}", component_name)
        .replace("{selected_sfrs_type}", selected_sfrs)
        .replace("{selected_structure_type}", selected_structure_type)
        .replace("{Ie}", f"{Ie:.1f}")
        .replace("{Ip}", f"{Ip:.1f}")
        .replace("{Hf_case}", Hf_case)
        .replace("{Hf_expr}", Hf_expr)
        .replace("{Fp_force_case}", Fp_force_case)
        .replace("{Hf}", f"{Hf:.3f}")
        .replace("{z_over_h}", f"{z_over_h:.3f}")
        .replace("{z}", f"{z:.1f}")
        .replace("{h}", f"{h:.1f}")
        .replace("{Rmu}", f"{Rmu:.3f}")
        .replace("{CAR}", f"{CAR}")
        .replace("{Rpo}", f"{Rpo}")
        .replace("{R}", f"{R:.1f}")
        .replace("{Omega_0}", f"{Omega_0:.1f}")
        .replace("{Fp_calc_coeff}", f"{Fp_calc_coeff:.3f}")
        .replace("{Fp_min_coeff}", f"{Fp_min_coeff:.3f}")
        .replace("{Fp_max_coeff}", f"{Fp_max_coeff:.3f}")
        .replace("{Fp_coeff}", f"{Fp_coeff:.3f}")
        .replace("{Fp}", f"{Fp:.0f}")
        .replace("{Wp}", f"{Wp:.0f}")
    )

# Streamlit button and logic
if st.button("📄 Generate PDF Report"):
    buffer = io.BytesIO()

    inputs = {
        "Component Type": component_name,
        "Component Category": component_category,
        "Importance Factor (Ip)": Ip,
        "Weight (Wp)": Wp,
        "SDS": SDS,
        "R": R,
        "Omega_0": Omega_0,
        "Ie": Ie,
        "z (ft)": z,
        "h (ft)": h,
        "Structure Type": selected_structure_type,
        "Risk Category": risk_category,
        "Site Class": site_class if sds_mode == "Fetch from USGS" else "Manual",
        "Tₐ (sec)": f"{Ta:.3f}" if Ta else "Not specified"
    }

    results = {
        "Hf": f"{Hf:.3f}",
        "Rμ": f"{Rmu:.3f}",
        "CAR": f"{CAR}",
        "Rpo": f"{Rpo}",
        "Fp Coefficient": f"{Fp_coeff:.3f}",
        "Fp": f"{Fp:.0f} lb" if Wp > 0 else "N/A",
    }

    generate_pdf_report(buffer, inputs, results)
    st.download_button(
        label="📥 Download Report",
        data=buffer,
        file_name="FpCalc_Report.pdf",
        mime="application/pdf"
    )

st.caption("FpCalc | ASCE/SEI 7-22 Chapter 13 © Degenkolb Engineers")
