import streamlit as st
import uuid
import time 

# Importaciones seguras para evitar bucles si falla la conexión
try:
    from services.supabase_db import supabase
    from config import PLAN_FEATURES
    from services.storage import load_database 
except ImportError:
    st.error("Error crítico: No se pudieron cargar los servicios de base de datos.")
    supabase = None
    PLAN_FEATURES = {}

# ==============================
# Autenticación con Supabase Auth
# ==============================

def show_login_page():
    st.header("Iniciar Sesión")
    
    # --- LÓGICA DE SESIÓN DUPLICADA ---
    if 'pending_login_info' in st.session_state:
        st.warning("**Este usuario ya tiene una sesión activa en otro dispositivo.**")
        
        # Botón 1: Acción principal
        if st.button("Cerrar la otra sesión e iniciar aquí", key="btn_force_login", width="stretch", type="primary"):
            try:
                pending = st.session_state.pending_login_info
                supabase.auth.set_session(pending['access_token'], pending['refresh_token'])
                new_sid = str(uuid.uuid4())
                
                # Actualización segura de la sesión
                try:
                    supabase.table("users").update({"active_session_id": new_sid}).eq("id", pending['user_id']).execute()
                except Exception: pass # Si falla (ej. tabla vieja), seguimos igual
                
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
            except Exception as e: 
                st.error(f"Error recuperando sesión: {e}")
            
        # Botón 2: Cancelar
        if st.button("Cancelar", key="btn_cancel_login", width="stretch"):
            st.session_state.pop('pending_login_info')
            st.rerun()
    
    # --- LOGIN FORM ---
    else:
        email = st.text_input("Correo Electrónico", placeholder="usuario@empresa.com")
        password = st.text_input("Contraseña", type="password", placeholder="••••••")
        st.write("")
        
        if st.button("Ingresar", width="stretch", type="primary"):
            if not email or not password:
                st.warning("Por favor ingresa usuario y contraseña."); return

            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                uid = res.user.id
                
                # Verificar sesión activa (Protegido contra fallos de DB)
                try:
                    check = supabase.table("users").select("active_session_id").eq("id", uid).single().execute()
                    session_active = check.data and check.data.get('active_session_id')
                except:
                    session_active = False # Si falla la consulta, asumimos que no hay sesión
                
                if session_active:
                    st.session_state.pending_login_info = {
                        'user_id': uid, 
                        'access_token': res.session.access_token, 
                        'refresh_token': res.session.refresh_token
                    }
                    st.rerun()
                else:
                    # Login exitoso
                    nsid = str(uuid.uuid4())
                    try: supabase.table("users").update({"active_session_id": nsid}).eq("id", uid).execute()
                    except: pass
                    
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
                        
                        with st.spinner("Cargando tu espacio de trabajo..."):
                            try:
                                st.session_state.db_full = load_database(st.session_state.cliente)
                            except Exception as db_err:
                                st.error(f"Error cargando datos: {db_err}")
                                time.sleep(2)
                        st.rerun()
                    else:
                        st.error("Tu usuario no tiene una empresa asignada. Contacta al soporte.")
                        supabase.auth.sign_out()
            except Exception as e:
                msg = str(e).lower()
                if "invalid login" in msg: st.error("Credenciales incorrectas.")
                elif "email not confirmed" in msg: st.warning("Tu correo no ha sido confirmado.")
                else: st.error(f"Error de conexión: {e}")

        if st.button("¿Olvidaste tu contraseña?", type="secondary", width="stretch"):
            st.session_state.page = "reset_password"; st.rerun()

def show_reset_password_page():
    st.header("Recuperar Acceso")
    st.write("Ingresa tu correo para recibir un enlace de recuperación.")
    email = st.text_input("Tu Correo Electrónico")
    if st.button("Enviar enlace", width="stretch", type="primary"):
        try:
            # Usamos la URL genérica para asegurar compatibilidad
            supabase.auth.reset_password_for_email(email, options={"redirect_to": "https://atelier-ai.streamlit.app"})
            st.success("✅ Correo enviado. Revisa tu bandeja de entrada.")
        except Exception as e: st.error(f"Error al enviar: {e}")
    
    if st.button("Volver al Login", type="secondary", width="stretch"):
         st.session_state.page = "login"; st.rerun()

