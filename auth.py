import streamlit as st
from services.supabase_db import supabase
from config import PLAN_FEATURES
import uuid
import time # Necesario para el timestamp

# ==============================
# Autenticación con Supabase Auth
# ==============================

def show_signup_page():
    # ... (Esta función no cambia) ...
    st.header("Crear Nueva Cuenta")
    email = st.text_input("Tu Correo Electrónico")
    password = st.text_input("Crea una Contraseña", type="password")
    invite_code = st.text_input("Código de Invitación de tu Empresa")

    if st.button("Registrarse", use_container_width=True):
        if not email or not password or not invite_code:
            st.error("Por favor, completa todos loscampos.")
            return

        try:
            client_response = supabase.table("clients").select("id").eq("invite_code", invite_code).single().execute()
            if not client_response.data:
                st.error("El código de invitación no es válido.")
                return
            selected_client_id = client_response.data['id']
            auth_response = supabase.auth.sign_up({
                "email": email, "password": password,
                "options": { "data": { 'client_id': selected_client_id } }
            })
            st.success("¡Registro exitoso! Revisa tu correo para confirmar tu cuenta.")
        except Exception as e:
            print(f"----------- ERROR DETALLADO DE REGISTRO -----------\n{e}\n-------------------------------------------------")
            st.error(f"Error en el registro: {e}")

    if st.button("¿Ya tienes cuenta? Inicia Sesión", type="secondary", use_container_width=True):
         st.session_state.page = "login"
         st.rerun()

