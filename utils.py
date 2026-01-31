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
    try:
        status = st.status(label, expanded=expanded)
        yield status
    except:
        yield st.empty()

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
# MOTOR DE BÚSQUEDA INTELIGENTE (NUEVO)
# ==============================
def expand_search_query(query):
    """
    Usa IA para encontrar sinónimos y conceptos relacionados.
    Ej: "Refresco" -> ["Refresco", "Gaseosa", "Bebida Carbonatada", "Soda"]
    """
    if not query or len(query.split()) > 10: return [query] # No expandir si es una frase muy larga
    
    try:
        # Importación tardía para evitar ciclos
        from services.gemini_api import call_gemini_api
        
        prompt = (
            f"Actúa como un motor de búsqueda experto en investigación de mercados. "
            f"Para el término de búsqueda: '{query}', genera 3 palabras clave alternativas, sinónimos técnicos o conceptos estrechamente relacionados. "
            f"Devuelve SOLAMENTE las palabras separadas por coma, sin numeración ni explicaciones."
        )
        
        # Llamada rápida (sin stream)
        response = call_gemini_api(prompt, generation_config_override={"max_output_tokens": 100})
        
        if response:
            # Limpiar respuesta
            expanded = [w.strip() for w in response.split(',') if w.strip()]
            # Retornar original + expandidos (únicos)
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
# RAG: RECUPERACIÓN DE CONTEXTO (OPTIMIZADO V2)
# ==============================
def get_relevant_info(db, question, selected_files, max_chars=150000):
    """
    Recupera información. Si el contenido total excede max_chars,
    aplica búsqueda semántica expandida para priorizar los mejores fragmentos.
    """
    if not selected_files: return ""
    selected_set = set(selected_files)
    
    # 1. Recolectar todos los fragmentos elegibles
    candidate_chunks = []
    total_len = 0
    
    for pres in db:
        if pres.get('nombre_archivo') in selected_set:
            try:
                doc_name = pres.get('nombre_archivo')
                doc_title = pres.get('titulo_estudio', doc_name)
                
                # Cada grupo/diapositiva es un chunk potencial
                for i, g in enumerate(pres.get("grupos", [])):
                    txt = str(g.get('contenido_texto', ''))
                    if txt and len(txt) > 20: # Ignorar textos vacíos o muy cortos
                        chunk_meta = f"--- DOC: {doc_name} | SECCIÓN: {i+1} ---\nMETA: {doc_title}\n"
                        full_chunk = f"{chunk_meta} - {txt}\n\n"
                        
                        candidate_chunks.append({
                            "text": full_chunk,
                            "raw_content": txt.lower(),
                            "len": len(full_chunk),
                            "original_idx": len(candidate_chunks) # Para mantener orden si no filtramos
                        })
                        total_len += len(full_chunk)
            except: pass

    # 2. Decisión de Estrategia
    # Si todo cabe, devolvemos todo (mejor para resúmenes generales)
    if total_len <= max_chars:
        return "".join([c["text"] for c in candidate_chunks])

    # 3. Estrategia "Smart Filter" (Si excede límite)
    # Expandimos la query para buscar mejor
    print(f"Content overflow ({total_len} chars). Activating Smart Search for: {question}")
    search_terms = expand_search_query(question)
    search_terms = [normalize_text(t) for t in search_terms] # Normalizar para búsqueda
    
    # Puntuar chunks
    for chunk in candidate_chunks:
        score = 0
        norm_content = normalize_text(chunk["raw_content"])
        
        for term in search_terms:
            if term in norm_content:
                # Puntos extra si es el término original, menos si es sinónimo
                weight = 3 if term == normalize_text(question) else 1
                score += (norm_content.count(term) * weight)
        
        chunk["score"] = score

    # Ordenar por relevancia
    # Priorizamos los que tienen score > 0, luego rellenamos con el resto si sobra espacio
    scored_chunks = sorted(candidate_chunks, key=lambda x: x["score"], reverse=True)
    
    final_output = ""
    current_chars = 0
    
    # Seleccionar los mejores hasta llenar el cupo
    chunks_to_include = []
    for chunk in scored_chunks:
        if current_chars + chunk["len"] <= max_chars:
            chunks_to_include.append(chunk)
            current_chars += chunk["len"]
        else:
            # Si ya tenemos buen contenido relevante, paramos.
            # Si aún tenemos poco texto, seguimos buscando chunks pequeños.
            if current_chars > max_chars * 0.8: break 
    
    # 4. Reordenar cronológicamente (Importante para coherencia)
    # Volvemos a ordenar por índice original para que el texto tenga sentido narrativo
    chunks_to_include.sort(key=lambda x: x["original_idx"])
    
    return "".join([c["text"] for c in chunks_to_include])


def validate_session_integrity():
    pass 

# =========================================================
# LÓGICA DE CITAS V6 (MANTENIDA)
# =========================================================
def process_text_with_tooltips(text):
    if not text: return ""

    try:
        source_map = {}
        
        text = text.replace('“', '"').replace('”', '"')
        
        def harvest_metadata(match):
            cid = match.group(1)
            fname = match.group(2).strip()
            raw_context = match.group(3).strip()
            
            clean_context = re.sub(r'^(?:Cita:|Contexto:|Quote:)\s*', '', raw_context, flags=re.IGNORECASE).strip('"').strip("'")
            
            source_map[cid] = {
                "file": html.escape(fname),
                "context": html.escape(clean_context[:400]) + ("..." if len(clean_context)>400 else "")
            }
            return "" 

        pattern_metadata = r'\[(\d+)\]\s*([^\[\]\|\n]+?)\s*\|\|\|\s*(.+?)(?=\n\[\d+\]|$|\n\n)'
        text = re.sub(pattern_metadata, harvest_metadata, text, flags=re.DOTALL)

        text = re.sub(r'\(\s*(?:Contexto|Cita|Quote|Evidencia)\s*:.*?\)', '', text, flags=re.IGNORECASE | re.DOTALL)
        
        text = re.sub(r'(?:\n|^)\s*(?:\*\*|##)?\s*Fuentes(?: Verificadas| Consultadas)?\s*:?\s*(?:\*\*|##)?\s*$', '', text, flags=re.IGNORECASE | re.MULTILINE)
        text = re.sub(r'\n{3,}', '\n\n', text)

        text = re.sub(r'(?<=\d)\]\s*\[(?=\d)', ', ', text)
        
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
                    html_out.append(f'<span class="citation-number" style="cursor:default; border:none;">[{cid}]</span>')
            
            return f" {''.join(html_out)} "

        enriched_body = re.sub(r"\[\s*([\d,\s]+)\s*\]", replace_citation_group, text)
        
        footer = ""
        if source_map:
            files = sorted(list(set(v['file'] for v in source_map.values())))
            if files:
                footer = "\n\n<div style='margin-top:20px; padding-top:10px; border-top:1px solid #eee;'>"
                footer += "<p style='font-size:0.85em; color:#666; font-weight:bold; margin-bottom:5px;'>📚 Fuentes Consultadas:</p>"
                footer += "<ul style='font-size:0.8em; color:#666; margin-top:0; padding-left:20px;'>"
                for f in files: 
                    footer += f"<li style='margin-bottom:2px;'>{f}</li>"
                footer += "</ul></div>"

        return enriched_body + footer

    except Exception as e:
        print(f"Error Tooltips: {e}")
        return text

def reset_report_workflow(): pass
def reset_chat_workflow(): pass
def reset_transcript_chat_workflow(): pass
def reset_etnochat_chat_workflow(): pass
