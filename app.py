import streamlit as st
import time # Importar time

# ==============================
# 1. IMPORTAR MÓDULOS
# ==============================

from styles import apply_styles
from config import PLAN_FEATURES, banner_file
from services.storage import load_database
from services.supabase_db import supabase
from auth import show_login_page, show_signup_page, show_reset_password_page
from admin.dashboard import show_admin_dashboard
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
from utils import (
    extract_brand, reset_chat_workflow, reset_report_workflow
)
import constants as c

def set_mode_and_reset(new_mode):
    if 'current_mode' not in st.session_state or st.session_state.current_mode != new_mode:
        reset_chat_workflow()
        st.session_state.pop("generated_concept", None)
        st.session_state.pop("evaluation_result", None)
        st.session_state.pop("report", None)
        st.session_state.pop("last_question", None)
        st.session_state.pop("image_evaluation_result", None)
        st.session_state.pop("video_evaluation_result", None)
        st.session_state.pop("generated_ppt_bytes", None)
        
        st.session_state.pop("data_analysis_df", None)
        st.session_state.pop("data_analysis_chat_history", None)
        st.session_state.pop("da_selected_project_id", None)
        st.session_state.pop("da_selected_project_name", None)
        st.session_state.pop("da_current_sub_mode", None)
        
        st.session_state.pop("text_analysis_files_dict", None)
        st.session_state.pop("text_analysis_combined_context", None)
        st.session_state.pop("text_analysis_file_names", None)
        
        st.session_state.current_mode = new_mode

# =====================================================
# FUNCIÓN PARA EL MODO USUARIO (REFACTORIZADA CON EXPANDERS)
# =====================================================
def run_user_mode(db_full, user_features, footer_html):

    # --- ¡BLOQUE DE HEARTBEAT CON "TEMPORIZADOR SUAVE"! ---
    
    GRACE_PERIOD_SECONDS = 5 # Período de gracia post-login
    HEARTBEAT_INTERVAL_SECONDS = 60 # Chequear solo cada 60 segundos
    current_time = time.time()
    
    login_time = st.session_state.get("login_timestamp", 0)
    if (current_time - login_time) > GRACE_PERIOD_SECONDS:
        
        last_check = st.session_state.get("last_heartbeat_check", 0)
        
        if (current_time - last_check) > HEARTBEAT_INTERVAL_SECONDS:
            print("--- Ejecutando Heartbeat de Sesión ---")
            try:
                if 'user_id' not in st.session_state or 'session_id' not in st.session_state:
                    st.error("Error de sesión (faltan datos). Por favor, inicie sesión de nuevo.")
                    st.session_state.clear()
                    st.rerun()

                response = supabase.table("users").select("active_session_id").eq("id", st.session_state.user_id).single().execute()
                
                if response.data and 'active_session_id' in response.data:
                    db_session_id = response.data['active_session_id']
                    
                    if db_session_id != st.session_state.session_id:
                        st.error("Tu sesión ha sido cerrada porque iniciaste sesión en otro dispositivo.")
                        st.session_state.clear()
                        st.rerun()
                    else:
                        print("Heartbeat exitoso.")
                        st.session_state.last_heartbeat_check = current_time
                
                else:
                    st.error("Error al verificar sesión (usuario no encontrado).")
                    st.session_state.clear()
                    st.rerun()

            except Exception as e:
                print(f"Heartbeat check falló (ej. red), pero NO se expulsará al usuario. Error: {e}")
                st.session_state.last_heartbeat_check = current_time
    
    # --- FIN DEL BLOQUE DE HEARTBEAT ---

    # --- INICIO DE LA SECCIÓN DE SIDEBAR ---
    st.sidebar.image("LogoDataStudio.png")
    st.sidebar.write(f"Usuario: {st.session_state.user}")
    if st.session_state.get("is_admin", False): st.sidebar.caption("Rol: Administrador 👑")
    st.sidebar.divider()
    # --- FIN DE LA SECCIÓN DE SIDEBAR ---

    st.sidebar.header("Seleccione el modo de uso")
    
    modo = st.session_state.current_mode

    all_categories = {
        "Análisis": {
            c.MODE_CHAT: True,
            c.MODE_TEXT_ANALYSIS: user_features.get("transcript_file_limit", 0) > 0,
            c.MODE_DATA_ANALYSIS: True
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
            c.MODE_CONCEPT: user_features.get("has_concept_generation")
        }
    }
    
    default_expanded = ""
    for category, modes in all_categories.items():
        if modo in modes:
            default_expanded = category
            break

    if any(all_categories["Análisis"].values()):
        with st.sidebar.expander("Análisis", expanded=(default_expanded == "Análisis")):
            if all_categories["Análisis"][c.MODE_CHAT]:
                st.button(c.MODE_CHAT, on_click=set_mode_and_reset, args=(c.MODE_CHAT,), use_container_width=True, type="primary" if modo == c.MODE_CHAT else "secondary")
            if all_categories["Análisis"][c.MODE_TEXT_ANALYSIS]:
                st.button(c.MODE_TEXT_ANALYSIS, on_click=set_mode_and_reset, args=(c.MODE_TEXT_ANALYSIS,), use_container_width=True, type="primary" if modo == c.MODE_TEXT_ANALYSIS else "secondary")
            if all_categories["Análisis"][c.MODE_DATA_ANALYSIS]:
                st.button(c.MODE_DATA_ANALYSIS, on_click=set_mode_and_reset, args=(c.MODE_DATA_ANALYSIS,), use_container_width=True, type="primary" if modo == c.MODE_DATA_ANALYSIS else "secondary")

    if any(all_categories["Evaluación"].values()):
        with st.sidebar.expander("Evaluación", expanded=(default_expanded == "Evaluación")):
            if all_categories["Evaluación"][c.MODE_IDEA_EVAL]:
                st.button(c.MODE_IDEA_EVAL, on_click=set_mode_and_reset, args=(c.MODE_IDEA_EVAL,), use_container_width=True, type="primary" if modo == c.MODE_IDEA_EVAL else "secondary")
            if all_categories["Evaluación"][c.MODE_IMAGE_EVAL]:
                st.button(c.MODE_IMAGE_EVAL, on_click=set_mode_and_reset, args=(c.MODE_IMAGE_EVAL,), use_container_width=True, type="primary" if modo == c.MODE_IMAGE_EVAL else "secondary")
            if all_categories["Evaluación"][c.MODE_VIDEO_EVAL]:
                st.button(c.MODE_VIDEO_EVAL, on_click=set_mode_and_reset, args=(c.MODE_VIDEO_EVAL,), use_container_width=True, type="primary" if modo == c.MODE_VIDEO_EVAL else "secondary")

    if any(all_categories["Reportes"].values()):
        with st.sidebar.expander("Reportes", expanded=(default_expanded == "Reportes")):
            if all_categories["Reportes"][c.MODE_REPORT]:
                st.button(c.MODE_REPORT, on_click=set_mode_and_reset, args=(c.MODE_REPORT,), use_container_width=True, type="primary" if modo == c.MODE_REPORT else "secondary")
            if all_categories["Reportes"][c.MODE_ONEPAGER]:
                st.button(c.MODE_ONEPAGER, on_click=set_mode_and_reset, args=(c.MODE_ONEPAGER,), use_container_width=True, type="primary" if modo == c.MODE_ONEPAGER else "secondary")

    if any(all_categories["Creatividad"].values()):
        with st.sidebar.expander("Creatividad", expanded=(default_expanded == "Creatividad")):
            if all_categories["Creatividad"][c.MODE_IDEATION]:
                st.button(c.MODE_IDEATION, on_click=set_mode_and_reset, args=(c.MODE_IDEATION,), use_container_width=True, type="primary" if modo == c.MODE_IDEATION else "secondary")
            if all_categories["Creatividad"][c.MODE_CONCEPT]:
                st.button(c.MODE_CONCEPT, on_click=set_mode_and_reset, args=(c.MODE_CONCEPT,), use_container_width=True, type="primary" if modo == c.MODE_CONCEPT else "secondary")

    
    st.sidebar.header("Filtros de Búsqueda")
    
    run_filters = modo not in [c.MODE_TEXT_ANALYSIS]

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
        except Exception as e:
            print(f"Error al limpiar sesión en DB: {e}")
        
        supabase.auth.sign_out()
        st.session_state.clear()
        st.rerun()

    st.sidebar.divider()
    st.sidebar.markdown(footer_html, unsafe_allow_html=True)

    selected_files = [d.get("nombre_archivo") for d in db_filtered]

    if run_filters and not selected_files and modo not in [c.MODE_REPORT, c.MODE_IMAGE_EVAL, c.MODE_VIDEO_EVAL, c.MODE_ONEPAGER]:
         st.warning("⚠️ No hay estudios que coincidan con los filtros seleccionados.")

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
    
