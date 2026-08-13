"""
ABONNEMENTS
PrevuFlow — SMD Global Consulting LLC

Trois responsabilités, et rien d'autre :
  1. dire ce que chaque plan débloque ;
  2. ouvrir une page de paiement Stripe ;
  3. répondre à la question « cet utilisateur a-t-il le droit ? ».

Ce module ne connaît pas l'interface et n'affiche rien. Il est testable seul,
sans Streamlit et sans réseau.

CONFIGURATION
-------------
Les clés se placent dans `.streamlit/secrets.toml`, jamais dans le code :

    [stripe]
    cle_secrete   = "sk_test_..."
    prix_particulier_mensuel = "price_..."
    prix_particulier_annuel  = "price_..."
    prix_entreprise_mensuel  = "price_..."
    prix_entreprise_annuel   = "price_..."

Tant que rien n'est configuré, l'application fonctionne en mode libre :
toutes les fonctions sont ouvertes. C'est voulu — le produit doit rester
utilisable en local pendant le développement et les démonstrations.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta          # noqa: F401
from enum import Enum


def _sans_traduction(cle: str, **variables) -> str:
    """
    Repli quand l'appelant n'a pas passé de fonction de traduction.

    On ne rend pas la clé brute : un test ou un script appelé sans contexte
    doit tout de même lire une phrase. Le français sert de langue de repli,
    comme partout ailleurs dans l'application.
    """
    import langues
    return langues.traduire(cle, langues.LANGUE_PAR_DEFAUT, **variables)


class Plan(str, Enum):
    LIBRE = "libre"                 # aucun paiement configuré, ou démonstration
    ESSAI = "essai"                 # 14 jours, tout ouvert, à partir de l'inscription
    DECOUVERTE = "decouverte"       # gratuit, limité, sans terme
    PARTICULIER = "particulier"
    ENTREPRISE = "entreprise"


# Durée de l'essai, en jours. Quatorze : assez pour importer un relevé et
# voir passer une échéance mensuelle, assez court pour qu'une décision se
# prenne. Sept ne laisse pas voir un cycle ; trente laisse l'essai s'endormir.
DUREE_ESSAI = 14


class Periode(str, Enum):
    MENSUELLE = "mensuelle"
    ANNUELLE = "annuelle"


# ---------------------------------------------------------------------------
# Ce que chaque plan permet
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Offre:
    """
    Un plan et ses limites.

    Les limites sont volontairement peu nombreuses. Une grille compliquée se
    retourne contre celui qui la vend : l'acheteur hésite, puis renonce.

    Les textes ne sont pas écrits ici mais désignés par une clé : `cle_nom`,
    `cle_resume`, `cles_arguments`. PrevuFlow se vend dans quatre langues ; une
    grille tarifaire rédigée en français dans le code serait restée française
    partout. La traduction se fait à l'affichage, par la vue.
    """
    plan: Plan
    cle_nom: str
    cle_resume: str
    prix_mensuel: int = 0           # en cents, monnaie de facturation
    prix_annuel: int = 0
    devise: str = "usd"

    jours_projection: int = 90      # horizon maximal du calendrier
    nb_fichiers: int = 1            # relevés et fichiers de factures cumulés
    scenarios: bool = False
    exports: bool = False
    profil_entreprise: bool = False
    cles_arguments: tuple[str, ...] = ()

    @property
    def gratuit(self) -> bool:
        return self.prix_mensuel == 0

    def prix(self, periode: Periode) -> int:
        return (self.prix_annuel if periode is Periode.ANNUELLE
                else self.prix_mensuel)

    def nom(self, t) -> str:
        return t(self.cle_nom)

    def resume(self, t) -> str:
        return t(self.cle_resume)

    def arguments(self, t) -> tuple[str, ...]:
        return tuple(t(c) for c in self.cles_arguments)

    @property
    def economie_annuelle(self) -> int:
        """Pourcentage gagné en payant à l'année plutôt qu'au mois."""
        if self.prix_mensuel == 0 or self.prix_annuel == 0:
            return 0
        plein = self.prix_mensuel * 12
        return round((plein - self.prix_annuel) / plein * 100)


OFFRES: dict[Plan, Offre] = {

    Plan.DECOUVERTE: Offre(
        plan=Plan.DECOUVERTE,
        cle_nom="plan.decouverte.nom",
        cle_resume="plan.decouverte.resume",
        jours_projection=90,
        nb_fichiers=1,
        scenarios=False,
        exports=False,
        profil_entreprise=False,
        cles_arguments=("plan.decouverte.arg1", "plan.decouverte.arg2",
                        "plan.decouverte.arg3")),

    Plan.PARTICULIER: Offre(
        plan=Plan.PARTICULIER,
        cle_nom="plan.particulier.nom",
        cle_resume="plan.particulier.resume",
        prix_mensuel=700,          # 7 $
        prix_annuel=5900,          # 59 $  — 30 % de moins que 12 × 7 $
        jours_projection=365,
        nb_fichiers=99,
        scenarios=True,
        exports=True,
        profil_entreprise=False,
        cles_arguments=("plan.particulier.arg1", "plan.particulier.arg2",
                        "plan.particulier.arg3", "plan.particulier.arg4",
                        "plan.particulier.arg5")),

    Plan.ENTREPRISE: Offre(
        plan=Plan.ENTREPRISE,
        cle_nom="plan.entreprise.nom",
        cle_resume="plan.entreprise.resume",
        prix_mensuel=2900,         # 29 $
        prix_annuel=24900,         # 249 $ — 28 % de moins que 12 × 29 $
        jours_projection=730,
        nb_fichiers=999,
        scenarios=True,
        exports=True,
        profil_entreprise=True,
        cles_arguments=("plan.entreprise.arg1", "plan.entreprise.arg2",
                        "plan.entreprise.arg3", "plan.entreprise.arg4",
                        "plan.entreprise.arg5", "plan.entreprise.arg6")),

    # L'essai ouvre tout, y compris le profil Entreprise. Bridé, il ne
    # vendrait que la formule à 7 $ : personne ne paie 29 $ pour des
    # indicateurs qu'il n'a jamais vus fonctionner sur ses propres chiffres.
    Plan.ESSAI: Offre(
        plan=Plan.ESSAI,
        cle_nom="plan.essai.nom",
        cle_resume="plan.essai.resume",
        jours_projection=730,
        nb_fichiers=999,
        scenarios=True,
        exports=True,
        profil_entreprise=True,
        cles_arguments=("plan.essai.arg1", "plan.essai.arg2",
                        "plan.essai.arg3")),

    # Plan interne : aucun paiement configuré, ou démonstration commerciale.
    Plan.LIBRE: Offre(
        plan=Plan.LIBRE,
        cle_nom="plan.libre.nom",
        cle_resume="plan.libre.resume",
        jours_projection=730,
        nb_fichiers=999,
        scenarios=True,
        exports=True,
        profil_entreprise=True),
}

OFFRES_VENDUES = [OFFRES[Plan.DECOUVERTE], OFFRES[Plan.PARTICULIER],
                  OFFRES[Plan.ENTREPRISE]]


def essai(inscrit_le: date | None) -> "Abonnement":
    """
    L'abonnement d'essai d'un compte, d'après sa date de création.

    Le compteur part de l'inscription, seul point de départ mesurable :
    un visiteur sans compte effacerait son navigateur et repartirait à
    zéro. Sans date connue, on n'invente pas d'échéance et on rend le plan
    Découverte — mieux vaut trop peu de droits qu'un accès fermé à tort.
    """
    if inscrit_le is None:
        return Abonnement(plan=Plan.DECOUVERTE)
    return Abonnement(plan=Plan.ESSAI,
                      fin=inscrit_le + timedelta(days=DUREE_ESSAI))


# ---------------------------------------------------------------------------
# L'abonnement d'un utilisateur
# ---------------------------------------------------------------------------

@dataclass
class Abonnement:
    """L'état d'un compte à un instant donné."""
    plan: Plan = Plan.LIBRE
    periode: Periode = Periode.MENSUELLE
    fin: date | None = None
    identifiant_client: str = ""        # customer Stripe
    identifiant_abonnement: str = ""    # subscription Stripe
    annule: bool = False                # résilié, mais encore valable jusqu'à `fin`

    @property
    def offre(self) -> Offre:
        return OFFRES[self.plan]

    def actif(self, au: date | None = None) -> bool:
        """
        Un abonnement résilié reste actif jusqu'au terme payé. On ne coupe
        jamais un accès déjà réglé : c'est la règle, et c'est aussi la loi
        dans la plupart des juridictions.
        """
        if self.plan in (Plan.LIBRE, Plan.DECOUVERTE):
            return True
        if self.fin is None:
            return False
        return (au or date.today()) <= self.fin

    def jours_restants(self, au: date | None = None) -> int | None:
        if self.fin is None:
            return None
        return max(0, (self.fin - (au or date.today())).days)

    def plan_effectif(self, au: date | None = None) -> Plan:
        """Le plan réellement applicable : on retombe en Découverte si expiré."""
        return self.plan if self.actif(au) else Plan.DECOUVERTE

    def offre_effective(self, au: date | None = None) -> Offre:
        return OFFRES[self.plan_effectif(au)]

    # ---- Droits ---------------------------------------------------------

    def autorise(self, fonction: str, au: date | None = None) -> bool:
        """
        Répond par oui ou par non à une fonction nommée.

        Fonctions reconnues : "scenarios", "exports", "entreprise".
        Une fonction inconnue est autorisée — on n'invente pas de restriction.
        """
        o = self.offre_effective(au)
        return {"scenarios": o.scenarios,
                "exports": o.exports,
                "entreprise": o.profil_entreprise}.get(fonction, True)

    def limite_jours(self, au: date | None = None) -> int:
        return self.offre_effective(au).jours_projection

    def limite_fichiers(self, au: date | None = None) -> int:
        return self.offre_effective(au).nb_fichiers

    def etat(self, t=None, au: date | None = None, date_lisible=None) -> str:
        """
        Une phrase à afficher, sans jargon.

        `t` traduit, `date_lisible` met la date au format du pays. Les deux
        sont injectés : ce module ne connaît ni la langue de lecture ni la
        convention de date, et « 05/09 » se lit 5 septembre en France et
        9 mai aux États-Unis.
        """
        t = t or _sans_traduction
        au = au or date.today()
        ecrire = date_lisible or (lambda j: j.strftime("%d/%m/%Y"))

        if self.plan is Plan.LIBRE:
            return t("abo.etat_libre")
        if self.plan is Plan.DECOUVERTE:
            return t("abo.etat_decouverte")
        if self.plan is Plan.ESSAI:
            restants = self.jours_restants(au)
            if not self.actif(au):
                return t("abo.etat_essai_fini")
            if restants == 0:
                return t("abo.etat_essai_dernier_jour")
            return t("abo.etat_essai", jours=restants,
                     date=ecrire(self.fin) if self.fin else "")
        if not self.actif(au):
            return t("abo.etat_expire", plan=self.offre.nom(t),
                     date=ecrire(self.fin) if self.fin else "")
        if self.annule:
            return t("abo.etat_resilie", plan=self.offre.nom(t),
                     jours=self.jours_restants(au), date=ecrire(self.fin))
        return t("abo.etat_actif", plan=self.offre.nom(t),
                 date=ecrire(self.fin))


# ---------------------------------------------------------------------------
# Configuration Stripe
# ---------------------------------------------------------------------------

@dataclass
class ConfigStripe:
    """Ce que l'application sait de Stripe. Vide = mode libre."""
    cle_secrete: str = ""
    prix: dict[tuple[Plan, Periode], str] = field(default_factory=dict)
    url_retour: str = "http://localhost:8501"

    @property
    def configure(self) -> bool:
        return bool(self.cle_secrete) and bool(self.prix)

    def identifiant_prix(self, plan: Plan, periode: Periode) -> str | None:
        return self.prix.get((plan, periode))


