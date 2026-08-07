"""
COMPTE UTILISATEUR — inscription, connexion, données en base
Dayzon — SMD Global Consulting LLC

Corrige la limite majeure de l'application en ligne : sans compte, chaque
visiteur repartait de zéro et devait redéposer son fichier à chaque visite.

Ce que ce module fait, et ce qu'il ne fait pas
----------------------------------------------
Il ne vérifie aucun mot de passe et n'en stocke aucun. Tout passe par
Supabase, qui gère le chiffrement, la confirmation d'adresse et la
réinitialisation. Dayzon ne voit jamais qu'un jeton de session.

L'isolation entre utilisateurs n'est pas assurée ici. Elle est appliquée
par PostgreSQL lui-même, via des politiques de sécurité au niveau des
lignes. Un défaut dans ce fichier ne peut donc pas exposer les données
financières de quelqu'un d'autre — c'est délibéré, et c'est vérifié.

Configuration attendue dans `.streamlit/secrets.toml` :

    [supabase]
    url          = "https://xxxx.supabase.co"
    cle_publique = "eyJ..."

La clé publique est faite pour être dans une application. La clé
`service_role`, elle, contourne toute l'isolation : elle n'a rien à faire
ici et ne doit jamais être placée dans ce fichier.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import streamlit as st


class ErreurCompte(Exception):
    """Message destiné à l'utilisateur, jamais une trace technique."""


# ---------------------------------------------------------------------------
# Connexion au service
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Configuration:
    url: str = ""
    cle_publique: str = ""

    @property
    def active(self) -> bool:
        return bool(self.url and self.cle_publique)


def configuration() -> Configuration:
    """
    Lit la configuration. Son absence n'est pas une erreur : l'application
    doit rester utilisable sans compte, en local comme en démonstration.
    """
    try:
        secrets = st.secrets.get("supabase", {})
    except Exception:
        return Configuration()
    return Configuration(url=str(secrets.get("url", "")),
                         cle_publique=str(secrets.get("cle_publique", "")))


@st.cache_resource(show_spinner=False)
def _client(url: str, cle: str):
    """Un seul client par session, réutilisé d'un affichage à l'autre."""
    from supabase import create_client
    return create_client(url, cle)


def client():
    config = configuration()
    if not config.active:
        raise ErreurCompte(
            "Les comptes ne sont pas configurés sur cette installation.")
    try:
        return _client(config.url, config.cle_publique)
    except ImportError:
        raise ErreurCompte(
            "La bibliothèque Supabase n'est pas installée. "
            "Lancez : py -m pip install supabase")
    except Exception as err:
        raise ErreurCompte(f"Connexion au service impossible : {err}")


def comptes_disponibles() -> bool:
    return configuration().active


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

@dataclass
class Session:
    identifiant: str
    email: str
    espace_id: str = ""
    jeton: str = ""


def session() -> Session | None:
    return st.session_state.get("session_utilisateur")


def connecte() -> bool:
    return session() is not None


def _messages_lisibles(erreur: Exception) -> str:
    """
    Traduit les messages du service en français compréhensible.

    Un utilisateur qui s'est trompé de mot de passe n'a pas à lire
    « Invalid login credentials » dans une application française.
    """
    texte = str(erreur).lower()
    traductions = [
        ("invalid login credentials",
         "Adresse ou mot de passe incorrect."),
        ("email not confirmed",
         "Votre adresse n'est pas encore confirmée. "
         "Ouvrez le message que nous vous avons envoyé."),
        ("user already registered",
         "Un compte existe déjà avec cette adresse. Connectez-vous."),
        ("password should be at least",
         "Le mot de passe doit contenir au moins 6 caractères."),
        ("unable to validate email",
         "Cette adresse e-mail n'est pas valide."),
        ("for security purposes",
         "Trop de tentatives. Patientez une minute avant de réessayer."),
        ("email rate limit",
         "Trop de messages envoyés à cette adresse. Réessayez plus tard."),
    ]
    for motif, message in traductions:
        if motif in texte:
            return message
    return "L'opération a échoué. Vérifiez votre connexion et réessayez."


