"""
VERIFICATION EN EXECUTION REELLE — les quatre langues
PrevuFlow — SMD Global Consulting LLC

Un fichier de traduction complet ne prouve rien : une cle peut exister sans
etre branchee, et l'ecran reste alors en francais. Ce test lance vraiment
l'application dans chaque langue et cherche, parmi tout ce qui s'affiche,
les phrases francaises du fichier de reference.

Il ne teste pas la qualite de la traduction — cela releve d'une relecture
humaine — mais il rend impossible d'oublier de brancher un ecran.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Sans cela, le premier passage ecrit une sauvegarde locale que le second
# recharge — langue comprise. Le test en francais imposait alors sa langue
# aux trois suivants, et l'anglais se retrouvait plein de francais.
# On se declare heberge : aucune lecture, aucune ecriture de fichier.
os.environ["PREVUFLOW_HEBERGE"] = "1"

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

    # Les choix proposes comptent autant que les etiquettes : le catalogue
    # de scenarios vivait dans les options d'un multiselect, invisible pour
    # une premiere version de ce test.
    for liste in (at.multiselect, at.selectbox, at.radio):
        for widget in liste:
            valeurs += [o for o in getattr(widget, "options", [])]
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

def avec_donnees(at: AppTest) -> None:
    """
    Place un compte et quelques echeances avant le premier rendu.

    Sans donnees, l'application s'arrete a l'ecran d'accueil et le
    calendrier n'est jamais rendu. Un test qui se contente de l'ecran vide
    laisse passer la moitie des textes — c'est ainsi qu'un « le 05/09 »
    est parti en production.

    On remplit l'etat plutot que de cliquer sur « Charger un exemple » :
    AppTest ne sait pas relire un radio muni d'un `format_func`, et le
    clic echouerait sur le selecteur de profil.
    """
    from datetime import date, timedelta
    from decimal import Decimal

    from comptes import Compte, Portefeuille
    from moteur_tresorerie import Recurrence

    p = Portefeuille(devise_reference="EUR")
    p.ajouter(Compte("Compte courant", "EUR", Decimal("2500")))
    at.session_state["portefeuille"] = p

    jour = date.today()
    at.session_state["operations"] = [
        {"libelle": "Salaire", "montant": 2800, "date": jour,
         "devise": "EUR", "recurrence": Recurrence.MENSUELLE, "certaine": True},
        {"libelle": "Loyer", "montant": -950, "date": jour + timedelta(days=3),
         "devise": "EUR", "recurrence": Recurrence.MENSUELLE, "certaine": True},
        {"libelle": "Assurance", "montant": -680,
         "date": jour + timedelta(days=25), "devise": "EUR",
         "recurrence": Recurrence.ANNUELLE, "certaine": False},
    ]


for code in ("fr", "en", "es", "zh"):
    at = AppTest.from_file("app_tresorerie.py", default_timeout=120)
    at.session_state["langue"] = code
    avec_donnees(at)
    at.run()

    verifier(f"{code} : l'application demarre sans erreur", not at.exception)
    if at.exception:
        print(f"          {at.exception[0].message}")
        continue

    affiches = textes_affiches(at)
    verifier(f"{code} : le calendrier est rendu ({len(affiches)} elements)",
             len(affiches) > 25)

    if code == "fr":
        continue

    restes = sorted({s for s in SENTINELLES
                     if any(s in t for t in affiches)})
    verifier(f"{code} : aucun texte francais residuel", not restes)
    for r in restes[:10]:
        print(f"          · {r[:72]}")

    # Les sentinelles ne voient que le francais DECLARE dans fr.json. Un
    # module jamais branche — analyse_lisible l'a ete pendant tout le
    # chantier — passait donc inapercu. On cherche aussi des mots francais
    # caracteristiques, qui n'existent dans aucune des trois autres langues.
    MOTS = ("Vous ", "Votre ", "Vos ", "chaque mois", "par mois", "revenus",
            "dépense", "n'est", "d'un", "qu'un", "Il vous")
    suspects = sorted({t[:78] for t in affiches
                       if any(m in t for m in MOTS)})
    verifier(f"{code} : aucun mot francais non declare", not suspects)
    for s in suspects[:8]:
        print(f"          ? {s}")


print("\n2 bis. L'ecran d'abonnement s'affiche dans la langue choisie")

# Cet ecran n'est rendu par aucun autre test : il remplace tout le corps de
# la page et ne s'ouvre que sur demande. Un module branche nulle part est
# exactement ce qui a laisse passer du francais en production.
def sans_reseau(at: AppTest) -> None:
    """
    Fournit une configuration Stripe factice et un abonnement deja lu.

    Sans cela, l'ecran interrogerait vraiment Stripe a chaque rendu : quatre
    passages, huit appels reseau, et un test qui echoue des que la connexion
    manque.
    """
    from abonnement import Abonnement, ConfigStripe, Periode, Plan

    at.session_state["config_stripe"] = ConfigStripe(
        cle_secrete="sk_test_faux",
        prix={(p, pe): f"price_{p.value}_{pe.value}"
              for p in (Plan.PARTICULIER, Plan.ENTREPRISE)
              for pe in (Periode.MENSUELLE, Periode.ANNUELLE)},
        url_retour="https://prevuflow.streamlit.app")
    at.session_state["abonnement"] = Abonnement(plan=Plan.DECOUVERTE)
    at.session_state["page"] = "abonnement"


for code in ("fr", "en", "es", "zh"):
    at = AppTest.from_file("app_tresorerie.py", default_timeout=120)
    at.session_state["langue"] = code
    avec_donnees(at)
    sans_reseau(at)
    at.run()

    verifier(f"{code} : l'ecran d'abonnement demarre", not at.exception)
    if at.exception:
        print(f"          {at.exception[0].message}")
        continue

    affiches = textes_affiches(at)
    verifier(f"{code} : les trois formules sont rendues",
             sum(1 for t in affiches if "dz-sc" in t) >= 3)

    if code == "fr":
        continue

    restes = sorted({s for s in SENTINELLES if any(s in t for t in affiches)})
    verifier(f"{code} : aucun texte francais residuel sur l'abonnement",
             not restes)
    for r in restes[:6]:
        print(f"          · {r[:72]}")

    MOTS_ABO = ("Vous ", "Votre ", "Vos ", "par mois", "par an", "Choisir",
                "Gratuit", "n'est", "d'un")
    suspects = sorted({t[:78] for t in affiches
                       if any(m in t for m in MOTS_ABO)})
    verifier(f"{code} : aucun mot francais non declare sur l'abonnement",
             not suspects)
    for s in suspects[:6]:
        print(f"          ? {s}")


print("\n2 ter. Le decompte de l'essai s'affiche en haut de l'application")

# Sans ce bandeau, la periode d'essai se terminerait sans que personne
# l'ait vue passer : la page d'abonnement n'est visitee que par ceux qui
# la cherchent, c'est-a-dire presque personne.
from datetime import timedelta as _td                          # noqa: E402

from abonnement import essai as _essai                         # noqa: E402


def _encarts(at: AppTest) -> list[str]:
    return [str(m.value) for m in at.markdown
            if '<div class="dz-msg' in str(m.value)]


for titre, jours_ecoules, attendu in (("essai neuf", 0, "14"),
                                      ("essai finissant", 12, "2"),
                                      ("essai termine", 30, None)):
    at = AppTest.from_file("app_tresorerie.py", default_timeout=120)
    at.session_state["langue"] = "fr"
    avec_donnees(at)
    sans_reseau(at)
    at.session_state["page"] = ""           # on reste sur l'application
    at.session_state["abonnement"] = _essai(
        __import__("datetime").date.today() - _td(days=jours_ecoules))
    at.run()

    verifier(f"{titre} : l'application demarre", not at.exception)
    if at.exception:
        print(f"          {at.exception[0].message}")
        continue

    encarts = " ".join(_encarts(at))
    verifier(f"{titre} : un encart d'abonnement est rendu", bool(encarts))
    if attendu:
        verifier(f"{titre} : le decompte annonce {attendu} jours",
                 f"{attendu} jours" in encarts)
    else:
        # Un essai echu ne doit pas afficher « 0 jours restants » : la
        # phrase serait exacte et incomprehensible. On cherche « restants »
        # et non « 0 jours » — la phrase de repli parle de 90 jours, et
        # « 90 jours » contient « 0 jours ».
        verifier(f"{titre} : la fin est annoncee, pas un decompte a zero",
                 "terminé" in encarts and "restants" not in encarts)
    verifier(f"{titre} : le bouton vers les formules est present",
             any(b.label for b in at.button if "formules" in b.label))


print("\n2 quater. Le profil Entreprise s'affiche dans la langue choisie")

# C'est l'ecran le plus cher — le plan a 29 $ — et il est reste francais
# jusqu'au 13 aout 2026 : aucun test ne l'ouvrait. Un client anglophone
# lisait ses propres indicateurs en francais.
def avec_factures(at: AppTest) -> None:
    """Des factures clients et fournisseurs, pour que tout l'ecran se rende."""
    from datetime import date, timedelta
    from decimal import Decimal

    from analyse_entreprise import Facture, LectureFactures
    from import_intelligent import Mouvement

    jour = date.today()
    at.session_state["mouvements"] = [
        Mouvement(jour - timedelta(days=n * 6), "Achat", Decimal("-410"))
        for n in range(8)
    ] + [Mouvement(jour - timedelta(days=n * 30), "Client", Decimal("5200"))
         for n in range(3)]

    clients = [
        Facture(date_emission=jour - timedelta(days=70), tiers="Alpha",
                montant=Decimal("9000"), sens="client",
                echeance=jour - timedelta(days=40)),
        Facture(date_emission=jour - timedelta(days=50), tiers="Beta",
                montant=Decimal("2000"), sens="client",
                echeance=jour - timedelta(days=20),
                date_paiement=jour - timedelta(days=15)),
    ]
    fournisseurs = [
        Facture(date_emission=jour - timedelta(days=60), tiers="Gamma",
                montant=Decimal("3000"), sens="fournisseur",
                echeance=jour - timedelta(days=30),
                date_paiement=jour - timedelta(days=28)),
    ]
    at.session_state["lecture_fc"] = LectureFactures(
        clients, {"date_emission": "Date"}, 0, Decimal("11000"))
    at.session_state["lecture_ff"] = LectureFactures(
        fournisseurs, {"date_emission": "Date"}, 0, Decimal("3000"))
    at.session_state["profil"] = "Entreprise"


