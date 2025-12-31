import streamlit as st
import json
import io
from services.supabase_db import get_monthly_usage, log_query_event
from config import safety_settings
from services.gemini_api import call_gemini_api 
from reporting.ppt_generator import crear_ppt_desde_json
from utils import get_relevant_info, extract_text_from_pdfs, clean_gemini_json
from prompts import PROMPTS_ONEPAGER, get_onepager_final_prompt
import constants as c

# =====================================================
# MODO: GENERADOR DE ONE-PAGER PPT (EDITABLE / NATIVO)
# =====================================================

def one_pager_ppt_mode(db_filtered, selected_files):
    st.subheader("Generador de Diapositivas Estratégicas")
    
    # 1. Verificación de Límites
    ppt_limit = st.session_state.plan_features.get('ppt_downloads_per_month', 0)
    is_unlimited = ppt_limit == float('inf')

    if is_unlimited:
        limit_text = "**Tu plan actual te permite generar One-Pagers ilimitados.**"
    elif ppt_limit > 0:
        limit_text = f"**Tu plan actual te permite generar {int(ppt_limit)} One-Pagers al mes.**"
    else:
        limit_text = "**Tu plan actual no incluye la generación de One-Pagers.**"

    st.markdown(f"""
        Sintetiza los hallazgos clave en una diapositiva de PowerPoint **totalmente editable**.
        {limit_text}
    """)

    # 2. Pantalla de Resultado (Descarga)
    if "generated_ppt_bytes" in st.session_state.mode_state:
        st.divider()
        template_name = st.session_state.mode_state.get('generated_ppt_template_name', 'Estratégica')
        
        st.success(f"✅ ¡Tu diapositiva '{template_name}' está lista y es editable!")
        st.info("ℹ️ Al ser un formato editable nativo, descárgalo para ver el diseño final en PowerPoint.")

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="📥 Descargar .pptx",
                data=st.session_state.mode_state["generated_ppt_bytes"],
                file_name=f"diapositiva_{template_name.lower().replace(' ','_')}.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                width='stretch',
                type="primary"
            )
        with col2:
            if st.button("✨ Generar otra", width='stretch', type="secondary"):
                # Limpiamos el estado
                st.session_state.mode_state.pop("generated_ppt_bytes", None)
                st.session_state.mode_state.pop("generated_ppt_template_name", None)
                st.rerun()
        return

    # 3. Configuración (Formulario)
    st.divider()
    st.markdown("#### 1. Selecciona la Plantilla")
    template_options = list(PROMPTS_ONEPAGER.keys()) 
    selected_template_name = st.selectbox("Elige el tipo de diapositiva:", template_options)

    st.markdown("#### 2. Selecciona la Fuente de Datos")
    col_src1, col_src2 = st.columns(2)
    with col_src1: use_repo = st.toggle("Usar Repositorio de Estudios", value=True)
    with col_src2: use_uploads = st.toggle("Usar Archivos PDF Cargados", value=False)

    uploaded_files = None
    if use_uploads:
        uploaded_files = st.file_uploader("Carga tus archivos PDF:", type=["pdf"], accept_multiple_files=True, key="onepager_pdf_uploader")
        if uploaded_files: st.caption(f"📎 {len(uploaded_files)} archivo(s) listo(s).")

    st.markdown(f"#### 3. Define el Tema Central")
    tema_central = st.text_area("¿Cuál es el enfoque principal?", height=100, placeholder=f"Ej: {selected_template_name} para la marca X...")
    
    st.divider()

    # 4. Acción de Generar
    if st.button(f"Generar Diapositiva '{selected_template_name}'", width='stretch', type="primary"):
        
        # --- Validaciones (Guard Clauses) ---
        current_ppt_usage = get_monthly_usage(st.session_state.user, c.MODE_ONEPAGER)
        if not is_unlimited and current_ppt_usage >= ppt_limit:
            st.error(f"⚠️ Has alcanzado tu límite mensual."); return
        if not tema_central.strip():
            st.warning("⚠️ Describe el tema central."); return
        if not use_repo and not use_uploads:
            st.error("⚠️ Selecciona una fuente de datos."); return

        # --- Proceso ---
        with st.status("🎨 Diseñando tu One-Pager...", expanded=True) as status:
            
            # A. Contexto
            status.write("📚 Analizando fuentes...")
            relevant_info = ""
            try:
                if use_repo:
                    repo_text = get_relevant_info(db_filtered, tema_central, selected_files)
                    if repo_text: relevant_info += f"--- CONTEXTO REPOSITORIO ---\n{repo_text}\n\n"
                if use_uploads and uploaded_files:
                    pdf_text = extract_text_from_pdfs(uploaded_files)
                    if pdf_text: relevant_info += f"--- CONTEXTO PDFS ---\n{pdf_text}\n\n"
            except Exception as e:
                status.update(label="Error leyendo archivos", state="error"); st.error(str(e)); return

            if not relevant_info.strip(): 
                status.update(label="Falta de contexto", state="error"); st.error("❌ No se encontró información relevante."); return

            # B. IA Estructura
            status.write(f"🧠 Estructurando contenido para '{selected_template_name}'...")
            final_prompt_json = get_onepager_final_prompt(relevant_info, selected_template_name, tema_central)
            
            data_json = None
            try:
                json_generation_config = {"response_mime_type": "application/json"}
                response_text = call_gemini_api(final_prompt_json, generation_config_override=json_generation_config)
                
                if not response_text: raise Exception("API vacía")
                
                cleaned_text = clean_gemini_json(response_text)
                data_json = json.loads(cleaned_text)
            except Exception as e:
                status.update(label="Error en IA", state="error"); st.error(f"Error IA: {e}"); return

            # C. Ensamblaje PPT (Nativo Editable)
            if data_json:
                status.write("🛠️ Construyendo formas editables en PowerPoint (.pptx)...")
                try:
                    # Llamamos al generador actualizado (sin imagen)
                    ppt_bytes = crear_ppt_desde_json(data_json)
                    
                    if ppt_bytes:
                        log_query_event(f"{selected_template_name}: {tema_central}", mode=c.MODE_ONEPAGER)
                        st.session_state.mode_state["generated_ppt_bytes"] = ppt_bytes
                        st.session_state.mode_state["generated_ppt_template_name"] = selected_template_name
                        status.update(label="¡Diapositiva creada!", state="complete", expanded=False)
                        st.rerun()
                    else:
                        raise Exception("Objeto PPT vacío")
                except Exception as e:
                    status.update(label="Error PPT", state="error"); st.error(str(e))
