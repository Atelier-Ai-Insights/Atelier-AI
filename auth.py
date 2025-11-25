import streamlit as st
from services.supabase_db import supabase
from config import PLAN_FEATURES
import uuid
import time 
from services.storage import load_database 
from services.logger import log_error, log_action

# ==============================
# Autenticación con Supabase Auth
# ==============================

def show_login_page():
    st.header("Iniciar Sesión")
    
    # --- LÓGICA DE SESIÓN DUPLICADA (Login Forzado) ---
    if 'pending_login_info' in st.session_state:
        st.warning("**Este usuario ya tiene una sesión activa en otro dispositivo.**")
        st.write("¿Qué deseas hacer?")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Cerrar la otra sesión e iniciar aquí", width='stretch', type="primary"):
                try:
                    pending_info = st.session_state.pending_login_info
                    user_id = pending_info['user_id']
                    
                    # 1. Restaurar la sesión localmente
                    st.session_state.access_token = pending_info['access_token']
                    st.session_state.refresh_token = pending_info['refresh_token']
                    supabase.auth.set_session(st.session_state.access_token, st.session_state.refresh_token)
                    
                    # 2. Generar nuevo ID y actualizar DB
                    new_session_id = str(uuid.uuid4())
                    supabase.table("users").update({"active_session_id": new_session_id}).eq("id", user_id).execute()
                    
                    # 3. Cargar perfil
                    user_profile = supabase.table("users").select("*, rol, clients(client_name, plan)").eq("id", user_id).single().execute()
                    
                    st.session_state.logged_in = True
                    st.session_state.user = user_profile.data['email']
                    st.session_state.user_id = user_id
                    st.session_state.session_id = new_session_id 
                    
                    client_info = user_profile.data.get('clients', {})
                    st.session_state.cliente = client_info.get('client_name', 'generico').lower() if client_info else 'generico'
                    st.session_state.plan = client_info.get('plan', 'Explorer') if client_info else 'Explorer'
                    st.session_state.plan_features = PLAN_FEATURES.get(st.session_state.plan, PLAN_FEATURES['Explorer'])
                    st.session_state.is_admin = (user_profile.data.get('rol', '') == 'admin')
                    st.session_state.login_timestamp = time.time() 
                    
                    with st.spinner("Cargando repositorio de conocimiento..."):
                        st.session_state.db_full = load_database(st.session_state.cliente)
                    
                    st.session_state.pop('pending_login_info')
                    log_action(f"Login forzado exitoso: {st.session_state.user}", module="Auth")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Error al forzar inicio de sesión: {e}")
                    log_error("Error forzando sesión", module="Auth", error=e)
                    
        with col2:
            if st.button("Cancelar", width='stretch', type="secondary"):
                st.session_state.pop('pending_login_info')
                st.rerun()
                
    # --- LOGIN NORMAL ---
    else:
        email = st.text_input("Correo Electrónico", placeholder="usuario@empresa.com")
        password = st.text_input("Contraseña", type="password", placeholder="password")
        
        st.write("") # Espaciador
        
        if st.button("Ingresar", width='stretch', type="primary"):
            try:
                response = supabase.auth.sign_in_with_password({"email": email, "password": password})
                user_id = response.user.id
                access_token = response.session.access_token
                refresh_token = response.session.refresh_token
                
                supabase.auth.set_session(access_token, refresh_token)
                
                user_profile_check = supabase.table("users").select("active_session_id").eq("id", user_id).single().execute()
                
                if user_profile_check.data and user_profile_check.data.get('active_session_id'):
                    st.session_state.pending_login_info = {
                        'user_id': user_id,
                        'access_token': access_token,
                        'refresh_token': refresh_token
                    }
                    st.rerun()
                else:
                    new_session_id = str(uuid.uuid4())
                    user_profile = supabase.table("users").select("*, rol, clients(client_name, plan)").eq("id", user_id).single().execute()
                    
                    # Validar que tenga cliente asignado
                    if user_profile.data and user_profile.data.get('clients'):
                        supabase.table("users").update({"active_session_id": new_session_id}).eq("id", user_id).execute()
                        
                        st.session_state.access_token = access_token
                        st.session_state.refresh_token = refresh_token
                        client_info = user_profile.data['clients']
                        
                        st.session_state.logged_in = True
                        st.session_state.user = user_profile.data['email']
                        st.session_state.user_id = user_id
                        st.session_state.session_id = new_session_id
                        
                        st.session_state.cliente = client_info['client_name'].lower()
                        st.session_state.plan = client_info.get('plan', 'Explorer')
                        st.session_state.plan_features = PLAN_FEATURES.get(st.session_state.plan, PLAN_FEATURES['Explorer'])
                        st.session_state.is_admin = (user_profile.data.get('rol', '') == 'admin')
                        st.session_state.login_timestamp = time.time() 
                        
                        with st.spinner("Cargando repositorio de conocimiento..."):
                            st.session_state.db_full = load_database(st.session_state.cliente)
                        
                        log_action(f"Login exitoso: {email}", module="Auth")
                        st.rerun()
                    else:
                        st.error("Usuario sin empresa asignada. Contacta al administrador.")
                        supabase.auth.sign_out()
                        
            except Exception as e:
                error_msg = str(e).lower()
                if "invalid login credentials" in error_msg:
                    st.error("🚫 Contraseña incorrecta o usuario no encontrado.")
                elif "email not confirmed" in error_msg:
                    st.warning("📧 Tu email no ha sido confirmado. Revisa tu bandeja de entrada.")
                else:
                    st.error(f"Error de acceso: {e}")
        
        if st.button("¿Olvidaste tu contraseña?", type="secondary", width='stretch'):
            st.session_state.page = "reset_password"
            st.rerun()

