import streamlit as st
import re
from reporting.pdf_generator import generate_pdf_html
from reporting.docx_generator import generate_docx
from config import banner_file

# --- VENTANA EMERGENTE (MODAL) ---
@st.dialog("Referencias y Evidencia Documental")
def show_sources_dialog(content):
    """Extrae la información técnica y la muestra en un modal."""
    pattern = r'\[(\d+)\]\s*([^\[\]\|\n]+?)\s*\|\|\|\s*(.+?)(?=\n\[\d+\]|$|\n\n)'
    matches = re.findall(pattern, content, flags=re.DOTALL)
    
    if not matches:
        st.warning("No se encontraron detalles técnicos de las citas.")
        return

    for cid, fname, quote in matches:
        with st.container(border=True):
            # Simplificación del nombre del archivo
            clean_name = re.sub(r'\.(pdf|docx|xlsx|txt)$', '', fname, flags=re.IGNORECASE)
            clean_name = re.sub(r'^\d{2,4}[-_]\d{1,2}[-_]\d{1,2}[-_]', '', clean_name).replace("In-ATL_", "")
            
            st.markdown(f"**[{cid}] {clean_name}**")
            st.info(f"\"{quote.strip()}\"")

def render_final_actions(content, title, mode_key, on_reset_func):
    """Barra maestra con Ver Referencias, Descargas y Reset."""
    if not content:
        return

    st.divider()
    clean_text = content.replace("```markdown", "").replace("```", "").strip()
    word_template = "Plantilla_Word_ATL.docx"
    
    # --- FILA DE ACCIONES ---
    # Dividimos en 4 columnas para incluir el nuevo botón
    col_ref, col_pdf, col_word, col_reset = st.columns(4)

    with col_ref:
        if st.button("🔍 Ver Referencias", use_container_width=True, key=f"btn_ref_final_{mode_key}"):
            show_sources_dialog(content)

    with col_pdf:
        pdf_bytes = generate_pdf_html(clean_text, title=title, banner_path=banner_file)
        if pdf_bytes:
            st.download_button("Descargar en PDF", data=pdf_bytes, file_name=f"{title}.pdf", use_container_width=True, key=f"pdf_{mode_key}")

    with col_word:
        docx_bytes = generate_docx(clean_text, title=title, template_path=word_template)
        if docx_bytes:
            st.download_button("Descargar en Word", data=docx_bytes, file_name=f"{title}.docx", use_container_width=True, key=f"word_{mode_key}")

    with col_reset:
        reset_label = "Nueva Búsqueda" if "chat" in mode_key else "Reiniciar"
        if st.button(reset_label, use_container_width=True, type="secondary", key=f"reset_{mode_key}"):
            on_reset_func()
            st.rerun()
