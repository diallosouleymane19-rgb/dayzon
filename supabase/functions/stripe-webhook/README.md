# Webhook Stripe

La fonction est deployee sur Supabase (Edge Functions), pas dans ce depot :
Streamlit ne sait pas recevoir une requete HTTP, il n'expose aucune route.

- Adresse : `https://tdbayrzyzcvnletxcyvj.supabase.co/functions/v1/stripe-webhook`
- Evenements ecoutes : `checkout.session.completed`,
  `customer.subscription.updated`, `customer.subscription.deleted`
- Verification du JWT Supabase : **desactivee**. Stripe n'en envoie pas ;
  le controle est la signature Stripe, verifiee dans la fonction.
- Secrets attendus (Supabase -> Edge Functions -> Secrets) :
  `STRIPE_CLE` et `STRIPE_WEBHOOK`.

Le code source vit dans le tableau de bord Supabase. Il n'est pas recopie
ici pour eviter deux versions qui divergent en silence.
