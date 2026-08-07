"""
Verification du socle multilingue.

Le point le plus important n'est pas la traduction des mots, mais le
formatage des nombres : un Espagnol lit « 1.234,56 » comme mille deux cent
trente-quatre, un Anglais lit « un virgule deux ». Se tromper la-dessus sur
une application financiere, c'est perdre la confiance en un coup d'oeil.

Lancer :  py test_langues.py
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import langues
from langues import (LANGUES_DISPONIBLES, LOCALES, couverture, cles_manquantes,
                     detecter, formater_date, formater_montant,
                     formater_nombre, jours_semaine, locale, nom_mois,
                     pluriel, traduire)

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


FINE = " "      # espace fine insecable, separateur francais
INSEC = " "     # espace insecable, avant le symbole


# ---------------------------------------------------------------------------
print("\n1. Les quatre langues sont declarees")
# ---------------------------------------------------------------------------

verifier("4 langues", len(LANGUES_DISPONIBLES), 4)
verifier("dans l'ordre attendu", LANGUES_DISPONIBLES, ["fr", "en", "es", "zh"])
for code, nom in [("fr", "Français"), ("en", "English"),
                  ("es", "Español"), ("zh", "中文")]:
    verifier(f"{code} se nomme « {nom} »", locale(code).nom_natif, nom)

verifier("langue inconnue retombe sur le francais", locale("xx").code, "fr")
verifier("code regional accepte", locale("fr-CA").code, "fr")
verifier("majuscules acceptees", locale("EN").code, "en")


# ---------------------------------------------------------------------------
print("\n2. LE POINT CRITIQUE : les nombres selon la langue")
# ---------------------------------------------------------------------------

# Le meme nombre, quatre ecritures. Une erreur ici fait lire mille pour un.
verifier("français : 1 234,56", formater_nombre(1234.56, 2, "fr"),
         f"1{FINE}234,56")
verifier("anglais : 1,234.56", formater_nombre(1234.56, 2, "en"), "1,234.56")
verifier("espagnol : 1.234,56", formater_nombre(1234.56, 2, "es"), "1.234,56")
verifier("chinois : 1,234.56", formater_nombre(1234.56, 2, "zh"), "1,234.56")

# Le piege : francais et espagnol inversent les deux separateurs. Un
# remplacement naif produirait 1,234,56 ou 1.234.56.
verifier("espagnol ne confond pas ses separateurs",
         formater_nombre(1234567.89, 2, "es"), "1.234.567,89")
verifier("français sur un million",
         formater_nombre(1234567.89, 2, "fr"), f"1{FINE}234{FINE}567,89")

verifier("negatif français", formater_nombre(-950.5, 2, "fr"), "-950,50")
verifier("negatif anglais", formater_nombre(-950.5, 2, "en"), "-950.50")
verifier("sans decimale", formater_nombre(1234, 0, "fr"), f"1{FINE}234")
verifier("zero", formater_nombre(0, 2, "en"), "0.00")
verifier("un Decimal est accepte",
         formater_nombre(Decimal("0.1") + Decimal("0.2"), 2, "en"), "0.30")


# ---------------------------------------------------------------------------
print("\n3. Montants : place du symbole")
# ---------------------------------------------------------------------------

verifier("français : symbole apres", formater_montant(1234.56, "EUR", "fr"),
         f"1{FINE}234,56{INSEC}€")
verifier("anglais : symbole avant", formater_montant(1234.56, "USD", "en"),
         "$1,234.56")
verifier("espagnol : symbole apres", formater_montant(1234.56, "EUR", "es"),
         f"1.234,56{INSEC}€")
verifier("chinois : symbole avant", formater_montant(1234.56, "CNY", "zh"),
         "¥1,234.56")

# Le signe reste devant le tout : -$1,234.56 et non $-1,234.56
verifier("negatif anglais bien place", formater_montant(-1234.56, "USD", "en"),
         "-$1,234.56")
verifier("negatif français", formater_montant(-1234.56, "EUR", "fr"),
         f"-1{FINE}234,56{INSEC}€")

# Les decimales viennent de la DEVISE, jamais de la langue : le yen n'a
# pas de centimes, qu'on le lise en anglais ou en chinois.
verifier("yen sans decimale en anglais",
         formater_montant(1500, "JPY", "en"), "¥1,500")
verifier("yen sans decimale en français",
         formater_montant(1500, "JPY", "fr"), f"1{FINE}500{INSEC}¥")
verifier("FCFA sans decimale",
         formater_montant(250000, "XOF", "fr"), f"250{FINE}000{INSEC}FCFA")
verifier("dinar a 3 decimales",
         formater_montant(1234.567, "KWD", "en"), "KD1,234.567")


# ---------------------------------------------------------------------------
print("\n4. Dates")
# ---------------------------------------------------------------------------

j = date(2026, 8, 7)
verifier("français : 07/08/2026", formater_date(j, "fr"), "07/08/2026")
verifier("espagnol : 07/08/2026", formater_date(j, "es"), "07/08/2026")
verifier("chinois : 2026年08月07日", formater_date(j, "zh"), "2026年08月07日")
# On evite le format americain m/j/a, ambigu partout ailleurs.
verifier("anglais : 07 Aug 2026", formater_date(j, "en"), "07 Aug 2026")
verifier("anglais n'utilise pas m/j/a", "/" in formater_date(j, "en"), False)

verifier("mois en français", nom_mois(8, "fr"), "Août")
verifier("mois en anglais", nom_mois(8, "en"), "August")
verifier("mois en espagnol", nom_mois(8, "es"), "Agosto")
verifier("mois en chinois", nom_mois(8, "zh"), "八月")

# L'anglais commence la semaine le dimanche.
verifier("semaine française commence lundi", jours_semaine("fr")[0], "Lun")
verifier("semaine anglaise commence dimanche", jours_semaine("en")[0], "Sun")
verifier("7 jours partout", all(len(jours_semaine(c)) == 7
                                for c in LANGUES_DISPONIBLES), True)


# ---------------------------------------------------------------------------
print("\n5. Detection de la langue du navigateur")
# ---------------------------------------------------------------------------

verifier("en-tete français", detecter("fr-FR,fr;q=0.9,en-US;q=0.8"), "fr")
verifier("en-tete anglais", detecter("en-US,en;q=0.9"), "en")
verifier("en-tete espagnol", detecter("es-MX,es;q=0.9"), "es")
verifier("en-tete chinois", detecter("zh-CN,zh;q=0.9"), "zh")
# Une langue non geree ne doit pas casser : on prend la suivante connue.
verifier("langue inconnue puis connue", detecter("de-DE,de;q=0.9,en;q=0.8"), "en")
verifier("aucune langue connue", detecter("de-DE,it;q=0.9"), "fr")
verifier("en-tete vide", detecter(""), "fr")
verifier("en-tete absent", detecter(None), "fr")


# ---------------------------------------------------------------------------
print("\n6. Textes")
# ---------------------------------------------------------------------------

verifier("texte français", traduire("app.particulier", "fr"), "Particulier")
verifier("texte anglais", traduire("app.particulier", "en"), "Personal")
verifier("texte espagnol", traduire("app.particulier", "es"), "Particular")
verifier("texte chinois", traduire("app.particulier", "zh"), "个人")

# Un texte manquant ne doit jamais effacer un ecran.
verifier("cle inconnue rend la cle", traduire("cle.qui.nexiste.pas", "fr"),
         "cle.qui.nexiste.pas")

verifier("variable remplacee",
         traduire("compte.enregistre_a", "fr", heure="18:25"),
         "Enregistré à 18:25")
verifier("variable en anglais",
         traduire("compte.enregistre_a", "en", heure="18:25"),
         "Saved at 18:25")
# Une variable oubliee ne doit pas faire planter l'ecran.
verifier("variable absente : texte brut",
         "{" in traduire("compte.enregistre_a", "fr"), True)


# ---------------------------------------------------------------------------
print("\n7. Pluriels")
# ---------------------------------------------------------------------------

# Le français met au singulier a zero, l'anglais au pluriel.
verifier("français : 0 compte",
         pluriel("gen.compte_singulier", "gen.compte_pluriel", 0, "fr"),
         "0 compte")
verifier("anglais : 0 accounts",
         pluriel("gen.compte_singulier", "gen.compte_pluriel", 0, "en"),
         "0 accounts")
verifier("français : 1 compte",
         pluriel("gen.compte_singulier", "gen.compte_pluriel", 1, "fr"),
         "1 compte")
verifier("français : 3 comptes",
         pluriel("gen.compte_singulier", "gen.compte_pluriel", 3, "fr"),
         "3 comptes")
verifier("anglais : 1 account",
         pluriel("gen.compte_singulier", "gen.compte_pluriel", 1, "en"),
         "1 account")
# Le chinois n'accorde pas : la forme est identique, seul le nombre change.
# On compare donc ce qui suit le nombre, pas le texte entier.
def _forme(nombre, code):
    texte = pluriel("gen.compte_singulier", "gen.compte_pluriel", nombre, code)
    return texte.replace(str(nombre), "").strip()

verifier("chinois : forme identique a 1 et a 5",
         _forme(1, "zh"), _forme(5, "zh"))
verifier("anglais : forme differente a 1 et a 5",
         _forme(1, "en") != _forme(5, "en"), True)
verifier("français : forme differente a 1 et a 5",
         _forme(1, "fr") != _forme(3, "fr"), True)


# ---------------------------------------------------------------------------
print("\n8. Completude des fichiers")
# ---------------------------------------------------------------------------

for code in LANGUES_DISPONIBLES:
    chemin = Path("traductions") / f"{code}.json"
    verifier(f"{code}.json existe", chemin.exists(), True)
    contenu = json.loads(chemin.read_text(encoding="utf-8"))
    verifier(f"{code}.json n'est pas vide", len(contenu) > 50, True)

for code in ["en", "es", "zh"]:
    manquantes = cles_manquantes(code)
    verifier(f"{code} : aucune cle manquante ({couverture(code)} %)",
             manquantes, [])

# Aucun texte ne doit rester en français dans les autres langues.
fr = json.loads((Path("traductions") / "fr.json").read_text(encoding="utf-8"))
for code in ["en", "es", "zh"]:
    autre = json.loads((Path("traductions") / f"{code}.json").read_text(encoding="utf-8"))
    identiques = [c for c in fr if fr[c] == autre.get(c) and len(fr[c]) > 12]
    verifier(f"{code} : aucun texte laisse en français", identiques, [])




# ---------------------------------------------------------------------------
print("\n9. Le selecteur de langue, dans les deux sens")
# ---------------------------------------------------------------------------
# Ces verifications protegent deux pannes reelles, survenues coup sur coup :
#   · widget avec sa propre cle  -> il ecrasait la langue chargee d'un compte
#   · widget lie a la cle langue -> le code ne pouvait plus la changer du tout
# Il faut que les DEUX sens fonctionnent.

import os
import shutil
import tempfile
from pathlib import Path

from streamlit.testing.v1 import AppTest

_BAC = Path(tempfile.mkdtemp(prefix="dz_lang_"))
import sauvegarde as _sv
_sv.chemin_par_defaut = lambda: _BAC / "t.json"

# Le script d'essai doit vivre a cote des modules, sinon `import commun`
# echoue et le test passerait a cote de ce qu'il pretend verifier.
_SCRIPT = Path("_ecran_essai_langue.py").resolve()
_SCRIPT.write_text(
    "import streamlit as st\n"
    "import commun, sauvegarde as sv\n"
    "commun.initialiser()\n"
    "with st.sidebar:\n"
    "    commun.selecteur_langue()\n"
    "if '_forcer' in st.session_state:\n"
    "    commun._appliquer(sv.Donnees(langue=st.session_state['_forcer'],\n"
    "                                 profil='Particulier'))\n"
    "st.write('langue=' + st.session_state['langue'])\n",
    encoding="utf-8")


def _langue_affichee(at) -> str:
    """Lit la langue telle que l'ecran l'affiche vraiment."""
    for element in at.markdown:
        if element.value.startswith("langue="):
            return element.value.split("=", 1)[1]
    return "?"


try:
    # Sens 1 : le CODE change la langue — chargement d'un compte, import.
    at = AppTest.from_file(str(_SCRIPT), default_timeout=60)
    at.run()
    at.session_state["_forcer"] = "en"
    at.run()
    verifier("le code peut changer la langue sans erreur",
             at.exception is None or len(at.exception) == 0, True)
    verifier("... et le changement atteint l'ecran", _langue_affichee(at), "en")

    # Sens 2 : l'UTILISATEUR change la langue dans le menu.
    at2 = AppTest.from_file(str(_SCRIPT), default_timeout=60)
    at2.run()
    verifier("le menu de langue est present", len(at2.selectbox) >= 1, True)
    if at2.selectbox:
        at2.selectbox[0].select("es").run()
        verifier("le choix de l'utilisateur est pris en compte",
                 _langue_affichee(at2), "es")
finally:
    _SCRIPT.unlink(missing_ok=True)
    shutil.rmtree(_BAC, ignore_errors=True)


print("\n" + "=" * 62)
if ko:
    print(f"{ok} verifications reussies, {len(ko)} ECHECS :")
    for n in ko:
        print(f"   - {n}")
    raise SystemExit(1)
print(f"{ok} verifications reussies, aucun echec.")