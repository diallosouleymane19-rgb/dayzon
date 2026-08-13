# Politique de confidentialité

**PrevuFlow — SMD GLOBAL CONSULTING LLC**
Version 1.0 · en vigueur au 13 août 2026

> ⚠️ **À faire relire avant publication.** Ce document décrit fidèlement ce
> que fait le logiciel — chaque affirmation ci-dessous est vérifiable dans
> le code. Sa conformité formelle au RGPD, en revanche, doit être validée
> par un professionnel : la base légale retenue, la durée de conservation
> et la question du transfert hors Union européenne méritent un examen.

---

## Le principe

Vos données financières sont les vôtres. PrevuFlow en a besoin pour
calculer, pas pour les exploiter. Elles ne sont ni vendues, ni louées, ni
cédées à quiconque à des fins commerciales ou publicitaires.

## Qui est responsable du traitement

**SMD GLOBAL CONSULTING LLC** — EIN 30-1497639, Wyoming, États-Unis.
Contact : **contact@smdconsulting.pro**

## Ce que nous traitons, et pourquoi

| Donnée | Pourquoi | Base légale |
|---|---|---|
| Adresse électronique | créer le compte, ouvrir une session, réinitialiser un mot de passe | exécution du contrat |
| Mot de passe | authentifier — stocké chiffré par Supabase, jamais visible de nous | exécution du contrat |
| Comptes, opérations, taux de change | calculer votre solde prévisionnel | exécution du contrat |
| Fichiers déposés (relevés, factures) | en extraire les mouvements | exécution du contrat |
| Formule d'abonnement, identifiant client Stripe | ouvrir les fonctions payées, facturer | exécution du contrat |
| Nombre de fichiers importés dans le mois | appliquer la limite de la formule | intérêt légitime |

**Nous ne collectons pas** vos identifiants bancaires, ni votre numéro de
carte, ni votre localisation, ni de données de navigation à des fins
publicitaires. Aucun traceur publicitaire n'est déposé.

## Sans compte, rien ne sort de votre appareil

PrevuFlow s'utilise sans inscription. Dans ce cas, les données saisies
restent dans la mémoire de votre navigateur et disparaissent à la
fermeture. Rien n'est transmis ni conservé.

## Avec un compte

Les données sont conservées chez **Supabase**, sur des serveurs situés
dans l'**Union européenne** (région Paris, eu-west-3).

L'isolation entre utilisateurs n'est pas assurée par le logiciel mais par
la base de données elle-même, au moyen de politiques de sécurité au
niveau des lignes. Concrètement : une requête ne peut pas rendre les
données d'un autre compte, même en cas de défaut dans le code de
l'application.

## Qui d'autre intervient

| Prestataire | Rôle | Où |
|---|---|---|
| Supabase | base de données, authentification | Union européenne |
| Streamlit (Snowflake Inc.) | hébergement de l'application | États-Unis |
| Stripe, Inc. | paiement et facturation | États-Unis |
| Resend | envoi des courriers électroniques du service | États-Unis |

Ces prestataires n'accèdent à vos données que pour fournir leur service.
Les transferts vers les États-Unis reposent sur les cadres contractuels
proposés par ces prestataires.

> ⚠️ Point à valider avec un juriste : la qualification exacte de ces
> transferts et les garanties applicables (clauses contractuelles types,
> *Data Privacy Framework*).

## Combien de temps

- **Données du compte** : tant que le compte existe.
- **Après suppression du compte** : effacement des données associées.
- **Traces de facturation** : conservées par Stripe selon ses propres
  obligations comptables et fiscales, qui s'imposent à nous.

## Vos droits

Vous pouvez demander l'accès à vos données, leur rectification, leur
effacement, leur portabilité, ou vous opposer à un traitement. Une seule
adresse : **contact@smdconsulting.pro**. Réponse sous trente jours.

Deux de ces droits s'exercent sans nous écrire :

- **Portabilité** : le bouton « Télécharger mes données » produit un
  fichier JSON lisible contenant tout ce que vous avez saisi.
- **Effacement** : la suppression du compte efface les données associées.

Si notre réponse ne vous satisfait pas, vous pouvez saisir l'autorité de
protection des données de votre pays de résidence — en France, la CNIL.

## Sécurité

- Les échanges sont chiffrés (HTTPS).
- Les mots de passe sont chiffrés par Supabase ; nous ne les voyons
  jamais.
- La longueur minimale d'un mot de passe est de huit caractères.
- Les clés d'accès aux services tiers sont limitées au strict nécessaire :
  la clé Stripe utilisée par l'application ne permet ni de lire vos
  clients, ni de déplacer de l'argent.

Aucun système n'est infaillible. En cas de violation de données
susceptible d'engendrer un risque élevé pour vos droits, vous serez
informé sans délai injustifié.

## Cookies

PrevuFlow ne dépose aucun cookie publicitaire ni de mesure d'audience.
Seuls sont utilisés les cookies techniques nécessaires au maintien de
votre session.

## Modifications

Toute modification substantielle sera notifiée par courrier électronique
aux titulaires d'un compte, trente jours avant son entrée en vigueur.
