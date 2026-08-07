"""
Verification du module argent.
Chaque attendu est calcule a la main dans le commentaire qui le precede.

Lancer :  py test_argent.py
"""

from datetime import date
from decimal import Decimal

from argent import (Conversion, DECIMALES, ESPACE_DEVISE, ESPACE_MILLIERS,
                    ErreurArgent, Montant, TableTaux, Taux, decimales, somme,
                    symbole, table_par_defaut, valider_devise)


def attendu(texte: str) -> str:
    """Traduit un attendu ecrit avec des espaces ordinaires vers les espaces
    insecables reellement produites. Le test reste lisible, le code reste juste."""
    milliers, devise = texte.rsplit(" ", 1)
    return milliers.replace(" ", ESPACE_MILLIERS) + ESPACE_DEVISE + devise

ok, ko = 0, []


def verifier(nom, obtenu, attendu):
    global ok
    reussi = (obtenu is attendu) if isinstance(attendu, bool) else (obtenu == attendu)
    if reussi:
        ok += 1
        print(f"  ok    {nom}")
    else:
        ko.append(nom)
        print(f"  ECHEC {nom} : obtenu {obtenu!r}, attendu {attendu!r}")


def leve(nom, fonction, fragment=""):
    """Verifie qu'une erreur est levee, et que son message est utile."""
    global ok
    try:
        fonction()
    except ErreurArgent as err:
        if fragment and fragment.lower() not in str(err).lower():
            ko.append(nom)
            print(f"  ECHEC {nom} : message inattendu « {err} »")
            return
        ok += 1
        print(f"  ok    {nom}")
    except Exception as err:
        ko.append(nom)
        print(f"  ECHEC {nom} : mauvaise exception {type(err).__name__} : {err}")
    else:
        ko.append(nom)
        print(f"  ECHEC {nom} : aucune erreur levee")


# ---------------------------------------------------------------------------
print("\n1. LE DEFAUT CORRIGE : un montant porte sa devise")
# ---------------------------------------------------------------------------

# C'est la correction principale. Avant, cette addition passait en silence
# et produisait un total faux.
euros = Montant.de(100, "EUR")
dollars = Montant.de(100, "USD")
leve("EUR + USD est refuse", lambda: euros + dollars, "sans conversion")
leve("EUR - USD est refuse", lambda: euros - dollars, "impossible")
leve("EUR < USD est refuse", lambda: euros < dollars, "impossible")

verifier("EUR + EUR fonctionne", (euros + Montant.de(50, "EUR")).valeur, Decimal("150"))
verifier("la devise est conservee", (euros + Montant.de(50, "EUR")).devise, "EUR")

# Le message doit dire quoi faire, pas seulement que c'est interdit.
try:
    euros + dollars
except ErreurArgent as err:
    verifier("le message propose une solution", "Convertissez" in str(err), True)


# ---------------------------------------------------------------------------
print("\n2. Codes devise")
# ---------------------------------------------------------------------------

verifier("minuscules acceptees", valider_devise("eur"), "EUR")
verifier("espaces ignores", valider_devise("  usd "), "USD")
leve("deux lettres refusees", lambda: valider_devise("EU"), "trois lettres")
leve("chiffres refuses", lambda: valider_devise("E1R"))
leve("vide refuse", lambda: valider_devise(""))
leve("devise inventee dans un montant", lambda: Montant.de(10, "XX"))


# ---------------------------------------------------------------------------
print("\n3. Decimales par devise — jamais « deux » par defaut")
# ---------------------------------------------------------------------------

verifier("EUR : 2 decimales", decimales("EUR"), 2)
verifier("JPY : 0 decimale", decimales("JPY"), 0)
verifier("XOF : 0 decimale", decimales("XOF"), 0)
verifier("KWD : 3 decimales", decimales("KWD"), 3)

# 1234,567 yens : le yen n'a pas de decimale, donc 1235 (demi-pair).
verifier("le yen s'arrondit a l'unite",
         Montant.de("1234.567", "JPY").arrondi, Decimal("1235"))
# 1234,5675 dinars : trois decimales -> 1234,568 (le chiffre suivant est 5,
# le precedent 7 est impair, le demi-pair monte a 8).
verifier("le dinar garde 3 decimales",
         Montant.de("1234.5675", "KWD").arrondi, Decimal("1234.568"))

