"""
Verification du multi-comptes.
Chaque attendu est calcule a la main dans le commentaire qui le precede.

Lancer :  py test_comptes.py
"""

from datetime import date
from decimal import Decimal

from argent import ErreurArgent, Montant, TableTaux, Taux
from comptes import (Compte, ErreurCompte, Portefeuille,
                     portefeuille_depuis_solde_unique)

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
    global ok
    try:
        fonction()
    except (ErreurCompte, ErreurArgent) as err:
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


def taux_de_test() -> TableTaux:
    return TableTaux([
        Taux("USD", "EUR", Decimal("0.92"), date(2026, 8, 1), "BCE"),
        Taux("GBP", "EUR", Decimal("1.17"), date(2026, 7, 15), "BCE"),
        Taux("XOF", "EUR", Decimal("0.001524"), date(2026, 8, 1), "BCEAO"),
    ])


# ---------------------------------------------------------------------------
print("\n1. Un compte")
# ---------------------------------------------------------------------------

c = Compte("Compte courant", "EUR", Decimal("8472.30"),
           pays="France", etablissement="Crédit Agricole")
verifier("le solde est un Montant", c.montant.valeur, Decimal("8472.30"))
verifier("le montant porte la devise du compte", c.montant.devise, "EUR")
verifier("libelle lisible", c.libelle, "Compte courant · Crédit Agricole · EUR")
verifier("identifiant genere", len(c.identifiant), 8)
verifier("actif par defaut", c.actif, True)

verifier("solde entier accepte", Compte("X", "EUR", 100).solde, Decimal("100"))
verifier("solde texte accepte", Compte("X", "EUR", "100.50").solde, Decimal("100.50"))

leve("nom vide refuse", lambda: Compte("", "EUR"), "nom")
leve("nom d'espaces refuse", lambda: Compte("   ", "EUR"))
leve("devise invalide refusee", lambda: Compte("X", "EURO"))

# Crediter dans la mauvaise devise doit echouer : c'est le meme defaut
# que l'addition inter-devises, applique a un compte.
c2 = Compte("Test", "EUR", Decimal("100"))
c2.crediter(Montant.de(50, "EUR"))
verifier("credit en devise du compte", c2.solde, Decimal("150"))
leve("credit en devise etrangere refuse",
     lambda: c2.crediter(Montant.de(50, "USD")), "convertissez")


# ---------------------------------------------------------------------------
print("\n2. Le portefeuille")
# ---------------------------------------------------------------------------

p = Portefeuille(devise_reference="EUR")
verifier("portefeuille vide", p.vide, True)
verifier("aucune devise", p.devises, [])

p.ajouter(Compte("Courant", "EUR", Decimal("8472.30")))
p.ajouter(Compte("International", "GBP", Decimal("3120.75")))
p.ajouter(Compte("Voyage", "USD", Decimal("900")))

verifier("3 comptes", len(p.comptes), 3)
verifier("3 devises", p.devises, ["EUR", "GBP", "USD"])
verifier("plus vide", p.vide, False)

# Deux comptes de meme nom ET meme devise sont indistinguables a l'ecran.
leve("doublon nom + devise refuse",
     lambda: p.ajouter(Compte("Courant", "EUR")), "existe déjà")
# Meme nom mais devise differente : c'est legitime.
p.ajouter(Compte("Courant", "XOF", Decimal("1000000")))
verifier("meme nom, devise differente accepte", len(p.comptes), 4)

verifier("compte retrouve par identifiant",
         p.trouver(p.comptes[0].identifiant).nom, "Courant")
verifier("identifiant inconnu rend None", p.trouver("inexistant"), None)


# ---------------------------------------------------------------------------
print("\n3. Solde par devise — aucune conversion")
# ---------------------------------------------------------------------------

p2 = Portefeuille([
    Compte("A", "EUR", Decimal("1000")),
    Compte("B", "EUR", Decimal("500")),
    Compte("C", "USD", Decimal("300")),
])
# 1 000 + 500 = 1 500 EUR, sans toucher au compte en dollars.
verifier("somme des comptes EUR", p2.solde_devise("EUR").valeur, Decimal("1500"))
verifier("le compte USD reste a part", p2.solde_devise("USD").valeur, Decimal("300"))
verifier("devise sans compte = zero", p2.solde_devise("JPY").valeur, Decimal("0"))
verifier("... avec la bonne devise", p2.solde_devise("JPY").devise, "JPY")

