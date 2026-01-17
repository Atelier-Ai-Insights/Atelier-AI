import streamlit as st
import sys
import traceback
import matplotlib
import time 
import re 
import os 

# --- 1. PARCHE CRÍTICO DE MATPLOTLIB ---
matplotlib.use('Agg') 
import matplotlib.pyplot as plt

# ==========================================
# 2. IMPORTACIONES
# ==========================================
try:
    import constants as c
    from styles import apply_styles, apply_login_styles 
    from config import PLAN_FEATURES, banner_file
    from services.storage import load_database 
    from services.supabase_db import supabase
    from auth import show_login_page, show_reset_password_page, show_activation_flow 
    from admin.dashboard import show_admin_dashboard
    from utils import extract_brand, validate_session_integrity, process_text_with_tooltips
    from services.memory_service import get_project_memory, delete_project_memory 
except ImportError as e:
    st.error(f"Error cargando módulos internos: {e}")
    st.stop()

# ==========================================
# 3. IMPORTACIÓN EXTERNA
# ==========================================
try:
    import google.generativeai as genai
except ImportError:
    print("Advertencia: Librería de Google AI no encontrada o incompatible.")

# --- HELPER FUNCTIONS ---
def remove_html_tags(text):
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text)

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

# --- FUNCIÓN SEGURA PARA RENDERIZAR LOGO ---
def render_logo(use_column_width=False, width=220):
    logo_file = "LogoDataStudio.png"
    if os.path.exists(logo_file):
        if use_column_width:
            st.image(logo_file, use_container_width=True)
        else:
            st.image(logo_file, width=width)
    else:
        st.markdown("### 🎨 **Atelier AI**")

# --- VISOR DE NOTAS (POP-UP) ---
@st.dialog("Nota Guardada")
def show_saved_insight(content, date_str):
    st.caption(f"📅 Guardado el: {date_str}")
    st.divider()
    html_content = process_text_with_tooltips(content)
    st.markdown(html_content, unsafe_allow_html=True)
    
    if st.button("Cerrar", use_container_width=True):
        st.rerun()

