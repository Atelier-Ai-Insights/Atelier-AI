from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_AUTO_SIZE
import io
import re

def crear_ppt_desde_json(data_json, image_stream=None):
    """
    Genera un PowerPoint con formas NATIVAS y EDITABLES.
    Incluye detección INTELIGENTE de plantillas para evitar listas genéricas.
    """
    
    # 1. Cargar Plantilla Base
    try:
        prs = Presentation("Plantilla_PPT_ATL.pptx")
    except:
        prs = Presentation()

    slide_layout = prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[-1]
    slide = prs.slides.add_slide(slide_layout)

    # 2. Configurar Título
    titulo_texto = data_json.get('titulo_diapositiva', 'Resumen Estratégico')
    
    if slide.shapes.title:
        slide.shapes.title.text = titulo_texto
    else:
        title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.2), Inches(9), Inches(1))
        tf = title_box.text_frame
        tf.text = titulo_texto
        tf.paragraphs[0].font.size = Pt(24)
        tf.paragraphs[0].font.bold = True
        tf.paragraphs[0].alignment = PP_ALIGN.CENTER

    # =========================================================================
    # 3. ROUTER INTELIGENTE (DETECCIÓN ROBUSTA)
    # =========================================================================
    
    # A. Normalización
    template_type = data_json.get('template_type', '').lower()
    keys_str = " ".join(data_json.keys()).lower() # Para buscar pistas en las claves
    
    # B. Lógica de Decisión (Prioridad: Nombre explícito -> Pistas en claves)
    
    # --- 1. MATRIZ 2x2 ---
    if "matriz" in template_type or "2x2" in template_type or "cuadrante" in keys_str:
        _dibujar_matriz_nativa(slide, data_json)

    # --- 2. FODA / DOFA ---
    elif "foda" in template_type or "swot" in template_type or "dofa" in template_type or ("fortalezas" in keys_str and "amenazas" in keys_str):
        _dibujar_foda_nativo(slide, data_json)

    # --- 3. EMBUDO ---
    elif "embudo" in template_type or "funnel" in template_type or "conversion" in keys_str:
        _dibujar_embudo_nativo(slide, data_json)

    # --- 4. CUSTOMER JOURNEY (Tabla) ---
    elif "journey" in template_type or "viaje" in template_type or "map" in template_type or "etapa 1" in keys_str:
        _dibujar_journey_nativo(slide, data_json)

    # --- 5. BUYER PERSONA (Tarjeta) ---
    elif "persona" in template_type or "buyer" in template_type or "perfil" in template_type or ("demografia" in keys_str and "frustraciones" in keys_str):
        _dibujar_buyer_persona_nativo(slide, data_json)

    # --- 6. MAPA EMPATÍA (Dice/Piensa) ---
    elif "empatia" in template_type or "empathy" in template_type or ("dice" in keys_str and "piensa" in keys_str):
        _dibujar_mapa_empatia_nativo(slide, data_json)

    # --- 7. PROPUESTA DE VALOR (Canvas) ---
    elif "valor" in template_type or "value" in template_type or ("alegrias" in keys_str and "dolores" in keys_str and "trabajos" in keys_str):
        _dibujar_propuesta_valor_nativo(slide, data_json)

    # --- 8. FALLBACK (Lista Genérica) ---
    else:
        _dibujar_lista_generica(slide, data_json)


    # 4. Agregar Conclusión (Común a todos)
    if 'conclusion_clave' in data_json:
        bg = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.5), Inches(6.6), Inches(9), Inches(0.8))
        bg.fill.solid()
        bg.fill.fore_color.rgb = RGBColor(245, 245, 245)
        bg.line.color.rgb = RGBColor(220, 220, 220)
        
        tf = bg.text_frame
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE 
        
        tf.text = "💡 " + data_json['conclusion_clave']
        p = tf.paragraphs[0]
        p.font.color.rgb = RGBColor(50, 50, 50)
        p.alignment = PP_ALIGN.LEFT

    # 5. Guardar y Retornar
    output = io.BytesIO()
    prs.save(output)
    output.seek(0)
    return output


# ==============================================================================
# FUNCIONES DE DIBUJO (ACTUALIZADAS PARA MAPEO FLEXIBLE)
# ==============================================================================

