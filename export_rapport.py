"""
EXPORT DU RAPPORT FINANCIER
PrevuFlow — SMD Global Consulting LLC

Produit un rapport telechargeable en Excel ou en PDF a partir de l'analyse.

Dependances : openpyxl (Excel) · reportlab (PDF)
"""

from __future__ import annotations

import io
from datetime import date, datetime
from decimal import Decimal

BLEU = "1F4E79"
VERT = "1F7244"
ROUGE = "C0392B"
GRIS = "F2F2F2"
POLICE = "Arial"


def _euro(v, devise: str = "EUR") -> str:
    symbole = {"EUR": "€", "USD": "$", "GBP": "£", "XOF": "FCFA",
               "CAD": "C$", "CHF": "CHF", "MAD": "DH"}.get(devise, devise)
    t = f"{abs(float(v)):,.2f}".replace(",", " ").replace(".", ",")
    return f"{'-' if float(v) < 0 else ''}{t} {symbole}"


# ---------------------------------------------------------------------------
# EXCEL
# ---------------------------------------------------------------------------

def exporter_excel(synthese, mouvements, projection=None,
                   devise: str = "EUR", titre: str = "Analyse financière") -> bytes:
    """Renvoie un classeur Excel : synthèse, postes, catégories, opérations."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    bord = Border(*[Side(style="thin", color="D9D9D9")] * 4)

    def entete(ws, colonnes, ligne=1):
        for i, h in enumerate(colonnes, 1):
            c = ws.cell(row=ligne, column=i, value=h)
            c.font = Font(name=POLICE, size=10, bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor=BLEU)
            c.alignment = Alignment(horizontal="center", vertical="center",
                                    wrap_text=True)
        ws.row_dimensions[ligne].height = 26

    # --- Feuille 1 : Synthèse ---------------------------------------------
    ws = wb.active
    ws.title = "Synthèse"
    ws["A1"] = titre
    ws["A1"].font = Font(name=POLICE, size=15, bold=True, color=BLEU)
    ws["A2"] = (f"Période du {synthese.debut.strftime('%d/%m/%Y')} "
                f"au {synthese.fin.strftime('%d/%m/%Y')} — "
                f"{synthese.nb_operations} opérations sur {synthese.nb_mois} mois")
    ws["A2"].font = Font(name=POLICE, size=9, italic=True, color="666666")

    lignes = [
        ("", ""),
        ("VOS CHIFFRES CLÉS", "par mois"),
        ("Ce qui rentre", float(synthese.entrees_par_mois)),
        ("Ce qui sort", float(synthese.sorties_par_mois)),
        ("Il vous reste", float(synthese.reste_par_mois)),
        ("", ""),
        ("Dont charges fixes", float(synthese.charges_fixes)),
        ("Dont dépenses variables", float(synthese.depenses_variables)),
        ("", ""),
        ("SUR TOUTE LA PÉRIODE", ""),
        ("Total encaissé", float(synthese.entrees)),
        ("Total dépensé", float(synthese.sorties)),
        ("Résultat de la période", float(synthese.solde_periode)),
        ("", ""),
        ("INDICATEURS", ""),
        ("Part de vos revenus mise de côté", f"{synthese.taux_epargne:.0f} %"),
        ("Part des charges fixes dans les revenus", f"{synthese.part_fixe:.0f} %"),
    ]
    for i, (lib, val) in enumerate(lignes, 4):
        cl = ws.cell(row=i, column=1, value=lib)
        titre_section = lib.isupper() and lib
        cl.font = Font(name=POLICE, size=11,
                       bold=bool(titre_section) or lib.startswith("Il vous reste"),
                       color=BLEU if titre_section else "000000")
        cv = ws.cell(row=i, column=2, value=val)
        cv.font = Font(name=POLICE, size=11,
                       bold=lib.startswith(("Il vous reste", "Résultat")),
                       color=(ROUGE if isinstance(val, float) and val < 0 else "000000"))
        if isinstance(val, float):
            cv.number_format = '#,##0.00 "€";[Red]-#,##0.00 "€"'
        cv.alignment = Alignment(horizontal="right")

    depart = len(lignes) + 5
    ws.cell(row=depart, column=1, value="CE QUE ÇA VEUT DIRE").font = \
        Font(name=POLICE, size=11, bold=True, color=BLEU)
    for i, (niveau, texte) in enumerate(synthese.messages(), depart + 1):
        couleur = {"alerte": ROUGE, "attention": "B7791F",
                   "bon": VERT}.get(niveau, "000000")
        c = ws.cell(row=i, column=1, value=texte)
        c.font = Font(name=POLICE, size=10, color=couleur)
        ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=4)
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 18

    # --- Feuille 2 : Postes ------------------------------------------------
    ws2 = wb.create_sheet("Postes")
    entete(ws2, ["Poste", "Catégorie", "Type", "Nombre",
                 "Total période", "Moyenne", "Par mois"])
    for i, p in enumerate(synthese.postes, 2):
        for j, v in enumerate([
                p.nom, p.categorie,
                "Charge fixe" if p.fixe else ("Entrée" if p.est_une_entree else "Variable"),
                p.nombre, float(p.total), float(p.moyenne), float(p.par_mois)], 1):
            c = ws2.cell(row=i, column=j, value=v)
            c.font = Font(name=POLICE, size=10)
            c.border = bord
            if j >= 5:
                c.number_format = '#,##0.00;[Red]-#,##0.00'
            if i % 2 == 0:
                c.fill = PatternFill("solid", fgColor=GRIS)
    for i, w in enumerate([34, 26, 13, 9, 15, 13, 13], 1):
        ws2.column_dimensions[get_column_letter(i)].width = w
    ws2.freeze_panes = "A2"
    ws2.auto_filter.ref = f"A1:G{len(synthese.postes) + 1}"

    # --- Feuille 3 : Catégories -------------------------------------------
    ws3 = wb.create_sheet("Catégories")
    entete(ws3, ["Catégorie", "Total période", "Par mois", "Part des dépenses"])
    total_sorties = abs(float(synthese.sorties)) or 1
    for i, (cat, tot) in enumerate(synthese.par_categorie.items(), 2):
        part = abs(float(tot)) / total_sorties if float(tot) < 0 else 0
        for j, v in enumerate([cat, float(tot),
                               float(tot) / max(synthese.nb_mois, 0.5), part], 1):
            c = ws3.cell(row=i, column=j, value=v)
            c.font = Font(name=POLICE, size=10)
            c.border = bord
            if j in (2, 3):
                c.number_format = '#,##0.00;[Red]-#,##0.00'
            if j == 4:
                c.number_format = "0.0 %"
    for i, w in enumerate([32, 16, 14, 18], 1):
        ws3.column_dimensions[get_column_letter(i)].width = w
    ws3.freeze_panes = "A2"

    # --- Feuille 4 : Opérations -------------------------------------------
    ws4 = wb.create_sheet("Opérations")
    entete(ws4, ["Date", "Libellé", "Catégorie", "Montant"])
    for i, m in enumerate(sorted(mouvements, key=lambda x: x.jour), 2):
        from analyse_lisible import categoriser
        for j, v in enumerate([m.jour, m.libelle,
                               categoriser(m.libelle, m.montant),
                               float(m.montant)], 1):
            c = ws4.cell(row=i, column=j, value=v)
            c.font = Font(name=POLICE, size=10)
            c.border = bord
            if j == 1:
                c.number_format = "DD/MM/YYYY"
            if j == 4:
                c.number_format = '#,##0.00;[Red]-#,##0.00'
    for i, w in enumerate([13, 52, 26, 14], 1):
        ws4.column_dimensions[get_column_letter(i)].width = w
    ws4.freeze_panes = "A2"
    ws4.auto_filter.ref = f"A1:D{len(mouvements) + 1}"

    # --- Feuille 5 : Prévision (facultative) ------------------------------
    if projection:
        ws5 = wb.create_sheet("Prévision")
        entete(ws5, ["Date", "Entrées", "Sorties", "Solde projeté", "Opérations"])
        for i, j_ in enumerate(projection, 2):
            for k, v in enumerate([j_.jour, float(j_.entrees), float(j_.sorties),
                                   float(j_.solde), " · ".join(j_.operations)], 1):
                c = ws5.cell(row=i, column=k, value=v)
                c.font = Font(name=POLICE, size=10)
                c.border = bord
                if k == 1:
                    c.number_format = "DD/MM/YYYY"
                if k in (2, 3, 4):
                    c.number_format = '#,##0.00;[Red]-#,##0.00'
                if k == 4 and float(j_.solde) < 0:
                    c.font = Font(name=POLICE, size=10, bold=True, color=ROUGE)
        for i, w in enumerate([13, 14, 14, 16, 46], 1):
            ws5.column_dimensions[get_column_letter(i)].width = w
        ws5.freeze_panes = "A2"

    flux = io.BytesIO()
    wb.save(flux)
    return flux.getvalue()


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def exporter_pdf(synthese, devise: str = "EUR",
                 titre: str = "Analyse financière",
                 auteur: str = "SMD Global Consulting LLC") -> bytes:
    """Renvoie un rapport PDF d'une à deux pages, lisible par un non-financier."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    flux = io.BytesIO()
    doc = SimpleDocTemplate(flux, pagesize=A4,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=titre, author=auteur)
    styles = getSampleStyleSheet()
    st_titre = ParagraphStyle("t", parent=styles["Title"], fontName="Helvetica-Bold",
                              fontSize=19, textColor=colors.HexColor("#" + BLEU),
                              alignment=0, spaceAfter=2)
    st_sous = ParagraphStyle("s", parent=styles["Normal"], fontSize=9,
                             textColor=colors.HexColor("#666666"), spaceAfter=14)
    st_h = ParagraphStyle("h", parent=styles["Heading2"], fontName="Helvetica-Bold",
                          fontSize=12, textColor=colors.HexColor("#" + BLEU),
                          spaceBefore=14, spaceAfter=6)
    st_n = ParagraphStyle("n", parent=styles["Normal"], fontSize=10, leading=15)

    contenu = [
        Paragraph(titre, st_titre),
        Paragraph(f"Période du {synthese.debut.strftime('%d/%m/%Y')} au "
                  f"{synthese.fin.strftime('%d/%m/%Y')} — {synthese.nb_operations} "
                  f"opérations sur {synthese.nb_mois} mois", st_sous),
    ]

    # Chiffres clés
    contenu.append(Paragraph("Vos chiffres clés, par mois", st_h))
    donnees = [
        ["Ce qui rentre", _euro(synthese.entrees_par_mois, devise)],
        ["Ce qui sort", _euro(synthese.sorties_par_mois, devise)],
        ["Il vous reste", _euro(synthese.reste_par_mois, devise)],
        ["dont charges fixes", _euro(synthese.charges_fixes, devise)],
        ["dont dépenses variables", _euro(synthese.depenses_variables, devise)],
    ]
    t = Table(donnees, colWidths=[105 * mm, 60 * mm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 10),
        ("FONT", (0, 2), (-1, 2), "Helvetica-Bold", 11),
        ("TEXTCOLOR", (1, 2), (1, 2),
         colors.HexColor("#" + (ROUGE if synthese.reste_par_mois < 0 else VERT))),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#DDDDDD")),
        ("LINEBELOW", (0, 2), (-1, 2), 1.0, colors.HexColor("#" + BLEU)),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LEFTINDENT", (0, 3), (0, 4), 12),
    ]))
    contenu += [t, Spacer(1, 4)]

    # Ce que ça veut dire
    contenu.append(Paragraph("Ce que ça veut dire", st_h))
    for niveau, texte in synthese.messages():
        puce = {"alerte": "▲", "attention": "▲", "bon": "●"}.get(niveau, "•")
        couleur = {"alerte": ROUGE, "attention": "B7791F", "bon": VERT}.get(niveau, "333333")
        contenu.append(Paragraph(
            f'<font color="#{couleur}">{puce}</font> {texte}', st_n))
        contenu.append(Spacer(1, 3))

    # Principaux postes
    contenu.append(Paragraph("Vos principaux postes", st_h))
    lignes = [["Poste", "Catégorie", "Par mois"]]
    for p in synthese.postes[:12]:
        lignes.append([p.nom[:30], p.categorie[:24], _euro(p.par_mois, devise)])
    t2 = Table(lignes, colWidths=[62 * mm, 62 * mm, 41 * mm], repeatRows=1)
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#" + BLEU)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F7F7")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DDDDDD")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    contenu.append(t2)

    # Répartition par catégorie
    contenu.append(Paragraph("Répartition par catégorie", st_h))
    total_sorties = abs(float(synthese.sorties)) or 1
    lignes3 = [["Catégorie", "Total période", "Part"]]
    for cat, tot in list(synthese.par_categorie.items())[:12]:
        part = f"{abs(float(tot)) / total_sorties * 100:.0f} %" if float(tot) < 0 else "—"
        lignes3.append([cat[:34], _euro(tot, devise), part])
    t3 = Table(lignes3, colWidths=[85 * mm, 50 * mm, 30 * mm], repeatRows=1)
    t3.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#" + BLEU)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F7F7")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DDDDDD")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    contenu.append(t3)

    contenu += [
        Spacer(1, 12),
        Paragraph(
            f'<font size="7.5" color="#888888">Rapport établi le '
            f'{datetime.now().strftime("%d/%m/%Y")} par {auteur}. '
            f'Analyse produite automatiquement à partir des documents fournis. '
            f'Les projections sont indicatives et doivent être validées avant '
            f'toute décision.</font>', st_n),
    ]

    doc.build(contenu)
    return flux.getvalue()


