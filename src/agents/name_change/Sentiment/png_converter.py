import fitz  # PyMuPDF

doc = fitz.open("Aadhar Card.pdf")

page = doc.load_page(0)   # first page
pix = page.get_pixmap(dpi=300)

pix.save("aadhar.png")

print("Converted successfully")
