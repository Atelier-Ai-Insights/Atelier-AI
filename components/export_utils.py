import streamlit as st
import time
from reporting.pdf_generator import generate_pdf_html
from reporting.docx_generator import generate_docx
from config import banner_file

def render_final_actions(content, title, mode_key, on_reset_func):
    """
    Crea la barra final con:
    1. Descarga PDF (con banner)
    2. Descarga Word (con plantilla)
    3. Botón dinámico de Reiniciar/Nueva Búsqueda
    """
    if not content:
        return

    st.divider()
    clean_text = content.replace("```markdown", "").replace("```", "")
    
    # Definir etiquetas según el modo
    reset_label = "Nueva Búsqueda" if "chat" in mode_key or "ideation" in mode_key else "Reiniciar"
    
    # Tres columnas para los tres botones
    col_pdf, col_word, col_reset = st.columns(3)

    with col_pdf:
        pdf_bytes = generate_pdf_html(clean_text, title=title, banner_path=banner_file)
        if pdf_bytes:
            st.download_button("Descargar en PDF", data=pdf_bytes, file_name=f"{title}.pdf", mime="application/pdf", width="stretch", key=f"pdf_{mode_key}")

    with col_word:
        docx_bytes = generate_docx(clean_text, title=title)
        if docx_bytes:
            st.download_button("Descargar en Word", data=docx_bytes, file_name=f"{title}.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", width="stretch", key=f"word_{mode_key}")

    with col_reset:
        if st.button(reset_label, width="stretch", type="secondary", key=f"reset_{mode_key}"):
            on_reset_func()
            st.rerun()
