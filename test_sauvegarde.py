"""
Verification de la sauvegarde.

Aucun fichier n'est ecrit ailleurs que dans un dossier temporaire,
supprime a la fin.

Lancer :  py test_sauvegarde.py
"""

import json
import shutil
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sauvegarde import (Donnees, ErreurSauvegarde, VERSION_FORMAT, charger,
                        chemin_par_defaut, dossier_par_defaut, enregistrer,
                        exporter_vers, informations, supprimer)

ok, ko = 0, []
BAC = Path(tempfile.mkdtemp(prefix="dayzon_test_"))


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
    except ErreurSauvegarde as err:
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


def donnees_de_test() -> Donnees:
    return Donnees(
        profil="Entreprise",
        devise_reference="EUR",
        comptes=[
            {"nom": "Courant", "devise": "EUR", "solde": "8472.30",
             "identifiant": "aaa", "actif": True},
            {"nom": "Dakar", "devise": "XOF", "solde": "5000000",
             "identifiant": "bbb", "actif": True},
        ],
        operations=[
            {"libelle": "Salaire", "montant": Decimal("2800.00"),
             "date": date(2026, 9, 5), "devise": "EUR",
             "recurrence": "mensuelle", "certaine": True},
            {"libelle": "Loyer", "montant": Decimal("-950.50"),
             "date": date(2026, 9, 3), "devise": "EUR",
             "recurrence": "mensuelle", "certaine": True},
        ],
        taux=[{"base": "XOF", "contre": "EUR", "valeur": "0.001524",
               "observe_le": "2026-08-01", "source": "BCEAO"}],
    )


# ---------------------------------------------------------------------------
print("\n1. LE DEFAUT CORRIGE : les donnees survivent")
# ---------------------------------------------------------------------------

fichier = BAC / "essai.json"
verifier("aucun fichier au depart", charger(fichier), None)

enregistrer(donnees_de_test(), fichier)
verifier("le fichier existe apres enregistrement", fichier.exists(), True)

relu = charger(fichier)
verifier("les donnees reviennent", relu is not None, True)
verifier("profil conserve", relu.profil, "Entreprise")
verifier("devise de reference conservee", relu.devise_reference, "EUR")
verifier("2 comptes relus", len(relu.comptes), 2)
verifier("2 operations relues", len(relu.operations), 2)
verifier("1 taux relu", len(relu.taux), 1)


# ---------------------------------------------------------------------------
print("\n2. Les montants restent exacts")
# ---------------------------------------------------------------------------

# Le piege : ecrire un Decimal en float dans le fichier reintroduirait
# exactement les erreurs de centime que le reste du programme evite.
montant = relu.operations[0]["montant"]
verifier("un montant reste un Decimal", isinstance(montant, Decimal), True)
verifier("valeur exacte au centime", montant, Decimal("2800.00"))
verifier("montant negatif exact", relu.operations[1]["montant"], Decimal("-950.50"))

# Verification directe dans le fichier : aucun nombre flottant ne doit y figurer.
brut = json.loads(fichier.read_text(encoding="utf-8"))
verifier("le montant est stocke en texte",
         brut["operations"][0]["montant"], {"__decimal__": "2800.00"})
verifier("la date est stockee en texte",
         brut["operations"][0]["date"], {"__date__": "2026-09-05"})

# Un Decimal fragile : 0,1 + 0,2 doit revenir a 0,3 exactement.
f2 = BAC / "precision.json"
enregistrer(Donnees(operations=[{"m": Decimal("0.1") + Decimal("0.2")}]), f2)
verifier("0,3 survit a l'aller-retour",
         charger(f2).operations[0]["m"], Decimal("0.3"))


# ---------------------------------------------------------------------------
print("\n3. Les dates restent des dates")
# ---------------------------------------------------------------------------

jour = relu.operations[0]["date"]
verifier("une date reste une date", isinstance(jour, date), True)
verifier("valeur exacte", jour, date(2026, 9, 5))
verifier("l'horodatage d'enregistrement est lu",
         isinstance(relu.enregistre_le, datetime), True)


# ---------------------------------------------------------------------------
print("\n4. Ecriture atomique — l'ancien fichier n'est jamais perdu")
# ---------------------------------------------------------------------------

f3 = BAC / "atomique.json"
enregistrer(Donnees(profil="Particulier", comptes=[{"nom": "V1"}]), f3)
avant = f3.read_text(encoding="utf-8")

# Une donnee non serialisable doit faire echouer l'enregistrement...
class NonSerialisable:
    pass

leve("donnee impossible signalee",
     lambda: enregistrer(Donnees(operations=[{"x": NonSerialisable()}]), f3),
     "impossible à enregistrer")

# ... sans abimer le fichier deja en place.
verifier("l'ancien fichier est intact", f3.read_text(encoding="utf-8"), avant)
verifier("l'ancien contenu est toujours lisible", charger(f3).comptes[0]["nom"], "V1")

# Aucun fichier temporaire ne doit trainer apres un echec.
verifier("aucun residu temporaire", list(BAC.glob("*.tmp")), [])


# ---------------------------------------------------------------------------
print("\n5. Fichier abime — conserve, jamais ecrase")
# ---------------------------------------------------------------------------

f4 = BAC / "abime.json"
f4.write_text('{"version_format": 1, "comptes": [ceci n\'est pas du JSON',
              encoding="utf-8")
