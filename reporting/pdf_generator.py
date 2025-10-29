import streamlit as st
import html
import markdown2
from bs4 import BeautifulSoup
from io import BytesIO
import os
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

# ==============================
# REGISTRO DE FUENTES PDF
# ==============================
# Registrar fuente Unicode para tildes/ñ
FONT_REGISTERED = False
FONT_NAME = 'DejaVuSans'
FALLBACK_FONT_NAME = 'Helvetica' # Fuente por defecto de ReportLab
try:
    pdfmetrics.registerFont(TTFont(FONT_NAME, 'DejaVuSans.ttf'))
    FONT_REGISTERED = True
    print(f"INFO: Fuente '{FONT_NAME}' registrada correctamente para PDF.")
except Exception as e:
    # Esta advertencia puede aparecer en Streamlit Cloud si no subes el .ttf
    print(f"Advertencia PDF: No se encontró '{FONT_NAME}.ttf'. Caracteres especiales podrían no mostrarse. Usando '{FALLBACK_FONT_NAME}'. Error: {e}")
    FONT_NAME = FALLBACK_FONT_NAME

# ==============================
# CLASE PDFReport
# ==============================
class PDFReport:
    def __init__(self, buffer_or_filename, banner_path=None):
        self.banner_path = banner_path
        self.elements = []
        self.styles = getSampleStyleSheet()
        self.doc = SimpleDocTemplate(buffer_or_filename, pagesize=A4, 
                                     rightMargin=15*mm, leftMargin=15*mm,
                                     topMargin=40*mm, bottomMargin=20*mm)
        
        pdf_font_name = FONT_NAME
        base_styles = ['Normal', 'BodyText', 'Italic', 'Bold', 'Heading1', 'Heading2', 'Heading3', 'Heading4', 'Heading5', 'Heading6', 'Code']
        
        for style_name in base_styles:
            if style_name in self.styles:
                try:
                    self.styles[style_name].fontName = pdf_font_name
                    if style_name == 'Code':
                        if pdf_font_name == FALLBACK_FONT_NAME or not FONT_REGISTERED: 
                            self.styles[style_name].fontName = 'Courier'
                        self.styles[style_name].fontSize = 9
                        self.styles[style_name].leading = 11
                        self.styles[style_name].leftIndent = 6*mm
                        self.styles[style_name].backColor = colors.whitesmoke
                        self.styles[style_name].textColor = colors.darkslategrey
                except Exception as e:
                    print(f"Warn: Font '{pdf_font_name}' -> '{style_name}'. {e}")

        self.styles.add(ParagraphStyle(name='CustomTitle', parent=self.styles['Heading1'], fontName=pdf_font_name, 
                                       alignment=1, spaceAfter=14, fontSize=16, leading=20)) 
        
        self.styles.add(ParagraphStyle(name='CustomHeading2', parent=self.styles['Heading2'], fontName=pdf_font_name, 
                                       spaceBefore=12, spaceAfter=6, fontSize=13, leading=17))
        self.styles.add(ParagraphStyle(name='CustomHeading3', parent=self.styles['Heading3'], fontName=pdf_font_name, 
                                       spaceBefore=10, spaceAfter=5, fontSize=12, leading=16))

        self.styles.add(ParagraphStyle(name='CustomBodyText', parent=self.styles['Normal'], fontName=pdf_font_name, 
                                       leading=15, alignment=4, fontSize=11, spaceAfter=6)) 
        
        self.styles.add(ParagraphStyle(name='CustomBullet', parent=self.styles['Normal'], fontName=pdf_font_name,
                                       fontSize=11, leading=15, spaceAfter=4,
                                       leftIndent=10*mm, bulletIndent=5*mm)) # Indentación clave
                                       
        self.styles.add(ParagraphStyle(name='CustomNumber', parent=self.styles['Normal'], fontName=pdf_font_name,
                                       fontSize=11, leading=15, spaceAfter=4,
                                       leftIndent=10*mm, bulletIndent=5*mm)) # Indentación clave

        self.styles.add(ParagraphStyle(name='CustomFooter', parent=self.styles['Normal'], fontName=pdf_font_name, 
                                       alignment=1, textColor=colors.grey, fontSize=8))

    def header(self, canvas, doc):
        canvas.saveState()
        if self.banner_path and os.path.isfile(self.banner_path):
            try:
                # Ajustar tamaño y posición del banner si es necesario
                img_w, img_h = 210*mm, 30*mm # Banner un poco más pequeño
                y_pos = A4[1] - img_h - 5*mm # Bajarlo un poco
                canvas.drawImage(self.banner_path, 0, y_pos, width=img_w, height=img_h, 
                                 preserveAspectRatio=True, anchor='n')
            except Exception as e:
                print(f"Error PDF header: {e}")
        canvas.restoreState()
        
    def footer(self, canvas, doc):
        canvas.saveState()
        footer_text = "Generado por Atelier Data Studio. Es posible que se muestre información imprecisa. Verifica las respuestas."
        p = Paragraph(footer_text, self.styles['CustomFooter'])
        w, h = p.wrap(doc.width, doc.bottomMargin)
        p.drawOn(canvas, doc.leftMargin, 8*mm)
        canvas.restoreState()
        
    def header_footer(self, canvas, doc): 
        self.header(canvas, doc)
        self.footer(canvas, doc)

    def add_paragraph(self, text, style='CustomBodyText'):
        """Añade un párrafo con el estilo especificado."""
        try:
            # Usar HTML <br> para saltos de línea explícitos dentro del párrafo
            text_with_breaks = text.replace('\n', '<br/>')
            style_to_use = self.styles.get(style, self.styles['CustomBodyText'])
            p = Paragraph(text_with_breaks, style_to_use)
            self.elements.append(p)
        except Exception as e:
            print(f"Err add para: {e}. Text: {text[:100]}...")
            self.elements.append(Paragraph(f"Err render: {text[:100]}...", self.styles['Code']))

    def add_title(self, text, level=1):
        """Añade un título basado en el nivel (H1, H2, H3)."""
        if level == 1:
            style_name = 'CustomTitle'
        elif level == 2:
            style_name = 'CustomHeading2'
        elif level >= 3:
            style_name = 'CustomHeading3' # Usar H3 para H3 y superiores
        else: # Por defecto, H2
            style_name = 'CustomHeading2'
            
        style_to_use = self.styles.get(style_name, self.styles['CustomHeading2'])
        p = Paragraph(text, style_to_use)
        self.elements.append(p)

    def build_pdf(self):
        try:
            self.doc.build(self.elements, onFirstPage=self.header_footer, onLaterPages=self.header_footer)
        except Exception as e:
            st.error(f"Error building PDF: {e}")

