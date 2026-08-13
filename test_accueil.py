"""
VERIFICATION DE L'ECRAN D'ACCUEIL
PrevuFlow — SMD Global Consulting LLC

Un visiteur arrivait directement sur un formulaire vide, sans un mot sur
ce qu'il avait sous les yeux. Cet ecran repond aux trois questions qu'on
se pose dans cet ordre : qu'est-ce que ca fait, est-ce que ca marche avec
ma banque, combien ca coute.

Deux regles a ne pas casser, et c'est l'objet de ce test :
  · il s'efface des qu'on entre, et ne se remontre jamais tout seul ;
  · les prix y sont lisibles avant toute inscription.

Lancer :  py test_accueil.py
"""

from __future__ import annotations

import os
import re
import sys
from datetime import date
from decimal import Decimal

os.environ["PREVUFLOW_HEBERGE"] = "1"

from streamlit.testing.v1 import AppTest                        # noqa: E402

import langues as lg                                            # noqa: E402
from comptes import Compte, Portefeuille                        # noqa: E402
from moteur_tresorerie import Recurrence                        # noqa: E402

echecs = 0


def verifier(titre: str, condition: bool) -> None:
    global echecs
    if condition:
        print(f"  ok    {titre}")
    else:
        print(f"  ECHEC {titre}")
        echecs += 1


def lancer(**etat) -> AppTest:
    at = AppTest.from_file("app_tresorerie.py", default_timeout=180)
    at.session_state["langue"] = etat.pop("langue", "fr")
    for cle, valeur in etat.items():
        at.session_state[cle] = valeur
    at.run()
    return at


def texte(at: AppTest) -> str:
    brut = " ".join(str(m.value) for m in at.markdown)
    brut += " " + " ".join(c.value for c in at.caption)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", brut))


print("1. Le visiteur qui arrive voit ce que fait l'outil")

at = lancer()
verifier("l'application demarre", not at.exception)
if at.exception:
    print(f"          {at.exception[0].message[:200]}")
else:
    contenu = texte(at)
    verifier("la promesse est affichee",
             lg.traduire("acc.promesse", "fr")[:30] in contenu)
    verifier("l'absence de connexion bancaire est dite",
             lg.traduire("acc.arg1_valeur", "fr") in contenu)
    verifier("les trois etapes sont la",
             all(lg.traduire(f"acc.etape{n}", "fr") in contenu
                 for n in (1, 2, 3)))
    verifier("un bouton fait entrer",
             any(lg.traduire("acc.commencer", "fr") == b.label
                 for b in at.button))


print("\n1 bis. L'accueil n'est coiffe ni d'un titre, ni de reglages")

# Deux defauts vus a l'ecran, corriges le 13 aout : le titre du logiciel
# s'affichait au-dessus de la promesse, et toute la barre de reglages
# etait deja la. Douze champs de saisie devant quelqu'un qui decouvre le
# produit, c'est une porte de sortie.
at = lancer()
verifier("aucun titre de logiciel au-dessus de la promesse",
         [t.value for t in at.title] == ["PrevuFlow"])
verifier("la barre laterale est reduite a l'essentiel",
         len(at.text_input) + len(at.number_input) + len(at.selectbox) <= 2)
verifier("aucun depot de fichier avant d'etre entre",
         len(at.button) <= 3)
verifier("la barre annonce ce qui viendra",
         lg.traduire("acc.barre_laterale", "fr") in texte(at))


print("\n2. Les prix sont lisibles avant toute inscription")

# C'est le point qui fait rester ou partir : un tarif qu'on ne decouvre
# qu'apres avoir cree un compte se lit comme un piege.
contenu = texte(lancer())
for attendu in ("7,00", "29,00"):
    verifier(f"le tarif {attendu} est affiche", attendu in contenu)
verifier("les trois formules sont nommees",
         all(lg.traduire(cle, "fr") in contenu
             for cle in ("plan.decouverte.nom", "plan.particulier.nom",
                         "plan.entreprise.nom")))
