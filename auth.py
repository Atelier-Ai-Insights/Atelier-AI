import streamlit as st
from services.supabase_db import supabase
from config import PLAN_FEATURES
import uuid
import time 
from services.storage import load_database 
from services.logger import log_error, log_action
# ¡ESTA IMPORTACIÓN ES NECESARIA AHORA!
from supabase.lib.client_options import ClientOptions 


# ==============================
# Autenticación con Supabase Auth
# ==============================

def show_signup_page():
    # ... (Esta función no cambia) ...
    st.header("Crear Nueva Cuenta")
    email = st.text_input("Tu Correo Electrónico")
    password = st.text_input("Crea una Contraseña", type="password")
    invite_code = st.text_input("Código de Invitación de tu Empresa")
    if st.button("Registrarse", width='stretch'):
        if not email or not password or not invite_code:
            st.error("Por favor, completa todos loscampos.")
            return
        try:
            client_response = supabase.table("clients").select("id").eq("invite_code", invite_code).single().execute()
            if not client_response.data:
                st.error("El código de invitación no es válido.")
                log_action(f"Intento de registro fallido: Código inválido '{invite_code}' para {email}", module="Auth")
                return
            selected_client_id = client_response.data['id']
            auth_response = supabase.auth.sign_up({
                "email": email, "password": password,
                "options": { "data": { 'client_id': selected_client_id } }
            })
            st.success("¡Registro exitoso! Revisa tu correo para confirmar tu cuenta.")
            log_action(f"Nuevo usuario registrado: {email}", module="Auth")
        except Exception as e:
            st.error(f"Error en el registro: {e}")
            log_error(f"Error crítico en registro de usuario {email}", module="Auth", error=e)
    if st.button("¿Ya tienes cuenta? Inicia Sesión", type="secondary", width='stretch'):
         st.session_state.page = "login"
         st.rerun()

def show_login_page():
    # ... (Esta función no cambia) ...
    st.header("Iniciar Sesión")
    if 'pending_login_info' in st.session_state:
        st.warning("**Este usuario ya tiene una sesión activa en otro dispositivo.**")
        st.write("¿Qué deseas hacer?")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Cerrar la otra sesión e iniciar aquí", width='stretch', type="primary"):
                try:
                    pending_info = st.session_state.pending_login_info
                    user_id = pending_info['user_id']
                    st.session_state.access_token = pending_info['access_token']
                    st.session_state.refresh_token = pending_info['refresh_token']
                    supabase.auth.set_session(st.session_state.access_token, st.session_state.refresh_token)
                    new_session_id = str(uuid.uuid4())
                    supabase.table("users").update({"active_session_id": new_session_id}).eq("id", user_id).execute()
                    user_profile = supabase.table("users").select("*, rol, clients(client_name, plan)").eq("id", user_id).single().execute()
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
    else:
        email = st.text_input("Correo Electrónico", placeholder="usuario@empresa.com")
        password = st.text_input("Contraseña", type="password", placeholder="password")
        if st.button("Ingresar", width='stretch'):
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
                        st.error("Perfil de usuario no encontrado. Contacta al administrador.")
                        log_error(f"Usuario autenticado pero sin perfil en tabla 'users': {email}", module="Auth", level="ERROR")
            except Exception as e:
                st.error(f"Credenciales incorrectas o cuenta no confirmada.")
                log_action(f"Intento fallido de login: {email}", module="Auth")
        if st.button("¿No tienes cuenta? Regístrate", type="secondary", width='stretch'):
            st.session_state.page = "signup"
            st.rerun()
        if st.button("¿Olvidaste tu contraseña?", type="secondary", width='stretch'):
            st.session_state.page = "reset_password"
            st.rerun()

def show_reset_password_page():
    # ... (Esta función no cambia) ...
    st.header("Restablecer Contraseña")
    st.write("Ingresa tu correo electrónico y te enviaremos un enlace para restablecer tu contraseña.")
    email = st.text_input("Tu Correo Electrónico")
    if st.button("Enviar enlace de recuperación", width='stretch'):
        if not email:
            st.warning("Por favor, ingresa tu correo electrónico.")
            return
        try:
            supabase.auth.reset_password_for_email(email)
            st.success("¡Correo enviado! Revisa tu bandeja de entrada.")
            st.info("Sigue las instrucciones del correo para crear una nueva contraseña. Una vez creada, podrás iniciar sesión.")
            log_action(f"Solicitud recuperación contraseña: {email}", module="Auth")
        except Exception as e:
            st.error(f"Error al enviar el correo: {e}")
            log_error(f"Fallo envío correo recuperación: {email}", module="Auth", error=e)
    if st.button("Volver a Iniciar Sesión", type="secondary", width='stretch'):
         st.session_state.page = "login"
         st.rerun()