# ==============================
# PARSEO DE MARKDOWN A PDF
# ==============================
def add_markdown_content(pdf: PDFReport, markdown_text: str):
    processed_elements = 0
    try:
        decoded_text = html.unescape(str(markdown_text))
        html_text = markdown2.markdown(decoded_text, extras=[
            "fenced-code-blocks", "tables", "break-on-newline",
            "code-friendly", "cuddled-lists", "smarty-pants"
        ])

        soup = BeautifulSoup(html_text, "html.parser")
        container = soup.body if soup.body else soup

        if not container:
             print("WARN: BeautifulSoup container is empty after parsing.")
             raise ValueError("Could not parse HTML content.")

        for elem in container.children:
            try:
                if isinstance(elem, str):
                    text = elem.strip()
                    if text:
                        pdf.add_paragraph(text)
                        processed_elements += 1
                    continue

                if not hasattr(elem, 'name') or not elem.name:
                    continue

                tag_name = elem.name.lower()

                # --- Títulos ---
                if tag_name.startswith("h"):
                   level = int(tag_name[1]) if len(tag_name) > 1 and tag_name[1].isdigit() else 1
                   title_text = elem.get_text(strip=True)
                   if title_text:
                       pdf.add_title(title_text, level=level)
                       processed_elements += 1

                # --- Párrafos ---
                elif tag_name == "p":
                    content = ""
                    try:
                        content = elem.decode_contents(formatter="html").strip()
                    except Exception:
                        content = elem.get_text(strip=True)
                    if content:
                        pdf.add_paragraph(content)
                        processed_elements += 1

                # --- Listas con Viñetas (ul) ---
                elif tag_name == "ul":
                    list_items = elem.find_all("li", recursive=False)
                    if not list_items: continue
                    for li in list_items:
                        content = li.get_text(separator=' ', strip=True)
                        if content:
                            pdf.add_paragraph(f"• {content}", style='CustomBullet')
                            processed_elements += 1

                # --- Listas Numeradas (ol) ---
                elif tag_name == "ol":
                    list_items = elem.find_all("li", recursive=False)
                    if not list_items: continue
                    for idx, li in enumerate(list_items, 1):
                        content = li.get_text(separator=' ', strip=True)
                        if content:
                            pdf.add_paragraph(f"{idx}. {content}", style='CustomNumber')
                            processed_elements += 1

                # --- Bloques de Código ---
                elif tag_name == "pre":
                   code_elem = elem.find('code')
                   code_text = (code_elem.get_text() if code_elem else elem.get_text())
                   if code_text:
                       pdf.add_paragraph(code_text, style='Code')
                       processed_elements += 1

                # --- Citas ---
                elif tag_name == "blockquote":
                    content = ""
                    try:
                        content = elem.decode_contents(formatter="html").strip()
                    except:
                        content = elem.get_text(strip=True)
                    if content:
                        pdf.add_paragraph(f"> {content}", style='Italic')
                        processed_elements += 1

                # --- Otros elementos (intentar como párrafo) ---
                else:
                    try:
                        content = elem.decode_contents(formatter="html").strip()
                        if content:
                            pdf.add_paragraph(content)
                            processed_elements += 1
                    except Exception:
                        plain_text = elem.get_text(strip=True)
                        if plain_text:
                            pdf.add_paragraph(plain_text)
                            processed_elements += 1

            except Exception as loop_error:
                print(f"ERROR processing element: <{elem.name if hasattr(elem, 'name') else 'unknown'}>. Error: {loop_error!r}")
                pdf.add_paragraph(f"--- Error processing tag: {elem.name if hasattr(elem, 'name') else 'unknown'} ---", style='Code')
                continue

        if processed_elements == 0 and markdown_text.strip():
             print("WARN: No elements were processed by add_markdown_content, but input text was not empty.")
             pdf.add_paragraph("--- Warning: Markdown parsing yielded no elements. Displaying raw text: ---", style='Code')
             pdf.add_paragraph(str(markdown_text), style='CustomBodyText')

    except Exception as e:
        print(f"CRITICAL ERROR in add_markdown_content: {e!r}")
        pdf.add_paragraph("--- Error Crítico al Parsear Markdown ---", style='Code')
        pdf.add_paragraph(str(markdown_text), style='Code')
        pdf.add_paragraph("--- Fin del Error ---", style='Code')
        
# ==============================
# FUNCIÓN PRINCIPAL DE GENERACIÓN
# ==============================
def generate_pdf_html(content, title="Documento Final", banner_path=None):
    try:
        buffer = BytesIO()
        pdf = PDFReport(buffer, banner_path=banner_path) # Crear instancia de PDFReport
        pdf.add_title(title, level=1) # Añadir título principal
        
        # --- ASEGÚRATE QUE ESTA LÍNEA PASE 'pdf' PRIMERO ---
        add_markdown_content(pdf, content) 
        # ---------------------------------------------------
        
        pdf.build_pdf() # Construir el PDF
        pdf_data = buffer.getvalue()
        buffer.close()
        
        if pdf_data:
            return pdf_data
        else:
            st.error("Error interno al construir PDF.")
            return None
            
    except Exception as e:
        st.error(f"Error crítico al generar PDF: {e}")
        return None