groupes = p2.par_devise()
verifier("2 groupes de devises", sorted(groupes), ["EUR", "USD"])
verifier("2 comptes en EUR", len(groupes["EUR"]), 2)


# ---------------------------------------------------------------------------
print("\n4. Consolidation — le total vient avec ses taux")
# ---------------------------------------------------------------------------

taux = taux_de_test()
p3 = Portefeuille([
    Compte("Courant", "EUR", Decimal("1000")),
    Compte("Londres", "GBP", Decimal("1000")),
    Compte("New York", "USD", Decimal("1000")),
], devise_reference="EUR")

# 1 000 EUR + (1 000 GBP x 1,17 = 1 170) + (1 000 USD x 0,92 = 920) = 3 090 EUR
cons = p3.consolider(taux)
verifier("total consolide = 3 090", cons.total.arrondi, Decimal("3090.00"))
verifier("devise du total", cons.total.devise, "EUR")
verifier("3 comptes retenus", cons.comptes_retenus, 3)
verifier("multidevise detecte", cons.multidevise, True)

# La ventilation par devise doit rester visible : c'est ce qui permet a
# l'utilisateur de retrouver son solde natif compte par compte.
verifier("ventilation en 3 devises", sorted(cons.par_devise), ["EUR", "GBP", "USD"])
verifier("sous-total GBP natif", cons.par_devise["GBP"].valeur, Decimal("1000"))
verifier("le sous-total garde sa devise", cons.par_devise["GBP"].devise, "GBP")

# LE POINT CORRIGE : les taux employes sont rendus avec le total.
verifier("2 taux employes", len(cons.taux_employes), 2)
verifier("les taux sont identifiables",
         sorted(t.base for t in cons.taux_employes), ["GBP", "USD"])
verifier("la phrase montre les taux",
         "1.17" in cons.phrase_taux() and "0.92" in cons.phrase_taux(), True)
verifier("la phrase montre les sources", "BCE" in cons.phrase_taux(), True)

# Le taux GBP date du 15/07, le taux USD du 01/08 : le plus ancien est le GBP.
verifier("le taux le plus ancien est identifie",
         cons.taux_le_plus_ancien.base, "GBP")
verifier("anciennete au 31/08 = 47 jours",
         cons.anciennete_max(date(2026, 8, 31)), 47)


# ---------------------------------------------------------------------------
print("\n5. Consolidation monodevise")
# ---------------------------------------------------------------------------

p4 = Portefeuille([Compte("A", "EUR", Decimal("100")),
                   Compte("B", "EUR", Decimal("200"))], devise_reference="EUR")
cons4 = p4.consolider(taux)
verifier("total sans conversion", cons4.total.valeur, Decimal("300"))
verifier("aucun taux employe", len(cons4.taux_employes), 0)
verifier("pas multidevise", cons4.multidevise, False)
verifier("la phrase le dit clairement",
         "même devise" in cons4.phrase_taux(), True)


# ---------------------------------------------------------------------------
print("\n6. Taux manquant : refuser plutot qu'afficher un total faux")
# ---------------------------------------------------------------------------

p5 = Portefeuille([Compte("A", "EUR", Decimal("100")),
                   Compte("Tokyo", "JPY", Decimal("500000"))],
                  devise_reference="EUR")
leve("total impossible signale", lambda: p5.consolider(taux), "aucun taux connu")
verifier("peut_consolider dit non", p5.peut_consolider(taux), False)
verifier("peut_consolider dit oui quand c'est possible",
         p3.peut_consolider(taux), True)

# Le message doit nommer la devise fautive et proposer une issue.
try:
    p5.consolider(taux)
except ErreurCompte as err:
    verifier("le message nomme la devise manquante", "JPY" in str(err), True)
    verifier("le message propose une issue", "Renseignez" in str(err), True)


# ---------------------------------------------------------------------------
print("\n7. Comptes inactifs")
# ---------------------------------------------------------------------------

p6 = Portefeuille([
    Compte("Actif", "EUR", Decimal("1000")),
    Compte("Clos", "EUR", Decimal("500"), actif=False),
], devise_reference="EUR")
verifier("2 comptes enregistres", len(p6.comptes), 2)
verifier("1 seul actif", len(p6.actifs), 1)
# Un compte clos ne doit pas gonfler le total.
verifier("le compte clos est exclu du total",
         p6.consolider(taux).total.valeur, Decimal("1000"))
