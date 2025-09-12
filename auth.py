import streamlit as st
import msal
import requests
import json

class MicrosoftAuth:
    def __init__(self):
        # Get configuration from Streamlit secrets
        self.client_id = st.secrets["microsoft"]["client_id"]
        self.client_secret = st.secrets["microsoft"]["client_secret"]
        self.tenant_id = st.secrets["microsoft"]["tenant_id"]
        
        # Get redirect URI from secrets or determine from current URL
        self.redirect_uri = st.secrets["microsoft"].get("redirect_uri")
        if not self.redirect_uri:
            # Auto-detect redirect URI from current request
            try:
                if hasattr(st, 'get_option'):
                    # For newer Streamlit versions
                    base_url = st.get_option("server.baseUrlPath") or ""
                    server_port = st.get_option("server.port")
                    self.redirect_uri = f"http://localhost:{server_port}{base_url}"
                else:
                    # Fallback
                    self.redirect_uri = "http://localhost:8501"
            except:
                # Final fallback
                self.redirect_uri = "http://localhost:8501"
        
        self.scope = ["https://graph.microsoft.com/User.Read"]
        
        # Create MSAL app
        self.app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            client_credential=self.client_secret,
        )
    
    def get_auth_url(self):
        """Generate Microsoft OAuth authorization URL"""
        auth_url = self.app.get_authorization_request_url(
            self.scope,
            redirect_uri=self.redirect_uri,
        )
        return auth_url
    
    def get_token_from_code(self, code):
        """Exchange authorization code for access token"""
        result = self.app.acquire_token_by_authorization_code(
            code,
            scopes=self.scope,
            redirect_uri=self.redirect_uri,
        )
        return result
    
    def get_user_info(self, access_token):
        """Get user information from Microsoft Graph API"""
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        response = requests.get(
            'https://graph.microsoft.com/v1.0/me',
            headers=headers
        )
        
        if response.status_code == 200:
            return response.json()
        return None
    
    def is_user_authorized(self, user_info):
        """Check if user is authorized to access the app"""
        # Get allowed users from secrets
        allowed_users = st.secrets.get("microsoft", {}).get("allowed_users", [])
        
        if not allowed_users:  # If no restrictions, allow all
            return True
            
        user_email = user_info.get("mail", "").lower()
        user_upn = user_info.get("userPrincipalName", "").lower()
        
        # Check if user email or UPN is in allowed list
        return any(
            user_email == allowed.lower() or user_upn == allowed.lower()
            for allowed in allowed_users
        )

def login_ui():
    """Microsoft 365 authentication UI"""
    # Initialize session state
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user_info" not in st.session_state:
        st.session_state.user_info = None
    if "access_token" not in st.session_state:
        st.session_state.access_token = None
    if "guest_mode" not in st.session_state:
        st.session_state.guest_mode = False
    
    # Check if user is already authenticated or in guest mode
    if st.session_state.authenticated or st.session_state.guest_mode:
        return
    
    # Initialize Microsoft auth
    try:
        ms_auth = MicrosoftAuth()
    except Exception as e:
        st.error(f"Authentication configuration error: {str(e)}")
        st.stop()
    
    # Check for authorization code in URL parameters
    query_params = st.query_params
    if "code" in query_params:
        code = query_params["code"]
        
        # Exchange code for token
        token_result = ms_auth.get_token_from_code(code)
        
        if "access_token" in token_result:
            # Get user info
            user_info = ms_auth.get_user_info(token_result["access_token"])
            
            if user_info:
                # Check if user is authorized
                if ms_auth.is_user_authorized(user_info):
                    st.session_state.authenticated = True
                    st.session_state.user_info = user_info
                    st.session_state.access_token = token_result["access_token"]
                    
                    # Clear URL parameters
                    st.query_params.clear()
                    st.rerun()
                else:
                    st.error("You are not authorized to access this application.")
                    st.stop()
            else:
                st.error("Failed to retrieve user information.")
                st.stop()
        else:
            st.error(f"Authentication failed: {token_result.get('error_description', 'Unknown error')}")
            st.stop()
    
    # Show login form
    st.title("🔐 FpCalc Login")
    st.markdown("Please sign in with your Microsoft 365 account to access FpCalc.")
    
    # Get authorization URL
    auth_url = ms_auth.get_auth_url()
    
    # Display the sign-in button
    st.markdown(f'<a href="{auth_url}" target="_self" style="text-decoration: none;"><button style="background-color: #0078d4; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-size: 16px; font-weight: 500;">Sign in with Microsoft 365</button></a>', unsafe_allow_html=True)
    
    # Display the guest access button
    if st.button("continue as guest", key="guest_button", help="Access the app without signing in"):
        st.session_state.guest_mode = True
        st.rerun()
    
    # Style the button to look like a link
    st.markdown("""
    <style>
    div[data-testid="stButton"] button[kind="secondary"] {
        background: transparent !important;
        color: #666 !important;
        border: none !important;
        font-size: 14px !important;
        text-decoration: underline !important;
        box-shadow: none !important;
        padding: 0 !important;
        height: auto !important;
        text-align: left !important;
        justify-content: flex-start !important;
    }
    div[data-testid="stButton"] button[kind="secondary"]:hover {
        background: transparent !important;
        color: #333 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.stop()

def logout_ui():
    """Logout UI in sidebar"""
    with st.sidebar:
        if st.session_state.authenticated and st.session_state.user_info:
            # Authenticated user - compact display
            user_info = st.session_state.user_info
            display_name = user_info.get("displayName", "User")
            email = user_info.get("mail", user_info.get("userPrincipalName", ""))
            
            # User info display
            st.write(f"👤 **{display_name}**")
            st.write(f"📧 {email}")
            
            if st.button("Logout", type="secondary", key="logout_btn"):
                # Clear session state
                for key in ["authenticated", "user_info", "access_token"]:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
        
        elif st.session_state.guest_mode:
            # Guest user
            st.write("👤 **Guest User**")
            st.write("📧 No account linked")
            
            if st.button("Exit Guest Mode", type="secondary", key="exit_guest_btn"):
                # Clear session state
                for key in ["guest_mode"]:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
