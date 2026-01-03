import streamlit as st
import time 
import re # <--- NUEVO: Para limpiar el HTML sucio
from datetime import datetime, timezone

# ==============================
# 1. IMPORTAR MÓDULOS GLOBALES
# ==============================
from styles import apply_styles, apply_login_styles 
from config import PLAN_FEATURES, banner_file
from services.storage import load_database 
from services.supabase_db import supabase
from auth import show_login_page, show_reset_password_page, show_activation_flow 
from admin.dashboard import show_admin_dashboard
from utils import extract_brand, validate_session_integrity 
# IMPORTAMOS LA FUNCIÓN DE BORRAR
from services.memory_service import get_project_memory, delete_project_memory 
import constants as c

# --- FUNCIÓN AUXILIAR PARA LIMPIAR HTML (NUEVO) ---
def remove_html_tags(text):
    """Elimina las etiquetas HTML para la vista previa de texto."""
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text)

# --- GESTIÓN DE ESTADO INTELIGENTE ---
def init_app_memory():
    if "app_memory" not in st.session_state:
        st.session_state.app_memory = {}

def set_mode_and_reset(new_mode):
    init_app_memory()
    current = st.session_state.get("current_mode")
    if current and "mode_state" in st.session_state:
        st.session_state.app_memory[current] = st.session_state.mode_state.copy()
    st.session_state.current_mode = new_mode
    if new_mode in st.session_state.app_memory:
        st.session_state.mode_state = st.session_state.app_memory[new_mode]
    else:
        st.session_state.mode_state = {}

