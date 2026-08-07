"""
Verification du moteur de scenarios.
Chaque attendu est calcule a la main dans le commentaire qui le precede.

Lancer :  py test_scenarios.py
"""

from datetime import date, timedelta
from decimal import Decimal

from moteur_tresorerie import Recurrence
from scenarios import Hypothese, Scenario, comparer, modeles, projeter_scenario

TAUX = {"EUR": Decimal("1"), "USD": Decimal("0.92")}
DEBUT = date(2026, 1, 1)

ok, ko = 0, []


def verifier(nom, obtenu, attendu, tolerance=0.01):
    global ok
    if attendu is None:
        reussi = obtenu is None
    elif isinstance(attendu, bool):
        reussi = obtenu is attendu
    elif isinstance(attendu, (int, float, Decimal)) and obtenu is not None:
        reussi = abs(float(obtenu) - float(attendu)) <= tolerance
    else:
        reussi = obtenu == attendu
    if reussi:
        ok += 1
        print(f"  ok    {nom}")
    else:
        ko.append(nom)
        print(f"  ECHEC {nom} : obtenu {obtenu!r}, attendu {attendu!r}")


def ops_de_base():
    """Salaire 3 000 le 5, loyer -1 000 le 10, courses -400 le 15. Tout mensuel."""
    return [
        {"libelle": "Salaire", "montant": 3000.0, "date": date(2026, 1, 5),
         "devise": "EUR", "recurrence": Recurrence.MENSUELLE, "date_fin": None,
         "certaine": True},
        {"libelle": "Loyer", "montant": -1000.0, "date": date(2026, 1, 10),
         "devise": "EUR", "recurrence": Recurrence.MENSUELLE, "date_fin": None,
         "certaine": True},
        {"libelle": "Courses", "montant": -400.0, "date": date(2026, 1, 15),
         "devise": "EUR", "recurrence": Recurrence.MENSUELLE, "date_fin": None,
         "certaine": True},
    ]


def projeter(scenario, solde=2000.0, jours=90):
    return projeter_scenario(scenario, ops_de_base(), solde, "EUR", TAUX, DEBUT, jours)


# ---------------------------------------------------------------------------
print("\n1. Le cas de base")
# ---------------------------------------------------------------------------

# 90 jours a partir du 01/01 : le 31/03 inclus.
# Salaire les 5/1, 5/2, 5/3 = +9 000 ; loyer les 10 = -3 000 ;
# courses les 15 = -1 200. Solde = 2 000 + 9 000 - 4 200 = 6 800.
base = projeter(Scenario("Base"))
verifier("solde final = 6 800", base.solde_final, 6800)
verifier("aucun decouvert", base.tient, True)
verifier("90 points de courbe", len(base.courbe), 90)


# ---------------------------------------------------------------------------
print("\n2. Hypothese « varier »")
# ---------------------------------------------------------------------------

# Entrees -20 % : salaire 2 400. 2 000 + 7 200 - 4 200 = 5 000.
r = projeter(Scenario("Revenus -20 %", [Hypothese("varier", -20, portee="entrees")]))
verifier("entrees -20 % : solde = 5 000", r.solde_final, 5000)

# Sorties +10 % : loyer 1 100 et courses 440 -> -4 620.
# 2 000 + 9 000 - 4 620 = 6 380.
r = projeter(Scenario("Charges +10 %", [Hypothese("varier", 10, portee="sorties")]))
verifier("sorties +10 % : solde = 6 380", r.solde_final, 6380)

# Cible precise : seules les courses baissent de 50 % -> -600 au lieu de -1 200.
# 2 000 + 9 000 - 3 000 - 600 = 7 400.
r = projeter(Scenario("Courses -50 %",
                      [Hypothese("varier", -50, cible="Courses", portee="sorties")]))
verifier("cible « Courses » seule : solde = 7 400", r.solde_final, 7400)

# La cible ne doit pas toucher le reste.
verifier("le loyer n'a pas bouge", r.solde_final != 6800, True)


# ---------------------------------------------------------------------------
print("\n3. Hypothese « supprimer »")
# ---------------------------------------------------------------------------

# Plus de salaire : 2 000 - 4 200 = -2 200.
r = projeter(Scenario("Sans salaire",
                      [Hypothese("supprimer", cible="Salaire", portee="entrees")]))
