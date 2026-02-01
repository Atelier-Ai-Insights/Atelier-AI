import io
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor

def create_pptx_from_structure(data):
    """
    Genera un archivo PowerPoint en memoria basado en un diccionario de datos.
    Estructura esperada de data:
    {
        "titulo": str,
        "subtitulo": str,
        "puntos_clave": list[str],
        "insight_principal": str
    }
    """
    # 1. Crear presentación vacía
    prs = Presentation()
    
    # 2. Usar un layout en blanco (generalmente el índice 6 es blank)
    slide_layout = prs.slide_layouts[6] 
    slide = prs.slides.add_slide(slide_layout)
    
    # --- CONFIGURACIÓN DE ESTILO ---
    # Colores corporativos simulados (Azul Oscuro y Gris)
    COLOR_PRIMARY = RGBColor(0, 51, 102) 
    COLOR_ACCENT = RGBColor(255, 102, 0) # Naranja para insights
    
    # --- A. TÍTULO ---
    title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.4), Inches(9), Inches(1))
    tf = title_box.text_frame
    p = tf.paragraphs[0]
    p.text = data.get("titulo", "Sin Título").upper()
    p.font.name = 'Arial'
    p.font.size = Pt(32)
    p.font.bold = True
    p.font.color.rgb = COLOR_PRIMARY
    
    # --- B. SUBTÍTULO ---
    sub_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.0), Inches(9), Inches(0.5))
    tf_sub = sub_box.text_frame
    p_sub = tf_sub.paragraphs[0]
    p_sub.text = data.get("subtitulo", "")
    p_sub.font.name = 'Arial'
    p_sub.font.size = Pt(14)
    p_sub.font.color.rgb = RGBColor(100, 100, 100)
    p_sub.font.italic = True

    # --- C. CONTENIDO (PUNTOS CLAVE) ---
    # Dibujar una línea separadora
    shape = slide.shapes.add_shape(
        1, Inches(0.5), Inches(1.6), Inches(9), Inches(0.05) # Tipo 1 es rectángulo
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = COLOR_PRIMARY
    shape.line.fill.background() # Sin borde

    # Caja de texto para bullets
    body_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.8), Inches(9), Inches(3.5))
    tf_body = body_box.text_frame
    tf_body.word_wrap = True
    
    puntos = data.get("puntos_clave", [])
    if isinstance(puntos, str): puntos = [puntos]
    
    for punto in puntos:
        p = tf_body.add_paragraph()
        p.text = f"• {punto}"
        p.font.name = 'Arial'
        p.font.size = Pt(16)
        p.space_after = Pt(10)
        p.level = 0

    # --- D. INSIGHT PRINCIPAL (DESTACADO) ---
    insight_text = data.get("insight_principal", "")
    if insight_text:
        # Fondo destacado (Rectángulo redondeado)
        left = Inches(0.5)
        top = Inches(5.5)
        width = Inches(9)
        height = Inches(1.5)
        
        shape = slide.shapes.add_shape(5, left, top, width, height) # 5 es Rounded Rectangle
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(240, 240, 240) # Gris muy claro
        shape.line.color.rgb = COLOR_PRIMARY
        shape.line.width = Pt(1.5)
        
        # Texto del Insight
        tf_insight = shape.text_frame
        tf_insight.margin_left = Inches(0.2)
        tf_insight.margin_right = Inches(0.2)
        tf_insight.vertical_anchor = 3 # Middle
        
        p = tf_insight.paragraphs[0]
        p.text = "💡 INSIGHT ESTRATÉGICO:"
        p.font.name = 'Arial'
        p.font.size = Pt(12)
        p.font.bold = True
        p.font.color.rgb = COLOR_ACCENT
        p.alignment = PP_ALIGN.CENTER
        
        p2 = tf_insight.add_paragraph()
        p2.text = insight_text
        p2.font.name = 'Arial'
        p2.font.size = Pt(14)
        p2.alignment = PP_ALIGN.CENTER
        p2.font.color.rgb = RGBColor(50, 50, 50)

    # --- E. GUARDAR EN MEMORIA ---
    output = io.BytesIO()
    prs.save(output)
    output.seek(0)
    
    return output
