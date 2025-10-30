import streamlit as st

# ==============================
# 1. IMPORTAR MÓDULOS
# ==============================

# Importar estilos y configuración
from styles import apply_styles
from config import PLAN_FEATURES, banner_file 

# Importar servicios
from services.storage import load_database
from services.supabase_db import supabase # Solo el cliente normal es necesario aquí

# Importar vistas de autenticación
from auth import show_login_page, show_signup_page, show_reset_password_page

# Importar panel de admin
from admin.dashboard import show_admin_dashboard

# Importar todos los modos de usuario
from modes.report_mode import report_mode
from modes.chat_mode import grounded_chat_mode
from modes.ideation_mode import ideacion_mode
from modes.concept_mode import concept_generation_mode
from modes.idea_eval_mode import idea_evaluator_mode
from modes.image_eval_mode import image_evaluation_mode
from modes.video_eval_mode import video_evaluation_mode
from modes.transcript_mode import transcript_analysis_mode
# (Importamos el modo onepager que modificaste para incluir PDFs)
from modes.onepager_mode import one_pager_ppt_mode

# Importar utilidades
from utils import (
    extract_brand, reset_chat_workflow, reset_report_workflow 
)

# =====================================================
# FUNCIÓN PARA EL MODO USUARIO (REFACTORIZADA)
# =====================================================
def run_user_mode(db_full, user_features, footer_html):
    st.sidebar.image("LogoDataStudio.png")
    st.sidebar.write(f"Usuario: {st.session_state.user}")
    if st.session_state.get("is_admin", False): st.sidebar.caption("Rol: Administrador 👑")
    st.sidebar.divider()

    db_filtered = db_full[:]

    # Construir lista de modos disponibles según el plan del usuario
    modos_disponibles = ["Chat de Consulta Directa"]
    if user_features.get("has_report_generation"): modos_disponibles.insert(0, "Generar un reporte de reportes")
    if user_features.get("has_creative_conversation"): modos_disponibles.append("Conversaciones creativas")
    if user_features.get("has_concept_generation"): modos_disponibles.append("Generación de conceptos")
    if user_features.get("has_idea_evaluation"): modos_disponibles.append("Evaluar una idea")
    if user_features.get("has_image_evaluation"): modos_disponibles.append("Evaluación Visual")
    if user_features.get("has_video_evaluation"): modos_disponibles.append("Evaluación de Video")
    if user_features.get("transcript_file_limit", 0) > 0: modos_disponibles.append("Análisis de Transcripciones")
    if user_features.get("ppt_downloads_per_month", 0) > 0: modos_disponibles.append("Generador de One-Pager PPT")

    st.sidebar.header("Seleccione el modo de uso")
    modo = st.sidebar.radio("Modos:", modos_disponibles, label_visibility="collapsed", key="main_mode_selector")

    # Resetear estados específicos del modo si cambia
    if 'current_mode' not in st.session_state: st.session_state.current_mode = modo
    if st.session_state.current_mode != modo:
        reset_chat_workflow() # Resetea chat_history
        st.session_state.pop("generated_concept", None)
        st.session_state.pop("evaluation_result", None)
        st.session_state.pop("report", None)
        st.session_state.pop("last_question", None)
        st.session_state.pop("image_evaluation_result", None)
        st.session_state.pop("video_evaluation_result", None)
        st.session_state.pop("uploaded_transcripts_text", None)
        st.session_state.pop("transcript_chat_history", None)
        st.session_state.pop("generated_ppt_bytes", None)
        
        st.session_state.current_mode = modo

    st.sidebar.header("Filtros de Búsqueda")
    # Aplicar filtros solo si el modo actual NO es Análisis de Transcripciones
    run_filters = modo not in ["Análisis de Transcripciones"] 

    marcas_options = sorted({doc.get("filtro", "") for doc in db_full if doc.get("filtro")})
    selected_marcas = st.sidebar.multiselect("Marca(s):", marcas_options, key="filter_marcas", disabled=not run_filters)
    if run_filters and selected_marcas: db_filtered = [d for d in db_filtered if d.get("filtro") in selected_marcas]

    years_options = sorted({doc.get("marca", "") for doc in db_full if doc.get("marca")})
    selected_years = st.sidebar.multiselect("Año(s):", years_options, key="filter_years", disabled=not run_filters)
    if run_filters and selected_years: db_filtered = [d for d in db_filtered if d.get("marca") in selected_years]

    brands_options = sorted({extract_brand(d.get("nombre_archivo", "")) for d in db_filtered if extract_brand(d.get("nombre_archivo", ""))})
    selected_brands = st.sidebar.multiselect("Proyecto(s):", brands_options, key="filter_projects", disabled=not run_filters)
    if run_filters and selected_brands: db_filtered = [d for d in db_filtered if extract_brand(d.get("nombre_archivo", "")) in selected_brands]

    if st.sidebar.button("Cerrar Sesión", key="logout_main", use_container_width=True):
        supabase.auth.sign_out()
        st.session_state.clear()
        st.rerun()

    st.sidebar.divider()
    st.sidebar.markdown(footer_html, unsafe_allow_html=True)

    # --- ENRUTADOR DE MODOS ---
    selected_files = [d.get("nombre_archivo") for d in db_filtered]

    if run_filters and not selected_files and modo not in ["Generar un reporte de reportes", "Evaluación Visual", "Evaluación de Video"]:
         st.warning("⚠️ No hay estudios que coincidan con los filtros seleccionados.")

    if modo == "Generar un reporte de reportes": report_mode(db_filtered, selected_files)
    elif modo == "Conversaciones creativas": ideacion_mode(db_filtered, selected_files)
    elif modo == "Generación de conceptos": concept_generation_mode(db_filtered, selected_files)
    elif modo == "Chat de Consulta Directa": grounded_chat_mode(db_filtered, selected_files)
    elif modo == "Evaluar una idea": idea_evaluator_mode(db_filtered, selected_files)
    elif modo == "Evaluación Visual": image_evaluation_mode(db_filtered, selected_files)
    elif modo == "Evaluación de Video": video_evaluation_mode(db_filtered, selected_files)
    elif modo == "Análisis de Transcripciones": transcript_analysis_mode() # No necesita db_filtered
    elif modo == "Generador de One-Pager PPT": one_pager_ppt_mode(db_filtered, selected_files)