verifier("sans salaire : solde = -2 200", r.solde_final, -2200)
verifier("decouvert detecte", r.tient, False)

# Solde 2 000. Le 10/01 : -1 000 -> 1 000. Le 15/01 : -400 -> 600.
# Le 10/02 : -1 000 -> -400. Premier jour negatif = 10/02/2026.
verifier("decouvert le 10/02/2026", r.premier_jour_negatif, date(2026, 2, 10))
verifier("soit dans 40 jours", r.jours_avant_negatif, 40)


# ---------------------------------------------------------------------------
print("\n4. Hypothese « decaler »")
# ---------------------------------------------------------------------------

# Salaire decale de 30 j : 5/2, 5/3 dans la fenetre -> 2 salaires au lieu de 3.
# Le 5/4 tombe hors des 90 jours. 2 000 + 6 000 - 4 200 = 3 800.
r = projeter(Scenario("Paiement +30 j",
                      [Hypothese("decaler", 30, portee="entrees")]))
verifier("decalage 30 j : solde = 3 800", r.solde_final, 3800)
verifier("le decalage n'affecte pas les sorties", float(r.solde_final) > 0, True)


# ---------------------------------------------------------------------------
print("\n5. Hypothese « ajouter »")
# ---------------------------------------------------------------------------

# Charge mensuelle de -500 a partir du 20/01 : 20/1, 20/2, 20/3 = -1 500.
# 6 800 - 1 500 = 5 300.
r = projeter(Scenario("Embauche", [Hypothese(
    "ajouter", -500, libelle_ajout="Salaire junior",
    date_ajout=date(2026, 1, 20), recurrence_ajout=Recurrence.MENSUELLE)]))
verifier("charge mensuelle ajoutee : solde = 5 300", r.solde_final, 5300)

# Depense unique de -2 000 le 20/01. 6 800 - 2 000 = 4 800.
r = projeter(Scenario("Imprévu", [Hypothese(
    "ajouter", -2000, libelle_ajout="Imprévu", date_ajout=date(2026, 1, 20),
    recurrence_ajout=Recurrence.PONCTUELLE)]))
verifier("depense unique : solde = 4 800", r.solde_final, 4800)


# ---------------------------------------------------------------------------
print("\n6. Hypothese « solde »")
# ---------------------------------------------------------------------------

# Trésorerie de depart ramenee a 500 : 500 + 9 000 - 4 200 = 5 300.
r = projeter(Scenario("Moins de départ", [Hypothese("solde", 500)]))
verifier("solde de depart force : solde = 5 300", r.solde_final, 5300)


# ---------------------------------------------------------------------------
print("\n7. Hypotheses cumulees")
# ---------------------------------------------------------------------------

# -25 % sur les entrees (2 250 x 3 = 6 750) et +10 % sur les sorties (-4 620).
# 2 000 + 6 750 - 4 620 = 4 130.
r = projeter(Scenario("Pire des cas",
                      [Hypothese("varier", -25, portee="entrees"),
                       Hypothese("varier", 10, portee="sorties")]))
verifier("deux hypotheses cumulees : solde = 4 130", r.solde_final, 4130)


# ---------------------------------------------------------------------------
print("\n8. Le scenario ne modifie jamais les donnees d'origine")
# ---------------------------------------------------------------------------

originales = ops_de_base()
avant = [dict(o) for o in originales]
s = Scenario("Test", [Hypothese("varier", -50, portee="tout"),
                      Hypothese("supprimer", cible="Loyer")])
s.appliquer(originales, 2000.0)
verifier("nombre d'operations inchange", len(originales), 3)
verifier("montants inchanges",
         [o["montant"] for o in originales], [o["montant"] for o in avant])
verifier("dates inchangees",
         [o["date"] for o in originales], [o["date"] for o in avant])


# ---------------------------------------------------------------------------
print("\n9. Comparaison")
# ---------------------------------------------------------------------------

resultats = comparer(
    [Scenario("A", [Hypothese("varier", -20, portee="entrees")]),
     Scenario("B", [Hypothese("supprimer", cible="Salaire")])],
    ops_de_base(), 2000.0, "EUR", TAUX, DEBUT, 90)

