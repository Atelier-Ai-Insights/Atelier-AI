import streamlit as st
import unicodedata
import json
import re
import fitz  # PyMuPDF
import time
from contextlib import contextmanager

# ==============================
# GESTIÓN DE STOPWORDS
# ==============================
@st.cache_resource
def get_stopwords():
    base_stopwords = {
        'de', 'la', 'el', 'en', 'y', 'a', 'los', 'del', 'las', 'un', 'para', 'con', 'no', 'una', 'su', 'que', 
        'se', 'por', 'es', 'más', 'lo', 'pero', 'me', 'mi', 'al', 'le', 'si', 'este', 'esta', 'son', 'sobre',
        'the', 'and', 'to', 'of', 'in', 'is', 'that', 'for', 'it', 'as', 'was', 'with', 'on', 'at', 'by'
    }
    custom_list = {
        '...', 'p', 'r', 'rta', 'respuesta', 'respuestas', 'si', 'no', 'na', 'ninguno', 'ninguna', 'nan',
        'document', 'presentation', 'python', 'warning', 'created', 'page', 'objetivo', 'tecnica', 
        'investigacion', 'participante', 'sesiones', 'proyecto', 'análisis', 'hola', 'buenos', 'dias',
        'video', 'audio', 'imagen', 'transcripcion'
    }
    return base_stopwords | custom_list

# ==============================
# UI COMPONENTS
# ==============================
@contextmanager
def render_process_status(label="Procesando solicitud...", expanded=True):
    status_container = st.status(label, expanded=expanded)
    try:
        yield status_container
    except Exception as e:
        status_container.update(label="❌ Error en el proceso", state="error", expanded=True)
        st.error(f"Ocurrió un error inesperado: {str(e)}")

# ==============================
# FUNCIONES AUXILIARES
# ==============================
def normalize_text(text):
    if not text: return ""
    try: 
        text = str(text).lower()
        normalized = unicodedata.normalize("NFD", text)
        return "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    except Exception: return str(text).lower()

def extract_brand(filename):
    if not filename or "In-ATL_" not in str(filename): return ""
    try: 
        base = str(filename).replace("\\", "/").split("/")[-1]
        if "In-ATL_" in base: return base.split("In-ATL_")[1].rsplit(".", 1)[0]
    except: pass
    return ""

def clean_text(text):
    return str(text) if text is not None else ""

def clean_gemini_json(text):
    if not text: return ""
    text = str(text).strip()
    text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'```$', '', text, flags=re.MULTILINE)
    return text.strip()

# ==============================
# PROCESAMIENTO DE PDFS
# ==============================
def extract_text_from_pdfs(uploaded_files):
    combined_text = ""
    if not uploaded_files: return combined_text
    for file in uploaded_files:
        try:
            file_bytes = file.getvalue()
            pdf_document = fitz.open(stream=file_bytes, filetype="pdf")
            combined_text += f"\n\n--- INICIO DOCUMENTO: {file.name} ---\n\n"
            for page in pdf_document: combined_text += page.get_text() + "\n"
            pdf_document.close()
            combined_text += f"\n--- FIN DOCUMENTO: {file.name} ---\n"
        except Exception as e:
            print(f"Error al procesar PDF '{file.name}': {e}")
            combined_text += f"\n\n--- ERROR AL PROCESAR: {file.name} ---\n"
    return combined_text

# ==============================
# RAG: RECUPERACIÓN DE INFORMACIÓN
# ==============================
def get_relevant_info(db, question, selected_files, max_chars=150000):
    all_text = ""
    selected_files_set = set(selected_files) if isinstance(selected_files, (list, set)) else set()
    
    for pres in db:
        if len(all_text) > max_chars:
            all_text += f"\n\n[ALERTA: Contexto truncado por límite de seguridad ({max_chars} chars)...]"
            break 

        doc_name = pres.get('nombre_archivo')
        if doc_name and doc_name in selected_files_set:
            try:
                titulo = pres.get('titulo_estudio', doc_name)
                ano = pres.get('marca')
                citation_header = f"{titulo} - {ano}" if ano else titulo

                doc_content = f"Documento: {citation_header}\n"
                
                for grupo in pres.get("grupos", []):
                    contenido = str(grupo.get('contenido_texto', ''))
                    metadatos = json.dumps(grupo.get('metadatos', {}), ensure_ascii=False) if grupo.get('metadatos') else ""
                    
                    if contenido: doc_content += f"  - {contenido}\n";
                    if metadatos: doc_content += f"  (Contexto: {metadatos})\n"
                        
                doc_content += "\n---\n\n"
                
                if len(all_text) + len(doc_content) > max_chars:
                    remaining = max_chars - len(all_text)
                    all_text += doc_content[:remaining]
                    break
                else:
                    all_text += doc_content

            except Exception as e: 
                print(f"Error proc doc '{doc_name}': {e}")
    return all_text

