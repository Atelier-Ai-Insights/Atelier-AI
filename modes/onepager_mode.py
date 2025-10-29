import streamlit as st
import json
from services.supabase_db import get_monthly_usage, log_query_event
import google.generativeai as genai
from config import safety_settings
from services.gemini_api import configure_api_dynamically 
from reporting.ppt_generator import crear_ppt_one_pager
from utils import get_relevant_info, extract_text_from_pdfs 

def one_pager_ppt_mode(db_filtered, selected_files):
    st.subheader("One-Pager Estratégico")
    ppt_limit = st.session_state.plan_features.get('ppt_downloads_per_month', 0)
    
    if ppt_limit == float('inf'): limit_text = "**Tu plan actual te permite generar One-Pagers ilimitados.**"
    elif ppt_limit > 0: limit_text = f"**Tu plan actual te permite generar {int(ppt_limit)} One-Pagers al mes.**"
    else: limit_text = "**Tu plan actual no incluye la generación de One-Pagers.**"
        
    st.markdown(f"Sintetiza los hallazgos clave... {limit_text}")

    if "generated_ppt_bytes" in st.session_state:
        st.success("¡Tu diapositiva One-Pager está lista!")
        st.download_button(label="Descargar One-Pager (.pptx)", data=st.session_state.generated_ppt_bytes, file_name=f"one_pager_estrategico.pptx", mime="application/vnd.openxmlformats-officedocument.presentationml.presentation", use_container_width=True)
        if st.button("Generar nuevo One-Pager", use_container_width=True, type="secondary"):
            del st.session_state.generated_ppt_bytes; st.rerun()
        return 

    st.divider()
    st.markdown("#### 1. Selecciona la Fuente de Datos")
    
    col1, col2 = st.columns(2)
    with col1: use_repo = st.toggle("Usar Repositorio de Estudios", value=True)
    with col2: use_uploads = st.toggle("Usar Archivos PDF Cargados", value=False)

    uploaded_files = None
    if use_uploads:
        uploaded_files = st.file_uploader("Carga tus archivos PDF aquí:", type=["pdf"], accept_multiple_files=True, key="onepager_pdf_uploader")
        if uploaded_files: st.caption(f"Cargados {len(uploaded_files)} archivo(s).")
            
    st.markdown("#### 2. Define el Tema Central")
    tema_central = st.text_area("¿Cuál es el tema central...?", height=100, placeholder="Ej: Oportunidades para snacks saludables...")
    st.divider()

    if st.button("Generar One-Pager", use_container_width=True, type="primary"):
        current_ppt_usage = get_monthly_usage(st.session_state.user, "Generador de One-Pager PPT")
        if current_ppt_usage >= ppt_limit and ppt_limit != float('inf'):
            st.error(f"¡Límite alcanzado! Tu plan permite {int(ppt_limit)} al mes.")
            return 
        if not tema_central.strip():
            st.warning("Por favor, describe el tema central."); return
        if not use_repo and not use_uploads:
            st.error("Debes seleccionar al menos una fuente de datos."); return
        if use_uploads and not uploaded_files:
            st.error("Has seleccionado 'Usar Archivos Cargados', pero no has subido PDFs."); return

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
        if not relevant_info.strip():
            st.error("No se pudo extraer ningún contexto de las fuentes."); return

        prompt_json = f"""... (Tu prompt JSON completo va aquí, igual que antes) ...""" # (Abreviado por espacio)

        data_json = None
        with st.spinner("Generando contenido con IA..."):
            response_text = None
            try:
                configure_api_dynamically() 
                json_generation_config = {"temperature": 0.5, "top_p": 0.8, "top_k": 32, "max_output_tokens": 8192, "response_mime_type": "application/json"}
                json_model = genai.GenerativeModel(model_name="gemini-2.5-flash", generation_config=json_generation_config, safety_settings=safety_settings)
                response = json_model.generate_content(prompt_json)
                response_text = response.text
                data_json = json.loads(response_text)
            except json.JSONDecodeError:
                st.error("Error: La IA no devolvió un JSON válido."); st.code(response_text); return
            except Exception as e:
                st.error(f"Error al contactar la API de Gemini: {e}"); st.code(str(response_text)); return
        
        if data_json:
            with st.spinner("Ensamblando diapositiva .pptx..."):
                ppt_bytes = crear_ppt_one_pager(data_json)
            if ppt_bytes:
                st.session_state.generated_ppt_bytes = ppt_bytes
                log_query_event(tema_central, mode="Generador de One-Pager PPT")
                st.rerun() 
            else:
                st.error("No se pudo crear el archivo PowerPoint.")