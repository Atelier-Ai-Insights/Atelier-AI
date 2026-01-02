import io
import os
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
import markdown2
from bs4 import BeautifulSoup

# ==============================
# GENERADOR DE WORD (DOCX) - PURO
# ==============================

def clean_text(text):
    """Limpia espacios y saltos de línea extra."""
    if not text: return ""
    return text.strip()

def process_rich_text(paragraph, html_content):
    """
    Procesa un párrafo HTML y añade 'runs' al párrafo de Word
    para manejar negritas (<strong>, <b>) y cursivas (<em>, <i>).
    """
    soup = BeautifulSoup(str(html_content), "html.parser")
    
    # Si no hay hijos, es texto plano
    if not list(soup.children):
        run = paragraph.add_run(soup.get_text())
        return

    # Recorrer nodos hijos (texto y tags)
    for child in soup.contents:
        if child.name in ['strong', 'b']:
            run = paragraph.add_run(child.get_text())
            run.bold = True
        elif child.name in ['em', 'i']:
            run = paragraph.add_run(child.get_text())
            run.italic = True
        elif child.name == 'code':
            run = paragraph.add_run(child.get_text())
            run.font.name = 'Courier New'
            run.font.color.rgb = RGBColor(100, 100, 100)
        elif isinstance(child, str):
            paragraph.add_run(child)
        else:
            # Recursividad simple para tags anidados o texto plano dentro de otros tags
            paragraph.add_run(child.get_text())

def generate_docx(markdown_text, title="Reporte Atelier", template_path=None):
    """
    Convierte Markdown a un documento Word (.docx).
    
    Args:
        markdown_text (str): El contenido en markdown.
        title (str): Título del documento.
        template_path (str, optional): Ruta a un archivo .docx para usar como plantilla base.
    
    Returns:
        bytes: El contenido del archivo .docx listo para descargar.
    """
    try:
        # 1. Cargar Plantilla o Crear Nuevo
        if template_path and os.path.exists(template_path):
            doc = Document(template_path)
        else:
            doc = Document()
            # Si no hay plantilla, agregamos el título manualmente al inicio
            doc.add_heading(title, 0)

        # 2. Convertir Markdown a HTML para facilitar el parseo
        html_content = markdown2.markdown(markdown_text)
        soup = BeautifulSoup(html_content, "html.parser")

        # 3. Iterar sobre los elementos bloque
        for element in soup.find_all(['h1', 'h2', 'h3', 'p', 'ul', 'ol', 'blockquote']):
            
            # --- ENCABEZADOS (H1, H2, H3) ---
            if element.name in ['h1', 'h2', 'h3']:
                level = int(element.name[1])
                # Mapear H1 markdown a Heading 1 de Word, etc.
                doc.add_heading(element.get_text().strip(), level=level)

            # --- PÁRRAFOS (P) ---
            elif element.name == 'p':
                p = doc.add_paragraph()
                # Procesar negritas/cursivas internas
                process_rich_text(p, element)

            # --- LISTAS (UL, OL) ---
            elif element.name in ['ul', 'ol']:
                for li in element.find_all('li'):
                    style = 'List Bullet' if element.name == 'ul' else 'List Number'
                    try:
                        p = doc.add_paragraph(style=style)
                    except:
                        # Fallback si el estilo no existe en la plantilla base
                        p = doc.add_paragraph(style='List Paragraph')
                    
                    process_rich_text(p, li)

            # --- CITAS (BLOCKQUOTE) ---
            elif element.name == 'blockquote':
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Inches(0.5)
                run = p.add_run(element.get_text().strip())
                run.italic = True
                run.font.color.rgb = RGBColor(80, 80, 80)

        # 4. Guardar en Buffer
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()

    except Exception as e:
        print(f"Error generando DOCX: {e}")
        return None
