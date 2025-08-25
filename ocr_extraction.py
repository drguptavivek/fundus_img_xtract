# ocr_extraction.py
# uses PyMuPDF  PIL,  pytesseract  matplotlib
import fitz  # PyMuPDF 
from PIL import Image
import pytesseract
import io
import matplotlib.pyplot as plt  # Import matplotlib

def find_report_pages_by_coords_with_grid(pdf_path):
    """
    Analyzes a PDF by checking specific coordinates, and saves an image
    of each page with a grid overlay.

    Args:
        pdf_path (str): The file path to the PDF.

    Returns:
        tuple: A tuple containing the page numbers for the Diabetic and Glaucoma reports.
    """
    pageNumberDiabeticReport = None
    text_diabetic_result  = None
    text_diabetic_qual_result  = None
    
    pageNumberGlaucomaReport = None
    text_glaucoma_result = None
    vcdr_rt = None
    vcdr_lt = None
    text_gl_qual_result = None


    diabetic_report_coords = (0, 200, 1200, 400)
    diabetic_result_coords = (350, 650, 2000, 800)
    diabetic_qual_coords = (50, 3100, 1600, 3200)

    glaucoma_report_coords = (0, 400, 1200, 600)
    glaucoma_result_coords = (0, 1550, 2000, 1650)
    glaucoma_vcdr_rt_coords = (0, 1300, 1000, 1500)
    glaucoma_vcdr_lt_coords = (1300, 1300, 2200, 1500)
    glaucoma_qual_coords =   (50, 3100, 1700, 3200)


    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"Error opening PDF file: {e}")
        return None, None

    for page_num in range(len(doc)):
        if pageNumberDiabeticReport is not None and pageNumberGlaucomaReport is not None:
            break

        page = doc.load_page(page_num)
        pix = page.get_pixmap(dpi=300)
        image = Image.open(io.BytesIO(pix.tobytes("png")))
        #image.show()
        """
        # --- Generate and save the image with a grid overlay ---
        plt.figure(figsize=(12, 16))
        plt.imshow(image)
        plt.title(f"Page {page_num + 1} with Coordinate Grid")
        plt.grid(True, which='both', color='red', linestyle='--', linewidth=0.5)
        plt.xticks(range(0, image.width, 200))
        plt.yticks(range(0, image.height, 200))
        plt.xlabel('X coordinate (pixels)')
        plt.ylabel('Y coordinate (pixels)')
        
        # Save the figure to a file instead of displaying it
        grid_image_filename = f"page_{page_num + 1}_with_grid.png"
        plt.savefig(grid_image_filename)
        plt.close() # Close the plot to free memory
        print(f"Generated grid image: {grid_image_filename}")
        # --- End of new code block ---
        """
        if pageNumberDiabeticReport is None:
            region_diabetic = image.crop(diabetic_report_coords)
            #region_diabetic.show()
            text_diabetic = pytesseract.image_to_string(region_diabetic).lower()
            if "diabetic" in text_diabetic:
                pageNumberDiabeticReport = page_num + 1
                diabeticresult_area = image.crop(diabetic_result_coords)
                #diabeticresult_area.show()  
                text_diabetic_result = pytesseract.image_to_string(diabeticresult_area)
                diabetic_qual_area = image.crop(diabetic_qual_coords)
                text_diabetic_qual_result = pytesseract.image_to_string(diabetic_qual_area)

                # EXTRACT DIABETIC RESULTS from cooridnates - 

        if pageNumberGlaucomaReport is None:
            region_glaucoma = image.crop(glaucoma_report_coords)
            text_glaucoma = pytesseract.image_to_string(region_glaucoma).lower()
            if "glaucoma" in text_glaucoma:
                pageNumberGlaucomaReport = page_num + 1
                glaucoma_result_area = image.crop(glaucoma_result_coords)
                text_glaucoma_result = pytesseract.image_to_string(glaucoma_result_area)

                glaucoma_vcdrRt_area = image.crop(glaucoma_vcdr_rt_coords)
                vcdr_rt = pytesseract.image_to_string(glaucoma_vcdrRt_area)

                glaucoma_vcdrLt_area = image.crop(glaucoma_vcdr_lt_coords)
                vcdr_lt = pytesseract.image_to_string(glaucoma_vcdrLt_area)
    
                gl_qual_area = image.crop(glaucoma_qual_coords)
                #gl_qual_area.show()
                text_gl_qual_result = pytesseract.image_to_string(gl_qual_area)
                


    doc.close()
    print(f" Report for {pdf_path}")
    print(f"pageNumberDiabeticReport = {pageNumberDiabeticReport}")
    print(f"Diabetic Result ----- {text_diabetic_result} \
          WARNINGS --- {text_diabetic_qual_result}")

    print(f"pageNumberGlaucomaReport = {pageNumberGlaucomaReport}")
    print(f"Glacuaom Result = {text_glaucoma_result} VCDR RT ---{vcdr_rt} \
          VCDR LT --- {vcdr_lt} -- Qual {text_gl_qual_result} ")

    return pageNumberDiabeticReport, pageNumberGlaucomaReport, text_diabetic_result, \
        text_diabetic_qual_result, text_glaucoma_result, vcdr_rt, vcdr_lt, text_gl_qual_result


# --- Execution ---
"""
pdf_path = 'files/pdfs/17116353_Rihanna_31-01-2025_10.52.27.355_AM.pdf'

pageNumberDiabeticReport, pageNumberGlaucomaReport, text_diabetic_result, \
text_diabetic_qual_result, text_glaucoma_result, vcdr_rt, vcdr_lt, text_gl_qual_result = \
    find_report_pages_by_coords_with_grid(pdf_path)



pdf_path = 'files/pdfs/17116368_Santosh_Kumar_31-01-2025_11.48.14.032_AM.pdf'
pageNumberDiabeticReport, pageNumberGlaucomaReport, text_diabetic_result, \
text_diabetic_qual_result, text_glaucoma_result, vcdr_rt, vcdr_lt, text_gl_qual_result = find_report_pages_by_coords_with_grid(pdf_path)

pdf_path = 'files/pdfs/17116374_naresh_Kumar_31-01-2025_11.43.16.231_AM.pdf'
pageNumberDiabeticReport, pageNumberGlaucomaReport, text_diabetic_result, \
text_diabetic_qual_result, text_glaucoma_result, vcdr_rt, vcdr_lt, text_gl_qual_result = \
      find_report_pages_by_coords_with_grid(pdf_path)

pdf_path = 'files/pdfs/17116378_Zarna_31-01-2025_0.53.49.815_PM.pdf'
pageNumberDiabeticReport, pageNumberGlaucomaReport, text_diabetic_result, \
text_diabetic_qual_result, text_glaucoma_result, vcdr_rt, vcdr_lt, text_gl_qual_result = \
    find_report_pages_by_coords_with_grid(pdf_path)

pageNumberDiabeticReport, pageNumberGlaucomaReport, text_diabetic_result, \
text_diabetic_qual_result, text_glaucoma_result, vcdr_rt, vcdr_lt , text_gl_qual_result= \
      find_report_pages_by_coords_with_grid(pdf_path)
"""

