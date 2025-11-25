import streamlit as st
import time 
from datetime import datetime, timezone

# ==============================
# 1. IMPORTAR MÓDULOS
# ==============================

from styles import apply_styles, apply_login_styles 
from config import PLAN_FEATURES, banner_file
from services.storage import load_database 
from services.supabase_db import supabase
from auth import (
    show_login_page, 
    show_reset_password_page, 
    show_activation_flow, 
    show_otp_verification_page 
)
from admin.dashboard import show_admin_dashboard

# --- MODOS DE USO ---
from modes.report_mode import report_mode
from modes.chat_mode import grounded_chat_mode
from modes.ideation_mode import ideacion_mode
from modes.concept_mode import concept_generation_mode
from modes.idea_eval_mode import idea_evaluator_mode
from modes.image_eval_mode import image_evaluation_mode
from modes.video_eval_mode import video_evaluation_mode
from modes.text_analysis_mode import text_analysis_mode
from modes.onepager_mode import one_pager_ppt_mode
from modes.data_analysis_mode import data_analysis_mode
from modes.etnochat_mode import etnochat_mode
from modes.trend_analysis_mode import trend_analysis_mode 
from modes.synthetic_mode import synthetic_users_mode 

from utils import extract_brand, validate_session_integrity 
import constants as c

def set_mode_and_reset(new_mode):
    if 'current_mode' not in st.session_state or st.session_state.current_mode != new_mode:
        st.session_state.mode_state = {} 
        st.session_state.current_mode = new_mode

# =====================================================
# FUNCIÓN PARA EL MODO USUARIO 
# =====================================================
def run_user_mode(db_full, user_features, footer_html):
    st.sidebar.image("LogoDataStudio.png")
    st.sidebar.write(f"Usuario: {st.session_state.user}")
    if st.session_state.get("is_admin", False): st.sidebar.caption("Rol: Administrador 👑")
    st.sidebar.divider()
    st.sidebar.header("Seleccione el modo de uso")
    modo = st.session_state.current_mode
    
    # Definición de Categorías (Igual que antes)
    all_categories = {
        "Análisis": { c.MODE_CHAT: True, c.MODE_TEXT_ANALYSIS: user_features.get("transcript_file_limit", 0) > 0, c.MODE_DATA_ANALYSIS: True, c.MODE_ETNOCHAT: user_features.get("has_etnochat_analysis"), c.MODE_TREND_ANALYSIS: True },
        "Evaluación": { c.MODE_IDEA_EVAL: user_features.get("has_idea_evaluation"), c.MODE_IMAGE_EVAL: user_features.get("has_image_evaluation"), c.MODE_VIDEO_EVAL: user_features.get("has_video_evaluation") },
        "Reportes": { c.MODE_REPORT: user_features.get("has_report_generation"), c.MODE_ONEPAGER: user_features.get("ppt_downloads_per_month", 0) > 0 },
        "Creatividad": { c.MODE_IDEATION: user_features.get("has_creative_conversation"), c.MODE_CONCEPT: user_features.get("has_concept_generation"), c.MODE_SYNTHETIC: True }
    }
    
    # Renderizado de Sidebar (Igual que antes - resumido para no ocupar espacio, mantén tu lógica visual)
    for category, modes in all_categories.items():
        if any(modes.values()):
            with st.sidebar.expander(category, expanded=(modo in modes)):
                for m_name, enabled in modes.items():
                    if enabled: st.button(m_name, on_click=set_mode_and_reset, args=(m_name,), use_container_width=True, type="primary" if modo == m_name else "secondary")

    # Filtros y Logout
    st.sidebar.divider()
    if st.sidebar.button("Cerrar Sesión", key="logout_main", use_container_width=True):
        try:
            if 'user_id' in st.session_state:
                supabase.table("users").update({"active_session_id": None}).eq("id", st.session_state.user_id).execute()
        except: pass
        supabase.auth.sign_out(); st.session_state.clear(); st.rerun()
    st.sidebar.markdown(footer_html, unsafe_allow_html=True)
    
    # Enrutador de Modos
    db_filtered = db_full # (Aquí iría tu lógica de filtros, simplificada para este ejemplo)
    selected_files = [d.get("nombre_archivo") for d in db_filtered] # Mock
    
    if modo == c.MODE_REPORT: report_mode(db_filtered, selected_files)
    elif modo == c.MODE_IDEATION: ideacion_mode(db_filtered, selected_files)
    elif modo == c.MODE_CONCEPT: concept_generation_mode(db_filtered, selected_files)
    elif modo == c.MODE_CHAT: grounded_chat_mode(db_filtered, selected_files)
    elif modo == c.MODE_IDEA_EVAL: idea_evaluator_mode(db_filtered, selected_files)
    elif modo == c.MODE_IMAGE_EVAL: image_evaluation_mode(db_filtered, selected_files)
    elif modo == c.MODE_VIDEO_EVAL: video_evaluation_mode(db_filtered, selected_files)
    elif modo == c.MODE_TEXT_ANALYSIS: text_analysis_mode()
    elif modo == c.MODE_ONEPAGER: one_pager_ppt_mode(db_filtered, selected_files)
    elif modo == c.MODE_DATA_ANALYSIS: data_analysis_mode(db_filtered, selected_files)
    elif modo == c.MODE_ETNOCHAT: etnochat_mode()
    elif modo == c.MODE_TREND_ANALYSIS: trend_analysis_mode(db_filtered, selected_files)
    elif modo == c.MODE_SYNTHETIC: synthetic_users_mode(db_filtered, selected_files)