def show_reset_password_page():
    st.header("Restablecer Contraseña")
    st.write("Ingresa tu correo electrónico y te enviaremos un enlace para restablecer tu contraseña.")
    email = st.text_input("Tu Correo Electrónico")
    if st.button("Enviar enlace de recuperación", width='stretch', type="primary"):
        if not email:
            st.warning("Por favor, ingresa tu correo electrónico.")
            return
        try:
            # Envía el correo con el OTP/Link
            supabase.auth.reset_password_for_email(email, options={"redirect_to": "https://atelier-ai.streamlit.app"})
            st.success("¡Correo enviado! Revisa tu bandeja de entrada.")
            log_action(f"Solicitud recuperación: {email}", module="Auth")
        except Exception as e:
            st.error(f"Error al enviar el correo: {e}")
            
    if st.button("Volver a Iniciar Sesión", type="secondary", width='stretch'):
         st.session_state.page = "login"
         st.rerun()

def show_otp_verification_page(otp_code, context="recovery"):
    """
    Pantalla intermedia: Pide el email para verificar el código OTP que llegó por URL.
    """
    st.header("Verificación de Seguridad")
    
    if context == "invite":
        st.info("Para activar tu invitación, confirma tu correo electrónico.")
        btn_label = "Validar y Activar"
        # Para invitaciones via API Admin, a veces el tipo es 'invite' o 'signup'
        # Probamos 'invite' por defecto
        otp_type = "invite" 
    else:
        st.write("Confirma tu correo para restablecer tu contraseña.")
        btn_label = "Verificar"
        otp_type = "recovery"

    email_verify = st.text_input("Confirma tu Correo Electrónico")
    
    if st.button(btn_label, width='stretch', type="primary"):
        if not email_verify:
            st.warning("Debes ingresar tu correo.")
            return
        
        try:
            # Intentamos verificar el OTP
            res = supabase.auth.verify_otp({
                "email": email_verify,
                "token": otp_code,
                "type": otp_type
            })
            
            if res.session:
                # Si hay sesión, guardamos tokens
                st.session_state.access_token = res.session.access_token
                st.session_state.refresh_token = res.session.refresh_token
                
                # Marcamos flag temporal para mostrar la pantalla de Password
                st.session_state['temp_auth_verified'] = True
                st.session_state['temp_auth_type'] = context
                
                st.success("¡Verificado! Configurando cuenta...")
                time.sleep(1)
                st.rerun()
            else:
                st.error("El código no es válido o ha expirado.")
        
        except Exception as e:
            # Fallback para invitaciones: A veces Supabase las trata como 'signup'
            if context == "invite" and "type" in str(e):
                try:
                    res = supabase.auth.verify_otp({"email": email_verify, "token": otp_code, "type": "signup"})
                    if res.session:
                        st.session_state.access_token = res.session.access_token
                        st.session_state.refresh_token = res.session.refresh_token
                        st.session_state['temp_auth_verified'] = True
                        st.session_state['temp_auth_type'] = context
                        st.rerun()
                        return
                except: pass
            
            st.error(f"Error de verificación: {e}")

def show_set_new_password_page(access_token=None, context="recovery"):
    """
    Pantalla final: Establecer la contraseña nueva.
    """
    if context == "invite":
        st.header("¡Bienvenido a Atelier!")
        st.info("Para activar tu cuenta, crea una contraseña segura.")
        btn_label = "Activar Cuenta"
    else:
        st.header("Restablecer Contraseña")
        st.write("Por favor, crea una nueva contraseña para recuperar tu acceso.")
        btn_label = "Actualizar Contraseña"

    new_password = st.text_input("Nueva Contraseña", type="password")
    confirm_password = st.text_input("Confirmar Nueva Contraseña", type="password")

    if st.button(btn_label, width='stretch', type="primary"):
        if not new_password or not confirm_password:
            st.error("Completa ambos campos."); return
        if new_password != confirm_password:
            st.error("Las contraseñas no coinciden."); return
        if len(new_password) < 6:
            st.error("La contraseña debe tener al menos 6 caracteres."); return

        try:
            # Actualizamos la contraseña del usuario activo
            user_response = supabase.auth.update_user(attributes={"password": new_password})
            
            # Cerramos sesión para obligar login limpio
            supabase.auth.sign_out() 
            st.session_state.logged_in = False
            st.session_state.clear() # Limpia flags temporales
            
            if context == "invite":
                st.success("¡Cuenta activada correctamente! Ya puedes iniciar sesión.")
            else:
                st.success("¡Contraseña actualizada con éxito!")
            
            time.sleep(3)
            
            # Limpiar params URL si existen
            if hasattr(st, "query_params"): st.query_params.clear()
            else: st.experimental_set_query_params()
            
            st.session_state.page = "login"
            st.rerun()
            
        except Exception as e:
            st.error(f"Error al procesar la solicitud: {e}")