# =====================================================
# FUNCIÓN DE UI (REORDENADA)
# =====================================================
def run_user_interface(db_full, user_features, footer_html):
    # Sidebar
    with st.sidebar:
        render_logo(width=220)
    
    usuario_actual = st.session_state.get("user", "Usuario")
    st.sidebar.write(f"Usuario: {usuario_actual}")
    if st.session_state.get("is_admin", False): st.sidebar.caption("Rol: Administrador")
    st.sidebar.divider()
    
    # 1. SELECTOR DE MODOS
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
                        st.button(mode_key, on_click=set_mode_and_reset, args=(mode_key,), use_container_width=True, type="primary" if modo == mode_key else "secondary")
    
    st.sidebar.divider()
    
    # 2. BITÁCORA / PINES (AHORA ARRIBA DE LOS FILTROS)
    # Al mover esto antes de los filtros, siempre estará visible y accesible.
    st.sidebar.subheader("Conversaciones y Reportes")
    saved_pins = get_project_memory()
    
    if saved_pins:
        for pin in saved_pins:
            date_str = pin.get('created_at', '')[:10]
            clean_text = remove_html_tags(pin.get('content', ''))
            
            with st.sidebar.expander(f"{date_str} | {clean_text[:20]}...", expanded=False):
                st.caption(clean_text[:100] + "...") 
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Ver", key=f"view_{pin['id']}", use_container_width=True):
                        st.session_state.pin_to_view = pin
                        st.rerun()
                with c2:
                    if st.button("Borrar", key=f"del_{pin['id']}", use_container_width=True):
                        delete_project_memory(pin['id']); st.rerun()
    else:
        st.sidebar.caption("No hay hallazgos guardados.")

    st.sidebar.divider()

    # 3. FILTROS DE BÚSQUEDA (AHORA AL FINAL)
    st.sidebar.header("Filtros de Búsqueda")
    run_filters = modo not in [c.MODE_TEXT_ANALYSIS, c.MODE_DATA_ANALYSIS, c.MODE_ETNOCHAT, c.MODE_TREND_ANALYSIS] 
    
    user_client_name = st.session_state.get("cliente", "")
    db_base = db_full
    if user_client_name == "atelier demo":
        db_base = [doc for doc in db_full if doc.get("cliente") and "atelier" in str(doc.get("cliente")).lower()]

    if run_filters:
        marcas_options = sorted({doc.get("filtro", "") for doc in db_base if doc.get("filtro")})
        selected_marcas = st.sidebar.multiselect("Marca(s):", marcas_options, key="filter_marcas")
        db_step_1 = [d for d in db_base if d.get("filtro") in selected_marcas] if selected_marcas else db_base

        years_options = sorted({doc.get("marca", "") for doc in db_step_1 if doc.get("marca")})
        selected_years = st.sidebar.multiselect("Año(s):", years_options, key="filter_years")
        db_step_2 = [d for d in db_step_1 if d.get("marca") in selected_years] if selected_years else db_step_1

        brands_options = sorted({extract_brand(d.get("nombre_archivo", "")) for d in db_step_2 if extract_brand(d.get("nombre_archivo", ""))})
        selected_brands = st.sidebar.multiselect("Proyecto(s):", brands_options, key="filter_projects")
        db_filtered = [d for d in db_step_2 if extract_brand(d.get("nombre_archivo", "")) in selected_brands] if selected_brands else db_step_2
    else:
        db_filtered = db_full
        if run_filters is False: st.sidebar.caption("Filtros no disponibles en este modo.")

    # Logout
    st.sidebar.divider()
    if st.sidebar.button("Cerrar Sesión", key="logout_main", use_container_width=True):
        try: supabase.table("users").update({"active_session_id": None}).eq("id", st.session_state.user_id).execute()
        except: pass
        supabase.auth.sign_out(); st.session_state.clear(); st.rerun()

    st.sidebar.markdown(footer_html, unsafe_allow_html=True)
    
    # --- ÁREA PRINCIPAL ---
    
    # Modal
    if "pin_to_view" in st.session_state:
        pin = st.session_state.pin_to_view
        show_saved_insight(pin['content'], pin.get('created_at', '')[:10])
        del st.session_state.pin_to_view

    selected_files = [d.get("nombre_archivo") for d in db_filtered]
    
    # Carga de módulos
    if modo == c.MODE_REPORT: 
        from modes.report_mode import report_mode; report_mode(db_filtered, selected_files)
    elif modo == c.MODE_IDEATION: 
        from modes.ideation_mode import ideacion_mode; ideacion_mode(db_filtered, selected_files)
    elif modo == c.MODE_CONCEPT: 
        from modes.concept_mode import concept_generation_mode; concept_generation_mode(db_filtered, selected_files)
    elif modo == c.MODE_CHAT: 
        from modes.chat_mode import grounded_chat_mode; grounded_chat_mode(db_filtered, selected_files)
    elif modo == c.MODE_IDEA_EVAL: 
        from modes.idea_eval_mode import idea_evaluator_mode; idea_evaluator_mode(db_filtered, selected_files)
    elif modo == c.MODE_IMAGE_EVAL: 
        from modes.image_eval_mode import image_evaluation_mode; image_evaluation_mode(db_filtered, selected_files)
    elif modo == c.MODE_VIDEO_EVAL: 
        from modes.video_eval_mode import video_evaluation_mode; video_evaluation_mode(db_filtered, selected_files)
    elif modo == c.MODE_TEXT_ANALYSIS: 
        from modes.text_analysis_mode import text_analysis_mode; text_analysis_mode()
    elif modo == c.MODE_ONEPAGER: 
        from modes.onepager_mode import one_pager_ppt_mode; one_pager_ppt_mode(db_filtered, selected_files)
    elif modo == c.MODE_DATA_ANALYSIS: 
        from modes.data_analysis_mode import data_analysis_mode; data_analysis_mode(db_filtered, selected_files)
    elif modo == c.MODE_ETNOCHAT: 
        from modes.etnochat_mode import etnochat_mode; etnochat_mode()
    elif modo == c.MODE_SYNTHETIC: 
        from modes.synthetic_mode import synthetic_users_mode; synthetic_users_mode(db_filtered, selected_files)
    elif modo == c.MODE_TREND_ANALYSIS:
        from modes.trend_analysis_mode import google_trends_mode; google_trends_mode()

