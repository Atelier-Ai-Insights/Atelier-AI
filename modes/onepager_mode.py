import streamlit as st
import json
from services.supabase_db import get_monthly_usage, log_query_event
# import google.generativeai as genai <--- ELIMINADO
from config import safety_settings
from services.gemini_api import call_gemini_api # <--- MODIFICADO
from reporting.ppt_generator import crear_ppt_desde_json
from utils import get_relevant_info, extract_text_from_pdfs
from prompts import PROMPTS_ONEPAGER, get_onepager_final_prompt
import constants as c

# =====================================================
# MODO: GENERADOR DE ONE-PAGER PPT (MEJORADO)
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

    if "generated_ppt_bytes" in st.session_state:
        st.success(f"¡Tu diapositiva '{st.session_state.get('generated_ppt_template_name', 'Estratégica')}' está lista!")
        
        st.download_button(
            label=f"Descargar Diapositiva (.pptx)",
            data=st.session_state.generated_ppt_bytes,
            file_name=f"diapositiva_{st.session_state.get('generated_ppt_template_name', 'estrategica').lower().replace(' ','_')}.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            use_container_width=True
        )
        if st.button("Generar nueva Diapositiva", use_container_width=True, type="secondary"):
            del st.session_state.generated_ppt_bytes
            st.session_state.pop('generated_ppt_template_name', None)
            st.rerun()
        return

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

    st.markdown(f"#### 3. Define el Tema Central para '{selected_template_name}'")
    tema_central = st.text_area("¿Cuál es el enfoque principal?", height=100, placeholder=f"Ej: {selected_template_name} para snacks saludables...")
    st.divider()

    if st.button(f"Generar Diapositiva '{selected_template_name}'", use_container_width=True, type="primary"):
        current_ppt_usage = get_monthly_usage(st.session_state.user, c.MODE_ONEPAGER)
        if current_ppt_usage >= ppt_limit and ppt_limit != float('inf'): st.error(f"¡Límite alcanzado!"); return
        if not tema_central.strip(): st.warning("Por favor, describe el tema central."); return
        if not use_repo and not use_uploads: st.error("Debes seleccionar al menos una fuente de datos."); return
        if use_uploads and not uploaded_files: st.error("Seleccionaste 'Usar Archivos Cargados', pero no has subido PDFs."); return

        relevant_info = ""
        with st.spinner("Procesando fuentes de datos..."):
            if use_repo:
                repo_text = get_relevant_info(db_filtered, tema_central, selected_files)
                if repo_text: relevant_info += f"--- CONTEXTO REPOSITORIO ---\n{repo_text}\n\n"
            if use_uploads and uploaded_files:
                try:
                    pdf_text = extract_text_from_pdfs(uploaded_files)
                    if pdf_text: relevant_info += f"--- CONTEXTO PDFS CARGADOS ---\n{pdf_text}\n\n"
                except Exception as e:
                    st.error(f"Error al procesar PDFs: {e}"); pdf_text = None
        if not relevant_info.strip(): st.error("No se pudo extraer ningún contexto."); return

        final_prompt_json = get_onepager_final_prompt(relevant_info, selected_template_name, tema_central)
        
        data_json = None
        with st.spinner(f"Generando contenido para '{selected_template_name}'..."):
            response_text = None
            try:
                # --- INICIO DE MODIFICACIÓN ---
                # Definimos la configuración JSON
                json_generation_config = {"response_mime_type": "application/json"}
                
                # Llamamos a la función API centralizada con el override
                response_text = call_gemini_api(
                    final_prompt_json,
                    generation_config_override=json_generation_config
                )
                
                if response_text is None:
                    # El error ya se mostró en la UI por call_gemini_api
                    raise Exception("La API de Gemini falló al generar el JSON.")

                data_json = json.loads(response_text)
                # --- FIN DE MODIFICACIÓN ---

            except json.JSONDecodeError: st.error("Error: La IA no devolvió un JSON válido."); st.code(response_text); return
            except Exception as e: 
                # Si el error no fue JSONDecode, imprimirlo (aunque call_gemini_api ya lo habrá hecho)
                if "JSON" not in str(e):
                    st.error(f"Error API Gemini: {e}")
                st.code(str(response_text)); 
                return

        if data_json:
            with st.spinner("Ensamblando diapositiva .pptx..."):
                ppt_bytes = crear_ppt_desde_json(data_json)
            if ppt_bytes:
                st.session_state.generated_ppt_bytes = ppt_bytes
                st.session_state.generated_ppt_template_name = selected_template_name
                
                # --- Lógica de guardado REVERTIDA ---
                query_text = f"{selected_template_name}: {tema_central}"
                log_query_event(query_text, mode=c.MODE_ONEPAGER)
                
                st.rerun()
            else:
                pass