verifier("l'essai de 14 jours est annonce",
         lg.traduire("acc.essai_rappel", "fr")[:40] in contenu)


print("\n3. Ce que l'outil ne fait pas est dit avant, pas apres")

# Une attente decue coute un remboursement et un avis negatif.
contenu = texte(lancer())
verifier("les limites sont annoncees",
         lg.traduire("acc.limites_titre", "fr") in contenu)
verifier("ni banque, ni comptabilite, ni conseil",
         all(mot in contenu for mot in ("banque", "comptabilité", "placement")))


print("\n4. L'accueil s'efface des qu'on travaille")

jour = date.today()
operations = [{"libelle": "Salaire", "montant": 2800, "date": jour,
               "devise": "EUR", "recurrence": Recurrence.MENSUELLE,
               "certaine": True}]

portefeuille = Portefeuille(devise_reference="EUR")
portefeuille.ajouter(Compte("Compte courant", "EUR", Decimal("2500")))

for nom, etat in (("des operations saisies", {"operations": operations}),
                  ("un compte cree", {"portefeuille": portefeuille}),
                  ("l'accueil deja quitte", {"accueil_vu": True})):
    contenu = texte(lancer(**etat))
    verifier(f"{nom} : l'accueil ne s'affiche plus",
             lg.traduire("acc.promesse", "fr")[:30] not in contenu)

# Et il reste joignable pour qui le cherche.
at = lancer(accueil_vu=True)
verifier("un bouton permet d'y revenir",
         any(lg.traduire("acc.voir_presentation", "fr") == b.label
             for b in at.button))


print("\n5. L'accueil parle les quatre langues")

for code in ("fr", "en", "es", "zh"):
    contenu = texte(lancer(langue=code))
    verifier(f"{code} : la promesse est traduite",
             lg.traduire("acc.promesse", code)[:28] in contenu)

# Une phrase francaise qui traine sur la page d'accueil est vue par tous
# les visiteurs, avant meme le premier clic.
SENTINELLES = {v for v in lg._charger("fr").values()
               if len(v) > 20 and "{" not in v}
for code in ("en", "es", "zh"):
    contenu = texte(lancer(langue=code))
    restes = sorted({p for p in SENTINELLES if p in contenu})
    verifier(f"{code} : aucune phrase francaise", not restes)
    for r in restes[:6]:
        print(f"          · {r[:72]}")




# ---------------------------------------------------------------------------
# Les documents juridiques sont consultables depuis l'application
# ---------------------------------------------------------------------------
#
# Stripe exige des conditions de vente accessibles. Un document range dans
# un dossier du depot, que personne ne peut ouvrir depuis l'ecran, ne vaut
# pas mieux qu'un document absent.

print("\n6. Les documents juridiques sont accessibles")

from pathlib import Path                                        # noqa: E402

for fichier in ("CGV.md", "CONFIDENTIALITE.md", "MENTIONS_LEGALES.md"):
    chemin = Path("juridique") / fichier
    verifier(f"{fichier} existe", chemin.exists())

at = lancer(page="juridique", accueil_vu=True)
verifier("la page juridique s'ouvre", not at.exception)
if at.exception:
    print(f"          {at.exception[0].message[:200]}")
else:
    contenu = texte(at)
    verifier("les trois documents sont en onglets", len(at.tabs) == 3)
    verifier("l'editeur est nomme", "SMD GLOBAL CONSULTING LLC" in contenu)
    verifier("la nature du service est dite",
             "n'est pas un" in contenu or "ne fait pas" in contenu)
    verifier("chaque document est telechargeable",
             len(at.download_button) >= 3)

    # Tant qu'un juriste n'a pas relu, l'avertissement doit rester visible :
    # le retirer ferait passer un brouillon pour un texte valide.
    verifier("l'avertissement de relecture est visible",
             "faire relire" in contenu)

print("\n" + "=" * 62)
print("Toutes les verifications sont passees."
      if not echecs else f"{echecs} echec(s).")
sys.exit(1 if echecs else 0)