def _depuis(source: dict, cle: str, defaut: str = "") -> str:
    valeur = source.get(cle, defaut)
    return str(valeur) if valeur is not None else defaut


def charger_configuration(secrets: dict | None = None) -> ConfigStripe:
    """
    Lit la configuration dans les secrets Streamlit, sinon dans
    l'environnement. Ne lève jamais d'exception : une configuration absente
    est un cas normal, pas une erreur.
    """
    source: dict = {}
    if secrets:
        source = dict(secrets)
    else:
        try:
            import streamlit as st
            source = dict(st.secrets.get("stripe", {}))
        except Exception:
            source = {}

    if not source:
        source = {c: os.environ.get(f"PREVUFLOW_{c.upper()}", "")
                  for c in ("cle_secrete", "url_retour",
                            "prix_particulier_mensuel", "prix_particulier_annuel",
                            "prix_entreprise_mensuel", "prix_entreprise_annuel")}

    prix: dict[tuple[Plan, Periode], str] = {}
    for plan, prefixe in ((Plan.PARTICULIER, "particulier"),
                          (Plan.ENTREPRISE, "entreprise")):
        for periode, suffixe in ((Periode.MENSUELLE, "mensuel"),
                                 (Periode.ANNUELLE, "annuel")):
            identifiant = _depuis(source, f"prix_{prefixe}_{suffixe}")
            if identifiant:
                prix[(plan, periode)] = identifiant

    return ConfigStripe(
        cle_secrete=_depuis(source, "cle_secrete"),
        prix=prix,
        url_retour=_depuis(source, "url_retour", "http://localhost:8501"),
    )


