import streamlit as st
from PIL import Image
from io import BytesIO
import time

# --- UTILS & SERVICES ---
from utils import get_relevant_info, render_process_status, process_text_with_tooltips
from services.gemini_api import call_gemini_stream 
from services.supabase_db import log_query_event, log_message_feedback
from services.memory_service import save_project_insight
from config import banner_file
from prompts import get_image_eval_prompt_parts
import constants as c

# --- GENERADORES ---
from reporting.pdf_generator import generate_pdf_html
from reporting.docx_generator import generate_docx

def image_evaluation_mode(db, selected_files):
    st.subheader("Evaluación Visual")
    st.markdown("Analiza el impacto de tus imágenes publicitarias cruzando datos con visión artificial.") 
    
    # 1. Inputs
    uploaded_file = st.file_uploader("Sube tu imagen aquí:", type=["jpg", "png", "jpeg"])
    target_audience = st.text_area("Describe el público objetivo (Target):", height=100, placeholder="Ej: Mujeres jóvenes...")
    comm_objectives = st.text_area("Define 2-3 objetivos de comunicación:", height=100, placeholder="Ej:\n1. Generar reconocimiento...")
    
    image_bytes = None
    if uploaded_file is not None: 
        image_bytes = uploaded_file.getvalue()
        st.image(image_bytes, caption="Imagen a evaluar", width='stretch')
        
    st.markdown("---")
    
    # ==========================================
    # 2. MOSTRAR RESULTADOS (Lectura + Acciones)
    # ==========================================
    if "image_evaluation_result" in st.session_state.mode_state:
        raw_text = st.session_state.mode_state["image_evaluation_result"]
        
        st.markdown("### Resultados Evaluación:")
        
        # --- A. Renderizado Rico (Tooltips + Iconos) ---
        # Limpiamos markdown crudo y procesamos
        clean_text = raw_text.replace("```markdown", "").replace("```", "")
        html_content = process_text_with_tooltips(clean_text)
        st.markdown(html_content, unsafe_allow_html=True)
        
        # --- B. Barra de Acciones (Feedback + Pin) ---
        st.write("") # Espaciador
        col_up, col_down, col_spacer, col_pin = st.columns([1, 1, 10, 1])
        
        # Hash corto para keys únicas
        key_suffix = str(hash(raw_text))[:10]

        with col_up:
            if st.button("👍", key=f"img_up_{key_suffix}", help="Análisis útil"):
                log_message_feedback(raw_text, "image_eval", "up")
                st.toast("Feedback registrado 👍")

        with col_down:
            if st.button("👎", key=f"img_down_{key_suffix}", help="Análisis inexacto"):
                log_message_feedback(raw_text, "image_eval", "down")
                st.toast("Revisaremos la calidad 🤔")

        with col_pin:
            if st.button("📌", key=f"img_pin_{key_suffix}", help="Guardar en Bitácora"):
                if save_project_insight(raw_text, source_mode="image_eval"):
                    st.toast("✅ Guardado en bitácora")
                    time.sleep(1)
                    st.rerun() # Recarga para actualizar sidebar

        st.divider()
        
        # --- C. Botones de Descarga ---
        col1, col2, col3 = st.columns(3)
        
        with col1:
            pdf_bytes = generate_pdf_html(clean_text, title=f"Evaluación Visual", banner_path=banner_file)
            if pdf_bytes: 
                st.download_button("Descargar PDF", data=pdf_bytes, file_name=f"eval_visual.pdf", mime="application/pdf", width='stretch')
        
        with col2:
            docx_bytes = generate_docx(clean_text, title="Evaluación Visual")
            if docx_bytes:
                st.download_button("Descargar Word", data=docx_bytes, file_name="eval_visual.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", width='stretch', type="primary")

        with col3:
            if st.button("Evaluar Otra", width='stretch'): 
                st.session_state.mode_state.pop("image_evaluation_result", None)
                st.rerun()
    
    # ==========================================
    # 3. GENERACIÓN (Escritura)
    # ==========================================
    elif st.button("Evaluar Imagen", width='stretch', disabled=(uploaded_file is None)):
        if not image_bytes or not target_audience.strip() or not comm_objectives.strip(): 
            st.warning("Completa todos los campos."); return
        
        stream = None
        full_response = ""
        
        with render_process_status("Analizando imagen y estrategia...", expanded=True) as status:
            
            # Paso 1: RAG
            status.write("Consultando repositorio para contexto del target...")
            relevant_text_context = get_relevant_info(db, f"Contexto: {target_audience}", selected_files)
            if len(relevant_text_context) > 800000: relevant_text_context = relevant_text_context[:800000]
            
            # Paso 2: Construcción Prompt Multimodal
            status.write("Procesando imagen con visión artificial (Gemini)...")
            prompt_parts = get_image_eval_prompt_parts(target_audience, comm_objectives, relevant_text_context)
            
            try:
                image_data = Image.open(BytesIO(image_bytes))
                prompt_parts.append("\n\n**Imagen para evaluar:**")
                prompt_parts.append(image_data)
                
                stream = call_gemini_stream(prompt_parts)
                
                if stream:
                    status.update(label="¡Análisis completado!", state="complete", expanded=False)
                else:
                    status.update(label="Error en el análisis", state="error")
            except Exception as e:
                status.update(label="Error técnico", state="error")
                st.error(f"Detalle: {e}")
            
        if stream: 
            st.markdown("### Resultados Evaluación:")
            # Usamos write_stream para efecto visual inmediato
            full_response = st.write_stream(stream)
            
            # Guardamos y recargamos para activar el modo "Lectura" con tooltips
            st.session_state.mode_state["image_evaluation_result"] = full_response
            log_query_event(f"Evaluación Imagen: {uploaded_file.name}", mode=c.MODE_IMAGE_EVAL)
            st.rerun() 
        else: 
            if not full_response: st.error("No se pudo generar evaluación.")
