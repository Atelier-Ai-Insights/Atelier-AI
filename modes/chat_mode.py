import streamlit as st
import re
import time
from reporting.pdf_generator import generate_pdf_html
from reporting.docx_generator import generate_docx
from config import banner_file

# --- VENTANA EMERGENTE (VERSIÓN DE SEGURIDAD) ---
@st.dialog("Documentación de Respaldo")
def show_sources_dialog(content):
    """Extrae y muestra las fuentes detectadas en el texto."""
    
    # 1. Intentamos capturar el formato: [1] Nombre.pdf |||
    matches = re.findall(r'\[(\d+)\]\s*([^\[\]\|\n]+?)\s*\|\|\|', content)
    
    # 2. Si falla, buscamos nombres de archivos .pdf mencionadas con su número [1] Nombre.pdf
    if not matches:
        matches = re.findall(r'\[(\d+)\]\s*([a-zA-Z0-9_-]+\.(?:pdf|docx))', content)

    if not matches:
        st.info("Este análisis se basó en el contexto general de los documentos seleccionados.")
        return

    # Usamos diccionario para limpiar y organizar {Número: NombreLimpio}
    fuentes_finales = {}
    for cid, fname in matches:
        # Limpieza profunda del nombre
        name = re.sub(r'\.(pdf|docx|xlsx)$', '', fname, flags=re.IGNORECASE)
        name = re.sub(r'^\d{2,4}[-_]\d{1,2}[-_]\d{1,2}[-_]', '', name).replace("In-ATL_", "")
        fuentes_finales[cid] = name.strip()

    st.write("### Fuentes asociadas a este análisis:")
    
    # Renderizar la lista numerada
    for cid in sorted(fuentes_finales.keys(), key=int):
        st.markdown(f"**[{cid}]** 📄 {fuentes_finales[cid]}")

def render_final_actions(content, title, mode_key, on_reset_func):
    """Barra Maestra con Feedback y Exportación."""
    if not content: return
    st.divider()
    
    # Botones de Feedback y Pin
    col_f1, col_f2, col_pin, col_spacer = st.columns([1, 1, 1, 9])
    with col_f1: st.button("👍", key=f"up_{mode_key}")
    with col_f2: st.button("👎", key=f"down_{mode_key}")
    with col_pin:
        if st.button("📌", key=f"pin_{mode_key}"):
            st.toast("✅ Guardado")
            time.sleep(0.5)
            st.rerun()

    st.write("")
    
    # Acciones de Exportación
    col_ref, col_pdf, col_word, col_reset = st.columns(4)
    with col_ref:
        # El botón se habilita si hay rastro de citas o PDFs
        tiene_datos = "[" in content or ".pdf" in content.lower()
        if st.button("Ver Referencias", use_container_width=True, key=f"ref_{mode_key}", disabled=not tiene_datos):
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
        if st.button("Nueva Búsqueda", use_container_width=True, type="secondary", key=f"r_{mode_key}"):
            on_reset_func()
            st.rerun()