def _dibujar_buyer_persona_nativo(slide, data):
    """
    Diseño de Tarjeta de Perfil con búsqueda de claves flexible (ej: 'NECESIDADES JTBD').
    """
    # 1. Barra Lateral
    sidebar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.5), Inches(1.2), Inches(2.5), Inches(5.2))
    sidebar.fill.solid(); sidebar.fill.fore_color.rgb = RGBColor(230, 240, 250); sidebar.line.fill.background()

    # Avatar
    avatar = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(1.0), Inches(1.4), Inches(1.5), Inches(1.5))
    avatar.fill.solid(); avatar.fill.fore_color.rgb = RGBColor(180, 200, 220); avatar.line.color.rgb = RGBColor(255, 255, 255)
    
    # Nombre (Busca 'nombre' o 'perfil nombre')
    nombre = _buscar_clave_flexible(data, ['nombre', 'name']) or "Buyer Persona"
    tb_name = slide.shapes.add_textbox(Inches(0.6), Inches(3.0), Inches(2.3), Inches(0.5))
    p = tb_name.text_frame.paragraphs[0]
    p.text = str(nombre).replace("PERFIL NOMBRE", "").strip()
    p.font.bold = True; p.font.size = Pt(14); p.alignment = PP_ALIGN.CENTER; p.font.color.rgb = RGBColor(0, 51, 102)

    # Demográficos / Bio
    bio_text = []
    # Busca 'demografia', 'demograficos', 'perfil'
    demos = _buscar_clave_flexible(data, ['demografia', 'demografico', 'perfil', 'bio'])
    if demos: bio_text.extend(demos if isinstance(demos, list) else [str(demos)])
    
    role = _buscar_clave_flexible(data, ['rol', 'trabajo', 'puesto'])
    if role: bio_text.insert(0, f"Rol: {role}")

    if bio_text:
        tb_bio = slide.shapes.add_textbox(Inches(0.6), Inches(3.5), Inches(2.3), Inches(2.8))
        tf_bio = tb_bio.text_frame; tf_bio.word_wrap = True; tf_bio.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        _llenar_text_frame_flexible(tf_bio, bio_text)

    # 2. Paneles Principales (Derecha)
    # Mapeo robusto basado en tu screenshot
    sections = [
        ("OBJETIVOS / MOTIVACIONES", _buscar_clave_flexible(data, ['metas', 'objetivos', 'deseos', 'motivaciones', 'wants']), (232, 245, 233)),
        ("PUNTOS DE DOLOR / FRUSTRACIONES", _buscar_clave_flexible(data, ['frustraciones', 'dolores', 'pains', 'miedos']), (255, 235, 238)),
        ("NECESIDADES / COMPORTAMIENTO", _buscar_clave_flexible(data, ['necesidades', 'jtbd', 'comportamiento', 'needs']), (255, 248, 225))
    ]
    
    start_y = 1.2; h_panel = 1.6; gap = 0.2
    for i, (title, content, color) in enumerate(sections):
        y_pos = start_y + (i * (h_panel + gap))
        box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(3.2), Inches(y_pos), Inches(6.3), Inches(h_panel))
        box.fill.solid(); box.fill.fore_color.rgb = RGBColor(*color); box.line.color.rgb = RGBColor(200, 200, 200)
        
        tb_title = slide.shapes.add_textbox(Inches(3.3), Inches(y_pos + 0.1), Inches(6.0), Inches(0.3))
        p = tb_title.text_frame.paragraphs[0]; p.text = title; p.font.bold = True; p.font.size = Pt(10); p.font.color.rgb = RGBColor(80, 80, 80)
        
        tb_content = slide.shapes.add_textbox(Inches(3.3), Inches(y_pos + 0.4), Inches(6.0), Inches(h_panel - 0.5))
        tf = tb_content.text_frame; tf.word_wrap = True; tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        _llenar_text_frame_flexible(tf, content)

