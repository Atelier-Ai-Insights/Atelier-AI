import streamlit as st
import json
from services.supabase_db import get_monthly_usage, log_query_event
from config import safety_settings
from services.gemini_api import call_gemini_api 
from reporting.ppt_generator import crear_ppt_desde_json
from utils import get_relevant_info, extract_text_from_pdfs, clean_gemini_json
from prompts import PROMPTS_ONEPAGER, get_onepager_final_prompt
import constants as c

# =====================================================
# MODO: GENERADOR DE ONE-PAGER PPT (MEJORADO UX)
# =====================================================

def one_pager_ppt_mode(db_filtered, selected_files):
    st.subheader("Generador de Diapositivas Estratégicas")
    ppt_limit = st.session_state.plan_features.get('ppt_downloads_per_month', 0)

    if ppt_limit == float('inf'):
        limit_text = "**Tu plan actual te permite generar One-Pagers ilimitados.**"
    elif ppt_limit > 0:
        limit_text = f"**Tu plan actual te permite generar {int(ppt_limit)} One-Pagers al mes.**"
    else:
        limit_text = "**Tu plan actual no incluye la generación de One-Pagers.**"

    st.markdown(f"""
        Sintetiza los hallazgos clave en una diapositiva de PowerPoint usando la plantilla seleccionada.
        {limit_text}
    """)

    # --- PANTALLA DE RESULTADO (DESCARGA) ---
    if "generated_ppt_bytes" in st.session_state.mode_state:
        st.divider()
        st.success(f"✅ ¡Tu diapositiva '{st.session_state.mode_state.get('generated_ppt_template_name', 'Estratégica')}' está lista!")
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label=f"📥 Descargar .pptx",
                data=st.session_state.mode_state["generated_ppt_bytes"],
                file_name=f"diapositiva_{st.session_state.mode_state.get('generated_ppt_template_name', 'estrategica').lower().replace(' ','_')}.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                width='stretch',
                type="primary"
            )
        with col2:
            if st.button("✨ Generar otra", width='stretch', type="secondary"):
                del st.session_state.mode_state["generated_ppt_bytes"]
                st.session_state.mode_state.pop('generated_ppt_template_name', None)
                st.rerun()
        return

    # --- PANTALLA DE CONFIGURACIÓN ---
    st.divider()
    st.markdown("#### 1. Selecciona la Plantilla")
    template_options = list(PROMPTS_ONEPAGER.keys()) 
    selected_template_name = st.selectbox("Elige el tipo de diapositiva:", template_options)

    st.markdown("#### 2. Selecciona la Fuente de Datos")
    col1, col2 = st.columns(2)
    with col1: use_repo = st.toggle("Usar Repositorio de Estudios", value=True)
    with col2: use_uploads = st.toggle("Usar Archivos PDF Cargados", value=False)

    uploaded_files = None
    if use_uploads:
        uploaded_files = st.file_uploader("Carga tus archivos PDF aquí:", type=["pdf"], accept_multiple_files=True, key="onepager_pdf_uploader")
        if uploaded_files: st.caption(f"Cargados {len(uploaded_files)} archivo(s).")

    st.markdown(f"#### 3. Define el Tema Central")
    tema_central = st.text_area("¿Cuál es el enfoque principal?", height=100, placeholder=f"Ej: {selected_template_name} para la marca X en el segmento joven...")
    
    st.divider()

    if st.button(f"Generar Diapositiva '{selected_template_name}'", width='stretch', type="primary"):
        # Validaciones
        current_ppt_usage = get_monthly_usage(st.session_state.user, c.MODE_ONEPAGER)
        if current_ppt_usage >= ppt_limit and ppt_limit != float('inf'): st.error(f"¡Límite alcanzado!"); return
        if not tema_central.strip(): st.warning("Por favor, describe el tema central."); return
        if not use_repo and not use_uploads: st.error("Debes seleccionar al menos una fuente de datos."); return
        if use_uploads and not uploaded_files: st.error("Seleccionaste 'Usar Archivos Cargados', pero no has subido PDFs."); return

        # --- MEJORA UX: st.status paso a paso ---
        with st.status("🎨 Diseñando tu One-Pager...", expanded=True) as status:
            
            # PASO 1: CONTEXTO
            status.write("📚 Recopilando contexto de las fuentes seleccionadas...")
            relevant_info = ""
            if use_repo:
                repo_text = get_relevant_info(db_filtered, tema_central, selected_files)
                if repo_text: relevant_info += f"--- CONTEXTO REPOSITORIO ---\n{repo_text}\n\n"
            if use_uploads and uploaded_files:
                try:
                    pdf_text = extract_text_from_pdfs(uploaded_files)
                    if pdf_text: relevant_info += f"--- CONTEXTO PDFS CARGADOS ---\n{pdf_text}\n\n"
                except Exception as e:
                    status.write(f"⚠️ Error leyendo PDFs: {e}")

            if not relevant_info.strip(): 
                status.update(label="Error: Sin contexto", state="error")
                st.error("No se pudo extraer información relevante.")
                return

            # PASO 2: GENERACIÓN DE ESTRUCTURA
            status.write(f"💡 Generando estructura estratégica para '{selected_template_name}'...")
            final_prompt_json = get_onepager_final_prompt(relevant_info, selected_template_name, tema_central)
            
            data_json = None
            response_text = None
            try:
                json_generation_config = {"response_mime_type": "application/json"}
                response_text = call_gemini_api(
                    final_prompt_json,
                    generation_config_override=json_generation_config
                )
                
                if response_text is None: raise Exception("API Error")

                cleaned_text = clean_gemini_json(response_text)
                data_json = json.loads(cleaned_text)

            except Exception as e:
                status.update(label="Error en IA", state="error")
                st.error(f"Error generando estructura: {e}")
                if response_text: st.code(response_text)
                return

            # PASO 3: ENSAMBLAJE PPT
            if data_json:
                status.write("🛠️ Ensamblando diapositiva en PowerPoint (.pptx)...")
                ppt_bytes = crear_ppt_desde_json(data_json)
                
                if ppt_bytes:
                    status.update(label="¡Diapositiva creada con éxito!", state="complete", expanded=False)
                    
                    st.session_state.mode_state["generated_ppt_bytes"] = ppt_bytes
                    st.session_state.mode_state["generated_ppt_template_name"] = selected_template_name
                    
                    query_text = f"{selected_template_name}: {tema_central}"
                    log_query_event(query_text, mode=c.MODE_ONEPAGER)
                    
                    st.rerun()
                else:
                    status.update(label="Error al crear archivo PPT", state="error")
