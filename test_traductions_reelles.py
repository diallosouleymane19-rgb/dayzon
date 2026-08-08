"""
VERIFICATION EN EXECUTION REELLE — les quatre langues
Dayzon — SMD Global Consulting LLC

Un fichier de traduction complet ne prouve rien : une cle peut exister sans
etre branchee, et l'ecran reste alors en francais. Ce test lance vraiment
l'application dans chaque langue et cherche, parmi tout ce qui s'affiche,
les phrases francaises du fichier de reference.

Il ne teste pas la qualite de la traduction — cela releve d'une relecture
humaine — mais il rend impossible d'oublier de brancher un ecran.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

echecs = 0


def verifier(titre: str, condition: bool) -> None:
    global echecs
    if condition:
        print(f"  ok    {titre}")
    else:
        print(f"  ECHEC {titre}")
        echecs += 1


FR = json.loads(Path("traductions/fr.json").read_text(encoding="utf-8"))

# Phrases assez longues pour ne pas se confondre avec un nom propre ou un
# mot identique d'une langue a l'autre (« Date », « Type », « Total »).
SENTINELLES = {v for v in FR.values() if len(v) > 14 and "{" not in v}


def textes_affiches(at: AppTest) -> list[str]:
    valeurs: list[str] = []
    for bloc in (at.markdown, at.caption, at.subheader, at.header, at.title,
                 at.info, at.warning, at.success, at.error):
        valeurs += [e.value for e in bloc]
    valeurs += [b.label for b in at.button]
    valeurs += [s.label for s in at.selectbox]
    valeurs += [c.label for c in at.checkbox]
    valeurs += [r.label for r in at.radio]
    return [v for v in valeurs if isinstance(v, str)]


print("1. Les fichiers de traduction sont complets")

import langues as lg                                          # noqa: E402

for code in ("en", "es", "zh"):
    lg.vider_cache()
    verifier(f"{code} : aucune cle manquante ({lg.couverture(code)} %)",
             not lg.cles_manquantes(code))
    autre = json.loads(Path(f"traductions/{code}.json").read_text(encoding="utf-8"))
    # Les textes a variables sont ecartes : « **{montant}** en {devise} »
    # s'ecrit pareil en francais et en espagnol sans que ce soit un oubli.
    recopiees = [k for k, v in FR.items()
                 if len(v) > 14 and "{" not in v and autre.get(k) == v]
    verifier(f"{code} : aucune valeur francaise recopiee telle quelle",
             not recopiees)


print("\n2. L'application s'affiche vraiment dans la langue choisie")

for code in ("fr", "en", "es", "zh"):
    at = AppTest.from_file("app_tresorerie.py", default_timeout=120)
    at.session_state["langue"] = code
    at.run()

    verifier(f"{code} : l'application demarre sans erreur", not at.exception)
    if at.exception:
        continue

    affiches = textes_affiches(at)
    verifier(f"{code} : {len(affiches)} elements affiches", len(affiches) > 10)

    if code == "fr":
        continue

    restes = sorted({s for s in SENTINELLES
                     if any(s in t for t in affiches)})
    verifier(f"{code} : aucun texte francais residuel", not restes)
    for r in restes[:10]:
        print(f"          · {r[:72]}")


print("\n3. Les valeurs internes ne dependent pas de la langue")

# Une etiquette traduite ne doit jamais servir de cle : sinon changer de
# langue changerait le sens des donnees enregistrees.
app = Path("app_tresorerie.py").read_text(encoding="utf-8")
verifier("le sens d'une operation est teste sur une valeur stable",
         'sens == "entree"' in app and 'sens == "Entrée"' not in app)
verifier("la recurrence passe par une cle stable",
         "RECURRENCES[recur]" in app)

sce = Path("vue_scenarios.py").read_text(encoding="utf-8")
verifier("les scenarios comparent aussi une valeur stable",
         'sens == "entree"' in sce)

import commun                                                  # noqa: E402
verifier("les cles de recurrence sont sans accent ni majuscule",
         all(k.islower() and k.isascii() for k in commun.RECURRENCES))


print("\n4. Les montants suivent la langue, pas le code")

# Defaut releve en production : le solde d'un compte s'affichait « 2 500,00 € »
# a un lecteur anglophone. `Montant.formater()` applique toujours la
# typographie francaise — c'est voulu, le module `argent` ignore la langue —
# donc aucune vue ne doit l'appeler directement.
for chemin in sorted(Path(".").glob("vue_*.py")) + [Path("app_tresorerie.py")]:
    contenu = chemin.read_text(encoding="utf-8")
    verifier(f"{chemin.name} n'appelle pas .formater() directement",
             ".formater()" not in contenu)

from decimal import Decimal                                    # noqa: E402
from argent import Montant                                     # noqa: E402

mille = Montant(Decimal("1234.56"), "EUR")
attendus = {
    "fr": "1 234,56 €",
    "en": "€1,234.56",
    "es": "1.234,56 €",
    "zh": "€1,234.56",
}
for code, attendu in attendus.items():
    obtenu = lg.formater_montant(mille.valeur, "EUR", code)
    verifier(f"{code} : 1234.56 EUR s'ecrit {attendu!r}", obtenu == attendu)

# Le yen n'a pas de centimes, quelle que soit la langue de lecture.
for code in ("fr", "en", "es", "zh"):
    yen = lg.formater_montant(Decimal("1234"), "JPY", code)
    verifier(f"{code} : le yen reste sans decimales ({yen})", "," not in yen[-4:]
             or "." not in yen)


print("\n" + "=" * 62)
print("Toutes les verifications sont passees."
      if not echecs else f"{echecs} echec(s).")
sys.exit(1 if echecs else 0)
