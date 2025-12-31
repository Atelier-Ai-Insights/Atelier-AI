from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_AUTO_SIZE 
import io

def crear_ppt_desde_json(data_json, image_stream=None):
    """
    Genera un PowerPoint con formas NATIVAS.
    Actualizado para soportar Customer Journey Map en formato TABLA.
    """
    
    # 1. Cargar Plantilla
    try:
        prs = Presentation("Plantilla_PPT_ATL.pptx")
    except:
        prs = Presentation()

    slide_layout = prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[-1]
    slide = prs.slides.add_slide(slide_layout)

    # 2. Configurar Título
    if slide.shapes.title:
        slide.shapes.title.text = data_json.get('titulo_diapositiva', 'Customer Journey Map')
    else:
        title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.2), Inches(9), Inches(1))
        tf = title_box.text_frame
        tf.text = data_json.get('titulo_diapositiva', 'Customer Journey Map')
        tf.paragraphs[0].font.size = Pt(24)
        tf.paragraphs[0].font.bold = True
        tf.paragraphs[0].alignment = PP_ALIGN.CENTER

    # 3. Detectar Tipo y Dibujar
    template_type = data_json.get('template_type', '').lower()
    
    if "matriz" in template_type or "2x2" in template_type:
        _dibujar_matriz_nativa(slide, data_json)
    elif "foda" in template_type or "swot" in template_type or "dofa" in template_type:
        _dibujar_foda_nativo(slide, data_json)
    elif "embudo" in template_type or "funnel" in template_type:
        _dibujar_embudo_nativo(slide, data_json)
    # --- NUEVA CONDICIÓN PARA JOURNEY MAP ---
    elif "journey" in template_type or "viaje" in template_type or "map" in template_type:
        _dibujar_journey_nativo(slide, data_json)
    else:
        _dibujar_lista_generica(slide, data_json)

    # 4. Agregar Conclusión
    if 'conclusion_clave' in data_json:
        # Ajustamos un poco la posición para que no choque con la tabla del Journey
        bg = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.5), Inches(6.8), Inches(9), Inches(0.6))
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

    output = io.BytesIO()
    prs.save(output)
    output.seek(0)
    return output

# ==============================================================================
# NUEVA FUNCIÓN: JOURNEY MAP (TABLA)
# ==============================================================================