for code in ("fr", "en", "es", "zh"):
    at = AppTest.from_file("app_tresorerie.py", default_timeout=180)
    at.session_state["langue"] = code
    avec_donnees(at)
    avec_factures(at)
    at.run()

    verifier(f"{code} : le profil Entreprise demarre", not at.exception)
    if at.exception:
        print(f"          {at.exception[0].message[:170]}")
        continue

    affiches = textes_affiches(at)
    verifier(f"{code} : l'ecran Entreprise est rendu ({len(affiches)} elements)",
             len(affiches) > 20)

    if code == "fr":
        continue

    restes = sorted({s for s in SENTINELLES if any(s in t for t in affiches)})
    verifier(f"{code} : aucun texte francais residuel en Entreprise", not restes)
    for r in restes[:8]:
        print(f"          · {r[:74]}")

    MOTS_ENT = ("Vous ", "Votre ", "Vos ", "par mois", "jours en moyenne",
                "trésorerie", "factures", "clients vous", "d'affaires",
                "n'est", "aucune", "argent")
    suspects = sorted({t[:80] for t in affiches
                       if any(m in t for m in MOTS_ENT)})
    verifier(f"{code} : aucun mot francais non declare en Entreprise",
             not suspects)
    for s in suspects[:8]:
        print(f"          ? {s}")


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