verifier("3 resultats (base + 2)", len(resultats), 3)
verifier("le cas de base est en tete", resultats[0].nom, "Situation actuelle")
verifier("ecart nul sur la reference", resultats[0].ecart_final, 0)
# A : 5 000 contre 6 800 -> -1 800
verifier("ecart de A = -1 800", resultats[1].ecart_final, -1800)
# B : -2 200 contre 6 800 -> -9 000
verifier("ecart de B = -9 000", resultats[2].ecart_final, -9000)
verifier("B ne tient pas", resultats[2].tient, False)
verifier("A tient", resultats[1].tient, True)


# ---------------------------------------------------------------------------
print("\n10. Verdicts et phrases")
# ---------------------------------------------------------------------------

niveau, texte = resultats[1].verdict()
verifier("verdict positif quand ca tient", niveau, "bon")
niveau, texte = resultats[2].verdict()
verifier("verdict negatif quand ca casse", niveau in ("alerte", "attention"), True)
verifier("le verdict donne une date", "2026" in texte, True)

verifier("phrase « varier » negatif",
         Hypothese("varier", -20, portee="entrees").phrase(),
         "Les entrées d'argent baissent de 20 %")
verifier("phrase « varier » positif",
         Hypothese("varier", 10, portee="sorties").phrase(),
         "Les sorties d'argent augmentent de 10 %")
verifier("phrase « supprimer » ciblee",
         Hypothese("supprimer", cible="Alpha SA").phrase(),
         "« Alpha SA » disparaît")
verifier("phrase « decaler »",
         Hypothese("decaler", 30, portee="entrees").phrase(),
         "Les entrées d'argent sont encaissées 30 jours plus tard")


# ---------------------------------------------------------------------------
print("\n11. Modeles")
# ---------------------------------------------------------------------------

ops = ops_de_base()
m_part = modeles("Particulier", ops)
m_ent = modeles("Entreprise", ops)
verifier("6 modeles particulier", len(m_part), 6)
verifier("6 modeles entreprise", len(m_ent), 6)
verifier("les catalogues different", set(m_part) != set(m_ent), True)

# Le modele doit viser le Salaire, plus grosse entree reelle.
perte = m_part["Je perds mon revenu principal"]
verifier("le modele cible la plus grosse entree",
         perte.hypotheses[0].cible, "Salaire")

r = projeter_scenario(perte, ops, 2000.0, "EUR", TAUX, DEBUT, 90)
verifier("le modele produit bien -2 200", r.solde_final, -2200)

# Sans operations, le modele doit rester utilisable.
m_vide = modeles("Entreprise", [])
verifier("modeles sans donnees : pas d'erreur", len(m_vide), 6)
r = projeter_scenario(m_vide["Je perds mon plus gros client"],
                      ops, 2000.0, "EUR", TAUX, DEBUT, 90)
verifier("repli sur -35 % des entrees", r.solde_final, 2000 + 9000 * 0.65 - 4200)

for nom, s in {**m_part, **m_ent}.items():
    verifier(f"« {nom} » se projette",
             projeter_scenario(s, ops, 2000.0, "EUR", TAUX, DEBUT, 90) is not None,
             True)
    verifier(f"« {nom} » a une explication", bool(s.explication), True)


# ---------------------------------------------------------------------------
print("\n12. Cas limites")
# ---------------------------------------------------------------------------

vide = projeter_scenario(Scenario("Rien"), [], 1000.0, "EUR", TAUX, DEBUT, 30)
verifier("aucune operation : solde inchange", vide.solde_final, 1000)
verifier("aucune operation : aucun decouvert", vide.tient, True)

r = projeter_scenario(Scenario("Cible absente",
                               [Hypothese("varier", -50, cible="Inexistant")]),
                      ops_de_base(), 2000.0, "EUR", TAUX, DEBUT, 90)
verifier("cible introuvable : rien ne change", r.solde_final, 6800)

r = projeter_scenario(Scenario("Tout supprimer", [Hypothese("supprimer")]),
                      ops_de_base(), 2000.0, "EUR", TAUX, DEBUT, 90)
verifier("tout supprimer : solde de depart", r.solde_final, 2000)


# ---------------------------------------------------------------------------
print("\n" + "=" * 62)
if ko:
    print(f"{ok} verifications reussies, {len(ko)} ECHECS :")
    for n in ko:
        print(f"   - {n}")
    raise SystemExit(1)
print(f"{ok} verifications reussies, aucun echec.")