# ---------------------------------------------------------------------------
# WORD — rapport modifiable
# ---------------------------------------------------------------------------

def exporter_word(synthese, devise: str = "EUR",
                  titre: str = "Analyse financière",
                  auteur: str = "SMD Global Consulting LLC") -> bytes:
    """
    Rapport Word modifiable, pour que l'utilisateur puisse le personnaliser
    avant de le transmettre a son banquier, son comptable ou son associe.

    Dependance : python-docx
    """
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor, Cm

    def _rgb(hexa: str) -> RGBColor:
        return RGBColor(int(hexa[0:2], 16), int(hexa[2:4], 16), int(hexa[4:6], 16))

    doc = Document()

    for section in doc.sections:
        section.top_margin = section.bottom_margin = Cm(2)
        section.left_margin = section.right_margin = Cm(2)

    normal = doc.styles["Normal"]
    normal.font.name = POLICE
    normal.font.size = Pt(10.5)

    # --- Titre ---
    t = doc.add_paragraph()
    r = t.add_run(titre)
    r.font.size = Pt(20)
    r.font.bold = True
    r.font.color.rgb = _rgb(BLEU)

    st_ = doc.add_paragraph()
    r = st_.add_run(f"Établi le {date.today().strftime('%d/%m/%Y')} — {auteur}")
    r.font.size = Pt(9)
    r.font.color.rgb = _rgb("808080")

    # --- Chiffres cles ---
    doc.add_paragraph()
    h = doc.add_paragraph()
    r = h.add_run("Vos chiffres, chaque mois")
    r.font.size = Pt(13); r.font.bold = True; r.font.color.rgb = _rgb(BLEU)

    lignes = [
        ("Ce qui rentre",       synthese.entrees_par_mois,   VERT),
        ("Ce qui sort",         -abs(synthese.sorties_par_mois), ROUGE),
        ("Il vous reste",       synthese.reste_par_mois,
         VERT if float(synthese.reste_par_mois) >= 0 else ROUGE),
        ("dont charges fixes",  -abs(synthese.charges_fixes), "404040"),
        ("dont depenses variables", -abs(synthese.depenses_variables), "404040"),
    ]

    tab = doc.add_table(rows=0, cols=2)
    tab.style = "Table Grid"
    for libelle, valeur, couleur in lignes:
        row = tab.add_row().cells
        p = row[0].paragraphs[0]
        rr = p.add_run(libelle)
        rr.font.size = Pt(10.5)
        if libelle.startswith("dont"):
            rr.font.italic = True
        p2 = row[1].paragraphs[0]
        p2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        rr2 = p2.add_run(_euro(valeur, devise))
        rr2.font.size = Pt(10.5); rr2.font.bold = True
        rr2.font.color.rgb = _rgb(couleur)

    # --- Ce que ca veut dire ---
    doc.add_paragraph()
    h = doc.add_paragraph()
    r = h.add_run("Ce que cela veut dire")
    r.font.size = Pt(13); r.font.bold = True; r.font.color.rgb = _rgb(BLEU)

    for niveau, texte in synthese.messages():
        p = doc.add_paragraph(style="List Bullet")
        rr = p.add_run(texte)
        rr.font.size = Pt(10.5)
        if niveau == "alerte":
            rr.font.color.rgb = _rgb(ROUGE); rr.font.bold = True
        elif niveau == "bon":
            rr.font.color.rgb = _rgb(VERT)

    # --- Principaux postes ---
    doc.add_paragraph()
    h = doc.add_paragraph()
    r = h.add_run("Vos principaux postes")
    r.font.size = Pt(13); r.font.bold = True; r.font.color.rgb = _rgb(BLEU)

    tp = doc.add_table(rows=1, cols=4)
    tp.style = "Table Grid"
    for i, entete in enumerate(["Poste", "Catégorie", "Nature", "Par mois"]):
        c = tp.rows[0].cells[i].paragraphs[0]
        if i == 3:
            c.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        rr = c.add_run(entete)
        rr.font.bold = True; rr.font.size = Pt(10)
        rr.font.color.rgb = _rgb("FFFFFF")
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement
        shd = OxmlElement("w:shd")
        shd.set(qn("w:fill"), BLEU)
        tp.rows[0].cells[i]._tc.get_or_add_tcPr().append(shd)

    for p_ in synthese.postes[:15]:
        row = tp.add_row().cells
        nature = ("Entrée" if p_.est_une_entree
                  else "Charge fixe" if p_.fixe else "Variable")
        for i, val in enumerate([p_.nom, p_.categorie, nature,
                                 _euro(p_.par_mois, devise)]):
            par = row[i].paragraphs[0]
            if i == 3:
                par.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            rr = par.add_run(str(val))
            rr.font.size = Pt(9.5)
            if i == 3:
                rr.font.bold = True
                rr.font.color.rgb = _rgb(VERT if p_.est_une_entree else ROUGE)

    # --- Repartition par categorie ---
    doc.add_paragraph()
    h = doc.add_paragraph()
    r = h.add_run("Répartition de vos dépenses")
    r.font.size = Pt(13); r.font.bold = True; r.font.color.rgb = _rgb(BLEU)

    depenses = sorted(((k, abs(float(v))) for k, v in synthese.par_categorie.items()
                       if float(v) < 0), key=lambda x: -x[1])
    total = sum(v for _, v in depenses) or 1

    tc = doc.add_table(rows=0, cols=3)
    tc.style = "Table Grid"
    for nom, valeur in depenses:
        row = tc.add_row().cells
        row[0].paragraphs[0].add_run(nom).font.size = Pt(9.5)
        p2 = row[1].paragraphs[0]; p2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p2.add_run(_euro(-valeur, devise)).font.size = Pt(9.5)
        p3 = row[2].paragraphs[0]; p3.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p3.add_run(f"{valeur / total:.0%}").font.size = Pt(9.5)

    # --- Pied ---
    doc.add_paragraph()
    p = doc.add_paragraph()
    rr = p.add_run("Rapport généré par le PrevuFlow. Les montants sont "
                   "issus des mouvements importés et doivent être validés.")
    rr.font.size = Pt(8); rr.font.italic = True
    rr.font.color.rgb = _rgb("808080")

    tampon = io.BytesIO()
    doc.save(tampon)
    return tampon.getvalue()


