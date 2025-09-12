import streamlit as st
import requests
import json
from geopy.geocoders import Nominatim
from streamlit_folium import st_folium
import folium
from auth import login_ui, logout_ui
from fpcalc import (
    calculate_ta, calculate_fp_coeff, calculate_hf, calculate_rmu,
    get_component_factors, get_sfrs_factors
)

st.set_page_config(page_title="FpCalc", layout="wide", initial_sidebar_state="collapsed")

# Authentication
login_ui()
logout_ui()

# Load Data
def load_json(file):
    with open(file, "r") as f:
        return json.load(f)

arch_components = load_json("data/arch.json")
mech_components = load_json("data/mech.json")
sfrs_data = load_json("data/building.json")
period_data = load_json("data/period.json")

# UI Setup
st.markdown("## 📐 FpCalc: Seismic Design Force (Fp) Calculator")
st.markdown("Based on **ASCE/SEI 7-22**, Chapter 13")

# Desktop layout
col1, sep1, col2, sep2, col3 = st.columns([3, 0.15, 3, 0.15, 4])

# LEFT COLUMN: Component & Building Parameters
with col1:
    # Component Information
    st.markdown("### 🧩 :blue[Component Parameters]")

    component_category = st.radio("Component Category", ["Architectural", "Mechanical/Electrical"])
    component_data = arch_components if component_category == "Architectural" else mech_components
    component_list = [item.get("Component") or item.get("Components") for item in component_data]
    component_name = st.selectbox("Select Component", options=component_list, index=None, placeholder="Type to filter...")

    col_ip, col_wp = st.columns(2)
    with col_ip:
        Ip = st.selectbox("Importance Factor (Ip)", [1.0, 1.5])
    with col_wp:
        Wp = st.number_input("Component Operating Weight (Wp) [lb]", min_value=0.0, format="%.2f")

    # Building Parameters
    st.markdown("### 🏢 :blue[Building Parameters]")

    risk_category = st.selectbox("Risk Category", ["I", "II", "III", "IV"], index=1)
    Ie = {"I": 1.0, "II": 1.0, "III": 1.25, "IV": 1.5}[risk_category]
    st.caption(f"Assigned Importance Factor (Ie): **{Ie}**")

    col_z, col_h = st.columns(2)
    with col_z:
        z = st.number_input("Attachment Height (z) [ft]", min_value=0.0)
    with col_h:
        h = st.number_input("Roof Height (h) [ft]", min_value=1.0)
    location = "Supported Above Grade" if z > 0 else "Supported At or Below Grade"

    # Structural System (R & Ω₀)
    st.markdown("#### Structural System Parameters (R & Ω₀)")
    
    col_mode, col_input = st.columns([1, 2])
    with col_mode:
        r_mode = st.radio("Define R and Ω₀", ["Use SFRS", "Manual input"])
    
    with col_input:
        if r_mode == "Use SFRS":
            sfrs_list = [s["SFRS"] for s in sfrs_data]
            selected_sfrs = st.selectbox("SFRS", options=sfrs_list, index=None, placeholder="Type to filter...")
            R, Omega_0 = get_sfrs_factors(sfrs_data, selected_sfrs)
            if R is not None: st.info(f"R = {R}, Ω₀ = {Omega_0}")
        else:
            selected_sfrs = "Manual Input"
            R = st.number_input("Response Modification Coefficient (R)", min_value=1.0, value=8.0, step=0.25)
            Omega_0 = st.number_input("Overstrength Factor (Ω₀)", min_value=1.0, value=3.0, step=0.25)

    # Period Input (Ta)
    st.markdown("#### Approximate Period (Tₐ)")

    col_mode, col_input = st.columns([1, 2])
    with col_mode:
        ta_mode = st.radio("Tₐ Method", ["Given structure type", "Manual input", "Unknown"])

    with col_input:
        if ta_mode == "Given structure type":
            structure_list = [p["Structure Type "] for p in period_data] 
            selected_structure_type = st.selectbox("Structure Type", options=structure_list, index=None, placeholder="Type to filter...")
            Ta, Ct, x = calculate_ta(period_data, selected_structure_type, h)
            if Ta is not None: st.info(f"Tₐ = {Ta:.3f} sec  |  Cₜ = {Ct}, x = {x}")
        elif ta_mode == "Manual input":
            Ta = st.number_input("Enter Tₐ [sec]", min_value=0.01, value=1.00, step=0.10)
            selected_structure_type = "Manual Input"
            Ct, x = "-", "-"
        else:
            Ta = None
            selected_structure_type = "Unknown"
            Ct, x = "-", "-"

