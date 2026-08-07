"""
SAUVEGARDE — les données survivent à la fermeture
Dayzon — SMD Global Consulting LLC

Corrige le défaut le plus pénalisant à l'usage : tout disparaissait à la
fermeture de l'application. Personne ne réimporte son relevé à chaque visite.

Trois règles qui guident ce module :

  1. **Ne jamais perdre de données.** L'écriture passe par un fichier
     temporaire remplacé d'un bloc : une coupure en pleine écriture laisse
     l'ancien fichier intact, jamais un fichier à moitié écrit.
  2. **Toujours pouvoir relire l'ancien.** Le fichier porte un numéro de
     version ; une version plus récente que le programme est refusée avec un
     message clair plutôt qu'avec une erreur incompréhensible.
  3. **Rester lisible.** Le format est du JSON indenté, que l'utilisateur
     peut ouvrir, comprendre et corriger lui-même. C'est son argent.

Module autonome : ne dépend ni de Streamlit, ni de pandas.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

VERSION_FORMAT = 1
NOM_FICHIER = "dayzon_donnees.json"


# ---------------------------------------------------------------------------
# Local ou hébergé — la distinction qui protège les données
# ---------------------------------------------------------------------------

def mode_local() -> bool:
    """
    Vrai seulement si l'application tourne sur la machine de l'utilisateur.

    C'EST LA QUESTION LA PLUS IMPORTANTE DE CE MODULE.

    Sur un serveur partagé, « le dossier de l'utilisateur » est celui du
    serveur, commun à tous les visiteurs. Y écrire ferait lire à chacun les
    données financières du précédent. Le fichier de sauvegarde est donc
    strictement réservé à l'exécution locale.

    La détection est volontairement pessimiste : au moindre indice
    d'hébergement, on considère que l'on n'est PAS en local. Se tromper dans
    ce sens fait perdre une commodité ; se tromper dans l'autre expose les
    relevés bancaires de quelqu'un.
    """
    indices_heberges = (
        # Streamlit Community Cloud déploie sous /mount/src
        os.path.isdir("/mount/src"),
        os.environ.get("HOSTNAME", "").startswith("streamlit"),
        # Conteneurs et plateformes courantes
        os.path.exists("/.dockerenv"),
        bool(os.environ.get("DYNO")),           # Heroku
        bool(os.environ.get("RENDER")),         # Render
        bool(os.environ.get("RAILWAY_ENVIRONMENT")),
        bool(os.environ.get("FLY_APP_NAME")),
        bool(os.environ.get("K_SERVICE")),      # Cloud Run
        bool(os.environ.get("WEBSITE_INSTANCE_ID")),   # Azure
        bool(os.environ.get("AWS_EXECUTION_ENV")),
        bool(os.environ.get("CODESPACES")),
        bool(os.environ.get("GITPOD_WORKSPACE_ID")),
        # Une variable explicite permet de forcer le mode hébergé.
        os.environ.get("DAYZON_HEBERGE", "").lower() in ("1", "true", "oui"),
    )
    if any(indices_heberges):
        return False

    # Un poste de travail a un dossier personnel accessible en écriture.
    try:
        maison = Path.home()
        return maison.exists() and os.access(maison, os.W_OK)
    except Exception:
        return False


def raison_mode() -> str:
    """Phrase affichable expliquant où vont les données."""
    if mode_local():
        return ("Vos données sont enregistrées sur cet ordinateur, "
                "dans votre dossier personnel.")
    return ("En ligne, rien n'est enregistré sur le serveur : vos données "
            "restent dans votre navigateur le temps de la visite. "
            "Téléchargez votre fichier pour les conserver.")


class ErreurSauvegarde(Exception):
    """Le message est destiné à l'utilisateur, pas au journal technique."""


# ---------------------------------------------------------------------------
# Emplacement
# ---------------------------------------------------------------------------

def dossier_par_defaut() -> Path:
    """
    Le dossier de données de l'utilisateur, selon son système.

    On n'écrit jamais à côté du programme : sur beaucoup d'installations ce
    dossier est en lecture seule, et les données seraient perdues à la
    moindre mise à jour.
    """
    if os.name == "nt":
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
    elif os.uname().sysname == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "Dayzon"


