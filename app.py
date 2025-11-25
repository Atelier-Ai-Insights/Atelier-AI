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
    show_activation_flow # <-- Única función necesaria para el flujo
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
    
    all_categories = {
        "Análisis": {
            c.MODE_CHAT: True,
            c.MODE_TEXT_ANALYSIS: user_features.get("transcript_file_limit", 0) > 0,
            c.MODE_DATA_ANALYSIS: True,
            c.MODE_ETNOCHAT: user_features.get("has_etnochat_analysis"),
            c.MODE_TREND_ANALYSIS: True, 
        },
        "Evaluación": {
            c.MODE_IDEA_EVAL: user_features.get("has_idea_evaluation"),
            c.MODE_IMAGE_EVAL: user_features.get("has_image_evaluation"),
            c.MODE_VIDEO_EVAL: user_features.get("has_video_evaluation")
        },
        "Reportes": {
            c.MODE_REPORT: user_features.get("has_report_generation"),
            c.MODE_ONEPAGER: user_features.get("ppt_downloads_per_month", 0) > 0
        },
        "Creatividad": {
            c.MODE_IDEATION: user_features.get("has_creative_conversation"),
            c.MODE_CONCEPT: user_features.get("has_concept_generation"),
            c.MODE_SYNTHETIC: True, 
        }
    }
    
    default_expanded = ""
    for category, modes in all_categories.items():
        if modo in modes:
            default_expanded = category
            break
            
    if any(all_categories["Análisis"].values()):
        with st.sidebar.expander("Análisis", expanded=(default_expanded == "Análisis")):
            if all_categories["Análisis"][c.MODE_CHAT]: st.button(c.MODE_CHAT, on_click=set_mode_and_reset, args=(c.MODE_CHAT,), use_container_width=True, type="primary" if modo == c.MODE_CHAT else "secondary")
            if all_categories["Análisis"][c.MODE_TEXT_ANALYSIS]: st.button(c.MODE_TEXT_ANALYSIS, on_click=set_mode_and_reset, args=(c.MODE_TEXT_ANALYSIS,), use_container_width=True, type="primary" if modo == c.MODE_TEXT_ANALYSIS else "secondary")
            if all_categories["Análisis"][c.MODE_DATA_ANALYSIS]: st.button(c.MODE_DATA_ANALYSIS, on_click=set_mode_and_reset, args=(c.MODE_DATA_ANALYSIS,), use_container_width=True, type="primary" if modo == c.MODE_DATA_ANALYSIS else "secondary")
            if all_categories["Análisis"][c.MODE_ETNOCHAT]: st.button(c.MODE_ETNOCHAT, on_click=set_mode_and_reset, args=(c.MODE_ETNOCHAT,), use_container_width=True, type="primary" if modo == c.MODE_ETNOCHAT else "secondary")
            if all_categories["Análisis"][c.MODE_TREND_ANALYSIS]: st.button(c.MODE_TREND_ANALYSIS, on_click=set_mode_and_reset, args=(c.MODE_TREND_ANALYSIS,), use_container_width=True, type="primary" if modo == c.MODE_TREND_ANALYSIS else "secondary")

    if any(all_categories["Evaluación"].values()):
        with st.sidebar.expander("Evaluación", expanded=(default_expanded == "Evaluación")):
            if all_categories["Evaluación"][c.MODE_IDEA_EVAL]: st.button(c.MODE_IDEA_EVAL, on_click=set_mode_and_reset, args=(c.MODE_IDEA_EVAL,), use_container_width=True, type="primary" if modo == c.MODE_IDEA_EVAL else "secondary")
            if all_categories["Evaluación"][c.MODE_IMAGE_EVAL]: st.button(c.MODE_IMAGE_EVAL, on_click=set_mode_and_reset, args=(c.MODE_IMAGE_EVAL,), use_container_width=True, type="primary" if modo == c.MODE_IMAGE_EVAL else "secondary")
            if all_categories["Evaluación"][c.MODE_VIDEO_EVAL]: st.button(c.MODE_VIDEO_EVAL, on_click=set_mode_and_reset, args=(c.MODE_VIDEO_EVAL,), use_container_width=True, type="primary" if modo == c.MODE_VIDEO_EVAL else "secondary")
    
    if any(all_categories["Reportes"].values()):
        with st.sidebar.expander("Reportes", expanded=(default_expanded == "Reportes")):
            if all_categories["Reportes"][c.MODE_REPORT]: st.button(c.MODE_REPORT, on_click=set_mode_and_reset, args=(c.MODE_REPORT,), use_container_width=True, type="primary" if modo == c.MODE_REPORT else "secondary")
            if all_categories["Reportes"][c.MODE_ONEPAGER]: st.button(c.MODE_ONEPAGER, on_click=set_mode_and_reset, args=(c.MODE_ONEPAGER,), use_container_width=True, type="primary" if modo == c.MODE_ONEPAGER else "secondary")
    
    if any(all_categories["Creatividad"].values()):
        with st.sidebar.expander("Creatividad", expanded=(default_expanded == "Creatividad")):
            if all_categories["Creatividad"][c.MODE_IDEATION]: st.button(c.MODE_IDEATION, on_click=set_mode_and_reset, args=(c.MODE_IDEATION,), use_container_width=True, type="primary" if modo == c.MODE_IDEATION else "secondary")
            if all_categories["Creatividad"][c.MODE_CONCEPT]: st.button(c.MODE_CONCEPT, on_click=set_mode_and_reset, args=(c.MODE_CONCEPT,), use_container_width=True, type="primary" if modo == c.MODE_CONCEPT else "secondary")
            if all_categories["Creatividad"][c.MODE_SYNTHETIC]: st.button(c.MODE_SYNTHETIC, on_click=set_mode_and_reset, args=(c.MODE_SYNTHETIC,), use_container_width=True, type="primary" if modo == c.MODE_SYNTHETIC else "secondary")

    st.sidebar.header("Filtros de Búsqueda")
    run_filters = modo not in [c.MODE_TEXT_ANALYSIS, c.MODE_DATA_ANALYSIS, c.MODE_ETNOCHAT] 
    
    if st.session_state.get("cliente") == "atelier demo":
        db_full = [doc for doc in db_full if doc.get("cliente") and "atelier" in str(doc.get("cliente")).lower()]
    
    db_filtered = db_full[:]
    marcas_options = sorted({doc.get("filtro", "") for doc in db_full if doc.get("filtro")})
    selected_marcas = st.sidebar.multiselect("Marca(s):", marcas_options, key="filter_marcas", disabled=not run_filters)
    if run_filters and selected_marcas:
        db_filtered = [d for d in db_filtered if d.get("filtro") in selected_marcas]
    years_options = sorted({doc.get("marca", "") for doc in db_full if doc.get("marca")})
    selected_years = st.sidebar.multiselect("Año(s):", years_options, key="filter_years", disabled=not run_filters)
    if run_filters and selected_years:
        db_filtered = [d for d in db_filtered if d.get("marca") in selected_years]
    brands_options = sorted({extract_brand(d.get("nombre_archivo", "")) for d in db_filtered if extract_brand(d.get("nombre_archivo", ""))})
    
    selected_brands = st.sidebar.multiselect("Proyecto(s):", brands_options, key="filter_projects", disabled=not run_filters)
    
    if run_filters and selected_brands:
        db_filtered = [d for d in db_filtered if extract_brand(d.get("nombre_archivo", "")) in selected_brands]

    if st.sidebar.button("Cerrar Sesión", key="logout_main", use_container_width=True):
        try:
            if 'user_id' in st.session_state:
                supabase.table("users").update({"active_session_id": None}).eq("id", st.session_state.user_id).execute()
        except: pass
        supabase.auth.sign_out(); st.session_state.clear(); st.rerun()

    st.sidebar.divider()
    st.sidebar.markdown(footer_html, unsafe_allow_html=True)
    
    selected_files = [d.get("nombre_archivo") for d in db_filtered]
    
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
    # 1. RUTA DE ACTIVACIÓN (INVITACIÓN / RECUPERACIÓN)
    # ------------------------------------------------------------------
    
    # A. Si ya validamos el email, mostramos pantalla de password
    if st.session_state.get('flow_email_verified'):
        apply_login_styles()
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            st.image("LogoDataStudio.png")
            ctx = st.session_state.get('temp_auth_type', 'recovery')
            show_activation_flow(None, ctx) 
        st.divider(); st.markdown(footer_html, unsafe_allow_html=True); st.stop()

    # B. Si llega por URL con Token (Paso 1)
    auth_type = params.get("type")
    access_token = params.get("access_token")
    
    if auth_type in ["recovery", "invite"] and access_token:
        if isinstance(access_token, list): access_token = access_token[0]
        
        apply_login_styles()
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            st.image("LogoDataStudio.png")
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
            try: st.session_state.db_full = load_database(st.session_state.cliente)
            except: st.session_state.clear(); st.rerun()
        
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
            show_login_page() 
            
    st.divider()
    st.markdown(footer_html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