# ========================================================
# FLUJO DE ACTIVACIÓN / RECUPERACIÓN (PASO A PASO)
# ========================================================

def show_activation_flow(otp_token, auth_type):
    """
    Maneja el flujo completo de activación/recuperación en 2 pasos.
    """
    if auth_type == "invite":
        title = "¡Bienvenido a Atelier!"
        subtitle = "Paso 1: Confirma tu identidad"
    else:
        title = "Restablecer Contraseña"
        subtitle = "Paso 1: Verifica tu correo"

    # PASO 1: VERIFICAR EMAIL
    if not st.session_state.get("flow_email_verified"):
        st.header(title)
        st.info(subtitle)
        st.write("Por seguridad, ingresa tu correo electrónico para validar el enlace.")
        
        email_input = st.text_input("Correo Electrónico")
        
        if st.button("Validar Identidad", width="stretch", type="primary"):
            if not email_input:
                st.warning("Debes ingresar tu correo."); return
            
            try:
                # Intentamos verificar el OTP
                type_api = "invite" if auth_type == "invite" else "recovery"
                
                try:
                    res = supabase.auth.verify_otp({
                        "email": email_input,
                        "token": otp_token,
                        "type": type_api
                    })
                except Exception:
                    # Retry para invitaciones fallidas como signup
                    if auth_type == "invite":
                        res = supabase.auth.verify_otp({
                            "email": email_input, 
                            "token": otp_token, 
                            "type": "signup"
                        })
                    else: raise

                if res.session:
                    st.session_state.temp_access_token = res.session.access_token
                    st.session_state.temp_refresh_token = res.session.refresh_token
                    st.session_state.flow_email_verified = True 
                    st.rerun()
                else:
                    st.error("El código es inválido o ha expirado.")
            
            except Exception as e:
                st.error(f"No pudimos verificar tu identidad. El enlace puede haber expirado. Error: {e}")

    # PASO 2: CREAR CONTRASEÑA
    else:
        if auth_type == "invite":
            st.header("Activar Cuenta")
            st.info("Paso 2: Crea tu contraseña de acceso personal.")
        else:
            st.header("Nueva Contraseña")
            st.info("Paso 2: Define tu nueva contraseña.")

        try:
            # Restauramos la sesión temporal para poder cambiar el password
            supabase.auth.set_session(st.session_state.temp_access_token, st.session_state.temp_refresh_token)
        except:
            st.error("La sesión ha expirado. Por favor reinicia el proceso."); return

        p1 = st.text_input("Nueva Contraseña", type="password")
        p2 = st.text_input("Confirmar Contraseña", type="password")

        if st.button("Guardar y Finalizar", width="stretch", type="primary"):
            if p1 != p2: st.error("Las contraseñas no coinciden."); return
            if len(p1) < 6: st.error("La contraseña debe tener al menos 6 caracteres."); return

            try:
                supabase.auth.update_user(attributes={"password": p1})
                
                # Limpieza final
                supabase.auth.sign_out()
                st.session_state.clear()
                
                if auth_type == "invite":
                    st.success("✅ ¡Cuenta activada correctamente! Ya puedes iniciar sesión.")
                else:
                    st.success("✅ ¡Contraseña actualizada! Ya puedes iniciar sesión.")
                
                time.sleep(2)
                
                # Limpieza de URL segura (compatible con versiones nuevas de Streamlit)
                try:
                    st.query_params.clear()
                except:
                    st.experimental_set_query_params() # Fallback para versiones viejas
                
                st.session_state.page = "login"
                st.rerun()
                
            except Exception as e:
                st.error(f"Error al guardar la contraseña: {e}")
