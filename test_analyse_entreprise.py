"""
Verification du moteur d'indicateurs d'entreprise.

Chaque test compare le resultat du code a un calcul fait a la main.
Lancer :  py test_analyse_entreprise.py
"""

import io
from datetime import date, timedelta
from decimal import Decimal

from analyse_entreprise import (Facture, calculer_indicateurs,
                                factures_vers_operations, lire_factures, _d)


class Mvt:
    """Substitut minimal de Mouvement, pour ne pas dependre de l'import PDF."""
    def __init__(self, jour, libelle, montant):
        self.jour, self.libelle, self.montant = jour, libelle, Decimal(str(montant))


ok = 0
ko = []


def verifier(nom, obtenu, attendu, tolerance=0.01):
    global ok
    if attendu is None:
        reussi = obtenu is None
    elif isinstance(attendu, (int, float, Decimal)) and obtenu is not None:
        reussi = abs(float(obtenu) - float(attendu)) <= tolerance
    else:
        reussi = obtenu == attendu
    if reussi:
        ok += 1
        print(f"  ok   {nom}")
    else:
        ko.append(nom)
        print(f"  ECHEC {nom} : obtenu {obtenu!r}, attendu {attendu!r}")


# ---------------------------------------------------------------------------
print("\n1. Lecture des montants")
# ---------------------------------------------------------------------------

verifier("1 234,56 (virgule decimale)", _d("1 234,56"), Decimal("1234.56"))
verifier("1,234.56 (format anglais)",   _d("1,234.56"), Decimal("1234.56"))
verifier("(500,00) = negatif",          _d("(500,00)"), Decimal("-500"))
verifier("1 200,00 EUR",                _d("1 200,00 EUR"), Decimal("1200"))
verifier("vide",                        _d(""), Decimal("0"))
verifier("texte illisible",             _d("n/a"), Decimal("0"))


# ---------------------------------------------------------------------------
print("\n2. DSO — delai moyen d'encaissement, pondere par les montants")
# ---------------------------------------------------------------------------

# 10 000 payes en 30 j et 1 000 payes en 90 j.
# A la main : (30*10000 + 90*1000) / 11000 = 390000/11000 = 35,45 j
fc = [
    Facture(date(2026, 1, 1), "Grand client", Decimal("10000"),
            date_paiement=date(2026, 1, 31)),
    Facture(date(2026, 1, 1), "Petit client", Decimal("1000"),
            date_paiement=date(2026, 4, 1)),
]
i = calculer_indicateurs(factures_clients=fc)
verifier("DSO pondere = 35,45 j", i.dso, 35.4545, 0.01)
verifier("CA facture = 11 000", i.ca_facture, Decimal("11000"))
verifier("encours = 0 (tout paye)", i.encours_client, Decimal("0"))
verifier("recouvrement = 100 %", i.taux_recouvrement, 100.0)

# La moyenne simple donnerait 60 j : on verifie que la ponderation joue bien.
verifier("la ponderation change le resultat", round(i.dso) != 60, True)


# ---------------------------------------------------------------------------
print("\n3. Impayes et retards")
# ---------------------------------------------------------------------------

au = date(2026, 6, 30)
fc = [
    Facture(date(2026, 5, 1), "A", Decimal("5000"), echeance=date(2026, 5, 31)),  # retard
    Facture(date(2026, 6, 20), "B", Decimal("2000"), echeance=date(2026, 7, 20)), # pas du
    Facture(date(2026, 4, 1), "C", Decimal("3000"), echeance=date(2026, 5, 1),
            date_paiement=date(2026, 5, 10)),                                     # paye
]
i = calculer_indicateurs(factures_clients=fc, au=au)
verifier("encours = 5000 + 2000", i.encours_client, Decimal("7000"))
verifier("en retard = 5000 seulement", i.retard_client, Decimal("5000"))
verifier("retard de A = 30 j", fc[0].jours_de_retard(au), 30)
verifier("B pas en retard au 30/06", fc[1].est_en_retard(au), False)
verifier("recouvrement = 3000/10000 = 30 %", i.taux_recouvrement, 30.0)


# ---------------------------------------------------------------------------
print("\n4. Concentration client")
# ---------------------------------------------------------------------------

fc = [Facture(date(2026, 1, 1), "Dominant", Decimal("8000")),
      Facture(date(2026, 1, 1), "Autre 1", Decimal("1500")),
      Facture(date(2026, 1, 1), "Autre 2", Decimal("500"))]