verifier("affichage yen sans decimale",
         Montant.de(1500, "JPY").formater(), attendu("1 500 ¥"))
verifier("affichage FCFA sans decimale",
         Montant.de(250000, "XOF").formater(), attendu("250 000 FCFA"))


# ---------------------------------------------------------------------------
print("\n4. Arrondi bancaire (demi-pair)")
# ---------------------------------------------------------------------------

# 2,5 -> 2 (2 est pair) et 3,5 -> 4 (4 est pair). C'est la regle bancaire :
# elle ne favorise ni le debiteur ni le creancier sur un grand nombre d'operations.
verifier("2,5 arrondit a 2", Montant.de("2.5", "JPY").arrondi, Decimal("2"))
verifier("3,5 arrondit a 4", Montant.de("3.5", "JPY").arrondi, Decimal("4"))
verifier("1,005 arrondit a 1,00", Montant.de("1.005", "EUR").arrondi, Decimal("1.00"))
verifier("1,015 arrondit a 1,02", Montant.de("1.015", "EUR").arrondi, Decimal("1.02"))

# Le piege classique du float : 0,1 + 0,2 != 0,3 en virgule flottante.
trois_dixiemes = Montant.de("0.1", "EUR") + Montant.de("0.2", "EUR")
verifier("0,1 + 0,2 = 0,3 exactement", trois_dixiemes.valeur, Decimal("0.3"))
verifier("... alors que le float echoue", 0.1 + 0.2 == 0.3, False)

# Un float passe par str() : sinon 0.1 devient 0.10000000000000000555…
verifier("un float est converti proprement",
         Montant.de(0.1, "EUR").valeur, Decimal("0.1"))


# ---------------------------------------------------------------------------
print("\n5. Formatage")
# ---------------------------------------------------------------------------

verifier("1 234,56 €", Montant.de("1234.56", "EUR").formater(),
         attendu("1 234,56 €"))
verifier("negatif", Montant.de("-950", "EUR").formater(), attendu("-950,00 €"))
verifier("sans decimales", Montant.de("1234.56", "EUR").formater(False),
         attendu("1 235 €"))
verifier("dollar", Montant.de(2500, "USD").formater(), attendu("2 500,00 $"))
verifier("devise inconnue affiche son code",
         Montant.de(100, "PLN").formater(), attendu("100,00 PLN"))
rendu = Montant.de("1234.56", "EUR").formater()
verifier("separateur de milliers insecable", ESPACE_MILLIERS in rendu, True)
verifier("espace insecable avant le symbole", ESPACE_DEVISE in rendu, True)
verifier("aucune espace ordinaire dans un montant", " " in rendu, False)

verifier("str() equivaut a formater()",
         str(Montant.de(10, "EUR")), Montant.de(10, "EUR").formater())


# ---------------------------------------------------------------------------
print("\n6. Somme")
# ---------------------------------------------------------------------------

verifier("somme de 3 montants",
         somme([Montant.de(10, "EUR"), Montant.de(20, "EUR"),
                Montant.de(30, "EUR")], "EUR").valeur, Decimal("60"))
# Une liste vide n'a pas de devise deductible : elle est donc exigee.
verifier("somme vide = zero", somme([], "USD").valeur, Decimal("0"))
verifier("somme vide garde la devise", somme([], "USD").devise, "USD")
leve("somme de devises melangees refusee",
     lambda: somme([Montant.de(10, "EUR"), Montant.de(10, "USD")], "EUR"))


# ---------------------------------------------------------------------------
print("\n7. LE DEFAUT CORRIGE : un taux est date et source")
# ---------------------------------------------------------------------------

t = Taux("USD", "EUR", Decimal("0.92"), date(2026, 8, 1), "BCE")
verifier("le taux porte sa date", t.observe_le, date(2026, 8, 1))
verifier("le taux porte sa source", t.source, "BCE")
verifier("la phrase est lisible",
         t.phrase(), "1 USD = 0.92 EUR · 01/08/2026 · BCE")
verifier("anciennete calculee", t.anciennete(date(2026, 8, 31)), 30)

leve("taux sans source refuse",
     lambda: Taux("USD", "EUR", Decimal("0.92"), date(2026, 8, 1), ""),
     "justifié")
