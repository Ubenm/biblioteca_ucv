FROM python:3.9
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y wait-for-it
RUN mkdir -p /app/uploads && chmod 777 /app/uploads  # Añadir esto
COPY . .
CMD ["sh", "-c", "wait-for-it db:3306 --timeout=30 -- python app.py"]