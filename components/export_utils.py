import streamlit as st
import time
from reporting.pdf_generator import generate_pdf_html
from reporting.docx_generator import generate_docx
from services.supabase_db import log_message_feedback
from services.memory_service import save_project_insight
from config import banner_file

def render_final_actions(content, title, mode_key, on_reset_func):
    """
    Barra de Acciones Maestra: Feedback, Pin, Exportación y Reinicio.
    """
    if not content:
        return

    st.divider()
    clean_text = content.replace("```markdown", "").replace("```", "").strip()
    word_template = "Plantilla_Word_ATL.docx"
    
    # --- BLOQUE 1: FEEDBACK Y PIN ---
    st.caption("¿Qué te pareció este análisis?")
    col_f1, col_f2, col_pin, col_spacer = st.columns([1, 1, 1, 9])
    
    with col_f1:
        if st.button("👍", key=f"up_{mode_key}", help="Útil"):
            if log_message_feedback(clean_text, mode_key, "up"):
                st.toast("¡Gracias! Feedback registrado. 👍")
    
    with col_f2:
        if st.button("👎", key=f"down_{mode_key}", help="No es lo que esperaba"):
            if log_message_feedback(clean_text, mode_key, "down"):
                st.toast("Tomamos nota para mejorar. 🤔")

    with col_pin:
        if st.button("📌", key=f"pin_{mode_key}", help="Guardar en Bitácora"):
            if save_project_insight(clean_text, source_mode=mode_key):
                st.toast("✅ Guardado en bitácora")
                time.sleep(1)
                st.rerun()

    st.write("") 

    # --- BLOQUE 2: EXPORTACIÓN Y RESET ---
    reset_label = "Nueva Búsqueda" if any(x in mode_key for x in ["chat", "ideation", "concept"]) else "Reiniciar"
    
    col_pdf, col_word, col_reset = st.columns(3)

    with col_pdf:
        pdf_bytes = generate_pdf_html(clean_text, title=title, banner_path=banner_file)
        if pdf_bytes:
            st.download_button(
                label="Descargar en PDF", 
                data=pdf_bytes, 
                file_name=f"{title}.pdf", 
                mime="application/pdf", 
                use_container_width=True,
                key=f"pdf_{mode_key}"
            )

    with col_word:
        docx_bytes = generate_docx(clean_text, title=title, template_path=word_template)
        if docx_bytes:
            st.download_button(
                label="Descargar en Word", 
                data=docx_bytes, 
                file_name=f"{title}.docx", 
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
                use_container_width=True,
                key=f"word_{mode_key}"
            )

    with col_reset:
        if st.button(reset_label, use_container_width=True, type="secondary", key=f"reset_{mode_key}"):
            on_reset_func()
            st.rerun()
