import math


# ---------------- Building parameters ----------------

def get_sfrs_factors(sfrs_data, selected_sfrs):
    if selected_sfrs is None:
        return None, None
    for row in sfrs_data:
        if row["SFRS"].strip().lower() == selected_sfrs.strip().lower():
            return row["R"], row["Omega"]
    return 1.0, 1.0  # Default fallback

def get_component_factors(component_data, component_name, location):
    if component_name is None:
        return 1.0, 1.0
    key = "Component" if "Component" in component_data[0] else "Components"
    for row in component_data:
        if row[key].strip().lower() == component_name.strip().lower():
            car = row["CAR_above"] if location == "Supported Above Grade" else row["CAR_below"]
            rpo = row["Rpo"]
            return car or 1.0, rpo or 1.5
    return 1.0, 1.0  # Default fallback

def calculate_ta(period_data, structure_type, hn):
    if structure_type is None:
        return None, None, None
    for row in period_data:
        if row["Structure Type "].strip().lower() == structure_type.strip().lower():
            Ct = row["Ct"]
            x = row["x"]
            Ta = Ct * hn ** x
            return Ta, Ct, x
    return None, None, None  # Default fallback


# ---------------- Component parameters ----------------

def calculate_hf(z, h, Ta):
    if z > h:
        z = h
    if Ta is None:
        return 1 + 2.5 * (z / h), None, None
    elif Ta <= 0 or h <= 0:
        return 3.5
    else:
        a1 = min(1 / Ta, 2.5)
        a2 = max(1 - (0.4 / Ta) ** 2, 0)
        return 1 + a1 * (z / h) + a2 * (z / h) ** 10, a1, a2
    

def calculate_rmu(R, Ie, Omega_0):
    try:
        rmu = math.sqrt(1.1 * R / (Ie * Omega_0))
        return max(rmu, 1.3)
    except ZeroDivisionError:
        return 1.3

def calculate_fp_coeff(SDS, Ip, Wp, Hf, Rmu, CAR, Rpo):
    Fp_calc = 0.4 * SDS * Ip * (Hf / Rmu) * (CAR / Rpo)
    Fp_min = 0.3 * SDS * Ip
    Fp_max = 1.6 * SDS * Ip
    Fp = max(min(Fp_calc, Fp_max), Fp_min)
    return Fp, Fp_calc, Fp_min, Fp_max