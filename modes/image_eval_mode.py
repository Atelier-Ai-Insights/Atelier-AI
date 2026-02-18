import streamlit as st
from PIL import Image
from io import BytesIO
import time
import constants as c

# --- UTILS & SERVICES ---
from utils import get_relevant_info, render_process_status
from services.gemini_api import call_gemini_stream 
from services.supabase_db import log_query_event
from config import banner_file
from prompts import get_image_eval_prompt_parts

# --- COMPONENTES UNIFICADOS ---
from components.chat_interface import render_chat_history
from components.export_utils import render_final_actions

def image_evaluation_mode(db, selected_files):
    """
    Modo de Evaluación Visual: Implementa el estándar de invisibilidad de fuentes
    y la barra maestra de acciones finales para análisis de imágenes.
    """
    st.subheader("Evaluación Visual")
    st.markdown("Analiza el impacto de tus imágenes publicitarias cruzando datos con visión artificial.") 
    
    # 1. Inputs de Usuario
    uploaded_file = st.file_uploader("Sube tu imagen aquí:", type=["jpg", "png", "jpeg"])
    target_audience = st.text_area("Describe el público objetivo (Target):", height=100, placeholder="Ej: Mujeres jóvenes...")
    comm_objectives = st.text_area("Define 2-3 objetivos de comunicación:", height=100, placeholder="Ej:\n1. Generar reconocimiento...")
    
    image_bytes = None
    if uploaded_file is not None: 
        image_bytes = uploaded_file.getvalue()
        st.image(image_bytes, caption="Imagen a evaluar", use_container_width=True)
        
    st.markdown("---")
    
    # 2. MOSTRAR RESULTADOS (Persistencia de Historial)
    if "image_eval_history" not in st.session_state.mode_state:
        st.session_state.mode_state["image_eval_history"] = []

    # Renderizado limpio: oculta metadatos técnicos mientras mantiene las citas
    render_chat_history(st.session_state.mode_state["image_eval_history"], source_mode="image")

    # 3. GENERACIÓN (Escritura)
    if st.button("Evaluar Imagen", use_container_width=True, disabled=(uploaded_file is None)):
        if not image_bytes or not target_audience.strip() or not comm_objectives.strip(): 
            st.warning("Completa todos los campos obligatorios."); return
        
        full_response = ""
        
        with render_process_status("Analizando imagen y estrategia...", expanded=True) as status:
            # Paso 1: RAG para contexto de mercado
            status.write("Consultando repositorio para contexto estratégico...")
            relevant_text_context = get_relevant_info(db, f"Target: {target_audience}", selected_files)
            if len(relevant_text_context) > 800000: relevant_text_context = relevant_text_context[:800000]
            
            # Paso 2: Construcción del análisis multimodal (Visión + Datos)
            status.write("Procesando imagen con visión artificial...")
            prompt_parts = get_image_eval_prompt_parts(target_audience, comm_objectives, relevant_text_context)
            
            try:
                img_obj = Image.open(BytesIO(image_bytes))
                prompt_parts.append("\n\n**Imagen para evaluar:**")
                prompt_parts.append(img_obj)
                
                stream = call_gemini_stream(prompt_parts)
                
                if stream:
                    status.update(label="¡Análisis completado!", state="complete", expanded=False)
                    st.markdown("### Resultados Evaluación:")
                    full_response = st.write_stream(stream)
                    
                    # GUARDADO CRÍTICO: Persistencia con metadatos para el modal
                    st.session_state.mode_state["image_eval_history"] = [
                        {"role": "user", "content": f"Evaluación de imagen: {uploaded_file.name}"},
                        {"role": "assistant", "content": full_response}
                    ]
                    
                    try: log_query_event(f"Image Eval: {uploaded_file.name}", mode=c.MODE_IMAGE_EVAL)
                    except: pass
                    
                    st.rerun() 
                else:
                    status.update(label="Error en el análisis", state="error")
            except Exception as e:
                status.update(label="Error técnico", state="error")
                st.error(f"Detalle: {e}")

    # 4. ACCIONES FINALES (Barra Maestra Unificada)
    if st.session_state.mode_state["image_eval_history"]:
        # Recuperamos el análisis más reciente
        analysis_content = st.session_state.mode_state["image_eval_history"][-1]["content"]
        
        def reset_image_workflow():
            st.session_state.mode_state["image_eval_history"] = []
            st.rerun()

        # Renderiza Feedback, Referencias (Modal con filtrado de duplicados) y Descargas
        render_final_actions(
            content=analysis_content,
            title=f"Evaluacion_Visual_{uploaded_file.name if uploaded_file else 'Atelier'}",
            mode_key="image_eval_actions",
            on_reset_func=reset_image_workflow
        )
