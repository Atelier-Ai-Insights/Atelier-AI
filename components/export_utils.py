import streamlit as st
import re

# --- VENTANA EMERGENTE (MODAL CON NUMERACIÓN) ---
@st.dialog("Documentación de Respaldo")
def show_sources_dialog(content):
    """Muestra la lista de archivos consultados con su índice de cita [x]."""
    
    # Regex robusta para capturar el índice y el nombre: [1] NombreArchivo.pdf |||
    # El primer grupo (\d+) es el número, el segundo ([^\[\]\|\n]+?) es el nombre
    pattern_tech = r'\[(\d+)\]\s*([^\[\]\|\n]+?)\s*\|\|\|'
    matches = re.findall(pattern_tech, content, flags=re.IGNORECASE | re.DOTALL)
    
    if not matches:
        # Intento de rescate si el formato de la IA varió ligeramente
        pattern_alt = r'\[(\d+)\]\s*([a-zA-Z0-9_-]+\.[a-z]{3,4})'
        matches = re.findall(pattern_alt, content)

    if not matches:
        st.info("Este análisis se basó en el contexto general de los documentos seleccionados.")
        return

    # Usar diccionario para mapear {Número: NombreLimpio} y evitar duplicados
    fuentes_mapeadas = {}
    for cid, fname in matches:
        # Limpieza estética del nombre del archivo (quitar fechas y marcas de sistema)
        clean_name = re.sub(r'\.(pdf|docx|xlsx|txt)$', '', fname, flags=re.IGNORECASE)
        clean_name = re.sub(r'^\d{2,4}[-_]\d{1,2}[-_]\d{1,2}[-_]', '', clean_name).replace("In-ATL_", "")
        fuentes_mapeadas[cid] = clean_name.strip()

    st.write("### Documentos utilizados como evidencia:")
    
    # Renderizado con la numeración asociada a las citas del texto
    # Se ordena numéricamente para que aparezca [1], [2], [3]...
    for cid in sorted(fuentes_mapeadas.keys(), key=int):
        st.markdown(f"**[{cid}]** 📄 {fuentes_mapeadas[cid]}")
