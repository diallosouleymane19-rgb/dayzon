"""
Verification du module d'abonnement.
Aucun appel reseau : on teste les regles, pas Stripe.

Lancer :  py test_abonnement.py
"""

from datetime import date, timedelta

from abonnement import (OFFRES, OFFRES_VENDUES, Abonnement, ConfigStripe,
                        ErreurPaiement, Periode, Plan, charger_configuration,
                        ouvrir_paiement)

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


# ---------------------------------------------------------------------------
print("\n1. La grille tarifaire")
# ---------------------------------------------------------------------------

part = OFFRES[Plan.PARTICULIER]
ent = OFFRES[Plan.ENTREPRISE]

verifier("Particulier 7 $/mois", part.prix_mensuel, 700)
verifier("Particulier 59 $/an", part.prix_annuel, 5900)
verifier("Entreprise 29 $/mois", ent.prix_mensuel, 2900)
verifier("Entreprise 249 $/an", ent.prix_annuel, 24900)

# 12 x 7 = 84 $. 59 $ represente une remise de (84-59)/84 = 29,76 % -> 30 %.
verifier("remise annuelle Particulier = 30 %", part.economie_annuelle, 30)
# 12 x 29 = 348 $. (348-249)/348 = 28,4 % -> 28 %.
verifier("remise annuelle Entreprise = 28 %", ent.economie_annuelle, 28)

verifier("affichage mensuel", part.prix_affiche(Periode.MENSUELLE), "7 $ par mois")
verifier("affichage annuel", part.prix_affiche(Periode.ANNUELLE), "59 $ par an")
verifier("Découverte affiché gratuit",
         OFFRES[Plan.DECOUVERTE].prix_affiche(), "Gratuit")
verifier("3 offres proposées à la vente", len(OFFRES_VENDUES), 3)

# On reste sous les concurrents : PocketSmith 9,99 $ · Cash Flow Frog 33 $.
verifier("Particulier sous PocketSmith", part.prix_mensuel < 999, True)
verifier("Entreprise sous Cash Flow Frog", ent.prix_mensuel < 3300, True)


# ---------------------------------------------------------------------------
print("\n2. Ce que chaque plan débloque")
# ---------------------------------------------------------------------------

decouverte = Abonnement(plan=Plan.DECOUVERTE)
verifier("Découverte : pas de scénarios", decouverte.autorise("scenarios"), False)
verifier("Découverte : pas d'exports", decouverte.autorise("exports"), False)
verifier("Découverte : pas d'entreprise", decouverte.autorise("entreprise"), False)
verifier("Découverte : 90 jours", decouverte.limite_jours(), 90)
verifier("Découverte : 1 fichier", decouverte.limite_fichiers(), 1)

demain = date.today() + timedelta(days=30)
p = Abonnement(plan=Plan.PARTICULIER, fin=demain)
verifier("Particulier : scénarios", p.autorise("scenarios"), True)
verifier("Particulier : exports", p.autorise("exports"), True)
verifier("Particulier : pas d'entreprise", p.autorise("entreprise"), False)
verifier("Particulier : 365 jours", p.limite_jours(), 365)

e = Abonnement(plan=Plan.ENTREPRISE, fin=demain)
verifier("Entreprise : entreprise", e.autorise("entreprise"), True)
verifier("Entreprise : 730 jours", e.limite_jours(), 730)

libre = Abonnement(plan=Plan.LIBRE)
verifier("Libre : tout ouvert",
         all(libre.autorise(f) for f in ("scenarios", "exports", "entreprise")), True)

# Une fonction inconnue ne doit jamais etre bloquee par erreur.
verifier("fonction inconnue autorisée", decouverte.autorise("truc_inexistant"), True)


# ---------------------------------------------------------------------------
print("\n3. Validité dans le temps")
# ---------------------------------------------------------------------------

hier = date.today() - timedelta(days=1)
expire = Abonnement(plan=Plan.ENTREPRISE, fin=hier)
verifier("abonnement expiré : inactif", expire.actif(), False)
verifier("expiré : retour en Découverte", expire.plan_effectif(), Plan.DECOUVERTE)
verifier("expiré : plus de scénarios", expire.autorise("scenarios"), False)
verifier("expiré : horizon ramené à 90 j", expire.limite_jours(), 90)

# Regle : un abonnement resilie reste utilisable jusqu'au terme paye.
resilie = Abonnement(plan=Plan.ENTREPRISE, fin=demain, annule=True)
verifier("résilié mais non échu : actif", resilie.actif(), True)
verifier("résilié : droits conservés", resilie.autorise("entreprise"), True)
verifier("jours restants = 30", resilie.jours_restants(), 30)
verifier("le message dit la résiliation", "résilié" in resilie.etat(), True)
verifier("le message donne la date restante", "30 jours" in resilie.etat(), True)