# MIDDLE COLUMN: Seismic Parameters
with col2:
    # SDS Input
    st.markdown("### ♒︎ :blue[Seismic Parameters]")
    sds_mode = st.radio("SDS Input", ["Fetch from USGS", "Manual input"])

    # Initialize session state for SDS caching
    if 'sds_value' not in st.session_state:
        st.session_state.sds_value = None
    if 'sds_location' not in st.session_state:
        st.session_state.sds_location = None
    if 'sds_params' not in st.session_state:
        st.session_state.sds_params = None

    # Cached SDS fetch function
    @st.cache_data(ttl=3600)  # Cache for 1 hour
    def fetch_sds_cached(lat, lon, risk_category, site_class):
        """Fetch SDS from USGS API with caching"""
        url = (
            f"https://earthquake.usgs.gov/ws/designmaps/asce7-22.json"
            f"?latitude={lat}&longitude={lon}"
            f"&riskCategory={risk_category}"
            f"&siteClass={site_class}&title=FpCalc"
        )
        r = requests.get(url)
        r.raise_for_status()
        return float(r.json()["response"]["data"]["sds"])

    SDS = None
    lat, lon = None, None
    default_lat, default_lon = 37.80423914364421, -122.27615639197262
    default_address = "601 12th Street, Oakland 94607"

    if sds_mode == "Fetch from USGS":
        coord_mode = st.radio("Location Input Method",
                    ["Manual Lat/Lon", "Address"],
                    index=0)
                    
        col_inputs, col_map = st.columns([1,1.5])

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

            # Check if we have cached SDS for current parameters
            current_params = (lat, lon, risk_category, site_class)
            has_cached_sds = (st.session_state.sds_value is not None and 
                             st.session_state.sds_params == current_params and
                             lat is not None and lon is not None)

            # Fetch SDS buttons
            if lat is not None and lon is not None and st.button("🔄 Fetch SDS"):
                try:
                    SDS = fetch_sds_cached(lat, lon, risk_category, site_class)
                    st.session_state.sds_value = SDS
                    st.session_state.sds_location = f"{lat:.6f}, {lon:.6f}"
                    st.session_state.sds_params = current_params
                    st.info(f"SDS = {SDS:.3f} g")
                except Exception as e:
                    st.error(f"Error fetching SDS: {e}")

            # Show cached SDS if available
            elif has_cached_sds:
                SDS = st.session_state.sds_value
                st.info(f"SDS = {SDS:.3f} g")
        
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