# =====================================================
# FUNCIÓN PRINCIPAL DE LA APLICACIÓN
# =====================================================
def main():
    
    st.set_page_config(
        page_title="Atelier Data Studio",
        page_icon="Logo_Casa.png"
    )
    
    apply_styles()

    if 'page' not in st.session_state: st.session_state.page = "login"
    if "api_key_index" not in st.session_state: st.session_state.api_key_index = 0
    if 'current_mode' not in st.session_state:
        st.session_state.current_mode = c.MODE_CHAT
        
    footer_text = "Atelier Consultoría y Estrategia S.A.S - Todos los Derechos Reservados 2025"
    footer_html = f"<div style='text-align: center; color: gray; font-size: 12px;'>{footer_text}</div>"

    if not st.session_state.get("logged_in"):
        
        st.markdown("""
            <style>
                [data-testid="stAppViewContainer"] > .main {
                    padding-top: 2rem;
                }
                div[data-testid="stBlock"] {
                    padding-top: 0rem;
                }
            </style>
            """, unsafe_allow_html=True)

        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            st.image("LogoDataStudio.png")
            if st.session_state.page == "login": show_login_page()
            elif st.session_state.page == "signup": show_signup_page()
            elif st.session_state.page == "reset_password": show_reset_password_page()
        st.divider()
        st.markdown(footer_html, unsafe_allow_html=True)
        st.stop()

    try:
        db_full = load_database(st.session_state.cliente)
    except Exception as e:
        st.error(f"Error crítico al cargar BD: {e}")
        st.stop()

    user_features = st.session_state.plan_features

    if st.session_state.get("is_admin", False):
        tab_user, tab_admin = st.tabs(["Modo Usuario", "Modo Administrador"])
        with tab_user:
            run_user_mode(db_full, user_features, footer_html)
        with tab_admin:
            st.title("Panel de Administración")
            st.write(f"Gestionando como: {st.session_state.user}")
            show_admin_dashboard(db_full)
    else:
        run_user_mode(db_full, user_features, footer_html)

# ==============================
# PUNTO DE ENTRADA
# ==============================
if __name__ == "__main__":
    main()
    