def _dibujar_mapa_empatia_nativo(slide, data):
    """4 Cuadrantes centrados."""
    center_x, center_y = 5.0, 3.8; w, h = 4.0, 2.2; margin = 0.05
    quads = [
        (center_x - w - margin, center_y - h - margin, "DICE", _buscar_clave_flexible(data, ['dice', 'says']), (227, 242, 253)),
        (center_x + margin, center_y - h - margin, "PIENSA", _buscar_clave_flexible(data, ['piensa', 'thinks']), (243, 229, 245)),
        (center_x - w - margin, center_y + margin, "HACE", _buscar_clave_flexible(data, ['hace', 'does']), (232, 245, 233)),
        (center_x + margin, center_y + margin, "SIENTE", _buscar_clave_flexible(data, ['siente', 'feels']), (255, 243, 224))
    ]
    for left, top, title, content, color in quads:
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(left), Inches(top), Inches(w), Inches(h))
        shape.fill.solid(); shape.fill.fore_color.rgb = RGBColor(*color); shape.line.color.rgb = RGBColor(200, 200, 200)
        
        tb_title = slide.shapes.add_textbox(Inches(left), Inches(top + 0.1), Inches(w), Inches(0.3))
        p = tb_title.text_frame.paragraphs[0]; p.text = f"¿QUÉ {title}?"; p.font.bold = True; p.alignment = PP_ALIGN.CENTER; p.font.size = Pt(11); p.font.color.rgb = RGBColor(80, 80, 80)
        
        tb_cont = slide.shapes.add_textbox(Inches(left + 0.2), Inches(top + 0.4), Inches(w - 0.4), Inches(h - 0.5))
        tf = tb_cont.text_frame; tf.word_wrap = True; tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        _llenar_text_frame_flexible(tf, content)
        
    center_circle = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(center_x - 0.5), Inches(center_y - 0.5), Inches(1), Inches(1))
    center_circle.fill.solid(); center_circle.fill.fore_color.rgb = RGBColor(255, 255, 255); center_circle.line.color.rgb = RGBColor(100, 100, 100)
    p = center_circle.text_frame.paragraphs[0]; p.text = "👤"; p.font.size = Pt(24); p.alignment = PP_ALIGN.CENTER

def _dibujar_propuesta_valor_nativo(slide, data):
    """Canvas Value Proposition."""
    # LADO PRODUCTO
    tb_prod = slide.shapes.add_textbox(Inches(0.5), Inches(1.2), Inches(4.0), Inches(0.3))
    tb_prod.text_frame.text = "MAPA DE VALOR (Producto)"; tb_prod.text_frame.paragraphs[0].font.bold = True
    
    s_prod = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.5), Inches(2.5), Inches(1.5), Inches(3.0))
    s_prod.fill.solid(); s_prod.fill.fore_color.rgb = RGBColor(220, 220, 220)
    _poner_titulo_contenido(slide, s_prod, "Productos", _buscar_clave_flexible(data, ['productos', 'servicios', 'products']))

    s_gain_c = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(2.1), Inches(1.5), Inches(2.4), Inches(1.9))
    s_gain_c.fill.solid(); s_gain_c.fill.fore_color.rgb = RGBColor(200, 230, 201)
    _poner_titulo_contenido(slide, s_gain_c, "Creadores de Alegrías", _buscar_clave_flexible(data, ['creadores', 'alegrias', 'gains']))

    s_pain_r = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(2.1), Inches(3.5), Inches(2.4), Inches(2.0))
    s_pain_r.fill.solid(); s_pain_r.fill.fore_color.rgb = RGBColor(255, 205, 210)
    _poner_titulo_contenido(slide, s_pain_r, "Aliviadores de Dolor", _buscar_clave_flexible(data, ['aliviadores', 'dolor', 'pain']))

    # LADO CLIENTE
    tb_cust = slide.shapes.add_textbox(Inches(5.0), Inches(1.2), Inches(4.0), Inches(0.3))
    p = tb_cust.text_frame.paragraphs[0]; p.text = "PERFIL DEL CLIENTE"; p.font.bold = True; p.alignment = PP_ALIGN.RIGHT

    s_gains = slide.shapes.add_shape(MSO_SHAPE.CHORD, Inches(5.0), Inches(1.5), Inches(4.0), Inches(2.0))
    s_gains.rotation = 180; s_gains.adjustments[0] = 180
    s_gains.fill.solid(); s_gains.fill.fore_color.rgb = RGBColor(200, 230, 201)
    _poner_titulo_contenido_manual(slide, 5.5, 1.6, 3.0, 1.5, "Alegrías (Gains)", _buscar_clave_flexible(data, ['alegrias', 'beneficios', 'gains']))

    s_pains = slide.shapes.add_shape(MSO_SHAPE.CHORD, Inches(5.0), Inches(3.5), Inches(4.0), Inches(2.0))
    s_pains.fill.solid(); s_pains.fill.fore_color.rgb = RGBColor(255, 205, 210)
    _poner_titulo_contenido_manual(slide, 5.5, 3.8, 3.0, 1.5, "Dolores (Pains)", _buscar_clave_flexible(data, ['dolores', 'frustraciones', 'pains', 'miedos']))

    s_jobs = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(8.2), Inches(2.5), Inches(1.3), Inches(2.0))
    s_jobs.fill.solid(); s_jobs.fill.fore_color.rgb = RGBColor(220, 220, 220)
    _poner_titulo_contenido(slide, s_jobs, "Trabajos (Jobs)", _buscar_clave_flexible(data, ['trabajos', 'jobs', 'tareas', 'acciones']))


