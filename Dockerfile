FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends nodejs && rm -rf /var/lib/apt/lists/*
COPY ["Server Requirements.txt", "/app/Server Requirements.txt"]
RUN pip install --no-cache-dir -r "Server Requirements.txt"
COPY public ./public
COPY server ./server
RUN useradd --create-home --uid 10001 petromind
USER petromind
EXPOSE 10000
CMD ["python", "server/Scientific Server.py"]
