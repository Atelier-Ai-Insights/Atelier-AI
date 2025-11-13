import streamlit as st
from io import BytesIO
from utils import get_relevant_info
from services.gemini_api import call_gemini_stream # <-- Usar Stream
from services.supabase_db import log_query_event
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
from prompts import get_video_eval_prompt_parts
import constants as c

def video_evaluation_mode(db, selected_files):
    st.subheader("Evaluación de Video")
    st.markdown("...") 
    
    uploaded_file = st.file_uploader("Sube tu video aquí:", type=["mp4", "mov", "avi", "wmv", "mkv"])
    target_audience = st.text_area("Describe el público objetivo:", height=100)
    comm_objectives = st.text_area("Define objetivos:", height=100)
    
    video_bytes = None
    if uploaded_file is not None:
        video_bytes = uploaded_file.getvalue()
        st.video(video_bytes)
            
    st.markdown("---")
    
    if "video_evaluation_result" in st.session_state.mode_state:
        st.markdown("### Resultados Evaluación:")
        st.markdown(st.session_state.mode_state["video_evaluation_result"])
        
        col1, col2 = st.columns(2)
        with col1:
            pdf_bytes = generate_pdf_html(st.session_state.mode_state["video_evaluation_result"], title="Evaluacion Video", banner_path=banner_file)
            if pdf_bytes: 
                st.download_button(label="Descargar PDF", data=pdf_bytes, file_name="evaluacion_video.pdf", mime="application/pdf", use_container_width=True)
        with col2:
            if st.button("Evaluar Otro Video", use_container_width=True): 
                st.session_state.mode_state.pop("video_evaluation_result", None)
                st.rerun()

    elif st.button("Evaluar Video", use_container_width=True, disabled=(uploaded_file is None)):
        if not video_bytes or not target_audience.strip() or not comm_objectives.strip(): 
            st.warning("Completa los campos."); return
            
        with st.spinner("Analizando video (esto puede tomar un momento)..."):
            relevant_text_context = get_relevant_info(db, f"Contexto: {target_audience}", selected_files)
            if len(relevant_text_context) > 800000: relevant_text_context = relevant_text_context[:800000]
                
            video_file_data = {'mime_type': uploaded_file.type, 'data': video_bytes}
            prompt_parts = get_video_eval_prompt_parts(target_audience, comm_objectives, relevant_text_context)
            prompt_parts.append("\n\n**Video para evaluar:**")
            prompt_parts.append(video_file_data)
            
            # --- STREAMING ---
            stream = call_gemini_stream(prompt_parts)
            
            if stream: 
                st.markdown("### Resultados Evaluación:")
                response = st.write_stream(stream)
                
                st.session_state.mode_state["video_evaluation_result"] = response
                log_query_event(f"Evaluación Video: {uploaded_file.name}", mode=c.MODE_VIDEO_EVAL)
                st.rerun()
            else: 
                st.error("No se pudo generar evaluación video.")
