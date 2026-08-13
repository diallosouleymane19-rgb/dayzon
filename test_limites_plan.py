"""
VERIFICATION DES LIMITES DE FORMULE — en execution reelle
PrevuFlow — SMD Global Consulting LLC

Le module `abonnement` sait depuis longtemps repondre a « cette personne
a-t-elle le droit ? ». Pendant des semaines, aucun ecran ne lui posait la
question : payer 7 $ donnait exactement ce que donnait la formule gratuite.

Ce test lance l'application avec chaque formule et verifie ce que l'ecran
laisse faire. Il ne teste pas les regles — `test_abonnement.py` s'en charge
sans reseau ni interface — mais leur application.

Lancer :  py test_limites_plan.py
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from decimal import Decimal

os.environ["PREVUFLOW_HEBERGE"] = "1"

from streamlit.testing.v1 import AppTest                        # noqa: E402

from abonnement import (Abonnement, ConfigStripe, Periode,      # noqa: E402
                        Plan, essai)
from comptes import Compte, Portefeuille                        # noqa: E402
from import_intelligent import Mouvement                        # noqa: E402
from moteur_tresorerie import Recurrence                        # noqa: E402

echecs = 0


def verifier(titre: str, condition: bool) -> None:
    global echecs
    if condition:
        print(f"  ok    {titre}")
    else:
        print(f"  ECHEC {titre}")
        echecs += 1


# Une configuration Stripe factice : sans elle, l'application se croit en
# mode libre et n'applique aucune limite. Aucun appel reseau n'est fait,
# l'abonnement etant place directement dans la session.
CONFIG = ConfigStripe(
    cle_secrete="sk_test_faux",
    prix={(p, pe): f"price_{p.value}_{pe.value}"
          for p in (Plan.PARTICULIER, Plan.ENTREPRISE)
          for pe in (Periode.MENSUELLE, Periode.ANNUELLE)},
    url_retour="https://prevuflow.streamlit.app")

DEMAIN = date.today() + timedelta(days=30)


def lancer(abonnement: Abonnement, profil: str = "Particulier",
           avec_releve: bool = True) -> AppTest:
    at = AppTest.from_file("app_tresorerie.py", default_timeout=180)
    for cle, valeur in (("langue", "fr"), ("config_stripe", CONFIG),
                        ("abonnement", abonnement), ("page", ""),
                        ("profil", profil)):
        at.session_state[cle] = valeur

    portefeuille = Portefeuille(devise_reference="EUR")
    portefeuille.ajouter(Compte("Compte courant", "EUR", Decimal("2500")))
    at.session_state["portefeuille"] = portefeuille

    jour = date.today()
    at.session_state["operations"] = [
        {"libelle": "Salaire", "montant": 2800, "date": jour, "devise": "EUR",
         "recurrence": Recurrence.MENSUELLE, "certaine": True},
        {"libelle": "Loyer", "montant": -950, "date": jour + timedelta(days=3),
         "devise": "EUR", "recurrence": Recurrence.MENSUELLE, "certaine": True},
    ]
    if avec_releve:
        # Sans releve importe, l'onglet Rapports n'existe pas : le mur des
        # exports ne serait jamais rendu, et le test passerait a cote.
        at.session_state["mouvements"] = [
            Mouvement(jour - timedelta(days=n * 7), "Courses",
                      Decimal("-62.40")) for n in range(6)
        ] + [Mouvement(jour - timedelta(days=30), "Salaire", Decimal("2800"))]
    at.run()
    return at


def rendu(at: AppTest) -> str:
    return " ".join(str(m.value) for m in at.markdown)


def crans_horizon(at: AppTest) -> list:
    for widget in at.select_slider:
        options = list(getattr(widget, "options", []))
        if options and "jours" in str(options[0]):
            return options
    return []


print("1. L'horizon du calendrier suit la formule")

for nom, abonnement, attendu in (
        ("Decouverte", Abonnement(plan=Plan.DECOUVERTE), 3),
        ("Particulier", Abonnement(plan=Plan.PARTICULIER, fin=DEMAIN), 5),
        ("Essai", essai(date.today()), 6)):
    at = lancer(abonnement)
    verifier(f"{nom} : l'application demarre", not at.exception)
    if at.exception:
        print(f"          {at.exception[0].message[:160]}")
        continue
    crans = crans_horizon(at)
    verifier(f"{nom} : {len(crans)} crans d'horizon ({crans})",
             len(crans) == attendu)

# Le plafond doit etre une borne, pas une suggestion : en Decouverte, aucun
# cran au-dela de 90 jours ne doit exister — pas meme grise.
at = lancer(Abonnement(plan=Plan.DECOUVERTE))
verifier("Decouverte : aucun cran au-dela de 90 jours",
         not any(x in str(crans_horizon(at)) for x in ("180", "365", "730")))


print("\n2. Les fonctions payantes sont fermees, et le disent")

at = lancer(Abonnement(plan=Plan.DECOUVERTE))
texte = rendu(at)
verifier("Decouverte : les scenarios et les exports sont fermes",
         texte.count("formule payante") == 2)
verifier("Decouverte : le mur nomme la formule qui debloque",
         "Particulier" in texte)
verifier("Decouverte : un bouton mene aux formules",
         any("formules" in b.label for b in at.button))

at = lancer(Abonnement(plan=Plan.PARTICULIER, fin=DEMAIN))
verifier("Particulier : plus aucun mur",
         "formule payante" not in rendu(at))
verifier("Particulier : les trois exports sont proposes",
         len(at.download_button) >= 3)

at = lancer(essai(date.today()))
verifier("Essai : plus aucun mur", "formule payante" not in rendu(at))


print("\n3. Le profil Entreprise est reserve")

at = lancer(Abonnement(plan=Plan.DECOUVERTE), profil="Entreprise")
verifier("Decouverte : le profil Entreprise est ferme",
         "formule payante" in rendu(at))
verifier("Decouverte : le mur nomme la formule Entreprise",
         "Entreprise" in rendu(at))

at = lancer(Abonnement(plan=Plan.PARTICULIER, fin=DEMAIN), profil="Entreprise")
verifier("Particulier : le profil Entreprise reste ferme",
         "formule payante" in rendu(at))

at = lancer(Abonnement(plan=Plan.ENTREPRISE, fin=DEMAIN), profil="Entreprise")
verifier("Entreprise : le profil s'ouvre",
         "formule payante" not in rendu(at))

at = lancer(essai(date.today()), profil="Entreprise")
verifier("Essai : le profil Entreprise s'ouvre aussi",
         "formule payante" not in rendu(at))


print("\n4. Un essai echu ne donne plus rien de plus que le gratuit")

# C'est tout l'objet de la periode d'essai : ce qui s'ouvre doit se refermer.
echu = essai(date.today() - timedelta(days=30))
at = lancer(echu)
verifier("essai echu : les fonctions payantes sont refermees",
         "formule payante" in rendu(at))
verifier("essai echu : l'horizon retombe a 90 jours",
         len(crans_horizon(at)) == 3)


print("\n4 bis. Le decompte des fichiers survit au rechargement")

# Le compteur vivait dans la session : recharger la page le remettait a
# zero, et la limite d'un fichier de la formule Decouverte se contournait
# sans meme le vouloir.
import commun                                                   # noqa: E402
import compte                                                   # noqa: E402
import streamlit as _st                                         # noqa: E402

_vrai_connecte = compte.connecte
_vrai_lire = compte.imports_du_mois
_vrai_ecrire = compte.enregistrer_import
_en_base = {"nombre": 0}

try:
    # Personne connectee : le compteur reste dans la session.
    compte.connecte = lambda: False
    for cle in ("imports_du_mois", "fichiers_importes"):
        _st.session_state.pop(cle, None)
    verifier("sans compte : le decompte part de zero",
             commun.fichiers_importes() == 0)
    commun.compter_import()
    verifier("sans compte : le decompte monte a 1",
             commun.fichiers_importes() == 1)

    # Avec un compte : la base fait foi, et la session ne fait que
    # transporter la valeur lue.
    compte.connecte = lambda: True
    compte.imports_du_mois = lambda: _en_base["nombre"]

    def _incrementer():
        _en_base["nombre"] += 1
        return _en_base["nombre"]

    compte.enregistrer_import = _incrementer

    for cle in ("imports_du_mois", "fichiers_importes"):
        _st.session_state.pop(cle, None)
    verifier("avec compte : le decompte vient de la base",
             commun.fichiers_importes() == 0)
    commun.compter_import()
    verifier("avec compte : l'import est inscrit en base",
             _en_base["nombre"] == 1)

    # Le rechargement : la session est videe, la base ne l'est pas.
    for cle in ("imports_du_mois", "fichiers_importes"):
        _st.session_state.pop(cle, None)
    verifier("apres rechargement : le decompte tient",
             commun.fichiers_importes() == 1)

    # Une base injoignable ne doit pas fermer l'import.
    compte.imports_du_mois = lambda: 0
    _st.session_state.pop("imports_du_mois", None)
    verifier("base illisible : l'import reste possible",
             commun.fichiers_importes() == 0)
finally:
    compte.connecte = _vrai_connecte
    compte.imports_du_mois = _vrai_lire
    compte.enregistrer_import = _vrai_ecrire
    for cle in ("imports_du_mois", "fichiers_importes"):
        _st.session_state.pop(cle, None)


print("\n5. Sans paiement configure, rien n'est bride")

# Une installation locale, une demonstration commerciale : tant qu'aucune
# cle Stripe n'est posee, l'application doit rester entierement ouverte.
at = AppTest.from_file("app_tresorerie.py", default_timeout=180)
at.session_state["langue"] = "fr"
at.session_state["config_stripe"] = ConfigStripe()
portefeuille = Portefeuille(devise_reference="EUR")
portefeuille.ajouter(Compte("Compte courant", "EUR", Decimal("2500")))
at.session_state["portefeuille"] = portefeuille
at.session_state["operations"] = [
    {"libelle": "Salaire", "montant": 2800, "date": date.today(),
     "devise": "EUR", "recurrence": Recurrence.MENSUELLE, "certaine": True}]
at.run()
verifier("sans configuration : aucun mur", "formule payante" not in rendu(at))
verifier("sans configuration : horizon complet",
         len(crans_horizon(at)) == 6)


print("\n" + "=" * 62)
print("Toutes les verifications sont passees."
      if not echecs else f"{echecs} echec(s).")
sys.exit(1 if echecs else 0)