# --- NUEVA FUNCIÓN PARA VALIDAR EL CÓDIGO OTP ---
def show_otp_verification_page(otp_code):
    """
    Muestra una pantalla para confirmar el correo cuando el enlace solo tiene un código.
    """
    st.header("Verificación de Seguridad")
    st.write("Hemos detectado un código de recuperación. Para continuar, confirma tu correo electrónico.")
    
    # Campo para que el usuario confirme su email
    email_verify = st.text_input("Confirma tu Correo Electrónico")
    
    if st.button("Verificar y Continuar", width='stretch', type="primary"):
        if not email_verify:
            st.warning("Debes ingresar tu correo.")
            return
            
        try:
            # Usamos verify_otp para canjear el código por una sesión
            res = supabase.auth.verify_otp({
                "email": email_verify,
                "token": otp_code,
                "type": "recovery"
            })
            
            if res.session:
                # Guardamos la sesión para que app.py sepa que estamos logueados
                st.session_state.access_token = res.session.access_token
                st.session_state.refresh_token = res.session.refresh_token
                st.session_state.logged_in = True # Importante para saltar al form de password
                
                st.success("Identidad verificada. Redirigiendo...")
                time.sleep(1)
                st.rerun()
            else:
                st.error("El código es válido pero no se pudo iniciar la sesión.")
        except Exception as e:
            st.error(f"Error de verificación: {e}")
            log_error("Fallo verificación OTP recuperación", module="Auth", error=e)


# --- FUNCIÓN CORREGIDA PARA ACTUALIZAR PASSWORD ---
def show_set_new_password_page(access_token=None):
    """
    Muestra el formulario para cambiar la contraseña.
    Ahora acepta access_token opcional, porque si venimos del OTP, ya tenemos sesión.
    """
    st.header("Establecer Nueva Contraseña")
    st.write("Por favor, crea una nueva contraseña.")

    new_password = st.text_input("Nueva Contraseña", type="password")
    confirm_password = st.text_input("Confirmar Nueva Contraseña", type="password")

    if st.button("Actualizar Contraseña", width='stretch'):
        if not new_password or not confirm_password:
            st.error("Completa ambos campos.")
            return
        
        if new_password != confirm_password:
            st.error("Las contraseñas no coinciden.")
            return
            
        if len(new_password) < 6:
            st.error("La contraseña debe tener al menos 6 caracteres.")
            return

        try:
            # Al usar update_user, Supabase usa la sesión activa.
            # No necesitamos pasar el token manualmente si ya hicimos set_session o verify_otp.
            user_response = supabase.auth.update_user(
                attributes={"password": new_password}
            )
            
            log_action(f"Contraseña actualizada exitosamente para: {user_response.user.email}", module="Auth")
            
            # Cerrar sesión para obligar al usuario a entrar con la nueva clave
            supabase.auth.sign_out() 
            st.session_state.logged_in = False
            st.session_state.clear()
            
            st.success("¡Contraseña actualizada con éxito!")
            st.info("Ahora puedes iniciar sesión con tu nueva contraseña.")
            time.sleep(3)
            
            # Limpiar URL y redirigir
            if hasattr(st, "query_params"):
                 st.query_params.clear() 
            else:
                 st.experimental_set_query_params()

            st.session_state.page = "login"
            st.rerun()

        except Exception as e:
            st.error(f"Error al actualizar la contraseña: {e}")
            log_error("Error crítico al actualizar contraseña", module="Auth", error=e)

    if st.button("Cancelar", type="secondary", width='stretch'):
        supabase.auth.sign_out()
        if hasattr(st, "query_params"):
             st.query_params.clear() 
        else:
             st.experimental_set_query_params()
        st.session_state.page = "login"
        st.rerun()
