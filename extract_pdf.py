import sys
from pypdf import PdfReader

def main():
    try:
        reader = PdfReader('data/PL-SZSE2513336-SGRU2236795.pdf')
        with open('pdf_text.txt', 'w', encoding='utf-8') as f:
            for i, page in enumerate(reader.pages):
                f.write(f"\n--- PAGE {i+1} ---\n")
                f.write(page.extract_text())
    except Exception as e:
        print(e)

if __name__ == '__main__':
    main()