def chemin_par_defaut() -> Path:
    return dossier_par_defaut() / NOM_FICHIER


# ---------------------------------------------------------------------------
# Conversion JSON
# ---------------------------------------------------------------------------

def _encoder(valeur):
    """
    Decimal et date deviennent du texte, jamais des nombres flottants.

    Écrire un Decimal en float dans le fichier suffirait à réintroduire les
    erreurs de centime que tout le reste du programme s'attache à éviter.
    """
    if isinstance(valeur, Decimal):
        return {"__decimal__": str(valeur)}
    if isinstance(valeur, datetime):
        return {"__datetime__": valeur.isoformat()}
    if isinstance(valeur, date):
        return {"__date__": valeur.isoformat()}
    if hasattr(valeur, "value") and hasattr(valeur, "name"):     # Enum
        return {"__enum__": valeur.value}
    raise TypeError(f"Type non sérialisable : {type(valeur).__name__}")


def _decoder(dictionnaire: dict):
    if "__decimal__" in dictionnaire:
        return Decimal(dictionnaire["__decimal__"])
    if "__date__" in dictionnaire:
        return date.fromisoformat(dictionnaire["__date__"])
    if "__datetime__" in dictionnaire:
        return datetime.fromisoformat(dictionnaire["__datetime__"])
    if "__enum__" in dictionnaire:
        return dictionnaire["__enum__"]
    return dictionnaire


# ---------------------------------------------------------------------------
# Le contenu sauvegardé
# ---------------------------------------------------------------------------

@dataclass
class Donnees:
    """Ce que l'application conserve d'une session à l'autre."""
    profil: str = "Particulier"
    devise_reference: str = "EUR"
    langue: str = "fr"
    comptes: list[dict] = None
    operations: list[dict] = None
    taux: list[dict] = None
    enregistre_le: datetime | None = None

    def __post_init__(self) -> None:
        self.comptes = self.comptes or []
        self.operations = self.operations or []
        self.taux = self.taux or []

    @property
    def vide(self) -> bool:
        return not self.comptes and not self.operations

    def resume(self) -> str:
        morceaux = []
        if self.comptes:
            morceaux.append(f"{len(self.comptes)} compte"
                            f"{'s' if len(self.comptes) > 1 else ''}")
        if self.operations:
            morceaux.append(f"{len(self.operations)} opération"
                            f"{'s' if len(self.operations) > 1 else ''}")
        if not morceaux:
            return "aucune donnée"
        texte = " et ".join(morceaux)
        if self.enregistre_le:
            texte += f", enregistrées le {self.enregistre_le.strftime('%d/%m/%Y à %H:%M')}"
        return texte


# ---------------------------------------------------------------------------
# Écriture et lecture
# ---------------------------------------------------------------------------

def enregistrer(donnees: Donnees, chemin: Path | str | None = None) -> Path:
    """
    Écrit les données de façon atomique.

    Le contenu part dans un fichier temporaire du même dossier, puis remplace
    l'ancien d'un seul mouvement. Une coupure de courant pendant l'écriture
    laisse donc l'ancien fichier intact — jamais un fichier tronqué.
    """
    # Garde-fou : sans chemin explicite, on n'écrit jamais hors du poste
    # de l'utilisateur. Un serveur partagé mélangerait les visiteurs.
    if chemin is None and not mode_local():
        raise ErreurSauvegarde(
            "L'enregistrement automatique est désactivé en ligne : le serveur "
            "est partagé entre tous les visiteurs. Utilisez « Télécharger mes "
            "données » pour conserver votre travail.")

    chemin = Path(chemin or chemin_par_defaut())
    donnees.enregistre_le = datetime.now()

    contenu = {
        "version_format": VERSION_FORMAT,
        "application": "Dayzon",
        "enregistre_le": donnees.enregistre_le.isoformat(),
        "profil": donnees.profil,
        "devise_reference": donnees.devise_reference,
        "langue": donnees.langue,
        "comptes": donnees.comptes,
        "operations": donnees.operations,
        "taux": donnees.taux,
    }

    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        raise ErreurSauvegarde(
            f"Impossible de créer le dossier {chemin.parent} : {err}")

    temporaire = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".tmp",
                dir=chemin.parent, delete=False) as f:
            temporaire = Path(f.name)
            json.dump(contenu, f, default=_encoder, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())        # forcer l'écriture disque avant le remplacement
        os.replace(temporaire, chemin)  # atomique sur Windows comme sur Unix
    except TypeError as err:
        if temporaire and temporaire.exists():
            temporaire.unlink(missing_ok=True)
        raise ErreurSauvegarde(f"Donnée impossible à enregistrer : {err}")
    except OSError as err:
        if temporaire and temporaire.exists():
            temporaire.unlink(missing_ok=True)
        raise ErreurSauvegarde(f"Écriture impossible dans {chemin} : {err}")

    return chemin


