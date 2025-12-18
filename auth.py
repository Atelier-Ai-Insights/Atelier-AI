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
    
    # --- LÓGICA DE SESIÓN DUPLICADA (MODIFICADO: BOTONES VERTICALES) ---
    if 'pending_login_info' in st.session_state:
        # Mensaje de advertencia
        st.warning("**Este usuario ya tiene una sesión activa en otro dispositivo.**")
        
        # Botón 1: Acción principal (Ocupa todo el ancho)
        if st.button("Cerrar la otra sesión e iniciar aquí", key="btn_force_login", use_container_width=True, type="primary"):
            try:
                pending = st.session_state.pending_login_info
                supabase.auth.set_session(pending['access_token'], pending['refresh_token'])
                new_sid = str(uuid.uuid4())
                supabase.table("users").update({"active_session_id": new_sid}).eq("id", pending['user_id']).execute()
                
                # Cargar datos
                user_data = supabase.table("users").select("*, clients(client_name, plan)").eq("id", pending['user_id']).single().execute()
                st.session_state.logged_in = True
                st.session_state.user = user_data.data['email']
                st.session_state.user_id = pending['user_id']
                st.session_state.session_id = new_sid
                
                client_info = user_data.data.get('clients', {})
                st.session_state.cliente = client_info.get('client_name', 'generico').lower() if client_info else 'generico'
                st.session_state.plan = client_info.get('plan', 'Explorer') if client_info else 'Explorer'
                st.session_state.plan_features = PLAN_FEATURES.get(st.session_state.plan, PLAN_FEATURES['Explorer'])
                st.session_state.is_admin = (user_data.data.get('rol', '') == 'admin')
                
                st.session_state.pop('pending_login_info')
                st.rerun()
            except Exception as e: st.error(f"Error: {e}")
            
        # Botón 2: Cancelar (Debajo del anterior, ocupando todo el ancho)
        if st.button("Cancelar", key="btn_cancel_login", use_container_width=True):
            st.session_state.pop('pending_login_info')
            st.rerun()
    
    # --- LOGIN FORM ---
    else:
        email = st.text_input("Correo Electrónico", placeholder="usuario@empresa.com")
        password = st.text_input("Contraseña", type="password", placeholder="password")
        st.write("")
        
        if st.button("Ingresar", use_container_width=True, type="primary"):
            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                uid = res.user.id
                
                # Verificar sesión activa
                check = supabase.table("users").select("active_session_id").eq("id", uid).single().execute()
                if check.data and check.data.get('active_session_id'):
                    st.session_state.pending_login_info = {'user_id': uid, 'access_token': res.session.access_token, 'refresh_token': res.session.refresh_token}
                    st.rerun()
                else:
                    # Login exitoso
                    nsid = str(uuid.uuid4())
                    supabase.table("users").update({"active_session_id": nsid}).eq("id", uid).execute()
                    prof = supabase.table("users").select("*, clients(client_name, plan)").eq("id", uid).single().execute()
                    
                    if prof.data and prof.data.get('clients'):
                        st.session_state.access_token = res.session.access_token
                        st.session_state.refresh_token = res.session.refresh_token
                        st.session_state.logged_in = True
                        st.session_state.user = prof.data['email']
                        st.session_state.user_id = uid
                        st.session_state.session_id = nsid
                        
                        c_info = prof.data['clients']
                        st.session_state.cliente = c_info['client_name'].lower()
                        st.session_state.plan = c_info.get('plan', 'Explorer')
                        st.session_state.plan_features = PLAN_FEATURES.get(st.session_state.plan, PLAN_FEATURES['Explorer'])
                        st.session_state.is_admin = (prof.data.get('rol') == 'admin')
                        
                        with st.spinner("Cargando..."):
                            st.session_state.db_full = load_database(st.session_state.cliente)
                        st.rerun()
                    else:
                        st.error("Usuario sin empresa asignada.")
                        supabase.auth.sign_out()
            except Exception as e:
                msg = str(e).lower()
                if "invalid login" in msg: st.error("Credenciales incorrectas.")
                elif "email not confirmed" in msg: st.warning("Email no confirmado.")
                else: st.error(f"Error: {e}")

        if st.button("¿Olvidaste tu contraseña?", type="secondary", use_container_width=True):
            st.session_state.page = "reset_password"; st.rerun()

