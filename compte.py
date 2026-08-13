"""
COMPTE UTILISATEUR — inscription, connexion, données en base
PrevuFlow — SMD Global Consulting LLC

Corrige la limite majeure de l'application en ligne : sans compte, chaque
visiteur repartait de zéro et devait redéposer son fichier à chaque visite.

Ce que ce module fait, et ce qu'il ne fait pas
----------------------------------------------
Il ne vérifie aucun mot de passe et n'en stocke aucun. Tout passe par
Supabase, qui gère le chiffrement, la confirmation d'adresse et la
réinitialisation. PrevuFlow ne voit jamais qu'un jeton de session.

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
from datetime import date, datetime
from decimal import Decimal

import streamlit as st

import langues as lg


def _t(cle: str, **variables) -> str:
    """
    Traduit un message pour l'utilisateur.

    Ce module ne peut pas importer `commun` : `commun` l'importe deja pour
    enregistrer en base, et l'import croise casserait le demarrage. On lit
    donc la langue directement dans la session, et `langues` reste pur.
    """
    try:
        code = st.session_state.get("langue", lg.LANGUE_PAR_DEFAUT)
    except Exception:
        code = lg.LANGUE_PAR_DEFAUT
    return lg.traduire(cle, code, **variables)


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
            _t("err.non_configure"))
    try:
        return _client(config.url, config.cle_publique)
    except ImportError:
        raise ErreurCompte(
            _t("err.bibliotheque"))
    except Exception as err:
        raise ErreurCompte(_t("err.service", erreur=err))


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
    inscrit_le: date | None = None      # début de la période d'essai


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
    correspondances = [
        ("invalid login credentials",  "err.identifiants"),
        ("email not confirmed",        "err.non_confirme"),
        ("user already registered",    "err.deja_inscrit"),
        ("password should be at least", "err.mot_court"),
        ("unable to validate email",   "err.email_invalide"),
        ("for security purposes",      "err.trop_tentatives"),
        ("email rate limit",           "err.trop_messages"),
        ("token has expired",          "err.code_invalide"),
        ("invalid token",              "err.code_invalide"),
        ("otp_expired",                "err.code_invalide"),
    ]
    for motif, cle in correspondances:
        if motif in texte:
            return _t(cle)
    return _t("err.echec")


def inscrire(email: str, mot_de_passe: str) -> str:
    """
    Crée un compte. Renvoie un message à afficher.

    Le mot de passe ne fait que traverser : il part chiffré vers Supabase
    et n'est ni conservé, ni journalisé, ni comparé ici.
    """
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ErreurCompte(_t("err.email_requis"))
    if len(mot_de_passe or "") < 8:
        raise ErreurCompte(_t("err.mot_8"))

    try:
        reponse = client().auth.sign_up(
            {"email": email, "password": mot_de_passe})
    except ErreurCompte:
        raise                       # message déjà clair : ne pas le noyer
    except Exception as err:
        raise ErreurCompte(_messages_lisibles(err))

    if reponse.session is not None:
        _ouvrir(reponse)
        return _t("cpt.cree_bienvenue")
    return _t("cpt.cree_confirmer", email=email)


def connecter(email: str, mot_de_passe: str) -> None:
    email = (email or "").strip().lower()
    if not email or not mot_de_passe:
        raise ErreurCompte(_t("err.identifiants_requis"))
    try:
        reponse = client().auth.sign_in_with_password(
            {"email": email, "password": mot_de_passe})
    except ErreurCompte:
        raise
    except Exception as err:
        raise ErreurCompte(_messages_lisibles(err))

    if reponse.session is None:
        raise ErreurCompte(_t("err.identifiants"))
    _ouvrir(reponse)


def _ouvrir(reponse) -> None:
    """Enregistre la session et retrouve l'espace de travail."""
    utilisateur = reponse.user
    st.session_state.session_utilisateur = Session(
        identifiant=utilisateur.id,
        email=utilisateur.email or "",
        jeton=reponse.session.access_token,
        inscrit_le=_date_inscription(utilisateur),
    )
    st.session_state.session_utilisateur.espace_id = _espace_courant()


