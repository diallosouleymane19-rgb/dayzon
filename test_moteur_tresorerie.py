"""
Tests du moteur de tresorerie.
Lancer : python test_moteur_tresorerie.py
"""

from datetime import date
from decimal import Decimal
from moteur_tresorerie import (
    Tresorerie, Operation, Recurrence, TauxChange, _ajouter_mois
)

ok, ko = 0, 0

def verifier(libelle, obtenu, attendu):
    global ok, ko
    if obtenu == attendu:
        ok += 1
        print(f"  OK   {libelle}")
    else:
        ko += 1
        print(f"  ECHEC {libelle}\n        attendu : {attendu}\n        obtenu  : {obtenu}")


print("\n=== 1. Operation ponctuelle ===")
t = Tresorerie(solde_initial=1000)
t.ajouter(Operation("Vente", 500, date(2026, 8, 5)))
j = t.projeter(date(2026, 8, 1), 10)
verifier("solde avant l'operation", j[3].solde, Decimal("1000.00"))
verifier("solde le jour meme",      j[4].solde, Decimal("1500.00"))
verifier("solde apres",             j[9].solde, Decimal("1500.00"))

print("\n=== 2. Recurrence mensuelle ===")
t = Tresorerie(solde_initial=0)
t.ajouter(Operation("Abonnement", -50, date(2026, 8, 10), recurrence=Recurrence.MENSUELLE))
j = t.projeter(date(2026, 8, 1), 95)
verifier("3 prelevements en 95 jours", j[-1].solde, Decimal("-150.00"))

print("\n=== 3. Fin de mois (31 janvier -> 28 fevrier) ===")
verifier("31/01 + 1 mois", _ajouter_mois(date(2026, 1, 31), 1), date(2026, 2, 28))
verifier("31/01 + 3 mois", _ajouter_mois(date(2026, 1, 31), 3), date(2026, 4, 30))

print("\n=== 4. Detection du jour negatif ===")
t = Tresorerie(solde_initial=1000)
t.ajouter(Operation("Loyer", -800, date(2026, 8, 5), recurrence=Recurrence.MENSUELLE))
t.ajouter(Operation("Salaire", 600, date(2026, 8, 28), recurrence=Recurrence.MENSUELLE))
neg = t.premier_jour_negatif(date(2026, 8, 1), 120)
verifier("un jour negatif est detecte", neg is not None, True)
# Deroule : 1000 -800(05/08)=200 +600(28/08)=800 -800(05/09)=0 (pas negatif)
#           +600(28/09)=600 -800(05/10)=-200 -> premier jour negatif
verifier("date du premier jour negatif", neg.jour, date(2026, 10, 5))
verifier("solde ce jour-la", neg.solde, Decimal("-200.00"))

print("\n=== 5. Multi-devises ===")
taux = TauxChange("EUR", {"USD": 0.92, "XOF": 0.001524})
t = Tresorerie(solde_initial=0, devise="EUR", taux=taux)
t.ajouter(Operation("Client US",  1000, date(2026, 8, 10), devise="USD"))
t.ajouter(Operation("Client Dakar", 500000, date(2026, 8, 10), devise="XOF"))
j = t.projeter(date(2026, 8, 1), 20)
verifier("1000 USD + 500000 XOF convertis", j[9].solde, Decimal("1682.00"))

print("\n=== 6. Operations incertaines ===")
t = Tresorerie(solde_initial=0)
t.ajouter(Operation("Facture signee", 1000, date(2026, 8, 5), certaine=True))
t.ajouter(Operation("Devis en cours",  5000, date(2026, 8, 6), certaine=False))
avec   = t.projeter(date(2026, 8, 1), 10, inclure_incertain=True)[-1].solde
sans   = t.projeter(date(2026, 8, 1), 10, inclure_incertain=False)[-1].solde
verifier("avec l'incertain",  avec, Decimal("6000.00"))
verifier("sans l'incertain",  sans, Decimal("1000.00"))

print("\n=== 7. Date de fin d'une recurrence ===")
t = Tresorerie(solde_initial=0)
t.ajouter(Operation("Credit", -200, date(2026, 8, 1),
                    recurrence=Recurrence.MENSUELLE, date_fin=date(2026, 10, 1)))
j = t.projeter(date(2026, 8, 1), 180)
verifier("3 echeances puis plus rien", j[-1].solde, Decimal("-600.00"))

print("\n=== 8. Synthese ===")
t = Tresorerie(solde_initial=5000, devise="EUR")
t.ajouter_plusieurs([
    Operation("Clients",     12000, date(2026, 8, 15), recurrence=Recurrence.MENSUELLE),
    Operation("Salaires",    -7000, date(2026, 8, 28), recurrence=Recurrence.MENSUELLE),
    Operation("Loyer",       -1500, date(2026, 8, 5),  recurrence=Recurrence.MENSUELLE),
    Operation("Fournisseur", -9000, date(2026, 9, 10)),
])
s = t.synthese(date(2026, 8, 1), 90)
verifier("devise",        s["devise"], "EUR")
verifier("solde initial", s["solde_initial"], Decimal("5000.00"))
verifier("une alerte est levee", s["alerte"], True)
print(f"\n  Solde final     : {s['solde_final']} {s['devise']}")
print(f"  Point bas       : {s['solde_minimum']} le {s['date_solde_min']}")
print(f"  Premier negatif : {s['premier_jour_negatif']} "
      f"(dans {s['jours_avant_negatif']} jours)")

print("\n" + "="*52)
print(f"  {ok} tests reussis, {ko} echecs")
print("="*52)
raise SystemExit(1 if ko else 0)