sans_fin = Abonnement(plan=Plan.PARTICULIER, fin=None)
verifier("payant sans date de fin : inactif", sans_fin.actif(), False)

verifier("Découverte toujours actif", decouverte.actif(), True)
verifier("Libre toujours actif", libre.actif(), True)

# Jugement a une date donnee, pas a la date du jour.
ref = date(2026, 6, 15)
a = Abonnement(plan=Plan.PARTICULIER, fin=date(2026, 6, 30))
verifier("actif au 15/06", a.actif(ref), True)
verifier("inactif au 15/07", a.actif(date(2026, 7, 15)), False)
verifier("le dernier jour compte", a.actif(date(2026, 6, 30)), True)


# ---------------------------------------------------------------------------
print("\n4. Configuration")
# ---------------------------------------------------------------------------

vide = ConfigStripe()
verifier("configuration vide : non configurée", vide.configure, False)

c = charger_configuration({
    "cle_secrete": "sk_test_abc",
    "prix_particulier_mensuel": "price_pm",
    "prix_particulier_annuel": "price_pa",
    "prix_entreprise_mensuel": "price_em",
    "prix_entreprise_annuel": "price_ea",
    "url_retour": "https://dayzon.app",
})
verifier("configuration lue", c.configure, True)
verifier("4 tarifs enregistrés", len(c.prix), 4)
verifier("tarif Particulier mensuel",
         c.identifiant_prix(Plan.PARTICULIER, Periode.MENSUELLE), "price_pm")
verifier("tarif Entreprise annuel",
         c.identifiant_prix(Plan.ENTREPRISE, Periode.ANNUELLE), "price_ea")
verifier("url de retour", c.url_retour, "https://dayzon.app")

# Une configuration partielle ne doit pas faire croire que tout est pret.
partielle = charger_configuration({"cle_secrete": "sk_test_abc"})
verifier("clé sans tarif : non configurée", partielle.configure, False)
sans_cle = charger_configuration({"prix_particulier_mensuel": "price_pm"})
verifier("tarif sans clé : non configurée", sans_cle.configure, False)

# Aucune exception si les secrets sont absents.
try:
    charger_configuration({})
    verifier("configuration absente : pas d'erreur", True, True)
except Exception as err:
    verifier("configuration absente : pas d'erreur", f"exception {err}", True)


# ---------------------------------------------------------------------------
print("\n5. Paiement — refus propres")
# ---------------------------------------------------------------------------

try:
    ouvrir_paiement(Plan.PARTICULIER, Periode.MENSUELLE, ConfigStripe())
    verifier("sans configuration : erreur levée", False, True)
except ErreurPaiement as err:
    verifier("sans configuration : erreur levée", True, True)
    verifier("message compréhensible", "pas encore configuré" in str(err), True)

incomplete = ConfigStripe(cle_secrete="sk_test_abc",
                          prix={(Plan.PARTICULIER, Periode.MENSUELLE): "price_pm"})
try:
    ouvrir_paiement(Plan.ENTREPRISE, Periode.ANNUELLE, incomplete)
    verifier("tarif manquant : erreur levée", False, True)
except ErreurPaiement as err:
    verifier("tarif manquant : erreur levée", True, True)
    verifier("l'erreur nomme le plan", "Entreprise" in str(err), True)


# ---------------------------------------------------------------------------
print("\n6. Messages affichés")
# ---------------------------------------------------------------------------

verifier("Libre : message d'accès complet",
         "Accès complet" in libre.etat(), True)
verifier("Découverte : message de limite",
         "90 jours" in decouverte.etat(), True)
verifier("expiré : message de fin",
         "pris fin" in expire.etat(), True)
actif = Abonnement(plan=Plan.PARTICULIER, fin=demain)
verifier("actif : message de renouvellement",
         "renouvelé" in actif.etat(), True)

for offre in OFFRES_VENDUES:
    verifier(f"« {offre.nom} » a des arguments de vente",
             len(offre.arguments) >= 3, True)
    verifier(f"« {offre.nom} » a un résumé", bool(offre.resume), True)


# ---------------------------------------------------------------------------
print("\n" + "=" * 62)
if ko:
    print(f"{ok} verifications reussies, {len(ko)} ECHECS :")
    for n in ko:
        print(f"   - {n}")
    raise SystemExit(1)
print(f"{ok} verifications reussies, aucun echec.")