def charger(chemin: Path | str | None = None) -> Donnees | None:
    """
    Relit les données. Renvoie None si le fichier n'existe pas — ce n'est
    pas une erreur, c'est le cas d'une première utilisation.

    Un fichier illisible est mis de côté plutôt qu'écrasé : les données de
    l'utilisateur ne nous appartiennent pas.
    """
    # Même garde-fou en lecture : sur un serveur, ce fichier appartiendrait
    # à un autre visiteur.
    if chemin is None and not mode_local():
        return None

    chemin = Path(chemin or chemin_par_defaut())
    if not chemin.exists():
        return None

    try:
        brut = json.loads(chemin.read_text(encoding="utf-8"),
                          object_hook=_decoder)
    except json.JSONDecodeError as err:
        secours = _mettre_de_cote(chemin)
        raise ErreurSauvegarde(
            f"Le fichier de sauvegarde est illisible (ligne {err.lineno}). "
            f"Il a été conservé sous « {secours.name} » et l'application "
            f"repart d'une base vide.")
    except OSError as err:
        raise ErreurSauvegarde(f"Lecture impossible de {chemin} : {err}")

    if not isinstance(brut, dict):
        raise ErreurSauvegarde("Le fichier de sauvegarde n'a pas le format attendu.")

    version = brut.get("version_format", 0)
    if version > VERSION_FORMAT:
        raise ErreurSauvegarde(
            f"Ce fichier a été créé par une version plus récente de Dayzon "
            f"(format {version}, cette version lit jusqu'au format "
            f"{VERSION_FORMAT}). Mettez l'application à jour pour l'ouvrir.")

    brut = _migrer(brut, version)

    enregistre = brut.get("enregistre_le")
    if isinstance(enregistre, str):
        try:
            enregistre = datetime.fromisoformat(enregistre)
        except ValueError:
            enregistre = None

    return Donnees(
        profil=brut.get("profil", "Particulier"),
        devise_reference=brut.get("devise_reference", "EUR"),
        langue=brut.get("langue", "fr"),
        comptes=brut.get("comptes") or [],
        operations=brut.get("operations") or [],
        taux=brut.get("taux") or [],
        enregistre_le=enregistre if isinstance(enregistre, datetime) else None,
    )


def _migrer(brut: dict, version: int) -> dict:
    """
    Met à jour un fichier ancien vers le format courant.

    Version 0 : l'application ne connaissait qu'un solde unique. On le
    transforme en un compte, pour que personne ne perde son paramétrage.
    """
    if version < 1:
        if "comptes" not in brut and "solde_initial" in brut:
            devise = brut.get("devise", "EUR")
            brut["comptes"] = [{
                "nom": "Compte principal",
                "devise": devise,
                "solde": str(brut["solde_initial"]),
                "identifiant": "principal",
                "actif": True,
            }]
            brut["devise_reference"] = devise
    return brut


def _mettre_de_cote(chemin: Path) -> Path:
    """Renomme un fichier abîmé au lieu de le détruire."""
    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    secours = chemin.with_name(f"{chemin.stem}_illisible_{horodatage}{chemin.suffix}")
    try:
        shutil.move(str(chemin), str(secours))
    except OSError:
        pass
    return secours


def supprimer(chemin: Path | str | None = None) -> bool:
    """Efface la sauvegarde. Action irréversible : à confirmer côté interface."""
    chemin = Path(chemin or chemin_par_defaut())
    if not chemin.exists():
        return False
    try:
        chemin.unlink()
        return True
    except OSError as err:
        raise ErreurSauvegarde(f"Suppression impossible : {err}")


