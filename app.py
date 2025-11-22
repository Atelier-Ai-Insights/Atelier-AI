import streamlit as st
from services.supabase_db import supabase
from config import PLAN_FEATURES
import uuid
import time 
from services.storage import load_database 

# --- AJUSTE CRÍTICO: Importación segura del Logger ---
try:
    from services.logger import log_error, log_action
except ImportError:
    # Si no existe el archivo services/logger, usamos estas funciones 'dummy' para que no falle
    def log_error(msg, module=None, error=None):
        print(f"⚠️ [LOG ERROR - {module}]: {msg} | {error}")
    def log_action(msg, module=None):
        print(f"ℹ️ [LOG ACTION - {module}]: {msg}")

# URL base para redirecciones (Ajustado a Producción)
BASE_URL = "https://atelier-ai.streamlit.app"

# ==============================
# Autenticación con Supabase Auth
# ==============================

def show_signup_page():
    st.header("Crear Nueva Cuenta")
    email = st.text_input("Tu Correo Electrónico")
    password = st.text_input("Crea una Contraseña", type="password")
    invite_code = st.text_input("Código de Invitación de tu Empresa")
    
    if st.button("Registrarse", width='stretch'):
        if not email or not password or not invite_code:
            st.error("Por favor, completa todos los campos.")
            return
        try:
            # 1. Obtener ID del cliente (Normalizado a Mayúsculas y sin espacios)
            code_limpio = invite_code.strip().upper()
            
            response = supabase.table("clients").select("id").eq("invite_code", code_limpio).execute()
            
            if not response.data:
                st.error(f"El código de invitación '{code_limpio}' no es válido.")
                return
            
            selected_client_id = response.data[0]['id']
            
            # 2. Registro en Auth
            supabase.auth.sign_up({
                "email": email, 
                "password": password,
                "options": { 
                    "data": { 'client_id': selected_client_id },
                    "email_redirect_to": BASE_URL
                }
            })
            
            st.success("¡Registro exitoso! Revisa tu correo para confirmar tu cuenta.")
            st.info("Si no ves el correo en 1 minuto, revisa la carpeta de Spam.")
            
        except Exception as e:
            # Capturar errores comunes
            err_msg = str(e).lower()
            if "already registered" in err_msg or "user already exists" in err_msg:
                st.warning("Este correo ya está registrado. Intenta iniciar sesión.")
            else:
                st.error(f"Error en el registro: {e}")
                # Aquí ya funcionará log_error
                log_error(f"Fallo registro {email}", module="Auth", error=e)
            
    if st.button("¿Ya tienes cuenta? Inicia Sesión", type="secondary", width='stretch'):
         st.session_state.page = "login"
         st.rerun()