# ---------------------------------------------------------------------------
# Paiement
# ---------------------------------------------------------------------------

class ErreurPaiement(Exception):
    """Le paiement n'a pas pu être engagé. Le message est destiné à l'écran."""


def ouvrir_paiement(plan: Plan, periode: Periode, config: ConfigStripe,
                    t=None, email: str = "",
                    identifiant_client: str = "") -> str:
    """
    Crée une session de paiement Stripe et renvoie l'adresse où envoyer
    l'utilisateur.

    Aucune donnée de carte ne transite par PrevuFlow : la saisie a lieu sur les
    pages de Stripe. C'est ce qui nous dispense des obligations PCI-DSS.
    """
    t = t or _sans_traduction

    if not config.configure:
        raise ErreurPaiement(t("abo.err_non_configure"))

    identifiant_prix = config.identifiant_prix(plan, periode)
    if not identifiant_prix:
        raise ErreurPaiement(t("abo.err_tarif_absent",
                               plan=OFFRES[plan].nom(t),
                               periode=t("abo." + periode.value)))

    try:
        import stripe
    except ImportError:
        raise ErreurPaiement(t("abo.err_stripe_absent"))

    stripe.api_key = config.cle_secrete

    parametres = {
        "mode": "subscription",
        "line_items": [{"price": identifiant_prix, "quantity": 1}],
        "success_url": f"{config.url_retour}?paiement=ok",
        "cancel_url": f"{config.url_retour}?paiement=annule",
        "allow_promotion_codes": True,
        "client_reference_id": identifiant_client or None,
        "metadata": {"plan": plan.value, "periode": periode.value,
                     "produit": "prevuflow"},
    }
    if identifiant_client:
        parametres["customer"] = identifiant_client
    elif email:
        parametres["customer_email"] = email

    try:
        session = stripe.checkout.Session.create(
            **{k: v for k, v in parametres.items() if v is not None})
    except Exception as erreur:
        raise ErreurPaiement(t("abo.err_stripe_refus", erreur=erreur))

    return session.url


