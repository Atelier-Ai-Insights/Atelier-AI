import streamlit as st
import time
import constants as c

# --- UTILS & SERVICES ---
from utils import get_relevant_info, render_process_status
from services.gemini_api import call_gemini_stream 
from services.supabase_db import log_query_event
from config import banner_file
from prompts import get_video_eval_prompt_parts

# --- COMPONENTES UNIFICADOS ---
from components.chat_interface import render_chat_history
from components.export_utils import render_final_actions

def video_evaluation_mode(db, selected_files):
    """
    Modo de Evaluación de Video: Integra el estándar de invisibilidad de fuentes
    y la barra maestra de acciones finales.
    """
    st.subheader("Evaluación de Video")
    st.markdown("Analiza piezas audiovisuales comparando objetivos contra hallazgos del repositorio.") 
    
    # 1. Inputs de Usuario
    uploaded_file = st.file_uploader("Sube tu video aquí:", type=["mp4", "mov", "avi", "wmv", "mkv"])
    target_audience = st.text_area("Describe el público objetivo:", height=100)
    comm_objectives = st.text_area("Define objetivos:", height=100)
    
    video_bytes = None
    if uploaded_file is not None:
        video_bytes = uploaded_file.getvalue()
        st.video(video_bytes)
            
    st.markdown("---")
    
    # 2. MOSTRAR RESULTADOS (Persistencia de Historial)
    # Usamos una lista para que render_chat_history pueda procesar el mensaje
    if "video_eval_history" not in st.session_state.mode_state:
        st.session_state.mode_state["video_eval_history"] = []

    # Renderizado limpio (oculta metadatos técnicos del video si los hubiera)
    render_chat_history(st.session_state.mode_state["video_eval_history"], source_mode="video")

    # 3. PROCESAMIENTO
    if st.button("Evaluar Video", use_container_width=True, disabled=(uploaded_file is None)):
        if not video_bytes or not target_audience.strip() or not comm_objectives.strip(): 
            st.warning("Completa los campos obligatorios."); return
        
        full_response = ""
        
        with render_process_status("Analizando video y contrastando con repositorio...", expanded=True) as status:
            # Búsqueda RAG de contexto
            relevant_text_context = get_relevant_info(db, f"Contexto: {target_audience}", selected_files)
            
            # Preparación de datos para Gemini (Multimodal)
            video_file_data = {'mime_type': uploaded_file.type, 'data': video_bytes}
            prompt_parts = get_video_eval_prompt_parts(target_audience, comm_objectives, relevant_text_context)
            prompt_parts.append("\n\n**Video para evaluar:**")
            prompt_parts.append(video_file_data)
            
            # Streaming de respuesta
            stream = call_gemini_stream(prompt_parts)
            
            if stream:
                status.update(label="¡Análisis completado!", state="complete", expanded=False)
                st.markdown("### Resultados Evaluación:")
                full_response = st.write_stream(stream)
                
                # GUARDADO CRÍTICO: Persistencia para render_final_actions
                st.session_state.mode_state["video_eval_history"] = [
                    {"role": "user", "content": f"Evaluación de: {uploaded_file.name}"},
                    {"role": "assistant", "content": full_response}
                ]
                
                try: log_query_event(f"Video Eval: {uploaded_file.name}", mode=c.MODE_VIDEO_EVAL)
                except: pass
                
                st.rerun()
            else:
                status.update(label="Error en el análisis", state="error")
                st.error("No se pudo generar la evaluación del video.")

    # 4. ACCIONES FINALES (Barra Maestra Unificada)
    if st.session_state.mode_state["video_eval_history"]:
        # Recuperamos el contenido del asistente (el análisis)
        analysis_content = st.session_state.mode_state["video_eval_history"][-1]["content"]
        
        def reset_video_workflow():
            st.session_state.mode_state["video_eval_history"] = []
            st.rerun()

        # Renderiza Feedback, Referencias (Modal con numeración filtrada) y Exportaciones
        render_final_actions(
            content=analysis_content,
            title=f"Evaluacion_Video_{uploaded_file.name if uploaded_file else 'Atelier'}",
            mode_key="video_eval_actions",
            on_reset_func=reset_video_workflow
        )
