import json
import time
import requests
import streamlit as st
import folium
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderUnavailable
from streamlit_folium import st_folium

from auth import login_ui, logout_ui
from fpcalc import (
    calculate_ta, calculate_fp_coeff_16, calculate_fp_coeff_22, calculate_hf, calculate_rmu,
    get_component_factors, get_component_factors_16, get_sfrs_factors
)

st.set_page_config(page_title="FpCalc", layout="wide", initial_sidebar_state="collapsed")

# Custom CSS
st.markdown("""
<style>
    .stExpander .stMarkdown p {
        margin-bottom: 0.5rem !important;
        line-height: 1.5 !important;
    }
    .stExpander .stMarkdown {
        margin-bottom: 0.5rem !important;
    }
    .stExpander .element-container {
        margin-bottom: 0.5rem !important;
    }
</style>
""", unsafe_allow_html=True)

# Authentication
login_ui()
logout_ui()

class RateLimitedGeocoder:
    def __init__(self):
        self.last_request_time = 0
        self.min_interval = 1.0  # 1 second minimum between requests
    
    def geocode_with_rate_limit(self, address):
        """Geocode address with rate limiting to comply with Nominatim policy"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_interval:
            time.sleep(self.min_interval - time_since_last)
        
        try:
            geolocator = Nominatim(user_agent="FpCalc")
            result = geolocator.geocode(address, timeout=10)
            self.last_request_time = time.time()
            return result
        except (GeocoderUnavailable, Exception):
            st.warning("⚠️ Geocoding service unavailable. Use manual coordinates.")
            return None

rate_limited_geocoder = RateLimitedGeocoder()

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

# ASCE Version Selection
col_asce1, col_asce2, _ = st.columns([1, 1, 10])
with col_asce1:
    asce_7_16 = st.checkbox("ASCE 7-16", value=True)
with col_asce2:
    asce_7_22 = st.checkbox("ASCE 7-22", value=True)

# Ensure at least one version is selected
if not asce_7_16 and not asce_7_22:
    st.warning("Please select at least one ASCE version.")
    st.stop()

# Display selected version(s)
selected_versions = []
if asce_7_16:
    selected_versions.append("ASCE/SEI 7-16")
if asce_7_22:
    selected_versions.append("ASCE/SEI 7-22")

st.markdown(f"Based on **{' and '.join(selected_versions)}**, Chapter 13")

# Layout
col1, _, col2 = st.columns([1, 0.1, 1])

with col1:
    st.markdown("### 🧩 :blue[Component Parameters]")

    component_category = st.radio("Component Category", ["Architectural", "Mechanical/Electrical"])
    component_data = arch_components if component_category == "Architectural" else mech_components
    component_list = [item.get("Component") or item.get("Components") for item in component_data]
    component_name = st.selectbox("Select Component", options=component_list, index=None, placeholder="Type to filter...")
    
    # Display component factors for both ASCE versions if component is selected
    if component_name is not None:
        if asce_7_16:
            ap_display, Rp_display, Omega_16_display = get_component_factors_16(component_data, component_name)
            if ap_display is not None:
                st.caption(f"**ASCE 7-16:** ap = **{ap_display}** | Rp = **{Rp_display}** | Ω₀ = **{Omega_16_display}**")
        if asce_7_22:
            CAR_above, Rpo, Omega = get_component_factors(component_data, component_name, "Supported Above Grade")
            CAR_below, _, Omega = get_component_factors(component_data, component_name, "Supported At or Below Grade")
            if CAR_above is not None:
                st.caption(f"**ASCE 7-22:** Above Grade CAR = **{CAR_above}** | At or Below Grade CAR = **{CAR_below}** | Rpo = **{Rpo}** | Ω₀ = **{Omega}**")
        
    col_ip, col_wp = st.columns(2)
    with col_ip:
        Ip = st.selectbox("Component Importance Factor (Ip)", [1.0, 1.5])
    with col_wp:
        Wp = st.number_input("Component Operating Weight (Wp) [lb]", min_value=0.0, format="%.2f")

    st.markdown("")

    st.markdown("### 🏢 :blue[Building Parameters]")

    risk_category = st.selectbox("Risk Category", ["I", "II", "III", "IV"], index=1)
    Ie = {"I": 1.0, "II": 1.0, "III": 1.25, "IV": 1.5}[risk_category]
    st.caption(f"Building Importance Factor (Ie): **{Ie}**")

    col_z, col_h = st.columns(2)
    with col_z:
        z = st.number_input("Attachment Height (z) [ft]", value=1.0, min_value=0.0)
    with col_h:
        h = st.number_input("Roof Height (h) [ft]", value=1.0, min_value=1.0)
    component_location = "Supported Above Grade" if z > 0 else "Supported At or Below Grade"

    if asce_7_22:
        st.markdown("#### Structural System Parameters (R & Ω₀)")
        
        col_mode, col_input = st.columns([1, 3])
        with col_mode:
            r_mode = st.radio("Define R and Ω₀", ["Use SFRS", "Manual input"])
        
        with col_input:
            if r_mode == "Use SFRS":
                sfrs_list = [s["SFRS"] for s in sfrs_data]
                selected_sfrs = st.selectbox("SFRS", options=sfrs_list, index=None, placeholder="Type to filter...")
                R, Omega_0 = get_sfrs_factors(sfrs_data, selected_sfrs)
                if R is not None: st.caption(f"R = {R}, Ω₀ = {Omega_0}")
            else:
                selected_sfrs = "Manual Input"
                R = st.number_input("Response Modification Coefficient (R)", min_value=1.0, value=8.0, step=0.25)
                Omega_0 = st.number_input("Overstrength Factor (Ω₀)", min_value=1.0, value=3.0, step=0.25)
    else:
        selected_sfrs = "Not Required for ASCE 7-16"
        R = 1.0
        Omega_0 = 1.0

    if asce_7_22:
        st.markdown("#### Approximate Period (Tₐ)")

        col_mode, col_input = st.columns([1, 3])
        with col_mode:
            ta_mode = st.radio("Tₐ Method", ["Calculate from structure type", "Manual input", "Unknown"])

        with col_input:
            if ta_mode == "Calculate from structure type":
                structure_list = [p["Structure Type "] for p in period_data] 
                selected_structure_type = st.selectbox("Structure Type", options=structure_list, index=None, placeholder="Type to filter...")
                Ta, Ct, x = calculate_ta(period_data, selected_structure_type, h)
                if Ta is not None: st.caption(f"Tₐ = {Ta:.3f} sec  |  Cₜ = {Ct}, x = {x}")
            elif ta_mode == "Manual input":
                Ta = st.number_input("Enter Tₐ [sec]", min_value=0.01, value=1.0, step=0.1)
                selected_structure_type = "Manual Input"
                Ct, x = "-", "-"
            else:
                Ta = None
                selected_structure_type = "Unknown"
                Ct, x = "-", "-"
    else:
        ta_mode = "Not Required for ASCE 7-16"
        Ta = None
        selected_structure_type = "Not Required for ASCE 7-16"
        Ct, x = "-", "-"

    st.markdown("")

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
    default_address = "601 12th Street, Oakland, CA 94607"
    default_formatted_address = "601 City Center, 601, 12th Street, Old Oakland Historic District, Downtown Oakland, Oakland, Alameda County, California, 94607, United States"
    
    default_location_cache = {
        "address": default_address,
        "latitude": default_lat,
        "longitude": default_lon,
        "formatted_address": default_formatted_address
    }

    if sds_mode == "Fetch from USGS":
    
        col_inputs, _, col_map = st.columns([1, 0.1, 1.5])

        with col_inputs:
            coord_mode = st.radio("Location Input Method", 
                            ["Manual Lat/Lon", "Address"], 
                            index=0)

            if coord_mode == "Manual Lat/Lon":
                lat = st.number_input("Latitude", value=default_lat, format="%.8f")
                lon = st.number_input("Longitude", value=default_lon, format="%.8f")

            elif coord_mode == "Address":
                @st.cache_data(show_spinner=False, ttl=3600)  # Cache for 1 hour to prevent repeated queries
                def geocode(addr: str):
                    if not addr:
                        return None
                    return rate_limited_geocoder.geocode_with_rate_limit(addr)
                
                address = st.text_input(
                    f"Building Address:",
                    value=default_address,
                    placeholder=default_address
                )
                
                # Check if it's the default address and use cached result
                if address.strip() == default_address:
                    # Use pre-cached default location
                    lat, lon = default_location_cache["latitude"], default_location_cache["longitude"]
                    st.caption(f"🔍 {default_location_cache['formatted_address']}\n Latitude: {lat:.6f}, Longitude: {lon:.6f}")
                else:
                    # Use geocoding API for other addresses
                    location = geocode(address.strip())
                    if location:
                        lat, lon = location.latitude, location.longitude
                        st.caption(f"🔍 {location.address}\n Latitude: {lat:.6f}, Longitude: {lon:.6f}")
                        st.caption("Geocoding by [OpenStreetMap](https://www.openstreetmap.org/) via Nominatim")
                    else:
                        if address:
                            st.warning("Unable to geocode that address. Try refining it or use manual coordinates.")

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
                    st.caption(f"SDS = {SDS:.3f} g")
                except Exception as e:
                    st.error(f"Error fetching SDS: {e}")

            # Show cached SDS if available
            elif has_cached_sds:
                SDS = st.session_state.sds_value
                st.caption(f"SDS = {SDS:.3f} g")
        
        with col_map:
            # Map display
            if lat is not None and lon is not None:
                m = folium.Map(location=[lat, lon], zoom_start=16)
                tooltip = folium.Tooltip(f"<strong>Selected Site</strong><br>"
                                         f"Lat: {lat:.6f}<br>Lon: {lon:.6f}", parse_html=True)
                folium.Marker([lat, lon], tooltip=tooltip, icon=folium.Icon(icon="map-pin", prefix="fa")).add_to(m)
                st_folium(m, width=500, height=380)

    else:
        # Manual SDS input unchanged
        SDS = st.number_input("SDS [g]", min_value=0.0, value=1.0, step=0.1, format="%.3f")


with col2:
    # Check for required parameters
    if component_name is None:
        st.warning("Please select a component before proceeding.")
        st.stop()

    # Only require SFRS for ASCE 7-22
    if asce_7_22 and selected_sfrs is None:
        st.warning("Please select a SFRS before proceeding.")
        st.stop()

    # Only require Ta for ASCE 7-22 when not unknown
    if asce_7_22 and ta_mode != "Unknown" and Ta is None:
        st.warning("Please select structural type or provide approximate period before proceeding.")
        st.stop()

    if SDS is None:
        st.warning("Please provide seismic parameters before proceeding.")
        st.stop()

    # Calculations
    z_over_h = z / h if h > 0 else 0
    
    # Calculate Hf and Rmu only for ASCE 7-22
    if asce_7_22:
        Hf, a1, a2 = calculate_hf(z, h, Ta)
        Rmu = calculate_rmu(R, Ie, Omega_0)
    else:
        # For ASCE 7-16, these are not needed
        Hf, a1, a2 = None, None, None
        Rmu = None
    
    # Calculate Fp coefficient for each selected ASCE version
    results = {}
    if asce_7_16:
        ap, Rp, Omega_16 = get_component_factors_16(component_data, component_name)
        if ap is not None:
            Fp_coeff_16, Fp_calc_coeff_16, Fp_min_coeff_16, Fp_max_coeff_16 = calculate_fp_coeff_16(SDS, Ip, ap, Rp, z_over_h)
            result_16 = {
                "Fp_coeff": Fp_coeff_16,
                "Fp_calc_coeff": Fp_calc_coeff_16,
                "Fp_min_coeff": Fp_min_coeff_16,
                "Fp_max_coeff": Fp_max_coeff_16,
                "Fp": Fp_coeff_16 * Wp,
                "ap": ap,
                "Rp": Rp,
                "Omega": Omega_16
            }
            if Omega_16 is not None:
                result_16["Emh_coeff"] = Omega_16 * Fp_coeff_16
                result_16["Emh"] = Omega_16 * Fp_coeff_16 * Wp
            results["7-16"] = result_16
        else:
            results["7-16"] = None
    
    if asce_7_22:
        CAR, Rpo, Omega = get_component_factors(component_data, component_name, component_location)
        if CAR is not None:
            Fp_coeff_22, Fp_calc_coeff_22, Fp_min_coeff_22, Fp_max_coeff_22 = calculate_fp_coeff_22(SDS, Ip, Hf, Rmu, CAR, Rpo)
            result_22 = {
                "Fp_coeff": Fp_coeff_22,
                "Fp_calc_coeff": Fp_calc_coeff_22,
                "Fp_min_coeff": Fp_min_coeff_22,
                "Fp_max_coeff": Fp_max_coeff_22,
                "Fp": Fp_coeff_22 * Wp,
                "CAR": CAR,
                "Rpo": Rpo,
                "Omega": Omega
            }
            if Omega is not None:
                result_22["Emh_coeff"] = Omega * Fp_coeff_22
                result_22["Emh"] = Omega * Fp_coeff_22 * Wp
            results["7-22"] = result_22
        else:
            results["7-22"] = None

    # Display Results 
    st.markdown("### ✅ :blue[Results]")
    
    # Display results for each selected version
    if Wp > 0:
        for version, result in results.items():
            if result is not None:
                if 'Emh_coeff' in result:
                    st.markdown(f"###### :blue[ASCE {version}]: $F_{{p,coeff}} = {result['Fp_coeff']:.3f}, E_{{mh,coeff}} = {result['Emh_coeff']:.3f}$ \n $F_p = {result['Fp']:.0f}$ lb, $E_{{mh}} = {result['Emh']:.0f}$ lb (with $W_p = {Wp:.0f}$ lb)")
                else:
                    st.markdown(f"###### :blue[ASCE {version}]: $F_{{p,coeff}} = {result['Fp_coeff']:.3f}$ \n $F_p = {result['Fp']:.0f}$ lb (with $W_p = {Wp:.0f}$ lb)")
                    st.caption(f"⚠️ Omega factor not available for ASCE {version}")
            else:
                st.caption(f"⚠️ No ASCE {version} factors found for the selected component.")
    else:
        for version, result in results.items():
            if result is not None:
                if 'Emh_coeff' in result:
                    st.markdown(f"###### :blue[ASCE {version}]: $F_{{p,coeff}} = {result['Fp_coeff']:.3f}, E_{{mh,coeff}} = {result['Emh_coeff']:.3f}$")
                else:
                    st.markdown(f"###### :blue[ASCE {version}]: $F_{{p,coeff}} = {result['Fp_coeff']:.3f}$")
                    st.caption(f"⚠️ Omega factor not available for ASCE {version}")
            else:
                st.caption(f"⚠️ No ASCE {version} factors found for the selected component.")
        st.warning("Enter a non-zero $W_p$ to compute the seismic design force $F_p$.")

    # Calculation Details - Separate expanders for each ASCE version
    if asce_7_16 and results["7-16"] is not None:
        with st.expander("🔢 ASCE 7-16 Calculation Details", expanded=False):
            result_16 = results["7-16"]
            
            if Wp > 0:
                Fp_force_case = (
                    f"**Fp Force:**\n\n"
                    f"$$\n"
                    f"\\small\n"
                    f"F_p = F_{{p,coeff}} \\cdot W_p = {result_16['Fp_coeff']:.3f} \\cdot {Wp:.0f} \\text{{ lb}} = {result_16['Fp']:.0f} \\text{{ lb}}\n"
                    f"$$"
                )
            else:
                Fp_force_case = "**FP FORCE:**\n\n_(Not shown. Enter a non-zero Wp to compute Fp)_"

            calc_text_16 = f"""