def trouver_client(email: str, config: ConfigStripe) -> str:
    """
    Retrouve l'identifiant du client Stripe à partir de son adresse.

    Sans cela, l'application ne saurait rien de ce qu'un visiteur vient de
    payer tant que le webhook n'est pas branché : il réglerait son
    abonnement et retrouverait l'écran de vente inchangé. Une recherche par
    adresse coûte un appel et évite ce moment-là.

    Rend une chaîne vide si personne ne correspond, ou si Stripe est
    indisponible : ce n'est pas une erreur, c'est le cas du visiteur qui
    n'a jamais payé.
    """
    if not config.configure or not email:
        return ""
    try:
        import stripe
        stripe.api_key = config.cle_secrete
        clients = stripe.Customer.list(email=email, limit=1)
    except Exception:
        return ""
    return clients.data[0].id if clients.data else ""


def lire_abonnement(identifiant_client: str, config: ConfigStripe) -> Abonnement:
    """
    Interroge Stripe et renvoie l'état réel de l'abonnement.

    En cas d'indisponibilité de Stripe, on renvoie le plan Découverte plutôt
    que de lever une exception : une panne de notre côté ne doit pas afficher
    une erreur incompréhensible à quelqu'un qui a payé.
    """
    if not config.configure or not identifiant_client:
        return Abonnement(plan=Plan.LIBRE)

    try:
        import stripe
        stripe.api_key = config.cle_secrete
        liste = stripe.Subscription.list(customer=identifiant_client,
                                         status="all", limit=10)
    except Exception:
        return Abonnement(plan=Plan.DECOUVERTE)

    vivants = [a for a in liste.data
               if a.status in ("active", "trialing", "past_due")]
    if not vivants:
        return Abonnement(plan=Plan.DECOUVERTE,
                          identifiant_client=identifiant_client)

    a = max(vivants, key=lambda x: x.get("current_period_end", 0))
    metadonnees = a.get("metadata") or {}
    valeur = metadonnees.get("plan", "")
    plan = Plan(valeur) if valeur in {p.value for p in Plan} else Plan.PARTICULIER

    # À défaut de métadonnée, on retrouve le plan par l'identifiant de tarif.
    if not valeur:
        try:
            prix_utilise = a["items"]["data"][0]["price"]["id"]
            for (p, _), identifiant in config.prix.items():
                if identifiant == prix_utilise:
                    plan = p
                    break
        except Exception:
            pass

    fin = None
    horodatage = a.get("current_period_end")
    if horodatage:
        fin = datetime.fromtimestamp(horodatage).date()

    periode_valeur = metadonnees.get("periode", "")
    periode = (Periode(periode_valeur) if periode_valeur in {p.value for p in Periode}
               else Periode.MENSUELLE)

    return Abonnement(
        plan=plan,
        periode=periode,
        fin=fin,
        identifiant_client=identifiant_client,
        identifiant_abonnement=a.get("id", ""),
        annule=bool(a.get("cancel_at_period_end")),
    )


def portail_client(identifiant_client: str, config: ConfigStripe,
                   t=None) -> str:
    """
    Adresse du portail Stripe où l'utilisateur gère lui-même sa carte,
    ses factures et sa résiliation. Nous n'avons rien à construire pour cela,
    et surtout rien à stocker.
    """
    t = t or _sans_traduction
    if not config.configure or not identifiant_client:
        raise ErreurPaiement(t("abo.err_sans_facturation"))
    try:
        import stripe
        stripe.api_key = config.cle_secrete
        session = stripe.billing_portal.Session.create(
            customer=identifiant_client, return_url=config.url_retour)
        return session.url
    except Exception as erreur:
        raise ErreurPaiement(t("abo.err_portail", erreur=erreur))