leve("taux negatif refuse",
     lambda: Taux("USD", "EUR", Decimal("-1"), date(2026, 8, 1), "x"))
leve("taux nul refuse",
     lambda: Taux("USD", "EUR", Decimal("0"), date(2026, 8, 1), "x"))
leve("taux d'une devise vers elle-meme refuse",
     lambda: Taux("EUR", "EUR", Decimal("1"), date(2026, 8, 1), "x"))

# L'inverse doit etre exact : 1/0,92 = 1,0869565…
verifier("inverse : base et contre permutes", (t.inverse.base, t.inverse.contre),
         ("EUR", "USD"))
verifier("inverse : produit = 1", (t.valeur * t.inverse.valeur).quantize(
    Decimal("0.0000000001")), Decimal("1.0000000000"))
verifier("inverse : date conservee", t.inverse.observe_le, date(2026, 8, 1))


# ---------------------------------------------------------------------------
print("\n8. LE DEFAUT CORRIGE : la conversion rend le taux employe")
# ---------------------------------------------------------------------------

table = TableTaux([t])

# 100 USD x 0,92 = 92,00 EUR
c = table.convertir(Montant.de(100, "USD"), "EUR")
verifier("montant converti", c.resultat.valeur, Decimal("92.00"))
verifier("devise cible", c.resultat.devise, "EUR")
verifier("le taux est rendu", c.taux.valeur, Decimal("0.92"))
verifier("la conversion est signalee", c.convertie, True)
verifier("la phrase montre le taux",
         "0.92" in c.phrase() and "01/08/2026" in c.phrase(), True)

# Convertir vers la meme devise n'est pas une conversion.
c2 = table.convertir(Montant.de(100, "EUR"), "EUR")
verifier("meme devise : aucun taux", c2.taux, None)
verifier("meme devise : montant inchange", c2.resultat.valeur, Decimal("100"))
verifier("meme devise : convertie = faux", c2.convertie, False)

# Sens inverse : 92 EUR / 0,92 = 100 USD
c3 = table.convertir(Montant.de(92, "EUR"), "USD")
verifier("conversion inverse disponible",
         c3.resultat.arrondi, Decimal("100.00"))

# Mieux vaut refuser un total que d'en afficher un faux.
leve("taux manquant : erreur explicite",
     lambda: table.convertir(Montant.de(100, "GBP"), "EUR"),
     "aucun taux connu")


# ---------------------------------------------------------------------------
print("\n9. Consolidation multidevise")
# ---------------------------------------------------------------------------

table2 = TableTaux([
    Taux("USD", "EUR", Decimal("0.92"), date(2026, 8, 1), "BCE"),
    Taux("GBP", "EUR", Decimal("1.17"), date(2026, 8, 1), "BCE"),
])

# 1 000 EUR + 1 000 USD (920 EUR) + 1 000 GBP (1 170 EUR) = 3 090 EUR
total, taux_employes = table2.consolider(
    [Montant.de(1000, "EUR"), Montant.de(1000, "USD"), Montant.de(1000, "GBP")],
    "EUR")
verifier("total consolide = 3 090", total.arrondi, Decimal("3090.00"))
verifier("devise du total", total.devise, "EUR")
verifier("2 taux employes", len(taux_employes), 2)
verifier("les taux employes sont identifiables",
         sorted(t.base for t in taux_employes), ["GBP", "USD"])

# Consolider dans une devise absente de la table doit echouer proprement.
leve("consolidation impossible signalee",
     lambda: table2.consolider([Montant.de(10, "JPY")], "EUR"))


# ---------------------------------------------------------------------------
print("\n9 bis. Triangulation — passage par une devise pivot")
# ---------------------------------------------------------------------------

# Cas reel : tous les taux sont exprimes vers l'euro, mais l'utilisateur veut
# un total en dollars. Il faut passer par l'euro. Sans cela, un portefeuille
# GBP + USD est impossible a consolider en USD.
pivot = TableTaux([
    Taux("USD", "EUR", Decimal("0.92"), date(2026, 8, 1), "BCE"),
    Taux("GBP", "EUR", Decimal("1.17"), date(2026, 7, 15), "BCE"),
])