**BASE EQUATION (EQN. 13.3-1):**
$$
\\small
F_p = \\frac{{0.4 \\cdot a_p \\cdot S_{{DS}} \\cdot W_p}}{{\\left( \\frac{{R_p}}{{I_p}} \\right)}} \\cdot \\left( 1 + 2 \\left( \\frac{{z}}{{h}} \\right) \\right)
$$

**PARAMETERS:**

- **_Component Amplification and Response Modification Factors (Table 13.5-1 or 13.6-1)_**:

    Component Type: _{component_name}_

    $$
    \\small
    a_p = {result_16['ap']}, \\quad R_p = {result_16['Rp']}
    $$

- **_Height Factor_**:

    $$
    \\small
    z = {z} \\text{{ ft}}, \\quad h = {h} \\text{{ ft}}
    $$

    $$
    \\small
    \\frac{{z}}{{h}} = \\frac{{{z} \\text{{ ft}}}}{{{h} \\text{{ ft}}}} = {z_over_h:.3f}
    $$

**FP COEFFICIENT:**

$$
\\small
\\begin{{aligned}}
F_{{p,coeff}} &= \\frac{{0.4 \\cdot a_p \\cdot S_{{DS}} }}{{\\left( \\frac{{R_p}}{{I_p}} \\right)}} \\cdot \\left( 1 + 2 \\left( \\frac{{z}}{{h}} \\right) \\right) \\scriptsize\\text{{ (Eqn. 13.3-1)}} \\\\
&= \\frac{{0.4 \\cdot {result_16['ap']} \\cdot {SDS:.3f}}}{{\\left( \\frac{{{result_16['Rp']}}}{{{Ip}}} \\right)}} \\cdot \\left( 1 + 2 \\cdot {z_over_h:.3f} \\right) = {result_16['Fp_calc_coeff']:.3f}
\\end{{aligned}}
$$