# ==============================================================================
# HELPERS EXISTENTES Y DE BÚSQUEDA
# ==============================================================================

def _buscar_clave_flexible(data, lista_keywords):
    """
    Busca en el JSON una clave que contenga alguna de las keywords.
    Ej: Si busco 'necesidades', encontrará 'NECESIDADES JTBD'.
    """
    # 1. Búsqueda exacta primero
    for kw in lista_keywords:
        if kw in data: return data[kw]
    
    # 2. Búsqueda parcial (case insensitive)
    for key_json, val in data.items():
        key_clean = key_json.lower()
        for kw in lista_keywords:
            if kw.lower() in key_clean:
                return val
    return None

# (MANTENER LAS OTRAS FUNCIONES SIN CAMBIOS: _dibujar_matriz_nativa, _dibujar_foda_nativo, 
# _dibujar_journey_nativo, _dibujar_embudo_nativo, _dibujar_lista_generica, 
# _llenar_text_frame_flexible, _llenar_text_frame_tabla, _crear_etiqueta)

def _dibujar_matriz_nativa(slide, data):
    center_x, center_y = 5.0, 3.5; width, height = 4.0, 2.2; margin = 0.05
    quads = [
        (center_x - width - margin, center_y - height - margin, (227, 242, 253), 'items_cuadrante_sup_izq'),
        (center_x + margin,         center_y - height - margin, (232, 245, 233), 'items_cuadrante_sup_der'),
        (center_x - width - margin, center_y + margin,          (255, 243, 224), 'items_cuadrante_inf_izq'),
        (center_x + margin,         center_y + margin,          (243, 229, 245), 'items_cuadrante_inf_der')
    ]
    for left, top, color, key in quads:
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
        shape.fill.solid(); shape.fill.fore_color.rgb = RGBColor(*color); shape.line.color.rgb = RGBColor(210, 210, 210)
        tf = shape.text_frame; tf.word_wrap = True; tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        _llenar_text_frame_flexible(tf, data.get(key, []))
    _crear_etiqueta(slide, center_x, center_y - height - 0.3, data.get('eje_y_positivo', 'Alto'), bold=True)
    _crear_etiqueta(slide, center_x, center_y + height + 0.3, data.get('eje_y_negativo', 'Bajo'), bold=True)
    _crear_etiqueta(slide, center_x - width - 0.3, center_y, data.get('eje_x_negativo', 'Bajo'), bold=True, vertical=True)
    _crear_etiqueta(slide, center_x + width + 0.3, center_y, data.get('eje_x_positivo', 'Alto'), bold=True, vertical=True)