def build_rag_context(query, documents, max_chars=100000):
    if not query or not documents: return ""
    query_terms = set(normalize_text(query).split())
    stopwords = get_stopwords()
    keywords = [w for w in query_terms if w not in stopwords and len(w) > 3]
    if not keywords: keywords = query_terms 

    scored_chunks = []
    for doc in documents:
        source = doc.get('source', 'Desconocido')
        content = doc.get('content', '')
        paragraphs = content.split('\n\n') 
        for i, para in enumerate(paragraphs):
            if len(para) < 50: continue 
            para_norm = normalize_text(para)
            score = sum(1 for kw in keywords if kw in para_norm)
            if i == 0: score += 0.5 
            if score > 0:
                scored_chunks.append({'score': score, 'source': source, 'text': para})

    scored_chunks.sort(key=lambda x: x['score'], reverse=True)
    final_context = ""
    current_chars = 0
    if not scored_chunks: return "" 
    for chunk in scored_chunks:
        if current_chars + len(chunk['text']) > max_chars: break
        final_context += f"\n[Fuente: {chunk['source']}]\n{chunk['text']}\n..."
        current_chars += len(chunk['text'])
    return final_context

# ==============================
# RESET WORKFLOWS
# ==============================
def reset_report_workflow():
    for k in ["report", "last_question"]: st.session_state.mode_state.pop(k, None)

def reset_chat_workflow():
    st.session_state.mode_state.pop("chat_history", None)
    if "mode_state" in st.session_state and "chat_suggestions" in st.session_state.mode_state:
        del st.session_state.mode_state["chat_suggestions"]

def reset_transcript_chat_workflow():
    st.session_state.mode_state.pop("transcript_chat_history", None)

def reset_etnochat_chat_workflow():
    st.session_state.mode_state.pop("etno_chat_history", None)

# ==============================
# VALIDACIÓN DE SESIÓN
# ==============================
def validate_session_integrity():
    if not st.session_state.get("logged_in"): return
    current_time = time.time()
    if 'last_session_check' not in st.session_state or (current_time - st.session_state.last_session_check > 300):
        try:
            from services.supabase_db import supabase 
            uid = st.session_state.user_id
            res = supabase.table("users").select("active_session_id").eq("id", uid).single().execute()
            if res.data and res.data.get('active_session_id') != st.session_state.session_id:
                st.error("⚠️ Tu sesión ha sido cerrada desde otro dispositivo.")
                time.sleep(2)
                st.session_state.clear()
                st.rerun()
            st.session_state.last_session_check = current_time
        except Exception as e:
            pass

# =========================================================
# LÓGICA AVANZADA DE CITAS: TOOLTIPS GRUPALES + FUENTES ÚNICAS
# =========================================================
def process_text_with_tooltips(text):
    """
    1. Lee las fuentes generadas por la IA.
    2. Convierte grupos de citas [8, 40] en tooltips individuales.
    3. Genera un pie de página limpio con archivos únicos (sin repetir).
    """
    
    # 1. Separar cuerpo y sección de fuentes
    split_patterns = [r"\n\*\*Fuentes:?\*\*", r"\n## Fuentes", r"\n### Fuentes", r"\nFuentes:"]
    body = text
    sources_raw = ""
    
    for pattern in split_patterns:
        parts = re.split(pattern, text, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) > 1:
            body = parts[0]
            sources_raw = parts[1]
            break
            
    if not sources_raw: return text

    # 2. Mapear IDs a {Archivo, Contexto}
    source_map = {}
    matches = re.findall(r"\[(\d+)\]\s*(.*?)(?:\s*\|\|\|\s*(.*))?$", sources_raw, re.MULTILINE)
    
    for num, filename, context in matches:
        source_map[num] = {
            "file": filename.strip(),
            "context": context.strip() if context else "Fuente del documento."
        }

    # 3. Reemplazar citas en el cuerpo (Maneja [1] y [1, 2, 3])
    def replace_citation_group(match):
        # match.group(1) captura lo de adentro: "8, 40" o "1"
        content_inside = match.group(1)
        
        # Dividimos por coma para sacar cada número individualmente
        ids = [x.strip() for x in content_inside.split(',')]
        
        html_parts = []
        for citation_num in ids:
            data = source_map.get(citation_num)
            
            if data:
                # Creamos el tooltip para este número específico
                tooltip = f'''
                <span class="citation-ref">
                    {citation_num}
                    <span class="tooltip-text">
                        <span class="tooltip-source-title">{data['file']}</span>
                        {data['context']}
                    </span>
                </span>
                '''
                html_parts.append(tooltip)
            else:
                # Si no hay data (error de la IA), dejamos el número plano
                html_parts.append(citation_num)
        
        # Reconstruimos el grupo con comas: [1, 2] -> [<span..>1</span>, <span..>2</span>]
        return f"[{', '.join(html_parts)}]"
    
    # Regex ajustada: Busca corchetes que contengan dígitos, comas o espacios
    enriched_body = re.sub(r"\[([\d,\s]+)\]", replace_citation_group, body)
    
    # 4. RE-GENERAR PIE DE PÁGINA LIMPIO (Archivos Únicos)
    clean_footer = "\n\n---\n**Fuentes Consultadas:**\n"
    
    # Usamos un Set para eliminar duplicados de nombres de archivo
    unique_files = set()
    for info in source_map.values():
        fname = info['file'].replace('"', '').replace("Documento:", "").strip()
        unique_files.add(fname)
        
    # Listamos los archivos únicos ordenados alfabéticamente
    for fname in sorted(list(unique_files)):
        clean_footer += f"* 📄 {fname}\n"

    return enriched_body + clean_footer
