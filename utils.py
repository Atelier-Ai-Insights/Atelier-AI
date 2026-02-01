import streamlit as st
import unicodedata
import json
import re
import time
import html
from contextlib import contextmanager

try:
    import fitz
except ImportError:
    fitz = None

# ==============================
# CONFIGURACIÓN BÁSICA
# ==============================
@st.cache_resource
def get_stopwords():
    return {
        'de', 'la', 'el', 'en', 'y', 'a', 'los', 'del', 'las', 'un', 'para', 'con', 'no', 'una', 'su', 'que', 
        'se', 'por', 'es', 'más', 'lo', 'pero', 'me', 'mi', 'al', 'le', 'si', 'este', 'esta', 'son', 'sobre',
        'the', 'and', 'to', 'of', 'in', 'is', 'that', 'for', 'it', 'as', 'was', 'with', 'on', 'at', 'by'
    }

@contextmanager
def render_process_status(label="Procesando...", expanded=True):
    status = st.status(label, expanded=expanded)
    try:
        yield status
    except Exception as e:
        raise e

def normalize_text(text):
    if not text: return ""
    try: 
        text = str(text).lower()
        normalized = unicodedata.normalize("NFD", text)
        return "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    except: return str(text).lower()

def extract_brand(filename):
    if not filename: return ""
    if "In-ATL_" in str(filename):
        try: return str(filename).split("In-ATL_")[1].rsplit(".", 1)[0]
        except: pass
    return str(filename)

def clean_text(text): return str(text) if text else ""

def clean_gemini_json(text): 
    text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
    return text.strip()

# ==============================
# MOTOR DE BÚSQUEDA INTELIGENTE
# ==============================
def expand_search_query(query):
    if not query or len(query.split()) > 10: return [query]
    try:
        from services.gemini_api import call_gemini_api
        prompt = (
            f"Actúa como un motor de búsqueda experto en investigación de mercados. "
            f"Para el término de búsqueda: '{query}', genera 3 palabras clave alternativas, sinónimos técnicos o conceptos estrechamente relacionados. "
            f"Devuelve SOLAMENTE las palabras separadas por coma, sin numeración ni explicaciones."
        )
        response = call_gemini_api(prompt, generation_config_override={"max_output_tokens": 100})
        if response:
            expanded = [w.strip() for w in response.split(',') if w.strip()]
            return list(dict.fromkeys([query] + expanded))
    except Exception as e:
        print(f"Error expanding query: {e}")
    return [query]

# ==============================
# LECTURA DE PDFS
# ==============================
def extract_text_from_pdfs(uploaded_files):
    combined_text = ""
    if not uploaded_files or fitz is None: return combined_text
    for file in uploaded_files:
        try:
            with fitz.open(stream=file.getvalue(), filetype="pdf") as doc:
                combined_text += f"\n\n--- DOC: {file.name} ---\n"
                for page in doc: combined_text += page.get_text() + "\n"
        except: pass
    return combined_text

# ==============================
# RAG: RECUPERACIÓN DE CONTEXTO
# ==============================
def get_relevant_info(db, question, selected_files, max_chars=150000):
    if not selected_files: return ""
    selected_set = set(selected_files)
    
    candidate_chunks = []
    total_len = 0
    
    for pres in db:
        if pres.get('nombre_archivo') in selected_set:
            try:
                doc_name = pres.get('nombre_archivo')
                doc_title = pres.get('titulo_estudio', doc_name)
                for i, g in enumerate(pres.get("grupos", [])):
                    txt = str(g.get('contenido_texto', ''))
                    if txt and len(txt) > 20:
                        # Simplificamos el META para ahorrar tokens y confundir menos a la IA
                        chunk_meta = f"--- DOC: {doc_name} | SECCIÓN: {i+1} ---\n" 
                        full_chunk = f"{chunk_meta}{txt}\n\n"
                        candidate_chunks.append({
                            "text": full_chunk,
                            "raw_content": txt.lower(),
                            "len": len(full_chunk),
                            "original_idx": len(candidate_chunks)
                        })
                        total_len += len(full_chunk)
            except: pass

    if total_len <= max_chars:
        return "".join([c["text"] for c in candidate_chunks])

    print(f"Content overflow ({total_len} chars). Activating Smart Search for: {question}")
    search_terms = expand_search_query(question)
    search_terms = [normalize_text(t) for t in search_terms]
    
    for chunk in candidate_chunks:
        score = 0
        norm_content = normalize_text(chunk["raw_content"])
        for term in search_terms:
            if term in norm_content:
                weight = 3 if term == normalize_text(question) else 1
                score += (norm_content.count(term) * weight)
        chunk["score"] = score

    scored_chunks = sorted(candidate_chunks, key=lambda x: x["score"], reverse=True)
    
    chunks_to_include = []
    current_chars = 0
    for chunk in scored_chunks:
        if current_chars + chunk["len"] <= max_chars:
            chunks_to_include.append(chunk)
            current_chars += chunk["len"]
        else:
            if current_chars > max_chars * 0.8: break 
    
    chunks_to_include.sort(key=lambda x: x["original_idx"])
    return "".join([c["text"] for c in chunks_to_include])


def validate_session_integrity():
    pass 