verifier("le compte clos est exclu du solde par devise",
         p6.solde_devise("EUR").valeur, Decimal("1000"))


# ---------------------------------------------------------------------------
print("\n8. Devise de reference")
# ---------------------------------------------------------------------------

# Le meme portefeuille consolide en USD : 3 090 EUR / 0,92 = 3 358,70 USD
cons_usd = p3.consolider(taux, vers="USD")
verifier("consolidation en USD", cons_usd.total.arrondi, Decimal("3358.70"))
verifier("devise du total suit", cons_usd.total.devise, "USD")

p3.definir_reference("GBP")
verifier("reference modifiee", p3.devise_reference, "GBP")
# 3 090 EUR / 1,17 = 2 641,03 GBP
verifier("consolidation suit la reference",
         p3.consolider(taux).total.arrondi, Decimal("2641.03"))
p3.definir_reference("EUR")


# ---------------------------------------------------------------------------
print("\n9. Franc CFA — le cas qui compte pour la cible")
# ---------------------------------------------------------------------------

p7 = Portefeuille([
    Compte("Compte France", "EUR", Decimal("2000")),
    Compte("Compte Dakar", "XOF", Decimal("5000000"), pays="Sénégal"),
], devise_reference="EUR")
# 5 000 000 FCFA x 0,001524 = 7 620 EUR ; + 2 000 = 9 620 EUR
cons7 = p7.consolider(taux)
verifier("total avec FCFA", cons7.total.arrondi, Decimal("9620.00"))
# Le FCFA n'a pas de decimale : le solde natif doit rester entier.
verifier("le FCFA s'affiche sans decimale",
         cons7.par_devise["XOF"].formater(), "5 000 000 FCFA")
verifier("la source BCEAO est citee", "BCEAO" in cons7.phrase_taux(), True)


# ---------------------------------------------------------------------------
print("\n10. Reprise de l'ancien reglage")
# ---------------------------------------------------------------------------

ancien = portefeuille_depuis_solde_unique(2500.0, "EUR")
verifier("un compte cree", len(ancien.comptes), 1)
verifier("solde repris", ancien.comptes[0].solde, Decimal("2500"))
verifier("devise reprise", ancien.comptes[0].devise, "EUR")
verifier("reference alignee", ancien.devise_reference, "EUR")
verifier("nom par defaut", ancien.comptes[0].nom, "Compte principal")


# ---------------------------------------------------------------------------
print("\n11. Sauvegarde et relecture")
# ---------------------------------------------------------------------------

donnees = p3.vers_liste()
verifier("3 comptes serialises", len(donnees), 3)
verifier("le solde est du texte", isinstance(donnees[0]["solde"], str), True)

relu = Portefeuille.depuis_liste(donnees, "EUR")
verifier("3 comptes relus", len(relu.comptes), 3)
verifier("solde intact apres relecture",
         relu.comptes[0].solde, p3.comptes[0].solde)
verifier("devise intacte", relu.comptes[1].devise, p3.comptes[1].devise)
verifier("identifiant conserve",
         relu.comptes[0].identifiant, p3.comptes[0].identifiant)
# Le total doit etre identique au centime apres un aller-retour.
verifier("total identique apres relecture",
         relu.consolider(taux).total.arrondi, p3.consolider(taux).total.arrondi)

verifier("liste vide relue sans erreur", len(Portefeuille.depuis_liste([]).comptes), 0)
verifier("None relu sans erreur", len(Portefeuille.depuis_liste(None).comptes), 0)


# ---------------------------------------------------------------------------
print("\n12. Retrait")
# ---------------------------------------------------------------------------

p8 = Portefeuille([Compte("A", "EUR", Decimal("100")),
                   Compte("B", "USD", Decimal("200"))])
identifiant = p8.comptes[0].identifiant
verifier("retrait reussi", p8.retirer(identifiant), True)
verifier("il reste 1 compte", len(p8.comptes), 1)
verifier("retrait d'un inconnu rend faux", p8.retirer("inexistant"), False)


# ---------------------------------------------------------------------------
print("\n" + "=" * 62)
if ko:
    print(f"{ok} verifications reussies, {len(ko)} ECHECS :")
    for n in ko:
        print(f"   - {n}")
    raise SystemExit(1)
print(f"{ok} verifications reussies, aucun echec.")