def _dibujar_foda_nativo(slide, data):
    center_x, center_y = 5.0, 3.5; width, height = 4.0, 2.2; margin = 0.1
    fortalezas = _buscar_clave_flexible(data, ['fortalezas'])
    debilidades = _buscar_clave_flexible(data, ['debilidades'])
    oportunidades = _buscar_clave_flexible(data, ['oportunidades'])
    amenazas = _buscar_clave_flexible(data, ['amenazas'])
    configs = [
        (center_x - width - margin, center_y - height - margin, (200, 230, 201), 'FORTALEZAS', fortalezas),
        (center_x + margin,         center_y - height - margin, (255, 205, 210), 'DEBILIDADES', debilidades),
        (center_x - width - margin, center_y + margin,          (187, 222, 251), 'OPORTUNIDADES', oportunidades),
        (center_x + margin,         center_y + margin,          (255, 224, 178), 'AMENAZAS', amenazas)
    ]
    for left, top, color, title, items in configs:
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
        shape.fill.solid(); shape.fill.fore_color.rgb = RGBColor(*color); shape.line.color.rgb = RGBColor(180, 180, 180)
        tf = shape.text_frame; tf.word_wrap = True; tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        p = tf.paragraphs[0]; p.text = title; p.font.bold = True; p.font.color.rgb = RGBColor(50, 50, 50)
        _llenar_text_frame_flexible(tf, items)

def _dibujar_journey_nativo(slide, data):
    keys_candidates = [k for k in data.keys() if "etapa" in k.lower() or "stage" in k.lower()]
    def natural_sort_key(s): nums = re.findall(r'\d+', s); return int(nums[0]) if nums else s
    sorted_keys = sorted(keys_candidates, key=natural_sort_key)
    etapas = []
    for k in sorted_keys:
        val = data[k]
        etapas.append(val if isinstance(val, dict) else {"nombre_etapa": k, "descripcion": str(val)})
    if not etapas:
        list_etapas = data.get('etapas', []) or data.get('pasos', [])
        if list_etapas and isinstance(list_etapas, list): etapas = list_etapas
    if not etapas: _dibujar_lista_generica(slide, data); return

    num_etapas = min(len(etapas), 6); etapas = etapas[:num_etapas]
    rows = 5; cols = num_etapas + 1
    left = Inches(0.5); top = Inches(1.2); width = Inches(9.0); height = Inches(5.0)
    shape = slide.shapes.add_table(rows, cols, left, top, width, height); table = shape.table
    row_headers = ["Fases", "Acciones", "Emociones", "Puntos de Dolor", "Oportunidades"]
    colors_rows = [(0, 51, 102), (245, 245, 245), (255, 255, 255), (255, 235, 238), (232, 245, 233)]
    for i, header in enumerate(row_headers):
        cell = table.cell(i, 0); cell.text = header; cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor(*colors_rows[i]) if i > 0 else RGBColor(0, 51, 102)
        cell.margin_left = Inches(0.05); cell.margin_right = Inches(0.05)
        p = cell.text_frame.paragraphs[0]; p.font.bold = True; p.font.size = Pt(9)
        p.font.color.rgb = RGBColor(255, 255, 255) if i == 0 else RGBColor(0, 0, 0)
    
    keys_map = ["nombre_etapa", "acciones", "emociones", "puntos_dolor", "oportunidades"]
    for col_idx, etapa_data in enumerate(etapas):
        real_col = col_idx + 1
        for row_idx, key_part in enumerate(keys_map):
            cell = table.cell(row_idx, real_col); cell.fill.solid()
            bg_color = colors_rows[row_idx] if row_idx > 0 else (33, 150, 243)
            cell.fill.fore_color.rgb = RGBColor(*bg_color)
            cell.margin_left = Inches(0.05); cell.margin_right = Inches(0.05)
            
            if row_idx == 0:
                content = etapa_data.get("nombre_etapa", f"Etapa {col_idx+1}") if isinstance(etapa_data, dict) else f"Etapa {col_idx+1}"
            else:
                content = _buscar_clave_flexible(etapa_data, [key_part])

            tf = cell.text_frame; tf.word_wrap = True
            if row_idx == 0:
                p = tf.paragraphs[0]; p.text = str(content).upper(); p.font.bold = True
                p.font.color.rgb = RGBColor(255, 255, 255); p.alignment = PP_ALIGN.CENTER; p.font.size = Pt(9)
            else:
                _llenar_text_frame_tabla(tf, content)

