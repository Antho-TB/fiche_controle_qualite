import pandas as pd
import sys

def inspect_excel(excel_path):
    try:
        xl = pd.ExcelFile(excel_path)
        print(f"Sheets: {xl.sheet_names}")
        for sheet in xl.sheet_names:
            df = xl.parse(sheet)
            print(f"\nSheet: {sheet}")
            print(f"Columns: {df.columns.tolist()}")
            print(f"Head:\n{df.head(10)}")
    except Exception as e:
        print(str(e))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(inspect_excel(sys.argv[1]))
    else:
        print("Usage: python inspect_excel.py <excel_path>")