$$
\\small
F_{{p,min,coeff}} = 0.3 \\cdot S_{{DS}} \\cdot I_p = 0.3 \\cdot {SDS:.3f} \\cdot {Ip} = {result_16['Fp_min_coeff']:.3f} \\scriptsize\\text{{ (Eqn. 13.3-2)}}
$$

$$
\\small
F_{{p,max,coeff}} = 1.6 \\cdot S_{{DS}} \\cdot I_p = 1.6 \\cdot {SDS:.3f} \\cdot {Ip} = {result_16['Fp_max_coeff']:.3f} \\scriptsize\\text{{ (Eqn. 13.3-3)}}
$$

$$
\\small
\\begin{{aligned}}
F_{{p,coeff}} &= \\max(F_{{p,min,coeff}}, \\min(F_{{p,calc}}, F_{{p,max,coeff}})) \\\\
&= \\max({result_16['Fp_min_coeff']:.3f}, \\min({result_16['Fp_calc_coeff']:.3f}, {result_16['Fp_max_coeff']:.3f})) = {result_16['Fp_coeff']:.3f}
\\end{{aligned}}
$$

{Fp_force_case}
"""
            st.markdown(calc_text_16)
            
    if asce_7_22 and results["7-22"] is not None:
        with st.expander("🔢 ASCE 7-22 Calculation Details", expanded=False):
            result_22 = results["7-22"]
            
            # Common parameters for ASCE 7-22
            if ta_mode == "Calculate from structure type":
                ta_section = (
                    f"Structure Type: _{selected_structure_type}_ (Eqn. 12.8-8)\n\n\t"
                    f"$$ \\small T_a = C_t \\cdot h_n^x = {Ct} \\cdot {h:.1f}^{{{x}}} = {Ta:.3f} \\text{{ sec}} $$"
                )
            elif ta_mode == "Manual input":
                ta_section = f"Manually entered:  $$ \\small T_a = {Ta:.3f} \\text{{ sec}} $$"
            else:
                ta_section = ""

            # Hf case description and math
            if ta_mode != "Unknown":
                Hf_expr = "1 + a_1 \\cdot \\left( \\frac{z }{h } \\right) + a_2 \\cdot \\left( \\frac{z }{h } \\right)^{10}"
                Hf_num_expr = f"1 + {a1:.3f} · ({z_over_h:.3f}) + {a2:.3f} · ({z_over_h:.3f})^{{10}}"
                Hf_case = f"""Since $T_a$ is specified, use Eqn. 13.3-4

  $$
  \\small
  a_1 = \\min\\left(\\frac{{1}}{{T_a}}, 2.5\\right) = \\min\\left(\\frac{{1}}{{{Ta:.3f}}}, 2.5\\right) = {a1:.3f}
  $$

  $$
  \\small
  a_2 = \\max\\left(1 - \\left(\\frac{{0.4}}{{T_a}}\\right)^2, 0\\right) = \\max\\left(1 - \\left(\\frac{{0.4}}{{{Ta:.3f}}}\\right)^2, 0\\right) = {a2:.3f}
  $$"""
            else:
                Hf_expr = "1 + 2.5 \\cdot \\left( \\frac{z }{h } \\right)"
                Hf_num_expr = f"1 + 2.5 · ({z_over_h:.3f})"
                Hf_case = r"Since $T_a$ is not specified, use Eqn. 13.3-5"

            # Fp Force calculation
            if Wp > 0:
                Fp_force_case = (
                    f"**Fp Force:**\n\n"
                    f"$$\n"
                    f"\\small\n"
                    f"F_p = F_{{p,coeff}} \\cdot W_p = {result_22['Fp_coeff']:.3f} \\cdot {Wp:.0f} \\text{{ lb}} = {result_22['Fp']:.0f} \\text{{ lb}}\n"
                    f"$$"
                )
            else:
                Fp_force_case = "**FP FORCE:**\n\n_(Not shown. Enter a non-zero Wp to compute Fp)_"

            calc_text_22 = f"""