def _date_inscription(utilisateur) -> date | None:
    """
    Le jour où le compte a été créé — le point de départ de l'essai.

    Supabase le donne dans `created_at`, tantôt en `datetime`, tantôt en
    texte ISO selon la version de la bibliothèque. Si la lecture échoue,
    on rend `None` : l'essai sera alors traité comme non commencé plutôt
    que comme expiré. Une erreur de notre côté ne doit jamais fermer
    l'accès à quelqu'un.
    """
    brut = getattr(utilisateur, "created_at", None)
    if brut is None:
        return None
    if isinstance(brut, datetime):
        return brut.date()
    try:
        return datetime.fromisoformat(str(brut).replace("Z", "+00:00")).date()
    except ValueError:
        return None


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
    """
    Envoie le message de récupération.

    Le message contient un code à six chiffres, et non seulement un lien.
    Un lien de récupération renvoie le jeton dans le fragment de l'URL
    (« #access_token=… »), que Streamlit ne peut pas lire : le fragment ne
    quitte jamais le navigateur. Le code, lui, se saisit dans l'écran
    suivant — cela fonctionne partout, y compris quand l'utilisateur ouvre
    son courrier sur son téléphone et l'application sur son ordinateur.
    """
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ErreurCompte(_t("err.adresse_compte"))
    try:
        client().auth.reset_password_for_email(email)
    except ErreurCompte:
        raise
    except Exception as err:
        raise ErreurCompte(_messages_lisibles(err))
    # On répond la même chose que l'adresse existe ou non : révéler
    # quelles adresses sont inscrites renseignerait un attaquant.
    return _t("cpt.envoye", email=email)


def verifier_code(email: str, code: str) -> None:
    """
    Vérifie le code reçu par courrier et ouvre la session.

    Le code n'autorise qu'une chose : choisir un nouveau mot de passe. Il
    expire, et il ne sert qu'une fois — c'est Supabase qui l'impose, non
    ce module.
    """
    email = (email or "").strip().lower()
    code = (code or "").strip().replace(" ", "")
    if not email or "@" not in email:
        raise ErreurCompte(_t("err.adresse_compte"))
    if not code:
        raise ErreurCompte(_t("err.code_requis"))

    try:
        reponse = client().auth.verify_otp(
            {"email": email, "token": code, "type": "recovery"})
    except ErreurCompte:
        raise
    except Exception as err:
        raise ErreurCompte(_messages_lisibles(err))

    if reponse.session is None:
        raise ErreurCompte(_t("err.code_invalide"))
    _ouvrir(reponse)


def changer_mot_de_passe(nouveau: str) -> str:
    """
    Remplace le mot de passe de l'utilisateur connecté.

    Exige une session ouverte : sans elle, n'importe qui pourrait changer
    le mot de passe de n'importe qui. La session vient soit d'une
    connexion normale, soit d'un code de récupération vérifié.
    """
    if not connecte():
        raise ErreurCompte(_t("err.non_connecte"))
    if len(nouveau or "") < 8:
        raise ErreurCompte(_t("err.mot_8"))

    try:
        client().auth.update_user({"password": nouveau})
    except ErreurCompte:
        raise
    except Exception as err:
        raise ErreurCompte(_messages_lisibles(err))
    return _t("cpt.mot_modifie")


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

def lire_abonnement_en_base():
    """
    L'abonnement inscrit par le webhook Stripe, ou `None`.

    Rend `None` — et jamais une exception — quand la table n'existe pas,
    quand personne n'est connecté, ou quand la base est injoignable. Un
    incident de lecture ne doit pas fermer l'accès à quelqu'un qui a payé :
    l'appelant retombera sur Stripe, puis sur la formule gratuite.
    """
    if not connecte():
        return None
    from abonnement import Abonnement, Periode, Plan

    try:
        reponse = client().table("abonnements").select("*") \
            .eq("email", session().email.lower()).limit(1).execute()
    except Exception:
        return None

    lignes = reponse.data or []
    if not lignes:
        return None
    ligne = lignes[0]

    valeurs = {p.value for p in Plan}
    plan = Plan(ligne["plan"]) if ligne.get("plan") in valeurs else Plan.DECOUVERTE
    periodes = {p.value for p in Periode}
    periode = (Periode(ligne["periode"]) if ligne.get("periode") in periodes
               else Periode.MENSUELLE)

    fin = None
    if ligne.get("fin"):
        try:
            fin = date.fromisoformat(str(ligne["fin"])[:10])
        except ValueError:
            fin = None

    return Abonnement(
        plan=plan,
        periode=periode,
        fin=fin,
        identifiant_client=ligne.get("client_stripe") or "",
        identifiant_abonnement=ligne.get("abonnement_stripe") or "",
        annule=bool(ligne.get("annule")))


def charger_espace() -> dict:
    """Ramène tout ce qui appartient à l'utilisateur connecté."""
    if not connecte():
        raise ErreurCompte(_t("err.non_connecte"))
    identifiant = espace_id()
    if not identifiant:
        raise ErreurCompte(_t("err.aucun_espace"))

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
        raise ErreurCompte(_t("err.lecture", erreur=err))

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
        raise ErreurCompte(_t("err.non_connecte"))
    identifiant = espace_id()
    if not identifiant:
        raise ErreurCompte(_t("err.aucun_espace"))

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
        raise ErreurCompte(_t("err.non_connecte"))
    identifiant = espace_id()
    c = client()
    try:
        for table in ("comptes", "operations", "taux"):
            c.table(table).delete().eq("espace_id", identifiant).execute()
    except ErreurCompte:
        raise
    except Exception as err:
        raise ErreurCompte(f"Suppression impossible : {err}")