# Meme raisonnement pour les dates : « 05/09 » se lit 5 septembre en France
# et 9 mai aux Etats-Unis. Un strftime avec des barres obliques dans une vue
# est donc toujours une erreur ; %Y%m%d dans un nom de fichier ne l'est pas.
motif_date = re.compile(r"strftime\(\s*['\"][^'\"]*/")
for chemin in sorted(Path(".").glob("vue_*.py")) + [Path("app_tresorerie.py")]:
    contenu = chemin.read_text(encoding="utf-8")
    verifier(f"{chemin.name} n'ecrit pas de date au format francais en dur",
             not motif_date.search(contenu))

print("\n5. Les messages d'authentification suivent la langue")

# Ces messages n'apparaissent qu'en cas d'erreur : aucun test d'ecran ne
# les rend. Ils etaient restes en francais pendant tout le chantier.
import compte                                                  # noqa: E402
import streamlit as st                                         # noqa: E402

for code, extrait in (("fr", "adresse"), ("en", "email"),
                      ("es", "correo"), ("zh", "邮")):
    st.session_state["langue"] = code
    try:
        compte.inscrire("pas-une-adresse", "motdepasselong")
        message = ""
    except compte.ErreurCompte as err:
        message = str(err)
    verifier(f"{code} : l'adresse invalide est signalee dans la langue "
             f"({message[:34]})", extrait in message.lower())

