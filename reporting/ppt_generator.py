import streamlit as st
from io import BytesIO
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.enum.text import MSO_AUTO_SIZE  # <-- ARREGLO 1
from pptx.dml.color import RGBColor
import os 

def crear_ppt_one_pager(data: dict):
    try:
        template_path = "Plantilla_PPT_ATL.pptx"
        if not os.path.isfile(template_path):
            st.error(f"Error fatal: No se encontró el archivo de plantilla '{template_path}'.")
            return None
            
        prs = Presentation(template_path) 
        prs.slide_width = Inches(16)
        prs.slide_height = Inches(9)
        
        blank_slide_layout = prs.slide_layouts[6] 
        slide = prs.slides.add_slide(blank_slide_layout)

        txBox_title = slide.shapes.add_textbox(Inches(1.5), Inches(0.5), Inches(13), Inches(1))
        p_title = txBox_title.text_frame.paragraphs[0]
        p_title.text = data.get("titulo_diapositiva", "Resumen Estratégico")
        p_title.font.bold = True
        p_title.font.size = Pt(44) 
        p_title.alignment = PP_ALIGN.CENTER
        txBox_title.text_frame.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT # <-- ARREGLO 2

        txBox_insight = slide.shapes.add_textbox(Inches(1.5), Inches(1.8), Inches(13), Inches(1))
        tf_insight = txBox_insight.text_frame
        tf_insight.word_wrap = True
        
        p_insight = tf_insight.add_paragraph()
        p_insight.text = f"Insight Clave: {data.get('insight_clave', 'N/A')}"
        p_insight.font.italic = True
        p_insight.font.size = Pt(18)
        p_insight.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
        p_insight.alignment = PP_ALIGN.LEFT 
        
        content_left = Inches(1.5); content_top = Inches(2.8); content_width = Inches(13); content_height = Inches(5.5)
        txBox_content = slide.shapes.add_textbox(content_left, content_top, content_width, content_height)
        tf_content = txBox_content.text_frame
        tf_content.word_wrap = True

        p_h_title = tf_content.paragraphs[0]
        p_h_title.text = "Hallazgos Principales"
        p_h_title.font.bold = True; p_h_title.font.size = Pt(28); p_h_title.space_after = Pt(6)

        for hallazgo in data.get("hallazgos_principales", ["N/A"]):
            p = tf_content.add_paragraph()
            p.text = hallazgo; p.font.size = Pt(16); p.level = 1; p.space_after = Pt(6)

        tf_content.add_paragraph().space_after = Pt(14)

        p_o_title = tf_content.add_paragraph()
        p_o_title.text = "Oportunidades"
        p_o_title.font.bold = True; p_o_title.font.size = Pt(28); p_o_title.space_after = Pt(6)
        
        for op in data.get("oportunidades", ["N/A"]):
            p = tf_content.add_paragraph()
            p.text = op; p.font.size = Pt(16); p.level = 1; p.space_after = Pt(6)

        tf_content.add_paragraph().space_after = Pt(14)

        p_r_title = tf_content.add_paragraph()
        p_r_title.text = "Recomendación Estratégica"
        p_r_title.font.bold = True; p_r_title.font.size = Pt(28); p_r_title.space_after = Pt(6)
        
        p_r = tf_content.add_paragraph()
        p_r.text = data.get("recomendacion_estrategica", "N/A")
        p_r.font.size = Pt(16); p_r.level = 1; p_r.space_after = Pt(6)
        
        f = BytesIO()
        prs.save(f)
        f.seek(0)
        return f.getvalue()

    except Exception as e:
        st.error(f"Error al generar el archivo .pptx: {e}") 
        return None