def show_login_page():
    st.header("Iniciar Sesión")
    
    # --- GESTIÓN DE SESIONES CONCURRENTES ---
    if 'pending_login_info' in st.session_state:
        st.warning("**Este usuario ya tiene una sesión activa en otro dispositivo.**")
        if st.button("Cerrar la otra sesión e iniciar aquí", type="primary"):
            try:
                p = st.session_state.pending_login_info
                supabase.auth.set_session(p['access_token'], p['refresh_token'])
                new_sid = str(uuid.uuid4())
                supabase.table("users").update({"active_session_id": new_sid}).eq("id", p['user_id']).execute()
                
                # Setup rápido de sesión forzada
                st.session_state.logged_in = True
                st.session_state.user_id = p['user_id']
                st.session_state.session_id = new_sid
                st.rerun()
            except Exception as e:
                st.error("Error al forzar sesión.")
                log_error("Error forcing session", module="Auth", error=e)
        return

    # --- LOGIN NORMAL ---
    email = st.text_input("Correo Electrónico")
    password = st.text_input("Contraseña", type="password")
    
    if st.button("Ingresar", width='stretch'):
        try:
            # 1. Autenticación (Auth)
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            user = res.user
            
            if not user:
                st.error("Credenciales inválidas.")
                return

            # 2. BUSCAR PERFIL PÚBLICO
            # Usamos maybe_single() para evitar error si no existe (y poder repararlo)
            profile_res = supabase.table("users").select("*, clients(client_name, plan)").eq("id", user.id).maybe_single().execute()
            
            # --- LÓGICA DE AUTO-REPARACIÓN (Por si falló el Trigger) ---
            if not profile_res.data:
                with st.spinner("Configurando tu cuenta por primera vez..."):
                    try:
                        meta_client_id = user.user_metadata.get('client_id')
                        
                        # Fallback si no hay metadata: usar DEMO
                        if not meta_client_id:
                            demo_res = supabase.table("clients").select("id").eq("invite_code", "DEMO-30-DIAS").execute()
                            if demo_res.data: 
                                meta_client_id = demo_res.data[0]['id']
                            else:
                                raise Exception("No se encontró cliente Demo para asignar.")

                        # Crear el perfil manualmente
                        new_profile = {
                            "id": user.id,
                            "email": user.email,
                            "client_id": meta_client_id,
                            "rol": "user"
                        }
                        supabase.table("users").insert(new_profile).execute()
                        
                        # Volver a consultar ahora que existe
                        profile_res = supabase.table("users").select("*, clients(client_name, plan)").eq("id", user.id).single().execute()
                        log_action(f"Perfil auto-reparado para {user.email}", module="Auth")
                        
                    except Exception as e_repair:
                        st.error(f"Error crítico configurando cuenta: {e_repair}")
                        log_error("Auto-repair failed", module="Auth", error=e_repair)
                        return

            # 3. Cargar Datos en Sesión
            profile = profile_res.data
            client_data = profile.get('clients', {})
            
            if not client_data: client_data = {} # Protección extra

            new_sid = str(uuid.uuid4())
            supabase.table("users").update({"active_session_id": new_sid}).eq("id", user.id).execute()
            
            st.session_state.access_token = res.session.access_token
            st.session_state.refresh_token = res.session.refresh_token
            st.session_state.logged_in = True
            st.session_state.user = profile['email']
            st.session_state.user_id = user.id
            st.session_state.session_id = new_sid
            
            # Carga segura de datos del cliente
            st.session_state.cliente = client_data.get('client_name', 'demo').lower()
            st.session_state.plan = client_data.get('plan', 'Explorer')
            st.session_state.plan_features = PLAN_FEATURES.get(st.session_state.plan, PLAN_FEATURES['Explorer'])
            st.session_state.is_admin = (profile.get('rol') == 'admin')
            st.session_state.login_timestamp = time.time()
            
            # Carga de base de datos vectorial
            with st.spinner(f"Iniciando entorno de {st.session_state.cliente.title()}..."):
                st.session_state.db_full = load_database(st.session_state.cliente)
            
            st.rerun()

        except Exception as e:
            err_msg = str(e).lower()
            if "email not confirmed" in err_msg:
                st.warning("Tu correo no ha sido confirmado. Revisa tu bandeja de entrada.")
            elif "invalid login credentials" in err_msg:
                st.error("Correo o contraseña incorrectos.")
            else:
                st.error(f"Error desconocido: {e}")
                log_error("Login Error", module="Auth", error=e)

    # Botones footer
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Registrarse", key="go_signup"):
            st.session_state.page = "signup"; st.rerun()
    with col_b:
        if st.button("Recuperar Clave", key="go_reset"):
            st.session_state.page = "reset_password"; st.rerun()

def show_reset_password_page():
    st.header("Recuperar Contraseña")
    email = st.text_input("Correo asociado")
    if st.button("Enviar Link"):
        try:
            supabase.auth.reset_password_for_email(email, options={"redirect_to": f"{BASE_URL}/?type=recovery"})
            st.success("Correo enviado. Revisa tu bandeja de entrada.")
        except Exception as e: 
            st.error(f"Error: {e}")
            log_error("Reset password failed", module="Auth", error=e)
            
    if st.button("Volver"): 
        st.session_state.page = "login"
        st.rerun()

# Functions placeholders (asegúrate de tener su implementación si las usas)
def show_otp_verification_page(otp_code):
    pass 

def show_set_new_password_page(token=None):
    pass
