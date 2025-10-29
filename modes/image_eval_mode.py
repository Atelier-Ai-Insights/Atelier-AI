import streamlit as st
from PIL import Image
from io import BytesIO
from utils import get_relevant_info
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event
from reporting.pdf_generator import generate_pdf_html
from config import banner_file

# =====================================================
# MODO: EVALUACIÓN VISUAL (IMAGEN)
# =====================================================

def image_evaluation_mode(db, selected_files):
    st.subheader("Evaluación Visual de Creatividades")
    st.markdown("""
    Sube una imagen (JPG/PNG) y describe tu público objetivo y objetivos de comunicación. 
    El asistente evaluará la imagen basándose en criterios de marketing y utilizará los 
    hallazgos de los estudios seleccionados como contexto.
    """)
    
    uploaded_file = st.file_uploader("Sube tu imagen aquí:", type=["jpg", "png", "jpeg"])
    target_audience = st.text_area("Describe el público objetivo (Target):", height=100, placeholder="Ej: Mujeres jóvenes, 25-35 años...")
    comm_objectives = st.text_area("Define 2-3 objetivos de comunicación:", height=100, placeholder="Ej:\n1. Generar reconocimiento.\n2. Comunicar frescura.")
    
    image_bytes = None
    if uploaded_file is not None: 
        image_bytes = uploaded_file.getvalue()
        st.image(image_bytes, caption="Imagen a evaluar", use_container_width=True)
        
    st.markdown("---")
    
    if st.button("Evaluar Imagen", use_container_width=True, disabled=(uploaded_file is None)):
        if not image_bytes: 
            st.warning("Sube una imagen.")
            return
        if not target_audience.strip(): 
            st.warning("Describe el público.")
            return
        if not comm_objectives.strip(): 
            st.warning("Define objetivos.")
            return
            
        with st.spinner("Analizando imagen y contexto... 🧠✨"):
            relevant_text_context = get_relevant_info(db, f"Contexto para imagen: {target_audience}", selected_files)
            
            MAX_CONTEXT_TEXT = 800000 
            if len(relevant_text_context) > MAX_CONTEXT_TEXT:
                relevant_text_context = relevant_text_context[:MAX_CONTEXT_TEXT] + "\n\n...(contexto truncado)..."
                st.warning("El contexto de los estudios es muy largo y ha sido truncado.", icon="⚠️")
                
            prompt_parts = [
                "Actúa como director creativo/estratega mkt experto. Analiza la imagen en contexto de target/objetivos, usando hallazgos como referencia.",
                f"\n\n**Target:**\n{target_audience}",
                f"\n\n**Objetivos:**\n{comm_objectives}",
                "\n\n**Imagen:**",
                Image.open(BytesIO(image_bytes)),
                f"\n\n**Contexto (Hallazgos Estudios):**\n```\n{relevant_text_context[:10000]}\n```",
                "\n\n**Evaluación Detallada (Markdown):**",
                "\n### 1. Notoriedad/Impacto Visual",
                "* ¿Capta la atención? ¿Atractiva/disruptiva para target?",
                "* Elementos visuales clave y su aporte (apóyate en contexto si hay insights visuales).",
                "\n### 2. Mensaje Clave/Claridad",
                "* Mensajes principal/secundarios vs objetivos?",
                "* ¿Claro para target? ¿Ambigüedad?",
                "* ¿Mensaje vs insights del contexto?",
                "\n### 3. Branding/Identidad",
                "* ¿Marca integrada efectivamente? ¿Reconocible?",
                "* ¿Refuerza personalidad/valores marca (según contexto)?",
                "\n### 4. Call to Action",
                "* ¿Sugiere acción o genera emoción/pensamiento (curiosidad, deseo, etc.)?",
                "* ¿Respuesta alineada con objetivos?",
                "* ¿Contexto sugiere que motivará al target?",
                "\n\n**Conclusión General:**",
                "* Valoración efectividad (target/objetivos), fortalezas, mejoras (conectando con insights si aplica)."
            ]
            
            evaluation_result = call_gemini_api(prompt_parts)
            
            if evaluation_result: 
                st.session_state.image_evaluation_result = evaluation_result
                log_query_event(f"Evaluación Imagen: {uploaded_file.name}", mode="Evaluación Visual")
            else: 
                st.error("No se pudo generar evaluación.")
                st.session_state.pop("image_evaluation_result", None)
                
    if "image_evaluation_result" in st.session_state:
        st.markdown("---")
        st.markdown("### Resultados Evaluación:")
        st.markdown(st.session_state.image_evaluation_result)
        
        col1, col2 = st.columns(2)
        with col1:
            pdf_bytes = generate_pdf_html(st.session_state.image_evaluation_result, title=f"Evaluacion Visual - {uploaded_file.name if uploaded_file else 'Imagen'}", banner_path=banner_file)
            if pdf_bytes: 
                st.download_button(label="Descargar Evaluación PDF", data=pdf_bytes, file_name=f"evaluacion_{uploaded_file.name if uploaded_file else 'imagen'}.pdf", mime="application/pdf", use_container_width=True)
            else: 
                st.error("Error al generar PDF.")
        with col2:
            if st.button("Evaluar Otra Imagen", use_container_width=True): 
                st.session_state.pop("image_evaluation_result", None)
                st.rerun()
