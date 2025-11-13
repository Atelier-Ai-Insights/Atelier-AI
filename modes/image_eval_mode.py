import streamlit as st
from PIL import Image
from io import BytesIO
from utils import get_relevant_info
from services.gemini_api import call_gemini_stream # <-- Usar Stream
from services.supabase_db import log_query_event
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
from prompts import get_image_eval_prompt_parts
import constants as c

def image_evaluation_mode(db, selected_files):
    st.subheader("Evaluación Visual")
    st.markdown("...") 
    
    uploaded_file = st.file_uploader("Sube tu imagen aquí:", type=["jpg", "png", "jpeg"])
    target_audience = st.text_area("Describe el público objetivo (Target):", height=100, placeholder="Ej: Mujeres jóvenes...")
    comm_objectives = st.text_area("Define 2-3 objetivos de comunicación:", height=100, placeholder="Ej:\n1. Generar reconocimiento...")
    
    image_bytes = None
    if uploaded_file is not None: 
        image_bytes = uploaded_file.getvalue()
        st.image(image_bytes, caption="Imagen a evaluar", use_container_width=True)
        
    st.markdown("---")
    
    # Lógica para mostrar resultado existente
    if "image_evaluation_result" in st.session_state.mode_state:
        st.markdown("### Resultados Evaluación:")
        st.markdown(st.session_state.mode_state["image_evaluation_result"])
        
        col1, col2 = st.columns(2)
        with col1:
            pdf_bytes = generate_pdf_html(st.session_state.mode_state["image_evaluation_result"], title=f"Evaluacion Visual - {uploaded_file.name if uploaded_file else 'Imagen'}", banner_path=banner_file)
            if pdf_bytes: 
                st.download_button(label="Descargar Evaluación PDF", data=pdf_bytes, file_name=f"evaluacion.pdf", mime="application/pdf", use_container_width=True)
        with col2:
            if st.button("Evaluar Otra Imagen", use_container_width=True): 
                st.session_state.mode_state.pop("image_evaluation_result", None)
                st.rerun()
    
    # Lógica de generación
    elif st.button("Evaluar Imagen", use_container_width=True, disabled=(uploaded_file is None)):
        if not image_bytes or not target_audience.strip() or not comm_objectives.strip(): 
            st.warning("Completa todos los campos."); return
            
        with st.spinner("Analizando imagen..."):
            relevant_text_context = get_relevant_info(db, f"Contexto: {target_audience}", selected_files)
            # Truncado preventivo
            if len(relevant_text_context) > 800000: relevant_text_context = relevant_text_context[:800000]
                
            prompt_parts = get_image_eval_prompt_parts(target_audience, comm_objectives, relevant_text_context)
            image_data = Image.open(BytesIO(image_bytes))
            prompt_parts.append("\n\n**Imagen para evaluar:**")
            prompt_parts.append(image_data)
            
            # --- STREAMING ---
            stream = call_gemini_stream(prompt_parts)
            
            if stream: 
                st.markdown("### Resultados Evaluación:")
                response = st.write_stream(stream)
                
                st.session_state.mode_state["image_evaluation_result"] = response
                log_query_event(f"Evaluación Imagen: {uploaded_file.name}", mode=c.MODE_IMAGE_EVAL)
                st.rerun() # Rerun para mostrar botones de descarga
            else: 
                st.error("No se pudo generar evaluación.")
