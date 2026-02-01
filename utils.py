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
# CONFIGURACIÓN
# ==============================
@st.cache_resource
def get_stopwords():
    return {'de', 'la', 'el', 'en', 'y', 'a', 'los', 'del', 'las', 'un', 'para', 'con', 'no', 'una', 'su', 'que', 'se', 'por', 'es', 'más', 'lo', 'pero', 'me', 'mi', 'al', 'le', 'si', 'este', 'esta', 'son', 'sobre'}

@contextmanager
def render_process_status(label="Procesando...", expanded=True):
    status = st.status(label, expanded=expanded)
    try: yield status
    except Exception as e: raise e

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
def clean_gemini_json(text): return re.sub(r'^```json\s*', '', re.sub(r'^```\s*', '', text, flags=re.MULTILINE), flags=re.MULTILINE).strip()

# ==============================
# LECTURA PDF
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
# RAG CONTEXT
# ==============================
def get_relevant_info(db, question, selected_files, max_chars=150000):
    if not selected_files: return ""
    selected_set = set(selected_files)
    candidate_chunks = []
    for pres in db:
        if pres.get('nombre_archivo') in selected_set:
            try:
                doc_name = pres.get('nombre_archivo')
                for i, g in enumerate(pres.get("grupos", [])):
                    txt = str(g.get('contenido_texto', ''))
                    if txt and len(txt) > 20:
                        chunk_meta = f"--- DOC: {doc_name} | SECCIÓN: {i+1} ---\n" 
                        candidate_chunks.append(f"{chunk_meta}{txt}\n\n")
            except: pass
    return "".join(candidate_chunks)[:max_chars]

def validate_session_integrity(): pass 

