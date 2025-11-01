import streamlit as st
from PIL import Image
from io import BytesIO
from utils import get_relevant_info
from services.gemini_api import call_gemini_api
# --- ¡IMPORTACIÓN ACTUALIZADA! ---
from services.supabase_db import log_query_event, log_query_feedback
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
from prompts import get_image_eval_prompt_parts

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

    # --- FUNCIÓN DE CALLBACK PARA EL FEEDBACK ---
    def image_feedback_callback(feedback):
        query_id = st.session_state.get("last_image_query_id")
        if query_id:
            score = 1 if feedback['score'] == 'thumbs_up' else 0
            log_query_feedback(query_id, score)
            st.toast("¡Gracias por tu feedback!")
            # Oculta los botones después de votar
            st.session_state.voted_on_last_image = True
        else:
            st.toast("Error: No se encontró el ID de la consulta.")
    # --- FIN DEL CALLBACK ---
    
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
                
            prompt_parts = get_image_eval_prompt_parts(
                target_audience, 
                comm_objectives, 
                relevant_text_context
            )
            
            image_data = Image.open(BytesIO(image_bytes))
            
            try:
                image_label_index = prompt_parts.index("\n\n**Imagen:**")
                prompt_parts.insert(image_label_index + 1, image_data)
            except ValueError:
                st.warning("Advertencia: Etiqueta de imagen no encontrada en el prompt. Añadiendo al final.")
                prompt_parts.append("\n\n**Imagen:**")
                prompt_parts.append(image_data)
            
            evaluation_result = call_gemini_api(prompt_parts)
            
            if evaluation_result: 
                st.session_state.image_evaluation_result = evaluation_result
                
                # --- ¡CAMBIO AQUÍ! ---
                # 1. Loguear la consulta y obtener el ID
                query_id = log_query_event(f"Evaluación Imagen: {uploaded_file.name}", mode="Evaluación Visual")
                # 2. Guardar el ID y el estado del voto
                st.session_state["last_image_query_id"] = query_id
                st.session_state["voted_on_last_image"] = False # Resetear el estado de voto
                # --- FIN DEL CAMBIO ---
                
            else: 
                st.error("No se pudo generar evaluación.")
                st.session_state.pop("image_evaluation_result", None)
                
    if "image_evaluation_result" in st.session_state:
        st.markdown("---")
        st.markdown("### Resultados Evaluación:")
        st.markdown(st.session_state.image_evaluation_result)
        
        # --- ¡NUEVA SECCIÓN DE FEEDBACK! ---
        query_id = st.session_state.get("last_image_query_id")
        if query_id and not st.session_state.get("voted_on_last_image", False):
            st.experimental_user_feedback(
                key=query_id, 
                on_submit=image_feedback_callback
            )
        # --- FIN DE LA SECCIÓN DE FEEDBACK ---
        
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
                # Limpiamos las variables de feedback
                st.session_state.pop("last_image_query_id", None)
                st.session_state.pop("voted_on_last_image", None)
                st.rerun()