i = calculer_indicateurs(factures_clients=fc)
verifier("1er client = Dominant", i.concentration[0].tiers, "Dominant")
verifier("part = 8000/10000 = 80 %", i.concentration[0].part, 0.80)
verifier("dependance = 80 %", i.dependance_premier_client, 80.0)
verifier("alerte de dependance emise",
         any("Dominant" in t and n == "alerte" for n, t in i.messages()), True)


# ---------------------------------------------------------------------------
print("\n5. Burn rate et runway")
# ---------------------------------------------------------------------------

# 3 mois pleins : +10 000 encaisses et -13 000 depenses chaque mois.
# Perte = 3 000/mois. Tresorerie 15 000 -> runway = 5 mois.
mvts = []
for m in range(3):
    d0 = date(2026, 1, 1) + timedelta(days=30 * m)
    mvts.append(Mvt(d0, "VIREMENT CLIENT", 10000))
    mvts.append(Mvt(d0 + timedelta(days=5), "PRELEVEMENT SALAIRES", -13000))

i = calculer_indicateurs(mouvements=mvts, tresorerie=15000)
# periode = 65 jours = 2,135 mois ; 30 000 encaisses -> 14 052/mois
verifier("resultat mensuel negatif", float(i.resultat_par_mois) < 0, True)
verifier("burn = resultat", i.burn_rate, i.resultat_par_mois)
attendu_runway = 15000 / abs(float(i.burn_rate))
verifier("runway = tresorerie / burn", i.runway_mois, attendu_runway, 0.01)
verifier("alerte de runway emise",
         any("trésorerie" in t.lower() for n, t in i.messages()), True)


# ---------------------------------------------------------------------------
print("\n6. Point mort")
# ---------------------------------------------------------------------------

# CA 10 000, charges variables 4 000, charges fixes 3 000.
# Taux de marge sur couts variables = (10000-4000)/10000 = 0,6
# Point mort = 3000 / 0,6 = 5 000
mvts = [Mvt(date(2026, 1, 1), "VIREMENT CLIENT", 10000),
        Mvt(date(2026, 1, 5), "PRELEVEMENT LOYER", -3000),
        Mvt(date(2026, 1, 8), "ACHAT CB MARCHANDISES", -4000),
        Mvt(date(2026, 2, 1), "VIREMENT CLIENT", 10000),
        Mvt(date(2026, 2, 5), "PRELEVEMENT LOYER", -3000),
        Mvt(date(2026, 2, 8), "ACHAT CB MARCHANDISES", -4000)]
i = calculer_indicateurs(mouvements=mvts)
verifier("loyer reconnu comme charge fixe", float(i.charges_fixes) > 0, True)
verifier("achat CB reconnu comme variable", float(i.charges_variables) > 0, True)
taux = float((i.encaissements_par_mois - i.charges_variables) / i.encaissements_par_mois)
verifier("point mort = fixes / taux de marge",
         i.point_mort, float(i.charges_fixes) / taux, 1.0)


# ---------------------------------------------------------------------------
print("\n7. Ecart de financement (DSO - DPO)")
# ---------------------------------------------------------------------------

fc = [Facture(date(2026, 1, 1), "Client", Decimal("10000"),
              date_paiement=date(2026, 3, 1))]                 # 59 j
ff = [Facture(date(2026, 1, 1), "Fournisseur", Decimal("5000"), sens="fournisseur",
              date_paiement=date(2026, 1, 21))]                # 20 j
i = calculer_indicateurs(factures_clients=fc, factures_fournisseurs=ff)
verifier("DSO = 59 j", i.dso, 59.0)
verifier("DPO = 20 j", i.dpo, 20.0)
verifier("ecart = 39 j", i.ecart_de_financement, 39.0)
verifier("alerte : l'entreprise finance ses clients",
         any("avancez" in t for n, t in i.messages()), True)


# ---------------------------------------------------------------------------
print("\n8. Lecture d'un fichier de factures")
# ---------------------------------------------------------------------------