**BASE EQUATION (EQN. 13.3-1):**

$$
\\small
F_p = 0.4 \\cdot S_{{DS}} \\cdot I_p \\cdot W_p \\cdot \\left[ \\frac{{H_f}}{{R_{{\\mu}}}} \\right] \\cdot \\left[ \\frac{{C_{{AR}}}}{{R_{{po}}}} \\right]
$$

**PARAMETERS:**

- **_Approximate Fundamental Period (Tₐ)_**:

  {ta_section}

- **_Component Amplification Factor (Table 13.5-1 or 13.6-1)_**:

  Component Type: _{component_name}_

  Location: _{component_location}_

  $$
  \\small
  C_{{AR}} = {result_22['CAR']}, \\quad R_{{po}} = {result_22['Rpo']}
  $$

- **_Structure Ductility Factor (Table 12.2-1 and Eqn. 13.3-6)_**:

  SFRS Type: _{selected_sfrs}_
  
  $$
  \\small
  R = {R}, \\quad \\Omega_0 = {Omega_0}
  $$

  $$
  \\small
  R_{{\\mu}} = \\sqrt{{ \\frac{{1.1 \\cdot R}}{{I_e \\cdot \\Omega_0}} }} = \\sqrt{{ \\frac{{{1.1} \\cdot {R}}}{{{Ie} \\cdot {Omega_0}}} }} = {Rmu:.3f}
  $$