st.session_state["langue"] = "en"
try:
    compte.changer_mot_de_passe("court")
    message = ""
except compte.ErreurCompte as err:
    message = str(err)
verifier("en : le mot de passe trop court est en anglais",
         "sign" in message.lower() or "password" in message.lower())
st.session_state["langue"] = "fr"

# Aucune phrase francaise ne doit subsister en dur dans le module.
src_compte = Path("compte.py").read_text(encoding="utf-8")
en_dur = re.findall(r'ErreurCompte\(\s*"([^"]{18,})"', src_compte)
verifier(f"compte.py n'a plus de message en dur ({len(en_dur)} trouve(s))",
         not en_dur)
for m in en_dur[:5]:
    print(f"          · {m[:70]}")


print("\n5 bis. Les erreurs des modules purs suivent la langue")

# Ces messages n'apparaissent qu'au pire moment — un fichier illisible, un
# taux manquant, un doublon. Ils sont restes francais jusqu'au 13 aout 2026,
# alors meme que tout le reste de l'ecran etait traduit.
import io as _io                                                # noqa: E402

import argent as _argent                                        # noqa: E402
import comptes as _comptes                                      # noqa: E402
import import_intelligent as _imp                               # noqa: E402
import sauvegarde as _sauv                                      # noqa: E402


def _message(action) -> str:
    try:
        action()
    except Exception as erreur:
        return str(erreur)
    return ""


for code, extrait in (("fr", "reconnu"), ("en", "recognised"),
                      ("es", "reconocido"), ("zh", "无法识别")):
    st.session_state["langue"] = code
    texte = _message(lambda: _imp.analyser(_io.BytesIO(b"x"), "releve.txt"))
    verifier(f"{code} : format de fichier refuse dans la langue "
             f"({texte[:30]})", extrait in texte)

for code, extrait in (("fr", "fini"), ("en", "finite"),
                      ("es", "finito"), ("zh", "有限")):
    st.session_state["langue"] = code
    texte = _message(lambda: _argent.Montant(Decimal("nan"), "EUR"))
    verifier(f"{code} : montant invalide dans la langue ({texte[:30]})",
             extrait in texte)

for code, extrait in (("fr", "existe"), ("en", "already exists"),
                      ("es", "Ya existe"), ("zh", "已存在")):
    st.session_state["langue"] = code

    def _doublon():
        p = _comptes.Portefeuille(devise_reference="EUR")
        p.ajouter(_comptes.Compte("A", "EUR", Decimal("1")))
        p.ajouter(_comptes.Compte("A", "EUR", Decimal("2")))

    texte = _message(_doublon)
    verifier(f"{code} : compte en double dans la langue ({texte[:30]})",
             extrait in texte)

for code, extrait in (("fr", "désactivé"), ("en", "off online"),
                      ("es", "desactivado"), ("zh", "已关闭")):
    st.session_state["langue"] = code
    texte = _message(lambda: _sauv.enregistrer(_sauv.Donnees()))
    verifier(f"{code} : refus d'ecrire en ligne dans la langue "
             f"({texte[:30]})", extrait in texte)

st.session_state["langue"] = "fr"


print("\n6. Les montants suivent la langue, pas le code")

# Le yen n'a pas de centimes, quelle que soit la langue de lecture.
for code in ("fr", "en", "es", "zh"):
    yen = lg.formater_montant(Decimal("1234"), "JPY", code)
    verifier(f"{code} : le yen reste sans decimales ({yen})", "," not in yen[-4:]
             or "." not in yen)


print("\n" + "=" * 62)
print("Toutes les verifications sont passees."
      if not echecs else f"{echecs} echec(s).")
sys.exit(1 if echecs else 0)
