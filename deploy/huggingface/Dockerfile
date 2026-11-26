# RetailPulse live API for Hugging Face Spaces (Docker SDK). Spaces run containers as uid 1000 and expose app_port 7860.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    RP_ENV=prod RP_DATA_DIR=/home/user/app/data RP_ARTIFACTS_DIR=/home/user/app/artifacts MPLCONFIGDIR=/tmp/mpl

RUN useradd -m -u 1000 user
USER user
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --user -r requirements.txt
ENV PATH="/home/user/.local/bin:$PATH"

COPY --chown=user retailpulse ./retailpulse
COPY --chown=user sql ./sql
COPY --chown=user web ./web
# Build the warehouse and train the models at image build time (synthetic data, seed 42): fast cold starts.
RUN python -m retailpulse.cli run-all

EXPOSE 7860
# RP_ENV=prod refuses to start without RP_API_KEYS (a Space secret). RP_CORS_ORIGINS (a Space variable) lists the website origin.
CMD ["python", "-m", "retailpulse.cli", "serve", "--host", "0.0.0.0", "--port", "7860"]
