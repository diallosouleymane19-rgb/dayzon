# PrevuFlow — image de production
#
# Streamlit Community Cloud endort les applications apres douze heures sans
# visite. Pour un produit vendu par abonnement, un client qui tombe sur
# « Zzzz » est un client perdu. Cette image tourne sur un hebergeur qui ne
# dort pas.

FROM python:3.12-slim

# Sans ces deux variables, Python ecrit des fichiers .pyc inutiles dans le
# conteneur et retient les journaux en memoire : on les veut immediats.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Les dependances d'abord, seules : cette couche est mise en cache et n'est
# reconstruite que si requirements.txt change. Un deploiement qui ne touche
# qu'au code prend alors quelques secondes.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY . .

# L'hebergeur impose le port par la variable PORT. On garde 8501 comme
# valeur de repli pour un lancement local.
ENV PORT=8501
EXPOSE 8501

# --server.address=0.0.0.0 est indispensable : par defaut Streamlit
# n'ecoute que sur la boucle locale et le conteneur serait injoignable.
# --server.headless evite qu'il tente d'ouvrir un navigateur au demarrage.
CMD streamlit run app_tresorerie.py \
    --server.port=$PORT \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false
