import streamlit as st
from io import BytesIO
import time

# --- UTILS & SERVICES ---
from utils import get_relevant_info, render_process_status, process_text_with_tooltips
from services.gemini_api import call_gemini_stream 
from services.supabase_db import log_query_event, log_message_feedback
from services.memory_service import save_project_insight
from config import banner_file
from prompts import get_video_eval_prompt_parts
import constants as c

# --- GENERADORES ---
from reporting.pdf_generator import generate_pdf_html
from reporting.docx_generator import generate_docx

def video_evaluation_mode(db, selected_files):
    st.subheader("Evaluación de Video")
    st.markdown("Analiza piezas audiovisuales comparando objetivos contra hallazgos del repositorio.") 
    
    # 1. Inputs
    uploaded_file = st.file_uploader("Sube tu video aquí:", type=["mp4", "mov", "avi", "wmv", "mkv"])
    target_audience = st.text_area("Describe el público objetivo:", height=100)
    comm_objectives = st.text_area("Define objetivos:", height=100)
    
    video_bytes = None
    if uploaded_file is not None:
        video_bytes = uploaded_file.getvalue()
        st.video(video_bytes)
            
    st.markdown("---")
    
    # ==========================================
    # 2. MOSTRAR RESULTADOS (Lectura + Acciones)
    # ==========================================
    if "video_evaluation_result" in st.session_state.mode_state:
        raw_text = st.session_state.mode_state["video_evaluation_result"]
        
        st.markdown("### Resultados Evaluación:")
        
        # --- A. Renderizado Rico (Tooltips + Iconos) ---
        clean_text = raw_text.replace("```markdown", "").replace("```", "")
        html_content = process_text_with_tooltips(clean_text)
        st.markdown(html_content, unsafe_allow_html=True)
        
        # --- B. Barra de Acciones (Feedback + Pin) ---
        st.write("") 
        col_up, col_down, col_spacer, col_pin = st.columns([1, 1, 10, 1])
        
        # Hash corto para keys únicas
        key_suffix = str(hash(raw_text))[:10]

        with col_up:
            if st.button("👍", key=f"vid_up_{key_suffix}", help="Análisis útil"):
                log_message_feedback(raw_text, "video_eval", "up")
                st.toast("Feedback registrado 👍")

        with col_down:
            if st.button("👎", key=f"vid_down_{key_suffix}", help="Análisis inexacto"):
                log_message_feedback(raw_text, "video_eval", "down")
                st.toast("Revisaremos la calidad 🤔")

        with col_pin:
            if st.button("📌", key=f"vid_pin_{key_suffix}", help="Guardar en Bitácora"):
                if save_project_insight(raw_text, source_mode="video_eval"):
                    st.toast("✅ Guardado en bitácora")
                    time.sleep(1)
                    st.rerun() # Recarga para actualizar sidebar

        st.divider()
        
        # --- C. Botones de Descarga ---
        col1, col2, col3 = st.columns(3)
        
        with col1:
            pdf_bytes = generate_pdf_html(clean_text, title="Evaluacion Video", banner_path=banner_file)
            if pdf_bytes: 
                st.download_button("Descargar PDF", data=pdf_bytes, file_name="eval_video.pdf", mime="application/pdf", width='stretch')
        
        with col2:
            docx_bytes = generate_docx(clean_text, title="Evaluación de Video")
            if docx_bytes:
                st.download_button("Descargar Word", data=docx_bytes, file_name="eval_video.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", width='stretch', type="primary")

        with col3:
            if st.button("Evaluar Otro", width='stretch'): 
                st.session_state.mode_state.pop("video_evaluation_result", None)
                st.rerun()

    # ==========================================
    # 3. GENERACIÓN (Escritura)
    # ==========================================
    elif st.button("Evaluar Video", width='stretch', disabled=(uploaded_file is None)):
        if not video_bytes or not target_audience.strip() or not comm_objectives.strip(): 
            st.warning("Completa los campos."); return
        
        stream = None
        full_response = ""
        
        with render_process_status("Analizando video y contexto...", expanded=True) as status:
            
            # Paso 1: RAG
            status.write("Consultando repositorio para contexto del target...")
            relevant_text_context = get_relevant_info(db, f"Contexto: {target_audience}", selected_files)
            if len(relevant_text_context) > 200000: relevant_text_context = relevant_text_context[:200000]
            
            # Paso 2: Prompt Multimodal
            status.write("Procesando video con visión artificial (Gemini)...")
            video_file_data = {'mime_type': uploaded_file.type, 'data': video_bytes}
            prompt_parts = get_video_eval_prompt_parts(target_audience, comm_objectives, relevant_text_context)
            prompt_parts.append("\n\n**Video para evaluar:**")
            prompt_parts.append(video_file_data)
            
            stream = call_gemini_stream(prompt_parts)
            
            if stream:
                status.update(label="¡Análisis completado!", state="complete", expanded=False)
            else:
                status.update(label="Error en el análisis", state="error")
        
        if stream: 
            st.markdown("### Resultados Evaluación:")
            # Write stream
            full_response = st.write_stream(stream)
            
            # Guardar y recargar
            st.session_state.mode_state["video_evaluation_result"] = full_response
            log_query_event(f"Evaluación Video: {uploaded_file.name}", mode=c.MODE_VIDEO_EVAL)
            st.rerun()
        else: 
            if not full_response: st.error("No se pudo generar evaluación video.")