- **_Height Amplification Factor_**:

  $$
  \\small
  z = {z} \\text{{ ft}}, \\quad h = {h} \\text{{ ft}}
  $$

  $$
  \\small
  \\frac{{z}}{{h}} = \\frac{{{z} \\text{{ ft}}}}{{{h} \\text{{ ft}}}} = {z_over_h:.3f}
  $$

  {Hf_case}

  $$
  \\begin{{aligned}}
  H_f &= {Hf_expr} \\\\
  &= {Hf_num_expr} ={Hf:.3f}
  \\end{{aligned}}
  $$

**FP COEFFICIENT:**

$$
\\small
\\begin{{aligned}}
F_{{p,coeff}} &= 0.4 \\cdot S_{{DS}} \\cdot I_p \\cdot \\left[ \\frac{{H_f}}{{R_{{\\mu}}}} \\right] \\cdot \\left[ \\frac{{C_{{AR}}}}{{R_{{po}}}} \\right] \\scriptsize\\text{{ (Eqn. 13.3-1)}} \\\\
&= 0.4 \\cdot {SDS:.3f} \\cdot {Ip} \\cdot \\left( \\frac{{{Hf:.3f}}}{{{Rmu:.3f}}} \\cdot \\frac{{{result_22['CAR']}}}{{{result_22['Rpo']}}} \\right) = {result_22['Fp_calc_coeff']:.3f}
\\end{{aligned}}
$$

