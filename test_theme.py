"""
Verification de l'apparence.

Un theme ne se teste pas au pixel : ce qui se verifie, c'est qu'il est
applique, qu'il ne casse pas l'ecran, et qu'il respecte les deux regles
qu'on s'est donnees — aucun texte sous 11 pixels, aucune donnee saisie
inseree telle quelle dans du HTML.

Lancer :  py test_theme.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

os.environ["DAYZON_HEBERGE"] = "1"

echecs = 0


def verifier(titre: str, condition: bool) -> None:
    global echecs
    if condition:
        print(f"  ok    {titre}")
    else:
        print(f"  ECHEC {titre}")
        echecs += 1


print("1. Le theme est un module a part")

import theme                                                    # noqa: E402

src = Path("theme.py").read_text(encoding="utf-8")
verifier("aucune logique metier dans le theme",
         "moteur_tresorerie" not in src and "import argent" not in src)
verifier("le theme expose appliquer()", callable(theme.appliquer))

# Les couleurs ne doivent vivre qu'ici.
for fichier in sorted(Path(".").glob("vue_*.py")) + [Path("app_tresorerie.py")]:
    contenu = fichier.read_text(encoding="utf-8")
    codes = set(re.findall(r'"#[0-9a-fA-F]{6}"', contenu))
    verifier(f"{fichier.name} : {len(codes)} couleur(s) en dur", len(codes) <= 4)


print("\n2. Aucun texte sous 11 pixels")

# Le prototype descendait a 7px. Illisible sur un telephone tenu a bout
# de bras, et sous le seuil recommande pour l'accessibilite.
trop_petit = sorted({int(t) for t in re.findall(r"font-size:\s*(\d+)px", src)
                     if int(t) < 11})
verifier(f"tailles utilisees toutes >= 11px (trouve : {trop_petit})",
         not trop_petit)

for fichier in sorted(Path(".").glob("vue_*.py")) + [Path("app_tresorerie.py")]:
    contenu = fichier.read_text(encoding="utf-8")
    petits = sorted({int(t) for t in re.findall(r"font-size:\s*(\d+)px", contenu)
                     if int(t) < 11})
    verifier(f"{fichier.name} : aucune taille sous 11px {petits or ''}",
             not petits)


print("\n3. Les donnees saisies sont echappees")

# Un nom de compte vient de l'utilisateur. Sans echappement, il finirait
# tel quel dans la page.
verifier("le theme echappe ce qu'il insere", "_html.escape" in src)
verifier("hero echappe", theme._e("<b>x</b>") == "&lt;b&gt;x&lt;/b&gt;")
verifier("les guillemets aussi", "&quot;" in theme._e('a"b'))


print("\n4. L'application se rend avec le theme")

from datetime import date, timedelta                            # noqa: E402
from decimal import Decimal                                     # noqa: E402

from streamlit.testing.v1 import AppTest                        # noqa: E402

from comptes import Compte, Portefeuille                        # noqa: E402
from moteur_tresorerie import Recurrence                        # noqa: E402

at = AppTest.from_file("app_tresorerie.py", default_timeout=120)
p = Portefeuille(devise_reference="EUR")
p.ajouter(Compte("Compte courant", "EUR", Decimal("2500")))
at.session_state["portefeuille"] = p
jour = date.today()
at.session_state["operations"] = [
    {"libelle": "Salaire", "montant": 2800, "date": jour, "devise": "EUR",
     "recurrence": Recurrence.MENSUELLE, "certaine": True},
    {"libelle": "Loyer", "montant": -950, "date": jour + timedelta(days=3),
     "devise": "EUR", "recurrence": Recurrence.MENSUELLE, "certaine": True},
]
at.run()

verifier("l'application demarre sans erreur", not at.exception)
if at.exception:
    print(f"          {at.exception[0].message}")
else:
    rendu = " ".join(str(m.value) for m in at.markdown)
    verifier("le chiffre de tete est rendu", "dz-hero" in rendu)
    verifier("les indicateurs sont rendus", rendu.count("dz-kpi") >= 4)
    verifier("un encart d'analyse est rendu", "dz-msg" in rendu)
    verifier("la grille du calendrier est rendue",
             rendu.count("dz-jour") > 20)


print("\n5. Un encart ne se lit pas deux fois")

# Defaut vu en ligne : « Vous passez sous zero... » apparaissait en titre
# ET en corps. Une phrase unique doit rester unique.
_rendus: list[str] = []


class _Faux:
    def markdown(self, contenu, **_):
        _rendus.append(contenu)


_vrai_st = theme.st
theme.st = _Faux()
theme.message_phrase("attention", "Une seule phrase sans suite.")
theme.message_phrase("bon", "Un constat. Puis son explication.")
theme.st = _vrai_st

verifier("phrase unique : ecrite une fois",
         _rendus[0].count("Une seule phrase sans suite.") == 1)
verifier("phrase double : titre et corps distincts",
         "Un constat." in _rendus[1] and "Puis son explication." in _rendus[1])
verifier("phrase double : le titre n'est pas repete",
         _rendus[1].count("Un constat.") == 1)


print("\n6. Les centimes suivent la devise")

# Demande explicite : deux decimales en euro et en dollar. Le nombre reste
# celui de la devise — le yen et le franc CFA n'ont pas de centimes.
import langues as _lg                                           # noqa: E402
import argent as _argent                                        # noqa: E402

for devise, attendu in (("EUR", 2), ("USD", 2), ("GBP", 2),
                        ("JPY", 0), ("XOF", 0), ("KWD", 3)):
    verifier(f"{devise} : {attendu} decimale(s)",
             _argent.decimales(devise) == attendu)

for code, devise, attendu in (("fr", "EUR", "7\u202f650,00\u00a0\u20ac"),
                              ("en", "USD", "$7,650.00"),
                              ("fr", "XOF", "7\u202f650\u00a0FCFA")):
    obtenu = _lg.formater_montant(7650, devise, code)
    verifier(f"{code}/{devise} : {obtenu}", obtenu == attendu)

# La fonction dite « courte » ne doit plus supprimer les centimes.
_src_commun = Path("commun.py").read_text(encoding="utf-8")
_bloc = _src_commun[_src_commun.index("def formater_court"):
                    _src_commun.index("def formater_date")]
verifier("formater_court n'ecrase plus les decimales",
         "avec_decimales=False" not in _bloc)


print("\n7. Ce que Streamlit ne permet pas n'est pas simule")

# Une barre de navigation basse en CSS ne reagirait pas au clic : mieux
# vaut ne pas la dessiner du tout qu'offrir des boutons morts.
for interdit in ("bottom-nav", "position:fixed;bottom", "class=\"fab\""):
    verifier(f"absent du theme : {interdit}", interdit not in src)


print("\n" + "=" * 62)
print("Toutes les verifications sont passees."
      if not echecs else f"{echecs} echec(s).")
sys.exit(1 if echecs else 0)