# =========================================================
# LÓGICA DE CITAS V.ROBUSTA (Multi-Pass Parsing)
# =========================================================
def process_text_with_tooltips(text):
    if not text: return ""

    try:
        source_map = {}
        # Normalizar comillas
        text = text.replace('“', '"').replace('”', '"')
        
        # ---------------------------------------------------------
        # 1. EXTRACCIÓN Y LIMPIEZA DEL BLOQUE FINAL
        # ---------------------------------------------------------
        # Estrategia: Buscar donde empieza la lista de referencias y procesarla aparte.
        # Esto evita problemas con regex gigantes que fallan con saltos de línea.
        
        # Patrones que indican inicio del bloque de metadatos
        split_patterns = [
            r'\[1\]\s*\|\|\|',  # Formato estándar
            r'\n\s*Referencias:\s*\n', 
            r'\n\s*Fuentes:\s*\n',
            r'\n\s*BLOQUE DE METADATA'
        ]
        
        metadata_text = ""
        main_text = text
        
        for pattern in split_patterns:
            split_match = re.search(pattern, text, re.IGNORECASE)
            if split_match:
                # Separamos el texto principal de la metadata
                idx = split_match.start()
                # Si el match es [1] |||, queremos incluirlo en la metadata, no cortarlo antes
                if "|||" in pattern:
                     metadata_text = text[idx:]
                     main_text = text[:idx]
                else:
                     metadata_text = text[split_match.end():]
                     main_text = text[:idx]
                break
        
        # Si no encontramos separador claro, intentamos buscar línea por línea al final
        if not metadata_text:
            # Fallback: Regex línea por línea para capturar definiciones dispersas
            pass 

        # ---------------------------------------------------------
        # 2. PARSEO DE LA METADATA (Línea por línea es más seguro)
        # ---------------------------------------------------------
        # Procesamos metadata_text para llenar source_map
        # Formatos soportados:
        # A. [1] ||| Archivo ||| Cita
        # B. [1] ||| Cita (Archivo inferido)
        # C. [1] Archivo: Cita
        
        # Limpiamos el texto principal de residuos si quedaron
        if metadata_text:
            text = main_text # Actualizamos el texto visible
            
            # Normalizamos saltos de línea para iterar
            lines = metadata_text.split('\n')
            current_id = None
            
            for line in lines:
                line = line.strip()
                if not line: continue
                
                # Detectar ID [N]
                id_match = re.match(r'^\[(\d+)\]', line)
                if id_match:
                    current_id = id_match.group(1)
                    content = line[id_match.end():].strip()
                    
                    # Intentar separar por |||
                    parts = content.split('|||')
                    parts = [p.strip() for p in parts if p.strip()]
                    
                    filename = "Fuente del Repositorio"
                    quote = ""
                    
                    if len(parts) >= 2:
                        filename = parts[0]
                        quote = parts[1]
                    elif len(parts) == 1:
                        # Heurística: Si termina en pdf es archivo, si no es cita
                        if '.pdf' in parts[0].lower(): filename = parts[0]
                        else: quote = parts[0]
                    
                    # Limpieza final de la cita
                    quote = re.sub(r'^(?:Cita:|Contexto:|Quote:|Evidencia:)\s*', '', quote, flags=re.IGNORECASE).strip('"')
                    
                    source_map[current_id] = {
                        "file": html.escape(filename),
                        "quote": html.escape(quote[:400]) + "..."
                    }

        # ---------------------------------------------------------
        # 3. RENDERIZADO EN EL TEXTO
        # ---------------------------------------------------------

        # Helper HTML Tooltip
        def create_tooltip(label_text, tooltip_title, tooltip_body, color_style="background-color:#f0f2f6; color:#444; border:1px solid #ccc;"):
            if not tooltip_body: tooltip_body = "<em>(Detalle no disponible)</em>"
            return (
                f'&nbsp;<span class="tooltip-container">'
                f'<span class="citation-number" style="{color_style} font-weight:bold; cursor:help;">{label_text}</span>'
                f'<span class="tooltip-text" style="width:350px;">'
                f'<strong style="color:#ffd700;">📂 {tooltip_title}</strong><br/>'
                f'<div style="margin-top:6px; padding-top:6px; border-top:1px solid #555; font-size:0.9em; line-height:1.3; color:#eee;">'
                f'{tooltip_body}'
                f'</div>'
                f'</span></span>'
            )

        # A. Citas Numéricas [N]
        def replace_numeric(match):
            cid = match.group(1)
            if cid in source_map:
                data = source_map[cid]
                return create_tooltip(f"[{cid}]", data["file"], data["quote"])
            else:
                # FALLBACK INTELIGENTE: Si no está en el mapa, mostramos un tooltip genérico
                # en lugar de un texto plano roto.
                return create_tooltip(f"[{cid}]?", "Referencia faltante", "La IA citó este documento pero no proveyó el detalle técnico al final.")

        text = re.sub(r'\[(\d+)\]', replace_numeric, text)

        # B. Video
        text = re.sub(
            r'\[Video:\s*([0-9:-]+)\]', 
            r'&nbsp;<span class="citation-number" style="background-color:#ffebee; color:#c62828; border:1px solid #ffcdd2; font-size:0.85em; font-weight:bold;">🎬 \1</span>', 
            text, flags=re.IGNORECASE
        )

        # C. Imagen
        text = re.sub(
            r'\[Imagen\]', 
            r'&nbsp;<span class="citation-number" style="background-color:#e0f7fa; color:#006064; border:1px solid #b2ebf2; font-size:0.85em; font-weight:bold;">🖼️ Visual</span>', 
            text, flags=re.IGNORECASE
        )

        # D. Limpieza final de basura visual
        text = re.sub(r'(?:\n|^)\s*(?:\*\*|##)?\s*Fuentes(?: Verificadas| Consultadas| Bibliografía)?\s*:?\s*(?:\*\*|##)?\s*$', '', text, flags=re.IGNORECASE | re.MULTILINE)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text

    except Exception as e:
        print(f"Error Tooltips: {e}")
        return text

def reset_report_workflow(): pass
def reset_chat_workflow(): pass
