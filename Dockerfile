FROM python:3.12-slim

# Create non-root user (UID 1000) required by Hugging Face Spaces Docker SDK
RUN useradd -m -u 1000 user

# Preserve <project_root>/backend layout so EPN checkpoint resolution
# (Path(__file__).resolve().parents[4] / "backend/models/checkpoints/epn_model.pth")
# works identically to local execution without modifying research code.
WORKDIR /home/user/app/backend

COPY --chown=user:user backend/requirements.txt /home/user/app/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /home/user/app/backend/requirements.txt

COPY --chown=user:user backend/app /home/user/app/backend/app
COPY --chown=user:user backend/data /home/user/app/backend/data
COPY --chown=user:user backend/models /home/user/app/backend/models

USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONPATH=/home/user/app/backend \
    PORT=7860 \
    CORS_ORIGINS=*

EXPOSE 7860

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
