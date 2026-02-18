import streamlit as st
from reporting.pdf_generator import generate_pdf_html
from reporting.docx_generator import generate_docx
from config import banner_file

def render_final_actions(content, title, mode_key, on_reset_func):
    """
    Barra de Acciones Finales: Gestiona la exportación global del historial 
    y el reinicio de la sesión actual.
    """
    if not content:
        return

    st.divider()
    
    # Limpieza de sintaxis markdown técnica para los documentos descargables
    clean_text = content.replace("```markdown", "").replace("```", "").strip()
    word_template = "Plantilla_Word_ATL.docx"
    
    # --- SECCIÓN DE EXPORTACIÓN Y CONTROL ---
    reset_label = "Nueva Búsqueda" if any(x in mode_key for x in ["chat", "ideation", "concept"]) else "Reiniciar"
    
    col_pdf, col_word, col_reset = st.columns(3)

    with col_pdf:
        # El generador de PDF ya inyecta el banner_file y el footer institucional
        pdf_bytes = generate_pdf_html(clean_text, title=title, banner_path=banner_file)
        if pdf_bytes:
            st.download_button(
                label="Descargar en PDF", 
                data=pdf_bytes, 
                file_name=f"{title}.pdf", 
                mime="application/pdf", 
                use_container_width=True,
                key=f"pdf_final_{mode_key}"
            )

    with col_word:
        # Se pasa la plantilla .docx para mantener la identidad visual en Word
        docx_bytes = generate_docx(clean_text, title=title, template_path=word_template)
        if docx_bytes:
            st.download_button(
                label="Descargar en Word", 
                data=docx_bytes, 
                file_name=f"{title}.docx", 
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
                use_container_width=True,
                key=f"word_final_{mode_key}"
            )

    with col_reset:
        # Ejecuta la función de limpieza de estado definida en el modo correspondiente
        if st.button(reset_label, use_container_width=True, type="secondary", key=f"reset_final_{mode_key}"):
            on_reset_func()
            st.rerun()
