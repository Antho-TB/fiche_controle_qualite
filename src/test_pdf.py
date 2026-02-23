import re
from pypdf import PdfReader

def extract_packing_list_data(pdf_path):
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"

    # Extraction des PO et Lots de l'en-tête
    po_header_match = re.search(r"PO\s*#\s*:\s*([\d、]+)", text)
    lot_header_match = re.search(r"N[°º]\s*Lot\s*[：:]\s*([\d、]+)", text)
    
    if not po_header_match or not lot_header_match:
        print("Erreur: Impossible de trouver les PO/Lots dans l'en-tête")
        return None
        
    po_list = [po.strip() for po in po_header_match.group(1).split("、")]
    lot_list = [lot.strip() for lot in lot_header_match.group(1).split("、")]
    
    print(f"PO trouvés: {po_list}")
    print(f"Lots trouvés: {lot_list}\n")
    
    # Mapping PO -> Lot
    po_to_lot = dict(zip(po_list, lot_list))
    
    # Recherche des articles dans les lignes
    # Format: PO:00162322821520000021970001 DESIGNATION...
    # Le PO fait 8 chiffres, le code douanier 10 chiffres (8215...), le code article
    items = []
    
    # Trouvons toutes les occurrences qui ressemblent à PO:xxxxxx
    lines = text.split("\n")
    for line in lines:
        match = re.search(r"(?i)po:\s*(\d{8})(\d{10})?(\d+)?\s*(.*)", line)
        if match:
            po = match.group(1)
            hs_code = match.group(2)
            art_code = match.group(3)
            designation = match.group(4).strip()
            
            lot = po_to_lot.get(po, "INCONNU")
            
            items.append({
                "po": po,
                "lot": lot,
                "ref_possible": art_code,
                "designation": designation
            })
            
    return items

if __name__ == "__main__":
    items = extract_packing_list_data("data/PL-SZSE2513336-SGRU2236795.pdf")
    for item in items:
        print(item)
