import streamlit as st
import os
from reporting.pdf_generator import generate_pdf_html
from reporting.docx_generator import generate_docx
from config import banner_file # Ya definido como "Banner (2).jpg" en config.py

def render_final_actions(content, title, mode_key, on_reset_func):
    """
    Crea la barra final asegurando el uso de plantillas y banners institucionales.
    """
    if not content:
        return

    st.divider()
    # Limpieza de sintaxis markdown para evitar errores de renderizado
    clean_text = content.replace("```markdown", "").replace("```", "").strip()
    
    # Rutas de plantillas basadas en tu estructura de archivos
    word_template = "Plantilla_Word_ATL.docx"
    
    # Definir etiquetas según el modo para mejorar UX
    reset_label = "Nueva Búsqueda" if any(x in mode_key for x in ["chat", "ideation", "concept"]) else "Reiniciar"
    
    col_pdf, col_word, col_reset = st.columns(3)

    with col_pdf:
        # El generador de PDF ya maneja internamente el banner y el footer
        pdf_bytes = generate_pdf_html(clean_text, title=title, banner_path=banner_file)
        if pdf_bytes:
            st.download_button(
                label="Descargar en PDF", 
                data=pdf_bytes, 
                file_name=f"{title}.pdf", 
                mime="application/pdf", 
                use_container_width=True, # Reemplaza width="stretch" para compatibilidad
                key=f"pdf_{mode_key}"
            )

    with col_word:
        # CRÍTICO: Pasamos la ruta de la plantilla explícitamente
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