def inscrire(email: str, mot_de_passe: str) -> str:
    """
    Crée un compte. Renvoie un message à afficher.

    Le mot de passe ne fait que traverser : il part chiffré vers Supabase
    et n'est ni conservé, ni journalisé, ni comparé ici.
    """
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ErreurCompte("Indiquez une adresse e-mail valide.")
    if len(mot_de_passe or "") < 8:
        raise ErreurCompte(
            "Choisissez un mot de passe d'au moins 8 caractères. "
            "Il protège vos données financières.")

    try:
        reponse = client().auth.sign_up(
            {"email": email, "password": mot_de_passe})
    except ErreurCompte:
        raise                       # message déjà clair : ne pas le noyer
    except Exception as err:
        raise ErreurCompte(_messages_lisibles(err))

    if reponse.session is not None:
        _ouvrir(reponse)
        return "Compte créé. Bienvenue."
    return ("Compte créé. Ouvrez le message envoyé à "
            f"{email} pour confirmer votre adresse, puis connectez-vous.")


def connecter(email: str, mot_de_passe: str) -> None:
    email = (email or "").strip().lower()
    if not email or not mot_de_passe:
        raise ErreurCompte("Indiquez votre adresse et votre mot de passe.")
    try:
        reponse = client().auth.sign_in_with_password(
            {"email": email, "password": mot_de_passe})
    except ErreurCompte:
        raise
    except Exception as err:
        raise ErreurCompte(_messages_lisibles(err))

    if reponse.session is None:
        raise ErreurCompte("Adresse ou mot de passe incorrect.")
    _ouvrir(reponse)


def _ouvrir(reponse) -> None:
    """Enregistre la session et retrouve l'espace de travail."""
    utilisateur = reponse.user
    st.session_state.session_utilisateur = Session(
        identifiant=utilisateur.id,
        email=utilisateur.email or "",
        jeton=reponse.session.access_token,
    )
    st.session_state.session_utilisateur.espace_id = _espace_courant()


def deconnecter() -> None:
    """
    Ferme la session et efface les données affichées.

    Le second point est le plus important : laisser les comptes d'une
    personne à l'écran après sa déconnexion, sur un ordinateur partagé,
    serait une faute.
    """
    try:
        client().auth.sign_out()
    except Exception:
        pass

    for cle in ("session_utilisateur", "operations", "portefeuille", "taux",
                "mouvements", "analyse", "lecture_fc", "lecture_ff",
                "scenarios_perso", "_initialise"):
        st.session_state.pop(cle, None)


def reinitialiser_mot_de_passe(email: str) -> str:
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ErreurCompte("Indiquez l'adresse de votre compte.")
    try:
        client().auth.reset_password_for_email(email)
    except ErreurCompte:
        raise
    except Exception as err:
        raise ErreurCompte(_messages_lisibles(err))
    # On répond la même chose que l'adresse existe ou non : révéler
    # quelles adresses sont inscrites renseignerait un attaquant.
    return (f"Si un compte existe pour {email}, un message vient d'être "
            f"envoyé avec la marche à suivre.")


# ---------------------------------------------------------------------------
# Espace de travail
# ---------------------------------------------------------------------------

def _espace_courant() -> str:
    """
    L'espace de l'utilisateur. Un déclencheur en base en crée un à
    l'inscription ; on le crée ici seulement si quelque chose a échoué.
    """
    try:
        reponse = client().table("espaces").select("id").limit(1).execute()
        if reponse.data:
            return reponse.data[0]["id"]
        creation = client().table("espaces").insert({
            "nom": "Mon espace", "profil": "Particulier",
            "devise_reference": "EUR"}).execute()
        return creation.data[0]["id"] if creation.data else ""
    except Exception:
        return ""


def espace_id() -> str:
    s = session()
    return s.espace_id if s else ""


# ---------------------------------------------------------------------------
# Lecture et écriture des données
# ---------------------------------------------------------------------------
# Les montants voyagent en texte. L'API sérialise un nombre décimal en
# virgule flottante ; sur une application dont la règle est « jamais de
# float », cela réintroduirait l'erreur qu'on écarte partout ailleurs.