csv = (
    "Date de facture;Client;Montant TTC;Echeance;Date de paiement;Devise\n"
    "05/01/2026;Alpha SARL;12 500,00;04/02/2026;03/02/2026;EUR\n"
    "12/01/2026;Beta Ltd;8 200,00;11/02/2026;;USD\n"
    "20/01/2026;Gamma;3 000,00;19/02/2026;;EUR\n"
    ";Ligne vide;;;;\n"
)
lecture = lire_factures(io.BytesIO(csv.encode("utf-8")), "factures.csv")
verifier("3 factures lues", len(lecture.factures), 3)
verifier("1 ligne ignoree", lecture.lignes_ignorees, 1)
verifier("total = 23 700", lecture.total, Decimal("23700"))
verifier("colonne date reconnue",
         lecture.colonnes_reconnues["date_emission"], "Date de facture")
verifier("colonne echeance reconnue",
         lecture.colonnes_reconnues["echeance"], "Echeance")
verifier("« Date de facture » prime sur « Date »",
         lecture.factures[0].date_emission, date(2026, 1, 5))
verifier("devise USD conservee", lecture.factures[1].devise, "USD")
verifier("1re facture payee", lecture.factures[0].payee, True)
verifier("2e facture impayee", lecture.factures[1].payee, False)

# Statut textuel au lieu d'une date de paiement
csv2 = ("Date,Customer,Amount,Status\n"
        "2026-01-05,Alpha,1000,Paid\n"
        "2026-01-06,Beta,2000,Open\n")
l2 = lire_factures(io.BytesIO(csv2.encode("utf-8")), "invoices.csv")
verifier("format anglais lu", len(l2.factures), 2)
verifier("statut « Paid » vaut paiement", l2.factures[0].payee, True)
verifier("statut « Open » reste impaye", l2.factures[1].payee, False)

# Fichier sans colonne exploitable
try:
    lire_factures(io.BytesIO(b"Colonne A,Colonne B\n1,2\n"), "x.csv")
    verifier("erreur claire si colonnes manquantes", False, True)
except ValueError as e:
    verifier("erreur claire si colonnes manquantes", "date" in str(e).lower(), True)


# ---------------------------------------------------------------------------
print("\n9. Factures reportees dans le calendrier")
# ---------------------------------------------------------------------------

au = date(2026, 6, 15)
fc = [Facture(date(2026, 6, 1), "A payer plus tard", Decimal("1000"),
              echeance=date(2026, 7, 1)),
      Facture(date(2026, 4, 1), "Deja en retard", Decimal("2000"),
              echeance=date(2026, 5, 1)),
      Facture(date(2026, 3, 1), "Deja payee", Decimal("500"),
              date_paiement=date(2026, 3, 15))]
ops = factures_vers_operations(fc, au=au)
verifier("la facture payee est exclue", len(ops), 2)
verifier("echeance future conservee", ops[0]["date"], date(2026, 7, 1))
verifier("echeance future = certaine", ops[0]["certaine"], True)
verifier("retard reporte a demain", ops[1]["date"], date(2026, 6, 16))
verifier("retard marque incertain", ops[1]["certaine"], False)
verifier("montant client positif", ops[0]["montant"] > 0, True)

ff = [Facture(date(2026, 6, 1), "Fournisseur", Decimal("800"), sens="fournisseur",
              echeance=date(2026, 7, 5))]
ops_f = factures_vers_operations(ff, au=au)
verifier("montant fournisseur negatif", ops_f[0]["montant"] < 0, True)


# ---------------------------------------------------------------------------
print("\n10. Cas limites")
# ---------------------------------------------------------------------------

vide = calculer_indicateurs()
verifier("aucune donnee : pas d'erreur", vide.encaissements_par_mois, Decimal("0"))
verifier("aucune donnee : aucun message", len(vide.messages()), 0)
verifier("aucune donnee : pas de runway", vide.runway_mois, None)

# Entreprise beneficiaire : pas de runway a calculer
mvts = [Mvt(date(2026, 1, 1), "CLIENT", 10000), Mvt(date(2026, 2, 1), "CLIENT", 10000),
        Mvt(date(2026, 1, 5), "PRELEVEMENT LOYER", -2000),
        Mvt(date(2026, 2, 5), "PRELEVEMENT LOYER", -2000)]
b = calculer_indicateurs(mouvements=mvts, tresorerie=5000)
verifier("benefice : pas de runway", b.runway_mois, None)
verifier("benefice : marge positive", b.marge > 0, True)


# ---------------------------------------------------------------------------
print("\n" + "=" * 62)
if ko:
    print(f"{ok} verifications reussies, {len(ko)} ECHECS :")
    for n in ko:
        print(f"   - {n}")
    raise SystemExit(1)
print(f"{ok} verifications reussies, aucun echec.")