def _dibujar_journey_nativo(slide, data):
    """
    Construye una tabla detallada para el Customer Journey Map.
    Filas: Dimensiones (Acciones, Emociones, etc.)
    Columnas: Etapas del viaje.
    """
    # 1. Extraer y Ordenar Etapas
    # Buscamos claves que empiecen con "ETAPA" o "STAGE" o que sean objetos diccionarios
    etapas = []
    
    # Lógica para encontrar las etapas en el JSON (pueden venir como claves 'Etapa 1', 'Etapa 2'...)
    sorted_keys = sorted([k for k in data.keys() if "etapa" in k.lower() or "stage" in k.lower()])
    
    for k in sorted_keys:
        val = data[k]
        # Si es un string (JSON mal parseado dentro de JSON), intentamos arreglarlo visualmente
        # pero asumiremos que clean_gemini_json hizo su trabajo y 'val' es un dict.
        if isinstance(val, dict):
            etapas.append(val)
        else:
            # Fallback simple si viene plano
            etapas.append({"nombre_etapa": k, "descripcion": str(val)})

    if not etapas:
        # Si no encontró claves "Etapa X", intenta buscar una lista llamada "pasos" o "etapas"
        list_etapas = data.get('etapas', []) or data.get('pasos', [])
        if list_etapas and isinstance(list_etapas, list):
            etapas = list_etapas

    if not etapas:
        _dibujar_lista_generica(slide, data)
        return

    # 2. Configurar Tabla
    num_etapas = len(etapas)
    # Filas: Encabezado (Nombre Etapa) + Acciones + Emociones + Puntos Dolor + Oportunidades
    rows = 5 
    cols = num_etapas + 1 # +1 para la columna de etiquetas de la izquierda
    
    # Dimensiones de la tabla
    left = Inches(0.5)
    top = Inches(1.2)
    width = Inches(9.0)
    height = Inches(5.0)

    shape = slide.shapes.add_table(rows, cols, left, top, width, height)
    table = shape.table

    # 3. Definir Encabezados de Fila (Columna 0)
    row_headers = ["Fases", "Acciones", "Emociones", "Puntos de Dolor", "Oportunidades"]
    colors = [(0, 51, 102), (240, 240, 240), (255, 255, 255), (255, 235, 238), (232, 245, 233)] # Azul, Gris, Blanco, Rojo claro, Verde claro
    
    for i, header in enumerate(row_headers):
        cell = table.cell(i, 0)
        cell.text = header
        cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor(*colors[i]) if i > 0 else RGBColor(0, 51, 102)
        
        p = cell.text_frame.paragraphs[0]
        p.font.bold = True
        p.font.size = Pt(10)
        p.font.color.rgb = RGBColor(255, 255, 255) if i == 0 else RGBColor(0, 0, 0)

    # 4. Llenar Datos (Columnas 1 a N)
    keys_map = [
        "nombre_etapa", # Fila 0
        "acciones",     # Fila 1
        "emociones",    # Fila 2
        "puntos_dolor", # Fila 3
        "oportunidades" # Fila 4
    ]

    for col_idx, etapa_data in enumerate(etapas):
        real_col = col_idx + 1 # Saltamos la columna de headers
        
        for row_idx, key in enumerate(keys_map):
            cell = table.cell(row_idx, real_col)
            
            # Formato de celda
            cell.fill.solid()
            # Alternar colores suaves o mantener blanco
            cell.fill.fore_color.rgb = RGBColor(*colors[row_idx]) if row_idx > 0 else RGBColor(33, 150, 243) # Header azul claro
            
            # Obtener contenido
            content = _get_case_insensitive_val(etapa_data, key)
            
            # Formatear texto
            tf = cell.text_frame
            tf.word_wrap = True
            
            p = tf.paragraphs[0]
            # Estilo header
            if row_idx == 0: 
                p.text = str(content).upper()
                p.font.bold = True
                p.font.color.rgb = RGBColor(255, 255, 255)
                p.alignment = PP_ALIGN.CENTER
                p.font.size = Pt(10)
            else:
                # Estilo contenido
                _llenar_text_frame_tabla(tf, content)


# ==============================================================================
# HELPERS EXISTENTES Y NUEVOS
# ==============================================================================

def _get_case_insensitive(data, key):
    """(Ya existente)"""
    key = key.lower()
    for k, v in data.items():
        if k.lower() == key:
            return v
    return []

def _get_case_insensitive_val(data, key_part):
    """Busca un valor en un dict si la clave contiene el string (ej: 'acciones' match con 'acciones_usuario')."""
    if not isinstance(data, dict): return ""
    # Búsqueda exacta primero
    if key_part in data: return data[key_part]
    # Búsqueda aproximada
    for k, v in data.items():
        if key_part in k.lower():
            return v
    return "-"

def _llenar_text_frame_tabla(text_frame, content):
    """Helper para llenar celdas de tabla con letra pequeña."""
    text_frame.clear() # Limpiar párrafo por defecto
    
    if isinstance(content, list):
        for item in content:
            p = text_frame.add_paragraph()
            p.text = f"• {item}"
            p.font.size = Pt(8) # Letra pequeña para que quepa todo
            p.font.color.rgb = RGBColor(0, 0, 0)
            p.space_after = Pt(2)
    else:
        p = text_frame.add_paragraph()
        p.text = str(content)
        p.font.size = Pt(8)
        p.font.color.rgb = RGBColor(0, 0, 0)

# (MANTENER AQUÍ EL RESTO DE TUS FUNCIONES: _dibujar_foda_nativo, _dibujar_matriz_nativa, etc.)
# ...
# ...