def charger_espace() -> dict:
    """Ramène tout ce qui appartient à l'utilisateur connecté."""
    if not connecte():
        raise ErreurCompte("Vous n'êtes pas connecté.")
    identifiant = espace_id()
    if not identifiant:
        raise ErreurCompte("Aucun espace de travail n'a été trouvé.")

    c = client()
    try:
        espace = c.table("espaces").select("*").eq("id", identifiant).single().execute()
        comptes = c.table("comptes").select("*").eq("espace_id", identifiant)\
                   .order("cree_le").execute()
        operations = c.table("operations").select("*").eq("espace_id", identifiant)\
                      .order("date_operation").execute()
        taux = c.table("taux").select("*").eq("espace_id", identifiant).execute()
    except ErreurCompte:
        raise
    except Exception as err:
        raise ErreurCompte(f"Lecture impossible : {err}")

    return {
        "profil": espace.data.get("profil", "Particulier"),
        "devise_reference": espace.data.get("devise_reference", "EUR"),
        "comptes": [{
            "nom": c_["nom"], "devise": c_["devise"], "solde": c_["solde"],
            "etablissement": c_.get("etablissement", ""),
            "pays": c_.get("pays", ""), "actif": c_.get("actif", True),
            "note": c_.get("note", ""), "identifiant": c_["id"][:8],
        } for c_ in (comptes.data or [])],
        "operations": [{
            "libelle": o["libelle"],
            "montant": Decimal(o["montant"]),
            "date": date.fromisoformat(o["date_operation"]),
            "devise": o["devise"],
            "recurrence": o.get("recurrence", "ponctuelle"),
            "date_fin": (date.fromisoformat(o["date_fin"])
                         if o.get("date_fin") else None),
            "categorie": o.get("categorie", ""),
            "certaine": o.get("certaine", True),
        } for o in (operations.data or [])],
        "taux": [{
            "base": t["base"], "contre": t["contre"], "valeur": t["valeur"],
            "observe_le": t["observe_le"], "source": t["source"],
        } for t in (taux.data or [])],
    }


def enregistrer_espace(profil: str, devise_reference: str,
                       comptes: list[dict], operations: list[dict],
                       taux: list[dict]) -> None:
    """
    Écrit l'état complet de l'espace.

    On remplace plutôt qu'on ne fusionne : c'est plus simple à raisonner et
    sans ambiguïté sur ce qui a été supprimé. Le volume reste modeste —
    quelques dizaines de lignes — et l'écriture est déclenchée par une
    action de l'utilisateur, pas en continu.
    """
    if not connecte():
        raise ErreurCompte("Vous n'êtes pas connecté.")
    identifiant = espace_id()
    if not identifiant:
        raise ErreurCompte("Aucun espace de travail n'a été trouvé.")

    c = client()
    try:
        c.table("espaces").update({
            "profil": profil,
            "devise_reference": devise_reference,
        }).eq("id", identifiant).execute()

        for table in ("comptes", "operations", "taux"):
            c.table(table).delete().eq("espace_id", identifiant).execute()

        if comptes:
            c.table("comptes").insert([{
                "espace_id": identifiant,
                "nom": x["nom"], "devise": x["devise"],
                "solde": str(x["solde"]),
                "etablissement": x.get("etablissement", ""),
                "pays": x.get("pays", ""),
                "actif": bool(x.get("actif", True)),
                "note": x.get("note", ""),
            } for x in comptes]).execute()

        if operations:
            c.table("operations").insert([{
                "espace_id": identifiant,
                "libelle": x["libelle"],
                "montant": str(x["montant"]),
                "devise": x.get("devise", devise_reference),
                "date_operation": _en_texte(x["date"]),
                "recurrence": _valeur(x.get("recurrence", "ponctuelle")),
                "date_fin": _en_texte(x.get("date_fin")),
                "categorie": x.get("categorie", ""),
                "certaine": bool(x.get("certaine", True)),
            } for x in operations]).execute()

        if taux:
            c.table("taux").insert([{
                "espace_id": identifiant,
                "base": t["base"], "contre": t["contre"],
                "valeur": str(t["valeur"]),
                "observe_le": _en_texte(t["observe_le"]),
                "source": t.get("source", "saisie manuelle"),
            } for t in taux]).execute()

    except ErreurCompte:
        raise
    except Exception as err:
        raise ErreurCompte(f"Enregistrement impossible : {err}")


def _en_texte(valeur) -> str | None:
    if valeur is None:
        return None
    return valeur.isoformat() if hasattr(valeur, "isoformat") else str(valeur)


def _valeur(recurrence) -> str:
    return getattr(recurrence, "value", str(recurrence))


def supprimer_mon_compte() -> None:
    """
    Efface les données de l'utilisateur.

    Le compte lui-même relève du service d'identité et demande un droit
    que l'application n'a pas — volontairement. On vide donc l'espace,
    et l'utilisateur est renvoyé vers le support pour la suppression
    définitive de son identifiant.
    """
    if not connecte():
        raise ErreurCompte("Vous n'êtes pas connecté.")
    identifiant = espace_id()
    c = client()
    try:
        for table in ("comptes", "operations", "taux"):
            c.table(table).delete().eq("espace_id", identifiant).execute()
    except ErreurCompte:
        raise
    except Exception as err:
        raise ErreurCompte(f"Suppression impossible : {err}")
