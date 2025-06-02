import streamlit as st
import bcrypt

def get_users_from_secrets():
    return st.secrets["users"]

def check_password(username, password, users):
    username = username.lower()
    if username in users:
        hashed = users[username].encode("utf-8")
        return bcrypt.checkpw(password.encode("utf-8"), hashed)
    return False

def login_ui(users):
    # ---- Initialize session state variables BEFORE any widgets ----
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "username" not in st.session_state:
        st.session_state.username = ""
    if "login_error" not in st.session_state:
        st.session_state.login_error = False

    # ---- Login form ----
    if not st.session_state.authenticated:
        st.title("🔐 Secure Login")

        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            login_button = st.form_submit_button("Login")

        if login_button:
            if check_password(username, password, users):
                st.session_state.authenticated = True
                st.session_state.username = username
                st.session_state.login_error = False
                st.rerun()
            else:
                st.session_state.login_error = True
                st.rerun()

        if st.session_state.login_error:
            st.error("Login failed. Try again.")
        
        st.stop()

    # ---- Logout button in sidebar ----
    with st.sidebar:
        st.write(f"👤 Logged in as: {st.session_state.username}")
        if st.button("Logout"):
            for key in ["authenticated", "username", "login_error"]:
                st.session_state[key] = False if key == "authenticated" else ""
            st.rerun()