verifier("aucun taux GBP -> USD saisi",
         ("GBP", "USD") in pivot._taux, False)

# 1 GBP = 1,17 EUR et 1 EUR = 1/0,92 USD = 1,0869565 USD
# donc 1 GBP = 1,17 x 1,0869565 = 1,2717391 USD
derive = pivot.trouver("GBP", "USD")
verifier("le taux est neanmoins trouve", derive is not None, True)
verifier("valeur triangulee correcte",
         derive.valeur.quantize(Decimal("0.0000001")), Decimal("1.2717391"))

# La provenance doit rester lisible : un taux calcule n'est pas un taux observe.
verifier("la source dit qu'il est calcule", "calculé via" in derive.source, True)
verifier("la source nomme le pivot", "EUR" in derive.source, True)
# Le resultat n'est pas plus frais que le plus ancien des deux taux employes.
verifier("la date est celle du plus ancien", derive.observe_le, date(2026, 7, 15))

# 1 000 GBP = 1 271,74 USD
c = pivot.convertir(Montant.de(1000, "GBP"), "USD")
verifier("conversion trianguleee", c.resultat.arrondi, Decimal("1271.74"))

# La triangulation ne doit pas inventer un chemin qui n'existe pas.
verifier("aucun chemin vers une devise inconnue",
         pivot.trouver("GBP", "JPY"), None)


# ---------------------------------------------------------------------------
print("\n10. Table de taux — le plus recent l'emporte")
# ---------------------------------------------------------------------------

table3 = TableTaux()
table3.ajouter(Taux("USD", "EUR", Decimal("0.90"), date(2026, 1, 1), "ancien"))
table3.ajouter(Taux("USD", "EUR", Decimal("0.95"), date(2026, 8, 1), "recent"))
verifier("le taux recent remplace l'ancien",
         table3.trouver("USD", "EUR").valeur, Decimal("0.95"))
verifier("la source suit", table3.trouver("USD", "EUR").source, "recent")

table3.ajouter(Taux("USD", "EUR", Decimal("0.80"), date(2025, 1, 1), "tres ancien"))
verifier("un taux plus ancien ne remplace pas",
         table3.trouver("USD", "EUR").valeur, Decimal("0.95"))

verifier("aucun taux d'une devise vers elle-meme",
         table3.trouver("EUR", "EUR"), None)


# ---------------------------------------------------------------------------
print("\n11. Table de repli")
# ---------------------------------------------------------------------------

defaut = table_par_defaut()
verifier("le FCFA est connu", defaut.trouver("XOF", "EUR") is not None, True)
verifier("le repli annonce sa source",
         defaut.trouver("USD", "EUR").source, "saisie manuelle")
verifier("le repli est date",
         defaut.trouver("USD", "EUR").observe_le, date(2026, 8, 1))

# 1 000 000 FCFA x 0,001524 = 1 524 EUR
c = defaut.convertir(Montant.de(1000000, "XOF"), "EUR")
verifier("1 000 000 FCFA = 1 524 EUR", c.resultat.arrondi, Decimal("1524.00"))

verifier("le plus ancien taux est identifiable",
         defaut.plus_ancien() is not None, True)


# ---------------------------------------------------------------------------
print("\n12. Immuabilite")
# ---------------------------------------------------------------------------

m = Montant.de(100, "EUR")
try:
    m.valeur = Decimal("200")
    verifier("un montant ne se modifie pas", False, True)
except Exception:
    verifier("un montant ne se modifie pas", True, True)

# Les operations rendent un nouvel objet, l'original ne bouge pas.
m2 = m + Montant.de(50, "EUR")
verifier("l'original est intact apres addition", m.valeur, Decimal("100"))
verifier("le resultat est un nouvel objet", m2.valeur, Decimal("150"))

verifier("egalite par valeur",
         Montant.de(10, "EUR") == Montant.de(10, "EUR"), True)
verifier("devises differentes ne sont pas egales",
         Montant.de(10, "EUR") == Montant.de(10, "USD"), False)


# ---------------------------------------------------------------------------
print("\n" + "=" * 62)
if ko:
    print(f"{ok} verifications reussies, {len(ko)} ECHECS :")
    for n in ko:
        print(f"   - {n}")
    raise SystemExit(1)
print(f"{ok} verifications reussies, aucun echec.")