def informations(chemin: Path | str | None = None) -> dict | None:
    """Taille et date du fichier, pour l'afficher dans les réglages."""
    # Même garde-fou en lecture : sur un serveur, ce fichier appartiendrait
    # à un autre visiteur.
    if chemin is None and not mode_local():
        return None

    chemin = Path(chemin or chemin_par_defaut())
    if not chemin.exists():
        return None
    stat = chemin.stat()
    return {
        "chemin": str(chemin),
        "taille_ko": round(stat.st_size / 1024, 1),
        "modifie_le": datetime.fromtimestamp(stat.st_mtime),
    }


def exporter_vers(source: Path | str | None, destination: Path | str) -> Path:
    """
    Copie la sauvegarde ailleurs — clé USB, dossier synchronisé, archive.

    L'utilisateur doit pouvoir emporter ses données sans dépendre de nous.
    """
    source = Path(source or chemin_par_defaut())
    destination = Path(destination)
    if not source.exists():
        raise ErreurSauvegarde("Aucune sauvegarde à exporter.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


# ---------------------------------------------------------------------------
# Emporter ses données — indispensable en ligne
# ---------------------------------------------------------------------------

def vers_octets(donnees: Donnees) -> bytes:
    """
    Produit le fichier de sauvegarde en mémoire, sans rien écrire sur disque.

    C'est ce qui permet à un visiteur d'emporter ses données depuis une
    application hébergée : le fichier passe du navigateur à son appareil,
    sans jamais séjourner sur le serveur.
    """
    donnees.enregistre_le = datetime.now()
    contenu = {
        "version_format": VERSION_FORMAT,
        "application": "Dayzon",
        "enregistre_le": donnees.enregistre_le.isoformat(),
        "profil": donnees.profil,
        "devise_reference": donnees.devise_reference,
        "langue": donnees.langue,
        "comptes": donnees.comptes,
        "operations": donnees.operations,
        "taux": donnees.taux,
    }
    try:
        texte = json.dumps(contenu, default=_encoder, ensure_ascii=False, indent=2)
    except TypeError as err:
        raise ErreurSauvegarde(f"Donnée impossible à enregistrer : {err}")
    return texte.encode("utf-8")


def depuis_octets(donnees_brutes: bytes) -> Donnees:
    """
    Relit un fichier déposé par l'utilisateur.

    Les mêmes contrôles qu'à la lecture disque s'appliquent : un fichier
    illisible ou trop récent est refusé avec un message clair, jamais
    silencieusement ignoré.
    """
    try:
        texte = donnees_brutes.decode("utf-8")
    except UnicodeDecodeError:
        raise ErreurSauvegarde(
            "Ce fichier n'est pas un fichier Dayzon : son encodage est illisible.")

    try:
        brut = json.loads(texte, object_hook=_decoder)
    except json.JSONDecodeError as err:
        raise ErreurSauvegarde(
            f"Ce fichier n'est pas un fichier Dayzon valide (ligne {err.lineno}).")

    if not isinstance(brut, dict):
        raise ErreurSauvegarde("Ce fichier n'a pas le format attendu.")

    version = brut.get("version_format", 0)
    if version > VERSION_FORMAT:
        raise ErreurSauvegarde(
            f"Ce fichier a été créé par une version plus récente de Dayzon "
            f"(format {version}). Mettez l'application à jour pour l'ouvrir.")

    brut = _migrer(brut, version)

    enregistre = brut.get("enregistre_le")
    if isinstance(enregistre, str):
        try:
            enregistre = datetime.fromisoformat(enregistre)
        except ValueError:
            enregistre = None

    return Donnees(
        profil=brut.get("profil", "Particulier"),
        devise_reference=brut.get("devise_reference", "EUR"),
        langue=brut.get("langue", "fr"),
        comptes=brut.get("comptes") or [],
        operations=brut.get("operations") or [],
        taux=brut.get("taux") or [],
        enregistre_le=enregistre if isinstance(enregistre, datetime) else None,
    )


def nom_fichier_export() -> str:
    """Nom daté, pour que l'utilisateur retrouve ses sauvegardes successives."""
    return f"dayzon_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