# =========================================================
# LÓGICA DE CITAS V8 (FIX FINAL DE FORMATO Y ESTABILIDAD)
# =========================================================
def process_text_with_tooltips(text):
    if not text: return ""

    try:
        source_map = {}
        # Normalizar comillas
        text = text.replace('“', '"').replace('”', '"')
        
        # 1. COSECHA DE METADATA (Estándar [1] File ||| Context)
        # Usamos una regex más robusta que no se rompa con saltos de línea extraños
        def harvest_metadata(match):
            try:
                cid = match.group(1)
                fname = match.group(2).strip()
                raw_context = match.group(3).strip()
                clean_context = re.sub(r'^(?:Cita:|Contexto:|Quote:)\s*', '', raw_context, flags=re.IGNORECASE).strip('"').strip("'")
                
                source_map[cid] = {
                    "file": html.escape(fname),
                    "context": html.escape(clean_context[:300]) + "..."
                }
            except: pass
            return "" # Borrar del texto visible

        # Patrón estándar de footer
        pattern_metadata = r'\[(\d+)\]\s*([^\[\]\|\n]+?)\s*\|\|\|\s*(.+?)(?=\n\[\d+\]|$|\n\n)'
        text = re.sub(pattern_metadata, harvest_metadata, text, flags=re.DOTALL)
        
        # 2. LIMPIEZA DE "FUGAS" [DOC:...] 
        # Esta regex atrapa el formato crudo que está saliendo en tu pantalla
        # y lo convierte en un bonito icono de carpeta [📂] con tooltip.
        def clean_raw_doc_leaks(match):
            try:
                # Capturamos todo lo que haya dentro de DOC: ... |
                content_inside = match.group(1) 
                
                # Intentamos separar Nombre y Sección si existe el pipe |
                if "|" in content_inside:
                    parts = content_inside.split("|")
                    fname = parts[0].replace("DOC:", "").strip()
                    section_info = parts[1].strip()
                else:
                    fname = content_inside.replace("DOC:", "").strip()
                    section_info = "Referencia general"

                # Tooltip visual
                return (
                    f'&nbsp;<span class="tooltip-container">'
                    f'<span class="citation-number" style="background-color:#f0f2f6; color:#444; border:1px solid #ccc;">📂</span>'
                    f'<span class="tooltip-text">'
                    f'<strong>Fuente:</strong> {html.escape(fname)}<br/>'
                    f'<span style="font-size:0.9em; opacity:0.9;">{html.escape(section_info)}</span>'
                    f'</span></span>'
                )
            except:
                return "" # Si falla, borrar la fuga

        # Regex muy permisiva para atrapar cualquier variante de [DOC: ...]
        # Busca [DOC: seguido de cualquier cosa que no sea ] hasta encontrar ]
        text = re.sub(r'\[(DOC:.+?)\]', clean_raw_doc_leaks, text, flags=re.IGNORECASE)

        # 3. LIMPIEZA GENERAL
        # Borrar paréntesis repetitivos tipo (Contexto: ...)
        text = re.sub(r'\(\s*(?:Contexto|Cita|Quote|Evidencia)\s*:.*?\)', '', text, flags=re.IGNORECASE | re.DOTALL)
        # Borrar títulos de footer residuales
        text = re.sub(r'(?:\n|^)\s*(?:\*\*|##)?\s*Fuentes(?: Verificadas| Consultadas)?\s*:?\s*(?:\*\*|##)?\s*$', '', text, flags=re.IGNORECASE | re.MULTILINE)
        
        # 4. RENDERIZADO DE CITAS NUMÉRICAS [1]
        # (Solo si sobrevivieron al proceso de cosecha)
        def replace_citation_group(match):
            content = match.group(1)
            ids = [x.strip() for x in re.findall(r'\d+', content)]
            html_out = []
            for cid in ids:
                data = source_map.get(cid)
                if data:
                    tooltip = (
                        f'<span class="tooltip-container">'
                        f'<span class="citation-number">[{cid}]</span>'
                        f'<span class="tooltip-text">'
                        f'<strong>📂 {data["file"]}</strong><br/>'
                        f'<span style="font-size:0.9em; opacity:0.9;">"{data["context"]}"</span>'
                        f'</span></span>'
                    )
                    html_out.append(tooltip)
                else:
                    # Si hay un número [1] pero no hay metadata (porque la IA falló al final),
                    # lo mostramos gris para que no parezca un error
                    html_out.append(f'<span class="citation-number" style="cursor:default; border:1px solid #eee; color:#aaa;">[{cid}]</span>')
            return f" {''.join(html_out)} "

        # Reemplazar [1, 2]
        enriched_body = re.sub(r"\[\s*([\d,\s]+)\s*\]", replace_citation_group, text)
        
        # 5. FOOTER DE SEGURIDAD
        # Si logramos extraer fuentes, las mostramos abajo
        footer = ""
        unique_files = sorted(list(set(v['file'] for v in source_map.values())))
        if unique_files:
            footer = "\n\n<div style='margin-top:20px; padding-top:10px; border-top:1px solid #eee;'>"
            footer += "<p style='font-size:0.85em; color:#666; font-weight:bold; margin-bottom:5px;'>📚 Fuentes Consultadas:</p>"
            footer += "<ul style='font-size:0.8em; color:#666; margin-top:0; padding-left:20px;'>"
            for f in unique_files: footer += f"<li style='margin-bottom:2px;'>{f}</li>"
            footer += "</ul></div>"

        return enriched_body + footer

    except Exception as e:
        # Si algo falla catastróficamente, devolvemos el texto original
        # pero intentamos limpiar al menos las etiquetas [DOC] para que sea legible
        print(f"Error Tooltips: {e}")
        try:
            return re.sub(r'\[DOC:.+?\]', '', text)
        except:
            return text

def reset_report_workflow(): pass
def reset_chat_workflow(): pass
def reset_transcript_chat_workflow(): pass
def reset_etnochat_chat_workflow(): pass