# =====================================================
# MAIN
# =====================================================
def main():
    st.set_page_config(page_title="Atelier Data Studio", page_icon="Logo_Casa.png", layout="wide", initial_sidebar_state="expanded")
    
    if 'has_cleared_cache' not in st.session_state:
        st.cache_resource.clear()
        st.session_state.has_cleared_cache = True

    status_placeholder = st.empty()
    
    try:
        status_placeholder.info("🚀 Iniciando sistema...")
        apply_styles()
        
        if 'page' not in st.session_state: st.session_state.page = "login"
        if "mode_state" not in st.session_state: st.session_state.mode_state = {}
        if 'current_mode' not in st.session_state: st.session_state.current_mode = c.MODE_CHAT
        init_app_memory()
        
        params = st.query_params 
        footer_text = "Atelier Consultoría y Estrategia S.A.S - Todos los Derechos Reservados 2025"
        footer_html = f"<div style='text-align: center; color: gray; font-size: 12px;'>{footer_text}</div>"

        # Rutas de Login
        if st.session_state.get('flow_email_verified') or (params.get("type") in ["recovery", "invite"]):
            status_placeholder.empty()
            apply_login_styles()
            c1, c2, c3 = st.columns([3, 2, 3])
            with c2:
                render_logo(use_column_width=True) 
                auth_type = params.get("type", "recovery")
                token = params.get("access_token")
                if isinstance(token, list): token = token[0]
                show_activation_flow(token, auth_type)
            st.stop()

        # Sesión Activa
        if st.session_state.get("logged_in"):
            status_placeholder.info("🔐 Verificando credenciales...")
            validate_session_integrity()
            
            if "user" not in st.session_state: st.session_state.clear(); st.rerun()

            if st.session_state.get("access_token"):
                try: supabase.auth.set_session(st.session_state.access_token, st.session_state.refresh_token)
                except: supabase.auth.sign_out(); st.session_state.clear(); st.rerun()
            
            if not hasattr(st.session_state, 'db_full'):
                status_placeholder.info("📂 Cargando base de datos del cliente...")
                try: 
                    st.session_state.db_full = load_database(st.session_state.cliente)
                except Exception as e:
                    st.error(f"Error cargando datos: {e}")
                    st.stop()
            
            status_placeholder.empty()
            
            if st.session_state.get("is_admin", False):
                t1, t2 = st.tabs(["Modo Usuario", "Modo Administrador"])
                with t1: run_user_interface(st.session_state.db_full, st.session_state.plan_features, footer_html)
                with t2: show_admin_dashboard(st.session_state.db_full)
            else:
                run_user_interface(st.session_state.db_full, st.session_state.plan_features, footer_html)
            st.stop() 

        # Login por defecto
        status_placeholder.empty()
        apply_login_styles()
        c1, c2, c3 = st.columns([3, 2, 3])
        with c2:
            render_logo(use_column_width=True)
            if st.session_state.page == "reset_password": show_reset_password_page()
            else: show_login_page() 
        st.divider()
        st.markdown(footer_html, unsafe_allow_html=True)

    except Exception as e:
        st.error("🔥 Error Fatal de Ejecución")
        st.code(traceback.format_exc())

if __name__ == "__main__":
    main()
