from pypdf import PdfReader
import sys

def extract_pdf_text(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        return str(e)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(extract_pdf_text(sys.argv[1]))
    else:
        print("Usage: python inspect_pdf.py <pdf_path>")