leve("fichier illisible signale", lambda: charger(f4), "illisible")

verifier("le fichier abime a ete deplace", f4.exists(), False)
secours = list(BAC.glob("abime_illisible_*.json"))
verifier("une copie de secours existe", len(secours), 1)
verifier("le contenu d'origine est preserve",
         "ceci n'est pas du JSON" in secours[0].read_text(encoding="utf-8"), True)

# Le message doit dire ou est passe le fichier.
try:
    f4.write_text("{cassé", encoding="utf-8")
    charger(f4)
except ErreurSauvegarde as err:
    verifier("le message indique le fichier de secours",
             "illisible" in str(err), True)


# ---------------------------------------------------------------------------
print("\n6. Versions de format")
# ---------------------------------------------------------------------------

f5 = BAC / "futur.json"
f5.write_text(json.dumps({"version_format": 99, "comptes": []}), encoding="utf-8")
leve("format trop recent refuse", lambda: charger(f5), "plus récente")

try:
    charger(f5)
except ErreurSauvegarde as err:
    verifier("le message dit quoi faire", "à jour" in str(err), True)

# Migration depuis l'ancien reglage a solde unique.
f6 = BAC / "ancien.json"
f6.write_text(json.dumps({
    "solde_initial": "2500.00", "devise": "EUR", "profil": "Particulier",
}), encoding="utf-8")
migre = charger(f6)
verifier("l'ancien solde devient un compte", len(migre.comptes), 1)
verifier("le solde est repris", migre.comptes[0]["solde"], "2500.00")
verifier("la devise est reprise", migre.comptes[0]["devise"], "EUR")
verifier("la reference est alignee", migre.devise_reference, "EUR")


# ---------------------------------------------------------------------------
print("\n7. Cas limites")
# ---------------------------------------------------------------------------

f7 = BAC / "vide.json"
enregistrer(Donnees(), f7)
vide = charger(f7)
verifier("donnees vides enregistrables", vide is not None, True)
verifier("aucun compte", vide.comptes, [])
verifier("vide detecte", vide.vide, True)
verifier("resume lisible quand vide", vide.resume(), "aucune donnée")

f8 = BAC / "pas_un_objet.json"
f8.write_text('["une", "liste"]', encoding="utf-8")
leve("fichier de mauvais type refuse", lambda: charger(f8), "format attendu")

# Le dossier doit etre cree s'il n'existe pas.
f9 = BAC / "sous" / "dossier" / "profond.json"
enregistrer(Donnees(profil="Particulier"), f9)
verifier("dossier cree automatiquement", f9.exists(), True)


# ---------------------------------------------------------------------------
print("\n8. Resume affichable")
# ---------------------------------------------------------------------------

d = charger(fichier)
verifier("le resume compte les comptes", "2 comptes" in d.resume(), True)
verifier("le resume compte les operations", "2 opérations" in d.resume(), True)
verifier("le resume donne la date", "enregistrées le" in d.resume(), True)

un_seul = Donnees(comptes=[{"nom": "A"}])
verifier("singulier respecte", "1 compte," in un_seul.resume() or
         un_seul.resume().startswith("1 compte"), True)


# ---------------------------------------------------------------------------
print("\n9. Informations, export et suppression")
# ---------------------------------------------------------------------------

infos = informations(fichier)
verifier("informations disponibles", infos is not None, True)
verifier("taille renseignee", infos["taille_ko"] > 0, True)
verifier("date de modification", isinstance(infos["modifie_le"], datetime), True)
verifier("aucune information si absent", informations(BAC / "neant.json"), None)

copie = BAC / "export" / "copie.json"
exporter_vers(fichier, copie)
verifier("export cree", copie.exists(), True)
verifier("export identique",
         copie.read_text(encoding="utf-8"), fichier.read_text(encoding="utf-8"))
leve("export d'un fichier absent signale",
     lambda: exporter_vers(BAC / "neant.json", copie), "aucune sauvegarde")

verifier("suppression reussie", supprimer(fichier), True)
verifier("le fichier a disparu", fichier.exists(), False)
verifier("supprimer deux fois rend faux", supprimer(fichier), False)


# ---------------------------------------------------------------------------
print("\n10. Emplacement par defaut")
# ---------------------------------------------------------------------------

dossier = dossier_par_defaut()
verifier("le dossier porte le nom de l'application", dossier.name, "Dayzon")
verifier("le chemin par defaut est dans ce dossier",
         chemin_par_defaut().parent, dossier)
verifier("le fichier est nomme lisiblement",
         chemin_par_defaut().name, "dayzon_donnees.json")
# On n'ecrit jamais a cote du programme : ce dossier est souvent en lecture seule.
verifier("l'ecriture n'est pas dans le dossier du code",
         Path(__file__).parent.resolve() in dossier.resolve().parents
         or dossier.resolve() == Path(__file__).parent.resolve(), False)


# ---------------------------------------------------------------------------
shutil.rmtree(BAC, ignore_errors=True)
print("\n" + "=" * 62)
if ko:
    print(f"{ok} verifications reussies, {len(ko)} ECHECS :")
    for n in ko:
        print(f"   - {n}")
    raise SystemExit(1)
print(f"{ok} verifications reussies, aucun echec.")
