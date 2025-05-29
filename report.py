import streamlit as st
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

def generate_pdf_report(buffer, inputs, results):
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    x, y = 50, height - 50

    def write_line(text, indent=0):
        nonlocal y
        if y < 50:
            c.showPage()
            y = height - 50
        c.drawString(x + indent, y, text)
        y -= 15

    # Title
    c.setFont("Helvetica-Bold", 16)
    write_line("FpCalc - Seismic Design Force Report")
    c.setFont("Helvetica", 12)
    y -= 10

    write_line("📥 Input Summary", 0)
    for key, value in inputs.items():
        write_line(f"{key}: {value}", indent=20)

    y -= 10
    write_line("📊 Computation Results", 0)
    for key, value in results.items():
        write_line(f"{key}: {value}", indent=20)

    c.save()