$$
\\small
F_{{p,min,coeff}} = 0.3 \\cdot S_{{DS}} \\cdot I_p = 0.3 \\cdot {SDS:.3f} \\cdot {Ip} = {result_22['Fp_min_coeff']:.3f} \\scriptsize\\text{{ (Eqn. 13.3-3)}} 
$$

$$
\\small
F_{{p,max,coeff}} = 1.6 \\cdot S_{{DS}} \\cdot I_p = 1.6 \\cdot {SDS:.3f} \\cdot {Ip} = {result_22['Fp_max_coeff']:.3f} \\scriptsize\\text{{ (Eqn. 13.3-2)}} 
$$

$$
\\small
\\begin{{aligned}}
F_{{p,coeff}} &= \\max(F_{{p,min,coeff}}, \\min(F_{{p,calc}}, F_{{p,max,coeff}})) \\\\
&= \\max({result_22['Fp_min_coeff']:.3f}, \\min({result_22['Fp_calc_coeff']:.3f}, {result_22['Fp_max_coeff']:.3f})) = {result_22['Fp_coeff']:.3f}
\\end{{aligned}}
$$

{Fp_force_case}
"""
            st.markdown(calc_text_22)

st.caption("FpCalc | ASCE/SEI 7-22 Chapter 13 © Degenkolb Engineers")