# =====================================================
# FUNCIÓN PRINCIPAL DE LA APLICACIÓN
# =====================================================
def main():
    st.set_page_config(page_title="Atelier Data Studio", page_icon="Logo_Casa.png")
    apply_styles()

    if 'page' not in st.session_state: st.session_state.page = "login"
    if "mode_state" not in st.session_state: st.session_state.mode_state = {}
    if 'current_mode' not in st.session_state: st.session_state.current_mode = c.MODE_CHAT
    
    params = st.query_params 
    footer_text = "Atelier Consultoría y Estrategia S.A.S - Todos los Derechos Reservados 2025"
    footer_html = f"<div style='text-align: center; color: gray; font-size: 12px;'>{footer_text}</div>"

    # ------------------------------------------------------------------
    # 1. PRIORIDAD MÁXIMA: DETECCIÓN DE INVITACIÓN / RECUPERACIÓN
    # ------------------------------------------------------------------
    
    # A. ¿Ya estamos en el paso 2 del flujo? (Ya validó email, falta password)
    if st.session_state.get('flow_email_verified'):
        apply_login_styles()
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            st.image("LogoDataStudio.png")
            ctx = st.session_state.get('temp_auth_type', 'recovery')
            show_activation_flow(None, ctx) 
        st.divider(); st.markdown(footer_html, unsafe_allow_html=True); st.stop()

    # B. ¿Viene llegando del correo? (Hay params en URL)
    auth_type = params.get("type")
    access_token = params.get("access_token")
    
    if auth_type in ["recovery", "invite"] and access_token:
        if isinstance(access_token, list): access_token = access_token[0]
        
        apply_login_styles()
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            st.image("LogoDataStudio.png")
            # Mostramos la pantalla de "Confirma tu email para validar"
            show_activation_flow(access_token, auth_type)
        st.divider(); st.markdown(footer_html, unsafe_allow_html=True); st.stop()

    # ------------------------------------------------------------------
    # 2. RUTA DE SESIÓN ACTIVA (APP)
    # ------------------------------------------------------------------
    if st.session_state.get("logged_in"):
        validate_session_integrity()
        
        # Restaurar sesión si es necesario
        if st.session_state.get("access_token"):
            try: supabase.auth.set_session(st.session_state.access_token, st.session_state.refresh_token)
            except: supabase.auth.sign_out(); st.session_state.clear(); st.rerun()
        
        # Cargar DB
        if not hasattr(st.session_state, 'db_full'):
            try: 
                st.session_state.db_full = load_database(st.session_state.cliente)
            except: st.session_state.clear(); st.rerun()
        
        # Renderizar App
        if st.session_state.get("is_admin", False):
            t1, t2 = st.tabs(["Modo Usuario", "Modo Administrador"])
            with t1: run_user_mode(st.session_state.db_full, st.session_state.plan_features, footer_html)
            with t2: show_admin_dashboard(st.session_state.db_full)
        else:
            run_user_mode(st.session_state.db_full, st.session_state.plan_features, footer_html)
        st.stop() 

    # ------------------------------------------------------------------
    # 3. PANTALLA DE LOGIN (DEFAULT)
    # ------------------------------------------------------------------
    apply_login_styles()
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.image("LogoDataStudio.png")
        if st.session_state.page == "reset_password": 
            show_reset_password_page()
        else: 
            show_login_page() # Default
            
    st.divider()
    st.markdown(footer_html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