def _dibujar_embudo_nativo(slide, data):
    pasos = data.get('pasos', []) or data.get('etapas', [])
    if not pasos: return
    num = len(pasos); start_y = 1.5; total_h = 4.8; step_h = total_h / num; max_w = 8.5; min_w = 3.0; center_x = 5.0
    for i, paso in enumerate(pasos):
        top_w = max_w - (i * (max_w - min_w) / num)
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(center_x - top_w/2), Inches(start_y + (i * step_h) + (i*0.05)), Inches(top_w), Inches(step_h))
        shape.fill.solid(); blue_val = max(100, 220 - (i * 30)); shape.fill.fore_color.rgb = RGBColor(30, 130, blue_val)
        shape.line.fill.background()
        tf = shape.text_frame; tf.word_wrap = True; tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        tf.text = str(paso); tf.paragraphs[0].font.color.rgb = RGBColor(255, 255, 255)
        tf.paragraphs[0].alignment = PP_ALIGN.CENTER; tf.paragraphs[0].font.bold = True

def _dibujar_lista_generica(slide, data):
    left = Inches(1); top = Inches(1.5); width = Inches(8); height = Inches(4.8)
    textbox = slide.shapes.add_textbox(left, top, width, height)
    tf = textbox.text_frame; tf.word_wrap = True; tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    excluded_keys = ['titulo_diapositiva', 'template_type', 'conclusion_clave']
    first = True
    for k, v in data.items():
        if k in excluded_keys: continue
        if not first: tf.add_paragraph()
        p = tf.add_paragraph() if not first else tf.paragraphs[0]
        p.text = k.replace('_', ' ').upper(); p.font.bold = True; p.font.color.rgb = RGBColor(0, 51, 102); first = False
        _llenar_text_frame_flexible(tf, v if isinstance(v, list) else [v])

def _llenar_text_frame_flexible(text_frame, lista_items):
    if not lista_items: return
    if not isinstance(lista_items, list): lista_items = [str(lista_items)]
    valid_items = [str(x) for x in lista_items if x and str(x).lower() != "none"]
    if not valid_items: return
    p = text_frame.paragraphs[0]; p.text = f"• {valid_items[0]}"; p.font.color.rgb = RGBColor(40, 40, 40)
    for item in valid_items[1:]:
        p = text_frame.add_paragraph(); p.text = f"• {item}"; p.font.color.rgb = RGBColor(40, 40, 40)

def _llenar_text_frame_tabla(text_frame, content):
    text_frame.clear()
    if content is None or str(content).strip().lower() == "none": content = "-"
    if isinstance(content, list):
        for item in content:
            if not item: continue
            p = text_frame.add_paragraph(); p.text = f"• {item}"; p.font.size = Pt(9); p.font.color.rgb = RGBColor(0, 0, 0); p.space_after = Pt(2)
    else:
        text_str = str(content).strip()
        if not text_str: return
        p = text_frame.add_paragraph(); p.text = text_str; p.font.size = Pt(9); p.font.color.rgb = RGBColor(0, 0, 0)

def _crear_etiqueta(slide, x, y, texto, bold=False, vertical=False):
    w, h = (Inches(2), Inches(0.5)) if not vertical else (Inches(0.5), Inches(2))
    tb = slide.shapes.add_textbox(Inches(x) - w/2, Inches(y) - h/2, w, h)
    tf = tb.text_frame; tf.word_wrap = True; tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    p = tf.paragraphs[0]; p.text = str(texto); p.alignment = PP_ALIGN.CENTER; p.font.bold = bold; p.font.color.rgb = RGBColor(80, 80, 80)
    if vertical: tb.rotation = -90

def _poner_titulo_contenido(slide, shape, title, content):
    tf = shape.text_frame; tf.word_wrap = True; tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    p = tf.paragraphs[0]; p.text = title.upper(); p.font.bold = True; p.font.size = Pt(10); p.alignment = PP_ALIGN.CENTER
    tf.add_paragraph()
    _llenar_text_frame_flexible(tf, content)

def _poner_titulo_contenido_manual(slide, x, y, w, h, title, content):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame; tf.word_wrap = True; tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    p = tf.paragraphs[0]; p.text = title.upper(); p.font.bold = True; p.font.size = Pt(10); p.alignment = PP_ALIGN.CENTER
    tf.add_paragraph()
    _llenar_text_frame_flexible(tf, content)