# ---------------------------------------------------------------------------
# EXCEL — profil entreprise
# ---------------------------------------------------------------------------

def exporter_entreprise_excel(indicateurs, synthese=None, mouvements=None,
                              devise: str = "EUR",
                              titre: str = "Analyse financière") -> bytes:
    """
    Classeur destine a un dirigeant, un banquier ou un investisseur.

    Feuille 1 : les indicateurs et leur lecture en clair.
    Feuille 2 : la repartition du chiffre d'affaires par client.
    Feuille 3 : les postes de depense, si un releve a ete importe.
    Feuille 4 : le detail des mouvements.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    i = indicateurs
    classeur = Workbook()

    titre_f = Font(name=POLICE, size=15, bold=True, color=BLEU)
    section_f = Font(name=POLICE, size=11, bold=True, color="FFFFFF")
    normal_f = Font(name=POLICE, size=10)
    gras_f = Font(name=POLICE, size=10, bold=True)
    fond_bleu = PatternFill("solid", fgColor=BLEU)
    fond_gris = PatternFill("solid", fgColor=GRIS)
    bord = Border(*(Side(style="thin", color="D9D9D9"),) * 4)
    droite = Alignment(horizontal="right")
    fmt = f'# ##0.00 "{_euro(0, devise).split()[-1]}"'

    def entete(f, ligne, colonnes, largeurs):
        for n, (texte, larg) in enumerate(zip(colonnes, largeurs), start=1):
            c = f.cell(row=ligne, column=n, value=texte)
            c.font = section_f
            c.fill = fond_bleu
            f.column_dimensions[get_column_letter(n)].width = larg

    # ---------------- Feuille 1 : indicateurs ----------------
    f = classeur.active
    f.title = "Indicateurs"
    f["A1"] = titre
    f["A1"].font = titre_f
    f["A2"] = (f"Période du {i.debut.strftime('%d/%m/%Y')} au "
               f"{i.fin.strftime('%d/%m/%Y')} — {i.nb_mois:.1f} mois. "
               f"Montants ramenés au mois.")
    f["A2"].font = Font(name=POLICE, size=9, italic=True, color="808080")
    f["A3"] = f"Établi le {date.today().strftime('%d/%m/%Y')}"
    f["A3"].font = Font(name=POLICE, size=9, color="808080")

    ligne = 5
    blocs = [
        ("ACTIVITÉ", [
            ("Encaissé par mois", i.encaissements_par_mois, "argent réellement reçu"),
            ("Décaissé par mois", i.decaissements_par_mois, "argent réellement sorti"),
            ("Résultat par mois", i.resultat_par_mois, f"{i.marge:.0f} % des encaissements"),
            ("Croissance mensuelle",
             f"{i.croissance:.1f} %" if i.croissance is not None else "—",
             "moyenne d'un mois sur l'autre"),
        ]),
        ("STRUCTURE DE COÛTS", [
            ("Charges fixes", i.charges_fixes, f"{i.part_fixe:.0f} % des charges"),
            ("Charges variables", i.charges_variables, "sur lesquelles agir"),
            ("Point d'équilibre", i.point_mort if i.point_mort is not None else "—",
             "chiffre d'affaires mensuel nécessaire"),
        ]),
        ("TRÉSORERIE", [
            ("Trésorerie", i.tresorerie, "solde de départ"),
            ("Résultat mensuel", i.burn_rate,
             "négatif = perte mensuelle (burn rate)"),
            ("Autonomie",
             f"{i.runway_mois:.1f} mois" if i.runway_mois is not None
             else ("illimitée" if i.resultat_par_mois >= 0 else "—"),
             "avant épuisement de la trésorerie (runway)"),
        ]),
        ("CLIENTS", [
            ("Facturé", i.ca_facture, "sur la période"),
            ("Reste à encaisser", i.encours_client, "factures non réglées"),
            ("Dont en retard", i.retard_client, "échéance dépassée"),
            ("Délai d'encaissement",
             f"{i.dso:.0f} jours" if i.dso is not None else "—",
             "moyenne pondérée par les montants (DSO)"),
            ("Taux de recouvrement",
             f"{i.taux_recouvrement:.0f} %" if i.taux_recouvrement is not None else "—",
             "part des factures encaissées"),
            ("Dépendance au 1er client", f"{i.dependance_premier_client:.0f} %",
             "part du plus gros client"),
        ]),
        ("FOURNISSEURS", [
            ("Facturé par vos fournisseurs", i.achats_factures, "sur la période"),
            ("Reste à payer", i.encours_fournisseur, "dettes non réglées"),
            ("Délai de paiement",
             f"{i.dpo:.0f} jours" if i.dpo is not None else "—",
             "moyenne pondérée par les montants (DPO)"),
            ("Écart de financement",
             f"{i.ecart_de_financement:.0f} jours"
             if i.ecart_de_financement is not None else "—",
             "positif = vous financez vos clients"),
        ]),
    ]

    for nom, elements in blocs:
        entete(f, ligne, [nom, "", ""], [34, 18, 46])
        ligne += 1
        for libelle, valeur, note in elements:
            f.cell(row=ligne, column=1, value=libelle).font = normal_f
            c = f.cell(row=ligne, column=2, value=(float(valeur)
                       if isinstance(valeur, (int, float, Decimal)) else valeur))
            c.font = gras_f
            c.alignment = droite
            if isinstance(valeur, (int, float, Decimal)):
                c.number_format = fmt
                c.font = Font(name=POLICE, size=10, bold=True,
                              color=VERT if float(valeur) >= 0 else ROUGE)
            n = f.cell(row=ligne, column=3, value=note)
            n.font = Font(name=POLICE, size=9, italic=True, color="808080")
            for col in (1, 2, 3):
                f.cell(row=ligne, column=col).border = bord
            ligne += 1
        ligne += 1

    entete(f, ligne, ["CE QUE CELA VEUT DIRE", "", ""], [34, 18, 46])
    ligne += 1
    for niveau, texte in i.messages():
        c = f.cell(row=ligne, column=1, value=texte)
        c.font = Font(name=POLICE, size=10,
                      bold=(niveau == "alerte"),
                      color={"alerte": ROUGE, "bon": VERT}.get(niveau, "404040"))
        c.alignment = Alignment(wrap_text=True, vertical="top")
        f.merge_cells(start_row=ligne, start_column=1, end_row=ligne, end_column=3)
        f.row_dimensions[ligne].height = 30
        ligne += 1

    # ---------------- Feuille 2 : clients ----------------
    if i.concentration:
        fc = classeur.create_sheet("Clients")
        fc["A1"] = "Répartition du chiffre d'affaires"
        fc["A1"].font = titre_f
        entete(fc, 3, ["Client", "Montant facturé", "Part du CA"], [38, 20, 14])
        for n, c_ in enumerate(i.concentration, start=4):
            fc.cell(row=n, column=1, value=c_.tiers).font = normal_f
            v = fc.cell(row=n, column=2, value=float(c_.montant))
            v.font = gras_f; v.number_format = fmt; v.alignment = droite
            p = fc.cell(row=n, column=3, value=c_.part)
            p.number_format = "0 %"; p.alignment = droite
            p.font = Font(name=POLICE, size=10, bold=True,
                          color=ROUGE if c_.part > 0.3 else "404040")
            if c_.part > 0.3:
                for col in (1, 2, 3):
                    fc.cell(row=n, column=col).fill = fond_gris

    # ---------------- Feuille 3 : postes ----------------
    if synthese is not None and getattr(synthese, "postes", None):
        fp = classeur.create_sheet("Postes")
        fp["A1"] = "Vos postes de dépense et de recette"
        fp["A1"].font = titre_f
        entete(fp, 3, ["Poste", "Catégorie", "Nature", "Nombre", "Par mois"],
               [32, 26, 14, 10, 16])
        for n, p in enumerate(synthese.postes, start=4):
            fp.cell(row=n, column=1, value=p.nom).font = normal_f
            fp.cell(row=n, column=2, value=p.categorie).font = normal_f
            fp.cell(row=n, column=3,
                    value=("Entrée" if p.est_une_entree
                           else "Charge fixe" if p.fixe else "Variable")).font = normal_f
            fp.cell(row=n, column=4, value=p.nombre).alignment = droite
            v = fp.cell(row=n, column=5, value=float(p.par_mois))
            v.number_format = fmt; v.alignment = droite
            v.font = Font(name=POLICE, size=10, bold=True,
                          color=VERT if p.est_une_entree else ROUGE)

    # ---------------- Feuille 4 : mouvements ----------------
    if mouvements:
        fm = classeur.create_sheet("Opérations")
        entete(fm, 1, ["Date", "Libellé", "Montant"], [14, 60, 18])
        for n, m in enumerate(sorted(mouvements, key=lambda x: x.jour), start=2):
            fm.cell(row=n, column=1, value=m.jour).number_format = "DD/MM/YYYY"
            fm.cell(row=n, column=2, value=m.libelle).font = normal_f
            v = fm.cell(row=n, column=3, value=float(m.montant))
            v.number_format = fmt; v.alignment = droite
            v.font = Font(name=POLICE, size=10,
                          color=VERT if m.montant > 0 else ROUGE)
        fm.freeze_panes = "A2"
        fm.auto_filter.ref = f"A1:C{len(mouvements) + 1}"

    tampon = io.BytesIO()
    classeur.save(tampon)
    return tampon.getvalue()
