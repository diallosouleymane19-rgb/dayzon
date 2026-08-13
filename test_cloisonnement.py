"""
Verification du cloisonnement des donnees entre visiteurs.

Ce test protege la correction la plus importante du projet : sur un serveur
partage, les donnees financieres d'un visiteur ne doivent JAMAIS apparaitre
chez un autre.

Lancer :  py test_cloisonnement.py
"""

import os
import shutil
import tempfile
from pathlib import Path

import sauvegarde as sv

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


class Heberge:
    """Simule un serveur partage en posant la variable d'environnement."""
    def __enter__(self):
        os.environ["PREVUFLOW_HEBERGE"] = "1"
        return self

    def __exit__(self, *a):
        os.environ.pop("PREVUFLOW_HEBERGE", None)


BAC = Path(tempfile.mkdtemp(prefix="dz_cloison_"))
sv.chemin_par_defaut = lambda: BAC / "serveur.json"

DONNEES_A = sv.Donnees(
    profil="Entreprise",
    comptes=[{"nom": "Compte de Souleymane", "devise": "EUR", "solde": "42000"}])


# ---------------------------------------------------------------------------
print("\n1. Detection du mode")
# ---------------------------------------------------------------------------

verifier("en local, mode local", sv.mode_local(), True)
with Heberge():
    verifier("en heberge, mode local faux", sv.mode_local(), False)

verifier("le message local parle de l'ordinateur",
         "cet ordinateur" in sv.raison_mode(), True)
with Heberge():
    verifier("le message heberge previent",
             "rien n'est enregistré sur le serveur" in sv.raison_mode().lower(), True)


# ---------------------------------------------------------------------------
print("\n2. LA FAILLE FERMEE : aucune ecriture sur un serveur partage")
# ---------------------------------------------------------------------------

with Heberge():
    try:
        sv.enregistrer(DONNEES_A)
        verifier("l'ecriture est refusee en ligne", False, True)
    except sv.ErreurSauvegarde as err:
        verifier("l'ecriture est refusee en ligne", True, True)
        verifier("le message explique pourquoi",
                 "partagé" in str(err), True)
        verifier("le message propose une solution",
                 "Télécharger" in str(err), True)

verifier("aucun fichier n'a ete cree",
         (BAC / "serveur.json").exists(), False)


# ---------------------------------------------------------------------------
print("\n3. LA FAILLE FERMEE : aucune lecture du fichier d'autrui")
# ---------------------------------------------------------------------------

# Un fichier existe sur le serveur (depose par erreur, ou reste d'un test).
sv.enregistrer(DONNEES_A)                      # en local : autorise
verifier("le fichier existe bien", (BAC / "serveur.json").exists(), True)

with Heberge():
    vu = sv.charger()
    verifier("un visiteur ne voit RIEN", vu, None)

# En local, l'utilisateur retrouve normalement ses donnees.
vu_local = sv.charger()
verifier("en local, les donnees reviennent", vu_local is not None, True)
verifier("... et ce sont les bonnes",
         vu_local.comptes[0]["nom"], "Compte de Souleymane")


# ---------------------------------------------------------------------------
print("\n4. Un chemin explicite reste possible")
# ---------------------------------------------------------------------------

# Le garde-fou ne doit pas empecher un usage delibere, par exemple un test
# ou un export vers un emplacement choisi.
explicite = BAC / "choisi.json"
with Heberge():
    sv.enregistrer(DONNEES_A, explicite)
    verifier("ecriture possible avec chemin explicite", explicite.exists(), True)
    relu = sv.charger(explicite)
    verifier("relecture possible avec chemin explicite",
             relu.comptes[0]["nom"], "Compte de Souleymane")


# ---------------------------------------------------------------------------
print("\n5. Emporter ses donnees sans passer par le disque")
# ---------------------------------------------------------------------------

with Heberge():
    octets = sv.vers_octets(DONNEES_A)
    verifier("le fichier est produit en memoire", isinstance(octets, bytes), True)
    verifier("il contient les donnees", b"Compte de Souleymane" in octets, True)

    repris = sv.depuis_octets(octets)
    verifier("relecture fidele", repris.comptes[0]["solde"], "42000")
    verifier("profil conserve", repris.profil, "Entreprise")

    nom = sv.nom_fichier_export()
    verifier("le nom de fichier est date", nom.startswith("prevuflow_"), True)
    verifier("... et se termine en .json", nom.endswith(".json"), True)


# ---------------------------------------------------------------------------
print("\n6. Fichier depose invalide")
# ---------------------------------------------------------------------------

for nom, contenu, fragment in [
    ("texte quelconque", b"ceci n'est pas du JSON", "valide"),
    ("liste au lieu d'objet", b'["a","b"]', "format attendu"),
    ("format trop recent", b'{"version_format": 99}', "plus récente"),
]:
    try:
        sv.depuis_octets(contenu)
        verifier(f"{nom} refuse", False, True)
    except sv.ErreurSauvegarde as err:
        verifier(f"{nom} refuse", fragment.lower() in str(err).lower(), True)

# Un fichier binaire ne doit pas faire planter la lecture.
try:
    sv.depuis_octets(b"\xff\xfe\x00\x01")
    verifier("binaire refuse", False, True)
except sv.ErreurSauvegarde:
    verifier("binaire refuse", True, True)


shutil.rmtree(BAC, ignore_errors=True)
print("\n" + "=" * 62)
if ko:
    print(f"{ok} verifications reussies, {len(ko)} ECHECS :")
    for n in ko:
        print(f"   - {n}")
    raise SystemExit(1)
print(f"{ok} verifications reussies, aucun echec.")
