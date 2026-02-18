import streamlit as st
import re
import time
from reporting.pdf_generator import generate_pdf_html
from reporting.docx_generator import generate_docx
from services.supabase_db import log_message_feedback
from services.memory_service import save_project_insight
from config import banner_file

# --- VENTANA EMERGENTE (MODAL DE RESPALDO) ---
@st.dialog("Documentación de Respaldo")
def show_sources_dialog(content):
    """Extrae las fuentes del contenido oculto y las lista numeradas."""
    
    # Buscamos nombres de archivos PDF con su número asociado [1]
    # Esta regex captura tanto el formato técnico como nombres de archivos sueltos
    matches = re.findall(r'\[(\d+)\]\s*([^\[\]\|\n\s]+?\.pdf)', content, flags=re.IGNORECASE)
    
    # Si no hay matches con .pdf, intentamos la regex técnica de las tres barras
    if not matches:
        matches = re.findall(r'\[(\d+)\]\s*([^\[\]\|\n]+?)\s*\|\|\|', content)

    if not matches:
        st.info("Este análisis se basó en el contexto general de los documentos seleccionados.")
        return

    fuentes_finales = {}
    for cid, fname in matches:
        # Limpieza de nombres para la visualización
        name = re.sub(r'\.(pdf|docx|xlsx)$', '', fname, flags=re.IGNORECASE)
        name = re.sub(r'^\d{2,4}[-_]\d{1,2}[-_]\d{1,2}[-_]', '', name).replace("In-ATL_", "")
        fuentes_finales[cid] = name.strip()

    st.write("### Fuentes asociadas a este análisis:")
    for cid in sorted(fuentes_finales.keys(), key=int):
        st.markdown(f"**[{cid}]** 📄 {fuentes_finales[cid]}")

def render_final_actions(content, title, mode_key, on_reset_func):
    """Barra de acciones finales."""
    if not content: return
    st.divider()
    
    # Feedback
    st.caption("¿Qué te pareció este análisis?")
    col_f1, col_f2, col_pin, col_spacer = st.columns([1, 1, 1, 9])
    with col_f1: st.button("👍", key=f"up_{mode_key}")
    with col_f2: st.button("👎", key=f"down_{mode_key}")
    with col_pin: st.button("📌", key=f"pin_{mode_key}")

    st.write("") 

    # Botones principales
    col_ref, col_pdf, col_word, col_reset = st.columns(4)
    with col_ref:
        if st.button("Ver Referencias", use_container_width=True, key=f"ref_{mode_key}"):
            show_sources_dialog(content)
    
    with col_pdf:
        pdf_bytes = generate_pdf_html(content, title=title, banner_path=banner_file)
        if pdf_bytes:
            st.download_button("Descargar PDF", pdf_bytes, f"{title}.pdf", use_container_width=True, key=f"p_{mode_key}")

    with col_word:
        docx_bytes = generate_docx(content, title=title)
        if docx_bytes:
            st.download_button("Descargar Word", docx_bytes, f"{title}.docx", use_container_width=True, key=f"w_{mode_key}")

    with col_reset:
        if st.button("Nueva Búsqueda", use_container_width=True, type="secondary", key=f"res_{mode_key}"):
            on_reset_func()
            st.rerun()
