import streamlit as st
from io import BytesIO
from utils import get_relevant_info
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event
from reporting.pdf_generator import generate_pdf_html
from config import banner_file

# =====================================================
# MODO: EVALUACIÓN DE VIDEO
# =====================================================

def video_evaluation_mode(db, selected_files):
    st.subheader("Evaluación de Video (Comerciales/Publicidad)")
    st.markdown("""
    Sube un video corto (MP4, MOV, AVI - preferiblemente < 100MB) y describe tu público objetivo y objetivos de comunicación. 
    El asistente evaluará el video (contenido visual y audio si lo tiene) basándose en criterios de marketing y 
    utilizará los hallazgos de los estudios seleccionados como contexto.
    """)
    
    uploaded_file = st.file_uploader("Sube tu video aquí:", type=["mp4", "mov", "avi", "wmv", "mkv"])
    target_audience = st.text_area("Describe el público objetivo (Target) [Video]:", height=100, placeholder="Ej: Adultos jóvenes 18-30...")
    comm_objectives = st.text_area("Define 2-3 objetivos de comunicación [Video]:", height=100, placeholder="Ej:\n1. Generar intriga.\n2. Asociar marca.")
    
    video_bytes = None
    if uploaded_file is not None:
        video_bytes = uploaded_file.getvalue()
        st.video(video_bytes)
        if uploaded_file.size > 100 * 1024 * 1024: 
            st.warning("⚠️ Video grande (>100MB). Análisis podría tardar/fallar.")
            
    st.markdown("---")
    
    if st.button("Evaluar Video", use_container_width=True, disabled=(uploaded_file is None)):
        if not video_bytes: 
            st.warning("Sube un video.")
            return
        if not target_audience.strip(): 
            st.warning("Describe el público.")
            return
        if not comm_objectives.strip(): 
            st.warning("Define objetivos.")
            return
            
        with st.spinner("Analizando video y contexto... ⏳ (Puede tardar minutos)"):
            relevant_text_context = get_relevant_info(db, f"Contexto para video: {target_audience}", selected_files)
            
            MAX_CONTEXT_TEXT = 800000 
            if len(relevant_text_context) > MAX_CONTEXT_TEXT:
                relevant_text_context = relevant_text_context[:MAX_CONTEXT_TEXT] + "\n\n...(contexto truncado)..."
                st.warning("El contexto de los estudios es muy largo y ha sido truncado.", icon="⚠️")
                
            video_file_data = {'mime_type': uploaded_file.type, 'data': video_bytes}
            
            prompt_parts = [
                "Actúa como director creativo/estratega mkt experto audiovisual. Analiza el video (visual/audio) en contexto de target/objetivos, usando hallazgos como referencia.",
                f"\n\n**Target:**\n{target_audience}",
                f"\n\n**Objetivos:**\n{comm_objectives}",
                "\n\n**Video:**",
                video_file_data,
                f"\n\n**Contexto (Hallazgos Estudios):**\n```\n{relevant_text_context[:8000]}\n```",
                "\n\n**Evaluación Detallada (Markdown):**",
                "\n### 1. Notoriedad/Impacto (Visual/Auditivo)",
                "* ¿Capta la atención? ¿Memorable? ¿Destaca?",
                "* Elementos clave (narrativa, ritmo, música, etc.) y su aporte (vs contexto).",
                "* ¿Insights contexto sobre preferencias audiovisuales?",
                "\n### 2. Mensaje Clave/Claridad",
                "* Mensajes principal/secundarios vs objetivos?",
                "* ¿Claro/relevante para target? ¿Audio+Video OK?",
                "* ¿Mensaje vs insights contexto?",
                "\n### 3. Branding/Identidad",
                "* ¿Marca integrada natural/efectiva? ¿Cuándo/cómo?",
                "* ¿Refuerza personalidad/valores marca?",
                "\n### 4. Call to Action",
                "* ¿Sugiere acción o genera emoción/pensamiento?",
                "* ¿Respuesta alineada con objetivos?",
                "* ¿Contexto sugiere que motivará?",
                "\n\n**Conclusión General:**",
                "* Valoración efectividad (target/objetivos), fortalezas, mejoras (conectando con insights si aplica)."
            ]
            
            evaluation_result = call_gemini_api(prompt_parts)
            
            if evaluation_result: 
                st.session_state.video_evaluation_result = evaluation_result
                log_query_event(f"Evaluación Video: {uploaded_file.name}", mode="Evaluación de Video")
            else: 
                st.error("No se pudo generar evaluación video.")
                st.session_state.pop("video_evaluation_result", None)
                
    if "video_evaluation_result" in st.session_state:
        st.markdown("---")
        st.markdown("### Resultados Evaluación:")
        st.markdown(st.session_state.video_evaluation_result)
        
        col1, col2 = st.columns(2)
        with col1:
            pdf_bytes = generate_pdf_html(st.session_state.video_evaluation_result, title=f"Evaluacion Video - {uploaded_file.name if uploaded_file else 'Video'}", banner_path=banner_file)
            if pdf_bytes: 
                st.download_button(label="Descargar Evaluación PDF", data=pdf_bytes, file_name=f"evaluacion_{uploaded_file.name if uploaded_file else 'video'}.pdf", mime="application/pdf", use_container_width=True)
            else: 
                st.error("Error al generar PDF.")
        with col2:
            if st.button("Evaluar Otro Video", use_container_width=True): 
                st.session_state.pop("video_evaluation_result", None)
                st.rerun()
