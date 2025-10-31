import streamlit as st
import time # Importar time

# ==============================
# 1. IMPORTAR MÓDULOS
# ==============================

# (Tus imports van aquí, no cambian)
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
from modes.transcript_mode import transcript_analysis_mode
from modes.onepager_mode import one_pager_ppt_mode
from utils import (
    extract_brand, reset_chat_workflow, reset_report_workflow 
)

def set_mode_and_reset(new_mode):
    # (Esta función no cambia)
    if 'current_mode' not in st.session_state or st.session_state.current_mode != new_mode:
        reset_chat_workflow() 
        st.session_state.pop("generated_concept", None)
        st.session_state.pop("evaluation_result", None)
        st.session_state.pop("report", None)
        st.session_state.pop("last_question", None)
        st.session_state.pop("image_evaluation_result", None)
        st.session_state.pop("video_evaluation_result", None)
        st.session_state.pop("uploaded_transcripts_text", None)
        st.session_state.pop("transcript_chat_history", None)
        st.session_state.pop("generated_ppt_bytes", None)
        st.session_state.current_mode = new_mode

# =====================================================
# FUNCIÓN PARA EL MODO USUARIO (REFACTORIZADA CON EXPANDERS)
# =====================================================
def run_user_mode(db_full, user_features, footer_html):
    
    # --- ¡BLOQUE DE HEARTBEAT CON "TEMPORIZADOR SUAVE"! ---
    
    GRACE_PERIOD_SECONDS = 5 # Período de gracia post-login
    HEARTBEAT_INTERVAL_SECONDS = 60 # Chequear solo cada 60 segundos
    current_time = time.time()
    
    # 1. Revisar si estamos en el período de gracia inicial
    login_time = st.session_state.get("login_timestamp", 0)
    if (current_time - login_time) > GRACE_PERIOD_SECONDS:
        
        # El período de gracia terminó. Ahora usamos el temporizador.
        last_check = st.session_state.get("last_heartbeat_check", 0)
        
        # 2. Revisar si han pasado 60 segundos desde el último chequeo
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

    # El resto de la función continúa
    st.sidebar.image("LogoDataStudio.png")
    st.sidebar.write(f"Usuario: {st.session_state.user}")
    if st.session_state.get("is_admin", False): st.sidebar.caption("Rol: Administrador 👑")
    st.sidebar.divider()

    st.sidebar.header("Seleccione el modo de uso")
    
    modo = st.session_state.current_mode

    all_categories = {
        "Análisis": {
            "Chat de Consulta Directa": True, 
            "Análisis de Notas y Transcripciones": user_features.get("transcript_file_limit", 0) > 0
        },
        "Evaluación": {
            "Evaluar una idea": user_features.get("has_idea_evaluation"),
            "Evaluación Visual": user_features.get("has_image_evaluation"),
            "Evaluación de Video": user_features.get("has_video_evaluation")
        },
        "Reportes": {
            "Generar un reporte de reportes": user_features.get("has_report_generation"),
            "Generador de One-Pager PPT": user_features.get("ppt_downloads_per_month", 0) > 0
        },
        "Creatividad": {
            "Conversaciones creativas": user_features.get("has_creative_conversation"),
            "Generación de conceptos": user_features.get("has_concept_generation")
        }
    }
    
    default_expanded = ""
    for category, modes in all_categories.items():
        if modo in modes:
            default_expanded = category
            break

    if any(all_categories["Análisis"].values()): 
        with st.sidebar.expander("Análisis", expanded=(default_expanded == "Análisis")):
            if all_categories["Análisis"]["Chat de Consulta Directa"]:
                st.button("Chat de Consulta Directa", on_click=set_mode_and_reset, args=("Chat de Consulta Directa",), use_container_width=True, type="primary" if modo == "Chat de Consulta Directa" else "secondary")
            if all_categories["Análisis"]["Análisis de Notas y Transcripciones"]:
                st.button("Análisis de Notas y Transcripciones", on_click=set_mode_and_reset, args=("Análisis de Notas y Transcripciones",), use_container_width=True, type="primary" if modo == "Análisis de Notas y Transcripciones" else "secondary")

    if any(all_categories["Evaluación"].values()):
        with st.sidebar.expander("Evaluación", expanded=(default_expanded == "Evaluación")):
            if all_categories["Evaluación"]["Evaluar una idea"]:
                st.button("Evaluar una idea", on_click=set_mode_and_reset, args=("Evaluar una idea",), use_container_width=True, type="primary" if modo == "Evaluar una idea" else "secondary")
            if all_categories["Evaluación"]["Evaluación Visual"]:
                st.button("Evaluación Visual", on_click=set_mode_and_reset, args=("Evaluación Visual",), use_container_width=True, type="primary" if modo == "Evaluación Visual" else "secondary")
            if all_categories["Evaluación"]["Evaluación de Video"]:
                st.button("Evaluación de Video", on_click=set_mode_and_reset, args=("Evaluación de Video",), use_container_width=True, type="primary" if modo == "Evaluación de Video" else "secondary")

    if any(all_categories["Reportes"].values()):
        with st.sidebar.expander("Reportes", expanded=(default_expanded == "Reportes")):
            if all_categories["Reportes"]["Generar un reporte de reportes"]:
                st.button("Generar un reporte de reportes", on_click=set_mode_and_reset, args=("Generar un reporte de reportes",), use_container_width=True, type="primary" if modo == "Generar un reporte de reportes" else "secondary")
            if all_categories["Reportes"]["Generador de One-Pager PPT"]:
                st.button("Generador de One-Pager PPT", on_click=set_mode_and_reset, args=("Generador de One-Pager PPT",), use_container_width=True, type="primary" if modo == "Generador de One-Pager PPT" else "secondary")

    if any(all_categories["Creatividad"].values()):
        with st.sidebar.expander("Creatividad", expanded=(default_expanded == "Creatividad")):
            if all_categories["Creatividad"]["Conversaciones creativas"]:
                st.button("Conversaciones creativas", on_click=set_mode_and_reset, args=("Conversaciones creativas",), use_container_width=True, type="primary" if modo == "Conversaciones creativas" else "secondary")
            if all_categories["Creatividad"]["Generación de conceptos"]:
                st.button("Generación de conceptos", on_click=set_mode_and_reset, args=("Generación de conceptos",), use_container_width=True, type="primary" if modo == "Generación de conceptos" else "secondary")

    
    st.sidebar.header("Filtros de Búsqueda")
    run_filters = modo not in ["Análisis de Notas y Transcripciones"] 

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

    if run_filters and not selected_files and modo not in ["Generar un reporte de reportes", "Evaluación Visual", "Evaluación de Video", "Generador de One-Pager PPT"]: 
         st.warning("⚠️ No hay estudios que coincidan con los filtros seleccionados.")

    if modo == "Generar un reporte de reportes": report_mode(db_filtered, selected_files)
    elif modo == "Conversaciones creativas": ideacion_mode(db_filtered, selected_files)
    elif modo == "Generación de conceptos": concept_generation_mode(db_filtered, selected_files)
    elif modo == "Chat de Consulta Directa": grounded_chat_mode(db_filtered, selected_files)
    elif modo == "Evaluar una idea": idea_evaluator_mode(db_filtered, selected_files)
    elif modo == "Evaluación Visual": image_evaluation_mode(db_filtered, selected_files)
    elif modo == "Evaluación de Video": video_evaluation_mode(db_filtered, selected_files)
    elif modo == "Análisis de Notas y Transcripciones": transcript_analysis_mode()
    elif modo == "Generador de One-Pager PPT": one_pager_ppt_mode(db_filtered, selected_files)

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
        st.session_state.current_mode = "Chat de Consulta Directa"
        
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
            show_admin_dashboard() 
    else: 
        run_user_mode(db_full, user_features, footer_html)

# ==============================
# PUNTO DE ENTRADA
# ==============================

# --- ¡LÍNEA CORREGIDA! ---
if __name__ == "__main__":
    main()