# RIGHT COLUMN: Results & Calculation Details
with col3:
    # Check for required parameters
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

    # Calculations
    CAR, Rpo = get_component_factors(component_data, component_name, location)
    Hf, a1, a2 = calculate_hf(z, h, Ta)
    Rmu = calculate_rmu(R, Ie, Omega_0)
    Fp_coeff, Fp_calc_coeff, Fp_min_coeff, Fp_max_coeff = calculate_fp_coeff(SDS, Ip, Wp, Hf, Rmu, CAR, Rpo)
    Fp = Fp_coeff * Wp

    # Display Results 
    st.markdown("### ✅ :blue[Results]")
    st.markdown(f"#### Fp coeff = **{Fp_coeff:.3f}**")
    if Wp > 0:
        st.markdown(f"#### Fp = **{Fp:.0f} lb** (with Wp = {Wp:.0f} lb)")
    else:
        st.warning("Enter a non-zero Wp to compute the seismic design force Fp.")

    # Calculation Details
    with st.expander("🔢 Calculation Details", expanded=False):
        calc_text = r"""
**Base Equation (Eqn. 13.3-1):**

$$
\small
F_p = 0.4 \cdot S_{DS} \cdot I_p \cdot W_p \cdot \left[ \frac{H_f}{R_{\mu}} \right] \cdot \left[ \frac{C_{AR}}{R_{po}} \right]
$$

**Parameters:**

- Approximate Fundamental Period (Tₐ):

  Structure Type: _{selected_structure_type}_

  {ta_section}

- Component Amplification Factor (Table 13.5-1 or 13.6-1):

  Component Type: _{selected_component_type}_

  $$
  \small
  C_{AR} = {CAR}, \quad R_{po} = {Rpo}
  $$

- Structure Ductility Factor (Table 12.2-1 and Eqn. 13.3-6):

  SFRS Type: _{selected_sfrs_type}_
  
  $$
  \small
  R = {R}, \quad \Omega_0 = {Omega_0}
  $$

  $$
  \small
  R_{\mu} = \sqrt{ \frac{1.1 \cdot R}{I_e \cdot \Omega_0} } = \sqrt{ \frac{{1.1} \cdot {R}}{{Ie} \cdot {Omega_0}} } = {Rmu}
  $$

- Height Amplification Factor:

  Location: _{location}_

  $$
  \small
  z = {z} \text{ ft}, h = {h} \text{ ft}
  $$

  $$
  \small
  \frac{z }{h } = \frac{{z} \text{ ft}}{{h} \text{ ft}} = {z_over_h}
  $$

  {Hf_case}

  $$
  \begin{aligned}
  H_f &= {Hf_expr} \\
  &= {Hf_num_expr} ={Hf}
  \end{aligned}
  $$

**Fp Coefficient:**

$$
\small
\begin{aligned}
F_{p,coeff} &= 0.4 \cdot S_{DS} \cdot I_p \cdot \left[ \frac{H_f}{R_{\mu}} \right] \cdot \left[ \frac{C_{AR}}{R_{po}} \right] \scriptsize\text{ (Eqn. 13.3-1)} \\
&= 0.4 \cdot {SDS} \cdot {Ip} \cdot \left( \frac{{Hf}}{{Rmu}} \cdot \frac{{CAR}}{{Rpo}} \right) = {Fp_calc_coeff}
\end{aligned}
$$

$$
\small
\begin{aligned}
F_{p,min,coeff} &= 0.3 \cdot S_{DS} \cdot I_p \scriptsize\text{ (Eqn. 13.3-3)} \\
&= 0.3 \cdot {SDS} \cdot {Ip} = {Fp_min_coeff}
\end{aligned}
$$

$$
\small
\begin{aligned}
F_{p,max,coeff} &= 1.6 \cdot S_{DS} \cdot I_p \scriptsize\text{ (Eqn. 13.3-2)} \\
&= 1.6 \cdot {SDS} \cdot {Ip} = {Fp_max_coeff}
\end{aligned}
$$

$$
\small
\begin{aligned}
F_{p,coeff} &= \max(F_{p,min,coeff}, \min(F_{p,calc}, F_{p,max,coeff})) \\
&= \max({Fp_min_coeff}, \min({Fp_calc_coeff}, {Fp_max_coeff})) = {Fp_coeff}
\end{aligned}
$$

{Fp_force_case}
"""

        if ta_mode == "Given structure type":
            ta_section = (
                f"Structure Type: _{selected_structure_type}_ (Eqn. 12.8-8)\n\n\t"
                f"$$ \\small T_a = C_t \\cdot h_n^x = {Ct} \\cdot {h:.1f}^{{{x}}} = {Ta:.3f} \\text{{ sec}} $$"
            )
        elif ta_mode == "Manual input":
            ta_section = f"Manually entered:  $$ \\small T_a = {Ta:.3f} \\text{{ sec}} $$"
        else:
            ta_section = ""

        # Hf case description and math
        z_over_h = z / h if h > 0 else 1
        if ta_mode != "Unknown":
            Hf_expr = "1 + a_1 \\cdot \\left( \\frac{z }{h } \\right) + a_2 \\cdot \\left( \\frac{z }{h } \\right)^{10}"
            Hf_num_expr = f"1 + {a1:.3f} · ({z_over_h:.3f}) + {a2:.3f} · ({z_over_h:.3f})^{{10}}"
            Hf_case = r"Since $T_a$ is specified, use Eqn. 13.3-4"
        else:
            Hf_expr = "1 + 2.5 \\cdot \\left( \\frac{z }{h } \\right)"
            Hf_num_expr = f"1 + 2.5 · ({z_over_h:.3f})"
            Hf_case = r"Since $T_a$ is not specified, use Eqn. 13.3-5"
        
        if Wp > 0:
            Fp_force_case = (
                f"**Fp Force:**\n\n"
                f"$$\n"
                f"F_p = F_{{p,coeff}} \\cdot W_p = {Fp_coeff:.3f} \\cdot {Wp:.0f} \\text{{ lb}} = {Fp:.0f} \\text{{ lb}}\n"
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
            .replace("{Hf_num_expr}", Hf_num_expr)
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

st.caption("FpCalc | ASCE/SEI 7-22 Chapter 13 © Degenkolb Engineers")