def show_login_page():
    st.header("Iniciar Sesión")

    # --- ¡NUEVA LÓGICA DE LOGIN EN DOS PASOS! ---
    
    # PASO 2.1: MOSTRAR CONFIRMACIÓN SI HAY UN LOGIN PENDIENTE
    if 'pending_login_info' in st.session_state:
        st.warning("**Este usuario ya tiene una sesión activa en otro dispositivo.**")
        st.write("¿Qué deseas hacer?")
        
        col1, col2 = st.columns(2)
        
        # Botón para forzar el inicio de sesión
        with col1:
            if st.button("Cerrar la otra sesión e iniciar aquí", use_container_width=True, type="primary"):
                try:
                    # Recuperamos los datos del usuario
                    pending_info = st.session_state.pending_login_info
                    user_id = pending_info['user_id']
                    
                    # Guardamos los tokens del login pendiente en la sesión principal
                    st.session_state.access_token = pending_info['access_token']
                    st.session_state.refresh_token = pending_info['refresh_token']
                    supabase.auth.set_session(st.session_state.access_token, st.session_state.refresh_token)
                    
                    # Generamos el NUEVO ID de sesión
                    new_session_id = str(uuid.uuid4())
                    
                    # Forzamos la actualización en la DB, "matando" la sesión antigua
                    supabase.table("users").update({"active_session_id": new_session_id}).eq("id", user_id).execute()
                    
                    # Obtenemos el perfil (¡ya está autenticado!)
                    user_profile = supabase.table("users").select("*, rol, clients(client_name, plan)").eq("id", user_id).single().execute()
                    
                    # Guardamos todos los datos en el session_state
                    client_info = user_profile.data['clients']
                    st.session_state.logged_in = True
                    st.session_state.user = user_profile.data['email']
                    st.session_state.user_id = user_id
                    st.session_state.session_id = new_session_id
                    st.session_state.cliente = client_info['client_name'].lower()
                    st.session_state.plan = client_info.get('plan', 'Explorer')
                    st.session_state.plan_features = PLAN_FEATURES.get(st.session_state.plan, PLAN_FEATURES['Explorer'])
                    st.session_state.is_admin = (user_profile.data.get('rol', '') == 'admin')
                    st.session_state.login_timestamp = time.time() # Guardamos la hora de inicio de sesión
                    
                    # Limpiamos el estado pendiente y recargamos la app
                    st.session_state.pop('pending_login_info')
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Error al forzar inicio de sesión: {e}")

        # Botón para cancelar
        with col2:
            if st.button("Cancelar", use_container_width=True, type="secondary"):
                # Simplemente limpiamos el estado pendiente y recargamos
                st.session_state.pop('pending_login_info')
                st.rerun()

    # PASO 2.2: MOSTRAR FORMULARIO DE LOGIN NORMAL
    else:
        email = st.text_input("Correo Electrónico", placeholder="usuario@empresa.com")
        password = st.text_input("Contraseña", type="password", placeholder="password")

        if st.button("Ingresar", use_container_width=True):
            try:
                # 1. Autenticar al usuario
                response = supabase.auth.sign_in_with_password({"email": email, "password": password})
                user_id = response.user.id
                
                # Capturamos los tokens
                access_token = response.session.access_token
                refresh_token = response.session.refresh_token

                # --- ¡INICIO DE LA CORRECCIÓN CRUCIAL! ---
                # ¡Autenticamos al cliente de Supabase AHORA!
                # Esto permite que la siguiente llamada a la tabla 'users' funcione.
                supabase.auth.set_session(access_token, refresh_token)
                # --- ¡FIN DE LA CORRECCIÓN CRUCIAL! ---
                
                # 2. Revisar la sesión activa en la DB (Esta llamada ahora SÍ funcionará)
                user_profile_check = supabase.table("users").select("active_session_id").eq("id", user_id).single().execute()

                if user_profile_check.data and user_profile_check.data.get('active_session_id'):
                    # --- ¡SESIÓN ACTIVA DETECTADA! ---
                    # Guardamos los datos Y LOS TOKENS y recargamos.
                    st.session_state.pending_login_info = {
                        'user_id': user_id,
                        'access_token': access_token,
                        'refresh_token': refresh_token
                    }
                    st.rerun()
                else:
                    # --- NO HAY SESIÓN ACTIVA (LOGIN NORMAL) ---
                    # Generamos un ID de sesión único
                    new_session_id = str(uuid.uuid4())
                    
                    # Obtenemos el perfil completo (Esta llamada también funcionará)
                    user_profile = supabase.table("users").select("*, rol, clients(client_name, plan)").eq("id", user_id).single().execute()
                    
                    if user_profile.data and user_profile.data.get('clients'):
                        # Guardamos el nuevo ID en la DB
                        supabase.table("users").update({"active_session_id": new_session_id}).eq("id", user_id).execute()
                        
                        # Guardamos los tokens en la sesión
                        st.session_state.access_token = access_token
                        st.session_state.refresh_token = refresh_token
                        
                        # Guardamos todo en el estado de Streamlit
                        client_info = user_profile.data['clients']
                        st.session_state.logged_in = True
                        st.session_state.user = user_profile.data['email']
                        st.session_state.user_id = user_id
                        st.session_state.session_id = new_session_id
                        st.session_state.cliente = client_info['client_name'].lower()
                        st.session_state.plan = client_info.get('plan', 'Explorer')
                        st.session_state.plan_features = PLAN_FEATURES.get(st.session_state.plan, PLAN_FEATURES['Explorer'])
                        st.session_state.is_admin = (user_profile.data.get('rol', '') == 'admin')
                        st.session_state.login_timestamp = time.time() # Guardamos la hora
                        
                        st.rerun()
                    else:
                        st.error("Perfil de usuario no encontrado. Contacta al administrador.")
                        
            except Exception as e:
                st.error(f"Credenciales incorrectas o cuenta no confirmada. Error: {e}")

        # Botones de registro y reseteo
        if st.button("¿No tienes cuenta? Regístrate", type="secondary", use_container_width=True):
            st.session_state.page = "signup"
            st.rerun()

        if st.button("¿Olvidaste tu contraseña?", type="secondary", use_container_width=True):
            st.session_state.page = "reset_password"
            st.rerun()

def show_reset_password_page():
    # ... (Esta función no cambia) ...
    st.header("Restablecer Contraseña")
    st.write("Ingresa tu correo electrónico y te enviaremos un enlace para restablecer tu contraseña.")
    email = st.text_input("Tu Correo Electrónico")

    if st.button("Enviar enlace de recuperación", use_container_width=True):
        if not email:
            st.warning("Por favor, ingresa tu correo electrónico.")
            return

        try:
            supabase.auth.reset_password_for_email(email)
            st.success("¡Correo enviado! Revisa tu bandeja de entrada.")
            st.info("Sigue las instrucciones del correo para crear una nueva contraseña. Una vez creada, podrás iniciar sesión.")
        except Exception as e:
            st.error(f"Error al enviar el correo: {e}")

    if st.button("Volver a Iniciar Sesión", type="secondary", use_container_width=True):
         st.session_state.page = "login"
         st.rerun()