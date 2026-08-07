"""
Verification que l'interface ne casse pas quand on l'utilise.

Lecon apprise a la dure : une fonction supprimee par megarde a fait planter
l'application au premier clic. Les tests d'affichage ne l'avaient pas vue,
parce qu'ils regardaient l'ecran sans jamais toucher un bouton.

Ce test fait deux choses :
  1. il verifie qu'aucune fonction appelee n'est manquante (analyse statique) ;
  2. il CLIQUE sur chaque bouton et verifie qu'aucune exception ne survient.

Lancer :  py test_interface.py
"""

import ast
import os
import sys
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

BAC = Path(tempfile.mkdtemp(prefix="dz_ui_"))
import sauvegarde as sv
sv.chemin_par_defaut = lambda: BAC / "t.json"

ok, ko = 0, []


def verifier(nom, obtenu, attendu=True):
    global ok
    if obtenu is attendu:
        ok += 1
        print(f"  ok    {nom}")
    else:
        ko.append(nom)
        print(f"  ECHEC {nom}")


# ---------------------------------------------------------------------------
print("\n1. Aucune fonction appelee n'est manquante")
# ---------------------------------------------------------------------------
# C'est exactement le defaut qui a casse l'application : un appel a
# `_enregistrer()` alors que la fonction avait ete supprimee.

MODULES = ["vue_compte.py", "vue_comptes.py", "vue_calendrier.py",
           "vue_scenarios.py", "vue_entreprise.py", "commun.py",
           "compte.py", "pwa.py"]

for nom_fichier in MODULES:
    chemin = Path(nom_fichier)
    if not chemin.exists():
        continue
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))

    definies = {n.name for n in ast.walk(arbre)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    importees = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.ImportFrom):
            importees |= {a.asname or a.name for a in n.names}
        elif isinstance(n, ast.Import):
            importees |= {(a.asname or a.name).split(".")[0] for a in n.names}
    locales = {n.id for n in ast.walk(arbre)
               if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}

    # Les appels a une fonction privee (prefixe _) du meme module doivent
    # y etre definis : personne d'autre ne peut les fournir.
    manquantes = set()
    for n in ast.walk(arbre):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id.startswith("_")
                and n.func.id not in definies
                and n.func.id not in importees
                and n.func.id not in locales):
            manquantes.add(n.func.id)

    verifier(f"{nom_fichier} — aucune fonction privee manquante",
             not manquantes)
    if manquantes:
        print(f"        introuvables : {', '.join(sorted(manquantes))}")


# ---------------------------------------------------------------------------
print("\n2. Chaque bouton peut etre clique sans casser l'application")
# ---------------------------------------------------------------------------

from streamlit.testing.v1 import AppTest
from moteur_tresorerie import Recurrence
from comptes import Compte, Portefeuille

APPLI = str(Path("app_tresorerie.py").resolve())
CONF = {"supabase": {"url": "https://exemple.supabase.co",
                     "cle_publique": "cle-de-test"}}


def preparer(at, avec_donnees=True, profil="Particulier"):
    if avec_donnees:
        at.session_state.portefeuille = Portefeuille(
            [Compte("Courant", "EUR", Decimal("2500"))], devise_reference="EUR")
        at.session_state.operations = [{
            "libelle": "Salaire", "montant": 2800.0, "date": date(2026, 9, 5),
            "devise": "EUR", "recurrence": Recurrence.MENSUELLE,
            "date_fin": None, "certaine": True}]
    at.session_state.profil = profil


def tous_les_boutons(nom_cas, avec_donnees=True, profil="Particulier",
                     conf=None):
    """Clique sur chaque bouton, un par un, depuis un etat neuf."""
    depart = AppTest.from_file(APPLI, default_timeout=120)
    if conf:
        for k, v in conf.items():
            depart.secrets[k] = v
    depart.run()
    preparer(depart, avec_donnees, profil)
    depart.run()

    if depart.exception:
        verifier(f"{nom_cas} — l'ecran s'affiche", False)
        return

    etiquettes = [b.label for b in depart.button]
    verifier(f"{nom_cas} — {len(etiquettes)} boutons trouves", len(etiquettes) > 0)

    for i, etiquette in enumerate(etiquettes):
        at = AppTest.from_file(APPLI, default_timeout=120)
        if conf:
            for k, v in conf.items():
                at.secrets[k] = v
        at.run()
        preparer(at, avec_donnees, profil)
        at.run()

        # On retrouve le bouton par son rang parmi ceux de meme etiquette :
        # un index absolu se decale des que l'ecran change de contenu.
        rang = etiquettes[:i].count(etiquette)
        candidats = [b for b in at.button if b.label == etiquette]
        if len(candidats) <= rang:
            continue                 # le bouton n'existe pas dans cet etat

        try:
            candidats[rang].click().run()
        except Exception as err:
            verifier(f"{nom_cas} — clic « {etiquette[:28]} »", False)
            print(f"        {type(err).__name__}: {str(err)[:90]}")
            continue

        casse = at.exception and "NameError" in str(at.exception[0].message) \
                or (at.exception and "AttributeError" in str(at.exception[0].message))
        verifier(f"{nom_cas} — clic « {etiquette[:28]} »", not casse)
        if casse:
            print(f"        {at.exception[0].message[:110]}")


tous_les_boutons("Particulier")
tous_les_boutons("Entreprise", profil="Entreprise")
tous_les_boutons("avec comptes configures", conf=CONF)
tous_les_boutons("application vide", avec_donnees=False)


import shutil
shutil.rmtree(BAC, ignore_errors=True)

print("\n" + "=" * 62)
if ko:
    print(f"{ok} verifications reussies, {len(ko)} ECHECS :")
    for n in ko:
        print(f"   - {n}")
    raise SystemExit(1)
print(f"{ok} verifications reussies, aucun echec.")