def show_reset_password_page():
    st.header("Recuperar Acceso")
    st.write("Ingresa tu correo para recibir un enlace de recuperación.")
    email = st.text_input("Tu Correo Electrónico")
    if st.button("Enviar enlace", use_container_width=True, type="primary"):
        try:
            # Usamos la URL correcta para que llegue el token como parámetro
            supabase.auth.reset_password_for_email(email, options={"redirect_to": "https://atelier-ai.streamlit.app"})
            st.success("Correo enviado. Revisa tu bandeja de entrada.")
        except Exception as e: st.error(f"Error: {e}")
    if st.button("Volver", type="secondary", use_container_width=True):
         st.session_state.page = "login"; st.rerun()

# ========================================================
# NUEVO FLUJO: VALIDACIÓN PASO A PASO (Link -> Email -> Pass)
# ========================================================

def show_activation_flow(otp_token, auth_type):
    """
    Maneja el flujo completo de activación/recuperación en 2 pasos.
    """
    # 1. Determinar título según el tipo
    if auth_type == "invite":
        title = "¡Bienvenido a Atelier!"
        subtitle = "Paso 1: Confirma tu identidad"
    else:
        title = "Restablecer Contraseña"
        subtitle = "Paso 1: Verifica tu correo"

    # Si aún no hemos validado el correo (Paso 1)
    if not st.session_state.get("flow_email_verified"):
        st.header(title)
        st.info(subtitle)
        st.write("Por seguridad, ingresa tu correo electrónico para validar el enlace.")
        
        email_input = st.text_input("Correo Electrónico")
        
        if st.button("Validar Identidad", use_container_width=True, type="primary"):
            if not email_input:
                st.warning("Ingresa el correo."); return
            
            try:
                # Intentamos verificar el OTP con la API
                type_api = "invite" if auth_type == "invite" else "recovery"
                
                res = supabase.auth.verify_otp({
                    "email": email_input,
                    "token": otp_token,
                    "type": type_api
                })
                
                if res.session:
                    st.session_state.temp_access_token = res.session.access_token
                    st.session_state.temp_refresh_token = res.session.refresh_token
                    st.session_state.flow_email_verified = True 
                    st.rerun()
                else:
                    st.error("Código inválido o expirado.")
            
            except Exception as e:
                if auth_type == "invite":
                    try:
                        res = supabase.auth.verify_otp({"email": email_input, "token": otp_token, "type": "signup"})
                        if res.session:
                            st.session_state.temp_access_token = res.session.access_token
                            st.session_state.flow_email_verified = True
                            st.rerun()
                            return
                    except: pass
                st.error(f"Error de verificación: {e}")

    # Paso 2: Establecer Contraseña (Si ya validamos correo)
    else:
        if auth_type == "invite":
            st.header("Activar Cuenta")
            st.info("Paso 2: Crea tu contraseña de acceso personal.")
        else:
            st.header("Nueva Contraseña")
            st.info("Paso 2: Define tu nueva contraseña.")

        try:
            supabase.auth.set_session(st.session_state.temp_access_token, st.session_state.temp_refresh_token)
        except:
            st.error("Sesión expirada. Vuelve a empezar."); return

        p1 = st.text_input("Nueva Contraseña", type="password")
        p2 = st.text_input("Confirmar Contraseña", type="password")

        if st.button("Guardar y Finalizar", use_container_width=True, type="primary"):
            if p1 != p2: st.error("No coinciden."); return
            if len(p1) < 6: st.error("Mínimo 6 caracteres."); return

            try:
                supabase.auth.update_user(attributes={"password": p1})
                
                # Limpieza final
                supabase.auth.sign_out()
                st.session_state.clear()
                
                if auth_type == "invite":
                    st.success("¡Cuenta activada! Inicia sesión.")
                else:
                    st.success("¡Contraseña actualizada! Inicia sesión.")
                
                time.sleep(2)
                
                # --- CORRECCIÓN CLAVE AQUÍ ---
                # Limpiamos la URL para que al recargar no vuelva a entrar al flujo
                st.query_params.clear() 
                
                st.session_state.page = "login"
                st.rerun()
                
            except Exception as e:
                st.error(f"Error al guardar: {e}")
