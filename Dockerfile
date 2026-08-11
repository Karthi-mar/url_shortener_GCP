#----------Stage 1-------------------------- Install all the dependencies
FROM python:3.12-slim AS builder

WORKDIR /app

COPY app/requirements.txt .

RUN pip install --no-cache-dir --user -r requirements.txt

#----------------Stage 2 ---------------------------minimal runtime image

FROM python:3.12-slim

RUN useradd --create-home appuser  #creating a appuser instead of root user for security reasons
WORKDIR /app

#only copies the pip , libraries and not the caches and all
COPY --from=builder /root/.local /home/appuser/.local
COPY app/main.py .

#as gunicorn exists in appuser/.local , while running it should read this first
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PORT=8080

USER appuser
EXPOSE 8080

CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 main:app