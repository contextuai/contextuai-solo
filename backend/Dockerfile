FROM python:3.11-slim

WORKDIR /app

# System deps for weasyprint
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV CONTEXTUAI_MODE=desktop
ENV HOST=0.0.0.0
ENV PORT=18741

EXPOSE 18741

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "18741"]