# =====================================================
# FUNCIÓN PRINCIPAL DE LA APLICACIÓN
# =====================================================
def main():
    # Aplicar estilos CSS (desde styles.py)
    apply_styles()

    # Inicializar estado de sesión
    if 'page' not in st.session_state: st.session_state.page = "login"
    if "api_key_index" not in st.session_state: st.session_state.api_key_index = 0
    
    footer_text = "Atelier Consultoría y Estrategia S.A.S - Todos los Derechos Reservados 2025"
    footer_html = f"<div style='text-align: center; color: gray; font-size: 12px;'>{footer_text}</div>"

    # Lógica de autenticación
    if not st.session_state.get("logged_in"):
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            st.image("LogoDataStudio.png")
            # Llamar a las funciones de auth.py
            if st.session_state.page == "login": show_login_page()
            elif st.session_state.page == "signup": show_signup_page()
            elif st.session_state.page == "reset_password": show_reset_password_page()
        st.divider() 
        st.markdown(footer_html, unsafe_allow_html=True)
        st.stop()

    # Carga de datos post-login
    try: 
        # Llamar a la función de storage.py
        db_full = load_database(st.session_state.cliente) 
    except Exception as e: 
        st.error(f"Error crítico al cargar BD: {e}")
        st.stop()

    user_features = st.session_state.plan_features

    # Lógica de enrutamiento Admin/Usuario
    if st.session_state.get("is_admin", False):
        tab_user, tab_admin = st.tabs(["Modo Usuario", "Modo Administrador"])
        with tab_user: 
            run_user_mode(db_full, user_features, footer_html)
        with tab_admin:
            st.title("Panel de Administración")
            st.write(f"Gestionando como: {st.session_state.user}")
            # Llamar a la función de admin/dashboard.py
            show_admin_dashboard() 
    else: 
        run_user_mode(db_full, user_features, footer_html)

# ==============================
# PUNTO DE ENTRADA
# ==============================
if __name__ == "__main__":
    main()
