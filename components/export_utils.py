import streamlit as st
import re
import time
from reporting.pdf_generator import generate_pdf_html
from reporting.docx_generator import generate_docx
from services.supabase_db import log_message_feedback
from services.memory_service import save_project_insight
from config import banner_file

# --- VENTANA EMERGENTE (MODAL) ---
@st.dialog("Referencias y Evidencia Documental")
def show_sources_dialog(content):
    """Extrae la información técnica y la muestra en un modal."""
    # Buscamos el patrón: [1] NombreArchivo ||| Cita: "..."
    pattern = r'\[(\d+)\]\s*([^\[\]\|\n]+?)\s*\|\|\|\s*(.+?)(?=\n\[\d+\]|$|\n\n)'
    matches = re.findall(pattern, content, flags=re.DOTALL)
    
    if not matches:
        st.warning("No se encontraron detalles técnicos de las citas.")
        return

    for cid, fname, quote in matches:
        with st.container(border=True):
            # Simplificación del nombre del archivo (quita fechas y extensiones)
            clean_name = re.sub(r'\.(pdf|docx|xlsx|txt)$', '', fname, flags=re.IGNORECASE)
            clean_name = re.sub(r'^\d{2,4}[-_]\d{1,2}[-_]\d{1,2}[-_]', '', clean_name).replace("In-ATL_", "")
            
            st.markdown(f"**[{cid}] {clean_name}**")
            st.info(f"\"{quote.strip()}\"")

def render_final_actions(content, title, mode_key, on_reset_func):
    """Barra maestra con Feedback, Pin, Ver Referencias y Descargas."""
    if not content:
        return

    st.divider()
    clean_text = content.replace("```markdown", "").replace("```", "").strip()
    word_template = "Plantilla_Word_ATL.docx"
    
    # --- BLOQUE 1: FEEDBACK Y PIN (Iconos) ---
    st.caption("¿Qué te pareció este análisis?")
    col_f1, col_f2, col_pin, col_spacer = st.columns([1, 1, 1, 9])
    
    with col_f1:
        if st.button("👍", key=f"up_{mode_key}"):
            if log_message_feedback(clean_text, mode_key, "up"):
                st.toast("Feedback registrado 👍")
    
    with col_f2:
        if st.button("👎", key=f"down_{mode_key}"):
            if log_message_feedback(clean_text, mode_key, "down"):
                st.toast("Feedback registrado 🤔")

    with col_pin:
        if st.button("📌", key=f"pin_{mode_key}"):
            if save_project_insight(clean_text, source_mode=mode_key):
                st.toast("✅ Guardado en bitácora")
                time.sleep(0.5)
                st.rerun()

    st.write("") # Espaciador

    # --- BLOQUE 2: ACCIONES PRINCIPALES (Botones de texto) ---
    col_ref, col_pdf, col_reset = st.columns([1, 1, 1])

    with col_ref:
        # LÓGICA AJUSTADA: Habilita si hay separador ||| o si detecta referencias [1]
        tiene_citas = re.search(r'\[\d+\]', content) or "|||" in content
        
        if tiene_citas:
            if st.button("Ver Referencias", use_container_width=True, key=f"ref_active_{mode_key}"):
                show_sources_dialog(content)
        else:
            st.button("🔍 Ver Referencias", use_container_width=True, disabled=True, key=f"ref_inactive_{mode_key}")

    with col_pdf:
        pdf_bytes = generate_pdf_html(clean_text, title=title, banner_path=banner_file)
        if pdf_bytes:
            st.download_button(
                label="Descargar PDF",
                data=pdf_bytes,
                file_name=f"{title}.pdf",
                use_container_width=True,
                key=f"dl_pdf_{mode_key}"
            )

    with col_reset:
        label = "Nueva Búsqueda" if "chat" in mode_key else "Reiniciar"
        if st.button(label, use_container_width=True, type="secondary", key=f"res_{mode_key}"):
            on_reset_func()
            st.rerun()