# =====================================================
# FUNCIÓN PARA EL MODO USUARIO 
# =====================================================
def run_user_mode(db_full, user_features, footer_html):
    
    # --- LOGO SIDEBAR ---
    st.sidebar.image("LogoDataStudio.png", width=220)
    
    st.sidebar.write(f"Usuario: {st.session_state.user}")
    if st.session_state.get("is_admin", False): st.sidebar.caption("Rol: Administrador 👑")
    st.sidebar.divider()
    
    # --- SELECTOR DE MODOS ---
    st.sidebar.header("Seleccione el modo de uso")
    modo = st.session_state.current_mode
    
    all_categories = {
        "Análisis": {
            c.MODE_CHAT: True,
            c.MODE_TEXT_ANALYSIS: user_features.get("transcript_file_limit", 0) > 0,
            c.MODE_DATA_ANALYSIS: True,
            c.MODE_ETNOCHAT: user_features.get("has_etnochat_analysis"),
            c.MODE_TREND_ANALYSIS: True 
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
            
    for category_name, modes_dict in all_categories.items():
        if any(modes_dict.values()):
            with st.sidebar.expander(category_name, expanded=(default_expanded == category_name)):
                for mode_key, has_access in modes_dict.items():
                    if has_access:
                        st.button(
                            mode_key, 
                            on_click=set_mode_and_reset, 
                            args=(mode_key,), 
                            use_container_width=True, 
                            type="primary" if modo == mode_key else "secondary"
                        )

    # --- FILTROS ---
    st.sidebar.header("Filtros de Búsqueda")
    run_filters = modo not in [c.MODE_TEXT_ANALYSIS, c.MODE_DATA_ANALYSIS, c.MODE_ETNOCHAT, c.MODE_TREND_ANALYSIS] 
    
    user_client_name = st.session_state.get("cliente", "")
    db_base = db_full
    if user_client_name == "atelier demo":
        db_base = [doc for doc in db_full if doc.get("cliente") and "atelier" in str(doc.get("cliente")).lower()]

    if run_filters:
        marcas_options = sorted({doc.get("filtro", "") for doc in db_base if doc.get("filtro")})
        selected_marcas = st.sidebar.multiselect("Marca(s):", marcas_options, key="filter_marcas")
        
        if selected_marcas: db_step_1 = [d for d in db_base if d.get("filtro") in selected_marcas]
        else: db_step_1 = db_base

        years_options = sorted({doc.get("marca", "") for doc in db_step_1 if doc.get("marca")})
        selected_years = st.sidebar.multiselect("Año(s):", years_options, key="filter_years")
        
        if selected_years: db_step_2 = [d for d in db_step_1 if d.get("marca") in selected_years]
        else: db_step_2 = db_step_1

        brands_options = sorted({extract_brand(d.get("nombre_archivo", "")) for d in db_step_2 if extract_brand(d.get("nombre_archivo", ""))})
        selected_brands = st.sidebar.multiselect("Proyecto(s):", brands_options, key="filter_projects")
        
        if selected_brands: db_filtered = [d for d in db_step_2 if extract_brand(d.get("nombre_archivo", "")) in selected_brands]
        else: db_filtered = db_step_2
            
    else:
        db_filtered = db_full
        if run_filters is False: st.sidebar.caption("Filtros no disponibles en este modo.")

    # ==============================================================================
    # 2. BITÁCORA DE PROYECTO (ARREGLADA)
    # ==============================================================================
    st.sidebar.divider()
    st.sidebar.subheader("📌 Bitácora de Proyecto")
    
    if st.sidebar.button("🔄 Actualizar", type="secondary", use_container_width=True, key="refresh_pins"):
        st.rerun()

    saved_pins = get_project_memory()
    
    if saved_pins:
        # Usamos un contenedor con borde para cada pin
        for pin in saved_pins:
            with st.sidebar.container(border=True):
                # Fecha
                date_str = pin.get('created_at', '')[:10]
                st.caption(f"📅 {date_str}")
                
                # VISTA PREVIA LIMPIA (Sin HTML sucio)
                raw_content = pin.get('content', '')
                clean_preview = remove_html_tags(raw_content) # <--- Aquí limpiamos el HTML
                st.write(clean_preview[:90] + "...")
                
                # BOTONES DE ACCIÓN (Ver y Borrar)
                c1, c2 = st.columns(2)
                
                with c1:
                    # Usamos Popover para "VER" el contenido completo renderizado
                    with st.popover("👁️", use_container_width=True, help="Leer completo"):
                        st.markdown(f"**Hallazgo del {date_str}**")
                        st.divider()
                        # Aquí SÍ permitimos HTML para que se vean los tooltips
                        st.markdown(raw_content, unsafe_allow_html=True)
                
                with c2:
                    # Botón de borrar
                    if st.button("🗑️", key=f"del_{pin['id']}", use_container_width=True, help="Borrar"):
                        if delete_project_memory(pin['id']):
                            st.toast("Elemento eliminado")
                            time.sleep(0.5)
                            st.rerun()
    else:
        st.sidebar.caption("No hay hallazgos guardados.")

    # --- LOGOUT ---
    st.sidebar.write("") 
    if st.sidebar.button("Cerrar Sesión", key="logout_main", use_container_width=True):
        try:
            if 'user_id' in st.session_state:
                supabase.table("users").update({"active_session_id": None}).eq("id", st.session_state.user_id).execute()
        except: pass
        supabase.auth.sign_out(); st.session_state.clear(); st.rerun()

    st.sidebar.divider()
    st.sidebar.markdown(footer_html, unsafe_allow_html=True)
    
    # --- EJECUCIÓN DE MODOS ---
    selected_files = [d.get("nombre_archivo") for d in db_filtered]
    
    if modo == c.MODE_REPORT: 
        from modes.report_mode import report_mode
        report_mode(db_filtered, selected_files)

    elif modo == c.MODE_IDEATION: 
        from modes.ideation_mode import ideacion_mode
        ideacion_mode(db_filtered, selected_files)

    elif modo == c.MODE_CONCEPT: 
        from modes.concept_mode import concept_generation_mode
        concept_generation_mode(db_filtered, selected_files)

    elif modo == c.MODE_CHAT: 
        from modes.chat_mode import grounded_chat_mode
        grounded_chat_mode(db_filtered, selected_files)

    elif modo == c.MODE_IDEA_EVAL: 
        from modes.idea_eval_mode import idea_evaluator_mode
        idea_evaluator_mode(db_filtered, selected_files)

    elif modo == c.MODE_IMAGE_EVAL: 
        from modes.image_eval_mode import image_evaluation_mode
        image_evaluation_mode(db_filtered, selected_files)

    elif modo == c.MODE_VIDEO_EVAL: 
        from modes.video_eval_mode import video_evaluation_mode
        video_evaluation_mode(db_filtered, selected_files)

    elif modo == c.MODE_TEXT_ANALYSIS: 
        from modes.text_analysis_mode import text_analysis_mode
        text_analysis_mode()

    elif modo == c.MODE_ONEPAGER: 
        from modes.onepager_mode import one_pager_ppt_mode
        one_pager_ppt_mode(db_filtered, selected_files)

    elif modo == c.MODE_DATA_ANALYSIS: 
        from modes.data_analysis_mode import data_analysis_mode
        data_analysis_mode(db_filtered, selected_files)

    elif modo == c.MODE_ETNOCHAT: 
        from modes.etnochat_mode import etnochat_mode
        etnochat_mode()
        
    elif modo == c.MODE_SYNTHETIC: 
        from modes.synthetic_mode import synthetic_users_mode
        synthetic_users_mode(db_filtered, selected_files)
        
    elif modo == c.MODE_TREND_ANALYSIS:
        from modes.trend_analysis_mode import google_trends_mode
        google_trends_mode()

def main():
    st.set_page_config(
        page_title="Atelier Data Studio", 
        page_icon="Logo_Casa.png", 
        layout="wide",
        initial_sidebar_state="expanded"
    )
    apply_styles()

    if 'page' not in st.session_state: st.session_state.page = "login"
    if "mode_state" not in st.session_state: st.session_state.mode_state = {}
    if 'current_mode' not in st.session_state: st.session_state.current_mode = c.MODE_CHAT
    init_app_memory()
    
    params = st.query_params 
    footer_text = "Atelier Consultoría y Estrategia S.A.S - Todos los Derechos Reservados 2025"
    footer_html = f"<div style='text-align: center; color: gray; font-size: 12px;'>{footer_text}</div>"

    if st.session_state.get('flow_email_verified'):
        apply_login_styles()
        col1, col2, col3 = st.columns([3, 2, 3])
        with col2:
            st.image("LogoDataStudio.png", use_container_width=True)
            ctx = st.session_state.get('temp_auth_type', 'recovery')
            show_activation_flow(None, ctx) 
        st.divider(); st.markdown(footer_html, unsafe_allow_html=True); st.stop()

    auth_type = params.get("type")
    access_token = params.get("access_token")
    
    if auth_type in ["recovery", "invite"] and access_token:
        if isinstance(access_token, list): access_token = access_token[0]
        apply_login_styles()
        col1, col2, col3 = st.columns([3, 2, 3])
        with col2:
            st.image("LogoDataStudio.png", use_container_width=True)
            show_activation_flow(access_token, auth_type)
        st.divider(); st.markdown(footer_html, unsafe_allow_html=True); st.stop()

    if st.session_state.get("logged_in"):
        validate_session_integrity()
        if st.session_state.get("access_token"):
            try: supabase.auth.set_session(st.session_state.access_token, st.session_state.refresh_token)
            except: supabase.auth.sign_out(); st.session_state.clear(); st.rerun()
        if not hasattr(st.session_state, 'db_full'):
            try: 
                with st.spinner("Cargando repositorio de conocimientos..."):
                    st.session_state.db_full = load_database(st.session_state.cliente)
            except: st.session_state.clear(); st.rerun()
        
        if st.session_state.get("is_admin", False):
            t1, t2 = st.tabs(["Modo Usuario", "Modo Administrador"])
            with t1: run_user_mode(st.session_state.db_full, st.session_state.plan_features, footer_html)
            with t2: show_admin_dashboard(st.session_state.db_full)
        else:
            run_user_mode(st.session_state.db_full, st.session_state.plan_features, footer_html)
        st.stop() 

    apply_login_styles()
    col1, col2, col3 = st.columns([3, 2, 3])
    with col2:
        st.image("LogoDataStudio.png", use_container_width=True)
        if st.session_state.page == "reset_password": show_reset_password_page()
        else: show_login_page() 
            
    st.divider()
    st.markdown(footer_html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
